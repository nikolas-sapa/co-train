"""Runnable reference to the original pending-before-result scheduling probe."""

# PROVES: Original SDK Harness.score can fail while Task.score waits before a
# result; original Env cancels/joins that child through held public cleanup.
# Underlying guarded composition probe: 1 passed in 3.95s, 2026-11-01.
# SHORTCUT: Reuse the retained first-party probe and dynamically requested
# framework fixture, rather than copy code and diverge from its AST checks.
# MISSING: Actual owned controller, native ACK/SAFE, active-query cancellation,
# fast-completed-close/late-sibling race and independent writer-bypass proof.
from ptc.test_owned_sql_sdk_retirement import (
    framework,  # noqa: F401
    test_sdk_sibling_postbase_sees_pending_pre_result_score,  # noqa: F401
)
