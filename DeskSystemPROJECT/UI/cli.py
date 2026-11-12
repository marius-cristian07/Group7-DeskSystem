# Terminal interface for show, sync, and move, called by DeskSystemPROJECT.py.
# Parse arguments, call DeskWorkflow, then print results and return an exit code.
# A zero exit code means success; one reports a failure, including partial failures.

"""
    python DeskSystemPROJECT.py                  show the help, does nothing else
    python DeskSystemPROJECT.py show             print current desk data (read-only)
    python DeskSystemPROJECT.py sync             fetch all desks and save readings
    python DeskSystemPROJECT.py move DESK_ID MM  request a height for one desk
"""

import argparse
import sys

from ..config import DEFAULT_BASE_URL, get_simulator_config
from ..Domain.desk_workflow import STATUS_ACCEPTED, STATUS_UNKNOWN, DeskWorkflow, WorkflowError

# The simulator moves desks once per second, so a reading taken at the same
# instant as the request would still show the desk standing still.
DEFAULT_WAIT_S = 2

EPILOG = f"""\
environment variables:
  DESK_API_KEY        API key of the simulator (required)
  DESK_API_BASE_URL   simulator address (default: {DEFAULT_BASE_URL})
  DATABASE_URL        PostgreSQL connection URL (required by sync and move)

examples:
  python DeskSystemPROJECT.py sync
  python DeskSystemPROJECT.py move cd:fb:1a:53:fb:e6 1000
"""


def positive_height(text):
    """argparse type for the target height in millimetres."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{text}' is not a whole number of millimetres"
        ) from None
    if value <= 0:
        raise argparse.ArgumentTypeError("the height must be greater than 0 mm")
    return value


def non_negative_seconds(text):
    """argparse type for the optional wait before the follow-up reading."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a number of seconds") from None
    if value < 0:
        raise argparse.ArgumentTypeError("the wait cannot be negative")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="DeskSystemPROJECT.py",
        description="Desk system: synchronise desk data and request desk heights.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Subcommands select the workflow; move also needs a desk ID and target height.
    commands = parser.add_subparsers(dest="command", metavar="command")

    commands.add_parser(
        "show",
        help="print the current data of every desk (read-only, nothing is saved)",
    )
    commands.add_parser(
        "sync",
        help="fetch all available desks and save a new reading for each",
    )
    move = commands.add_parser(
        "move",
        help="request a height for ONE desk (this moves the desk)",
        description=(
            "Request a target height for one desk. The request is saved in "
            "desk_commands as accepted, failed, or unknown. Heights must be "
            "680–1320 mm. If it was accepted, the desk "
            "is read again and a new reading is saved."
        ),
    )
    move.add_argument("desk_id", metavar="DESK_ID", help="ID of the desk, e.g. cd:fb:1a:53:fb:e6")
    move.add_argument(
        "height_mm",
        metavar="HEIGHT_MM",
        type=positive_height,
        help="target height in millimetres",
    )
    move.add_argument(
        "--wait",
        metavar="SECONDS",
        type=non_negative_seconds,
        default=DEFAULT_WAIT_S,
        help="seconds to wait before the follow-up reading, so the desk has "
        f"started moving; 0 reads straight away (default: {DEFAULT_WAIT_S})",
    )
    return parser


def _error(message):
    print(message, file=sys.stderr)


# These handlers format workflow results and return the terminal exit code.
def run_show(workflow):
    fetched = workflow.fetch_all()
    print(f"Found {len(fetched)} available desk(s).")
    failed = False
    for item in fetched:
        if item.error:
            _error(f"Cannot retrieve desk {item.desk_id}: {item.error}")
            failed = True
            continue
        desk = item.record
        print(
            f"{desk['config']['name']} | ID: {item.desk_id} | "
            f"Height: {desk['state']['position_mm']} mm | "
            f"Status: {desk['state']['status']}"
        )
        print(f"  Manufacturer: {desk['config']['manufacturer']}")
        print(f"  State: {desk['state']}")
        print(f"  Usage: {desk['usage']}")
        print(f"  Last errors: {desk['lastErrors']}")
    return 1 if failed else 0


def run_sync(workflow, base_url):
    print(f"Synchronising desks from {base_url} ...")
    report = workflow.sync_all()
    if not report.items:
        print("The API returned no desks, so nothing was saved.")
        return 0
    print(f"Found {len(report.items)} available desk(s).")
    for item in report.items:
        if item.reading:
            r = item.reading
            print(
                f"  [saved]  {r.name} | {r.desk_id} | {r.position_mm} mm | "
                f"{r.status} | reading #{r.reading_id}"
            )
        else:
            _error(f"  [FAILED] {item.desk_id} | {item.error}")
    print(f"Sync finished: {report.saved} saved, {report.failed} failed.")
    return 0 if report.failed == 0 else 1


def run_move(workflow, desk_id, height_mm, wait_s):
    print(f"Requesting {height_mm} mm for desk {desk_id} ...")
    result = workflow.request_height(desk_id, height_mm, wait_s=wait_s)

    if result.status == STATUS_ACCEPTED:
        print(f"Request ACCEPTED: desk {result.desk_id} was asked to move to {result.requested_mm} mm.")
        if result.accepted_mm != result.requested_mm:
            print(
                f"  The desk adjusted the target to {result.accepted_mm} mm "
                f"(requested {result.requested_mm} mm)."
            )
    elif result.status == STATUS_UNKNOWN:
        _error(f"Request UNKNOWN for desk {result.desk_id}: {result.error}")
        _error("  The desk may have moved. Check its state before issuing another command.")
    else:
        _error(f"Request FAILED for desk {result.desk_id}: {result.error}")

    # Report storage failures separately: the desk may already have accepted the move.
    if result.command_id is not None:
        print(f"  Recorded in desk_commands as command #{result.command_id} ({result.status}).")
    else:
        _error(f"  WARNING: the request could not be recorded in desk_commands: {result.record_error}")

    if result.status == STATUS_ACCEPTED:
        if result.reading:
            r = result.reading
            print(
                f"  New reading #{r.reading_id} saved: {r.name} | {r.position_mm} mm | "
                f"speed {r.speed_mms} mm/s | {r.status}"
            )
            print("  (The desk moves gradually, so the reading can still show it on its way.)")
        else:
            _error(f"  WARNING: the follow-up reading was not saved: {result.reading_error}")

    return 0 if result.succeeded else 1


def main(argv=None, env=None, workflow_factory=DeskWorkflow):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Starting the application without a command only explains the commands.
    if args.command is None:
        parser.print_help()
        return 0

    base_url, api_key = get_simulator_config(env)
    if not api_key:
        _error("Set DESK_API_KEY before starting the application.")
        return 1

    workflow = workflow_factory(base_url, api_key)
    try:
        if args.command == "show":
            return run_show(workflow)
        if args.command == "sync":
            return run_sync(workflow, base_url)
        return run_move(workflow, args.desk_id, args.height_mm, args.wait)
    except WorkflowError as error:
        _error(f"Error: {error}")
        return 1
