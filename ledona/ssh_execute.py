"""
Functions that use command line ssh to do some useful things. If an ssh command can be run on the
command line then it can work here. Use execute to run an arbitrary ssh command line. All the other
functions wrap around execute and parse the result to something convenient
"""
import logging
from subprocess import run, CalledProcessError
from typing import List


LOGGER = logging.getLogger(__name__)


def ssh_execute(ssh_args: str, remote_cmd: str) -> str:
    """
    Use ssh to execute the command in cli_str
    connect - ssh connection string. i.e. run f"ssh {connect} {cmd}"
    cmd - command to run on remote
    returns - stdout as a string

    raises CalledProcessError if there is an error running ssh
    """
    LOGGER.info("Running: ssh %s '%s'", ssh_args, remote_cmd)
    try:
        completed_process = run(f"ssh {ssh_args} '{remote_cmd}'",
                                shell=True,
                                encoding="utf-8",
                                capture_output=True,
                                check=True)
    except CalledProcessError as cpe:
        LOGGER.debug("SSH subprocess run failed", exc_info=cpe)
        raise

    result = completed_process.stdout
    LOGGER.debug("Successfully Received: %s", result)
    return result


def ls(remote_url: str) -> List[str]:
    """
    List the contents of the requested remote path.

    remote_path - Of the form {REMOTE_HOST}[:port][/path] where port and path are optional, if no path
      then list contents are default directory. If no path is given then '*' will be used (i.e. glob
      search for all files in the default directory). To list multiple files a glob MUST be used.

    returns - list of filenames

    If no files are found at path then return an empty list.
    """
    if '/' in remote_url:
        remote_host, remote_path = remote_url.split('/', 1)
    else:
        remote_host = remote_url
        remote_path = '*'

    if ':' in remote_host:
        if remote_host.count(':') > 1:
            raise ValueError(f"Remote url format invalid. Must be REMOTE_HOST[:port][/path]. {remote_url=}")
        host, port = remote_host.split(':')
        assert port.isdigit(), f"port should be an integer. instead {port=}"
        ssh_args = f"{host} -p {port}"
    else:
        ssh_args = remote_host

    try:
        ls_result = ssh_execute(ssh_args, f"shopt -s dotglob ; ls -Ad {remote_path}")
        return ls_result.strip().split("\n")
    except CalledProcessError as cpe:
        LOGGER.debug("Error listing contents for '%s", remote_url, exc_info=cpe)
        if 'No such file or directory' in cpe.stderr:
            return []
        raise


def scp(src_path: str, dest_path: str):
    """
    copy file from source_path to dest_path using scp. Will run f"scp {source_path} {dest_path}"
    Make sure that whichever path is remote it looks like scp://[user@]host[:port][/path]
    raises CalledProcessError if there is an error running scp
    """
    assert src_path.startswith("scp://") != dest_path.startswith("scp://"), "expecting to be writing to XOR from remote"
    run(f"scp {src_path} {dest_path}",
        shell=True,
        encoding="utf-8",
        check=True,
        capture_output=True)
