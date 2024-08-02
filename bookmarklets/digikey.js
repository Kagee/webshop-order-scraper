/*
1. Open item page when instructed
2. Let page load
3. Run  bookmarklet
4. Ctrl+P
5. Open temporary PDF in other browser to check quality
6. Download/open other attachments.
*/
javascript:(function(){
function rx(xpath) {
    f = document.evaluate(
        xpath,
        document.body,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE
        ).singleNodeValue;
    if (f) {
        f.remove();
    } else {
        console.log("Failed to remove " + xpath);
    }
};
document.querySelectorAll("*").forEach(
(el) => {
    el.style.fontFamily = "unset";
    el.style.background = "unset";
    el.style.backgroundImage = "unset";
    el.style.boxShadow = "unset";
    }
);
document.querySelectorAll("a").forEach(
(el) => {
    if (el.href != "") {
        el.innerHTML = el.innerHTML + ` (${el.href})`
    }
    }
);
[
    '//div[@data-testid="sub-header-container"]/parent::div',
    '//header',
    '//div[@id="footer"]/parent::div',
    '//div[@data-evg="product-details-association-AlsoEvaluated"]',
    '//div[@data-evg="price-procurement-wrapper"]',
    '//div[@data-testid="card-association"]',
    '//div[@id="product-details-alt-pack-types"]',
].forEach((e) => {rx(e);});
document.querySelectorAll('img[data-testid]').forEach((e)=>{
    var img = document.createElement('img');
    img.src = e.src;
    document.querySelector("body").appendChild(img);
});
})()