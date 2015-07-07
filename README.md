# magellan

`magellan` is a service for configuring load-balancers to redirect net traffic to microservices that run
in the Armada cluster.
Right now it supports only HTTP redirects through HAProxy configuration. It is recommended to run it alongside
`main-haproxy` service(s) and let `magellan` configure them.


# Building and running the service.

    armada build magellan
    armada run magellan

`magellan` is configured using Hermes.
It reads list of domain --> service mappings from all files `domains-*.json`. They should be in json format
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
        }
    }

* Dictionary key - Name of the domain/URL that will be redirected.
* Dictionary value - Information about desired target microservice.
    * `protocol` - Protocol used by microservice. Currently only `http` is supported.
    * `service_name`, `environment`, `app_id` - Name (required), environment (optional) and app_id (optional) of the target microservice.

        If environment/app_id is not supplied, `magellan` will look only for services with no environment/app_id set.


Here, requests to two domains (`badguys.initech.com` and `www.badguys.initech.com`) will be redirected to the main endpoint
of service `badguys-finder` run with environment `production-office`.

## Wildcards.

In case you have a set of similiar services that differ by environment or app_id you can use wildcards to configure them,
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


# API

Magellan provides single HTTP endpoint at its root URL (`/`).
It returns JSON object with the list of all current mappings it is using to configure HAProxies.



# Additional information.

`magellan` constantly monitors which services are running in the Armada cluster. It tries to reconfigure HAProxies as
soon as possible to reflect any changes in services state. When an instance of the service is stopped
or enters `critical` state, it is automatically removed from HAProxy configuration.


Some more explanations about using `magellan` can be found at one of Armada
[guides](http://armada.sh/doc/guide-new-service-service-discovery.html).
