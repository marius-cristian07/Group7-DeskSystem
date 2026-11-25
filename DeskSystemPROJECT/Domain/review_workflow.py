# S6-3: how a manager reviews and resolves a failure, and how that stays separate from movement.
#
#   needs_review --(documented decision + fresh healthy desks)--> resolved
#
# Resolving writes review records only. It never sends a movement command, never resets a
# desk flag and never deletes history. A follow-up movement is a separate, explicit request
# (the individual or group endpoints). Acknowledging a fault only records that someone saw it.
#
# The simulator is asked about the desks BEFORE the database transaction starts, and the
# transaction then re-checks the state under the review lock (see Data/review_repository.py).

"""Review, acknowledgement and resolution of cleaning failures."""

import logging
from datetime import datetime, timezone

from ..Data import review_repository
from ..Data.database import DatabaseError
from ..Data.desk_api_client import DeskAPIError
from ..Data.review_repository import ReviewError, SUBJECT_INCIDENT, SUBJECT_OPERATION, SUBJECT_RUN
from .desk_faults import classify_faults

logger = logging.getLogger(__name__)

# What the manager decided. A short fixed list keeps the history searchable.
DECISIONS = (
    "inspected_ok",       # the desks were inspected and no action is needed
    "moved_manually",     # the desks were moved or set right by hand, outside this system
    "fault_repaired",     # a fault was repaired
    "nothing_to_review",  # nothing moved or failed (for example a missed start)
)
MIN_EXPLANATION = 10
MAX_EXPLANATION = 1000
MAX_NAME = 100

NOT_A_MOVEMENT = "No movement command was sent. Any follow-up movement is a separate request."


def validate_decision(decision, explanation, recorded_by):
    """Return the cleaned explanation and name, or raise ReviewError (HTTP 422)."""
    if decision not in DECISIONS:
        raise ReviewError(f"decision must be one of: {', '.join(DECISIONS)}", "invalid_input")
    if not isinstance(explanation, str) or not MIN_EXPLANATION <= len(explanation.strip()) <= MAX_EXPLANATION:
        raise ReviewError(
            f"Explain the decision in {MIN_EXPLANATION} to {MAX_EXPLANATION} characters.", "invalid_input",
        )
    return explanation.strip(), _clean_name(recorded_by)


def _clean_name(name):
    if name is None:
        return None
    if not isinstance(name, str) or len(name.strip()) > MAX_NAME:
        raise ReviewError(f"The name can be at most {MAX_NAME} characters.", "invalid_input")
    return name.strip() or None


class ReviewWorkflow:
    def __init__(self, workflow_factory, group_service=None, repository=review_repository):
        # workflow_factory returns a DeskWorkflow: the same simulator client and reading
        # storage as the movement paths. It is used only to READ desks here.
        self._workflow_factory = workflow_factory
        self._group_service = group_service
        self._repository = repository

    # ---------- resolving ----------

    def resolve_run(self, run_id, decision, explanation, recorded_by=None):
        explanation, recorded_by = validate_decision(decision, explanation, recorded_by)
        checks = self._checked_desks(SUBJECT_RUN, run_id)
        result = self._repository.resolve_run(run_id, checks, decision, explanation, recorded_by)
        return self._finish(SUBJECT_RUN, run_id, decision, explanation, recorded_by, checks, result)

    def resolve_operation(self, operation_id, decision, explanation, recorded_by=None):
        explanation, recorded_by = validate_decision(decision, explanation, recorded_by)
        checks = self._checked_desks(SUBJECT_OPERATION, operation_id)
        result = self._repository.resolve_operation(operation_id, checks, decision, explanation, recorded_by)
        return self._finish(SUBJECT_OPERATION, operation_id, decision, explanation, recorded_by, checks, result)

    def resolve_incident(self, incident_id, decision, explanation, recorded_by=None):
        explanation, recorded_by = validate_decision(decision, explanation, recorded_by)
        checks = self._checked_desks(SUBJECT_INCIDENT, incident_id)
        result = self._repository.resolve_incident(incident_id, checks, decision, explanation, recorded_by)
        return self._finish(SUBJECT_INCIDENT, incident_id, decision, explanation, recorded_by, checks, result)

    def _finish(self, subject_type, subject_id, decision, explanation, recorded_by, checks, result):
        if self._group_service is not None:
            self._group_service.note_review_resolved(result["resolved"]["group_operations"])
        logger.info("%s %s resolved (%s): %s", subject_type, subject_id, decision, result["resolved"])
        return {
            "subject_type": subject_type,
            "subject_id": str(subject_id),
            "decision": decision,
            "explanation": explanation,
            "recorded_by": recorded_by,
            "recorded_at": result["recorded_at"],
            "record_id": result["record_id"],
            "desk_checks": checks,
            "resolved": result["resolved"],
            "message": f"Review recorded. {NOT_A_MOVEMENT}",
        }

    # ---------- acknowledging ----------

    def acknowledge_incident(self, incident_id, note=None, recorded_by=None):
        """Record that the fault has been seen. It is still unresolved and still blocks starts."""
        recorded_by = _clean_name(recorded_by)
        if note is not None and (not isinstance(note, str) or len(note.strip()) > MAX_EXPLANATION):
            raise ReviewError(f"The note can be at most {MAX_EXPLANATION} characters.", "invalid_input")
        note = (note or "").strip() or "Acknowledged without a note."
        result = self._repository.acknowledge_incident(incident_id, note, recorded_by)
        return {
            "subject_type": SUBJECT_INCIDENT,
            "subject_id": str(incident_id),
            "acknowledged_at": result["acknowledged_at"],
            "recorded_at": result["recorded_at"],
            "record_id": result["record_id"],
            "message": ("Acknowledged. The incident is not resolved: it still needs a review and "
                        "still blocks automatic starts on this desk."),
        }

    # ---------- the fresh desk checks ----------

    def _checked_desks(self, subject_type, subject_id):
        """Read every involved desk now. All must be reachable, healthy and standing still."""
        context = self._repository.get_review_context(subject_type, subject_id)
        if context is None:
            raise ReviewError("Record not found", "not_found")
        if not context["reviewable"]:
            raise ReviewError(
                f"This record is not waiting for review (current state: {context['status']}). "
                "Nothing was changed.",
                "not_reviewable",
            )
        # An incident that is still active is checked AFTER the fresh reading: a healthy
        # reading clears it, and the repository refuses if it is still active then.
        return self._read_desks(context["desk_ids"])

    def _read_desks(self, desk_ids):
        workflow = self._workflow_factory()
        try:
            workflow.api.validate_config(workflow.base_url, workflow.api_key)
        except DeskAPIError:
            raise ReviewError(
                "The simulator address or API key is not configured. Nothing was changed.", "unavailable",
            ) from None

        checks, problems = {}, []
        for desk_id in sorted(desk_ids):
            try:
                record = workflow.api.get_desk(workflow.base_url, workflow.api_key, desk_id)
            except DeskAPIError as error:
                if error.status_code == 404:
                    problems.append(f"{desk_id}: the desk is not available")
                    continue
                raise ReviewError(
                    "The simulator could not be reached to check the desks. Nothing was changed.",
                    "simulator_unavailable",
                ) from None
            state = record["state"]
            health = classify_faults(state)
            try:
                # Saved as evidence of what was seen. A healthy reading also clears an active
                # incident, exactly as the history collector would.
                reading_id = workflow.readings.save_desk(record)
            except DatabaseError:
                raise ReviewError(
                    "The fresh reading could not be saved, so the check cannot be documented. "
                    "Nothing was changed.",
                    "unavailable",
                ) from None
            if health.blocks_movement:
                detail = health.classification + (f" ({', '.join(health.faults)})" if health.faults else "")
                problems.append(f"{desk_id}: {detail}")
            elif state["speed_mms"] != 0:
                problems.append(f"{desk_id}: the desk is still moving")
            checks[desk_id] = {
                "classification": health.classification,
                "position_mm": state["position_mm"],
                "speed_mms": state["speed_mms"],
                "status": state["status"],
                "reading_id": reading_id,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        if problems:
            raise ReviewError(
                "The desks are not ready to be marked as reviewed: " + "; ".join(problems)
                + ". Nothing was changed.",
                "desk_not_ready",
            )
        return checks

    # ---------- reading ----------

    def unresolved(self, desk_id=None):
        return self._repository.list_unresolved(desk_id)

    def records(self, subject_type=None, subject_id=None, limit=50):
        if subject_type not in (None, SUBJECT_RUN, SUBJECT_OPERATION, SUBJECT_INCIDENT):
            raise ReviewError("Unknown subject_type", "invalid_input")
        if not 1 <= limit <= 200:
            raise ReviewError("limit must be 1-200", "invalid_input")
        return self._repository.list_records(subject_type, subject_id, limit)
