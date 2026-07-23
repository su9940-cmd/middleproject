"""Human-in-the-loop checklist submission contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ChecklistItemStatus


class ChecklistItemResult(BaseModel):
    """Worker result for one generated checklist item."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    checklist_item_id: str = Field(min_length=1)
    status: ChecklistItemStatus
    worker_note: str | None = None
    completed_at: datetime | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: object) -> object:
        """Accept checklist status strings case-insensitively."""

        if isinstance(value, str):
            return value.strip().upper()
        return value

    @model_validator(mode="after")
    def reject_pending_submission(self) -> "ChecklistItemResult":
        """A submitted checklist item must have a terminal worker result."""

        if self.status is ChecklistItemStatus.PENDING:
            raise ValueError("submitted checklist items cannot remain PENDING")
        return self


class WorkerResumePayload(BaseModel):
    """Validated payload used to resume an interrupted incident graph."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    response_id: str = Field(min_length=1)
    alert_id: str = Field(min_length=1)
    checklist_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    submitted_at: datetime
    item_results: list[ChecklistItemResult] = Field(min_length=1)
    overall_note: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
