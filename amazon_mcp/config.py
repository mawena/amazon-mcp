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
