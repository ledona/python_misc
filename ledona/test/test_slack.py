from unittest.mock import patch
import pytest
import json

from .. import slack

@pytest.fixture
def mock_requests():
    with patch("ledona.slack.requests") as mock_requests_cls:
        yield mock_requests_cls


SLACK_URL = "slack.com"


@pytest.mark.parametrize("text,attachments,ref_data",
                         [("tex", None, {'text': 'tex'}),
                          (None, [{'a': 1, 'b': 2}], {'attachments': [{'a': 1, 'b': 2}]}),
                          ("tex", [{'a': 1, 'b': 2}], {'attachments': [{'a': 1, 'b': 2}],
                                                       'text': "tex"})])
def test_webhook(mock_requests, text, attachments, ref_data):
    slack.webhook(SLACK_URL, text=text, attachments=attachments)

    mock_requests.post.assert_called_once()
    assert SLACK_URL == mock_requests.post.call_args[0][0]
    test_data = json.loads(mock_requests.post.call_args[1]['data'])
    assert ref_data == test_data

def test_decorator():
    raise NotImplementedError()
