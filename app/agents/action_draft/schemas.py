"""Structured LLM output used to compose a grounded checklist draft.

The LLM selects source document keys and proposes checklist wording. Stable
identifiers and source metadata are attached by server-side code afterwards;
the model is never trusted to mint identifiers or citations on its own.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DraftedAction(BaseModel):
    """One LLM-proposed action before server-side grounding."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=1000)
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    required: bool
    source_keys: list[str] = Field(min_length=1)
    previously_failed: bool

    @field_validator("source_keys")
    @classmethod
    def source_keys_must_not_contain_blanks(cls, value: list[str]) -> list[str]:
        cleaned = [key.strip() for key in value if key and key.strip()]
        if not cleaned:
            raise ValueError("source_keys must contain at least one non-blank key")
        return cleaned


class DraftedChecklist(BaseModel):
    """Complete structured response expected from the Action Draft LLM."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=500)
    actions: list[DraftedAction]
