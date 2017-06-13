from __future__ import print_function

import base64
import hashlib
import os
import re
import socket
import traceback

import requests
from armada import hermes
from jinja2 import Environment
from jinja2 import FileSystemLoader

import remote
from utils import setup_sentry

auth_config = hermes.get_config('auth_config.json', {})
AUTHORIZATION_TOKEN = auth_config.get('main_haproxy_auth_token')


def _is_ip(hostname):
    try:
        socket.inet_aton(hostname)
        return True
    except socket.error:
        return False


def _clean_string(s):
    return re.sub(r'[^a-zA-Z0-9_\-.]', '_', s)


class Haproxy(object):
    _max_connections_global = DEFAULT_MAX_CONNECTIONS_GLOBAL = 256
    _max_connections_service = DEFAULT_MAX_CONNECTIONS_SERVICE = 32

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
        # Sort by the length of domains (descending), to ensure that entries for overlapping paths like:
        #    example.com/sub/path, example.com/sub, example.com
        # will be ordered starting from the most specific one.
        domains = list(sorted(domains_to_addresses.items(), key=lambda (domain, _): -len(domain)))

        entries = []
        for i, (domain, container_id_to_address) in enumerate(domains):
            host, path = self.split_url(domain)
            cleaned_host = _clean_string(host)
            container_ids_with_addresses = sorted(container_id_to_address.items())
            entries.append((i, host, cleaned_host, path, container_ids_with_addresses))

        j2_env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))
        j2_env.tests['ip'] = _is_ip
        result = j2_env.get_template('templates/haproxy.conf.jinja2').render(
            listen_port=self.listen_port,
            max_connections=self._max_connections_global,
            max_connections_service=self._max_connections_service,
            stats_enables=self.stats_enabled,
            stats_user=self.stats_user,
            stats_password=self.stats_password,
            entries=entries,
        )
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
            setup_sentry().captureException()
            traceback.print_exc()

    def update(self, domains_to_addresses):
        old_config = self.get_current_config()
        new_config = self.generate_config_from_domains_to_addresses(domains_to_addresses)
        if old_config != new_config:
            try:
                self.put_config(new_config)
                self.restart()
            except:
                setup_sentry().captureException()
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
        self._max_connections_global = haproxy_parameters.get('max_connections_global',
                                                              self.DEFAULT_MAX_CONNECTIONS_GLOBAL)
        self._max_connections_service = haproxy_parameters.get('max_connections_service',
                                                               self.DEFAULT_MAX_CONNECTIONS_SERVICE)
