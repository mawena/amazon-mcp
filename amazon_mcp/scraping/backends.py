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
    """Interface commune : fetch(url) -> HTML.

    Ajouter un backend = sous-classer + l'insérer dans la cascade (engine.default_backends).
    """

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
        from playwright_stealth import Stealth

        from amazon_mcp.config import COOKIES_PATH
        from amazon_mcp.scraping.cookies import load_cookies
        from amazon_mcp.scraping.detection import is_blocked

        cookies = load_cookies(COOKIES_PATH)
        # Stealth masque les signaux d'automatisation (navigator.webdriver, etc.)
        # sur tous les contextes créés dans ce bloc.
        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    locale="fr-FR",
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    timezone_id="Europe/Paris",
                )
                if cookies:
                    context.add_cookies(cookies)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                # Le challenge AWS WAF se résout en JS puis recharge la page :
                # on attend jusqu'à ~20 s que du vrai contenu apparaisse.
                html = page.content()
                for _ in range(10):
                    if not is_blocked(html):
                        break
                    page.wait_for_timeout(2_000)
                    html = page.content()
                return html
            finally:
                browser.close()
