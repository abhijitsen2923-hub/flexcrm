import re
import unicodedata


def make_schema_name(business_type: str, org_name: str) -> str:
    """Derive a safe PostgreSQL schema name from org attributes.

    Format: {business_type}_{slugified_name}, truncated to 63 chars (Postgres limit).
    Only lowercase alphanumerics and underscores; starts with a letter.
    """
    raw = f"{business_type}_{org_name}"
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"org_{slug}".strip("_")
    return slug[:63]
