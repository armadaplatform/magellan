from __future__ import print_function

import base64
import hashlib
import os
import re
import socket
import traceback

import requests
from armada import hermes

import remote

auth_config = hermes.get_config('auth_config.json', {})
AUTHORIZATION_TOKEN = auth_config.get('main_haproxy_auth_token')


def _is_ip(hostname):
    try:
        socket.inet_aton(hostname)
        return True
    except socket.error:
        return False


def _clean_string(s):
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', s)


class Haproxy(object):
    _max_connections_global = DEFAULT_MAX_CONNECTIONS_GLOBAL = 256
    _max_connections_service = DEFAULT_MAX_CONNECTIONS_SERVICE = 32

    CONFIG_HEADER = r'''
global
    daemon
    maxconn {max_connections}
    stats socket /var/run/haproxy/stats.sock

{stats_section}

defaults
    mode http
    timeout connect 5s
    timeout client 300s
    timeout server 300s
    option http-server-close

frontend http-in
    bind *:{listen_port}
    default_backend backend_default
    http-request del-header Proxy
    maxconn {max_connections}

'''

    STATS_SECTION = r'''

listen stats
    bind            *:8001
    mode            http
    log             global

    maxconn 10

    timeout client      100s
    timeout server      100s
    timeout connect     100s
    timeout queue       100s

    stats enable
    stats hide-version
    stats refresh 30s
    stats show-node
    stats auth {stats_user}:{stats_password}
    stats uri /

'''

    DEFAULT_BACKEND_SECTION = '''
backend backend_default
    server server_0 localhost:8080 maxconn {max_connections_service}
    http-request del-header Proxy

'''

    stats_enabled = False
    stats_user = 'root'
    stats_password = 'armada'

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
        stats_section = self.STATS_SECTION if self.stats_enabled else ''
        stats_section = stats_section.format(
            stats_user=self.stats_user,
            stats_password=self.stats_password,
        )
        result = self.CONFIG_HEADER.format(
            listen_port=self.listen_port,
            max_connections=self._max_connections_global,
            stats_section=stats_section,
        )

        # Sort by the length of domains (descending), to ensure that entries for overlapping paths like:
        #    example.com/sub/path, example.com/sub, example.com
        # will be ordered starting from the most specific one.
        domains = list(sorted(domains_to_addresses.items(), key=lambda (domain, _): -len(domain)))

        urls = [self.split_url(domain) for domain, _ in domains]
        for i, (host, path) in enumerate(urls):
            cleaned_host = _clean_string(host)
            lines = '\tacl host_{i} hdr(host) -i {host}\n'
            if path:
                lines += '\tacl path_{i} path_beg /{path}/\n'
                lines += '\tuse_backend backend_{i}_{cleaned_host} if host_{i} path_{i}\n'
                lines += '\tacl path_{i}a path /{path}\n'
                lines += '\tuse_backend backend_{i}a_{cleaned_host} if host_{i} path_{i}a\n'
            else:
                lines += '\tuse_backend backend_{i}_{cleaned_host} if host_{i}\n'
            lines += '\n'
            result += lines.format(**locals())
        max_connections_service = self._max_connections_service
        for i, (host, path) in enumerate(urls):
            cleaned_host = _clean_string(host)
            lines = 'backend backend_{i}_{cleaned_host}\n'
            lines += '\thttp-request del-header Proxy\n'
            if path:
                lines += '\treqirep ^([^\ ]*)\ /{path}/(.*)  \\1\ /\\2\n'
            for container_id, address in sorted(domains[i][1].items()):
                lines += '\tserver server_{container_id} {address}'.format(**locals()) + ' maxconn {max_connections_service}\n'
                hostname = address.split(':')[0]
                if not _is_ip(hostname):
                    lines += '\thttp-request set-header Host {}\n'.format(address)
            lines += '\n'
            if path:
                lines += 'backend backend_{i}a_{cleaned_host}\n'
                lines += '\thttp-request del-header Proxy\n'
                lines += '\treqirep ^([^\\ ]*)\\ /{path}\\ (.*)  \\1\\ /\\ \\2\n'
                for container_id, address in sorted(domains[i][1].items()):
                    lines += '\tserver server_{container_id} {address}'.format(**locals()) + ' maxconn {max_connections_service}\n'
                lines += '\n'
            result += lines.format(**locals())
        result += self.DEFAULT_BACKEND_SECTION.format(**locals())

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

    def configure_stats(self, stats_config):
        stats_config = stats_config or {}
        self.stats_enabled = stats_config.get('enabled') or self.stats_enabled
        self.stats_user = stats_config.get('user') or self.stats_user
        self.stats_password = stats_config.get('password') or self.stats_password


class MainHaproxy(Haproxy):
    def __init__(self, load_balancer):
        super(MainHaproxy, self).__init__(load_balancer)
        self.config_path = '/tmp/main-haproxy_{}.cfg'.format(self.load_balancer['container_id'])

    def restart(self):
        pass

    @staticmethod
    def get_headers():
        headers = {}
        # if token was provided, let's introduce ourselves with it
        # in case main-haproxy requires it.
        if AUTHORIZATION_TOKEN:
            headers['Authorization'] = 'Token {}'.format(AUTHORIZATION_TOKEN)
        return headers

    def put_config(self, config):
        with open(self.config_path, 'w') as config_file:
            config_file.write(config)
        address = self.load_balancer['address']
        url = 'http://{address}/upload_config'.format(**locals())
        response = requests.post(url, data=base64.b64encode(config), headers=self.get_headers())
        if response.status_code != 200:
            raise Exception('upload_config http code: {status_code}'.format(status_code=response.status_code))

    def override_haproxy_parameters(self, haproxy_parameters):
        haproxy_parameters = haproxy_parameters or {}
        self._max_connections_global = haproxy_parameters.get('max_connections_global', self.DEFAULT_MAX_CONNECTIONS_GLOBAL)
        self._max_connections_service = haproxy_parameters.get('max_connections_service', self.DEFAULT_MAX_CONNECTIONS_SERVICE)
