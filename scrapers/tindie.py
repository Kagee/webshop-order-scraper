# pylint: disable=unused-import
import contextlib
import re
import time
import urllib.request
from datetime import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Final, List  # noqa: UP035

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from .base import BaseScraper

# pylint: disable=unused-import
from .utils import AMBER, RED

if TYPE_CHECKING:
    from selenium.webdriver.remote.webelement import WebElement


class TindieScraper(BaseScraper):
    tla: Final[str] = "TND"
    name: Final[str] = "Tindie"
    simple_name: Final[str] = "tindie"

    def __init__(self, options: dict):
        super().__init__(options, __name__)
        self.setup_cache(self.simple_name)
        self.setup_templates()

    def command_scrape(self):
        order_dict = self.browser_scrape_order_list()

    def browser_scrape_order_list(self):
        if self.options.use_cached_orderlist and self.can_read(
            self.ORDER_LIST_JSON,
        ):
            order_dict = self.read(self.ORDER_LIST_JSON, from_json=True)
        else:
            order_dict = {}
            _brws = self.browser_visit(
                "https://www.tindie.com/orders/purchases/",
            )
            csss = "main table.table tbody tr"
            order_trs: WebElement = self.find_elements(
                By.CSS_SELECTOR,
                csss,
            )

            for order_tr in order_trs:
                order = {}
                tds: List[WebElement] = order_tr.find_elements(  # noqa: UP006
                    By.TAG_NAME,
                    "td",
                )
                # td1 a.text = #<order_id>
                order["id"] = tds[0].text[1:]
                self.log.debug("Order ID: %s", order["id"])

                # td2.text = order date 27 Jun 2023
                order["date"] = dt.strptime(
                    tds[1].text,
                    "%d %b %Y",
                ).astimezone()
                self.log.debug("Order date: %s", order["date"])

                csss = "div.row"
                item_divs: List[WebElement] = tds[2].find_elements(  # noqa: UP006
                    By.CSS_SELECTOR,
                    csss,
                )
                # td3 div -> order item ->
                #     div (3 stk):

                items = []
                for item_div in item_divs:
                    item = {}
                    item_cols: List[WebElement] = item_div.find_elements(  # noqa: UP006
                        By.TAG_NAME,
                        "div",
                    )
                    #     -div1 <a href="/products/hamstudio/ham-ch552-micro/">Ham CH552 Micro</a>
                    item_a = item_cols[0].find_element(By.TAG_NAME, "a")
                    item["name"] = item_a.text
                    item["id"] = re.sub(
                        "http.*/products/",
                        "",
                        item_a.get_attribute("href"),
                    )[:-1]
                    self.log.debug(
                        "Item id: %s, Item name: %s",
                        item["id"],
                        item["name"],
                    )
                    #     -div2 : ignore?
                    #     -div3: line1: order status, line 2: status date, line x in small: tracking name or url(href)
                    item_tracking_info = []
                    tracking_small_element: WebElement = None
                    with contextlib.suppress(NoSuchElementException):
                        tracking_small_element = item_cols[2].find_element(
                            By.TAG_NAME,
                            "small",
                        )

                        if tracking_small_element:
                            tracking_a: WebElement = None
                            with contextlib.suppress(NoSuchElementException):
                                tracking_a = (
                                    tracking_small_element.find_element(
                                        By.TAG_NAME,
                                        "a",
                                    )
                                )
                            for (
                                line
                            ) in tracking_small_element.text.splitlines():
                                sline = line.strip()
                                if sline and "Track Your Package" not in sline:
                                    item_tracking_info.append(sline)
                            if tracking_a:
                                item_tracking_info.append(
                                    tracking_a.get_attribute("href"),
                                )
                        else:
                            self.log.warning("No tracking info")
                        self.browser.execute_script(
                            """
                                arguments[0].remove();
                            """,
                            tracking_small_element,
                        )
                    item["extra_data"] = {}
                    item["extra_data"]["status"] = " ".join(
                        item_cols[2].text.splitlines(),
                    )
                    self.log.warning(
                        "Item status: %s",
                        item["extra_data"]["status"],
                    )
                    if item_tracking_info:
                        item_tracking_info = "; ".join(item_tracking_info)
                        item["extra_data"]["tracking"] = item_tracking_info
                        self.log.debug(
                            "Item tracking info: %s",
                            item["extra_data"]["tracking"],
                        )
                    items.append(item)
                order["items"] = items
                # td4.text order total $43.00
                order_total = self.get_value_currency("total", tds[3].text)
                self.log.debug("Order total: %s", order_total)
                order_dict[order["id"]] = order

        self.write(self.ORDER_LIST_JSON, order_dict, to_json=True)
        return order_dict

    def browser_save_item_page(self, item_id: str, order_dir: Path):
        item_pdf_file = order_dir / f"item-{item_id}.pdf"

        if self.can_read(item_pdf_file):
            self.log.debug("Found PDf for item %s", item_id)
            return
        self.log.debug("Visiting item %s", item_id)
        brws = self.browser_visit(
            f"https://www.komplett.no/product/{item_id}?noredirect=true",
        )
        thumbs = self.find_elements(
            By.CSS_SELECTOR,
            "div.product-images__thumb-carousel img",
        )
        if len(thumbs) > 0:
            thumb_src = thumbs[0].get_attribute("src")
            for thumb in thumbs:
                thumb_src = thumb.get_attribute("src")
                if not re.search(r"_\d*\.", thumb_src):
                    break
        else:
            thumb_src = self.find_element(
                By.CSS_SELECTOR,
                "div.product-images__main-carousel"
                " div.medium-image-carousel img",
            ).get_attribute("src")
        self.browser_get_item_thumb(order_dir, item_id, thumb_src)
        self.browser_cleanup_item_page()
        self.clear_folder()
        brws.execute_script("window.print();")
        files = self.wait_for_files("*.pdf")
        assert len(files) == 1, "Got more than one file when printing item PDF"
        file = files[0]
        self.move_file(file, item_pdf_file)
        self.log.debug("Saved PDF print of item page for %s", item_id)

    def browser_get_item_thumb(self, order_dir, item_id, src, order_page=False):
        thumb_url = re.sub(
            r"(.*)(/p/\d*/)(.*)",
            "\\1/p/1000/\\3",
            src,
        )
        if order_page:
            image_path = Path(order_dir) / f"item-{item_id}-order-thumb.jpg"
        else:
            image_path = Path(order_dir) / f"item-{item_id}-thumb.jpg"

        if not self.can_read(image_path):
            self.log.debug("Downloading %s", thumb_url)

            self.browser.execute_script(
                """
                            dwimg = document.createElement('img');
                            dwimg.src = arguments[0];
                            dwimg.id = "image-to-download"
                            document.body.appendChild(dwimg);
                        """,
                thumb_url,
            )
            # Wait for image load
            wait_count = 0
            while True:
                self.log.debug("Waiting for image to download")
                time.sleep(2)
                if (
                    int(
                        self.browser.execute_script(
                            """
                                return document.querySelector('#image-to-download').naturalWidth
                            """,
                        ),
                    )
                    > 0
                ):
                    # .complete does not work in Firefox sometimes?
                    break
                wait_count += 1
                if wait_count > 60:
                    self.log.error(
                        RED(
                            "We have been waiting for a file for 3 minutes,"
                            " something is wrong...",
                        ),
                    )
                    msg = f"{thumb_url}"
                    raise NotImplementedError(msg)
            image_dataurl: str = self.browser.execute_script(
                """
                            const canvas = document.createElement('canvas');
                            dwimg = document.querySelector('#image-to-download');
                            canvas.width = dwimg.naturalWidth;
                            canvas.height = dwimg.naturalHeight;
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(dwimg, 0, 0);
                            img_data = canvas.toDataURL('image/jpeg');
                            dwimg.remove()
                            canvas.remove()
                            return img_data
                        """,
            )

            # data:image/jpeg;base64,
            assert len(image_dataurl) > 23
            self.log.debug(image_dataurl[0:50])
            response = urllib.request.urlopen(image_dataurl)
            self.write(image_path, response.file.read(), binary=True)
            self.log.debug("Thumbnail for %s saved to %s", item_id, image_path)
        else:
            self.log.debug("Thumbnail for %s found", item_id)

    def browser_cleanup_item_page(self):
        brws = self.browser_get_instance()
        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")

        time.sleep(2)
        brws.execute_script(
            r"""
            // shuffle some stuff
            mc = document.querySelector('main#MainContent');
            bdy = document.querySelector('body');
            bdy.prepend(mc);
            while (bdy.lastChild != mc) { bdy.lastChild.remove(); }

            // remove some obvious stuff
            [
            'div.menu-bar',
            'div.breadcrumbs-wrapper',
            'section.reviews',
            'div.comparison-widget-wrapper',
            'div.alert-wrapper',
            'div#videoly-videobox-placeholder',
            'videoly-tape'
            ].forEach((e) => {f=document.querySelector(e); if(f){f.remove()}});

            // remove some obvious stuff #2
            [
            'div.recommendations-extended'
            ].forEach((e) => {
                document.querySelectorAll(e).forEach((f) =>{
                f.parentElement.remove();
                })
            });

            // remove evernything but some stuyff we don't
            document.querySelectorAll("div.productMainInfo-completeGrid > div").forEach(
            (e) => {
            keep = ['webtext1','productCarusel','hightlights'];
            for (let i = 0; i < keep.length; i++) {
                f=e.getAttribute("class").toLowerCase()
                if ( f.search(keep[i].toLowerCase()) >= 0 ) {return;}}
                e.remove();
            }
            );

            document.querySelector("div.product-sections-left").style.width="100%" ;

            // custom font can make print difficult
            document.querySelectorAll('*').forEach(function(e){
                                e.style.fontFamily = "sans-serif";
                                e.style.lineHeight = "1";
                            });


            document.querySelectorAll("div.product-section-content").forEach(function(e){
            e.style.display="block";
            e.style.float="unset";
            })

            document.querySelectorAll("div.product-section-content div").forEach(function(e){
            e.style.float="unset";
            })


            document.querySelectorAll("figure").forEach(function(e){e.style.pageBreakInside="avoid";})


            document.body.style.display="unset";
            document.querySelector("div.productMainInfo-completeGrid").style.display="unset";


            images=new Set();
            main_image = null;

            carousel = document.querySelectorAll("div.product-images__thumb-carousel img");
            if (carousel.length) {
            document.querySelectorAll("div.product-images__thumb-carousel img").forEach(
                function(e){
                images.add(e.src.replace(/p\/\d*\//, 'p/1000/'));
                }
            );
            main_image = images[0];
            images.forEach((e)=>{if (e.search('_\d*\.') == -1) {main_image =e;}});
            } else {
            main_image = document.querySelector("div.product-images__main-carousel div.medium-image-carousel img").src.replace(/p\/\d*\//, 'p/1000/');
            }

            images.delete(main_image)

            dpi = document.querySelector("div.product-images")
            while (dpi.lastChild) { dpi.lastChild.remove(); }

            img = document.createElement("img");
            img.src=main_image;
            img.style.maxWidth="100%"
            dpi.appendChild(img);


            document.body.lastChild.appendChild(document.createElement("br"));
            document.body.lastChild.appendChild(document.createElement("br"));
            document.body.lastChild.appendChild(document.createElement("br"));
            images.forEach((e) => {
            img = document.createElement("img");
            img.src=e;
            img.style.maxWidth="100%"
            img.style.pageBreakInside="avoid";
            document.body.lastChild.appendChild(img);

            });

            document.querySelectorAll("div.product-section-content img").forEach(function(e){
            e.style.pageBreakInside="avoid";
            e.parentElement.style.pageBreakInside="avoid";
            })



            document.querySelectorAll("iframe").forEach(function(e){
            video = e.src
            if (!video.startsWith("https://www.youtube")) { return;}
            parent = e.parentElement;
            np = parent;
            e.remove();
            video_parent = null;
            for (let i = 0; i < 10; i++) {
                c = np.parentElement.getAttribute("class");
                if (c && (c.toLowerCase().search('video') >= 0)){
                    if (!np.parentElement) {
                            return
                    }
                    video_parent = np.parentElement;
                }
                np = np.parentElement;
            }
            if (video_parent) {
                parent = video_parent.parentElement;
            }
            p = document.createElement("p");
            p.className ="youtube-replacement"
            p.innerText = video;
            if (parent.querySelectorAll("iframe").length == 0) {
                if (video_parent) {
                    while (video_parent.lastChild) {
                        video_parent.lastChild.remove();
                    }
                }
            }
            parent.parentElement.appendChild(p);
            })
        """,
        )
        time.sleep(2)
        brws.execute_script(
            """
            [
            'videoly-tape'
            ].forEach((e) => {f=document.querySelector(e); if(f){f.remove()}});
        """,
        )
        time.sleep(1)
        brws.execute_script(
            """
            document.querySelectorAll("button.read-more-toggle").forEach(function(e){e.scrollIntoView();e.click();})
        """,
        )

    def browser_detect_handle_interrupt(self, _):
        brws = self.browser_get_instance()
        if "login" in brws.current_url:
            self.log.error(
                AMBER(
                    "Please manyally login to Tindie, "
                    "and press ENTER when finished.",
                ),
            )
            input()

    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDER_LIST_JSON = self.cache["BASE"] / "order_list.json"
        self.ORDER_FOLDER_TP = str(self.cache["BASE"] / "orders/{order_id}/")
        self.ORDER_URL = "https://www.tindie.com/orders/purchases/{order_id}/"

    def command_to_std_json(self):
        structure = self.get_structure(
            self.name,
            None,
            "https://www.tindie.com/orders/purchases/{order_id}/",
            "https://www.tindie.com/products/{item_id}",
        )
        self.output_schema_json(structure)
