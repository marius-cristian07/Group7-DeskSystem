"""HTTP contract and safe presentation of shared movement results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .Domain.desk_workflow import MIN_HEIGHT_MM, MAX_HEIGHT_MM


class HeightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_position_mm: int = Field(strict=True, ge=MIN_HEIGHT_MM, le=MAX_HEIGHT_MM)


class HeightResponse(BaseModel):
    desk_id: str
    requested_position_mm: int
    accepted_position_mm: int | None
    command_id: int | None
    status: Literal["accepted", "failed", "unknown"]
    error: str | None
    recording_error: str | None
    follow_up_error: str | None
    reading_id: int | None

    @classmethod
    def from_result(cls, result):
        # Never serialize raw infrastructure errors: they can contain credentials.
        errors = {
            "accepted": None,
            "failed": "The simulator rejected the movement request.",
            "unknown": "Acceptance could not be confirmed. The desk may have moved; check its state before another request.",
        }
        return cls(
            desk_id=result.desk_id,
            requested_position_mm=result.requested_mm,
            accepted_position_mm=result.accepted_mm,
            command_id=result.command_id,
            status=result.status,
            error=errors[result.status],
            recording_error="Could not record the movement request." if result.record_error else None,
            follow_up_error="Could not retrieve or save the follow-up reading." if result.reading_error else None,
            reading_id=result.reading.reading_id if result.reading else None,
        )
