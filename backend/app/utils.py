"""Small shared helpers."""

import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str, max_length: int = 60) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _NON_SLUG.sub("-", normalized.lower()).strip("-")
    return (slug[:max_length].strip("-")) or "org"
