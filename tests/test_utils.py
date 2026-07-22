import pytest

from amazon_mcp.utils import extract_asin, parse_int, parse_price, product_url


def test_parse_price_simple():
    assert parse_price("19,99 €") == 19.99


def test_parse_price_thousands_nbsp():
    assert parse_price("1 234,56 €") == 1234.56


def test_parse_price_dot_thousands():
    assert parse_price("1.234,56 €") == 1234.56


def test_parse_price_empty():
    assert parse_price("") is None
    assert parse_price("Indisponible") is None


def test_parse_int_nbsp():
    assert parse_int("1 234 évaluations") == 1234


def test_extract_asin_from_asin():
    assert extract_asin("b08n5wrwnw") == "B08N5WRWNW"


def test_extract_asin_from_urls():
    assert extract_asin("https://www.amazon.fr/dp/B08N5WRWNW") == "B08N5WRWNW"
    assert extract_asin("https://www.amazon.fr/Nom-Produit/dp/B08N5WRWNW/ref=sr_1_1?k=x") == "B08N5WRWNW"
    assert extract_asin("https://www.amazon.fr/gp/product/B08N5WRWNW") == "B08N5WRWNW"


def test_extract_asin_invalid():
    with pytest.raises(ValueError):
        extract_asin("https://www.amazon.fr/s?k=clavier")


def test_product_url():
    assert product_url("B08N5WRWNW") == "https://www.amazon.fr/dp/B08N5WRWNW"
