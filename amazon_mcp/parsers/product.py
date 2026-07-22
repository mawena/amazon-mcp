import re

from bs4 import BeautifulSoup

from amazon_mcp.utils import parse_int, parse_price, product_url

# Essayés dans l'ordre ; le premier qui donne un prix exploitable gagne.
# Le layout 2025+ laisse `a-offscreen` vide et met le prix dans `aok-offscreen`.
_PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div span.aok-offscreen",
    "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
    "#apex_desktop span.aok-offscreen",
    "#apex_desktop span.a-price span.a-offscreen",
    "span.a-price span.a-offscreen",
]

# Notes/avis : la section DOM peut être lazy-loadée ; les données restent
# disponibles dans le JSON embarqué (averageCustomerReviews).
_JSON_RATING_RE = re.compile(r'averageCustomerReviews.{0,400}?value(?:\\?&quot;|"):([\d.]+)')
_JSON_REVIEWS_RE = re.compile(r'reviewCount(?:\\?&quot;|"):(\d+)')


def _extract_price(soup) -> float | None:
    for sel in _PRICE_SELECTORS:
        for el in soup.select(sel):
            price = parse_price(el.get_text(strip=True))
            if price is not None:
                return price
    # Dernier recours : prix décomposé (a-price-whole + a-price-fraction)
    whole = soup.select_one("span.a-price-whole")
    fraction = soup.select_one("span.a-price-fraction")
    if whole and fraction:
        return parse_price(f"{whole.get_text(strip=True)}{fraction.get_text(strip=True)}")
    return None


def parse_product(html: str, asin: str) -> dict:
    """Extrait les infos d'une page produit amazon.fr."""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("#productTitle")
    availability_el = soup.select_one("#availability span")
    # Restreint à la section avis : un sélecteur global attraperait la note
    # d'un produit du carrousel "produits similaires".
    rating_el = soup.select_one("#acrPopover span.a-icon-alt") or soup.select_one(
        "#averageCustomerReviews span.a-icon-alt"
    )
    reviews_el = soup.select_one("#acrCustomerReviewText")
    seller_el = soup.select_one("#sellerProfileTriggerId")

    availability = availability_el.get_text(strip=True) if availability_el else None
    in_stock = availability is None or "indisponible" not in availability.lower()

    rating = None
    if rating_el:
        rating = parse_price(rating_el.get_text(strip=True).split(" sur ")[0])
    if rating is None and (m := _JSON_RATING_RE.search(html)):
        rating = float(m.group(1))

    review_count = parse_int(reviews_el.get_text(strip=True)) if reviews_el else None
    if review_count is None and (m := _JSON_REVIEWS_RE.search(html)):
        review_count = int(m.group(1))

    return {
        "asin": asin,
        "url": product_url(asin),
        "title": title_el.get_text(strip=True) if title_el else None,
        "price": _extract_price(soup),
        "currency": "EUR",
        "in_stock": in_stock,
        "availability": availability,
        "rating": rating,
        "review_count": review_count,
        "seller": seller_el.get_text(strip=True) if seller_el else None,
    }
