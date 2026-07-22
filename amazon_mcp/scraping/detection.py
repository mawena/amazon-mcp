_MARKERS = (
    "/errors/validateCaptcha",
    "api-services-support@amazon.com",
    "Saisissez les caractères",
    "Robot Check",
    "To discuss automated access",
)


def is_blocked(html: str | None) -> bool:
    """Vrai si la page est vide ou est une page captcha/anti-robot d'Amazon."""
    if not html:
        return True
    return any(marker in html for marker in _MARKERS)
