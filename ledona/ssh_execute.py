"""
Functions that use command line ssh to do some useful things. If an ssh command can be run on the
command line then it can work here. Use execute to run an arbitrary ssh command line. All the other
functions wrap around execute and parse the result to something convenient
"""
import logging
from subprocess import run, CalledProcessError
from typing import List


LOGGER = logging.getLogger(__name__)


def ssh_execute(connect: str, remote_cmd: str) -> str:
    """
    Use ssh to execute the command in cli_str
    connect - ssh connection string. i.e. run f"ssh {connect} {cmd}"
    cmd - command to run on remote
    returns - stdout as a string

    raises CalledProcessError if there is an error running ssh
    """
    LOGGER.info("Running: %s %s", connect, remote_cmd)
    try:
        completed_process = run(f"ssh {connect} {remote_cmd}",
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


def ls(connect: str, path: str = "*") -> List[str]:
    """
    List the contents of the requested path. Will run f"ssh {ssh_connect} 'ls {path}'".
    If the connection is not successful or the path does not exist then CalledProcessError
    will be raised.

    connect: ssh command line args needed to connect. Will result in command line of
       f"ssh {ssh_connect}"
    returns - list of filenames

    If no files are found at path then return an empty list.
    """
    try:
        ls_result = ssh_execute(connect, f"'ls -d {path}'")
        return ls_result.strip().split("\n")
    except CalledProcessError as cpe:
        LOGGER.error("Error listing contents for '%s/%s'", connect, path, exc_info=cpe)
        if 'No such file or directory' in cpe.stderr:
            return []
        raise


def scp(src_path: str, dest_path: str):
    """
    copy file from source_path to dest_path using scp. Will run f"scp {source_path} {dest_path}"
    Make sure that whichever path is remote looks like {REMOTE_HOST}:path

    raises CalledProcessError if there is an error running scp
    """
    completed_process = run(f"scp {src_path} {dest_path}",
                            shell=True,
                            encoding="utf-8",
                            check=True,
                            capture_output=True)
