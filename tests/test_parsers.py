from pathlib import Path

from amazon_mcp.parsers.product import parse_product
from amazon_mcp.parsers.search import parse_search

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_product():
    html = (FIXTURES / "product.html").read_text()
    p = parse_product(html, "B08N5WRWNW")
    assert p["title"] == "Clavier Mécanique Gamer RGB"
    assert p["price"] == 89.99
    assert p["currency"] == "EUR"
    assert p["in_stock"] is True
    assert p["rating"] == 4.5
    assert p["review_count"] == 1234
    assert p["seller"] == "TechShop France"
    assert p["url"] == "https://www.amazon.fr/dp/B08N5WRWNW"


def test_parse_product_unavailable():
    html = "<html><body><span id='productTitle'>X</span><div id='availability'><span>Actuellement indisponible.</span></div></body></html>"
    p = parse_product(html, "B000000001")
    assert p["in_stock"] is False
    assert p["price"] is None


def test_parse_search():
    html = (FIXTURES / "search.html").read_text()
    results = parse_search(html)
    assert len(results) == 2
    r = results[0]
    assert r["asin"] == "B0AAAA0001"
    assert r["title"] == "Clavier RGB 60%"
    assert r["price"] == 59.99
    assert r["rating"] == 4.3
    assert r["prime"] is True
    assert r["url"].startswith("https://www.amazon.fr/")
    assert results[1]["prime"] is False


def test_parse_search_max_results():
    html = (FIXTURES / "search.html").read_text()
    assert len(parse_search(html, max_results=1)) == 1
