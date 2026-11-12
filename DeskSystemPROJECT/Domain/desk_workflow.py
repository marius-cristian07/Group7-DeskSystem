# Coordinates the CLI's three actions: show reads desks, sync saves snapshots,
# and move requests a height, records the outcome, then takes a follow-up reading.
# API and SQL details live in Data; this file returns result objects for UI/cli.py to print.

import re
import time
from dataclasses import dataclass
from typing import List, Optional

from ..Data import desk_api_client, desk_command_repository, desk_repository
from ..Data.desk_api_client import DeskAPIError
from ..Data.desk_command_repository import STATUS_ACCEPTED, STATUS_FAILED, STATUS_UNKNOWN
from ..Data.database import DatabaseError, get_database_connection


class WorkflowError(Exception):
    """A command was stopped BEFORE anything was sent to a desk."""

    def __init__(self, message, reason="unavailable"):
        super().__init__(message)
        self.reason = reason


# Match the simulator's default travel range. Shared by HTTP and CLI callers.
MIN_HEIGHT_MM = 680
MAX_HEIGHT_MM = 1320


def validate_movement(desk_id, target_mm):
    """Validate user input before configuration, storage, or simulator access."""
    if not isinstance(desk_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:_-]{0,127}", desk_id):
        raise WorkflowError("Invalid desk identifier", reason="invalid_input")
    if type(target_mm) is not int or not MIN_HEIGHT_MM <= target_mm <= MAX_HEIGHT_MM:
        raise WorkflowError(
            f"Target height must be a whole number from {MIN_HEIGHT_MM} to {MAX_HEIGHT_MM} mm",
            reason="invalid_input",
        )


# These result classes carry data and per-step errors back to the CLI.
# @dataclass supplies the constructor, so callers can create them from field values.
@dataclass
class DeskReading:
    """The values of one saved reading, for display."""
    desk_id: str
    name: str
    position_mm: int
    speed_mms: int
    status: str
    reading_id: int


@dataclass
class FetchedDesk:
    """One desk from the API (record) or the reason it could not be fetched."""
    desk_id: str
    record: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class SyncItem:
    """Result of synchronising one desk."""
    desk_id: str
    reading: Optional[DeskReading] = None
    error: Optional[str] = None


@dataclass
class SyncReport:
    items: List[SyncItem]

    @property
    def saved(self):
        return sum(1 for item in self.items if item.reading is not None)

    @property
    def failed(self):
        return len(self.items) - self.saved


@dataclass
class MoveResult:
    """What happened to one movement request."""
    desk_id: str
    requested_mm: int
    status: str                          # "accepted", "failed" (rejected), or "unknown"
    accepted_mm: Optional[int] = None    # target the desk confirmed (may differ)
    error: Optional[str] = None          # why the API request failed
    command_id: Optional[int] = None     # row in desk_commands
    record_error: Optional[str] = None   # set if the row could not be saved
    reading: Optional[DeskReading] = None
    reading_error: Optional[str] = None  # set if the follow-up reading failed

    @property
    def succeeded(self):
        """True only if accepted, recorded, and the new reading was saved."""
        return (
            self.status == STATUS_ACCEPTED
            and self.command_id is not None
            and self.reading is not None
        )


def _make_reading(record, reading_id):
    return DeskReading(
        desk_id=record["desk_id"],
        name=record["config"]["name"],
        position_mm=record["state"]["position_mm"],
        speed_mms=record["state"]["speed_mms"],
        status=record["state"]["status"],
        reading_id=reading_id,
    )


def _read_accepted_height(response):
    """Return the target height confirmed by the API, or raise DeskAPIError."""
    if type(response) is dict and type(response.get("position_mm")) is int:
        return response["position_mm"]
    raise DeskAPIError("The API did not confirm the requested height")


def _text(error):
    """One-line message (database errors can span several lines)."""
    return " ".join(str(error).split())


def _sentence(text):
    """Make sure a message ends with punctuation before more text follows."""
    return text if text.endswith((".", "?", "!")) else text + "."


class DeskWorkflow:
    def __init__(
        self,
        base_url,
        api_key,
        api=desk_api_client,
        readings=desk_repository,
        commands=desk_command_repository,
        sleep=time.sleep,
        connect=get_database_connection,
    ):
        self.base_url = base_url
        self.api_key = api_key
        # Keep API and storage calls replaceable so tests need no running services.
        self.api = api
        self.readings = readings
        self.commands = commands
        self.sleep = sleep
        self.connect = connect

    # Check configuration and database access before starting work.

    def _check_config(self):
        try:
            self.api.validate_config(self.base_url, self.api_key)
        except DeskAPIError as error:
            raise WorkflowError(_text(error)) from None

    def _check_database(self):
        """Fail early if PostgreSQL cannot be reached."""
        try:
            self.connect().close()
        except DatabaseError as error:
            raise WorkflowError(_text(error)) from None

    # Show: fetch each desk without opening a database connection.

    def fetch_all(self):
        """Fetch every desk from the API. Nothing is saved."""
        self._check_config()
        try:
            desk_ids = self.api.get_desk_ids(self.base_url, self.api_key)
        except DeskAPIError as error:
            raise WorkflowError(f"Cannot retrieve desk list: {_text(error)}") from None

        # Keep successful results even when another desk cannot be reached.
        fetched = []
        for desk_id in desk_ids:
            try:
                record = self.api.get_desk(self.base_url, self.api_key, desk_id)
                fetched.append(FetchedDesk(desk_id, record=record))
            except DeskAPIError as error:
                fetched.append(FetchedDesk(desk_id, error=_text(error)))
        return fetched

    # Sync: save desks independently so one failure does not discard the others.

    def sync_all(self):
        """Fetch all available desks and save one new reading for each."""
        self._check_config()
        self._check_database()
        try:
            desk_ids = self.api.get_desk_ids(self.base_url, self.api_key)
        except DeskAPIError as error:
            raise WorkflowError(f"Cannot retrieve desk list: {_text(error)}") from None
        # Each desk gets its own transaction and success or failure result.
        return SyncReport([self._sync_one(desk_id) for desk_id in desk_ids])

    def _sync_one(self, desk_id):
        try:
            record = self.api.get_desk(self.base_url, self.api_key, desk_id)
        except DeskAPIError as error:
            return SyncItem(desk_id, error=f"cannot retrieve desk: {_text(error)}")
        try:
            reading_id = self.readings.save_desk(record)
        except DatabaseError as error:
            return SyncItem(desk_id, error=f"cannot save reading: {_text(error)}")
        return SyncItem(desk_id, reading=_make_reading(record, reading_id))

    # Move: validate first, then send, record, and read back the desk.

    def request_height(self, desk_id, target_mm, wait_s=0):
        """
        Ask one desk to move to target_mm.

        Raises WorkflowError if the request is stopped before it is sent
        (bad input, database or API configuration problem, desk unknown).
        Once the request has been sent, a MoveResult is always returned.
        """
        try:
            desk_id = self._prepare_move(desk_id, target_mm)
        except WorkflowError as error:
            raise WorkflowError(
                f"{_sentence(str(error))} Nothing was sent.", error.reason,
            ) from None

        result = MoveResult(desk_id, target_mm, STATUS_FAILED)

        # 1. Send the request. The API's answer decides accepted / failed.
        try:
            response = self.api.set_desk_height(
                self.base_url, self.api_key, desk_id, target_mm
            )
            result.accepted_mm = _read_accepted_height(response)
            result.status = STATUS_ACCEPTED
        except DeskAPIError as error:
            # Only explicit client-error responses establish rejection. A timeout,
            # server error or unreadable acknowledgement may follow a real move.
            if error.status_code not in (400, 401, 403, 404, 405, 422):
                result.status = STATUS_UNKNOWN
            result.error = _text(error)

        # 2. Record it, whatever the outcome.
        try:
            result.command_id = self.commands.save_command(
                desk_id, target_mm, result.status
            )
        except DatabaseError as error:
            result.record_error = _text(error)

        # 3. If the desk accepted it, read the desk again and save the reading.
        if result.status == STATUS_ACCEPTED:
            if wait_s > 0:
                self.sleep(wait_s)
            self._follow_up(result)
        return result

    def _prepare_move(self, desk_id, target_mm):
        """Everything that must be true BEFORE a desk is sent a request."""
        validate_movement(desk_id, target_mm)
        self._check_config()
        self._check_database()
        self._ensure_desk_is_stored(desk_id)
        return desk_id

    def _ensure_desk_is_stored(self, desk_id):
        """
        Verify the desk is available and ensure its identity is stored first.
        desk_commands references desk(desk_id); save missing identities without
        adding a reading. Any failure here prevents sending a movement request.
        """
        try:
            # Check current availability even when the identity is already stored.
            record = self.api.get_desk(self.base_url, self.api_key, desk_id)
            if self.commands.desk_exists(desk_id):
                return
            self.commands.save_desk_identity(record)
        except DeskAPIError as error:
            raise WorkflowError(
                f"Desk {desk_id} could not be fetched from the API ({_text(error)})",
                reason="desk_not_found" if error.status_code == 404 else "simulator_unavailable",
            ) from None
        except DatabaseError as error:
            raise WorkflowError(_text(error)) from None

    def _follow_up(self, result):
        try:
            record = self.api.get_desk(self.base_url, self.api_key, result.desk_id)
        except DeskAPIError as error:
            result.reading_error = f"cannot retrieve desk again: {_text(error)}"
            return
        try:
            reading_id = self.readings.save_desk(record)
        except DatabaseError as error:
            result.reading_error = f"cannot save reading: {_text(error)}"
            return
        result.reading = _make_reading(record, reading_id)
