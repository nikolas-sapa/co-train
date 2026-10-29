"""CLI option counts are framing, not different SQLite failures."""

import pytest

from ptc.sql_diff import _sqlite_message


@pytest.mark.parametrize("ordinal", ["1st", "2nd", "3rd", "5th", "6th", "11th", "23rd"])
@pytest.mark.parametrize("message", [
    "no such table: missing",
    "no such column: source:field",
])
def test_cli_argument_position_preserves_the_sqlite_message(ordinal, message):
    detail = f"Parse error in {ordinal} command line argument: {message}"
    assert _sqlite_message(detail) == message


def test_error_framing_does_not_hide_different_database_errors():
    first = "no such table: first_table"
    second = "no such table: second_table"
    assert _sqlite_message(first) == first
    assert _sqlite_message(second) == second
    assert _sqlite_message(f"Parse error in 6th command line argument: {first}") != (
        _sqlite_message(f"Parse error in 6th command line argument: {second}"))
