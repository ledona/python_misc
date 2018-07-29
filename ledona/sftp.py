from contextlib import contextmanager
import paramiko
import os

_DEFAULT_SSH_PATH = os.path.expanduser(os.path.join("~", ".ssh"))
_DEFAULT_SSH_CONFIG_PATH = os.path.join(_DEFAULT_SSH_PATH, "config")
_DEFAULT_SSH_PKEY_PATH = os.path.join(_DEFAULT_SSH_PATH, "id_rsa")


@contextmanager
def connect(connection_str=None, hostname=None, username=None, port=None, password=None,
            ssh_config_filepath=_DEFAULT_SSH_CONFIG_PATH, pkey_filepath=_DEFAULT_SSH_PKEY_PATH):
    """
    Context manager that yields a paramiko sftp client object, if connection_str is given then
    username and password are ignored.

    ssh_config_filepath: default to ~/.ssh/config, set to None for no config
    pkey_filepath: default to ~/.ssh/pkey, set to None for no pkey
    connection_str: [user@]host[:port]

    yields: a paramiko sftp client object
    """
    if connection_str is not None:
        if '@' in connection_str:
            username, connection_str = connection_str.split("@")
        else:
            username = None

        if ":" in connection_str:
            hostname, port = connection_str.split(":")
            port = int(port)
        else:
            hostname = connection_str
            port = None

    if ssh_config_filepath is not None:
        # update with things from config
        ssh_config = paramiko.SSHConfig()
        with open(ssh_config_filepath, "r") as f:
            ssh_config.parse(f)

        user_config = ssh_config.lookup(hostname)
        # always use config hostname
        hostname = user_config['hostname']

        # grab port and user if needed
        if username is None:
            username = user_config['user']
        # only use port if not already explicitly set
        if port is None and 'port' in user_config:
            port = int(user_config['port'])

    if port is None:
        port = 22

    mykey = (paramiko.RSAKey.from_private_key_file(pkey_filepath)
             if pkey_filepath is not None else None)

    transport = paramiko.Transport((hostname, port))
    transport.connect(username=(username or ""), pkey=mykey)

    sftp = paramiko.SFTPClient.from_transport(transport)

    yield sftp

    sftp.close()
