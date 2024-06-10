import json
from unittest.mock import MagicMock, patch

import pytest

from ledona import slack


@pytest.fixture(scope="function", autouse=True)
def enable_slack():
    """make sure slack is enabled prior to every test"""
    slack.enable()


@pytest.fixture(name="mock_requests")
def _mock_requests():
    with patch("ledona.slack.requests") as mock_requests_cls:
        mock_requests_cls.post.return_value.status_code = 200
        yield mock_requests_cls


SLACK_URL = "slack.com"


@pytest.mark.parametrize(
    "text,attachments,ref_data",
    [
        ("tex", None, {"text": "tex"}),
        ("tex", [{"a": 1, "b": 2}], {"attachments": [{"a": 1, "b": 2}], "text": "tex"}),
    ],
)
def test_webhook(mock_requests, text, attachments, ref_data):
    slack.webhook(SLACK_URL, text=text, attachments=attachments)

    mock_requests.post.assert_called_once()
    assert SLACK_URL == mock_requests.post.call_args[0][0]
    test_data = json.loads(mock_requests.post.call_args[1]["data"])
    assert ref_data == test_data


def test_disable(mock_requests: MagicMock):
    assert slack.is_enabled()
    slack.disable()
    assert not slack.is_enabled()
    slack.webhook(SLACK_URL, text="disable test")
    slack.enable()
    assert slack.is_enabled()
    mock_requests.post.assert_not_called()
