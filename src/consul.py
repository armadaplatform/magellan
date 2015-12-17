from __future__ import print_function
from collections import defaultdict
import sys

import requests

sys.path.append('/opt/microservice/src')
import common.consul


class Consul(object):
    @staticmethod
    def get_local_armada_address():
        local_services_dict = common.consul.consul_query('agent/services')
        ship_ip = common.consul._get_ship_ip()
        for service in local_services_dict.values():
            if service['Service'] == 'armada':
                return '{}:{}'.format(ship_ip, service['Port'])
        raise Exception('Could not find local Armada agent.')

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
