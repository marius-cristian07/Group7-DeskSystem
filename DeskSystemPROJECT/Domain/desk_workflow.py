# Coordinates the CLI's three actions: show reads desks, sync saves snapshots,
# and move requests a height, records the outcome, then takes a follow-up reading.
# API and SQL details live in Data; this file returns result objects for UI/cli.py to print.

import time
from dataclasses import dataclass
from typing import List, Optional

from ..Data import desk_api_client, desk_command_repository, desk_repository
from ..Data.desk_api_client import DeskAPIError
from ..Data.desk_command_repository import STATUS_ACCEPTED, STATUS_FAILED
from ..Data.database import DatabaseError, get_database_connection


class WorkflowError(Exception):
    """A command was stopped BEFORE anything was sent to a desk."""


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
    status: str                          # "accepted" or "failed"
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
            raise WorkflowError(f"{_sentence(str(error))} Nothing was sent.") from None

        result = MoveResult(desk_id, target_mm, STATUS_FAILED)

        # 1. Send the request. The API's answer decides accepted / failed.
        try:
            response = self.api.set_desk_height(
                self.base_url, self.api_key, desk_id, target_mm
            )
            result.accepted_mm = _read_accepted_height(response)
            result.status = STATUS_ACCEPTED
        except DeskAPIError as error:
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
        if not isinstance(desk_id, str) or not desk_id.strip():
            raise WorkflowError("Desk ID cannot be empty")
        desk_id = desk_id.strip()
        if type(target_mm) is not int or target_mm <= 0:
            raise WorkflowError(
                "Target height must be a positive whole number of millimetres"
            )
        self._check_config()
        self._check_database()
        self._ensure_desk_is_stored(desk_id)
        return desk_id

    def _ensure_desk_is_stored(self, desk_id):
        """
        desk_commands points to desk(desk_id), so the desk must be stored first.
        If it is not (never synchronised), fetch it and store just the desk row.
        If that is impossible, stop BEFORE sending anything, so a request is only
        sent when the database is reachable and the desk can be referenced.
        """
        try:
            if self.commands.desk_exists(desk_id):
                return
            record = self.api.get_desk(self.base_url, self.api_key, desk_id)
            self.commands.save_desk_identity(record)
        except DeskAPIError as error:
            raise WorkflowError(
                f"Desk {desk_id} is not in the database yet and could not be "
                f"fetched from the API ({_text(error)})"
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
