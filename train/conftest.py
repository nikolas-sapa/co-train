"""Pytest options for TEST_ONLY controller guard mutations."""


def pytest_addoption(parser):
    parser.addoption("--controller-mutant", default=None, help="TEST_ONLY intended controller guard bypass")
