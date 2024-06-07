import argparse
import functools
import json
import os
import time
import warnings
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

import requests

_WEBHOOK_ENV_VAR_NAME = "LEDONA_SLACK_WEBHOOK_URL"
_ENABLED = True


def is_enabled():
    """is slack notification enabled?"""
    return _ENABLED


def enable():
    """
    enable notifications. notifications are enabled by default,
    only useful after a call to disable
    """
    global _ENABLED
    _ENABLED = True


def disable():
    """disable notifications"""
    global _ENABLED
    _ENABLED = False


def webhook(url, text=None, attachments=None):
    """returns the requests result, or 'disabled' if slack notifications are disabled"""
    if not is_enabled():
        return "disabled"

    dict_ = {}
    if text is not None:
        assert isinstance(text, str)
        dict_["text"] = text
    if attachments is not None:
        assert isinstance(attachments, (list, tuple))
        dict_["attachments"] = attachments

    if len(dict_) == 0:
        raise ValueError("Nothing to send")

    return requests.post(url, data=json.dumps(dict_), headers={"Content-Type": "application/json"})


class SlackNotifyError(Exception):
    pass


SlackNotifyCallback = Callable[
    [
        Literal["start", "end", "fail"],
        tuple,
        dict[str, Any],
        dict[Literal["func_name", "elapsed", "returned", "exception"]],
    ],
    str | None,
]
"""
callback sig for notify decorator
arg1: why is the callback being executed
arg2: the args being sent to the decorated function
arg3: the kwargs being sent to the decorated function
arg4: if the decorated function is finished then this is dict containing the 
    result of the function if the
returns: string to slack or if None then nothing
"""


def _default_slack_msg_func(
    stage: Literal["start", "end", "fail"],
    args: tuple,
    kwargs: dict,
    info: dict[Literal["func", "elapsed", "returned", "exception"], Any],
):
    return f"Function={info['func']}\n{stage=}\n{args=}\n{kwargs=}\n{info=}"


def notify(
    msg_func: SlackNotifyCallback = _default_slack_msg_func,
    webhook_url=None,
    raise_on_http_error=False,
    on_entrance=True,
    on_exit=True,
):
    """
    Decorator that sends a message to slack on func entrance/exit

    raise_on_http_error: If true then an exception is raised if the http
        response is not success if false, then a warning will be issued
    """
    assert on_entrance or on_exit, "Nothing to do, both on_exit and on_entrance are False"
    url = webhook_url or os.environ.get(_WEBHOOK_ENV_VAR_NAME)
    if url is None:
        warnings.warn(
            f"Slack webhook url environment variable '{_WEBHOOK_ENV_VAR_NAME}' is not set! "
            "Slack notifications disabled!"
        )
        disable()

    def send_slack(msg: str):
        r = webhook(url, text=msg)
        if r == "disabled" or r.status_code == 200:
            return

        err_msg = f"Non 200 response from Slack. {r}"
        if raise_on_http_error:
            raise SlackNotifyError(err_msg, r)
        warnings.warn(err_msg)

    # actual decorator, paramaterized
    def dec_(func):
        @functools.wraps(func)
        def wrapper_notify(*args, **kwargs):
            msg = msg_func("start", args, kwargs, {"func": func})
            if msg is not None:
                send_slack(msg)
            func_exception = None
            result = None
            _start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except BaseException as ex:
                func_exception = ex
                raise
            finally:
                if on_exit:
                    elapsed = timedelta(seconds=round(time.perf_counter() - _start, 3))
                    state = "end" if func_exception is None else "fail"
                    msg = msg_func(
                        state,
                        args,
                        kwargs,
                        {
                            "func": func,
                            "exception": func_exception,
                            "returned": result,
                            "elapsed": elapsed,
                        },
                    )
                    if msg is not None:
                        send_slack(msg)
            return result

        return wrapper_notify

    return dec_


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a message to slack")
    hook_url = os.environ.get(_WEBHOOK_ENV_VAR_NAME)
    assert hook_url, f"No webhook set to environment variable '{_WEBHOOK_ENV_VAR_NAME}'"
    parser.add_argument(
        "--url",
        metavar="WEBHOOK_URL",
        default=hook_url,
        help="Default is value of environment variable LEDONA_SLACK_WEBHOOK_URL, "
        f"now set to '{hook_url}'",
    )
    parser.add_argument("msg")
    args_ = parser.parse_args()

    result_ = webhook(args_.url, text=args_.msg)
    if result_ == "disabled":
        print("Failed to send because messaging is disabled")
    else:
        print(f"{result_.status_code}: {result_.text}")
