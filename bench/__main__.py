"""`python -m bench <bird-root> [spider-root]` -- the shape inventory and power report.

Separate from `bench/suite.py` because `bench/__init__.py` imports `bench.suite` for its
re-exports, so running `python -m bench.suite` makes runpy execute a module that is
already in `sys.modules` and warn about it. One file removes the warning without giving
up either the package API or the entry point.
"""

import sys

from bench.suite import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
