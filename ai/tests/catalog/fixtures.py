"""사이트 종류별 합성 HTML.

실제 사이트에서 받은 것이 아니라 플랫폼의 알려진 표지와 주소 모양만 흉내 냈다.

실제 사이트와의 차이는 12단계의 사이트별 점검에서 확인한다.
"""

BASE = "https://shop.example"


def page(body: str, head: str = "", charset: str = "utf-8") -> str:
    return (
        f'<!doctype html><html lang="ko"><head><meta charset="{charset}">{head}</head>'
        f"<body>{body}</body></html>"
    )


CAFE24_PRODUCT = page(
    '<div class="xans-product xans-product-detail"><h2>쥬시 래스팅 틴트</h2></div>',
    "<script>var EC_FRONT_JS_CONFIG = {};</script>"
    '<link rel="stylesheet" href="//img.echosting.cafe24.com/ec/base.css">',
)
SHOPIFY_PRODUCT = page(
    '<div class="shopify-section"><h1>Blush</h1></div>',
    '<script src="https://cdn.shopify.com/s/files/1/theme.js"></script>'
    "<script>Shopify.theme = {name: 'dawn'};</script>",
)
WOOCOMMERCE_PRODUCT = page(
    '<form class="variations_form cart" data-product_variations="[]"></form>',
    '<link rel="stylesheet" href="/wp-content/plugins/woocommerce/assets/css/woocommerce.css">',
)
MAKESHOP_PRODUCT = page(
    '<a href="/shop/shopdetail.html?branduid=1001">상품</a>',
    '<script src="/js/makeshop_common.js"></script>',
    charset="euc-kr",
)
GODOMALL_PRODUCT = page(
    '<a href="/goods/goods_view.php?goodsNo=2002">상품</a>',
    "<!-- godomall5 -->",
)
YOUNGCART_PRODUCT = page(
    '<a href="/shop/item.php?it_id=3003">상품</a>',
    '<script>var g5_url = "https://shop.example";</script>',
)
SITECORE_PRODUCT = page(
    '<img src="/-/media/Images/3ce/main.jpg">',
    '<meta name="generator" content="Sitecore">',
)
UNKNOWN_PAGE = page("<p>안녕하세요</p>")
MIXED_PAGE = page(
    "<p>cdn.shopify.com woocommerce</p>",
)


def cafe24_listing(items: list[tuple[int, str]]) -> str:
    """Cafe24 목록 모양: 상품 번호와 이름. 이름은 링크 안의 span에 둔다."""
    anchors = "".join(
        f'<li><p class="name"><a href="/product/item-{number}/{number}/category/24/display/1/">'
        f"<span>{title}</span></a></p></li>"
        for number, title in items
    )
    return page(f'<ul class="prdList">{anchors}</ul>', "<script>EC_FRONT</script>")


def shopify_listing(items: list[tuple[str, str]]) -> str:
    anchors = "".join(
        f'<a href="/collections/all/products/{handle}">{title}</a>' for handle, title in items
    )
    return page(anchors, '<script src="https://cdn.shopify.com/x.js"></script>')


def woocommerce_listing(items: list[tuple[str, str]]) -> str:
    anchors = "".join(
        f'<li class="product"><a href="/product/{slug}/">{title}</a></li>' for slug, title in items
    )
    return page(f"<ul>{anchors}</ul>", '<link href="/wp-content/plugins/woocommerce/x.css">')


def cafe24_home(categories: list[tuple[str, int]]) -> str:
    nav = "".join(f'<a href="/category/{slug}/{number}/">{slug}</a>' for slug, number in categories)
    return page(f"<nav>{nav}</nav>", "<script>EC_FRONT</script>")


def urlset(entries: list[tuple[str, str | None]]) -> str:
    body = ""
    for loc, title in entries:
        image = (
            f"<image:image><image:loc>https://x/i.jpg</image:loc><image:title>{title}</image:title>"
            "</image:image>"
            if title
            else ""
        )
        body += f"<url><loc>{loc}</loc>{image}</url>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
        f"{body}</urlset>"
    )


def sitemap_index(locs: list[str]) -> str:
    body = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</sitemapindex>'
    )


XML_WITH_ENTITY = (
    '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>&lol;</loc></url></urlset>"
)


SHOPIFY_JS = (
    '{"id": 701, "title": "Dear Dahlia Blush", "vendor": "Dear Dahlia", "available": true,'
    ' "options": [{"name": "Shade", "position": 1, "values": ["Rose", "Peach"]}],'
    ' "images": ["//cdn.example/main.jpg"],'
    ' "variants": ['
    '{"id": 9001, "title": "Rose", "option1": "Rose", "price": 4800, "available": true,'
    ' "featured_image": {"src": "//cdn.example/rose.jpg"}},'
    '{"id": 9002, "title": "Peach", "option1": "Peach", "price": 4800, "available": false,'
    ' "featured_image": null}]}'
)
SHOPIFY_JSON = (
    '{"product": {"id": 701, "title": "Dear Dahlia Blush", "vendor": "Dear Dahlia",'
    ' "options": [{"name": "Shade", "values": ["Rose"]}],'
    ' "images": [{"id": 1, "src": "https://cdn.example/rose.jpg"}],'
    ' "variants": [{"id": 9001, "title": "Rose", "option1": "Rose", "price": "48.00",'
    ' "image_id": 1}]}}'
)
SHOPIFY_SINGLE = (
    '{"id": 702, "title": "Lip Balm", "available": false, "options": [],'
    ' "variants": [{"id": 9100, "title": "Default Title", "option1": "Default Title"}]}'
)

WOOCOMMERCE_FORM = page(
    "<h1>Curl Fix Mascara</h1>"
    '<form class="variations_form cart" data-product_variations=\'['
    '{"variation_id": 31, "attributes": {"attribute_pa_color": "01-black"},'
    ' "image": {"src": "https://s.example/01.jpg"}, "is_in_stock": true,'
    ' "display_price": 12000},'
    '{"variation_id": 32, "attributes": {"attribute_pa_color": "02-brown"},'
    ' "image": {"src": ""}, "is_in_stock": false, "display_price": 12000},'
    '{"variation_id": 33, "attributes": {"attribute_pa_color": "03-unknown"},'
    ' "is_in_stock": true}]\'>'
    '<select name="attribute_pa_color"><option value="">옵션 선택</option>'
    '<option value="01-black">01 블랙</option><option value="02-brown">02 브라운</option>'
    "</select></form>",
    '<link rel="stylesheet" href="/wp-content/plugins/woocommerce/x.css">',
)

JSONLD_PRODUCT = page(
    "<p>상품</p>",
    '<script type="application/ld+json">'
    '{"@context": "https://schema.org", "@graph": [{"@type": "WebSite", "name": "Shop"},'
    '{"@type": "Product", "name": "쥬시 래스팅 틴트", "image": ["https://s.example/m.jpg"],'
    ' "brand": {"@type": "Brand", "name": "롬앤"},'
    ' "offers": [{"@type": "Offer", "name": "01 쥬시", "sku": "T01",'
    ' "availability": "https://schema.org/InStock", "price": "9900"},'
    '{"@type": "Offer", "name": "02 레드", "sku": "T02",'
    ' "availability": "https://schema.org/OutOfStock", "price": "9900"}]}]}'
    "</script>",
)
JSONLD_SINGLE_OFFER = page(
    "<p>상품</p>",
    '<script type="application/ld+json">'
    '{"@type": "Product", "name": "단일 크림", "offers": {"@type": "AggregateOffer",'
    ' "offers": [{"@type": "Offer", "price": "1000", "availability": "InStock"}]}}'
    "</script>",
)

CAFE24_CHIPS = page(
    '<h1>쥬시 래스팅 틴트</h1><ul class="ec-product-button">'
    '<li option_value="01 쥬시" title="01 쥬시"><a href="#"><img src="//s.example/c1.jpg"></a></li>'
    '<li option_value="02 레드" title="02 레드 [품절]"><img src="//s.example/c2.jpg"></li>'
    "</ul>",
    '<meta property="og:title" content="[롬앤] 쥬시 래스팅 틴트">'
    '<meta property="og:image" content="https://s.example/og.jpg">'
    "<script>var EC_FRONT_JS_CONFIG = {};</script>",
)
CAFE24_SELECT = page(
    '<select name="option1" id="product_option_id1">'
    '<option value="*">- [필수] 옵션을 선택해 주세요 -</option>'
    '<option value="**">-------------------</option>'
    '<option value="C01">01 로즈</option>'
    '<option value="C02">02 피치 [품절]</option>'
    '<option value="C03" disabled>03 코랄</option></select>'
    '<select name="quantity"><option value="1">1</option></select>',
    "<script>var EC_FRONT_JS_CONFIG = {};</script><title>롬앤 쥬시 | 쇼핑몰</title>",
)
NO_OPTIONS = page("<h1>단일 크림</h1>", '<meta property="og:title" content="단일 크림">')
