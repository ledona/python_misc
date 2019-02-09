from unittest.mock import patch
from contextlib import ExitStack
import pytest
import json
import socket
import os

from .. import slack

@pytest.fixture(scope="function", autouse=True)
def enable_slack():
    """ make sure slack is enabled prior to every test """
    slack.enable()


@pytest.fixture
def mock_requests():
    with patch("ledona.slack.requests") as mock_requests_cls:
        mock_requests_cls.post.return_value.status_code = 200
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


def test_disable(mock_requests):
    assert slack.is_enabled()
    slack.disable()
    assert not slack.is_enabled()
    slack.webhook(SLACK_URL, text="disable test")
    slack.enable()
    assert slack.is_enabled()
    mock_requests.post.not_called()


def notify_test_helper(msg, required_present_text, required_absent_text):
    assert {type(required_present_text), type(required_absent_text)} == {list}
    for text in required_present_text:
        assert text in msg

    for text in required_absent_text:
        assert text not in msg


@pytest.mark.parametrize(
    "url,env_var,additional_msg,on_entrance,on_exit,include_timing,include_host,include_args,include_return",
    [(SLACK_URL, None, None, True, True, True, True, True, True),
     (SLACK_URL, None, None, False, True, True, True, False, True),
     (SLACK_URL, None, None, True, False, True, False, False, False),
     (SLACK_URL, None, 'additional text', True, True, True, True, False, False),
     (None, "ENV_VAR", 'additional text', True, True, True, True, True, False),
    ]
)
def test_decorator_simple_w_url(url, env_var, additional_msg,
                                on_entrance, on_exit, include_timing, include_host,
                                include_args, include_return):
    """ some minimal testing of notify decorator """
    with ExitStack() as stack:
        mock_webhook = stack.enter_context(patch("ledona.slack.webhook"))
        mock_webhook.return_value.status_code = 200
        if env_var is not None:
            stack.enter_context(patch.dict(os.environ,
                                           {env_var: SLACK_URL + "env"}))

        call_args = []
        return_value = {'tanis': 'there are wonderous things'}

        @slack.notify(webhook_url=url, env_var=env_var, additional_msg=additional_msg,
                      on_entrance=on_entrance, on_exit=on_exit, include_args=include_args,
                      include_timing=include_timing, include_host=include_host,
                      include_return=include_return)
        def test_func(a, b, c=None, d=None):
            call_args.append(((a, b), {'c': c, 'd': d}))
            return return_value

        test_func(1, 2, c='x', d='y')

        assert call_args == [((1, 2), {'c': 'x', 'd': 'y'})]

        assert mock_webhook.call_count == (1 if on_entrance else 0) + (1 if on_exit else 0)

        # figure out the expected text present and absent in the msg
        webhook_call_args_list = list(mock_webhook.call_args_list)
        host_name = socket.gethostname()
        required_text = ['test_func']
        absent_text = []
        if include_host:
            required_text.append(host_name)
        else:
            absent_text.append(host_name)
        if additional_msg is not None:
            required_text.append(additional_msg)
        if include_args:
            required_text += [str(call_args[0][0]), str(call_args[0][1])]
        else:
            absent_text += [str(call_args[0][0]), str(call_args[0][1])]

        # what is the expected URL
        expected_url = SLACK_URL
        if url is None:
            expected_url += "env"

        return_value_as_str = str(return_value)
        if on_entrance:
            assert expected_url == webhook_call_args_list[0][0][0]
            notify_test_helper(webhook_call_args_list[0][1]['text'],
                               required_text + ['call'],
                               absent_text + [return_value_as_str])
            del webhook_call_args_list[0]

        if on_exit:
            assert expected_url == webhook_call_args_list[0][0][0]
            req = required_text + ['exit']
            absent = absent_text
            if include_return:
                req.append(return_value_as_str)
            else:
                absent += [return_value_as_str]

            notify_test_helper(webhook_call_args_list[0][1]['text'],
                               req, absent)
