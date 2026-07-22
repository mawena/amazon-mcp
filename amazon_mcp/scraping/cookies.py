"""Chargement des cookies d'une session amazon.fr réelle pour Playwright.

Exporte tes cookies amazon.fr depuis ton navigateur (extension type
« Cookie-Editor », bouton Export → JSON) et place le fichier au chemin
`COOKIES_PATH` (déf. data/cookies.json). Ils seront injectés dans le
contexte Playwright pour présenter une session déjà connectée.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Format d'export navigateur -> valeurs sameSite acceptées par Playwright.
_SAMESITE_MAP = {
    "no_restriction": "None",
    "none": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "Lax",
}


def normalize_cookies(raw: list) -> list[dict]:
    """Convertit des cookies au format d'export navigateur vers le format Playwright.

    Ignore les entrées sans `name` ou `domain` (invalides pour add_cookies).
    """
    out = []
    for c in raw:
        name, domain = c.get("name"), c.get("domain")
        if not name or not domain:
            continue
        cookie = {
            "name": name,
            "value": c.get("value", ""),
            "domain": domain,
            "path": c.get("path", "/"),
        }
        if "expirationDate" in c and c["expirationDate"]:
            cookie["expires"] = int(c["expirationDate"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        same_site = _SAMESITE_MAP.get(str(c.get("sameSite", "")).lower())
        if same_site:
            cookie["sameSite"] = same_site
        out.append(cookie)
    return out


def load_cookies(path: Path) -> list[dict]:
    """Charge et normalise les cookies depuis un fichier JSON. [] si absent/illisible."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cookies illisibles (%s) : %s", path, exc)
        return []
    if not isinstance(raw, list):
        logger.warning("Cookies : format inattendu (liste attendue) dans %s", path)
        return []
    return normalize_cookies(raw)
