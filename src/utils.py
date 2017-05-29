from __future__ import print_function

import logging
import sys

from armada import hermes
from raven import Client, setup_logging
from raven.handlers.logging import SentryHandler

sentry_ignore_exceptions = ['KeyboardInterrupt']


def print_err(*objs):
    print(*objs, file=sys.stderr)


def setup_sentry():
    sentry_url = hermes.get_config('config.json').get('sentry_url', '')

    sentry_client = Client(sentry_url,
                           auto_log_stacks=True,
                           ignore_exceptions=sentry_ignore_exceptions,
                           )

    handler = SentryHandler(sentry_client, level=logging.WARNING)
    setup_logging(handler)

    return sentry_client
