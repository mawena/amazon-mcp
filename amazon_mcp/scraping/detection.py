_MARKERS = (
    "/errors/validateCaptcha",
    "api-services-support@amazon.com",
    "Saisissez les caractères",
    "Robot Check",
    "To discuss automated access",
    "window.awsWafCookie",  # page de challenge AWS WAF (JS anti-bot)
)

# Marqueurs valables uniquement sur les petites pages (les interstitiels anti-bot
# font ~2 Ko ; une vraie page produit/recherche dépasse largement ce seuil).
_SMALL_PAGE_MARKERS = ("Continuer les achats",)
_SMALL_PAGE_THRESHOLD = 50_000

# Une vraie page Amazon contient au moins un de ces marqueurs de contenu.
# Le DOM rendu d'un challenge AWS WAF (~2 Ko) n'en contient aucun.
_CONTENT_MARKERS = ("productTitle", "s-search-result", "nav-logo")
_TINY_PAGE_THRESHOLD = 10_000


def is_blocked(html: str | None) -> bool:
    """Vrai si la page est vide ou est une page captcha/anti-robot d'Amazon."""
    if not html:
        return True
    if any(marker in html for marker in _MARKERS):
        return True
    if len(html) < _SMALL_PAGE_THRESHOLD and any(m in html for m in _SMALL_PAGE_MARKERS):
        return True
    if len(html) < _TINY_PAGE_THRESHOLD and not any(m in html for m in _CONTENT_MARKERS):
        return True
    return False
