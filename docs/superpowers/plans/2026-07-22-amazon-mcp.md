# Amazon MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serveur MCP distant (HTTP streamable) qui scrape amazon.fr — recherche, fiche produit, suivi de prix — déployé en Docker derrière Nginx sur `amazon.mcp.mawena.cloud`.

**Architecture:** Un seul service Python. `MCPServer` (SDK `mcp` v2) expose 6 outils ; un `ScraperEngine` essaie une cascade de backends (requests → curl_cffi → Playwright) avec rate-limit, cache TTL et détection captcha ; SQLite stocke le suivi et l'historique ; APScheduler relève les prix toutes les 6 h.

**Tech Stack:** Python 3.12, mcp (SDK officiel), requests, curl_cffi, playwright, beautifulsoup4+lxml, APScheduler 3.x, sqlite3 (stdlib), pytest + anyio.

## Global Constraints

- Python ≥ 3.11 ; paquet nommé `amazon_mcp`.
- Transport MCP : **streamable-http**, `stateless_http=True`, chemin secret `MCP_SECRET_PATH` (déf. `/mcp`), port `8321`.
- Rate limit : ≥ `MIN_REQUEST_INTERVAL` (3.0 s) entre requêtes Amazon ; cache TTL `CACHE_TTL_SECONDS` (900 s).
- Scheduler : toutes les `TRACK_INTERVAL_HOURS` (6 h), jitter 1800 s, délai aléatoire 5–15 s entre articles.
- Aucun test ne fait de requête réseau réelle (fixtures HTML + mocks).
- Messages d'erreur utilisateur en français.
- Compat SDK : `try: from mcp.server import MCPServer / except ImportError: from mcp.server.fastmcp import FastMCP as MCPServer`.
- Commits fréquents, messages `feat:/test:/docs:/chore:`.

## File Structure

```
pyproject.toml            # métadonnées + deps
.env.example              # variables d'env documentées
.gitignore
amazon_mcp/
  __init__.py
  config.py               # lecture env (.env via python-dotenv)
  utils.py                # parse_price, extract_asin, product_url, parse_int
  db.py                   # SQLite : schéma + CRUD suivi/historique
  scraping/
    __init__.py
    detection.py          # is_blocked(html)
    backends.py           # ScraperBackend + Requests/CurlCffi/Playwright
    engine.py             # ScraperEngine (cascade, throttle, cache)
  parsers/
    __init__.py
    product.py            # parse_product(html, asin) -> dict
    search.py             # parse_search(html, max_results) -> list[dict]
  tracker.py              # track/refresh_all (logique de suivi)
  server.py               # MCPServer, 6 outils, scheduler, main()
tests/
  conftest.py
  fixtures/{product.html, search.html, captcha.html}
  test_utils.py test_db.py test_detection.py test_engine.py
  test_parsers.py test_tracker.py test_server.py
Dockerfile  docker-compose.yml  deploy/nginx.conf  README.md
```

---

### Task 1: Scaffolding + config

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `amazon_mcp/__init__.py`, `amazon_mcp/config.py`, `tests/conftest.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `config.HOST:str`, `config.PORT:int`, `config.MCP_SECRET_PATH:str`, `config.DB_PATH:Path`, `config.CACHE_TTL_SECONDS:int`, `config.MIN_REQUEST_INTERVAL:float`, `config.TRACK_INTERVAL_HOURS:int`

- [ ] **Step 1: Écrire les fichiers de base**

`pyproject.toml` :
```toml
[project]
name = "amazon-mcp"
version = "0.1.0"
description = "Serveur MCP de scraping amazon.fr"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.9",
    "requests>=2.32",
    "curl_cffi>=0.7",
    "playwright>=1.45",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "apscheduler>=3.10,<4",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "anyio>=4.0", "inline-snapshot>=0.10"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["amazon_mcp*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore` :
```
__pycache__/
*.pyc
.venv/
.env
data/
*.egg-info/
```

`.env.example` :
```
# Chemin secret du endpoint MCP (générer: python -c "import secrets; print('/mcp-'+secrets.token_urlsafe(12))")
MCP_SECRET_PATH=/mcp
HOST=0.0.0.0
PORT=8321
DB_PATH=data/amazon.db
CACHE_TTL_SECONDS=900
MIN_REQUEST_INTERVAL=3.0
TRACK_INTERVAL_HOURS=6
```

`amazon_mcp/__init__.py` : vide.

`amazon_mcp/config.py` :
```python
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8321"))
MCP_SECRET_PATH = os.getenv("MCP_SECRET_PATH", "/mcp")
DB_PATH = Path(os.getenv("DB_PATH", "data/amazon.db"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "900"))
MIN_REQUEST_INTERVAL = float(os.getenv("MIN_REQUEST_INTERVAL", "3.0"))
TRACK_INTERVAL_HOURS = int(os.getenv("TRACK_INTERVAL_HOURS", "6"))
```

`tests/conftest.py` :
```python
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

`tests/test_config.py` :
```python
from amazon_mcp import config


def test_defaults():
    assert config.PORT == 8321
    assert config.MCP_SECRET_PATH.startswith("/")
    assert config.MIN_REQUEST_INTERVAL >= 3.0
```

- [ ] **Step 2: Créer le venv et installer**

Run: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
Expected: installation sans erreur (playwright s'installe mais pas ses navigateurs — pas nécessaire pour les tests).

- [ ] **Step 3: Lancer le test**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: scaffolding projet + config"
```

---

### Task 2: Utils (parse_price, extract_asin)

**Files:**
- Create: `amazon_mcp/utils.py`, `tests/test_utils.py`

**Interfaces:**
- Produces: `parse_price(text:str)->float|None`, `parse_int(text:str)->int|None`, `extract_asin(url_or_asin:str)->str` (lève `ValueError`), `product_url(asin:str)->str`

- [ ] **Step 1: Écrire les tests (échec attendu)**

`tests/test_utils.py` :
```python
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
```

- [ ] **Step 2: Vérifier l'échec** — Run: `.venv/bin/pytest tests/test_utils.py -v` → FAIL (module absent)

- [ ] **Step 3: Implémenter**

`amazon_mcp/utils.py` :
```python
import re

_ASIN_RE = re.compile(r"^[A-Za-z0-9]{10}$")
_URL_ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.IGNORECASE)


def extract_asin(url_or_asin: str) -> str:
    """Extrait l'ASIN d'une URL amazon.fr ou d'un ASIN brut."""
    s = url_or_asin.strip()
    if "/" not in s and _ASIN_RE.match(s):
        return s.upper()
    m = _URL_ASIN_RE.search(s)
    if m:
        return m.group(1).upper()
    raise ValueError(f"Impossible d'extraire un ASIN de : {url_or_asin!r}")


def product_url(asin: str) -> str:
    return f"https://www.amazon.fr/dp/{asin}"


def parse_price(text: str | None) -> float | None:
    """Convertit un prix au format français ("1 234,56 €") en float."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(text: str | None) -> int | None:
    """Extrait un entier d'un texte ("1 234 évaluations" -> 1234)."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None
```

- [ ] **Step 4: Vérifier le succès** — Run: `.venv/bin/pytest tests/test_utils.py -v` → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: utilitaires prix/ASIN"`

---

### Task 3: Base de données SQLite

**Files:**
- Create: `amazon_mcp/db.py`, `tests/test_db.py`

**Interfaces:**
- Consomme : `config.DB_PATH`
- Produces:
  - `get_conn(db_path:Path|None=None)->sqlite3.Connection` (crée le schéma si absent)
  - `add_tracked(conn, asin, url, label=None)` / `remove_tracked(conn, asin)->bool`
  - `list_tracked(conn)->list[dict]` — clés: `asin,label,url,created_at,last_price,previous_price,last_scraped_at`
  - `is_tracked(conn, asin)->bool`
  - `record_price(conn, asin, price:float|None, currency:str, in_stock:bool)`
  - `price_history(conn, asin, days:int=30)->list[dict]` — clés: `price,currency,in_stock,scraped_at`

- [ ] **Step 1: Écrire les tests**

`tests/test_db.py` :
```python
from amazon_mcp import db


def make_conn(tmp_path):
    return db.get_conn(tmp_path / "test.db")


def test_track_and_list(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "https://www.amazon.fr/dp/B000000001", "Clavier")
    rows = db.list_tracked(conn)
    assert len(rows) == 1
    assert rows[0]["asin"] == "B000000001"
    assert rows[0]["label"] == "Clavier"
    assert rows[0]["last_price"] is None


def test_track_idempotent(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    db.add_tracked(conn, "B000000001", "u")
    assert len(db.list_tracked(conn)) == 1


def test_untrack(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    assert db.remove_tracked(conn, "B000000001") is True
    assert db.remove_tracked(conn, "B000000001") is False
    assert db.list_tracked(conn) == []


def test_price_history_and_last_price(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    db.record_price(conn, "B000000001", 29.99, "EUR", True)
    db.record_price(conn, "B000000001", 24.99, "EUR", True)
    hist = db.price_history(conn, "B000000001")
    assert [h["price"] for h in hist] == [29.99, 24.99]
    row = db.list_tracked(conn)[0]
    assert row["last_price"] == 24.99
    assert row["previous_price"] == 29.99
```

- [ ] **Step 2: Vérifier l'échec** — `.venv/bin/pytest tests/test_db.py -v` → FAIL

- [ ] **Step 3: Implémenter**

`amazon_mcp/db.py` :
```python
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from amazon_mcp.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracked_products (
    asin TEXT PRIMARY KEY,
    label TEXT,
    url TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    price REAL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    in_stock INTEGER NOT NULL DEFAULT 1,
    scraped_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_asin ON price_history(asin, scraped_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def add_tracked(conn, asin: str, url: str, label: str | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_products (asin, label, url, created_at) VALUES (?,?,?,?)",
        (asin, label, url, _now()),
    )
    conn.commit()


def remove_tracked(conn, asin: str) -> bool:
    cur = conn.execute("DELETE FROM tracked_products WHERE asin = ?", (asin,))
    conn.commit()
    return cur.rowcount > 0


def is_tracked(conn, asin: str) -> bool:
    return conn.execute("SELECT 1 FROM tracked_products WHERE asin = ?", (asin,)).fetchone() is not None


def record_price(conn, asin: str, price: float | None, currency: str = "EUR", in_stock: bool = True) -> None:
    conn.execute(
        "INSERT INTO price_history (asin, price, currency, in_stock, scraped_at) VALUES (?,?,?,?,?)",
        (asin, price, currency, int(in_stock), _now()),
    )
    conn.commit()


def list_tracked(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM tracked_products ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        hist = conn.execute(
            "SELECT price, scraped_at FROM price_history WHERE asin = ? ORDER BY scraped_at DESC, id DESC LIMIT 2",
            (r["asin"],),
        ).fetchall()
        out.append({
            "asin": r["asin"],
            "label": r["label"],
            "url": r["url"],
            "created_at": r["created_at"],
            "last_price": hist[0]["price"] if hist else None,
            "previous_price": hist[1]["price"] if len(hist) > 1 else None,
            "last_scraped_at": hist[0]["scraped_at"] if hist else None,
        })
    return out


def price_history(conn, asin: str, days: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT price, currency, in_stock, scraped_at FROM price_history "
        "WHERE asin = ? AND scraped_at >= datetime('now', ?) ORDER BY scraped_at, id",
        (asin, f"-{int(days)} days"),
    ).fetchall()
    return [
        {"price": r["price"], "currency": r["currency"], "in_stock": bool(r["in_stock"]), "scraped_at": r["scraped_at"]}
        for r in rows
    ]
```

- [ ] **Step 4: Vérifier le succès** — `.venv/bin/pytest tests/test_db.py -v` → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: stockage SQLite suivi + historique"`

---

### Task 4: Détection captcha + backends de scraping

**Files:**
- Create: `amazon_mcp/scraping/__init__.py`, `amazon_mcp/scraping/detection.py`, `amazon_mcp/scraping/backends.py`, `tests/test_detection.py`, `tests/fixtures/captcha.html`

**Interfaces:**
- Produces: `is_blocked(html:str)->bool` ; `ScraperError(Exception)` ; `ScraperBackend` (attr `name:str`, méthode `fetch(url:str)->str`) ; `RequestsBackend`, `CurlCffiBackend`, `PlaywrightBackend` ; `build_headers()->dict`

- [ ] **Step 1: Fixture captcha + tests**

`tests/fixtures/captcha.html` :
```html
<html><head><title>Amazon.fr</title></head><body>
<form method="get" action="/errors/validateCaptcha">
<h4>Saisissez les caractères que vous voyez ci-dessous</h4>
<p>Nous vous prions de nous excuser. Contactez api-services-support@amazon.com.</p>
</form></body></html>
```

`tests/test_detection.py` :
```python
from pathlib import Path

from amazon_mcp.scraping.detection import is_blocked

FIXTURES = Path(__file__).parent / "fixtures"


def test_captcha_detected():
    assert is_blocked((FIXTURES / "captcha.html").read_text()) is True


def test_normal_page_ok():
    assert is_blocked("<html><body><span id='productTitle'>Clavier</span></body></html>") is False


def test_empty_is_blocked():
    assert is_blocked("") is True
```

- [ ] **Step 2: Vérifier l'échec** — `.venv/bin/pytest tests/test_detection.py -v` → FAIL

- [ ] **Step 3: Implémenter détection + backends**

`amazon_mcp/scraping/__init__.py` : vide.

`amazon_mcp/scraping/detection.py` :
```python
_MARKERS = (
    "/errors/validateCaptcha",
    "api-services-support@amazon.com",
    "Saisissez les caractères",
    "Robot Check",
    "To discuss automated access",
)


def is_blocked(html: str | None) -> bool:
    """Vrai si la page est vide ou est une page captcha/anti-robot d'Amazon."""
    if not html:
        return True
    return any(marker in html for marker in _MARKERS)
```

`amazon_mcp/scraping/backends.py` :
```python
import random

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


class ScraperError(Exception):
    """Échec d'un backend de scraping."""


def build_headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }


class ScraperBackend:
    """Interface commune : fetch(url) -> HTML. Ajouter un backend = sous-classer + l'insérer dans la cascade."""

    name = "base"

    def fetch(self, url: str) -> str:
        raise NotImplementedError


class RequestsBackend(ScraperBackend):
    name = "requests"

    def fetch(self, url: str) -> str:
        import requests

        r = requests.get(url, headers=build_headers(), timeout=20)
        if r.status_code != 200:
            raise ScraperError(f"HTTP {r.status_code}")
        return r.text


class CurlCffiBackend(ScraperBackend):
    name = "curl_cffi"

    def fetch(self, url: str) -> str:
        from curl_cffi import requests as creq

        r = creq.get(
            url,
            impersonate="chrome",
            headers={"Accept-Language": "fr-FR,fr;q=0.9"},
            timeout=20,
        )
        if r.status_code != 200:
            raise ScraperError(f"HTTP {r.status_code}")
        return r.text


class PlaywrightBackend(ScraperBackend):
    name = "playwright"

    def fetch(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="fr-FR", user_agent=random.choice(_USER_AGENTS))
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                return page.content()
            finally:
                browser.close()
```

- [ ] **Step 4: Vérifier le succès** — `.venv/bin/pytest tests/test_detection.py -v` → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: détection captcha + backends requests/curl_cffi/playwright"`

---

### Task 5: ScraperEngine (cascade + throttle + cache)

**Files:**
- Create: `amazon_mcp/scraping/engine.py`, `tests/test_engine.py`

**Interfaces:**
- Consomme : `ScraperBackend`, `is_blocked`, `config.CACHE_TTL_SECONDS`, `config.MIN_REQUEST_INTERVAL`
- Produces: `ScrapeFailed(Exception)` ; `ScraperEngine(backends:list|None=None, cache_ttl:float=..., min_interval:float=...)` avec `get_html(url:str, use_cache:bool=True)->str`

- [ ] **Step 1: Écrire les tests (avec faux backends)**

`tests/test_engine.py` :
```python
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
```

- [ ] **Step 2: Vérifier l'échec** — `.venv/bin/pytest tests/test_engine.py -v` → FAIL

- [ ] **Step 3: Implémenter**

`amazon_mcp/scraping/engine.py` :
```python
import threading
import time

from amazon_mcp.config import CACHE_TTL_SECONDS, MIN_REQUEST_INTERVAL
from amazon_mcp.scraping.detection import is_blocked


class ScrapeFailed(Exception):
    """Tous les backends ont échoué."""


def default_backends():
    from amazon_mcp.scraping.backends import CurlCffiBackend, PlaywrightBackend, RequestsBackend

    return [RequestsBackend(), CurlCffiBackend(), PlaywrightBackend()]


class ScraperEngine:
    """Cascade de backends avec rate-limit global et cache TTL."""

    def __init__(self, backends=None, cache_ttl: float = CACHE_TTL_SECONDS,
                 min_interval: float = MIN_REQUEST_INTERVAL):
        self.backends = backends if backends is not None else default_backends()
        self.cache_ttl = cache_ttl
        self.min_interval = min_interval
        self._cache: dict[str, tuple[float, str]] = {}
        self._last_request = 0.0
        self._lock = threading.Lock()

    def get_html(self, url: str, use_cache: bool = True) -> str:
        if use_cache:
            hit = self._cache.get(url)
            if hit and time.time() - hit[0] < self.cache_ttl:
                return hit[1]
        with self._lock:
            self._throttle()
            errors = []
            for backend in self.backends:
                try:
                    html = backend.fetch(url)
                except Exception as exc:  # noqa: BLE001 — tout échec déclenche l'escalade
                    errors.append(f"{backend.name}: {exc}")
                    continue
                if is_blocked(html):
                    errors.append(f"{backend.name}: page captcha/anti-robot")
                    continue
                self._cache[url] = (time.time(), html)
                return html
        raise ScrapeFailed(
            "Amazon bloque actuellement toutes les méthodes de scraping, réessaie plus tard. "
            f"Détails : {'; '.join(errors)}"
        )

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
```

- [ ] **Step 4: Vérifier le succès** — `.venv/bin/pytest tests/test_engine.py -v` → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: moteur de scraping en cascade avec cache et rate-limit"`

---

### Task 6: Parsers (produit + recherche) sur fixtures

**Files:**
- Create: `amazon_mcp/parsers/__init__.py`, `amazon_mcp/parsers/product.py`, `amazon_mcp/parsers/search.py`, `tests/fixtures/product.html`, `tests/fixtures/search.html`, `tests/test_parsers.py`

**Interfaces:**
- Consomme : `utils.parse_price`, `utils.parse_int`, `utils.product_url`
- Produces:
  - `parse_product(html:str, asin:str)->dict` — clés: `asin,url,title,price,currency,in_stock,rating,review_count,seller`
  - `parse_search(html:str, max_results:int=10)->list[dict]` — clés: `asin,title,price,currency,url,rating,prime`

- [ ] **Step 1: Fixtures HTML**

`tests/fixtures/product.html` (structure réelle simplifiée d'une page produit amazon.fr) :
```html
<html><body>
<span id="productTitle"> Clavier Mécanique Gamer RGB </span>
<div id="corePriceDisplay_desktop_feature_div">
  <span class="a-price"><span class="a-offscreen">89,99&nbsp;€</span></span>
</div>
<div id="averageCustomerReviews">
  <span id="acrPopover"><span class="a-icon-alt">4,5 sur 5 étoiles</span></span>
  <span id="acrCustomerReviewText">1&#8239;234 évaluations</span>
</div>
<div id="availability"><span> En stock </span></div>
<a id="sellerProfileTriggerId">TechShop France</a>
</body></html>
```

`tests/fixtures/search.html` :
```html
<html><body>
<div data-component-type="s-search-result" data-asin="B0AAAA0001">
  <h2><a href="/Clavier-RGB/dp/B0AAAA0001/ref=sr_1_1"><span>Clavier RGB 60%</span></a></h2>
  <span class="a-price"><span class="a-offscreen">59,99&nbsp;€</span></span>
  <span class="a-icon-alt">4,3 sur 5 étoiles</span>
  <i class="a-icon a-icon-prime"></i>
</div>
<div data-component-type="s-search-result" data-asin="B0AAAA0002">
  <h2><a href="/Clavier-Simple/dp/B0AAAA0002/ref=sr_1_2"><span>Clavier simple</span></a></h2>
  <span class="a-price"><span class="a-offscreen">19,99&nbsp;€</span></span>
</div>
<div data-component-type="s-search-result" data-asin=""></div>
</body></html>
```

- [ ] **Step 2: Tests**

`tests/test_parsers.py` :
```python
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
```

- [ ] **Step 3: Vérifier l'échec** — `.venv/bin/pytest tests/test_parsers.py -v` → FAIL

- [ ] **Step 4: Implémenter**

`amazon_mcp/parsers/__init__.py` : vide.

`amazon_mcp/parsers/product.py` :
```python
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
```

`amazon_mcp/parsers/search.py` :
```python
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
```

- [ ] **Step 5: Vérifier le succès** — `.venv/bin/pytest tests/test_parsers.py -v` → PASS

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: parsers page produit et recherche"`

---

### Task 7: Tracker (suivi + rafraîchissement planifié)

**Files:**
- Create: `amazon_mcp/tracker.py`, `tests/test_tracker.py`

**Interfaces:**
- Consomme : `db.*`, `engine.get_html`, `parse_product`, `utils.extract_asin`, `utils.product_url`
- Produces:
  - `track(engine, conn, url_or_asin, label=None)->dict` (scrape + enregistre + 1er relevé)
  - `refresh_all(engine, conn, sleep_range=(5,15))->dict` — `{"refreshed": int, "errors": list[str]}` ; n'échoue jamais globalement

- [ ] **Step 1: Tests**

`tests/test_tracker.py` :
```python
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
```

- [ ] **Step 2: Vérifier l'échec** — `.venv/bin/pytest tests/test_tracker.py -v` → FAIL

- [ ] **Step 3: Implémenter**

`amazon_mcp/tracker.py` :
```python
import logging
import random
import time

from amazon_mcp import db
from amazon_mcp.parsers.product import parse_product
from amazon_mcp.utils import extract_asin, product_url

logger = logging.getLogger(__name__)


def track(engine, conn, url_or_asin: str, label: str | None = None) -> dict:
    """Ajoute un produit au suivi et enregistre un premier relevé de prix."""
    asin = extract_asin(url_or_asin)
    html = engine.get_html(product_url(asin))
    product = parse_product(html, asin)
    db.add_tracked(conn, asin, product["url"], label or product["title"])
    db.record_price(conn, asin, product["price"], product["currency"], product["in_stock"])
    return product


def refresh_all(engine, conn, sleep_range: tuple[float, float] = (5, 15)) -> dict:
    """Relève le prix de tous les produits suivis. Ne lève jamais : erreurs collectées."""
    refreshed, errors = 0, []
    for i, row in enumerate(db.list_tracked(conn)):
        if i > 0:
            time.sleep(random.uniform(*sleep_range))
        try:
            html = engine.get_html(product_url(row["asin"]), use_cache=False)
            product = parse_product(html, row["asin"])
            db.record_price(conn, row["asin"], product["price"], product["currency"], product["in_stock"])
            refreshed += 1
        except Exception as exc:  # noqa: BLE001 — un échec ne doit pas bloquer les autres
            logger.warning("Échec relevé %s : %s", row["asin"], exc)
            errors.append(f"{row['asin']}: {exc}")
    return {"refreshed": refreshed, "errors": errors}
```

- [ ] **Step 4: Vérifier le succès** — `.venv/bin/pytest tests/test_tracker.py -v` → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: logique de suivi et rafraîchissement des prix"`

---

### Task 8: Serveur MCP (6 outils) + scheduler

**Files:**
- Create: `amazon_mcp/server.py`, `tests/test_server.py`

**Interfaces:**
- Consomme : tout ce qui précède
- Produces: instance module-level `mcp`, fonction `main()`, outils MCP `search_products, get_product, track_product, untrack_product, list_tracked, get_price_history`

- [ ] **Step 1: Tests (client MCP en mémoire, backend fixture injecté)**

`tests/test_server.py` :
```python
import json
from pathlib import Path

import pytest

from amazon_mcp import db
from amazon_mcp import server
from amazon_mcp.scraping.backends import ScraperBackend
from amazon_mcp.scraping.engine import ScraperEngine

try:
    from mcp import Client
except ImportError:
    from mcp.shared.memory import create_connected_server_and_client_session as Client  # fallback SDK v1

FIXTURES = Path(__file__).parent / "fixtures"


class FixtureBackend(ScraperBackend):
    name = "fixture"

    def fetch(self, url):
        name = "search.html" if "/s?" in url else "product.html"
        return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def wire_test_deps(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "engine", ScraperEngine(backends=[FixtureBackend()], min_interval=0))
    monkeypatch.setattr(server, "_db_path", tmp_path / "test.db")


def get_json(result):
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_search_products():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_products", {"query": "clavier", "max_results": 5})
    data = get_json(result)
    assert data[0]["asin"] == "B0AAAA0001"


@pytest.mark.anyio
async def test_get_product():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_product", {"url_or_asin": "B08N5WRWNW"})
    assert get_json(result)["price"] == 89.99


@pytest.mark.anyio
async def test_track_untrack_history():
    async with Client(server.mcp) as client:
        await client.call_tool("track_product", {"url_or_asin": "B08N5WRWNW", "label": "Clavier"})
        listed = get_json(await client.call_tool("list_tracked", {}))
        assert listed[0]["asin"] == "B08N5WRWNW"
        hist = get_json(await client.call_tool("get_price_history", {"asin": "B08N5WRWNW"}))
        assert hist["current"] == 89.99
        removed = await client.call_tool("untrack_product", {"asin": "B08N5WRWNW"})
        assert "retiré" in removed.content[0].text
```

Note : si `get_json` ne colle pas au format de retour du SDK installé (structured content), adapter en lisant `result.structured_content` — vérifier à l'exécution.

- [ ] **Step 2: Vérifier l'échec** — `.venv/bin/pytest tests/test_server.py -v` → FAIL

- [ ] **Step 3: Implémenter**

`amazon_mcp/server.py` :
```python
import logging
from urllib.parse import quote_plus

try:
    from mcp.server import MCPServer
except ImportError:  # SDK v1
    from mcp.server.fastmcp import FastMCP as MCPServer

from amazon_mcp import db
from amazon_mcp.config import DB_PATH, HOST, MCP_SECRET_PATH, PORT, TRACK_INTERVAL_HOURS
from amazon_mcp import tracker as tracker_mod
from amazon_mcp.parsers.product import parse_product
from amazon_mcp.parsers.search import parse_search
from amazon_mcp.scraping.engine import ScraperEngine
from amazon_mcp.utils import extract_asin, product_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = MCPServer("Amazon FR")
engine = ScraperEngine()
_db_path = DB_PATH  # surchargé en test


def _conn():
    return db.get_conn(_db_path)


@mcp.tool()
def search_products(query: str, max_results: int = 10) -> list[dict]:
    """Recherche des produits sur amazon.fr et retourne titre, prix, ASIN, URL, note, Prime."""
    html = engine.get_html(f"https://www.amazon.fr/s?k={quote_plus(query)}")
    return parse_search(html, max_results)


@mcp.tool()
def get_product(url_or_asin: str) -> dict:
    """Détails d'un produit amazon.fr (URL ou ASIN) : prix, disponibilité, note, avis, vendeur."""
    asin = extract_asin(url_or_asin)
    html = engine.get_html(product_url(asin))
    return parse_product(html, asin)


@mcp.tool()
def track_product(url_or_asin: str, label: str | None = None) -> dict:
    """Ajoute un produit au suivi de prix (relevé automatique périodique)."""
    return tracker_mod.track(engine, _conn(), url_or_asin, label)


@mcp.tool()
def untrack_product(asin: str) -> str:
    """Retire un produit du suivi de prix."""
    if db.remove_tracked(_conn(), extract_asin(asin)):
        return f"Produit {asin} retiré du suivi."
    return f"Produit {asin} introuvable dans le suivi."


@mcp.tool()
def list_tracked() -> list[dict]:
    """Liste les produits suivis avec dernier prix et variation."""
    rows = db.list_tracked(_conn())
    for r in rows:
        if r["last_price"] is not None and r["previous_price"] is not None:
            r["change"] = round(r["last_price"] - r["previous_price"], 2)
        else:
            r["change"] = None
    return rows


@mcp.tool()
def get_price_history(asin: str, days: int = 30) -> dict:
    """Historique de prix d'un produit suivi (série datée + min/max/actuel)."""
    asin = extract_asin(asin)
    points = db.price_history(_conn(), asin, days)
    prices = [p["price"] for p in points if p["price"] is not None]
    return {
        "asin": asin,
        "days": days,
        "points": points,
        "min": min(prices) if prices else None,
        "max": max(prices) if prices else None,
        "current": prices[-1] if prices else None,
    }


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: tracker_mod.refresh_all(engine, _conn()),
        IntervalTrigger(hours=TRACK_INTERVAL_HOURS, jitter=1800),
        id="refresh_prices",
    )
    scheduler.start()
    logger.info("Scheduler démarré (toutes les %s h)", TRACK_INTERVAL_HOURS)
    return scheduler


def main():
    _conn().close()  # crée le schéma au démarrage
    _start_scheduler()
    logger.info("Serveur MCP sur %s:%s%s", HOST, PORT, MCP_SECRET_PATH)
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path=MCP_SECRET_PATH,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
```

Note : si le SDK installé est un v1 (`FastMCP`), `run()` n'accepte pas les kwargs de transport — les passer alors au constructeur (`FastMCP("Amazon FR", host=..., port=..., streamable_http_path=..., stateless_http=True)`) et appeler `mcp.run(transport="streamable-http")`. Trancher à l'exécution selon la version installée.

- [ ] **Step 4: Vérifier le succès** — `.venv/bin/pytest tests/test_server.py -v` → PASS, puis suite complète `.venv/bin/pytest -v` → PASS

- [ ] **Step 5: Smoke test local du transport HTTP**

Run: `MCP_SECRET_PATH=/mcp-test .venv/bin/python -m amazon_mcp.server & sleep 3 && curl -s -X POST http://127.0.0.1:8321/mcp-test -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' ; kill %1`
Expected: réponse JSON-RPC `initialize` avec `serverInfo.name` = "Amazon FR".

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: serveur MCP avec 6 outils + scheduler"`

---

### Task 9: Docker + Nginx + README de déploiement

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `deploy/nginx.conf`, `README.md`

- [ ] **Step 1: Fichiers Docker**

`Dockerfile` :
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY amazon_mcp ./amazon_mcp
RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium \
    && rm -rf /root/.cache

ENV DB_PATH=/data/amazon.db
EXPOSE 8321
CMD ["python", "-m", "amazon_mcp.server"]
```

`.dockerignore` :
```
.venv
.git
data
tests
docs
__pycache__
```

`docker-compose.yml` :
```yaml
services:
  amazon-mcp:
    build: .
    container_name: amazon-mcp
    restart: unless-stopped
    ports:
      - "127.0.0.1:8321:8321"
    env_file: .env
    environment:
      - DB_PATH=/data/amazon.db
    volumes:
      - ./data:/data
```

- [ ] **Step 2: Config Nginx**

`deploy/nginx.conf` :
```nginx
server {
    server_name amazon.mcp.mawena.cloud;
    listen 80;

    location / {
        proxy_pass http://127.0.0.1:8321;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;          # indispensable pour le streaming SSE
        proxy_read_timeout 300s;
    }
}
```

- [ ] **Step 3: README complet**

`README.md` — sections obligatoires (rédiger intégralement) :
1. Présentation + liste des 6 outils.
2. Dev local : venv, `pip install -e ".[dev]"`, `playwright install chromium`, `pytest`, lancement local.
3. Déploiement VPS pas-à-pas :
   - cloner le repo sur le VPS, `cp .env.example .env`, générer `MCP_SECRET_PATH` avec `python3 -c "import secrets; print('/mcp-'+secrets.token_urlsafe(12))"`
   - `docker compose up -d --build`
   - copier `deploy/nginx.conf` vers `/etc/nginx/sites-available/amazon-mcp`, `ln -s` vers `sites-enabled`, `nginx -t && systemctl reload nginx`
   - `certbot --nginx -d amazon.mcp.mawena.cloud`
   - test : `curl -i https://amazon.mcp.mawena.cloud<MCP_SECRET_PATH>` (405/406 attendu en GET simple = serveur vivant)
4. Connexion des clients Claude :
   - **claude.ai** : Paramètres → Connecteurs → Ajouter un connecteur personnalisé → URL `https://amazon.mcp.mawena.cloud<MCP_SECRET_PATH>`
   - **Claude Code** : `claude mcp add --transport http amazon https://amazon.mcp.mawena.cloud<MCP_SECRET_PATH>`
   - **Claude Desktop** : Paramètres → Connecteurs → Ajouter (même URL)
5. Note légale (CGU Amazon, usage perso faible volume) + avertissement de garder l'URL secrète.

- [ ] **Step 4: Vérifier la config compose** — Run: `docker compose config -q` → aucune erreur (si Docker absent en local, vérification faite sur le VPS).

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: déploiement Docker + Nginx + doc"`

---

## Self-Review (fait)

- **Couverture spec :** cascade (T4–T5), parsers extensibles (T6), 6 outils (T8), SQLite+historique (T3), scheduler 6 h+jitter+délais (T7–T8), chemin secret+stateless HTTP (T1, T8), Docker/Nginx/certbot/README (T9), erreurs FR (T5, T8), tests sans réseau (tous). ✓
- **Placeholders :** aucun TBD ; le README (T9) est spécifié section par section avec les commandes exactes. ✓
- **Cohérence des types :** `ScraperEngine.get_html`, `parse_product(html, asin)`, signatures `db.*` et `tracker.*` identiques entre tâches. ✓
