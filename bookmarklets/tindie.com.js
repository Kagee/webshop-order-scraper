/*1. Open item page
2. Let page load
3. Click on first gallery image, and let it load
4. Open bookmarklet
5. Copy filename from prompt
2. Save PDF in the scraper-cache/tindie/pdfs/ folder
*/
javascript:(function(){
	document.querySelector("div.control-wrapper button").click(); 
	document.querySelector('footer').remove();
	document.querySelectorAll('iframe').forEach(function(e){e.remove()});
	document.querySelectorAll("div.page-wrap").forEach(function(e){e.remove()});
	document.querySelectorAll("div.alert").forEach(function(e){e.remove()});
	document.querySelectorAll("div.seller-products").forEach(function(e){e.remove()});
	document.querySelector("div.container").style.width="100%";
	document.querySelector("div.gallery").parentElement.style.width="100%";
	document.querySelector("#related_products").remove();
	document.querySelector("#product-reviews").remove();
	document.querySelectorAll("#product-description img").forEach(function(e){
		e.parentElement.style.pageBreakInside="avoid"; 
		e.style.height="unset";  
		e.style.maxHeight="180mm";
		e.style.maxWidth="180mm";
		});
	document.querySelectorAll("*").forEach(function (e) {e.style.fontFamily = "unset";});
	document.querySelector("#product-photo-carousel").addEventListener("loadeddata", (event) => {alert("foo");});
	document.querySelectorAll("#product_photo_zoom_carousel img").forEach(function(e){
		i = document.createElement('img');
		p = document.createElement('p');
		p.style.pageBreakInside="avoid";
		p.appendChild(i);
		i.src=e.srcset.split(",").at(-2).trim().split(" ")[0];
		i.style.maxHeight="180mm";
		i.style.maxWidth="180mm";
		document.querySelector("#product-well").after(p);
	});
	setTimeout(function() {
		document.querySelector("div.gallery").remove();
		document.querySelector("div.sharing-links").remove();
	}, 1000);
	setTimeout(function() { 
		prompt("Save PDF as",document.location.href.replace("https://www.tindie.com/products/", "").replace(/([^/]*)\/([^/]*).*/,function(m,p1,p2){return p1 + "_"+p2+".pdf";}));
		window.print();
	 }, 2000);
})()