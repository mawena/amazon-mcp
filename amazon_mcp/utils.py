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
