"""Shared-composition seam, deliberately not a runnable product plugin."""

from verifiers.v1.runtimes import Runtime

from ptc.sql_owned_bash import BashSqlBinding, BashSqlError, public_bash_prompt

__all__ = [
    "bind_bash_sql_leaf", "public_bash_prompt", "require_production_bash_runtime",
]


def bind_bash_sql_leaf(*, schema: str, **binding) -> BashSqlBinding:
    return BashSqlBinding(schema=schema, **binding)


def require_production_bash_runtime(runtime: Runtime | None) -> None:
    # No existing concrete runtime owns and qualifies the complete Bash path.
    # Accepting an interface, flag or profile digest would invent that authority.
    raise BashSqlError(
        "externally qualified full-shell runtime and shared Env hook required; "
        "SQL-only diagnostics are not the original Bash baseline")
