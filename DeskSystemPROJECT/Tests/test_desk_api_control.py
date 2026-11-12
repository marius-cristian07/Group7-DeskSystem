# Checks outgoing simulator requests and how HTTP/network errors are reported.
# Fake response streams let tests inspect URLs and payloads without moving a desk.

import io
import json
import unittest
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from DeskSystemPROJECT.Data import desk_api_client as api


class RequestTests(unittest.TestCase):
    def test_truncated_acknowledgement_is_a_transport_error_without_retry(self):
        with patch.object(api, "urlopen", side_effect=IncompleteRead(b"partial")) as open_url:
            with self.assertRaises(api.DeskAPIError) as caught:
                api.set_desk_height("http://example.test", "key", "desk-1", 1000)
        self.assertIsNone(caught.exception.status_code)
        open_url.assert_called_once()

    def test_move_keeps_put_url_and_payload(self):
        # BytesIO stands in for the response body, so no real desk is moved.
        with patch.object(api, "urlopen", return_value=io.BytesIO(b'{"position_mm": 1320}')) as open_url:
            result = api.set_desk_height("http://127.0.0.1:8000/", "test/key", "aa:bb", 2000)
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/v2/test%2Fkey/desks/aa:bb/state")
        self.assertEqual(json.loads(request.data), {"position_mm": 2000})
        self.assertEqual(result, {"position_mm": 1320})

    def test_get_and_put_errors_keep_messages_and_hide_key(self):
        url = "http://127.0.0.1:8000/api/v2/private-key/desks"
        for method, expected in ((api.get_json, "Desk not found or currently unavailable"),
                                 (lambda url: api.put_json(url, {}), "API request failed")):
            with self.subTest(method=method):
                with patch.object(api, "urlopen", side_effect=HTTPError(url, 404, url, {}, None)):
                    with self.assertRaises(api.DeskAPIError) as caught:
                        method(url)
                self.assertEqual(str(caught.exception), f"HTTP 404: {expected}")
                self.assertEqual(caught.exception.status_code, 404)
                self.assertNotIn("private-key", str(caught.exception))

    def test_invalid_json_and_network_failures_have_safe_messages(self):
        with patch.object(api, "urlopen", return_value=io.BytesIO(b"not json")):
            with self.assertRaisesRegex(api.DeskAPIError, "invalid JSON"):
                api.get_json("http://example.test")
        with patch.object(api, "urlopen", side_effect=URLError("secret URL")):
            with self.assertRaisesRegex(api.DeskAPIError, "^Connection failed or request timed out$"):
                api.put_json("http://example.test", {})

    def test_bad_ids_are_rejected_before_network_access(self):
        with patch.object(api, "urlopen") as open_url:
            for desk_id in (None, "", "  ", 123):
                with self.subTest(desk_id=desk_id):
                    with self.assertRaises(api.DeskAPIError):
                        api.get_desk("http://127.0.0.1:8000", "key", desk_id)
                    with self.assertRaises(api.DeskAPIError):
                        api.set_desk_height("http://127.0.0.1:8000", "key", desk_id, 900)
            open_url.assert_not_called()
