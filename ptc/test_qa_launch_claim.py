"""One-shot reporting-channel launch ownership (spec/qa-launch-claim.md).

`test_harness_qa.py` proved the per-harness-instance reuse guard: a live
channel cannot be claimed twice by concurrent launches on ONE harness. That
guard is a `WeakSet` on the instance -- it cannot see a second harness. This
file covers the cross-instance half: `QaChannel._claim_launch` is a one-shot
flag that lives on the channel itself, so a spent channel stays spent for its
whole lifetime no matter which harness instance asks for it next.

Everything goes through the real `PTCHarness.launch` against the scripted SSE
policy from `test_harness.py`, plus direct `QaChannel` calls for the flag's
own contract -- no model endpoint, no server, no MCP discovery beyond a faked
`_mcp_catalog`, and threads only inside the one bounded contention test.

`test_cross_instance_reuse_refused_before_actions` is the spec's control
target: mutating `_claim_launch` into a no-op must turn it red, because it
asserts the refusal through a real second launch on a real second harness,
not through a stand-in. The disabled-path child import/copy/pickle and
weak-tracking tests stay in `test_harness_qa.py`, unchanged.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers.v1.task import TaskData  # noqa: E402

from ptc.sql_arms import build_probe_db, sql_catalog  # noqa: E402
from ptc.sql_qa import (  # noqa: E402
    MAX_REPORTS_PER_ARM,
    QaChannel,
    ReportRejected,
)
from ptc.test_harness import Policy, _assistant  # noqa: E402
from ptc.test_harness_qa import (  # noqa: E402
    _harness,
    _launch,
    _report_events,
)


def test_first_claim_returns_none_later_claims_refuse():
    """The one-shot contract in isolation: `_claim_launch` returns None the
    first time and raises a neutral ValueError on every later call. Resolved
    as an attribute on a real channel so a missing API fails here outright
    rather than skipping."""
    channel = QaChannel()
    claim = channel._claim_launch
    assert claim() is None
    with pytest.raises(ValueError):
        claim()
    with pytest.raises(ValueError):
        claim()


def test_claim_contention_has_exactly_one_winner():
    """12 threads released together onto ONE channel: exactly one claim
    succeeds, eleven are refused with ValueError, every worker's outcome is
    captured per thread (an unexpected exception type is a failure, not a
    silent winner) and the whole join completes inside the 5s bound."""
    channel = QaChannel()
    workers = 12
    barrier = threading.Barrier(workers)
    pending = object()
    outcomes = [pending] * workers

    def worker(index):
        try:
            barrier.wait(timeout=5.0)
            outcomes[index] = channel._claim_launch()
        except BaseException as exc:
            outcomes[index] = exc

    start = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(workers)]
    for thread in threads:
        thread.start()
    deadline = start + 5.0
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    elapsed = time.monotonic() - start

    assert elapsed < 5.0
    assert not any(thread.is_alive() for thread in threads), (
        "a claiming worker never returned")
    assert not any(outcome is pending for outcome in outcomes), (
        "a worker thread died without recording an outcome")

    wins = [o for o in outcomes if o is None]
    refused = [o for o in outcomes if isinstance(o, ValueError)]
    unexpected = [o for o in outcomes
                  if o is not None and not isinstance(o, ValueError)]
    assert unexpected == []
    assert len(wins) == 1
    assert len(refused) == workers - 1


def test_claim_leaves_collector_state_byte_identical():
    """Claiming is ownership, not data: export bytes, shortcut IDs and the
    stored events are identical before and after a claim and a refused
    re-claim, and the report quota still bites at exactly the arm cap."""
    channel = QaChannel(shortcut_ids=("fixture_shortcut",))
    channel.submit("ptc", kind="other", detail="filed before the claim")
    channel.record_shortcut(
        "ptc", "fixture_shortcut", provenance="fixture")
    export_before = channel.export()
    events_before = channel.events
    ids_before = channel.shortcut_ids

    assert channel._claim_launch() is None
    export_after_claim = channel.export()
    with pytest.raises(ValueError):
        channel._claim_launch()
    export_after_refusal = channel.export()

    assert export_after_claim == export_before
    assert export_after_refusal == export_before
    assert channel.events == events_before
    assert channel.shortcut_ids == ids_before

    # Quota behaviour unchanged: the pre-claim report plus the cap minus one
    # fill the arm exactly, and the next submission is still refused.
    for i in range(MAX_REPORTS_PER_ARM - 1):
        channel.submit("ptc", kind="other", detail=f"after claim {i}")
    with pytest.raises(ReportRejected):
        channel.submit("ptc", kind="other", detail="one too many")


def test_cross_instance_reuse_refused_before_actions(tmp_path):
    """The control case. One caller-retained channel serves a complete first
    launch on one harness; a SECOND, distinct harness instance handed the same
    channel by its factory must refuse the launch before it issues any model
    request -- even though the first launch already completed. The per-instance
    weakref guard cannot see across harnesses, so this goes red the moment
    `_claim_launch` stops refusing a spent channel."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    shared = QaChannel()

    policy_a = Policy(_assistant("print(1)"), _assistant(None))
    harness_a = _harness(
        policy_a, sql_catalog(str(db)), qa_factory=lambda data: shared)
    result_a = asyncio.run(_launch(harness_a, TaskData(prompt="first")))
    assert result_a.exit_code == 0
    requests_after_first = len(policy_a.requests)
    assert requests_after_first >= 1

    policy_b = Policy(_assistant("print(2)"), _assistant(None))
    harness_b = _harness(
        policy_b, sql_catalog(str(db)), qa_factory=lambda data: shared)
    assert harness_b is not harness_a

    with pytest.raises(ValueError):
        asyncio.run(_launch(harness_b, TaskData(prompt="second")))

    # Refused before the wire: the new instance made no request of its own and
    # the completed launch's request count did not grow either.
    assert len(policy_b.requests) == 0
    assert len(policy_a.requests) == requests_after_first


def test_fresh_channels_on_two_instances_isolated(tmp_path):
    """The other half of the ownership rule: two harness instances each given
    a FRESH channel both launch successfully, and each channel records only
    its own launch's report -- zero cross-channel events."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    channel_a, channel_b = QaChannel(), QaChannel()
    policy_a = Policy(
        _assistant('print(report_defect(kind="other", detail="from_a"))'),
        _assistant(None))
    policy_b = Policy(
        _assistant('print(report_defect(kind="other", detail="from_b"))'),
        _assistant(None))
    harness_a = _harness(
        policy_a, sql_catalog(str(db)), qa_factory=lambda data: channel_a)
    harness_b = _harness(
        policy_b, sql_catalog(str(db)), qa_factory=lambda data: channel_b)

    result_a = asyncio.run(_launch(harness_a, TaskData(prompt="a")))
    result_b = asyncio.run(_launch(harness_b, TaskData(prompt="b")))
    assert result_a.exit_code == 0
    assert result_b.exit_code == 0

    reports_a = _report_events(channel_a)
    reports_b = _report_events(channel_b)
    assert [e["detail"] for e in reports_a] == ["from_a"]
    assert [e["detail"] for e in reports_b] == ["from_b"]


def test_setup_failure_spends_the_channel_across_instances(tmp_path,
                                                           monkeypatch):
    """A launch that fails AFTER claiming still spends the channel. MCP
    discovery is faked to blow up mid-setup: the first launch dies with the
    injected error, a second harness instance retrying with the same channel
    is refused before any request, and a fresh channel on a third instance is
    completely unaffected."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    shared = QaChannel()

    class SetupBoom(RuntimeError):
        pass

    async def boom_catalog():
        raise SetupBoom("setup failed after the claim")

    monkeypatch.setattr(
        "ptc.harness._mcp_catalog",
        lambda urls, stack, timeout: boom_catalog())

    policy_a = Policy(_assistant(None))
    harness_a = _harness(
        policy_a, sql_catalog(str(db)), qa_factory=lambda data: shared)
    with pytest.raises(SetupBoom):
        asyncio.run(_launch(
            harness_a, TaskData(prompt="setup fails"),
            mcp_urls={"srv": "http://mcp.invalid"}))
    assert len(policy_a.requests) == 0

    # The claim persisted through the failure: a different harness instance
    # cannot take the spent channel over, before a single request.
    policy_b = Policy(_assistant(None))
    harness_b = _harness(
        policy_b, sql_catalog(str(db)), qa_factory=lambda data: shared)
    with pytest.raises(ValueError):
        asyncio.run(_launch(harness_b, TaskData(prompt="retry")))
    assert len(policy_b.requests) == 0

    # A fresh channel on another instance is unaffected by the spent one.
    fresh = QaChannel()
    policy_c = Policy(_assistant("print(1)"), _assistant(None))
    harness_c = _harness(
        policy_c, sql_catalog(str(db)), qa_factory=lambda data: fresh)
    result_c = asyncio.run(_launch(harness_c, TaskData(prompt="fresh")))
    assert result_c.exit_code == 0
    assert len(policy_c.requests) >= 1
