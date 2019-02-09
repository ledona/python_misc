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


def notify(webhook_url=None, env_var=None, additional_msg=None, raise_on_http_error=False,
           on_entrance=True, on_exit=True, include_timing=True, include_host=True,
           include_args=False, include_return=False):
    """
    decorator that sends a message to slack on func entrance/exit

    raise_on_requests_error - If true then an exception is raised if the http response is not success
      if false, then a warning will be issued
    include_return - include the return value in the exit message. Only matters if on_exit is true
    """
    assert on_entrance or on_exit, \
        "Nothing to do, both on_exit and on_entrance are False"
    assert (webhook_url is None) != (env_var is None), \
        "Either provide a url XOR an env_var"
    assert not (include_return and not on_exit), \
        "include return should not be true if on_exit is false"

    url = webhook_url
    if url is None:
        if env_var not in os.environ:
            raise ValueError("Slack webhook url environment variable '{}' is not set!"
                             .format(env_var))
        url = os.environ[env_var]

    msg_format = "" if additional_msg is None else additional_msg + " : "
    if include_host:
        msg_format += socket.gethostname() + " "
    msg_format += "{stage} function {func}"
    if include_timing:
        msg_format += " at {dt}"
    msg_format += "."
    if include_args:
        msg_format += "\nargs: {args}\nkwargs: {kwargs}"

    # actual decorator, paramaterized
    def dec_(func):
        @functools.wraps(func)
        def wrapper_notify(*args, **kwargs):
            start_dt = datetime.now() if include_timing else None

            if on_entrance:
                msg = msg_format.format(stage='called',
                                        func=func,
                                        dt=start_dt,
                                        args=args,
                                        kwargs=kwargs)
                r = webhook(url, text=msg)
                if r.status_code != 200:
                    err_msg = "Non 200 response from Slack. {}".format(r)
                    if raise_on_requests_error:
                        raise SlackNotifyError(err_msg, r)
                    else:
                        warnings.warn(err_msg)
            try:
                result = func(*args, **kwargs)
            finally:
                if on_exit:
                    end_dt = datetime.now() if include_timing else None
                    end_msg_format = msg_format
                    if include_timing:
                        end_dt = datetime.now()
                        end_msg_format += " Elapsed time {}".format(end_dt - start_dt)
                    else:
                        end_dt = None

                    msg = end_msg_format.format(stage='exited',
                                                func=func,
                                                dt=end_dt,
                                                args=args,
                                                kwargs=kwargs)
                    if include_return:
                        msg += "\nReturned: {}".format(result)
                    r = webhook(url, text=msg)
                    if r.status_code != 200:
                        err_msg = "Non 200 response from Slack. {}".format(r)
                        if raise_on_requests_error:
                            raise SlackNotifyError(err_msg, r)
                        else:
                            warnings.warn(err_msg)
            return result

        return wrapper_notify

    return dec_


if __name__ == "__main__":
    raise NotImplementedError("Command line use not yet implemented")
