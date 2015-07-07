from __future__ import print_function
import sys


def print_err(*objs):
    print(*objs, file=sys.stderr)
