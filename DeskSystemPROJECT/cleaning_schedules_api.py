"""HTTP API for S5-2 schedules and cancellation of individual cleaning runs."""

from datetime import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from .Data import cleaning_schedule_repository as repository
from .Data.cleaning_schedule_repository import ScheduleBusyError, ScheduleConflictError
from .Data.database import DatabaseError
from .Data.desk_command_repository import desk_exists
from .Domain.group_operations import GroupOperationError
from .group_operations_api import get_group_service

router = APIRouter(prefix="/api/cleaning-schedules", tags=["cleaning schedules"])


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1)
    cleaning_height_mm: int = Field(ge=680, le=1320)
    return_height_mm: int = Field(ge=680, le=1320)
    start_time: time
    end_time: time
    timezone: str = "Europe/Copenhagen"
    desk_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def check_schedule(self):
        if not self.name.strip():
            raise ValueError("Schedule name cannot be empty")
        if self.start_time == self.end_time:
            raise ValueError("Start and end times must be different")
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("Times must not include UTC offsets")
        if any(t.second or t.microsecond for t in (self.start_time, self.end_time)):
            raise ValueError("Start and end must use whole minutes")
        if self.timezone != "Europe/Copenhagen":
            raise ValueError("Only Europe/Copenhagen is supported")
        if len(self.desk_ids) != len(set(self.desk_ids)):
            raise ValueError("Duplicate desk IDs are not allowed")
        if any(not desk_id.strip() for desk_id in self.desk_ids):
            raise ValueError("Desk IDs cannot be empty")
        return self


def _check_desks(desk_ids):
    for desk_id in desk_ids:
        if not desk_exists(desk_id):
            raise HTTPException(status_code=422, detail=f"Desk {desk_id} does not exist")


@router.get("")
def get_all_schedules():
    try:
        return repository.list_schedules()
    except DatabaseError:
        raise HTTPException(503, "Database is unavailable") from None


@router.get("/{schedule_id}")
def get_schedule(schedule_id: int):
    try:
        result = repository.get_schedule(schedule_id)
    except DatabaseError:
        raise HTTPException(503, "Database is unavailable") from None
    if result is None:
        raise HTTPException(404, "Schedule not found")
    return result


@router.post("", status_code=201)
def create_schedule(data: ScheduleCreate):
    try:
        _check_desks(data.desk_ids)
        schedule_id = repository.create_schedule(
            name=data.name,
            cleaning_height_mm=data.cleaning_height_mm,
            return_height_mm=data.return_height_mm,
            start_time=data.start_time,
            end_time=data.end_time,
            timezone=data.timezone,
            desk_ids=data.desk_ids,
        )
        return {"schedule_id": schedule_id}
    except ScheduleConflictError as error:
        raise HTTPException(409, str(error)) from None
    except DatabaseError:
        raise HTTPException(503, "Database is unavailable") from None


@router.put("/{schedule_id}")
def update_schedule(schedule_id: int, data: ScheduleCreate):
    try:
        _check_desks(data.desk_ids)
        updated = repository.update_schedule(
            schedule_id=schedule_id,
            name=data.name,
            cleaning_height_mm=data.cleaning_height_mm,
            return_height_mm=data.return_height_mm,
            start_time=data.start_time,
            end_time=data.end_time,
            timezone=data.timezone,
            desk_ids=data.desk_ids,
        )
    except ScheduleBusyError as error:
        raise HTTPException(409, str(error)) from None
    except ScheduleConflictError as error:
        raise HTTPException(409, str(error)) from None
    except DatabaseError:
        raise HTTPException(503, "Database is unavailable") from None
    if not updated:
        raise HTTPException(404, "Schedule not found")
    return {"schedule_id": schedule_id, "updated": True}


@router.post("/{schedule_id}/disable")
def disable_schedule(schedule_id: int):
    try:
        disabled = repository.disable_schedule(schedule_id)
    except DatabaseError:
        raise HTTPException(503, "Database is unavailable") from None
    if not disabled:
        raise HTTPException(404, "Schedule not found")
    return {"schedule_id": schedule_id, "is_enabled": False}


@router.post("/runs/{run_id}/cancel")
def cancel_cleaning_run(run_id: int, group_service=Depends(get_group_service)):
    """Cancel a run. A dispatched S5-1 movement cannot be stopped by this endpoint."""
    try:
        run = repository.get_cleaning_run(run_id)
        if run is None:
            raise HTTPException(404, "Cleaning run not found")
        status = run["status"]
        if status == "cancelled":
            return {"run_id": run_id, "status": "cancelled"}

        if status in ("raising", "returning"):
            operation_id = (run["raise_operation_id"] if status == "raising"
                            else run["return_operation_id"])
            if not operation_id:
                raise HTTPException(409, "Operation is not yet linked; cancellation is unsafe")
            try:
                operation = group_service.cancel(operation_id)
            except GroupOperationError as error:
                raise HTTPException(409, str(error)) from None
            if operation.state != "cancelled":
                raise HTTPException(409, "Movement was not cancelled")
        elif status not in ("scheduled", "cleaning"):
            raise HTTPException(409, f"Cannot cancel a run in state {status}")

        if not repository.set_run_status(run_id, status, "cancelled"):
            raise HTTPException(409, "Run changed concurrently; check its current state")
        return {
            "run_id": run_id,
            "status": "cancelled",
            "message": "No automatic return will occur. Inspect desk positions if already raised.",
        }
    except DatabaseError:
        raise HTTPException(503, "Database is unavailable") from None
