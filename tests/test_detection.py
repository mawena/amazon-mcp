from pathlib import Path

from amazon_mcp.scraping.detection import is_blocked

FIXTURES = Path(__file__).parent / "fixtures"


def test_captcha_detected():
    assert is_blocked((FIXTURES / "captcha.html").read_text()) is True


def test_normal_page_ok():
    assert is_blocked("<html><body><span id='productTitle'>Clavier</span></body></html>") is False


def test_empty_is_blocked():
    assert is_blocked("") is True


def test_aws_waf_challenge_detected():
    html = '<html><head><title></title><script>window.awsWafCookieDomainList=[];</script></head></html>'
    assert is_blocked(html) is True


def test_interstitial_detected():
    html = "<html><body><button>Continuer les achats</button></body></html>"
    assert is_blocked(html) is True


def test_tiny_page_without_amazon_content_detected():
    # DOM rendu d'un challenge WAF : petit, sans marqueur littéral ni contenu Amazon
    html = "<html><head></head><body><div id='challenge'>Vérification…</div></body></html>"
    assert is_blocked(html) is True


def test_small_page_with_product_content_ok():
    html = "<html><body><span id='productTitle'>Clavier</span></body></html>"
    assert is_blocked(html) is False
