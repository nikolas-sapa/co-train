"""Connection-local SQLite file-access guard, shared by actions and scoring.

Callers must open the main database read-only before installing this guard. It
does not make a writable main database read-only, sandbox the OS or bash shell,
or prohibit SQLite's ordinary temporary-file IO.
"""

from __future__ import annotations

import sqlite3


class SQLiteSafetyError(RuntimeError):
    """Required SQLite protections could not be installed, not a query error."""


_BLOCKED_FUNCTIONS = frozenset({"writefile", "edit", "load_extension", "readfile"})


def protect_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Install the authorizer and return conn, or close once and fail closed."""
    try:
        attach, function, deny, ok = (
            getattr(sqlite3, name)
            for name in ("SQLITE_ATTACH", "SQLITE_FUNCTION", "SQLITE_DENY", "SQLITE_OK")
        )
        if not all(isinstance(value, int) for value in (attach, function, deny, ok)):
            raise RuntimeError("required SQLite authorizer constants are unavailable")
        set_authorizer = getattr(conn, "set_authorizer")
        if not callable(set_authorizer):
            raise RuntimeError("SQLite set_authorizer is unavailable")

        def authorizer(action, arg1, arg2, database, trigger):
            if action == attach:
                return deny
            if action == function and (arg2 or "").casefold() in _BLOCKED_FUNCTIONS:
                return deny
            return ok

        set_authorizer(authorizer)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            # Preserve the installation failure as the cause even if close fails.
            pass
        raise SQLiteSafetyError("could not install SQLite file-access guard") from exc
    return conn
