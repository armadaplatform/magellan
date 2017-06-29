from __future__ import print_function

import json
import logging
import os
import re
import time
import traceback

import requests
from armada import hermes

import consul
import domains
import haproxy
from utils import print_err, setup_sentry

WILDCARD_PATTERN = '%(?P<variable>[^%]+)%'
NAMED_WILDCARD_PATTERN = '(?P<\\g<variable>>[A-Za-z_][A-Za-z_\-0-9\.]+)'
DOMAIN_PATTERN = '^[\w\-\./]+$'
DOMAIN_TO_ADDRESSES_PATH = '/tmp/domain_to_addresses.json'
TIMEOUT = '10s'
MINIMAL_INTERVAL = 1


def create_named_pattern_for_wildcard(wildcard):
    if not wildcard:
        return None
    return re.sub(WILDCARD_PATTERN, NAMED_WILDCARD_PATTERN, wildcard)


def get_matching_main_haproxies(env):
    armada_address = consul.Consul.get_local_armada_address()
    url = 'http://{armada_address}/list?microservice_name=main-haproxy'.format(**locals())
    main_haproxies = requests.get(url).json()['result']
    for main_haproxy in main_haproxies:
        if main_haproxy['tags'].get('env') == env and main_haproxy['tags'].get('app_id') is None:
            yield main_haproxy


def get_load_balancers():
    load_balancer_configs = hermes.get_config('load-balancers.json')
    if not load_balancer_configs:
        load_balancer_configs = [{
            'type': 'main-haproxy',
            'env': os.environ.get('MICROSERVICE_ENV'),
        }]
    for load_balancer_config in load_balancer_configs:
        load_balancer_type = load_balancer_config['type']
        if load_balancer_type == 'haproxy':
            load_balancer = haproxy.Haproxy(load_balancer_config)
            yield load_balancer
        elif load_balancer_type == 'main-haproxy':
            main_haproxies = get_matching_main_haproxies(load_balancer_config.get('env'))
            for main_haproxy in main_haproxies:
                load_balancer_config.update(main_haproxy)
                load_balancer = haproxy.MainHaproxy(load_balancer_config)
                yield load_balancer
        else:
            print_err("Unknown load-balancer type: {load_balancer_type}".format(**locals()))


def match_domains_to_services(domain_wildcard, name, env, app_id, service_to_addresses):
    result = {}
    service_index = (name, env, app_id)

    service_index_pattern = [create_named_pattern_for_wildcard(wildcard) for wildcard in service_index]
    if any(named_pattern and '%' in named_pattern for named_pattern in service_index_pattern):
        print_err('Invalid wildcard in {service_index}'.format(**locals()))
        return result
    for service, addresses in service_to_addresses.items():
        replacements = {}
        matched = True
        for i, named_pattern in enumerate(service_index_pattern):
            if not named_pattern and not service[i]:
                continue
            if not named_pattern or not service[i]:
                matched = False
                break
            match = re.match('^' + named_pattern + '$', service[i])
            if not match:
                matched = False
                break
            replacements.update(match.groupdict())
        if matched:
            domain = str(domain_wildcard)
            for pattern_name, replacement in replacements.items():
                domain = domain.replace('%{0}%'.format(pattern_name), replacement)
            if not re.match(DOMAIN_PATTERN, domain):
                print_err('Invalid domain: {domain}'.format(**locals()))
                continue
            result[domain] = addresses
    return result


def match_domains_to_address(domain_wildcard, address):
    result = {domain_wildcard: {'0': address}}
    return result


def match_domains_to_addresses(domains_to_services, service_to_addresses):
    result = {}
    for domain_wildcard, service_definition in domains_to_services.items():
        if service_definition.get('protocol') != 'http':
            continue
        address = service_definition.get('address')
        allow_all = service_definition.get('allow_all') is True
        if address:
            mapping = match_domains_to_address(domain_wildcard, address)
        else:
            name = service_definition['service_name']
            env = service_definition.get('environment')
            app_id = service_definition.get('app_id')
            mapping = match_domains_to_services(domain_wildcard, name, env, app_id, service_to_addresses)
        for domain, addresses in mapping.items():
            mapping[domain] = {
                'addresses': addresses,
                'allow_all': allow_all,
            }
        result.update(mapping)

    return result


def main():
    sentry_client = setup_sentry()
    logging.basicConfig(level=logging.WARNING)
    x_consul_index = 0
    while True:

        x_consul_index = consul.Consul.watch_for_health_checks(x_consul_index, TIMEOUT)
        try:
            domains_to_services = domains.get_domains_to_services()
            logging.info('domains_to_services: {}'.format(json.dumps(domains_to_services, indent=4)))
            service_to_addresses = consul.Consul.discover()
            logging.info('service_to_addresses: {}'.format(
                json.dumps({str(k): v for k, v in service_to_addresses.items()}, indent=4)))
            domain_to_addresses = match_domains_to_addresses(domains_to_services, service_to_addresses)
            logging.info('domain_to_addresses: {}'.format(json.dumps(domain_to_addresses, indent=4)))
            if domain_to_addresses:
                with open(DOMAIN_TO_ADDRESSES_PATH, 'w') as f:
                    json.dump(domain_to_addresses, f, indent=4, sort_keys=True)
                for load_balancer in get_load_balancers():
                    load_balancer.update(domain_to_addresses)
        except:
            sentry_client.captureException()
            traceback.print_exc()

        time.sleep(MINIMAL_INTERVAL)


if __name__ == '__main__':
    main()
