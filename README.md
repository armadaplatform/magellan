# magellan

`magellan` is a service for configuring load-balancers to redirect net traffic to given addresses or microservices
that run in the Armada cluster.
Right now it supports only HTTP redirects through HAProxy configuration. It is recommended to run it alongside
`main-haproxy` service(s) and let `magellan` configure them.


# Building and running the service.

    armada build magellan
    armada run magellan

`magellan` is configured using Hermes.
It reads list of domain --> service/address mappings from all files `domains-*.json`. They should be in json format
and contain list of json objects like the one below:

    {
        "badguys.initech.com": {
            "protocol": "http",
            "service_name": "badguys-finder",
            "environment": "production-office"
        },
        "www.badguys.initech.com": {
            "protocol": "http",
            "service_name": "badguys-finder",
            "environment": "production-office"
        },
        "dashboard.initech.com": {
            "protocol": "http",
            "address": "server2.internal-initech.com:8080"
        }
    }

* Dictionary key - Name of the domain/URL that will be redirected.
* Dictionary value - Information about desired target microservice.
    * `protocol` - Protocol used by microservice. Currently only `http` is supported.
    * `service_name`, `environment`, `app_id` - Name (required), environment (optional) and app_id (optional) of the target microservice.

        If environment/app_id is not supplied, `magellan` will look only for services with no environment/app_id set.

    * `address` - Address to which the domain will be pointed to. If provided, it will override service_name/environment/app_id.

Here, requests to two domains (`badguys.initech.com` and `www.badguys.initech.com`) will be redirected to the main endpoint
of service `badguys-finder` run with environment `production-office`.

The third domain - `dashboard.initech.com` - will be redirected to `server2.internal-initech.com:8080`, which shows
that we can easily create pretty aliases for non-armada services too.
It can also be used for exposing services available only from internal networks (e.g. `internal-initech.com`) to
the public - `initech.com`.

## Wildcards.

In case you have a set of similar services that differ by environment or app_id you can use wildcards to configure them,
e.g.:

    {
        "translation.%GAME_NAME%.initech.com": {
            "protocol":"http",
            "app_id": "%GAME_NAME%",
            "environment": "production-office",
            "service_name": "translation-panel"
        }
    }

In the above example, when you run a service with `armada run translation-panel --env production-office --app_id chess`,
it will be available at the address `translation.chess.initech.com`.
You can use any variable name that match regular expression `[A-Za-z_][A-Za-z_\-0-9]+`,
just put it between the `%` characters.

It is also possible to redirect only certain path of the domain, so instead of `translation.%GAME_NAME%.initech.com`
you can also use something like `translation.initech.com/%GAME_NAME%`.

Wildcards do not work with `address` field.

## Choosing which load balancers to configure.

By default `magellan` will configure all `main-haproxy` services in its Armada cluster that have the same
environment set.
If you want to change that behaviour you can choose other load balancers by placing file `load-balancers.json` in the Hermes
configuration directory. It should contain a json array with list of HAProxies to configure. E.g.:

    [
        {
            "type": "main-haproxy",
            "env": "production-aws"
        },
        {
            "type": "haproxy",
            "ssh": {
                "host": "haproxy.initech.com",
                "port": 22,
                "user": "service",
                "ssh_key": "service@haproxy.initech.com.key"
            }
        }
    ]

You can ask `magellan` to configure either `main-haproxy` Armada service or pure HAProxy instance. In the latter case
providing proper SSH credentials to the server with HAProxy is required.

## Restricting access.

With `magellan` you can also restrict access to some domains, allowing the only for defined netmasks.

To do that, add section "restrictions" in `load-balancers.json` config file. E.g.:
```json
[
    {
        "type": "main-haproxy",
        "env": "production",
        "restrictions": [
            {
                "domain": ".secure.example.com",
                "allowed_request_ip": [
                    "192.168.3.0/24",
                    "57.58.59.60"
                ]
            },
            {
                "domain": ".lb.example.com",
                "allowed_X-Forwarded-For": [
                    "192.168.3.0/24",
                    "57.58.59.60"
                ]
            }
        ]
    }
]
```

It will restrict access to all hosts ending with ".secure.example.com", and allow access only for source IPs
(`src` ACL in HAProxy) in `allowed_request_ip` section: `["192.168.3.0/24", "57.58.59.60"]`.

When your domain, let's say ".lb.example.com", is behind another load-balancer, e.g. ELB, the source IP received by
HAProxy will be the load-balancer's IP, which may be useless. In that case, use `allowed_X-Forwarded-For` section. It
will match the IPs against the last IP in `X-Forwarded-For` HTTP header (`hdr_ip(X-Forwarded-For)` ACL in HAProxy),
which should be the client's IP.

You can also expose some of the domains behind the restricted domain, by adding `"allow_all": true` to domain
definition. E.g.:
```json
{
    "allowed.secure.example.com": {
        "protocol": "http",
        "service_name": "allowed",
        "environment": "production",
        "allow_all": true
    }
}
```

### Enabling HAProxy stats.

Additionally you can enable HAProxy html stats (see http://tecadmin.net/how-to-configure-haproxy-statics/). It will be
accessible as another endpoint in `main-haproxy`, registered in Armada catalog as `main-haproxy:stats` subservice.

To do that add section "stats" to load-balancer config, e.g.:

    [
        {
            "type": "main-haproxy",
            "env": "production-aws",
            "stats": {
                "enabled": true,
                "user": "admin",
                "password": "secret"
            }
        }
    ]

`user` and `password` fields are optional. The default are `root` / `armada`.

# API.

Magellan provides single HTTP endpoint at its root URL (`/`).
It returns JSON object with the list of all current mappings it is using to configure HAProxies.



# Additional information.

`magellan` constantly monitors which services are running in the Armada cluster. It tries to reconfigure HAProxies as
soon as possible to reflect any changes in services state. When an instance of the service is stopped
or enters `critical` state, it is automatically removed from HAProxy configuration.


Some more explanations about using `magellan` can be found at one of Armada
[guides](http://armada.sh/doc/guide-new-service-service-discovery.html).
