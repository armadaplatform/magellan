def get_ssh_connection(remote_address):
    import paramiko

    class SilentPolicy(paramiko.WarningPolicy):
        def missing_host_key(self, client, hostname, key):
            pass

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(SilentPolicy())
    ssh_key = paramiko.RSAKey.from_private_key_file(remote_address['ssh_key'])
    ssh.connect(remote_address['host'], username=remote_address['user'], pkey=ssh_key, port=int(remote_address['port']),
                timeout=10)
    return ssh


def execute_remote_command(command, remote_address):
    ssh = get_ssh_connection(remote_address)
    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)
    ssh_out = ssh_stdout.read()
    ssh_err = ssh_stderr.read()
    ssh_return_code = ssh_stdout.channel.recv_exit_status()
    ssh.close()
    return ssh_return_code, ssh_out, ssh_err


def put_remote_file(local_path, remote_path, remote_address):
    ssh = get_ssh_connection(remote_address)
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    ssh.close()
