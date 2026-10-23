import sys
from pathlib import Path
import unittest

# tells Python where to find the data folder
sys.path.append(str(Path(__file__).resolve().parent.parent))

from Data.desk_api_client import (
    DeskAPIError,
    validate_config,
    validate_desk,
    get_desk,
)


class DeskTests(unittest.TestCase):

    # check that an empty URL causes an error
    def test_empty_url_is_rejected(self):
        with self.assertRaises(DeskAPIError):
            validate_config("", "my-secret-key")

    # check that good desk data is accepted
    def test_valid_desk_data_works(self):
        sample_desk = {
            "config": {"name": "Office Desk", "manufacturer": "Linak"},
            "state": {
                "position_mm": 720,
                "speed_mms": 0,
                "status": "Normal",
                "isPositionLost": False,
                "isOverloadProtectionUp": False,
                "isOverloadProtectionDown": False,
                "isAntiCollision": False,
            },
            "usage": {"activationsCounter": 10, "sitStandCounter": 3},
            "lastErrors": [],
        }
        result = validate_desk(sample_desk, "desk-1")
        self.assertEqual(result["desk_id"], "desk-1")
        self.assertEqual(result["state"]["position_mm"], 720)

    # check that missing data causes an error
    def test_missing_state_is_rejected(self):
        broken_desk = {
            "config": {"name": "Broken Desk", "manufacturer": "Linak"},
            # missing "state", "usage", etc.
        }
        with self.assertRaises(DeskAPIError):
            validate_desk(broken_desk, "desk-1")

    # check that a dead server connection is caught cleanly
    def test_offline_server_is_caught(self):
        # Port 9999 is closed, so the connection fails immediately
        with self.assertRaises(DeskAPIError):
            get_desk("http://127.0.0.1:9999", "test-key", "desk-1")


if __name__ == "__main__":
    unittest.main()