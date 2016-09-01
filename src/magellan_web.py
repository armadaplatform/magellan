import os
import traceback
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


class Update(object):
    def GET(self):
        try:
            magellan.update()
            return 'ok'
        except:
            traceback.print_exc()
            return 'Error'


def main():
    urls = (
        '/health', Health.__name__,
        '/', ShowMapping.__name__,
        '/update', Update.__name__,
    )
    app = web.application(urls, globals())
    app.run()


if __name__ == '__main__':
    main()
