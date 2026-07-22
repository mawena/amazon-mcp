from bs4 import BeautifulSoup

from amazon_mcp.utils import parse_price

_BASE = "https://www.amazon.fr"


def parse_search(html: str, max_results: int = 10) -> list[dict]:
    """Extrait les résultats d'une page de recherche amazon.fr."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    for div in soup.select('div[data-component-type="s-search-result"]'):
        asin = div.get("data-asin")
        if not asin:
            continue
        title_el = div.select_one("h2 span")
        price_el = div.select_one("span.a-price > span.a-offscreen")
        rating_el = div.select_one("span.a-icon-alt")
        link_el = div.select_one("h2 a")
        rating = None
        if rating_el:
            rating = parse_price(rating_el.get_text(strip=True).split(" sur ")[0])
        results.append({
            "asin": asin,
            "title": title_el.get_text(strip=True) if title_el else None,
            "price": parse_price(price_el.get_text(strip=True)) if price_el else None,
            "currency": "EUR",
            "url": _BASE + link_el["href"].split("/ref=")[0] if link_el else f"{_BASE}/dp/{asin}",
            "rating": rating,
            "prime": div.select_one("i.a-icon-prime") is not None,
        })
        if len(results) >= max_results:
            break
    return results
