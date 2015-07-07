from __future__ import print_function
from collections import defaultdict
import json

import requests


SHIP_IP = '172.17.42.1'


class Consul(object):
    @staticmethod
    def _query(query):
        url = 'http://{hostname}:8500/v1/{query}'.format(hostname=SHIP_IP, query=query)
        return json.loads(requests.get(url).text)

    @staticmethod
    def get_local_armada_address():
        local_services_dict = Consul._query('agent/services')
        for service in local_services_dict.values():
            if service['Service'] == 'armada':
                return '{}:{}'.format(SHIP_IP, service['Port'])

    @staticmethod
    def discover():
        armada_address = Consul.get_local_armada_address()
        url = 'http://{armada_address}/list'.format(**locals())
        all_services = requests.get(url).json()['result']
        service_to_addresses = defaultdict(list)
        working_services = [service for service in all_services if service['status'] in ('passing', 'warning')]
        for service in working_services:
            service_index = (service['name'], service['tags'].get('env'), service['tags'].get('app_id'))
            service_to_addresses[service_index].append(service['address'])
        return service_to_addresses
