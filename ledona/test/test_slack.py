from unittest.mock import patch
from contextlib import ExitStack
import pytest
import json
import socket
import os

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

@pytest.mark.parametrize(
    "url,env_var,additional_msg,on_entrance,on_exit,include_timing,include_host",
    [(SLACK_URL, None, None, True, True, True, True),
     (SLACK_URL, None, None, False, True, True, True),
     (SLACK_URL, None, None, True, False, True, True),
     (SLACK_URL, None, 'additional text', True, True, True, True),
     (None, "ENV_VAR", 'additional text', True, True, True, True),
    ]
)
def test_decorator_simple_w_url(url, env_var, additional_msg,
                                on_entrance, on_exit, include_timing, include_host):
    """ some minimal testing of notify decorator """
    with ExitStack() as stack:
        mock_webhook = stack.enter_context(patch("ledona.slack.webhook"))
        if env_var is not None:
            stack.enter_context(patch.dict(os.environ,
                                           {env_var: SLACK_URL + "env"}))

        call_args = []

        @slack.notify(webhook_url=url, env_var=env_var, additional_msg=additional_msg,
                      on_entrance=on_entrance, on_exit=on_exit,
                      include_timing=include_timing, include_host=include_host)
        def test_func(a, b, c=None, d=None):
            call_args.append((a, b, c, d))

        test_func(1, 2, c='x', d='y')

        assert call_args == [(1, 2, 'x', 'y')]

        assert mock_webhook.call_count == (1 if on_entrance else 0) + (1 if on_exit else 0)

        webhook_call_args_list = list(mock_webhook.call_args_list)
        if on_entrance:
            if url is None:
                assert SLACK_URL + "env" in webhook_call_args_list[0][0]
            else:
                assert SLACK_URL in webhook_call_args_list[0][0]

            test_text = webhook_call_args_list[0][1]['text']
            assert 'call' in test_text
            if additional_msg is not None:
                assert additional_msg in test_text

            assert 'test_func' in test_text

            if include_host:
                assert socket.gethostname() in test_text

            del webhook_call_args_list[0]

        if on_exit:
            if url is None:
                assert SLACK_URL + "env" in webhook_call_args_list[0][0]
            else:
                assert SLACK_URL in webhook_call_args_list[0][0]

            test_text = webhook_call_args_list[0][1]['text']
            assert 'exit' in test_text
            if additional_msg is not None:
                assert additional_msg in test_text

            assert 'test_func' in test_text

            if include_host:
                assert socket.gethostname() in test_text
