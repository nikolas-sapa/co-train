"""In-memory wrong-result control. Never edits product or spike source."""
import json
from pathlib import Path

from ptc.harness import Catalog
from ptc.sql_arms import ArmPair

original = ArmPair.catalog
hits = 0


def pytest_addoption(parser):
    parser.addoption("--bird-control-receipt", required=True)


def pytest_runtest_setup(item):
    def broken_catalog(self, observe=None):
        catalog = original(self, observe)
        tools = dict(catalog.tools)

        def wrong_execute_sql(*, query):
            global hits
            hits += 1
            return [{"total": -777}]

        tools["execute_sql"] = wrong_execute_sql
        return Catalog(tools=tools)

    ArmPair.catalog = broken_catalog


def pytest_sessionfinish(session, exitstatus):
    ArmPair.catalog = original
    path = Path(session.config.getoption("--bird-control-receipt"))
    if not path.is_absolute():
        raise ValueError("control receipt path must be absolute")
    with path.open("x") as handle:
        json.dump({"hits": hits, "pytest_exit": int(exitstatus)}, handle)
