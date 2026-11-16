# HTTP routes for group movements (S5-1). All rules live in Domain/group_operations.py;
# this file only turns requests into service calls and the service's errors into HTTP codes.
# See docs/group-operations.md for the workflow and the warning-acknowledgement contract.

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .Domain.group_operations import GroupOperationError, GroupOperationService, OperationView

router = APIRouter(prefix="/api/group-operations", tags=["group operations"])

# Which HTTP status each kind of refusal gets. Messages already say whether anything was sent.
_STATUS = {
    "invalid_input": 422,
    "not_found": 404,
    "desk_not_found": 404,
    "conflict": 409,
    "desks_not_ready": 409,
    "not_active": 409,
    "too_late": 409,
    "finished": 409,
    "simulator_unavailable": 502,
    "unavailable": 503,
}


class GroupOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desk_ids: List[str] = Field(description="Desks to move. At least one, no repeats.")
    # Strict, like the single-desk endpoint: 900.5 or "900" are rejected, not rounded.
    target_position_mm: StrictInt


class AcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = Field(description="Who is warning: for example pico or dashboard.")


class AcknowledgementResponse(BaseModel):
    channel: str
    acknowledged_at: datetime
    last_confirmed_at: datetime


class DeskResultResponse(BaseModel):
    desk_id: str
    result: str
    detail: str
    # What the movement workflow recorded for the command, once one was attempted.
    command_status: Optional[str] = None   # accepted, failed or unknown
    command_id: Optional[int] = None
    accepted_position_mm: Optional[int] = None
    last_position_mm: Optional[int] = None
    last_status: Optional[str] = None
    last_observed_at: Optional[datetime] = None


class GroupOperationResponse(BaseModel):
    operation_id: str
    state: str
    message: str
    desk_ids: List[str]
    target_position_mm: int
    created_at: datetime
    countdown_seconds: float
    acknowledgement_deadline: datetime
    warning_deadline: Optional[datetime]
    seconds_remaining: Optional[float]
    dispatched_at: Optional[datetime]
    finished_at: Optional[datetime]
    required_channels: List[str]
    acknowledgements: List[AcknowledgementResponse]
    blocked_code: Optional[str]
    blocked_message: Optional[str]
    cancellable: bool
    desks: List[DeskResultResponse]

    @classmethod
    def from_view(cls, view: OperationView):
        desks = []
        for desk in view.desks:
            move = desk.move
            desks.append(DeskResultResponse(
                desk_id=desk.desk_id,
                result=desk.result,
                detail=desk.detail,
                command_status=move.status if move else None,
                command_id=move.command_id if move else None,
                accepted_position_mm=move.accepted_mm if move else None,
                last_position_mm=desk.last_position_mm,
                last_status=desk.last_status,
                last_observed_at=desk.last_observed_at,
            ))
        return cls(
            operation_id=view.operation_id,
            state=view.state,
            message=view.message,
            desk_ids=list(view.desk_ids),
            target_position_mm=view.target_position_mm,
            created_at=view.created_at,
            countdown_seconds=view.countdown_seconds,
            acknowledgement_deadline=view.acknowledgement_deadline,
            warning_deadline=view.warning_deadline,
            seconds_remaining=view.seconds_remaining,
            dispatched_at=view.dispatched_at,
            finished_at=view.finished_at,
            required_channels=list(view.required_channels),
            acknowledgements=[AcknowledgementResponse(**vars(ack)) for ack in view.acknowledgements],
            blocked_code=view.blocked_code,
            blocked_message=view.blocked_message,
            cancellable=view.cancellable,
            desks=desks,
        )


class ActiveWarningsResponse(BaseModel):
    """What the Pico and the dashboard poll to know whether a warning must be shown."""

    warning_active: bool
    operations: List[GroupOperationResponse]


def get_group_service(request: Request) -> GroupOperationService:
    """The service created at startup; tests replace this dependency."""
    return request.app.state.group_service


def _call(function, *args):
    try:
        return function(*args)
    except GroupOperationError as error:
        raise HTTPException(status_code=_STATUS.get(error.reason, 400), detail=str(error)) from None


@router.post("", response_model=GroupOperationResponse, status_code=201)
def create_group_operation(
    request: GroupOperationRequest,
    service: GroupOperationService = Depends(get_group_service),
):
    """Publish the warning for a group movement. No desk moves until the countdown ends."""
    return GroupOperationResponse.from_view(_call(service.create, request.desk_ids, request.target_position_mm))


# Declared before /{operation_id} so "active-warning" is not read as an operation ID.
@router.get("/active-warning", response_model=ActiveWarningsResponse)
def get_active_warning(service: GroupOperationService = Depends(get_group_service)):
    operations = [GroupOperationResponse.from_view(view) for view in service.active_warnings()]
    return ActiveWarningsResponse(warning_active=bool(operations), operations=operations)


@router.get("/{operation_id}", response_model=GroupOperationResponse)
def get_group_operation(operation_id: str, service: GroupOperationService = Depends(get_group_service)):
    return GroupOperationResponse.from_view(_call(service.get, operation_id))


@router.post("/{operation_id}/acknowledge", response_model=GroupOperationResponse)
def acknowledge_group_warning(
    operation_id: str,
    request: AcknowledgementRequest,
    service: GroupOperationService = Depends(get_group_service),
):
    """A warning channel confirms its warning is showing. Repeat it while the warning lasts."""
    return GroupOperationResponse.from_view(_call(service.acknowledge, operation_id, request.channel))


@router.post("/{operation_id}/cancel", response_model=GroupOperationResponse)
def cancel_group_operation(operation_id: str, service: GroupOperationService = Depends(get_group_service)):
    """Cancel before dispatch. After commands were sent this is refused (it is not an emergency stop)."""
    return GroupOperationResponse.from_view(_call(service.cancel, operation_id))
