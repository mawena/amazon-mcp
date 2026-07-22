import logging
from functools import partial
from urllib.parse import quote_plus

import anyio.to_thread

from amazon_mcp import db
from amazon_mcp import tracker as tracker_mod
from amazon_mcp.config import DB_PATH, HOST, MCP_SECRET_PATH, PORT, TRACK_INTERVAL_HOURS
from amazon_mcp.parsers.product import parse_product
from amazon_mcp.parsers.search import parse_search
from amazon_mcp.scraping.engine import ScraperEngine
from amazon_mcp.utils import extract_asin, product_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:  # SDK v2
    from mcp.server import MCPServer

    mcp = MCPServer("Amazon FR")
    _V2 = True
except ImportError:  # SDK v1 : params transport dans le constructeur
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "Amazon FR",
        host=HOST,
        port=PORT,
        streamable_http_path=MCP_SECRET_PATH,
        stateless_http=True,
    )
    _V2 = False

engine = ScraperEngine()
_db_path = DB_PATH  # surchargé en test


def _conn():
    return db.get_conn(_db_path)


async def _scrape(url: str) -> str:
    # Le scraping (Playwright sync inclus) doit tourner hors de la boucle asyncio :
    # offload dans un thread worker pour ne pas bloquer le serveur.
    return await anyio.to_thread.run_sync(partial(engine.get_html, url))


@mcp.tool()
async def search_products(query: str, max_results: int = 10) -> list[dict]:
    """Recherche des produits sur amazon.fr et retourne titre, prix, ASIN, URL, note, Prime."""
    html = await _scrape(f"https://www.amazon.fr/s?k={quote_plus(query)}")
    return parse_search(html, max_results)


@mcp.tool()
async def get_product(url_or_asin: str) -> dict:
    """Détails d'un produit amazon.fr (URL ou ASIN) : prix, disponibilité, note, avis, vendeur."""
    asin = extract_asin(url_or_asin)
    html = await _scrape(product_url(asin))
    return parse_product(html, asin)


def _track_sync(url_or_asin: str, label: str | None) -> dict:
    # La connexion SQLite doit être créée dans le thread qui l'utilise.
    return tracker_mod.track(engine, _conn(), url_or_asin, label)


@mcp.tool()
async def track_product(url_or_asin: str, label: str | None = None) -> dict:
    """Ajoute un produit au suivi de prix (relevé automatique périodique)."""
    return await anyio.to_thread.run_sync(partial(_track_sync, url_or_asin, label))


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
    if _V2:
        mcp.run(
            transport="streamable-http",
            host=HOST,
            port=PORT,
            streamable_http_path=MCP_SECRET_PATH,
            stateless_http=True,
        )
    else:
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
