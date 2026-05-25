from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


class LeadDocumentRead(ORMModel):
    id: UUID
    lead_id: UUID
    doc_type: str
    status: str
    uploaded_path: str | None = None
    uploaded_at: datetime | None = None


class LeadDocumentUpload(ORMModel):
    doc_type: str = Field(min_length=1, max_length=64)
    uploaded_path: str | None = Field(default=None, max_length=512)
