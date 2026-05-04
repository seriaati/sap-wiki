import re

LINK_RE = re.compile(r"\[\[([^\]|]+)\|[^\]]+\]\]")
ICON_RE = re.compile(r"\s*\{[A-Z][A-Za-z]*Icon\}\s*")


def clean(text: str) -> str:
    if not text:
        return text
    text = LINK_RE.sub(r"\1", text)
    text = ICON_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()
