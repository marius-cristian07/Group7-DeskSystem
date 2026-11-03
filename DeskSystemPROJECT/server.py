# HTTP entry point used by React. Uvicorn serves the FastAPI app defined here.
# Desk routes read live simulator data through Data/desk_api_client.py and return
# the smaller frontend response. They do not read or save PostgreSQL history.

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .Data.desk_api_client import DeskAPIError, get_desk_ids, get_desk
from .config import FRONTEND_PORT, get_simulator_config


app = FastAPI()

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
