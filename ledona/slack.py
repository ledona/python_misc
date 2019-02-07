import requests
import json
import functools
import time


def webhook(url, text=None, attachments=None):
    """ returns the requests result """
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


def notify(func,
           webhook_url=None, env_var=None, additional_msg=None,
           on_entrance=True, on_exit=True, include_timing=True):
    """ decorator that sends a message to slack on func entrance/exit """
    if not (on_entrance or on_exit):
        raise ValueError("Nothing to do, both on_exit and on_entrance are False")
    @functools.wraps(func)
    def wrapper_notify(*args, **kargs):
        raise NotImplementedError()
        if include_timing:
            start_time = time.now()
        result = func(*args, **kwargs)
        raise NotImplementedError()
        return result

    return wrapper_notify
