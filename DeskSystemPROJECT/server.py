# the backend serves live desk data and saves history in the background
# desk routes read live data and never write to the database

import logging
import math
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .Data.desk_api_client import DeskAPIError, get_desk, get_desk_ids
from .config import FRONTEND_PORT, get_simulator_config
from .Domain.desk_workflow import DeskWorkflow, WorkflowError


logger = logging.getLogger(__name__)
DEFAULT_HISTORY_INTERVAL = 60


def _collect_history(stop_event, interval):
    # save readings without waiting for someone to open the dashboard
    base_url, api_key = get_simulator_config()
    workflow = DeskWorkflow(base_url, api_key)

    while not stop_event.is_set():
        try:
            report = workflow.sync_all()
            for item in report.items:
                if item.error:
                    logger.warning("desk %s history failed: %s", item.desk_id, item.error)
            logger.info("desk history saved %s readings; %s failed", report.saved, report.failed)
        except WorkflowError as error:
            logger.warning("desk history collection failed: %s", error)
        except Exception:
            logger.exception("desk history collection failed unexpectedly")
        stop_event.wait(interval)


@asynccontextmanager
async def lifespan(_app):
    # keep the collector tied to the backend lifetime
    stop_event = threading.Event()
    collector = None
    if os.environ.get("DATABASE_URL", "").strip():
        try:
            interval = float(os.environ.get(
                "DESK_HISTORY_INTERVAL_SECONDS", str(DEFAULT_HISTORY_INTERVAL)
            ))
        except ValueError:
            raise ValueError("DESK_HISTORY_INTERVAL_SECONDS must be a positive number") from None
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("DESK_HISTORY_INTERVAL_SECONDS must be a positive number")
        collector = threading.Thread(
            target=_collect_history,
            args=(stop_event, interval),
            name="desk_history_collector",
            daemon=True,
        )
        collector.start()
    else:
        logger.info("desk history collection is off because DATABASE_URL is not set")

    try:
        yield
    finally:
        if collector is not None:
            stop_event.set()
            collector.join(timeout=5)


app = FastAPI(lifespan=lifespan)

# Let the React development servers call this backend from another origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        f"http://localhost:{FRONTEND_PORT}",
        f"http://127.0.0.1:{FRONTEND_PORT}",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# This only confirms the HTTP server is up; it does not contact the simulator or DB.
@app.get("/api/health")
def get_health():
    return {"status": "ok"}


def get_api_config():
    base_url, api_key = get_simulator_config()
    if not api_key:
        raise HTTPException(status_code=503, detail="Simulator API key is not configured")
    return base_url, api_key


# Flatten config/state into the fields React expects; see docs/backend-api-contract.md.
def format_desk(desk_record):
    """Convert simulator data to the backend API format"""

    config = desk_record["config"]
    state = desk_record["state"]

    return {
        "desk_id": desk_record["desk_id"],
        "name": config["name"],
        "position_mm": state["position_mm"],
        "speed_mms": state["speed_mms"],
        "status": state["status"],
        "is_anti_collision": state["isAntiCollision"],
        "last_errors": desk_record["lastErrors"],
    }


@app.get("/api/desks")
def list_desks():
    """Return the current state of all available desks"""

    base_url, api_key = get_api_config()
    try:
        # The simulator lists IDs first; fetch each desk to build the frontend list.
        desk_ids = get_desk_ids(base_url, api_key)

        desks = []
        for desk_id in desk_ids:
            desk_record = get_desk(base_url, api_key, desk_id)
            desks.append(format_desk(desk_record))

        return desks

    except DeskAPIError as error:
        # Fail the whole list if any read fails, rather than return an incomplete success.
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/desks/{desk_id}")
def get_desk_state(desk_id: str):
    """Return the current state of a specific desk"""

    base_url, api_key = get_api_config()
    try:
        desk_record = get_desk(base_url, api_key, desk_id)
        return format_desk(desk_record)

    except DeskAPIError as error:
        # A missing desk is different from an unavailable simulator.
        if error.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Desk {desk_id} not found") from error
        raise HTTPException(status_code=502, detail=str(error)) from error
