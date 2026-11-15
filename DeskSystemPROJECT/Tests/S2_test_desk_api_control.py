"""Unit tests for the HTTP height-request function (network is mocked)."""
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from Data import desk_api_client
from Data.desk_api_client import DeskAPIError


def test_set_desk_height_sends_put_with_expected_url_and_json():
    expected_response = {"position_mm": 1000}
    with patch.object(desk_api_client, "put_json", return_value=expected_response) as put:
        result = desk_api_client.set_desk_height(
            "http://localhost:8000/", "secret-key", "desk:01", 1000
        )

    assert result == expected_response
    put.assert_called_once_with(
        "http://localhost:8000/api/v2/secret-key/desks/desk:01/state",
        {"position_mm": 1000},
        5,
    )


def test_set_desk_height_rejects_empty_desk_id():
    with pytest.raises(DeskAPIError, match="Desk ID cannot be empty"):
        desk_api_client.set_desk_height(
            "http://localhost:8000", "secret-key", "   ", 1000
        )


def test_set_desk_height_reports_http_failure_without_api_key():
    http_error = HTTPError(
        "http://localhost:8000/api/v2/very-secret-key/desks/desk:01/state",
        401, "Unauthorized", {}, None,
    )
    with patch.object(desk_api_client, "urlopen", side_effect=http_error):
        with pytest.raises(DeskAPIError) as error:
            desk_api_client.set_desk_height(
                "http://localhost:8000", "very-secret-key", "desk:01", 1000
            )

    assert "very-secret-key" not in str(error.value)


@pytest.mark.parametrize("height", ["1000", 1000.5, 0, -1, True, None])
def test_set_desk_height_rejects_invalid_height(height):
    with pytest.raises(DeskAPIError, match="positive whole number"):
        desk_api_client.set_desk_height(
            "http://localhost:8000", "secret-key", "desk:01", height
        )