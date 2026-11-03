import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .Data.desk_api_client import DeskAPIError, get_desk_ids, get_desk


app = FastAPI()

# Let the React development servers call this backend from another origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# A small endpoint the frontend can use to check whether the backend is running.
@app.get("/api/health")
def get_health():
    return {"status": "ok"}

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

    base_url = os.getenv("DESK_API_BASE_URL", "http://localhost:8000")
    api_key = os.getenv("DESK_API_KEY")

    if not api_key:
        raise HTTPException(status_code=503, detail="Simulator API key is not configured")
    try:
        desk_ids = get_desk_ids(base_url, api_key)

        desks = []
        for desk_id in desk_ids:
            desk_record = get_desk(base_url, api_key, desk_id)
            desks.append(format_desk(desk_record))

        return desks

    except DeskAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

@app.get("/api/desks/{desk_id}")
def get_desk_state(desk_id: str):
    """Return the current state of a specific desk"""

    base_url = os.getenv("DESK_API_BASE_URL", "http://localhost:8000")
    api_key = os.getenv("DESK_API_KEY")

    if not api_key:
        raise HTTPException(status_code=503, detail="Simulator API key is not configured")
    try:
        desk_record = get_desk(base_url, api_key, desk_id)
        return format_desk(desk_record)

    except DeskAPIError as error:
        if str(error).startswith("HTTP 404"):
            raise HTTPException(status_code=404, detail=f"Desk {desk_id} not found") from error
        raise HTTPException(status_code=502, detail=str(error)) from error
