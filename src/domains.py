from hermes import get_configs


def get_domains_to_services():
    result = {}
    domains_configs = get_configs('.')
    for config_name, domains in domains_configs.items():
        if config_name.startswith('domains-') and config_name.endswith('.json'):
            result.update(domains)
    return result
