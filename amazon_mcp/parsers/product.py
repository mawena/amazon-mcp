from bs4 import BeautifulSoup

from amazon_mcp.utils import parse_int, parse_price, product_url

_PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
    "#apex_desktop span.a-price span.a-offscreen",
    "span.a-price span.a-offscreen",
]


def parse_product(html: str, asin: str) -> dict:
    """Extrait les infos d'une page produit amazon.fr."""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("#productTitle")
    price_el = next((el for sel in _PRICE_SELECTORS if (el := soup.select_one(sel))), None)
    availability_el = soup.select_one("#availability span")
    rating_el = soup.select_one("#acrPopover span.a-icon-alt") or soup.select_one("span.a-icon-alt")
    reviews_el = soup.select_one("#acrCustomerReviewText")
    seller_el = soup.select_one("#sellerProfileTriggerId")

    availability = availability_el.get_text(strip=True) if availability_el else None
    in_stock = availability is None or "indisponible" not in availability.lower()

    rating = None
    if rating_el:
        rating = parse_price(rating_el.get_text(strip=True).split(" sur ")[0])

    return {
        "asin": asin,
        "url": product_url(asin),
        "title": title_el.get_text(strip=True) if title_el else None,
        "price": parse_price(price_el.get_text(strip=True)) if price_el else None,
        "currency": "EUR",
        "in_stock": in_stock,
        "availability": availability,
        "rating": rating,
        "review_count": parse_int(reviews_el.get_text(strip=True)) if reviews_el else None,
        "seller": seller_el.get_text(strip=True) if seller_el else None,
    }
