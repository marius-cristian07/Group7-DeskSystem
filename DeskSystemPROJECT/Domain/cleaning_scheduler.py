"""S5-2 scheduler: determine due work, persist claims, delegate movement to S5-1."""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..Data import cleaning_schedule_repository as repository
from .cleaning_schedule_timing import get_window_utc
from .group_operations import GroupOperationError

logger = logging.getLogger(__name__)
ONE_MINUTE = timedelta(minutes=1)


class CleaningScheduler:
    def get_due_actions(self, now=None):
        """Find start/return actions due right now, never overdue catch-up actions."""
        now = now or datetime.now(timezone.utc)
        if now.utcoffset() is None:
            raise ValueError("now must have a timezone")
        now = now.astimezone(timezone.utc)
        today = now.astimezone(ZoneInfo("Europe/Copenhagen")).date()
        actions = []

        for schedule in repository.list_schedules():
            for day in (today - timedelta(days=1), today):
                try:
                    start, end = get_window_utc(schedule, day)
                except ValueError:
                    continue
                if schedule["is_enabled"] and start <= now < start + ONE_MINUTE:
                    actions.append(("start", schedule["schedule_id"], day))
                # Disabling a schedule must not suppress an already-authorized return.
                if end <= now < end + ONE_MINUTE:
                    actions.append(("return", schedule["schedule_id"], day))
        return actions

    def check_operations(self, group_service):
        """Mirror S5-1 terminal states. Never turn a cancelled raise into a return."""
        active = {"pending_warning", "countdown", "dispatching", "monitoring"}
        for run in repository.get_active_movement_runs():
            status = run["status"]
            operation_id = (run["raise_operation_id"] if status == "raising"
                            else run["return_operation_id"])
            if not operation_id:
                repository.set_run_status(run["run_id"], status, "needs_review")
                continue
            try:
                operation = group_service.get(operation_id)
            except GroupOperationError:
                # S5-1 may have forgotten the operation after an unexpected restart.
                repository.set_run_status(run["run_id"], status, "needs_review")
                continue
            if operation.state in active:
                continue
            if status == "raising":
                next_status = {
                    "completed": "cleaning",
                    "cancelled": "cancelled",
                    "blocked": "blocked",
                }.get(operation.state, "needs_review")
            else:
                next_status = "completed" if operation.state == "completed" else "needs_review"
            repository.set_run_status(run["run_id"], status, next_status)

    def mark_overdue(self, now):
        """If return time was missed, require review rather than a late movement."""
        for run in repository.get_unfinished_runs():
            try:
                _, end = get_window_utc(run, run["occurrence_date"])
            except ValueError:
                repository.set_run_status(run["run_id"], run["status"], "needs_review")
                continue
            if run["status"] in ("raising", "cleaning") and now >= end + ONE_MINUTE:
                repository.set_run_status(run["run_id"], run["status"], "needs_review")
            elif run["status"] == "returning" and now >= end + timedelta(minutes=5):
                repository.set_run_status(run["run_id"], "returning", "needs_review")

    def mark_missed_starts(self, now):
        """Record missed starts, without sending a surprise catch-up command."""
        today = now.astimezone(ZoneInfo("Europe/Copenhagen")).date()
        for schedule in repository.list_schedules():
            if not schedule["is_enabled"]:
                continue
            for day in (today - timedelta(days=1), today):
                try:
                    start, _ = get_window_utc(schedule, day)
                except ValueError:
                    # For a skipped DST time, obtain an approximate UTC instant
                    # only to mark it for review; NEVER use it for movement.
                    local = datetime.combine(
                        day, schedule["start_time"], tzinfo=ZoneInfo(schedule["timezone"])
                    )
                    start = local.astimezone(timezone.utc)
                if now >= start + ONE_MINUTE:
                    repository.claim_missed_start(schedule["schedule_id"], day, start)

    def tick(self, group_service, now=None):
        """One safe scheduler check; called by the backend's single background thread."""
        now = now or datetime.now(timezone.utc)
        if now.utcoffset() is None:
            raise ValueError("now must have a timezone")
        now = now.astimezone(timezone.utc)

        self.check_operations(group_service)
        self.mark_overdue(now)
        self.mark_missed_starts(now)

        for action, schedule_id, day in self.get_due_actions(now):
            schedule = repository.get_schedule(schedule_id)
            if schedule is None:
                continue
            try:
                start_at, _ = get_window_utc(schedule, day)
            except ValueError:
                continue

            if action == "start":
                run_id = repository.claim_cleaning_start(schedule_id, day, start_at)
                status, height = "raising", schedule["cleaning_height_mm"]
            else:
                run_id = repository.claim_cleaning_return(schedule_id, day)
                status, height = "returning", schedule["return_height_mm"]
            if run_id is None:
                continue  # Already claimed, disabled, or unsafe return.

            try:
                # S5-1 is the ONLY component allowed to request desk movements.
                operation = group_service.create(schedule["desk_ids"], height)
            except GroupOperationError:
                # S5-1.create fails before a movement can be dispatched.
                repository.set_run_status(run_id, status, "blocked")
                continue
            except Exception:
                repository.set_run_status(run_id, status, "needs_review")
                logger.exception("S5-1 request had an uncertain result; run %s", run_id)
                continue

            try:
                saved = (repository.save_raise_operation(run_id, operation.operation_id)
                         if action == "start" else
                         repository.save_return_operation(run_id, operation.operation_id))
            except Exception:
                logger.exception("Could not persist S5-1 operation ID for run %s", run_id)
                saved = False
            if not saved:
                # Do not risk a group operation continuing without a persistent link.
                try:
                    group_service.cancel(operation.operation_id)
                except GroupOperationError:
                    logger.warning("S5-1 operation %s could not be cancelled", operation.operation_id)
                try:
                    repository.set_run_status(run_id, status, "needs_review")
                except Exception:
                    logger.exception("Could not mark uncertain run %s for review", run_id)