import argparse

from .. import ArgumentDefaultsHelpNoNoneFormatter


class HelpFormatterTest(argparse.HelpFormatter):
    def _get_help_string(self, action):
        help = action.help
        if '%(default)' not in action.help:
            if action.default not in (argparse.SUPPRESS, None):
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help += ' (default: %(default)s)'
        return help


def test_help_formatter_class_call(mocker):
    """ try and discern changes in the way formatter class is called for arg help """
    get_help_string_call_args = []

    class TestHelpFormatter(argparse.HelpFormatter):
        def _get_help_string(self, action):
            get_help_string_call_args.append(action)
            help = super()._get_help_string(action)
            return help

    parser = argparse.ArgumentParser(formatter_class=TestHelpFormatter)
    help_ = "test formatted call"
    default = 1
    parser.add_argument("--x", help=help_, default=default)
    try:
        parser.parse_args(["--help"])
    except SystemExit:
        pass

    assert len(get_help_string_call_args) == 2, "Should be two calls, first for -h, second for --x"
    assert get_help_string_call_args[1].help == help_
    assert get_help_string_call_args[1].default == default
    assert get_help_string_call_args[1].option_strings == ['--x']


def test_nonone_help_w_None(capsys):
    parser = argparse.ArgumentParser(formatter_class=ArgumentDefaultsHelpNoNoneFormatter)
    parser.add_argument("--x", help="this is help with no default")
    try:
        parser.parse_args(["--help"])
    except SystemExit:
        pass

    captured = capsys.readouterr()
    assert 'default:' not in captured.out


def test_nonone_help_w_value(capsys):
    parser = argparse.ArgumentParser(formatter_class=ArgumentDefaultsHelpNoNoneFormatter)
    default = 1
    parser.add_argument("--x", help="this is help with a default", default=default)
    try:
        parser.parse_args(["--help"])
    except SystemExit:
        pass

    captured = capsys.readouterr()
    assert 'default: {}'.format(default) in captured.out
