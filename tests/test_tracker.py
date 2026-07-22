from pathlib import Path

from amazon_mcp import db, tracker
from amazon_mcp.scraping.backends import ScraperBackend, ScraperError
from amazon_mcp.scraping.engine import ScraperEngine

FIXTURES = Path(__file__).parent / "fixtures"


class FixtureBackend(ScraperBackend):
    name = "fixture"

    def __init__(self, fail=False):
        self.fail = fail

    def fetch(self, url):
        if self.fail:
            raise ScraperError("boom")
        return (FIXTURES / "product.html").read_text()


def make(tmp_path, fail=False):
    conn = db.get_conn(tmp_path / "t.db")
    engine = ScraperEngine(backends=[FixtureBackend(fail)], min_interval=0)
    return conn, engine


def test_track_records_first_price(tmp_path):
    conn, engine = make(tmp_path)
    p = tracker.track(engine, conn, "B08N5WRWNW", label="Clavier")
    assert p["price"] == 89.99
    rows = db.list_tracked(conn)
    assert rows[0]["last_price"] == 89.99
    assert rows[0]["label"] == "Clavier"


def test_refresh_all(tmp_path):
    conn, engine = make(tmp_path)
    tracker.track(engine, conn, "B08N5WRWNW")
    result = tracker.refresh_all(engine, conn, sleep_range=(0, 0))
    assert result == {"refreshed": 1, "errors": []}
    assert len(db.price_history(conn, "B08N5WRWNW")) == 2


def test_refresh_all_survives_errors(tmp_path):
    conn, _ = make(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    failing = ScraperEngine(backends=[FixtureBackend(fail=True)], min_interval=0)
    result = tracker.refresh_all(failing, conn, sleep_range=(0, 0))
    assert result["refreshed"] == 0
    assert len(result["errors"]) == 1
