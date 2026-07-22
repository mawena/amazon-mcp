import pytest

from amazon_mcp.scraping.backends import ScraperBackend, ScraperError
from amazon_mcp.scraping.engine import ScrapeFailed, ScraperEngine

OK_HTML = "<html><body><span id='productTitle'>x</span></body></html>"
CAPTCHA_HTML = "<html>/errors/validateCaptcha</html>"


class FakeBackend(ScraperBackend):
    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = 0

    def fetch(self, url):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_engine(*backends):
    return ScraperEngine(backends=list(backends), cache_ttl=900, min_interval=0)


def test_first_backend_success():
    b1, b2 = FakeBackend("a", OK_HTML), FakeBackend("b", OK_HTML)
    assert make_engine(b1, b2).get_html("http://x") == OK_HTML
    assert (b1.calls, b2.calls) == (1, 0)


def test_escalade_on_error():
    b1, b2 = FakeBackend("a", ScraperError("HTTP 503")), FakeBackend("b", OK_HTML)
    assert make_engine(b1, b2).get_html("http://x") == OK_HTML
    assert (b1.calls, b2.calls) == (1, 1)


def test_escalade_on_captcha():
    b1, b2 = FakeBackend("a", CAPTCHA_HTML), FakeBackend("b", OK_HTML)
    assert make_engine(b1, b2).get_html("http://x") == OK_HTML


def test_all_fail_raises():
    b1 = FakeBackend("a", CAPTCHA_HTML)
    b2 = FakeBackend("b", ScraperError("HTTP 503"))
    with pytest.raises(ScrapeFailed):
        make_engine(b1, b2).get_html("http://x")


def test_cache_hit():
    b1 = FakeBackend("a", OK_HTML)
    eng = make_engine(b1)
    eng.get_html("http://x")
    eng.get_html("http://x")
    assert b1.calls == 1


def test_cache_bypass():
    b1 = FakeBackend("a", OK_HTML)
    eng = make_engine(b1)
    eng.get_html("http://x")
    eng.get_html("http://x", use_cache=False)
    assert b1.calls == 2
