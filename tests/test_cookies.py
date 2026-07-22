import json

from amazon_mcp.scraping.cookies import load_cookies, normalize_cookies


def test_normalize_maps_editor_format():
    raw = [{
        "name": "session-id", "value": "123", "domain": ".amazon.fr", "path": "/",
        "expirationDate": 1893456000.5, "httpOnly": True, "secure": True,
        "sameSite": "no_restriction",
    }]
    out = normalize_cookies(raw)
    assert out == [{
        "name": "session-id", "value": "123", "domain": ".amazon.fr", "path": "/",
        "expires": 1893456000, "httpOnly": True, "secure": True, "sameSite": "None",
    }]


def test_normalize_samesite_variants():
    def ss(v):
        return normalize_cookies([{"name": "x", "value": "y", "domain": ".amazon.fr", "path": "/", "sameSite": v}])[0]["sameSite"]
    assert ss("lax") == "Lax"
    assert ss("strict") == "Strict"
    assert ss("unspecified") == "Lax"


def test_normalize_skips_entries_without_name_or_domain():
    raw = [{"value": "y", "domain": ".amazon.fr"}, {"name": "x", "value": "y"}]
    assert normalize_cookies(raw) == []


def test_load_cookies_missing_file_returns_empty(tmp_path):
    assert load_cookies(tmp_path / "nope.json") == []


def test_load_cookies_invalid_json_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert load_cookies(p) == []


def test_load_cookies_reads_and_normalizes(tmp_path):
    p = tmp_path / "cookies.json"
    p.write_text(json.dumps([{"name": "a", "value": "b", "domain": ".amazon.fr", "path": "/", "sameSite": "lax"}]))
    out = load_cookies(p)
    assert out[0]["name"] == "a"
    assert out[0]["sameSite"] == "Lax"
