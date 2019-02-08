import requests
import json
import functools
from datetime import datetime
import socket
import os
import warnings

_ENABLED = True

def is_enabled():
    """ is slack notification enabled? """
    return _ENABLED


def enable():
    """
    enable notifications. notifications are enabled by default,
    only useful after a call to disable
    """
    global _ENABLED
    _ENABLED = True


def disable():
    """ disable notifications """
    global _ENABLED
    _ENABLED = False


def webhook(url, text=None, attachments=None):
    """ returns the requests result, or 'disabled' if slack notifications are disabled """
    if not is_enabled():
        return "disabled"

    dict_ = {}
    if text is not None:
        assert isinstance(text, str)
        dict_['text'] = text
    if attachments is not None:
        assert isinstance(attachments, (list, tuple))
        dict_['attachments'] = attachments

    if len(dict_) == 0:
        raise ValueError("Nothing to send")

    return requests.post(url, data=json.dumps(dict_),
                         headers={'Content-Type': 'application/json'})


class SlackNotifyError(Exception):
    pass


def notify(webhook_url=None, env_var=None, additional_msg=None, raise_on_requests_error=False,
           on_entrance=True, on_exit=True, include_timing=True, include_host=True):
    """
    decorator that sends a message to slack on func entrance/exit

    raise_on_requests_error - If true then an exception is raised if the http response is not success
      if false, then a warning will be issued
    """
    assert on_entrance or on_exit, \
        "Nothing to do, both on_exit and on_entrance are False"
    assert (webhook_url is None) != (env_var is None), \
        "Either provide a url XOR an env_var"

    if additional_msg is None:
        additional_msg = ""
    else:
        additional_msg += " "
    url = webhook_url
    if url is None:
        if env_var not in os.environ:
            raise ValueError("Slack webhook url environment variable '{}' is not set!"
                             .format(env_var))
        url = os.environ[env_var]

    # actual decorator, paramaterized
    def dec_(func):
        @functools.wraps(func)
        def wrapper_notify(*args, **kwargs):
            if include_timing:
                start_dt = datetime.now()

            if on_entrance:
                msg = additional_msg
                if include_host:
                    msg += socket.gethostname() + " "
                msg += "called function {}".format(func)
                if include_timing:
                    msg += " at {}".format(start_dt)
                r = webhook(url, text=msg)
                if r.status_code != 200:
                    msg = "Non 200 response from Slack. {}".format(r)
                    if raise_on_requests_error:
                        raise SlackNotifyError(msg, r)
                    else:
                        warnings.warn(msg)
            try:
                result = func(*args, **kwargs)
            finally:
                if on_exit:
                    msg = additional_msg
                    if include_host:
                        msg += socket.gethostname() + " "
                    msg += "exited function {}".format(func)
                    if include_timing:
                        end_dt = datetime.now()
                        msg += " at {}. Elapsed time {}".format(end_dt, end_dt - start_dt)
                    r = webhook(url, text=msg)
                    if r.status_code != 200:
                        msg = "Non 200 response from Slack. {}".format(r)
                        if raise_on_requests_error:
                            raise SlackNotifyError(msg, r)
                        else:
                            warnings.warn(msg)
            return result

        return wrapper_notify

    return dec_
