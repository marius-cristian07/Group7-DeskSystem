# HTTP routes for S6-3: reviewing and resolving failed cleaning runs, group operations and
# desk incidents. All rules live in Domain/review_workflow.py and Data/review_repository.py.
# None of these routes sends a movement command. See docs/s6-3-review-workflow.md.

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .Data.database import DatabaseError
from .Data.review_repository import ReviewError
from .Domain.desk_workflow import DeskWorkflow
from .Domain.review_workflow import DECISIONS, MAX_EXPLANATION, MAX_NAME, MIN_EXPLANATION, ReviewWorkflow
from .config import get_simulator_config

router = APIRouter(tags=["review and resolution"])

# Which HTTP status each kind of refusal gets. The message always says whether anything changed.
_STATUS = {
    "invalid_input": 422,
    "not_found": 404,
    "not_reviewable": 409,
    "busy": 409,
    "desk_not_ready": 409,
    "changed": 409,
    "simulator_unavailable": 502,
    "unavailable": 503,
}


def get_review_workflow(request: Request) -> ReviewWorkflow:
    """The review workflow with the live simulator client; tests replace this dependency."""
    return ReviewWorkflow(
        lambda: DeskWorkflow(*get_simulator_config()),
        group_service=getattr(request.app.state, "group_service", None),
    )


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ReviewError as error:
        raise HTTPException(status_code=_STATUS.get(error.reason, 400), detail=str(error)) from None
    except DatabaseError:
        raise HTTPException(status_code=503, detail="Database is unavailable. Nothing was changed.") from None


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal[DECISIONS] = Field(description="What was decided. Required.")
    explanation: str = Field(
        min_length=MIN_EXPLANATION, max_length=MAX_EXPLANATION,
        description="Why this is safe to mark as reviewed. Required, recorded with the time.",
    )
    resolved_by: Optional[str] = Field(
        default=None, max_length=MAX_NAME,
        description="Who reviewed it. Optional: the system has no logins yet.",
    )

    @field_validator("explanation")
    @classmethod
    def _not_blank(cls, value):
        if len(value.strip()) < MIN_EXPLANATION:
            raise ValueError(f"explanation needs at least {MIN_EXPLANATION} characters of text")
        return value


class AcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None, max_length=MAX_EXPLANATION)
    acknowledged_by: Optional[str] = Field(default=None, max_length=MAX_NAME)


class ResolvedItems(BaseModel):
    cleaning_runs: List[int]
    group_operations: List[str]
    desk_incidents: List[int]


class ResolutionResponse(BaseModel):
    subject_type: str
    subject_id: str
    decision: str
    explanation: str
    recorded_by: Optional[str]
    recorded_at: datetime
    record_id: int
    desk_checks: Dict[str, Any]
    resolved: ResolvedItems
    message: str


class AcknowledgementResponse(BaseModel):
    subject_type: str
    subject_id: str
    acknowledged_at: datetime
    recorded_at: datetime
    record_id: int
    message: str


class UnresolvedRun(BaseModel):
    run_id: int
    schedule_id: int
    schedule_name: str
    occurrence_date: date
    status: str
    raise_operation_id: Optional[str]
    return_operation_id: Optional[str]
    updated_at: datetime
    desk_ids: List[str]


class UnresolvedOperation(BaseModel):
    operation_id: str
    reason: str
    state: str
    finished_at: Optional[datetime]
    desk_ids: List[str]


class UnresolvedIncident(BaseModel):
    incident_id: int
    desk_id: str
    fault_category: str
    first_seen_at: datetime
    last_seen_at: datetime
    cleared_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    operation_id: Optional[str]
    blocks_starts: bool


class UnresolvedResponse(BaseModel):
    """What waits for review, and `blocking_desk_ids`: the desks on which automatic starts are blocked."""

    cleaning_runs: List[UnresolvedRun]
    group_operations: List[UnresolvedOperation]
    desk_incidents: List[UnresolvedIncident]
    blocking_desk_ids: List[str]


class ReviewRecord(BaseModel):
    record_id: int
    subject_type: str
    subject_id: str
    action: str
    decision: Optional[str]
    explanation: str
    recorded_by: Optional[str]
    desk_checks: Optional[Dict[str, Any]]
    recorded_at: datetime


class ReviewRecordsResponse(BaseModel):
    records: List[ReviewRecord]


# ---------- resolving ----------

@router.post("/api/cleaning-schedules/runs/{run_id}/resolve", response_model=ResolutionResponse)
def resolve_cleaning_run(
    run_id: int,
    request: ResolutionRequest,
    workflow: ReviewWorkflow = Depends(get_review_workflow),
):
    """Mark a run that needs review as resolved, with the operations and incidents it caused.

    Needs a decision, an explanation and fresh readings showing every involved desk reachable,
    healthy and standing still. Sends no movement command. The run is not repeated afterwards:
    only future occurrences run."""
    return _call(workflow.resolve_run, run_id, request.decision, request.explanation, request.resolved_by)


@router.post("/api/group-operations/{operation_id}/resolve", response_model=ResolutionResponse)
def resolve_group_operation(
    operation_id: str,
    request: ResolutionRequest,
    workflow: ReviewWorkflow = Depends(get_review_workflow),
):
    """Mark a failed or interrupted group operation as reviewed. Sends no movement command."""
    return _call(workflow.resolve_operation, operation_id, request.decision, request.explanation,
                 request.resolved_by)


@router.post("/api/desk-incidents/{incident_id}/resolve", response_model=ResolutionResponse)
def resolve_desk_incident(
    incident_id: int,
    request: ResolutionRequest,
    workflow: ReviewWorkflow = Depends(get_review_workflow),
):
    """Mark a cleared desk incident as reviewed. An incident that is still active cannot be resolved."""
    return _call(workflow.resolve_incident, incident_id, request.decision, request.explanation,
                 request.resolved_by)


# ---------- acknowledging ----------

@router.post("/api/desk-incidents/{incident_id}/acknowledge", response_model=AcknowledgementResponse)
def acknowledge_desk_incident(
    incident_id: int,
    request: AcknowledgementRequest,
    workflow: ReviewWorkflow = Depends(get_review_workflow),
):
    """Record that someone has seen the fault.

    This is not a resolution: the incident stays unresolved and keeps blocking automatic
    starts. It does not clear the fault, change any desk, or remove history."""
    return _call(workflow.acknowledge_incident, incident_id, request.note, request.acknowledged_by)


# ---------- reading ----------

@router.get("/api/reviews/unresolved", response_model=UnresolvedResponse)
def get_unresolved(
    desk_id: Optional[str] = Query(default=None, description="Only items involving this desk."),
    workflow: ReviewWorkflow = Depends(get_review_workflow),
):
    return _call(workflow.unresolved, desk_id)


@router.get("/api/reviews/records", response_model=ReviewRecordsResponse)
def get_review_records(
    subject_type: Optional[Literal["cleaning_run", "group_operation", "desk_incident"]] = None,
    subject_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    workflow: ReviewWorkflow = Depends(get_review_workflow),
):
    """The documented decisions and acknowledgements, newest first."""
    return {"records": _call(workflow.records, subject_type, subject_id, limit)}
