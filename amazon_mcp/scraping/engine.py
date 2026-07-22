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
        errors = []
        with self._lock:
            self._throttle()
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
