from pathlib import Path

from amazon_mcp.scraping.detection import is_blocked

FIXTURES = Path(__file__).parent / "fixtures"


def test_captcha_detected():
    assert is_blocked((FIXTURES / "captcha.html").read_text()) is True


def test_normal_page_ok():
    assert is_blocked("<html><body><span id='productTitle'>Clavier</span></body></html>") is False


def test_empty_is_blocked():
    assert is_blocked("") is True
