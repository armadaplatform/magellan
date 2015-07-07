import json
import os

import web

import magellan


class Health(object):
    def GET(self):
        return 'ok'


class ShowMapping(object):
    def GET(self):
        if os.path.exists(magellan.DOMAIN_TO_ADDRESSES_PATH):
            with open(magellan.DOMAIN_TO_ADDRESSES_PATH) as f:
                return f.read()
        return 'WARNING: magellan is not configured.'


def main():
    urls = (
        '/health', Health.__name__,
        '/', ShowMapping.__name__,
    )
    app = web.application(urls, globals())
    app.run()


if __name__ == '__main__':
    main()
