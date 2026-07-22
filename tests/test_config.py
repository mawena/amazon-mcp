from amazon_mcp import config


def test_defaults():
    assert config.PORT == 8321
    assert config.MCP_SECRET_PATH.startswith("/")
    assert config.MIN_REQUEST_INTERVAL >= 3.0
