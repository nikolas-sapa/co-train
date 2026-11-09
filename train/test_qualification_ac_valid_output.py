"""V278 owned-fixture A/C spike. SOURCEONLY UNRUN, parent review required.

PROVES, only if independently passed: real A reservation/lease/filesystem
custody, unchanged C metadata/hash/receipt checks, sealing and one-use
publication/release under the inherited synthetic lifecycle observations.
SHORTCUT: base supplies owned source/interpreter/SDK files, fake Popen,
waitpid/session/signal/channel observations and a fixture stager. No original
stager, interpreter, SDK or worker executes. Fixture phase PIDs 101/102 are data.
SHORTCUT: four b"{}" bulk files (8 bytes) satisfy structural receipt metadata,
not valid native observations, checkpoints or tensors.
MISSING: real SDK/provider/process/reap/native/science evidence, throughput
and public admission. Native/science remains 0/7; public refusal stays intact.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from types import SimpleNamespace

import pytest

from train import test_qualification_isolated_owner as base


# Explicit fixture exposure only. No old test functions enter this namespace.
case = base.case
owner = base.owner
prohibit_real_effects = base.prohibit_real_effects

api = base.api
adapter = base.adapter
program = base.program
native = base.native
original = program.original

_BULK_KEYS = (
    "checkpoint-1/native-observation.json",
    "checkpoint-1/trainer_state.json",
    "checkpoint-2/native-observation.json",
    "checkpoint-2/trainer_state.json",
)
_EVIDENCE_KEYS = (
    "attempt-latch.json",
    "attempt-observations.json",
    "verification.json",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _different_digest(value):
    return ("1" if value[0] == "0" else "0") + value[1:]


def _descriptor(key, raw):
    return dict(key=key, size=len(raw), sha256=_sha(raw))


def _fixture_documents(request, *, bad_checkpoint=False):
    """Data only. Never construct an original result, lease or execution proof."""
    binding = native._request_binding(request)
    attempt = original._attempt_id(binding, base.APP, base.SANDBOX)
    links = dict(
        request_sha256=binding, attempt_id=attempt,
        app_id=base.APP, sandbox_id=base.SANDBOX)
    bulk = {key: b"{}" for key in _BULK_KEYS}
    manifest = [_descriptor(key, bulk[key]) for key in _BULK_KEYS]
    phases = [
        dict(phase=1, pid=101, returncode=0),
        dict(phase=2, pid=102, returncode=0),
    ]
    checkpoints = [
        dict(
            checkpoint=f"checkpoint-{phase}",
            members=["native-observation.json", "trainer_state.json"],
            observation_sha256=_sha(bulk[f"checkpoint-{phase}/native-observation.json"]),
            trainer_state_sha256=_sha(bulk[f"checkpoint-{phase}/trainer_state.json"]),
        )
        for phase in (1, 2)
    ]
    if bad_checkpoint:
        # Change only the inner checkpoint digest. All enclosing descriptors
        # below are rebuilt from these actual, now deliberately invalid bytes.
        checkpoints[0]["observation_sha256"] = _different_digest(
            checkpoints[0]["observation_sha256"])
    receipt = dict(
        v=1, op="remote-verification-receipt",
        scope=original._REMOTE_VERIFICATION_SCOPE, **links,
        phase_observations=phases, phase_returncodes=[0, 0],
        checkpoints=checkpoints, artifact_bytes=8, manifest=manifest)
    evidence = {
        "attempt-latch.json": original._canonical_json(
            dict(v=1, op="native-attempt", **links)),
        "attempt-observations.json": original._canonical_json(
            dict(v=1, op="phase-observations", **links, observations=phases)),
        "verification.json": original._canonical_json(receipt),
    }
    assert tuple(sorted(original._EVIDENCE_KEYS)) == _EVIDENCE_KEYS
    evidence_manifest = [
        _descriptor(key, evidence[key]) for key in _EVIDENCE_KEYS]
    files = dict(bulk)
    files.update(("evidence/" + key, evidence[key]) for key in _EVIDENCE_KEYS)
    exports = [
        dict(name=key, path=key, size=len(files[key]), sha256=_sha(files[key]))
        for key in sorted(files)
    ]
    document = dict(
        attempt_id=attempt, app_id=base.APP, sandbox_id=base.SANDBOX,
        phase_returncodes=[0, 0], receipt_size=len(evidence["verification.json"]),
        receipt_sha256=_sha(evidence["verification.json"]),
        evidence_manifest=evidence_manifest, exports=exports)
    # Use the actual C wire encoder, not guessed JSON formatting. Original
    # evidence/latch/receipt bytes above use the original canonical encoder.
    outcome = program.canonical(document)
    return SimpleNamespace(
        binding=binding, attempt=attempt, files=files, manifest=manifest,
        evidence_manifest=evidence_manifest, document=document, outcome=outcome,
        receipt=receipt)


def _install_fixture(c, o, monkeypatch, *, fault=None):
    prepared, _ = base.register(c, o)
    # Capture BEFORE the inherited installer replaces this production method.
    real_validate = adapter._ParentValidator.validate
    events, born, channels = base.install_mocked_lifecycle(c, o, monkeypatch)
    monkeypatch.setattr(adapter._ParentValidator, "validate", real_validate)
    data = _fixture_documents(c.request, bad_checkpoint=fault == "checkpoint")
    for key, raw in data.files.items():
        base.put(c.export / key, raw)
    for key in ("checkpoint-1", "checkpoint-2", "evidence"):
        (c.export / key).chmod(0o700)
    audit = SimpleNamespace(
        prepared=prepared, data=data, events=events, born=born, channels=channels,
        allocations=[], frames=[], validators=[], validated=[], bodies=[],
        originals=[], receipt_calls=[], receipt_accepted=[], receipt_errors=[],
        export_attempts=[], opened=[], inventories=[], identities=[],
        identity_errors=[], close_boundaries=[], takes=[], published=[],
        mutations=[])

    # SHORTCUT: adapt the inherited synthetic allocator, which calls real A
    # allocation once and writes b"{}". Replace only its owned FD contents.
    fixture_allocate = o._allocate_worker

    def allocate():
        result = fixture_allocate()
        audit.allocations.append(result)
        fd = o._outcome.record.handle
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        assert os.write(fd, data.outcome) == len(data.outcome)
        os.lseek(fd, 0, os.SEEK_SET)
        return result

    monkeypatch.setattr(o, "_allocate_worker", allocate)
    fixture_channel = api._ParentChannel

    class FixtureOutcomeChannel(fixture_channel):
        """SHORTCUT: adapt only the inherited fake worker's OUTCOME data."""

        async def receive(self, *, allowed, end_ns):
            message = await super().receive(allowed=allowed, end_ns=end_ns)
            if message["kind"] != "OUTCOME":
                return message
            body = dict(size=len(data.outcome), sha256=_sha(data.outcome))
            if fault == "outcome_digest":
                body["sha256"] = _different_digest(body["sha256"])
            # This is a fixture substitution, not an observational wrapper.
            # Keep the closed frame and run its unchanged actual DTO validator.
            frame = dict(message, body=body)
            result = base.dto.validate_message(
                frame, session=o._session, seq=self._recv_seq, allowed=allowed)
            audit.frames.append(result)
            return result

    monkeypatch.setattr(api, "_ParentChannel", FixtureOutcomeChannel)

    # PROVES: observers below call the captured actual implementation once,
    # returning its exact result or propagating its exact exception.
    async def validate(validator, lease):
        audit.validators.append((validator, lease))
        result = await real_validate(validator, lease)
        audit.validated.append(result)
        return result

    monkeypatch.setattr(adapter._ParentValidator, "validate", validate)
    real_body = program._validate_outcome_lease

    async def body(*args, **kwargs):
        audit.bodies.append(kwargs["lease"])
        result = await real_body(*args, **kwargs)
        audit.originals.append(result)
        return result

    monkeypatch.setattr(program, "_validate_outcome_lease", body)
    real_receipt = original._validate_receipt

    def receipt(*args, **kwargs):
        audit.receipt_calls.append((args, kwargs))
        try:
            result = real_receipt(*args, **kwargs)
        except ValueError as error:
            audit.receipt_errors.append(error)
            raise
        audit.receipt_accepted.append(result)
        return result

    monkeypatch.setattr(original, "_validate_receipt", receipt)
    real_open_outcome = api.ParentReadLease.open_outcome
    real_open_export = api.ParentReadLease.open_export

    def open_outcome(lease):
        result = real_open_outcome(lease)
        audit.opened.append((None, result))
        return result

    def open_export(lease, key):
        audit.export_attempts.append((key, len(audit.receipt_accepted)))
        result = real_open_export(lease, key)
        audit.opened.append((key, result))
        return result

    monkeypatch.setattr(api.ParentReadLease, "open_outcome", open_outcome)
    monkeypatch.setattr(api.ParentReadLease, "open_export", open_export)
    real_inventory = api.ParentReadLease.export_inventory

    async def inventory(lease):
        result = await real_inventory(lease)
        audit.inventories.append(result)
        if fault == "late_identity" and len(audit.inventories) == 2:
            # SHORTCUT: inject only after the actual second inventory and all
            # eight hash/read closes, before C's unchanged final identity sweep.
            readers = tuple(lease._readers)
            assert len(readers) == 8
            assert all(reader._file.record.closed for reader in readers)
            target = next(reader for key, reader in audit.opened if key == _BULK_KEYS[0])
            audit.mutations.append(target)
            # Size drift guarantees identity drift without timestamp assumptions.
            base.put(c.export / _BULK_KEYS[0], b"{}!")
        return result

    monkeypatch.setattr(api.ParentReadLease, "export_inventory", inventory)
    real_identity = api.RegisteredReader.check_identity

    async def identity(reader):
        closed = reader._file.record.closed
        try:
            result = await real_identity(reader)
        except ValueError as error:
            audit.identity_errors.append((reader, closed, error))
            raise
        audit.identities.append((reader, closed))
        return result

    monkeypatch.setattr(api.RegisteredReader, "check_identity", identity)
    real_close_validation = o._close_validation

    def close_validation():
        result = real_close_validation()
        lease = o._lease
        records = tuple(
            record for record in o._registry.records
            if lease is not None and record.anchor is lease and record.handle is not None)
        audit.close_boundaries.append((
            o._validated, o._validation_closed,
            tuple(record.closed for record in records)))
        return result

    monkeypatch.setattr(o, "_close_validation", close_validation)
    real_take = o.take_validated_original

    def take(**kwargs):
        audit.takes.append(kwargs)
        result = real_take(**kwargs)
        audit.published.append(result)
        return result

    monkeypatch.setattr(o, "take_validated_original", take)
    return audit


def _assert_one_attempt(audit):
    assert len(audit.allocations) == len(audit.frames) == 1
    assert len(audit.validators) == len(audit.bodies) == 1
    assert [event[1] for event in audit.events if event[0] == "birth"] == [
        "worker", "controller", "gate"]
    assert sum(event[0] == "stage" for event in audit.events) == 1
    assert set(audit.born) == {"worker", "controller", "gate"}
    assert all(process.polls > 0 for process in audit.born.values())
    worker_commands = [kind for kind, _ in audit.channels["worker"].sent]
    assert worker_commands == ["OPEN", "CREATE"]
    for role in ("controller", "gate"):
        assert [kind for kind, _ in audit.channels[role].sent].count("ARM") == 1


def _assert_no_publication(o, audit):
    assert o._validated is None and o._execution is None
    assert o._published is False
    assert audit.validated == audit.originals == audit.published == audit.takes == []


def _assert_inventory(audit):
    expected = {
        (key, "file", len(raw)) for key, raw in audit.data.files.items()}
    expected.update(
        (key, "directory", 0) for key in ("checkpoint-1", "checkpoint-2", "evidence"))
    assert len(expected) == 10
    assert len(audit.inventories) == 2
    for entries in audit.inventories:
        assert len(entries) == 10
        assert {(entry.key, entry.kind, entry.size) for entry in entries} == expected


def _release(o, primary=None):
    # Actual C release, never a fixture substitute or registry/latch mutation.
    adapter._release(o, primary)
    assert o._released and not o._latch_held
    assert base.common._ACTIVE_HOST is None
    o._reservation_custody.require_released()


def test_actual_ac_valid_output_publishes_once_after_join_bookkeeping(case, owner, monkeypatch):
    audit = _install_fixture(case, owner, monkeypatch)
    assert type(owner._reservation) is base.authority.AttemptReservation
    assert base.authority._custody_for_reservation(
        owner._reservation) is owner._reservation_custody
    execution = asyncio.run(owner.run_once())
    _assert_one_attempt(audit)
    _assert_inventory(audit)
    outcome_facts = len(audit.data.outcome), _sha(audit.data.outcome)
    assert owner._outcome_facts == outcome_facts
    assert (execution.outcome_size, execution.outcome_sha256) == outcome_facts
    assert audit.frames[0]["body"] == dict(
        size=outcome_facts[0], sha256=outcome_facts[1])
    assert audit.receipt_errors == []
    assert len(audit.receipt_calls) == len(audit.receipt_accepted) == 1
    assert audit.receipt_accepted[0] == tuple(audit.data.manifest)
    bulk_opens = [(key, accepted) for key, accepted in audit.export_attempts if key in _BULK_KEYS]
    assert bulk_opens == [(key, 1) for key in _BULK_KEYS]
    readers = tuple(owner._lease._readers)
    assert len(readers) == len(audit.opened) == 8
    assert [key for key, _ in audit.opened] == [
        None, *("evidence/" + key for key in _EVIDENCE_KEYS), *_BULK_KEYS]
    assert all(
        reader._file.record.closed
        and reader._file.record.closed_ns < owner._booking.close_ns
        for reader in readers)
    assert len(audit.identities) == 24 and audit.identity_errors == []
    assert tuple(reader for reader, closed in audit.identities if closed) == readers
    before_seal, validation_closed, record_closes = audit.close_boundaries[0]
    assert before_seal is None and validation_closed
    assert record_closes and all(record_closes)
    assert len(audit.validated) == len(audit.originals) == 1
    assert owner._validated is audit.validated[0]
    assert owner._validated.original is audit.originals[0]
    assert owner._validation_closed and not owner._validation_close_late
    assert owner._execution is execution
    assert tuple(child.role for child in execution.children) == ("worker", "controller", "gate")
    assert all(child.actual_reap_observed and child.returncode == 0 for child in execution.children)
    assert all(
        child.code == 0 and child.record.closed and child.reaped_ns is not None
        for child in owner._children.values())
    assert all(record.closed or record.handle is None for record in owner._runtime_records)
    assert all(process.returncode == 0 for process in audit.born.values())
    assert audit.published == [] and owner._published is False

    result = adapter.validate_joined_outcome(
        case.request, owner=owner, prepared=audit.prepared,
        execution=execution, export_root=case.export)
    assert result.original_outcome is audit.originals[0]
    assert result.local_containment == "JOINED"
    assert len(audit.published) == 1 and audit.published[0] is result.original_outcome
    actual = result.original_outcome
    assert type(actual) is original.EngineeringRunOutcome
    assert (actual.attempt_id, actual.app_id, actual.sandbox_id, actual.phase_returncodes) == (
        audit.data.attempt, base.APP, base.SANDBOX, (0, 0))
    assert (actual.receipt_size, actual.receipt_sha256) == (
        audit.data.document["receipt_size"], audit.data.document["receipt_sha256"])
    assert actual.evidence_manifest == tuple(audit.data.evidence_manifest)
    assert [(entry.name, entry.path, entry.size, entry.sha256) for entry in actual.exports] == [
        (item["name"], case.export / item["name"], item["size"], item["sha256"])
        for item in audit.data.document["exports"]]
    with pytest.raises(ValueError, match="one-use sealed original"):
        owner.take_validated_original(
            request=case.request, prepared=audit.prepared,
            execution=execution, export_root=case.export)
    assert len(audit.takes) == 2 and len(audit.published) == 1
    _release(owner)


def test_actual_ac_export_byte_mutation_refuses_publication(case, owner, monkeypatch):
    audit = _install_fixture(case, owner, monkeypatch)
    target = _BULK_KEYS[0]
    assert audit.data.files[target] == b"{}"
    base.put(case.export / target, b"{]")  # One byte, same size, stale declared hash.
    with pytest.raises(ValueError, match="leased actual full hash/size differs") as caught:
        asyncio.run(owner.run_once())
    _assert_one_attempt(audit)
    _assert_no_publication(owner, audit)
    assert len(audit.receipt_calls) == len(audit.receipt_accepted) == 1
    assert audit.receipt_errors == []
    assert [(key, accepted) for key, accepted in audit.export_attempts if key in _BULK_KEYS] == [
        (target, 1)]
    assert all(reader._file.record.closed for reader in owner._lease._readers)
    _release(owner, caught.value)


def test_actual_ac_outcome_digest_mutation_refuses_publication(case, owner, monkeypatch):
    audit = _install_fixture(case, owner, monkeypatch, fault="outcome_digest")
    with pytest.raises(ValueError, match="leased actual full hash/size differs") as caught:
        asyncio.run(owner.run_once())
    _assert_one_attempt(audit)
    _assert_no_publication(owner, audit)
    frame = audit.frames[0]
    assert set(frame["body"]) == {"size", "sha256"}
    assert frame["body"]["size"] == len(audit.data.outcome)
    assert frame["body"]["sha256"] == _different_digest(_sha(audit.data.outcome))
    assert audit.export_attempts == audit.receipt_calls == []
    assert len(owner._lease._readers) == 1
    assert owner._lease._readers[0]._file.record.closed
    _release(owner, caught.value)


def test_actual_ac_late_identity_mutation_refuses_sealing(case, owner, monkeypatch):
    audit = _install_fixture(case, owner, monkeypatch, fault="late_identity")
    with pytest.raises(ValueError, match="named file identity changed") as caught:
        asyncio.run(owner.run_once())
    _assert_one_attempt(audit)
    _assert_no_publication(owner, audit)
    _assert_inventory(audit)
    assert len(audit.receipt_calls) == len(audit.receipt_accepted) == 1
    assert len(audit.mutations) == len(audit.identity_errors) == 1
    target = audit.mutations[0]
    failed_reader, closed, error = audit.identity_errors[0]
    assert failed_reader is target and closed and error is caught.value
    assert len(owner._lease._readers) == 8
    assert all(reader._file.record.closed for reader in owner._lease._readers)
    assert [(key, accepted) for key, accepted in audit.export_attempts if key in _BULK_KEYS] == [
        (key, 1) for key in _BULK_KEYS]
    _release(owner, caught.value)


def test_actual_ac_receipt_checkpoint_digest_mutation_refuses_before_bulk(case, owner, monkeypatch):
    audit = _install_fixture(case, owner, monkeypatch, fault="checkpoint")
    with pytest.raises(
        ValueError, match="receipt checkpoint JSON digest differs from output manifest"
    ) as caught:
        asyncio.run(owner.run_once())
    _assert_one_attempt(audit)
    _assert_no_publication(owner, audit)
    assert len(audit.receipt_calls) == len(audit.receipt_errors) == 1
    assert audit.receipt_errors[0] is caught.value
    assert audit.receipt_accepted == []
    assert [key for key, _ in audit.export_attempts] == [
        "evidence/" + key for key in _EVIDENCE_KEYS]
    assert len(owner._lease._readers) == 4
    assert all(reader._file.record.closed for reader in owner._lease._readers)
    receipt = audit.receipt_calls[0][0][0]
    checkpoint = receipt["checkpoints"][0]
    assert checkpoint["observation_sha256"] == _different_digest(_sha(b"{}"))
    assert receipt["manifest"] == audit.data.manifest
    assert audit.frames[0]["body"] == dict(
        size=len(audit.data.outcome), sha256=_sha(audit.data.outcome))
    _release(owner, caught.value)


def test_actual_ac_public_preadmission_refusal_remains(case, monkeypatch):
    # No owner fixture: this case must observe zero actual admissions/consumption.
    calls = dict(refusal=0, admission=0, consumption=0, claim=0, birth=0)
    real_refusal = adapter._require_parent_read_custody
    real_admit = api.admit_isolated_owner
    real_bind = base.authority.EngineeringAuthorization._bind_once
    real_claim = api.claim_attempt_reservation
    real_spawn = api._spawn_child

    def refusal():
        calls["refusal"] += 1
        return real_refusal()

    def admit(*args, **kwargs):
        calls["admission"] += 1
        return real_admit(*args, **kwargs)

    def bind(authorization):
        calls["consumption"] += 1
        return real_bind(authorization)

    def claim(*args, **kwargs):
        calls["claim"] += 1
        return real_claim(*args, **kwargs)

    def spawn(*args, **kwargs):
        calls["birth"] += 1
        return real_spawn(*args, **kwargs)

    monkeypatch.setattr(adapter, "_require_parent_read_custody", refusal)
    monkeypatch.setattr(api, "admit_isolated_owner", admit)
    monkeypatch.setattr(base.authority.EngineeringAuthorization, "_bind_once", bind)
    monkeypatch.setattr(api, "claim_attempt_reservation", claim)
    monkeypatch.setattr(api, "_spawn_child", spawn)
    assert not case.auth.bound and base.common._ACTIVE_HOST is None
    with pytest.raises(adapter.FrozenReadCustodyUnavailable) as caught:
        asyncio.run(adapter.run_engineering_isolated_once(
            case.request, authorization=case.auth, owner_spec=case.spec,
            uploads=case.items, setup_argv=case.auth.setup_argv,
            export_root=case.export))
    assert type(caught.value) is adapter.FrozenReadCustodyUnavailable
    assert calls == dict(refusal=1, admission=0, consumption=0, claim=0, birth=0)
    assert not case.auth.bound and base.common._ACTIVE_HOST is None
    assert not case.export.exists()
