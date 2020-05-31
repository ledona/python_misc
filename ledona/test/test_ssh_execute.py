import pytest

from ledona import ssh_execute


LS_FILES = [
    'a',
    'b',
    'c',
]
HOST = 'remote_host'
PORT = 1234
PATH = 'x/y/z/*'


@pytest.mark.parametrize('ls_url, expected_ssh_cmdline', [
    (f"{HOST}", f"ssh {HOST} 'shopt -s dotglob ; ls -Ad *'"),
    (f"{HOST}//{PATH}", f"ssh {HOST} 'shopt -s dotglob ; ls -Ad /{PATH}'"),
    (f"{HOST}:{PORT}/{PATH}", f"ssh {HOST} -p {PORT} 'shopt -s dotglob ; ls -Ad {PATH}'"),
    (f"{HOST}:{PORT}//{PATH}", f"ssh {HOST} -p {PORT} 'shopt -s dotglob ; ls -Ad /{PATH}'"),
])
def test_ls(ls_url, expected_ssh_cmdline, mocker):
    """ test that the correct ssh commands are run for ls """
    mock_run = mocker.patch('ledona.ssh_execute.run')
    mock_run.return_value.stdout = "\n".join(LS_FILES)

    test_files = ssh_execute.ls(ls_url)
    assert test_files == LS_FILES

    mock_run.assert_called_once()
    assert mock_run.call_args_list[0][0][0] == expected_ssh_cmdline


def test_scp(mocker):
    """ just test that run is called """
    mock_run = mocker.patch('ledona.ssh_execute.run')
    src = "scp://user@remote:1234/x/y/z"
    dest = "x/y/z"
    ssh_execute.scp(src, dest)
    mock_run.assert_called_once()
    assert mock_run.call_args_list[0][0][0] == f"scp {src} {dest}"
