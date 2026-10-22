"""
Created by : Edris Fiazi
Created on : 21.10.2026
Purpose    : KAN-5 Retrieve and display current desk data from the WiFi2BLE simulator
"""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import urlopen


class DeskAPIError(Exception):
    """A request or desk data validation failed."""



def validate_config(base_url, api_key):
    """Check the API URL and API key before sending a request."""

    if not isinstance(base_url, str) or not base_url.strip():
        raise DeskAPIError("Base URL cannot be empty")

    try:
        parsed_url = urlsplit(base_url)
    except ValueError:
        raise DeskAPIError("Invalid base URL") from None

    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise DeskAPIError("Base URL must be a valid HTTP or HTTPS address")

    if not isinstance(api_key, str) or not api_key.strip():
        raise DeskAPIError("API key cannot be empty")



def get_json(url, timeout=5):
    """Retrieve JSON through HTTP without exposing the API key in errors."""
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        descriptions = {
            400: "Invalid API request",
            401: "Authentication failed",
            404: "Desk not found or currently unavailable",
        }
        raise DeskAPIError(
            f"HTTP {error.code}: {descriptions.get(error.code, 'API request failed')}"
        ) from None
    except (URLError, TimeoutError, OSError):
        raise DeskAPIError("Connection failed or request timed out") from None
    except (ValueError, UnicodeError):
        raise DeskAPIError("API returned invalid JSON") from None


def get_desk_ids(base_url, api_key, timeout=5):
    """Retrieve and validate the available desk IDs."""
    validate_config(base_url, api_key)
    url = f"{base_url.rstrip('/')}/api/v2/{quote(api_key, safe='')}/desks"
    desk_ids = get_json(url, timeout)
    if type(desk_ids) is not list or any(type(item) is not str for item in desk_ids):
        raise DeskAPIError("Desk list must be an array of string IDs")
    return desk_ids


def require_field(data, field, expected_type, path, non_negative=False):
    """Reject missing, mistyped or negative contract fields."""
    value = data.get(field)
    if type(value) is not expected_type:
        raise DeskAPIError(f"{path}.{field}: expected {expected_type.__name__}")
    if non_negative and value < 0:
        raise DeskAPIError(f"{path}.{field}: expected a non-negative integer")
    return value


def validate_desk(data, desk_id):
    """Validate the documented desk contract and add the requested ID."""
    path = f"Desk {desk_id}"
    if type(data) is not dict:
        raise DeskAPIError(f"{path}: expected an object")
    config = require_field(data, "config", dict, path)
    state = require_field(data, "state", dict, path)
    usage = require_field(data, "usage", dict, path)
    errors = require_field(data, "lastErrors", list, path)
    for field in ("name", "manufacturer"):
        require_field(config, field, str, f"{path}.config")
    for field in ("position_mm", "speed_mms"):
        require_field(state, field, int, f"{path}.state")
    require_field(state, "status", str, f"{path}.state")
    for field in (
        "isPositionLost", "isOverloadProtectionUp",
        "isOverloadProtectionDown", "isAntiCollision",
    ):
        require_field(state, field, bool, f"{path}.state")
    for field in ("activationsCounter", "sitStandCounter"):
        require_field(usage, field, int, f"{path}.usage", non_negative=True)
    for index, error in enumerate(errors):
        error_path = f"{path}.lastErrors[{index}]"
        if type(error) is not dict:
            raise DeskAPIError(f"{error_path}: expected an object")
        for field in ("time_s", "errorCode"):
            require_field(error, field, int, error_path, non_negative=True)
    return {
        "desk_id": desk_id, "config": config, "state": state,
        "usage": usage, "lastErrors": errors,
    }


def get_desk(base_url, api_key, desk_id, timeout=5):
    """Retrieve one current desk record through the simulator API."""

    validate_config(base_url, api_key)

    if not isinstance(desk_id, str) or not desk_id.strip():
        raise DeskAPIError("Desk ID cannot be empty")

    url = (
        f"{base_url.rstrip('/')}/api/v2/{quote(api_key, safe='')}/desks/"
        f"{quote(desk_id, safe=':')}"
    )
    return validate_desk(get_json(url, timeout), desk_id)
