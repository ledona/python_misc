import argparse
import json
import os
import pprint
import socket
import time
import traceback
import warnings
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal, Required, TypedDict, TypeVar, cast

import requests

_WEBHOOK_ENV_VAR_NAME = "LEDONA_SLACK_WEBHOOK_URL"
_ENABLED = True
_HOSTNAME = None
"""cache of the host name if it is ever needed when sending a message"""


def _get_hostname():
    global _HOSTNAME
    if _HOSTNAME is None:
        _HOSTNAME = socket.gethostname()
    return _HOSTNAME


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


class SlackNotifyError(Exception): ...


def webhook(
    url,
    payload: dict[str, dict | list | tuple | str] | None = None,
    text: str | None = None,
    attachments: list | tuple | None = None,
):
    """returns the requests result, or 'disabled' if slack notifications are disabled"""
    if not is_enabled():
        return "disabled"

    if payload:
        if text is not None and attachments is not None:
            raise SlackNotifyError("if payload is not None then attachments and text must be None")
        dict_ = payload
    else:
        if text is None:
            raise SlackNotifyError("payload or text must be defined")
        dict_ = {"text": text}
        if attachments is not None:
            dict_["attachments"] = attachments

    if len(dict_) == 0:
        raise ValueError("Nothing to send")

    return requests.post(url, data=json.dumps(dict_), headers={"Content-Type": "application/json"})


def send_slack(
    msg: str | dict,
    webhook_url: str | None = None,
    include_hostname=True,
    raise_on_http_error=False,
):
    """
    send a message to slack

    include_hostname: if true include the hostname in the message
    raise_on_http_error: If true then an exception is raised if the http
        response is not success if false, then a warning will be issued
    """
    if not is_enabled():
        return
    url = webhook_url or os.environ.get(_WEBHOOK_ENV_VAR_NAME)
    if url is None:
        warnings.warn(
            f"Slack webhook url environment variable '{_WEBHOOK_ENV_VAR_NAME}' is not set! "
            "Slack notifications disabled!"
        )
        disable()
        return

    kwargs: dict[str, Any]
    if isinstance(msg, str):
        kwargs = {"text": (f"[{_get_hostname()}] " if include_hostname else "") + msg}
    elif not include_hostname:
        kwargs = {"payload": msg}
    else:
        # include hostname and msg is a dict
        payload = msg.copy()
        payload["text"] = f"[{_get_hostname()}]" + (
            (" " + payload["text"]) if "text" in payload else ""
        )
        kwargs = {"payload": payload}
    r = webhook(url, **kwargs)
    if r == "disabled" or r.status_code == 200:
        return

    err_msg = f"Non 200 response from Slack. {r}"
    if raise_on_http_error:
        raise SlackNotifyError(err_msg, r)
    warnings.warn(err_msg)


class _InfoDict(TypedDict, total=False):
    """information dict for notify callback"""

    func: Required[Callable]
    """The function that notify is wrapping"""
    elapsed: timedelta
    """elapsed time to completion"""
    returned: Any
    """the returned value from the function"""
    exception: BaseException
    """the exception raised by the function"""


_Stage = Literal["start", "end", "fail"]

SlackNotifyCallback = Callable[[_Stage, tuple, dict[str, Any], _InfoDict], str | dict | None]
"""
callback sig for notify decorator
arg1: why is the callback being executed
arg2: the args being sent to the decorated function
arg3: the kwargs being sent to the decorated function
arg4: if the decorated function is finished then this is dict containing the 
    result of the function if the
returns: string or dict to slack or if None then nothing
"""


def _default_slack_msg_func(
    stage: _Stage,
    args: tuple,
    kwargs: dict,
    info: _InfoDict,
):
    msg = f"""*{stage}* of *{info['func'].__name__}(...)*

*ARGS*

```{pprint.pformat(args)}```

*KWARGS*

```{pprint.pformat(kwargs)}```"""
    if stage == "end":
        assert "returned" in info
        msg += f"\n\n*RETURNED*\n`{pprint.pformat(info['returned'])}`"
    elif stage == "fail":
        assert "exception" in info
        trace = "\n".join(traceback.format_exception(info["exception"]))
        msg += f"\n\n*EXCEPTION*: `{info['exception']}`\n```{trace}```"

    return msg


F = TypeVar("F", bound=Callable[..., Any])


def notify(
    msg_func: SlackNotifyCallback = _default_slack_msg_func,
    webhook_url=None,
    raise_on_http_error=False,
    on_entrance=True,
    on_exit=True,
):
    """
    Decorator that sends a message to slack on func entrance/exit.

    The decorated function will have the attribute 'slack_set_enabled'
    attached to it. this is a function that takes a boolean that will
    override the global slack enabled state for this function for the
    next call only
    """
    assert on_entrance or on_exit, "Nothing to do, both on_exit and on_entrance are False"

    def dec_(func: F) -> F:
        local_enabled_flag: bool | None = None

        def _slack_set_enabled(enable_: bool | None):
            nonlocal local_enabled_flag
            local_enabled_flag = enable_

        def wrapper_notify(*args, **kwargs):
            nonlocal local_enabled_flag

            dont_slack = (
                not is_enabled() and local_enabled_flag is not True
            ) or local_enabled_flag is False
            local_enabled_flag = None
            if dont_slack:
                local_enabled_flag = None
                return func(*args, **kwargs)

            msg = msg_func("start", args, kwargs, {"func": func})
            if msg is not None:
                send_slack(msg, raise_on_http_error=raise_on_http_error, webhook_url=webhook_url)
            func_exception: None | BaseException = None
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
                    info: _InfoDict = {
                        "func": func,
                        "returned": result,
                        "elapsed": elapsed,
                    }
                    if func_exception:
                        info["exception"] = func_exception
                    msg = msg_func(state, args, kwargs, info)
                    if msg is not None:
                        send_slack(msg)
            return result

        setattr(wrapper_notify, "slack_set_enabled", _slack_set_enabled)
        return cast(F, wrapper_notify)

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
