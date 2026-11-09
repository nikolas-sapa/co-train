"""V301 seven new allocation/guard cases, not GPU or throughput evidence."""
import asyncio

import pytest

from train import test_qualification_ac_valid_output as valid

base = valid.base
api, adapter = base.api, base.adapter
case, owner = base.case, base.owner
prohibit_real_effects = base.prohibit_real_effects


def instrument_constructions(monkeypatch):
    counts = dict(assertions=0, constructions=0, depth=0)
    actual_assert = api.IsolatedOwner._assert_parent_read_lease
    actual_observation = api.ChildObservation

    def assertion(self, *args, **kwargs):
        counts["assertions"] += 1
        counts["depth"] += 1
        try:
            return actual_assert(self, *args, **kwargs)
        finally:
            counts["depth"] -= 1

    def observation(*args, **kwargs):
        if counts["depth"]:
            counts["constructions"] += 1
        return actual_observation(*args, **kwargs)

    monkeypatch.setattr(api.IsolatedOwner, "_assert_parent_read_lease", assertion)
    monkeypatch.setattr(api, "ChildObservation", observation)
    return counts


def run_with_hook(c, o, monkeypatch, hook):
    primary = None
    try:
        audit = valid._install_fixture(c, o, monkeypatch)
        actual_validate = adapter._ParentValidator.validate
        calls = []

        async def validate(validator, lease):
            calls.append(lease)
            await hook(lease)
            return await actual_validate(validator, lease)

        monkeypatch.setattr(adapter._ParentValidator, "validate", validate)
        execution = asyncio.run(o.run_once())
        assert len(calls) == 1 and calls[0] is o._lease
        valid._assert_one_attempt(audit)
        valid._assert_inventory(audit)
        assert len(audit.opened) == 8 and len(audit.identities) == 24
        assert all(reader._file.record.closed for _, reader in audit.opened)
        result = adapter.validate_joined_outcome(
            c.request, owner=o, prepared=audit.prepared,
            execution=execution, export_root=c.export)
        assert result.original_outcome is audit.originals[0]
        assert result.local_containment == "JOINED"
        with pytest.raises(ValueError, match="one-use sealed original"):
            o.take_validated_original(
                request=c.request, prepared=audit.prepared,
                execution=execution, export_root=c.export)
        assert len(audit.published) == 1 and len(audit.takes) == 2
    except BaseException as error:
        primary = error
        raise
    finally:
        if not o._running:
            valid._release(o, primary)
    assert all(record.closed or record.handle is None for record in o._registry.records)


def test_active_lease_does_not_reconstruct_expected_proof(case, owner, monkeypatch):
    counts = instrument_constructions(monkeypatch)

    async def hook(lease):
        lease._check()

    run_with_hook(case, owner, monkeypatch, hook)
    assert counts["assertions"] > 0
    assert counts["constructions"] == 0, "active lease reconstructs expected ChildObservation"


def test_1000_lease_checks_keep_all_independent_monitors(case, owner, monkeypatch):
    counts = instrument_constructions(monkeypatch)
    observed = {}

    async def hook(lease):
        actual_live = owner._independent_live
        tallies = dict(live=0, controller_observe=0, gate_observe=0,
                       controller_channel=0, gate_channel=0)
        measuring = [False]

        def live():
            if measuring[0]:
                tallies["live"] += 1
            return actual_live()

        monkeypatch.setattr(owner, "_independent_live", live)
        for role in ("controller", "gate"):
            child, channel = owner._children[role], owner._channels[role]
            actual_observe, actual_channel = child.observe, channel.check_live

            def observe(method=actual_observe, key=role + "_observe"):
                if measuring[0]:
                    tallies[key] += 1
                return method()

            def channel_live(method=actual_channel, key=role + "_channel"):
                if measuring[0]:
                    tallies[key] += 1
                return method()

            monkeypatch.setattr(child, "observe", observe)
            monkeypatch.setattr(channel, "check_live", channel_live)
        before = counts["constructions"]
        measuring[0] = True
        try:
            for _ in range(1000):
                lease._check()
        finally:
            measuring[0] = False
        observed.update(tallies)
        observed["constructions"] = counts["constructions"] - before

    run_with_hook(case, owner, monkeypatch, hook)
    assert {key: value for key, value in observed.items() if key != "constructions"} == dict(
        live=1000, controller_observe=1000, gate_observe=1000,
        controller_channel=1000, gate_channel=1000)
    assert observed["constructions"] == 0, "active lease reconstructs expected ChildObservation"


@pytest.mark.parametrize("fault", ("missing", "wrong-role", "nonzero", "extra-child", "unobserved"))
def test_worker_proof_mutation_still_refuses(case, owner, monkeypatch, fault):
    rejected = []

    async def hook(lease):
        actual = owner._worker_execution
        saved = actual.children
        child = base.dto.ChildObservation("worker", 0, True)
        if fault == "missing":
            changed = ()
        elif fault == "wrong-role":
            changed = (base.dto.ChildObservation("controller", 0, True),)
        elif fault == "nonzero":
            changed = (base.dto.ChildObservation("worker", 1, True),)
        elif fault == "extra-child":
            changed = (child, base.dto.ChildObservation("controller", 0, True))
        else:
            # Deliberately invalid owned synthetic proof data. Never used to
            # obtain authority; original active-lease predicate MUST refuse it.
            object.__setattr__(child, "actual_reap_observed", False)
            changed = (child,)
        object.__setattr__(actual, "children", changed)
        try:
            with pytest.raises(ValueError, match="actual matching worker-only proof"):
                lease._check()
            rejected.append(fault)
        finally:
            object.__setattr__(actual, "children", saved)
        lease._check()  # Restored actual proof still passes unchanged predicates.

    run_with_hook(case, owner, monkeypatch, hook)
    assert rejected == [fault]
