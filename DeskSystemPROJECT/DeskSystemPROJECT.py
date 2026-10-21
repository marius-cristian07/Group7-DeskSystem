
"""
Created by : Edris Fiazi
Created on : 21.10.2026
Purpose    : KAN-5 Retrieve and display current desk data from the WiFi2BLE simulator
"""

import os
import sys

from Data.desk_api_client import DeskAPIError, get_desk, get_desk_ids


def main():
    """Display current data for every available simulated desk."""
    base_url = os.environ.get("DESK_API_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("DESK_API_KEY")
    if not api_key:
        print("Set DESK_API_KEY before starting the application.", file=sys.stderr)
        return 1
    try:
        desk_ids = get_desk_ids(base_url, api_key)
    except DeskAPIError as error:
        print(f"Cannot retrieve desk list: {error}", file=sys.stderr)
        return 1

    print(f"Found {len(desk_ids)} available desk(s).")
    failed = False
    for desk_id in desk_ids:
        try:
            desk = get_desk(base_url, api_key, desk_id)
        except DeskAPIError as error:
            print(f"Cannot retrieve desk {desk_id}: {error}", file=sys.stderr)
            failed = True
            continue
        print(
            f"{desk['config']['name']} | ID: {desk_id} | "
            f"Height: {desk['state']['position_mm']} mm | "
            f"Status: {desk['state']['status']}"
        )
        print(f"  Manufacturer: {desk['config']['manufacturer']}")
        print(f"  State: {desk['state']}")
        print(f"  Usage: {desk['usage']}")
        print(f"  Last errors: {desk['lastErrors']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
