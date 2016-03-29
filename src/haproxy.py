from __future__ import print_function

import base64
import hashlib
import os
import socket
import traceback

import requests

import remote


def _is_ip(hostname):
    try:
        socket.inet_aton(hostname)
        return True
    except socket.error:
        return False


class Haproxy(object):
    MAX_CONNECTIONS_GLOBAL = 256
    MAX_CONNECTIONS_SERVICE = 32
    CONFIG_HEADER = '''
global
    daemon
    maxconn {max_connections}

defaults
    mode http
    timeout connect 5s
    timeout client 300s
    timeout server 300s
    option http-server-close

frontend http-in
    bind *:{listen_port}
    default_backend backend_default

'''

    DEFAULT_BACKEND = '''
backend backend_default
    server server_0 localhost:8080 maxconn {max_connections_service}

'''.format(max_connections_service=MAX_CONNECTIONS_SERVICE)

    def __init__(self, load_balancer):
        self.load_balancer = load_balancer
        self.config_path = '/tmp/haproxy_{hash}.cfg'.format(hash=hashlib.md5(repr(load_balancer)).hexdigest())
        self.listen_port = 80

    def get_current_config(self):
        if not os.path.exists(self.config_path):
            return ''
        with open(self.config_path, 'r') as haproxy_config_file:
            return haproxy_config_file.read()

    @staticmethod
    def split_url(url):
        host, path = (url.split('/', 1) + [''])[:2]
        return host, path.strip('/')

    def generate_config_from_domains_to_addresses(self, domains_to_addresses):
        result = self.CONFIG_HEADER.format(listen_port=self.listen_port,
                                           max_connections=self.MAX_CONNECTIONS_GLOBAL)

        # Sort by the length of domains (descending), to ensure that entries for overlapping paths like:
        #    example.com/sub/path, example.com/sub, example.com
        # will be ordered starting from the most specific one.
        domains = list(sorted(domains_to_addresses.items(), key=lambda (domain, _): -len(domain)))

        urls = [self.split_url(domain) for domain, _ in domains]
        for i, (host, path) in enumerate(urls):
            lines = '\tacl host_{i} hdr(host) -i {host}\n'
            if path:
                lines += '\tacl path_{i} path_beg /{path}/\n'
                lines += '\tuse_backend backend_{i} if host_{i} path_{i}\n'
                lines += '\tacl path_{i}a path /{path}\n'
                lines += '\tuse_backend backend_{i}a if host_{i} path_{i}a\n'
            else:
                lines += '\tuse_backend backend_{i} if host_{i}\n'
            lines += '\n'
            result += lines.format(**locals())
        max_connections_service = self.MAX_CONNECTIONS_SERVICE
        for i, (host, path) in enumerate(urls):
            lines = 'backend backend_{i}\n'
            if path:
                lines += '\treqirep ^([^\ ]*)\ /{path}/(.*)  \\1\ /\\2\n'
            for j, address in enumerate(domains[i][1]):
                lines += '\tserver server_{j} {address}'.format(**locals()) + ' maxconn {max_connections_service}\n'
                hostname = address.split(':')[0]
                if not _is_ip(hostname):
                    lines += '\thttp-request set-header Host {}\n'.format(address)
            lines += '\n'
            if path:
                lines += 'backend backend_{i}a\n'
                lines += '\treqirep ^([^\\ ]*)\\ /{path}\\ (.*)  \\1\\ /\\ \\2\n'
                for j, address in enumerate(domains[i][1]):
                    lines += '\tserver server_{j} {address}'.format(**locals()) + ' maxconn {max_connections_service}\n'
                lines += '\n'
            result += lines.format(**locals())
        result += self.DEFAULT_BACKEND
        return result

    def put_config(self, config):
        with open(self.config_path, 'w') as config_file:
            config_file.write(config)
        remote_address = self.load_balancer['ssh']
        remote.put_remote_file(self.config_path, self.config_path, remote_address)
        code, out, err = remote.execute_remote_command(
            'sudo cp {source} {dest}'.format(source=self.config_path, dest='/etc/haproxy/haproxy.cfg'),
            remote_address)
        if code != 0:
            raise Exception('put_config error: {err}'.format(err=err))

    def restart(self):
        remote_address = self.load_balancer['ssh']
        code, out, err = remote.execute_remote_command('sudo service haproxy reload', remote_address)
        if code != 0:
            raise Exception('restart error: {err}'.format(err=err))

    def clear_current_config(self):
        try:
            os.remove(self.config_path)
        except OSError:
            traceback.print_exc()

    def update(self, domains_to_addresses):
        old_config = self.get_current_config()
        new_config = self.generate_config_from_domains_to_addresses(domains_to_addresses)
        if old_config != new_config:
            try:
                self.put_config(new_config)
                self.restart()
            except:
                traceback.print_exc()
                self.clear_current_config()


class MainHaproxy(Haproxy):
    def __init__(self, load_balancer):
        super(MainHaproxy, self).__init__(load_balancer)
        self.config_path = '/tmp/main-haproxy_{}.cfg'.format(self.load_balancer['container_id'])

    def restart(self):
        pass

    def put_config(self, config):
        with open(self.config_path, 'w') as config_file:
            config_file.write(config)
        address = self.load_balancer['address']
        url = 'http://{address}/upload_config'.format(**locals())
        response = requests.post(url, data=base64.b64encode(config))
        if response.status_code != 200:
            raise Exception('upload_config http code: {status_code}'.format(status_code=response.status_code))
