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
