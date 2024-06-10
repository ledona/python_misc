import json
from unittest.mock import MagicMock, patch

import pytest

from .. import slack


@pytest.fixture(scope="function", autouse=True)
def enable_slack():
    """make sure slack is enabled prior to every test"""
    slack.enable()


@pytest.fixture
def mock_requests():
    with patch("ledona.slack.requests") as mock_requests_cls:
        mock_requests_cls.post.return_value.status_code = 200
        yield mock_requests_cls


SLACK_URL = "slack.com"


@pytest.mark.parametrize(
    "text,attachments,ref_data",
    [
        ("tex", None, {"text": "tex"}),
        (None, [{"a": 1, "b": 2}], {"attachments": [{"a": 1, "b": 2}]}),
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


def notify_test_helper(msg, required_present_text, required_absent_text):
    assert {type(required_present_text), type(required_absent_text)} == {list}
    for text in required_present_text:
        assert text in msg

    for text in required_absent_text:
        assert text not in msg
