"""V311 six new armed-role allocation/live-fact regressions, not throughput proof."""
import dis

import pytest

from train import test_qualification_lease_performance as perf

api = perf.api
case, owner = perf.case, perf.owner
prohibit_real_effects = perf.prohibit_real_effects


def monitor_counts(o, monkeypatch):
    counts = dict(monitor=0, controller_observe=0, gate_observe=0,
                  controller_channel=0, gate_channel=0)
    measuring = [True]
    actual_monitor = o._monitor_armed

    def monitor():
        if measuring[0]:
            counts["monitor"] += 1
        return actual_monitor()

    monkeypatch.setattr(o, "_monitor_armed", monitor)
    for role in ("controller", "gate"):
        child, channel = o._children[role], o._channels[role]
        actual_observe, actual_channel = child.observe, channel.check_live

        def observe(method=actual_observe, key=role + "_observe"):
            if measuring[0]:
                counts[key] += 1
            return method()

        def channel_live(method=actual_channel, key=role + "_channel"):
            if measuring[0]:
                counts[key] += 1
            return method()

        monkeypatch.setattr(child, "observe", observe)
        monkeypatch.setattr(channel, "check_live", channel_live)
    return counts, measuring


def test_active_independent_check_has_no_expected_set_allocation(case, owner, monkeypatch):
    async def hook(lease):
        lease._check()
        assert not any(item.opname == "BUILD_SET" for item in
                       dis.get_instructions(api.IsolatedOwner._independent_live)), (
            "active independent-live reconstructs armed-role set")
        assert type(api._ARMED_ROLE_NAMES) is frozenset
        assert api._ARMED_ROLE_NAMES == frozenset(("controller", "gate"))

    perf.run_with_hook(case, owner, monkeypatch, hook)


def test_1000_checks_preserve_every_monitor_and_role_observation(case, owner, monkeypatch):
    observed = {}

    async def hook(lease):
        counts, measuring = monitor_counts(owner, monkeypatch)
        try:
            for _ in range(1000):
                lease._check()
        finally:
            measuring[0] = False
        observed.update(counts)

    perf.run_with_hook(case, owner, monkeypatch, hook)
    assert observed == dict(monitor=1000, controller_observe=1000, gate_observe=1000,
                            controller_channel=1000, gate_channel=1000)


def test_armed_mutation_between_checks_refuses_immediately(case, owner, monkeypatch):
    observed = {}

    async def hook(lease):
        counts, measuring = monitor_counts(owner, monkeypatch)
        try:
            lease._check()
            saved = owner._armed.copy()
            owner._armed.remove("gate")
            try:
                with pytest.raises(ValueError, match="both actual ARM acknowledgements"):
                    lease._check()
            finally:
                owner._armed.clear()
                owner._armed.update(saved)
            lease._check()
        finally:
            measuring[0] = False
        observed.update(counts)

    perf.run_with_hook(case, owner, monkeypatch, hook)
    assert observed == dict(monitor=2, controller_observe=2, gate_observe=2,
                            controller_channel=2, gate_channel=2)


@pytest.mark.parametrize("fault", ("missing-controller", "missing-gate", "extra-role"))
def test_exact_armed_membership_still_refuses(case, owner, monkeypatch, fault):
    rejected = []

    async def hook(lease):
        saved = owner._armed.copy()
        if fault == "extra-role":
            owner._armed.add("worker")
        else:
            owner._armed.remove(fault.removeprefix("missing-"))
        try:
            with pytest.raises(ValueError, match="both actual ARM acknowledgements"):
                lease._check()
            rejected.append(fault)
        finally:
            owner._armed.clear()
            owner._armed.update(saved)
        lease._check()

    perf.run_with_hook(case, owner, monkeypatch, hook)
    assert rejected == [fault]
