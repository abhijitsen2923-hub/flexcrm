from collections.abc import Iterable

from app.core.exceptions import ValidationError


def validate_sort_field(sort_by: str, allowed_fields: Iterable[str]) -> str:
    if sort_by not in allowed_fields:
        raise ValidationError(f"Unsupported sort field '{sort_by}'")
    return sort_by
