import json
from pathlib import Path

import pytest

from amazon_mcp import server
from amazon_mcp.scraping.backends import ScraperBackend
from amazon_mcp.scraping.engine import ScraperEngine

try:
    from mcp import Client

    def client_session():
        return Client(server.mcp)
except ImportError:  # SDK v1
    from mcp.shared.memory import create_connected_server_and_client_session

    def client_session():
        return create_connected_server_and_client_session(server.mcp._mcp_server)

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


def get_data(result):
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_scraping_runs_outside_event_loop(monkeypatch):
    """Régression : Playwright sync exige que fetch() tourne hors de la boucle asyncio."""
    import asyncio

    class LoopCheckBackend(ScraperBackend):
        name = "loopcheck"

        def fetch(self, url):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass  # hors de la boucle : OK
            else:
                raise AssertionError("fetch() exécuté dans la boucle asyncio")
            return (FIXTURES / "product.html").read_text()

    monkeypatch.setattr(server, "engine", ScraperEngine(backends=[LoopCheckBackend()], min_interval=0))
    async with client_session() as client:
        result = await client.call_tool("get_product", {"url_or_asin": "B08N5WRWNW"})
    assert not result.isError, result.content[0].text
    assert get_data(result)["price"] == 89.99


@pytest.mark.anyio
async def test_search_products():
    async with client_session() as client:
        result = await client.call_tool("search_products", {"query": "clavier", "max_results": 5})
    data = get_data(result)
    assert data[0]["asin"] == "B0AAAA0001"


@pytest.mark.anyio
async def test_get_product():
    async with client_session() as client:
        result = await client.call_tool("get_product", {"url_or_asin": "B08N5WRWNW"})
    assert get_data(result)["price"] == 89.99


@pytest.mark.anyio
async def test_track_untrack_history():
    async with client_session() as client:
        await client.call_tool("track_product", {"url_or_asin": "B08N5WRWNW", "label": "Clavier"})
        listed = get_data(await client.call_tool("list_tracked", {}))
        assert listed[0]["asin"] == "B08N5WRWNW"
        hist = get_data(await client.call_tool("get_price_history", {"asin": "B08N5WRWNW"}))
        assert hist["current"] == 89.99
        removed = await client.call_tool("untrack_product", {"asin": "B08N5WRWNW"})
        assert "retiré" in removed.content[0].text
