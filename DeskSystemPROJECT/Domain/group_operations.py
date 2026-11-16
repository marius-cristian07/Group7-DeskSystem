# Group movements (S5-1): one shared process that warns, can be cancelled, then dispatches.
# A group operation is a list of desks and one target height. It moves through these states:
#
#   pending_warning -> countdown -> dispatching -> monitoring -> completed
#                                                              -> partial_failure / failed
#   pending_warning or countdown -> cancelled        (before anything was sent)
#   pending_warning or countdown -> blocked          (warning not confirmed, or stale)
#
# Nothing moves until every required warning channel (the Pico, the dashboard) has
# acknowledged that its warning has started and the countdown has run out. Each desk is
# then sent at most one command, through the same DeskWorkflow.request_height that the CLI
# and the single-desk endpoint use, so there is no second copy of the movement rules.
#
# Everything that changes an operation's state happens under one lock, so cancel and
# dispatch can never both succeed. Operations are kept in memory (their commands are
# recorded in desk_commands as usual), so this relies on the backend running as one process.

"""Warn, cancel, dispatch and monitor movements of several desks as one operation."""

import logging
import math
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..Data.database import DatabaseError
from ..Data.desk_api_client import DeskAPIError
from .desk_workflow import MoveResult, WorkflowError, validate_movement

logger = logging.getLogger(__name__)

# ---------- states of a whole operation ----------

PENDING_WARNING = "pending_warning"  # warning published; waiting for acknowledgements
COUNTDOWN = "countdown"              # all required channels acknowledged; counting down
DISPATCHING = "dispatching"          # point of no return: commands are being sent
MONITORING = "monitoring"            # commands sent; waiting for fresh readings
COMPLETED = "completed"              # every desk confirmed at the target by a fresh reading
PARTIAL_FAILURE = "partial_failure"  # some desks reached the target, others did not
FAILED = "failed"                    # commands were sent but no desk reached the target
CANCELLED = "cancelled"              # cancelled before dispatch; nothing was sent
BLOCKED = "blocked"                  # stopped before dispatch; nothing was sent

ACTIVE_STATES = (PENDING_WARNING, COUNTDOWN, DISPATCHING, MONITORING)
WARNING_STATES = (PENDING_WARNING, COUNTDOWN)  # the states in which cancelling still works

# ---------- result for one desk ----------

R_PENDING = "pending"          # not sent yet
R_MOVING = "moving"            # command accepted; waiting for a fresh reading at the target
R_REACHED = "reached"          # a fresh reading shows the desk at the target
R_NOT_REACHED = "not_reached"  # accepted, but not at the target when monitoring stopped
R_UNVERIFIED = "unverified"    # accepted, but no fresh reading could be taken at the end
R_DESK_ERROR = "desk_error"    # the desk reported an error while moving
R_REJECTED = "rejected"        # the simulator explicitly rejected the command
R_UNKNOWN = "unknown"          # outcome uncertain; the desk may have moved; never retried
R_NOT_SENT = "not_sent"        # nothing was sent to this desk
R_CANCELLED = "cancelled"      # the operation was cancelled before dispatch

# Channels are the places a warning is shown, for example the Pico and the dashboard.
_CHANNEL = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class GroupOperationError(Exception):
    """A request could not be accepted. `reason` says which HTTP status fits (see the API)."""

    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


class DeskBusyError(GroupOperationError):
    """A desk is already part of another active movement."""

    def __init__(self, detail):
        super().__init__(detail, "conflict")
        self.detail = detail


# ---------- settings ----------

def _positive_number(env, name, default):
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive number") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


@dataclass(frozen=True)
class GroupOperationSettings:
    """Timing and safety settings. Every value can be set with an environment variable."""

    # The proposal's 10-second countdown is a demo setting, not a fixed requirement.
    countdown_s: float = 10.0
    # How long to wait for the warning channels to acknowledge before giving up.
    ack_timeout_s: float = 15.0
    # A channel must have confirmed its warning this recently when the countdown ends.
    stale_s: float = 15.0
    # Channels that must acknowledge before the countdown starts.
    required_channels: Tuple[str, ...] = ("pico", "dashboard")
    # How long to wait for fresh readings to show the target after the commands were sent.
    monitor_timeout_s: float = 60.0
    monitor_poll_s: float = 1.0
    # How close to the target a stopped desk must be to count as having reached it.
    tolerance_mm: int = 2
    max_desks: int = 50
    max_parallel_sends: int = 8
    max_kept_operations: int = 100

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        defaults = cls()
        channels = defaults.required_channels
        raw = env.get("GROUP_WARNING_REQUIRED_CHANNELS")
        if raw is not None and raw.strip():
            channels = tuple(part.strip() for part in raw.split(","))
            if any(not _CHANNEL.fullmatch(name) for name in channels) or len(set(channels)) != len(channels):
                raise ValueError(
                    "GROUP_WARNING_REQUIRED_CHANNELS must be a comma-separated list of "
                    "different channel names, for example pico,dashboard"
                )
        return cls(
            countdown_s=_positive_number(env, "GROUP_WARNING_COUNTDOWN_SECONDS", defaults.countdown_s),
            ack_timeout_s=_positive_number(env, "GROUP_WARNING_ACK_TIMEOUT_SECONDS", defaults.ack_timeout_s),
            stale_s=_positive_number(env, "GROUP_WARNING_STALE_SECONDS", defaults.stale_s),
            required_channels=channels,
            monitor_timeout_s=_positive_number(env, "GROUP_MONITOR_TIMEOUT_SECONDS", defaults.monitor_timeout_s),
            monitor_poll_s=_positive_number(env, "GROUP_MONITOR_POLL_SECONDS", defaults.monitor_poll_s),
        )


# ---------- what callers see (copies, safe to read without the lock) ----------

@dataclass(frozen=True)
class DeskView:
    desk_id: str
    result: str
    detail: str
    move: Optional[MoveResult]          # the DeskWorkflow result, once a command was attempted
    last_position_mm: Optional[int]
    last_status: Optional[str]
    last_observed_at: Optional[datetime]


@dataclass(frozen=True)
class AckView:
    channel: str
    acknowledged_at: datetime
    last_confirmed_at: datetime


@dataclass(frozen=True)
class OperationView:
    operation_id: str
    state: str
    message: str
    desk_ids: Tuple[str, ...]
    target_position_mm: int
    created_at: datetime
    countdown_seconds: float
    acknowledgement_deadline: datetime
    warning_deadline: Optional[datetime]    # when the countdown ends; None until it starts
    seconds_remaining: Optional[float]      # only while counting down
    dispatched_at: Optional[datetime]
    finished_at: Optional[datetime]
    required_channels: Tuple[str, ...]
    acknowledgements: Tuple[AckView, ...]
    blocked_code: Optional[str]
    blocked_message: Optional[str]
    cancellable: bool
    desks: Tuple[DeskView, ...]


# ---------- internal, mutable records (only touched under the lock) ----------

@dataclass
class _Desk:
    desk_id: str
    result: str = R_PENDING
    detail: str = "Waiting for the warning to finish. Nothing has been sent."
    move: Optional[MoveResult] = None
    last_position_mm: Optional[int] = None
    last_status: Optional[str] = None
    last_observed: Optional[float] = None
    poll_failed: bool = False


@dataclass
class _Operation:
    operation_id: str
    desk_ids: Tuple[str, ...]
    target_mm: int
    required_channels: Tuple[str, ...]
    created: float                      # monotonic seconds; every deadline uses this clock
    wall_origin: float                  # wall-clock time at `created`, only for display
    ack_deadline: float
    state: str = PENDING_WARNING
    warning_deadline: Optional[float] = None
    dispatched: Optional[float] = None
    finished: Optional[float] = None
    monitor_deadline: Optional[float] = None
    acks: Dict[str, List[float]] = field(default_factory=dict)  # channel -> [first, last]
    desks: Dict[str, _Desk] = field(default_factory=dict)
    block_code: Optional[str] = None
    block_message: Optional[str] = None


@dataclass
class _Reservation:
    owner: str
    group: bool


def has_error(state):
    """The same rule the dashboard uses: a status other than Normal, or anti-collision.

    The simulator's lastErrors list is history, not a current fault, so it is not used."""
    return state.get("isAntiCollision") is True or str(state.get("status", "")).strip().lower() != "normal"


class GroupOperationService:
    def __init__(
        self,
        workflow_factory,
        settings=None,
        clock=time.monotonic,
        wall_clock=time.time,
        sleep=time.sleep,
        spawn=None,
    ):
        # workflow_factory returns a DeskWorkflow. Everything that talks to desks goes
        # through it, so the simulator client and the command history are shared.
        self._workflow_factory = workflow_factory
        self.settings = settings or GroupOperationSettings()
        # Time is injected so tests can run a 10-second countdown instantly.
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._spawn = spawn or self._spawn_thread
        self._lock = threading.RLock()
        self._operations: Dict[str, _Operation] = {}
        self._reserved: Dict[str, _Reservation] = {}
        self._stop = threading.Event()
        self._supervisor = None
        if self.settings.stale_s < self.settings.countdown_s:
            logger.warning(
                "GROUP_WARNING_STALE_SECONDS (%s) is shorter than the countdown (%s): warning "
                "channels must repeat their acknowledgement during the countdown",
                self.settings.stale_s, self.settings.countdown_s,
            )

    # ---------- lifecycle ----------

    @staticmethod
    def _spawn_thread(function, *args):
        threading.Thread(target=function, args=args, name="group_operation", daemon=True).start()

    def start(self):
        """Start the timer that moves operations from one state to the next."""
        if self._supervisor is not None:
            return
        self._stop.clear()
        self._supervisor = threading.Thread(target=self._supervise, name="group_supervisor", daemon=True)
        self._supervisor.start()

    def stop(self):
        self._stop.set()
        if self._supervisor is not None:
            self._supervisor.join(timeout=5)
            self._supervisor = None
        # Nothing may be dispatched after shutdown, so end any warning that is still running.
        with self._lock:
            for operation in self._operations.values():
                if operation.state in WARNING_STATES:
                    self._cancel_locked(operation, "The backend was shut down before dispatch.")

    def _supervise(self):
        while not self._stop.wait(0.2):
            try:
                self.tick()
            except Exception:
                logger.exception("group operation timer failed")

    def tick(self):
        """Apply any deadline that has passed. Called by the timer; tests call it directly."""
        with self._lock:
            now = self._clock()
            for operation in list(self._operations.values()):
                self._advance_locked(operation, now)

    # ---------- reservations: one active movement per desk ----------

    def _reserve(self, desk_ids, owner, group, suffix):
        with self._lock:
            busy = []
            for desk_id in desk_ids:
                held = self._reserved.get(desk_id)
                if held is None:
                    continue
                if held.group:
                    state = self._operations[held.owner].state if held.owner in self._operations else "being created"
                    busy.append(f"{desk_id} (group operation {held.owner}, {state})")
                else:
                    busy.append(f"{desk_id} (another movement request is in progress)")
            if busy:
                raise DeskBusyError(f"Desk(s) already in use: {'; '.join(busy)}. {suffix}")
            for desk_id in desk_ids:
                self._reserved[desk_id] = _Reservation(owner, group)

    def _release(self, desk_ids, owner):
        with self._lock:
            for desk_id in desk_ids:
                held = self._reserved.get(desk_id)
                if held is not None and held.owner == owner:
                    del self._reserved[desk_id]

    @contextmanager
    def reserve_single(self, desk_id):
        """Hold one desk while a single-desk request runs, so it cannot overlap a group movement."""
        owner = f"single-{uuid.uuid4().hex[:8]}"
        self._reserve((desk_id,), owner, False, "Nothing was sent.")
        try:
            yield
        finally:
            self._release((desk_id,), owner)

    # ---------- creating an operation ----------

    def _validate(self, desk_ids, target_mm):
        if not isinstance(desk_ids, (list, tuple)):
            raise GroupOperationError("desk_ids must be a list of desk IDs. Nothing was created.", "invalid_input")
        if len(desk_ids) == 0:
            raise GroupOperationError("Select at least one desk. Nothing was created.", "invalid_input")
        if len(desk_ids) > self.settings.max_desks:
            raise GroupOperationError(
                f"A group can contain at most {self.settings.max_desks} desks. Nothing was created.",
                "invalid_input",
            )
        for desk_id in desk_ids:
            try:
                # The same rules as a single-desk request: ID format and height range.
                validate_movement(desk_id, target_mm)
            except WorkflowError as error:
                raise GroupOperationError(f"{error} Nothing was created.", "invalid_input") from None
        duplicates = sorted({desk_id for desk_id in desk_ids if desk_ids.count(desk_id) > 1})
        if duplicates:
            raise GroupOperationError(
                f"Each desk can appear only once. Repeated: {', '.join(duplicates)}. Nothing was created.",
                "invalid_input",
            )
        return tuple(desk_ids)

    def _check_desk(self, workflow, desk_id):
        """Return None if the desk is available and reports no error now, else (code, text)."""
        try:
            record = workflow.api.get_desk(workflow.base_url, workflow.api_key, desk_id)
        except DeskAPIError as error:
            if error.status_code == 404:
                return "missing", "the desk is not available"
            return "unreachable", "the desk could not be checked with the simulator"
        if has_error(record["state"]):
            return "error", f"the desk reports an error (status: {record['state']['status']})"
        return None

    def create(self, desk_ids, target_mm):
        """Create a group operation and publish its warning. No desk is moved."""
        desk_ids = self._validate(desk_ids, target_mm)
        operation_id = uuid.uuid4().hex
        # Reserve first, so two requests for the same desk cannot both get past the checks.
        self._reserve(desk_ids, operation_id, True, "Nothing was created.")
        try:
            workflow = self._workflow_factory()
            try:
                workflow.api.validate_config(workflow.base_url, workflow.api_key)
            except DeskAPIError:
                raise GroupOperationError(
                    "The simulator address or API key is not configured. Nothing was created.", "unavailable",
                ) from None
            try:
                workflow.connect().close()
            except DatabaseError:
                raise GroupOperationError(
                    "The database is unavailable, so movements could not be recorded. Nothing was created.",
                    "unavailable",
                ) from None
            self._check_desks_now(workflow, desk_ids)
        except BaseException:
            self._release(desk_ids, operation_id)
            raise

        with self._lock:
            now = self._clock()
            operation = _Operation(
                operation_id=operation_id,
                desk_ids=desk_ids,
                target_mm=target_mm,
                required_channels=self.settings.required_channels,
                created=now,
                wall_origin=self._wall_clock(),
                ack_deadline=now + self.settings.ack_timeout_s,
                desks={desk_id: _Desk(desk_id) for desk_id in desk_ids},
            )
            self._operations[operation_id] = operation
            self._prune_locked()
            logger.info("group operation %s created for %d desk(s), target %d mm", operation_id, len(desk_ids), target_mm)
            return self._view_locked(operation, now)

    def _check_desks_now(self, workflow, desk_ids):
        """Refuse to publish a warning for desks that could not be moved anyway."""
        missing, faulty = [], []
        for desk_id in desk_ids:
            problem = self._check_desk(workflow, desk_id)
            if problem is None:
                continue
            if problem[0] == "unreachable":
                raise GroupOperationError(
                    "The simulator could not be reached to check the desks. Nothing was created.",
                    "simulator_unavailable",
                )
            (missing if problem[0] == "missing" else faulty).append(desk_id)
        if missing:
            raise GroupOperationError(
                f"Desk(s) not available: {', '.join(missing)}. Nothing was created.", "desk_not_found",
            )
        if faulty:
            raise GroupOperationError(
                f"Desk(s) currently report an error: {', '.join(faulty)}. Nothing was created.", "desks_not_ready",
            )

    def _prune_locked(self):
        finished = [op for op in self._operations.values() if op.state not in ACTIVE_STATES]
        extra = len(finished) - self.settings.max_kept_operations
        for operation in sorted(finished, key=lambda op: op.finished or 0)[:max(0, extra)]:
            del self._operations[operation.operation_id]

    # ---------- reading ----------

    def get(self, operation_id):
        with self._lock:
            return self._view_locked(self._find_locked(operation_id), self._clock())

    def active_warnings(self):
        """Operations whose warning is currently running, for the Pico and the dashboard."""
        with self._lock:
            now = self._clock()
            return [self._view_locked(op, now) for op in self._operations.values() if op.state in WARNING_STATES]

    def _find_locked(self, operation_id):
        operation = self._operations.get(operation_id)
        if operation is None:
            raise GroupOperationError("Group operation not found", "not_found")
        return operation

    # ---------- acknowledging the warning ----------

    def acknowledge(self, operation_id, channel):
        """A warning channel reports that its warning has started (or, again, is still running).

        The first acknowledgement from every required channel starts the countdown. Repeating
        it keeps the warning from going stale during a long countdown."""
        if not isinstance(channel, str) or not _CHANNEL.fullmatch(channel):
            raise GroupOperationError(
                "channel must be 1-32 lowercase letters, digits, hyphens or underscores, starting with a letter",
                "invalid_input",
            )
        with self._lock:
            operation = self._find_locked(operation_id)
            now = self._clock()
            self._advance_locked(operation, now)
            if operation.state not in WARNING_STATES:
                raise GroupOperationError(
                    f"The warning for this operation is no longer active (state: {operation.state}).", "not_active",
                )
            if channel in operation.acks:
                operation.acks[channel][1] = now
            else:
                operation.acks[channel] = [now, now]
            if operation.state == PENDING_WARNING and all(c in operation.acks for c in operation.required_channels):
                operation.state = COUNTDOWN
                operation.warning_deadline = now + self.settings.countdown_s
                logger.info("group operation %s: warning acknowledged, countdown started", operation_id)
            return self._view_locked(operation, now)

    # ---------- cancelling ----------

    def cancel(self, operation_id):
        """Cancel before dispatch. Once commands are being sent, this is no longer possible."""
        with self._lock:
            operation = self._find_locked(operation_id)
            # A deadline that has already passed is applied first. If that starts the
            # dispatch, this cancel is too late: exactly one of the two takes effect.
            self._advance_locked(operation, self._clock())
            if operation.state in WARNING_STATES:
                self._cancel_locked(operation, "Cancelled before dispatch.")
            elif operation.state == CANCELLED:
                pass  # cancelling twice is harmless
            elif operation.state in (DISPATCHING, MONITORING):
                raise GroupOperationError(
                    "Movement commands have already been sent, so cancelling is no longer possible. "
                    "Cancelling is not an emergency stop and does not stop desks that are already moving.",
                    "too_late",
                )
            else:
                raise GroupOperationError(f"The operation has already finished (state: {operation.state}).", "finished")
            return self._view_locked(operation, self._clock())

    def _cancel_locked(self, operation, why):
        for desk in operation.desks.values():
            if desk.result == R_PENDING:
                desk.result = R_CANCELLED
                desk.detail = "Cancelled before dispatch. No command was sent."
        self._finish_locked(operation, CANCELLED)
        logger.info("group operation %s cancelled: %s", operation.operation_id, why)

    # ---------- moving from one state to the next ----------

    def _advance_locked(self, operation, now):
        """Apply deadlines. Every transition happens here or in cancel/acknowledge, under the lock."""
        if operation.state == PENDING_WARNING and now >= operation.ack_deadline:
            missing = [c for c in operation.required_channels if c not in operation.acks]
            self._block_locked(
                operation, "warning_not_acknowledged",
                f"The warning was not acknowledged by: {', '.join(missing)}. No desk was moved.",
            )
        elif operation.state == COUNTDOWN and now >= operation.warning_deadline:
            stale = [c for c in operation.required_channels if now - operation.acks[c][1] > self.settings.stale_s]
            if stale:
                self._block_locked(
                    operation, "warning_stale",
                    f"The warning was not confirmed recently enough by: {', '.join(stale)}. No desk was moved.",
                )
            else:
                # The commitment point. From here, cancel() is refused.
                operation.state = DISPATCHING
                operation.dispatched = now
                logger.info("group operation %s: dispatching", operation.operation_id)
                self._spawn(self._run, operation.operation_id)

    def _block_locked(self, operation, code, message):
        for desk in operation.desks.values():
            if desk.result == R_PENDING:
                desk.result = R_NOT_SENT
                desk.detail = "Not sent: the warning could not be confirmed."
        operation.block_code, operation.block_message = code, message
        self._finish_locked(operation, BLOCKED)
        logger.warning("group operation %s blocked: %s", operation.operation_id, message)

    def _finish_locked(self, operation, state):
        operation.state = state
        operation.finished = self._clock()
        self._release(operation.desk_ids, operation.operation_id)

    def _finalize_locked(self, operation, block=None):
        """Choose the final state from the per-desk results."""
        results = [desk.result for desk in operation.desks.values()]
        if block is None and all(result == R_NOT_SENT for result in results):
            block = ("nothing_sent", "No movement command was sent to any desk.")
        if block is not None:
            operation.block_code, operation.block_message = block
            self._finish_locked(operation, BLOCKED)
        elif all(result == R_REACHED for result in results):
            self._finish_locked(operation, COMPLETED)
        elif any(result == R_REACHED for result in results):
            self._finish_locked(operation, PARTIAL_FAILURE)
        else:
            self._finish_locked(operation, FAILED)
        logger.info("group operation %s finished: %s", operation.operation_id, operation.state)

    # ---------- dispatch and monitoring (run on their own thread) ----------

    def _run(self, operation_id):
        with self._lock:
            operation = self._operations[operation_id]
        try:
            workflow = self._workflow_factory()
            if self._dispatch(operation, workflow):
                self._monitor(operation, workflow)
        except Exception:
            logger.exception("group operation %s failed unexpectedly", operation_id)
            with self._lock:
                for desk in operation.desks.values():
                    if desk.result == R_PENDING:
                        desk.result, desk.detail = R_NOT_SENT, "Not sent: an unexpected error stopped the operation."
                    elif desk.result == R_MOVING:
                        desk.result = R_UNVERIFIED
                        desk.detail = "The command was accepted, but monitoring failed unexpectedly. The final position is unknown."
        finally:
            with self._lock:
                # Whatever happened, the desks must not stay reserved.
                if operation.state in ACTIVE_STATES:
                    self._finalize_locked(operation)

    def _dispatch(self, operation, workflow):
        """Recheck every desk, then send each ready desk one command. Returns True if any was sent."""
        ready, skipped = [], {}
        for desk_id in operation.desk_ids:
            problem = self._check_desk(workflow, desk_id)
            if problem is None:
                ready.append(desk_id)
            else:
                skipped[desk_id] = problem[1]
        with self._lock:
            for desk_id, why in skipped.items():
                desk = operation.desks[desk_id]
                desk.result, desk.detail = R_NOT_SENT, f"Not sent: {why}."
            if not ready:
                self._finalize_locked(operation, block=(
                    "no_desks_ready", "No desk passed the final availability and error check. Nothing was sent.",
                ))
                return False

        # One command per desk, sent together so the group starts moving at about the same time.
        workers = max(1, min(len(ready), self.settings.max_parallel_sends))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._send_one, workflow, desk_id, operation.target_mm): desk_id for desk_id in ready}
            for future in as_completed(futures):
                with self._lock:
                    self._record_send(operation.desks[futures[future]], *future.result())

        with self._lock:
            if all(desk.result == R_NOT_SENT for desk in operation.desks.values()):
                self._finalize_locked(operation)
                return False
            if not any(desk.result == R_MOVING for desk in operation.desks.values()):
                self._finalize_locked(operation)  # everything was rejected or uncertain
                return False
            operation.state = MONITORING
            operation.monitor_deadline = self._clock() + self.settings.monitor_timeout_s
            return True

    @staticmethod
    def _send_one(workflow, desk_id, target_mm):
        """Send one command through the shared workflow. Never raises, never retries."""
        try:
            return workflow.request_height(desk_id, target_mm), None
        except WorkflowError as error:
            return None, error.reason  # raised only when nothing was sent
        except Exception:
            logger.exception("sending to desk %s failed unexpectedly", desk_id)
            return None, "unexpected"  # the command may or may not have been sent

    @staticmethod
    def _record_send(desk, move, not_sent_reason):
        if move is None:
            if not_sent_reason == "unexpected":
                desk.result = R_UNKNOWN
                desk.detail = ("An unexpected error happened while sending. The desk may have moved. "
                               "The command was not retried.")
                return
            reasons = {
                "invalid_input": "the desk ID or height was rejected",
                "desk_not_found": "the desk is not available",
                "simulator_unavailable": "the desk could not be verified with the simulator",
            }
            desk.result = R_NOT_SENT
            desk.detail = f"Not sent: {reasons.get(not_sent_reason, 'the movement configuration or database is unavailable')}."
            return
        desk.move = move
        if move.status == "accepted":
            desk.result = R_MOVING
            desk.detail = "Command accepted. Waiting for a fresh reading to confirm the target was reached."
        elif move.status == "failed":
            desk.result = R_REJECTED
            desk.detail = "The simulator rejected the movement request."
        else:
            desk.result = R_UNKNOWN
            desk.detail = ("Acceptance could not be confirmed. The desk may have moved. "
                           "The command was not retried; check the desk before trying again.")
        if move.record_error:
            desk.detail += " The request could not be recorded in the command history."

    def _monitor(self, operation, workflow):
        """Poll fresh readings until each accepted desk is at its target, or time runs out."""
        latest = {}  # last good record per desk, saved as a final reading
        while True:
            with self._lock:
                waiting = [desk for desk in operation.desks.values() if desk.result == R_MOVING]
                deadline = operation.monitor_deadline
            if not waiting:
                break
            for desk in waiting:
                self._poll(operation, workflow, desk, latest)
            with self._lock:
                if not any(desk.result == R_MOVING for desk in operation.desks.values()):
                    break
                remaining = deadline - self._clock()
                if remaining <= 0:
                    self._time_out_locked(operation)
                    break
            self._sleep(min(self.settings.monitor_poll_s, remaining))

        for desk_id, record in latest.items():
            try:
                workflow.readings.save_desk(record)  # so the history chart ends at the real position
            except DatabaseError:
                logger.warning("could not save the final reading of desk %s", desk_id)
        with self._lock:
            self._finalize_locked(operation)

    def _poll(self, operation, workflow, desk, latest):
        try:
            record = workflow.api.get_desk(workflow.base_url, workflow.api_key, desk.desk_id)
        except DeskAPIError:
            with self._lock:
                desk.poll_failed = True
            return
        state = record["state"]
        accepted = desk.move.accepted_mm if desk.move.accepted_mm is not None else operation.target_mm
        reached = abs(state["position_mm"] - accepted) <= self.settings.tolerance_mm and state["speed_mms"] == 0
        with self._lock:
            desk.poll_failed = False
            desk.last_position_mm = state["position_mm"]
            desk.last_status = state["status"]
            desk.last_observed = self._clock()
            if reached:
                desk.result = R_REACHED
                desk.detail = f"A fresh reading confirms the desk is at {state['position_mm']} mm."
                latest[desk.desk_id] = record
            elif has_error(state):
                desk.result = R_DESK_ERROR
                desk.detail = (f"The desk reported an error while moving (status: {state['status']}) "
                               f"and did not reach the target. Last reading: {state['position_mm']} mm.")
                latest[desk.desk_id] = record

    def _time_out_locked(self, operation):
        for desk in operation.desks.values():
            if desk.result != R_MOVING:
                continue
            if desk.poll_failed or desk.last_observed is None:
                desk.result = R_UNVERIFIED
                desk.detail = ("The command was accepted, but no fresh reading could be taken when monitoring "
                               "stopped. The final position is unknown.")
            else:
                desk.result = R_NOT_REACHED
                desk.detail = (f"The desk had not reached the target when monitoring stopped "
                               f"(last reading: {desk.last_position_mm} mm). It may still be moving.")

    # ---------- turning internal records into views ----------

    def _wall(self, operation, moment):
        return datetime.fromtimestamp(operation.wall_origin + (moment - operation.created), tz=timezone.utc)

    def _message(self, operation):
        state = operation.state
        if state == PENDING_WARNING:
            waiting = [c for c in operation.required_channels if c not in operation.acks]
            return (f"Warning published. Waiting for acknowledgement from: {', '.join(waiting)}. "
                    "No desk will move until the countdown has finished.")
        if state == COUNTDOWN:
            return "Warning acknowledged. The desks will move when the countdown ends unless this is cancelled."
        if state == DISPATCHING:
            return "Sending movement commands. Cancelling is no longer possible."
        if state == MONITORING:
            return "Commands sent. Waiting for fresh readings to confirm that each desk reached the target."
        if state == COMPLETED:
            return "Every desk was confirmed at the target by a fresh reading."
        if state == PARTIAL_FAILURE:
            return ("Some desks did not reach the target. See each desk's result. "
                    "Uncertain commands were not retried.")
        if state == FAILED:
            return "No desk reached the target. See each desk's result. Uncertain commands were not retried."
        if state == CANCELLED:
            return "Cancelled before dispatch. No movement command was sent."
        return operation.block_message or "Stopped before dispatch. No movement command was sent."

    def _view_locked(self, operation, now):
        remaining = None
        if operation.state == COUNTDOWN:
            remaining = max(0.0, operation.warning_deadline - now)
        wall = lambda moment: None if moment is None else self._wall(operation, moment)  # noqa: E731
        return OperationView(
            operation_id=operation.operation_id,
            state=operation.state,
            message=self._message(operation),
            desk_ids=operation.desk_ids,
            target_position_mm=operation.target_mm,
            created_at=wall(operation.created),
            countdown_seconds=self.settings.countdown_s,
            acknowledgement_deadline=wall(operation.ack_deadline),
            warning_deadline=wall(operation.warning_deadline),
            seconds_remaining=remaining,
            dispatched_at=wall(operation.dispatched),
            finished_at=wall(operation.finished),
            required_channels=operation.required_channels,
            acknowledgements=tuple(
                AckView(channel, wall(times[0]), wall(times[1])) for channel, times in operation.acks.items()
            ),
            blocked_code=operation.block_code,
            blocked_message=operation.block_message,
            cancellable=operation.state in WARNING_STATES,
            desks=tuple(
                DeskView(
                    desk.desk_id, desk.result, desk.detail, desk.move,
                    desk.last_position_mm, desk.last_status, wall(desk.last_observed),
                )
                for desk in operation.desks.values()
            ),
        )
