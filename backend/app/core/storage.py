"""S3-compatible object storage (Backblaze B2 / Cloudflare R2 / AWS S3).

Configured via the ``S3_*`` settings. The layer is provider-agnostic — it talks
plain S3 to whatever ``S3_ENDPOINT_URL`` points at, so Backblaze B2 today and any
other S3 store tomorrow work unchanged.

When the settings are unset, every operation raises a clean **503** ("File storage
is not configured") rather than 500ing — so local/dev and not-yet-provisioned
deploys keep working for everything else, and the missing config is obvious.

Buckets are private; callers hand out short-lived **presigned GET URLs** for
downloads instead of making objects public.
"""
from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import get_settings


def is_configured() -> bool:
    s = get_settings()
    return bool(
        s.s3_endpoint_url and s.s3_bucket and s.s3_access_key_id and s.s3_secret_access_key
    )


def _require_configured() -> None:
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured.",
        )


@lru_cache
def _client():
    # Imported lazily so environments without boto3 (or without storage
    # configured) don't pay the import at startup.
    import boto3
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def put_object(key: str, data: bytes, content_type: str | None = None) -> str:
    """Upload bytes to ``key`` and return the key. Raises 503 if unconfigured."""
    _require_configured()
    s = get_settings()
    extra = {"ContentType": content_type} if content_type else {}
    _client().put_object(Bucket=s.s3_bucket, Key=key, Body=data, **extra)
    return key


def presigned_get_url(key: str, ttl: int | None = None) -> str:
    """Return a short-lived signed GET URL for ``key``. Raises 503 if unconfigured."""
    _require_configured()
    s = get_settings()
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": s.s3_bucket, "Key": key},
        ExpiresIn=ttl or s.s3_presign_ttl_seconds,
    )


def delete_object(key: str) -> None:
    _require_configured()
    s = get_settings()
    _client().delete_object(Bucket=s.s3_bucket, Key=key)


# --- Key layout ------------------------------------------------------------
# Keys are scoped by organization for bucket tidiness / tenant isolation. UUIDs
# are globally unique so this is organisational, not a correctness requirement.

def _safe_name(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "._-") else "_" for c in (name or "file"))
    return keep[-120:] or "file"


def kyc_key(org_id: UUID, booking_id: UUID, doc_id: UUID, filename: str) -> str:
    return f"org/{org_id}/bookings/{booking_id}/kyc/{doc_id}_{_safe_name(filename)}"


def doc_key(org_id: UUID, booking_id: UUID, doc_type: str) -> str:
    # Deterministic per (booking, doc_type): regenerating a document overwrites.
    return f"org/{org_id}/bookings/{booking_id}/documents/{doc_type}.pdf"


def receipt_key(org_id: UUID, booking_id: UUID, receipt_id: UUID) -> str:
    return f"org/{org_id}/bookings/{booking_id}/receipts/{receipt_id}.pdf"


def token_receipt_key(org_id: UUID, booking_id: UUID) -> str:
    # Deterministic per booking: re-recording the token overwrites the receipt.
    return f"org/{org_id}/bookings/{booking_id}/token-receipt.pdf"


def media_key(org_id: UUID, project_id: UUID, media_id: UUID, filename: str) -> str:
    return f"org/{org_id}/projects/{project_id}/media/{media_id}_{_safe_name(filename)}"
