"""New offline transport contracts, never custody or measurement evidence."""

from __future__ import annotations

import base64
from dataclasses import fields, is_dataclass, replace, FrozenInstanceError
import hashlib
import importlib
import json
import os
import socket
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from train import frontier_bindings as core


def _api():
    return importlib.import_module("train.frontier_transport")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _limits(**changes):
    return replace(core.BindingLimits(
        1024, 4096, 12289, 12289, 1 << 20, 16 << 20, 256, 10), **changes)


def _canonical(document):
    return (json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _record(value):
    if is_dataclass(value):
        return {f.name: _record(getattr(value, f.name)) for f in fields(value)}
    if type(value) is tuple:
        return [_record(item) for item in value]
    return value


def _document(data):
    return dict(kind="cotrain-unverified-frontier-transport", version=1,
                plan=_record(data.plan), retention_pins=_record(data.pins),
                samples=_record(data.batch.samples),
                blobs=[dict(evidence_id=b.evidence_id,
                            payload_base64=base64.b64encode(b.payload).decode("ascii"))
                       for b in data.batch.blobs])


def _shape(value):
    if is_dataclass(value):
        return (type(value), tuple((f.name, _shape(getattr(value, f.name)))
                                   for f in fields(value)))
    if type(value) is tuple:
        return tuple(_shape(item) for item in value)
    return (type(value), value.hex() if type(value) is float else value)


def _size(value):
    if type(value) is str:
        return len(value.encode("utf-8"))
    if type(value) is bytes:
        return len(value)
    if type(value) is tuple:
        return sum(_size(item) for item in value)
    if is_dataclass(value):
        return sum(_size(getattr(value, f.name)) for f in fields(value))
    return 0


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    # Reuse only staging; actual preparation, wrapper, extraction, SQLite and
    # capture/final core checks execute. No aggregate reconstruction or mock.
    from bench.frontier.test_sample_capture import _stage
    from bench.frontier.sample_capture import CaptureSession
    module = importlib.import_module("bench.frontier.probe")
    staged = _stage(tmp_path_factory.mktemp("transport-capture"))
    original, scored, generated = module.execution_accuracy, [], []

    def score(*args, **kwargs):
        result = original(*args, **kwargs)
        scored.append(result)
        return result

    def generate(task):
        generated.append(task.name)
        sql = task.gold_sql if len(generated) % 2 else "SELECT -98765"
        return f"```sql\n{sql}\n```"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "execution_accuracy", score)
        session = CaptureSession(staged.plan, b"inventory", limits=_limits())
        result = session.run(
            staged.root, staged.draw, staged.supplement, generate,
            expected_draw_sha256=staged.plan.draw_sha256,
            expected_supplement_sha256=staged.plan.supplement_sha256, fixture=True)
    assert len(generated) == len(scored) == 28
    return SimpleNamespace(plan=result.batch.plan, pins=result.retention_pins,
                           batch=result.batch, report=result.report, scores=scored,
                           generated=generated)


@pytest.fixture
def tiny(captured):
    task = next(t for t in captured.plan.tasks if t.task_id == captured.plan.eligible_ids[0])
    plan = replace(captured.plan, tasks=(task,), eligible_ids=(task.task_id,),
                   exclusions=(), g=2, checkpoint_sha256=_sha(b"x"))
    pin = core.ExpectedEvidence("checkpoint", "checkpoint", plan.plan_id,
                               plan.execution_id, None, None, None, None, None, 1, _sha(b"x"))
    return SimpleNamespace(plan=plan, pins=(pin,),
                           batch=core.EvidenceBatch(plan, (core.EvidenceBlob("checkpoint", b"x"),), ()))


def _out(tmp_path, name="archive.json"):
    return tmp_path.resolve() / name


def _write(data, path, limits=None):
    return _api().write_unverified_bindings(
        data.plan, data.pins, data.batch, path, limits=limits or _limits())


def _load(path, digest, limits=None):
    return _api().load_unverified_bindings(
        path, expected_archive_sha256=digest, limits=limits or _limits())


def _candidate(tmp_path, raw, name="candidate.json"):
    path = _out(tmp_path, name)
    path.write_bytes(raw)
    return path


def _refuses(action, error=None):
    api = _api()
    with pytest.raises(error or api.TransportError) as caught:
        action()
    assert caught.value.__suppress_context__ is True
    assert caught.value.__cause__ is None
    assert len(str(caught.value)) <= 80
    return caught.value


def _authority(report):
    assert report.provenance == "unverified" and report.attested_facts == ()
    assert report.genuine_measurement_accepted is False
    assert report.training_authorized is False


def _score_fields(payload):
    assert payload.startswith(b"frontier-score-v1;")
    remaining, result = payload[len(b"frontier-score-v1;"):], []
    while remaining:
        count, remaining = remaining.split(b":", 1)
        size = int(count)
        result.append(remaining[:size].decode("utf-8"))
        remaining = remaining[size:]
    assert len(result) == 8
    return result


def test_capture_roundtrip(captured, tmp_path, monkeypatch):
    api = _api()
    module = importlib.import_module("bench.frontier.probe")

    def forbidden(*args, **kwargs):
        raise AssertionError("transport rescored a captured sample")

    monkeypatch.setattr(module, "execution_accuracy", forbidden)
    path = _out(tmp_path)
    digest = _write(captured, path)
    assert digest == _sha(path.read_bytes())
    assert path.read_bytes() == _canonical(_document(captured))
    loaded = _load(path, digest)
    assert type(loaded) is api.TransportedBindings
    assert len(loaded.batch.samples) == 28
    assert len(loaded.batch.blobs) == len(loaded.retention_pins) == 57
    assert _shape(loaded.plan) == _shape(captured.plan)
    assert _shape(loaded.retention_pins) == _shape(captured.pins)
    assert _shape(loaded.batch) == _shape(captured.batch)
    assert loaded.plan is loaded.batch.plan
    assert loaded.plan is not captured.plan
    assert loaded.plan.scorer is not captured.plan.scorer
    assert loaded.batch.samples[0] is not captured.batch.samples[0]
    assert loaded.report == captured.report
    assert core.validate_frontier_bindings(
        loaded.plan, loaded.retention_pins, loaded.batch, limits=_limits()) == loaded.report
    _authority(loaded.report)
    # Score payloads retain all six original fields as exact captured bytes.
    for blob, original, before in zip(loaded.batch.blobs[2::2], captured.scores,
                                      captured.batch.blobs[2::2]):
        assert blob.payload == before.payload
        assert _score_fields(blob.payload)[2:] == [
            "f:" + original.score.hex(), original.status,
            "true" if original.valid else "false", original.detail,
            str(original.n_pred_rows), str(original.n_gold_rows)]
    with pytest.raises(FrozenInstanceError):
        loaded.plan = None
    assert not hasattr(loaded, "__dict__")
    assert "provider-declaration" not in repr(loaded)


def test_archive_sha_before_decode(tiny, tmp_path, monkeypatch):
    api = _api()
    raw = _canonical(_document(tiny))
    changed = raw.replace(b'"runtime_id":"runtime"', b'"runtime_id":"runtimf"')
    assert changed != raw and len(changed) == len(raw)
    path = _candidate(tmp_path, changed)
    with monkeypatch.context() as patch:
        patch.setattr(api, "_decode_utf8", lambda *a: pytest.fail("SHA guard decoded"))
        _refuses(lambda: _load(path, _sha(raw)))
    admitted = _load(path, _sha(changed))
    assert admitted.plan.runtime_id == "runtimf"
    _authority(admitted.report)


@pytest.mark.parametrize("pin", [None, b"x", True, "a" * 63, "A" * 64, "z" * 64])
def test_bad_external_sha_before_read(tmp_path, monkeypatch, pin):
    api = _api()
    monkeypatch.setattr(api, "_read_regular", lambda *a: pytest.fail("invalid pin read"))
    _refuses(lambda: _load(_out(tmp_path), pin))


@pytest.mark.parametrize("case", [
    "top_extra", "top_missing", "kind", "version", "bool_version",
    "plan_extra", "plan_missing", "task_extra", "scorer_extra", "pin_extra",
    "blob_extra", "blob_missing", "cached_report", "authority", "tuple_shape",
])
def test_strict_format(tiny, tmp_path, case):
    doc = _document(tiny)
    if case == "top_extra":
        doc["extension"] = {}
    elif case == "top_missing":
        del doc["samples"]
    elif case == "kind":
        doc["kind"] = "genuine-frontier"
    elif case == "version":
        doc["version"] = 2
    elif case == "bool_version":
        doc["version"] = True
    elif case == "plan_extra":
        doc["plan"]["extra"] = 1
    elif case == "plan_missing":
        del doc["plan"]["adapter_sha256"]
    elif case == "task_extra":
        doc["plan"]["tasks"][0]["question"] = "private"
    elif case == "scorer_extra":
        doc["plan"]["scorer"]["callback"] = None
    elif case == "pin_extra":
        doc["retention_pins"][0]["verified"] = True
    elif case == "blob_extra":
        doc["blobs"][0]["path"] = "/private/never-open"
    elif case == "blob_missing":
        del doc["blobs"][0]["payload_base64"]
    elif case == "cached_report":
        doc["report"] = {"schedule_complete": True}
    elif case == "authority":
        doc["training_authorized"] = True
    else:
        doc["plan"]["eligible_ids"] = {"0": "not an array"}
    raw = _canonical(doc)
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw)))


@pytest.mark.parametrize("key", [b"version", b"runtime_id"])
def test_duplicate_decoded_keys(tiny, tmp_path, key):
    raw = _canonical(_document(tiny))
    if key == b"version":
        raw = raw.replace(b'"version":1', b'"version":1,"\\u0076ersion":1')
    else:
        raw = raw.replace(b'"runtime_id":"runtime"',
                          b'"runtime_id":"runtime","\\u0072untime_id":"runtime"')
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw)))


@pytest.mark.parametrize("case", ["space", "no_newline", "two_newlines", "unsorted", "escaped"])
def test_noncanonical_json(tiny, tmp_path, case):
    doc = _document(tiny)
    raw = _canonical(doc)
    if case == "space":
        raw = raw.replace(b'":', b'": ', 1)
    elif case == "no_newline":
        raw = raw[:-1]
    elif case == "two_newlines":
        raw += b"\n"
    elif case == "unsorted":
        raw = (json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    else:
        raw = raw.replace(b"runtime", b"\\u0072untime", 1)
    assert raw != _canonical(doc)
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw)))


@pytest.mark.parametrize("raw", [
    b"\xff", b'{"version":NaN}', b'{"version":Infinity}',
    b'{"version":-Infinity}', b'{"version":1e999}',
    b'{"version":9223372036854775808}', b'{"version":-9223372036854775809}',
    b'{"version":111111111111111111111111111111111}',
    b'{"x":"unterminated}', b'{"x":"unescaped\ncontrol"}',
])
def test_invalid_lexical_numbers_and_utf8(tmp_path, raw):
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw)))


@pytest.mark.parametrize("encoded", ["eA", "eA===", "eA==\n", "eB==", "_A==",
                                      "éA==", "====", True])
def test_strict_base64(tiny, tmp_path, encoded):
    doc = _document(tiny)
    doc["blobs"][0]["payload_base64"] = encoded
    raw = _canonical(doc)
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw)))


def test_numeric_helper_endpoints():
    api = _api()
    assert api._parse_int(str(-(1 << 63))) == -(1 << 63)
    assert api._parse_int(str((1 << 63) - 1)) == (1 << 63) - 1
    for text in (str(1 << 63), str(-(1 << 63) - 1)):
        _refuses(lambda: api._parse_int(text))
    assert api._parse_float("0." + "0" * 29 + "1") > 0
    _refuses(lambda: api._parse_float("0." + "0" * 30 + "1"))
    _refuses(lambda: api._parse_float("1e999"))


def _value_count(value):
    if type(value) is dict:
        return 1 + sum(1 + _value_count(item) for item in value.values())
    if type(value) is list:
        return 1 + sum(_value_count(item) for item in value)
    return 1


@pytest.mark.parametrize("constant,exact", [
    ("_MAX_DEPTH", 4), ("_MAX_OBJECT_MEMBERS", 24),
    ("_MAX_STRING_TOKEN_CHARS", 66), ("_MAX_NUMBER_CHARS", 6),
    ("_MAX_ENCODED_BLOB_CHARS", 4),
])
def test_small_transport_boundaries(tiny, tmp_path, monkeypatch, constant, exact):
    api = _api()
    monkeypatch.setattr(api, constant, exact)
    path = _out(tmp_path)
    digest = _write(tiny, path)
    assert _load(path, digest).report.observed_slots == 0
    monkeypatch.setattr(api, constant, exact - 1)
    _refuses(lambda: _write(tiny, _out(tmp_path, "over.json")))
    _refuses(lambda: _load(path, digest))


def test_total_value_boundary(tiny, tmp_path, monkeypatch):
    api = _api()
    count = _value_count(_document(tiny))
    monkeypatch.setattr(api, "_MAX_VALUES", count)
    path = _out(tmp_path)
    digest = _write(tiny, path)
    _load(path, digest)
    monkeypatch.setattr(api, "_MAX_VALUES", count - 1)
    _refuses(lambda: _load(path, digest))
    _refuses(lambda: _write(tiny, _out(tmp_path, "over.json")))


def test_archive_bytes_and_writer_allocation_order(tiny, tmp_path, monkeypatch):
    api = _api()
    plan = replace(tiny.plan, runtime_id='\x00\b\f\n\r\t"\\é☃')
    data = SimpleNamespace(plan=plan, pins=tiny.pins, batch=replace(tiny.batch, plan=plan))
    raw = _canonical(_document(data))
    monkeypatch.setattr(api, "_MAX_ARCHIVE_BYTES", len(raw))
    path = _out(tmp_path)
    digest = _write(data, path)
    assert path.read_bytes() == raw
    _load(path, digest)
    monkeypatch.setattr(api, "_MAX_ARCHIVE_BYTES", len(raw) - 1)
    with monkeypatch.context() as patch:
        patch.setattr(api.base64, "b64encode", lambda *a: pytest.fail("oversize writer encoded"))
        _refuses(lambda: _write(data, _out(tmp_path, "over.json")))
    with monkeypatch.context() as patch:
        patch.setattr(api, "_decode_utf8", lambda *a: pytest.fail("oversize reader decoded"))
        _refuses(lambda: _load(path, digest))


def test_core_aggregate_before_base64(tiny, tmp_path, monkeypatch):
    api = _api()
    actual = _size(tiny.plan) + _size(tiny.pins) + _size(tiny.batch)
    path = _out(tmp_path)
    digest = _write(tiny, path, _limits(max_aggregate_bytes=actual))
    _load(path, digest, _limits(max_aggregate_bytes=actual))
    with monkeypatch.context() as patch:
        patch.setattr(api.base64, "b64decode", lambda *a, **k: pytest.fail("quota decoded"))
        _refuses(lambda: _load(path, digest, _limits(max_aggregate_bytes=actual - 1)))


def test_all_blob_quotas_precede_any_decode(tiny, tmp_path, monkeypatch):
    api = _api()
    doc = _document(tiny)
    doc["blobs"].append(dict(evidence_id="extra", payload_base64="eHg="))
    raw = _canonical(doc)
    monkeypatch.setattr(api.base64, "b64decode", lambda *a, **k: pytest.fail("early blob decoded"))
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw), _limits(max_item_bytes=1)))


def test_core_item_count_and_utf8_bounds(tiny, tmp_path):
    path = _out(tmp_path)
    digest = _write(tiny, path, _limits(
        max_item_bytes=1, max_raw_evidence=1, max_expected_evidence=1,
        max_planned_tasks=1, max_scheduled_slots=2))
    _load(path, digest, _limits(max_item_bytes=1, max_raw_evidence=1,
                               max_expected_evidence=1, max_planned_tasks=1,
                               max_scheduled_slots=2))
    doc = _document(tiny)
    doc["blobs"][0]["payload_base64"] = "eHg="
    raw = _canonical(doc)
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw), _limits(max_item_bytes=1)))
    extra = replace(tiny.batch, blobs=tiny.batch.blobs + (core.EvidenceBlob("extra", b"x"),))
    _refuses(lambda: _api().write_unverified_bindings(
        tiny.plan, tiny.pins, extra, _out(tmp_path, "count.json"),
        limits=_limits(max_raw_evidence=1)))
    plan = replace(tiny.plan, runtime_id="é" * 128)
    data = SimpleNamespace(plan=plan, pins=tiny.pins, batch=replace(tiny.batch, plan=plan))
    _write(data, _out(tmp_path, "utf8.json"))
    plan = replace(plan, runtime_id=plan.runtime_id + "x")
    _refuses(lambda: _api().write_unverified_bindings(
        plan, tiny.pins, replace(tiny.batch, plan=plan), _out(tmp_path, "utf8-over.json"),
        limits=_limits()))


@pytest.mark.parametrize("variant", ["provider", "timeout_type", "timeout_inverse", "task"])
def test_no_repair_plan_projection(tiny, tmp_path, monkeypatch, variant):
    api = _api()
    plan = tiny.plan
    if variant == "provider":
        other = replace(plan, provider_id="other")
    elif variant == "timeout_type":
        other = replace(plan, scorer=replace(plan.scorer, timeout_s=30))
        assert core._plan_projection(plan) == core._plan_projection(other)
    elif variant == "timeout_inverse":
        plan = replace(plan, scorer=replace(plan.scorer, timeout_s=30))
        other = replace(plan, scorer=replace(plan.scorer, timeout_s=30.0))
    else:
        other = replace(plan, tasks=(replace(plan.tasks[0], task_sha256="0" * 64),))
    monkeypatch.setattr(api.prepare, "_publish", lambda *a: pytest.fail("mismatched plans published"))
    _refuses(lambda: api.write_unverified_bindings(
        plan, tiny.pins, replace(tiny.batch, plan=other), _out(tmp_path), limits=_limits()))


@pytest.mark.parametrize("variant", ["missing", "reference", "unused", "invalid_gold",
                                      "failed_zero", "bytes"])
def test_inconsistent_semantics_preserved(captured, tmp_path, variant):
    pins, batch = captured.pins, captured.batch
    if variant == "missing":
        batch = replace(batch, samples=batch.samples[:-1])
    elif variant == "reference":
        batch = replace(batch, samples=(replace(
            batch.samples[0], generation_evidence_id="absent"),) + batch.samples[1:])
    elif variant == "unused":
        pins = pins + (replace(pins[-1], evidence_id="unused"),)
    elif variant == "invalid_gold":
        batch = replace(batch, samples=(replace(
            batch.samples[0], status="invalid_gold", score=None),) + batch.samples[1:])
    elif variant == "failed_zero":
        batch = replace(batch, samples=(replace(
            batch.samples[0], status="generation_failed", score=0),) + batch.samples[1:])
    else:
        batch = replace(batch, blobs=(batch.blobs[0], replace(
            batch.blobs[1], payload=b"changed bytes")) + batch.blobs[2:])
    original = core.validate_frontier_bindings(captured.plan, pins, batch, limits=_limits())
    data = SimpleNamespace(plan=captured.plan, pins=pins, batch=batch)
    path = _out(tmp_path)
    loaded = _load(path, _write(data, path))
    assert loaded.report == original
    assert _shape(loaded.retention_pins) == _shape(pins)
    assert _shape(loaded.batch) == _shape(batch)
    assert not loaded.report.all_samples_validly_scored
    _authority(loaded.report)


def test_detached_before_publication(tiny, tmp_path, monkeypatch):
    api = _api()
    real = api.prepare._publish
    old = tiny.plan.runtime_id

    def publish(doc, output):
        object.__setattr__(tiny.plan, "runtime_id", "mutated after admission")
        return real(doc, output)

    monkeypatch.setattr(api.prepare, "_publish", publish)
    path = _out(tmp_path)
    loaded = _load(path, _write(tiny, path))
    assert loaded.plan.runtime_id == old
    assert tiny.plan.runtime_id != loaded.plan.runtime_id


def test_filesystem_paths_and_existing_output(tiny, tmp_path):
    api = _api()
    real = tmp_path.resolve()
    path = _out(tmp_path)
    digest = _write(tiny, path)
    assert _load(str(path), digest).report.matched_evidence == 1
    _refuses(lambda: _write(tiny, path))
    assert path.read_bytes() == _canonical(_document(tiny))
    assert _sha(path.read_bytes()) == digest
    for bad in ("relative.json", real / "absent" / "new.json",
                str(real) + "/../escape.json", real):
        _refuses(lambda: _write(tiny, bad))
        _refuses(lambda: _load(bad, digest))
    assert not (real / "absent").exists()
    link = real / "link"
    link.symlink_to(real, target_is_directory=True)
    _refuses(lambda: _write(tiny, link / "new.json"))
    _refuses(lambda: _load(link / path.name, digest))
    leaf = real / "leaf"
    leaf.symlink_to(path)
    _refuses(lambda: _write(tiny, leaf))
    _refuses(lambda: _load(leaf, digest))
    assert leaf.is_symlink() and path.read_bytes() == _canonical(_document(tiny))
    fifo = real / "fifo"
    os.mkfifo(fifo)
    _refuses(lambda: _load(fifo, digest))
    _refuses(lambda: _write(tiny, fifo))
    class HostilePath:
        def __fspath__(self):
            raise AssertionError("path hook invoked")
    _refuses(lambda: _write(tiny, HostilePath()))


@pytest.mark.parametrize("drift", ["inplace", "replacement"])
def test_read_detects_drift(tiny, tmp_path, monkeypatch, drift):
    api = _api()
    path = _out(tmp_path)
    digest = _write(tiny, path)
    replacement = _out(tmp_path, "replacement")
    replacement.write_bytes(path.read_bytes())
    real_read, changed = api.os.read, []

    def read(fd, size):
        raw = real_read(fd, size)
        if raw and not changed:
            changed.append(1)
            if drift == "replacement":
                os.replace(replacement, path)
            else:
                with path.open("ab") as handle:
                    handle.write(b" ")
        return raw

    monkeypatch.setattr(api.os, "read", read)
    _refuses(lambda: _load(path, digest))
    assert changed == [1]


def test_final_entry_checked(tiny, tmp_path, monkeypatch):
    api = _api()
    path = _out(tmp_path)
    digest = _write(tiny, path)
    real_stat, seen = api.os.stat, []

    def stat(name, *args, **kwargs):
        if name == path.name:
            seen.append(kwargs)
        return real_stat(name, *args, **kwargs)

    monkeypatch.setattr(api.os, "stat", stat)
    _load(path, digest)
    assert len(seen) == 1
    assert seen[0]["follow_symlinks"] is False and type(seen[0]["dir_fd"]) is int


def test_fd_cleanup_preserves_baseexception(tiny, tmp_path, monkeypatch):
    api = _api()
    path = _out(tmp_path)
    digest = _write(tiny, path)
    original_open, original_close = api.os.open, api.os.close
    live, closed = set(), []
    failure = KeyboardInterrupt("sensitive interrupted read")

    def open_fd(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        live.add(fd)
        return fd

    def close_fd(fd):
        original_close(fd)
        live.remove(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise OSError("sensitive cleanup fault")

    def read(*args):
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(api.os, "open", open_fd)
        patch.setattr(api.os, "close", close_fd)
        patch.setattr(api.os, "read", read)
        with pytest.raises(KeyboardInterrupt) as caught:
            _load(path, digest)
    assert caught.value is failure and live == set() and closed


@pytest.mark.parametrize("phase", ["prelink", "postlink", "baseexception"])
def test_publication(tiny, tmp_path, monkeypatch, phase):
    api = _api()
    path = _out(tmp_path)
    real_publish, publishes, links = api.prepare._publish, [], []
    failure = KeyboardInterrupt("private publication interruption")

    def publish(*args, **kwargs):
        publishes.append(1)
        return real_publish(*args, **kwargs)

    def link(*args, **kwargs):
        links.append(1)
        raise OSError("private prelink fault")

    def sync(*args):
        if phase == "baseexception":
            raise failure
        raise OSError("private postlink fault")

    monkeypatch.setattr(api.prepare, "_publish", publish)
    if phase == "prelink":
        monkeypatch.setattr(api.prepare.os, "link", link)
        _refuses(lambda: _write(tiny, path))
        assert not path.exists() and links == [1]
    elif phase == "postlink":
        monkeypatch.setattr(api.prepare, "_sync_dir", sync)
        error = _refuses(lambda: _write(tiny, path), api.TransportPublicationIndeterminateError)
        assert str(error) == "unverified frontier transport publication indeterminate"
        assert path.read_bytes() == _canonical(_document(tiny))
    else:
        monkeypatch.setattr(api.prepare, "_sync_dir", sync)
        with pytest.raises(KeyboardInterrupt) as caught:
            _write(tiny, path)
        assert caught.value is failure
        assert path.read_bytes() == _canonical(_document(tiny))
    assert publishes == [1]


def test_no_execution_privacy(captured, tmp_path, monkeypatch):
    api = _api()
    path = _out(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("transport executed an external/scoring operation")

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(importlib.import_module("bench.score"), "execution_accuracy", forbidden)
        patch.setattr(importlib.import_module("bench.frontier.probe"), "execution_accuracy", forbidden)
        patch.setattr(api.prepare, "load_validated_draw", forbidden)
        loaded = _load(path, _write(captured, path))
    assert "provider-declaration" not in repr(loaded)
    error = _refuses(lambda: _load(_out(tmp_path, "SECRET-SELECT-missing"), "a" * 64))
    assert str(error) == "invalid unverified frontier transport"
    assert "SECRET" not in repr(error) and str(tmp_path) not in repr(error)
    _authority(loaded.report)


@pytest.mark.parametrize("phase", ["read", "precheck"])
def test_cleanup_failure_not_hidden_by_callers_exception(tiny, tmp_path, monkeypatch, phase):
    api = _api()
    path = _out(tmp_path)
    digest = _write(tiny, path)
    original_close, closed = api.os.close, []

    def close(fd):
        original_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise OSError("private successful-operation cleanup fault")

    with monkeypatch.context() as patch:
        patch.setattr(api.os, "close", close)
        try:
            raise LookupError("unrelated caller exception")
        except LookupError:
            if phase == "read":
                _refuses(lambda: _load(path, digest))
            else:
                _refuses(lambda: _write(tiny, _out(tmp_path, "new.json")))
    assert closed
    if phase == "precheck":
        assert not _out(tmp_path, "new.json").exists()


@pytest.mark.parametrize("case", ["depth", "members", "values", "string", "number"])
def test_lexical_quotas_before_parser(tiny, tmp_path, monkeypatch, case):
    api = _api()
    doc = _document(tiny)
    if case == "depth":
        nested = 0
        for _ in range(13):
            nested = [nested]
        doc["extra"] = nested
    elif case == "members":
        doc.update({f"extra-{i}": i for i in range(41)})
    elif case == "values":
        monkeypatch.setattr(api, "_MAX_VALUES", _value_count(doc) - 1)
    elif case == "string":
        doc["plan"]["runtime_id"] = "x" * 65
        monkeypatch.setattr(api, "_MAX_STRING_TOKEN_CHARS", 66)
    raw = _canonical(doc)
    if case == "number":
        raw = raw.replace(b'"version":1', b'"version":' + b"1" * 33)
    path = _candidate(tmp_path, raw)
    monkeypatch.setattr(api.json, "loads", lambda *a, **k: pytest.fail("lexical limit parsed"))
    _refuses(lambda: _load(path, _sha(raw)))


def test_quoted_punctuation_is_not_structure(tiny, tmp_path, monkeypatch):
    api = _api()
    value = '[]{}:"1e999":\\' * 10
    plan = replace(tiny.plan, runtime_id=value)
    data = SimpleNamespace(plan=plan, pins=tiny.pins, batch=replace(tiny.batch, plan=plan))
    monkeypatch.setattr(api, "_MAX_DEPTH", 4)
    monkeypatch.setattr(api, "_MAX_OBJECT_MEMBERS", 24)
    monkeypatch.setattr(api, "_MAX_VALUES", _value_count(_document(data)))
    path = _out(tmp_path)
    assert _load(path, _write(data, path)).plan.runtime_id == value


@pytest.mark.parametrize("which", ["pins", "blobs", "samples"])
def test_duplicate_core_identities_refuse(captured, tmp_path, which):
    data = SimpleNamespace(plan=captured.plan, pins=captured.pins, batch=captured.batch)
    if which == "pins":
        data.pins += (data.pins[0],)
    else:
        data.batch = replace(data.batch, **{
            which: getattr(data.batch, which) + (getattr(data.batch, which)[0],)})
    output = _out(tmp_path)
    _refuses(lambda: _write(data, output))
    assert not output.exists()
    raw = _canonical(_document(data))
    _refuses(lambda: _load(_candidate(tmp_path, raw), _sha(raw)))


def test_scalar_types_and_negative_zero_preserved(captured, tmp_path):
    plan = replace(captured.plan, scorer=replace(captured.plan.scorer, timeout_s=30))
    samples = (replace(captured.batch.samples[0], score=1),
               replace(captured.batch.samples[1], score=-0.0)) + captured.batch.samples[2:]
    batch = replace(captured.batch, plan=plan, samples=samples)
    data = SimpleNamespace(plan=plan, pins=captured.pins, batch=batch)
    path = _out(tmp_path)
    loaded = _load(path, _write(data, path))
    assert type(loaded.plan.scorer.timeout_s) is int
    assert type(loaded.batch.samples[0].score) is int
    assert loaded.batch.samples[1].score.hex() == "-0x0.0p+0"
    assert _shape(loaded.batch) == _shape(batch)
    _authority(loaded.report)


def test_sha_guard_loss(tiny, tmp_path, monkeypatch):
    api = _api()
    raw = _canonical(_document(tiny))
    changed = raw.replace(b'"runtime_id":"runtime"', b'"runtime_id":"runtimf"')
    good = _candidate(tmp_path, raw, "good.json")
    bad = _candidate(tmp_path, changed, "bad.json")
    assert _load(good, _sha(raw)).plan.runtime_id == "runtime"
    assert _load(bad, _sha(changed)).plan.runtime_id == "runtimf"

    def oracle():
        try:
            _load(bad, _sha(raw))
        except api.TransportError:
            return
        raise AssertionError("archive SHA oracle")

    oracle()
    with monkeypatch.context() as patch:
        patch.setattr(api, "_check_archive_sha", lambda *a: None)
        with pytest.raises(AssertionError) as caught:
            oracle()
        assert str(caught.value).splitlines()[0] == "archive SHA oracle"
    oracle()
    _load(good, _sha(raw))


def test_predecode_quota_guard_loss(tiny, tmp_path, monkeypatch):
    api = _api()
    doc = _document(tiny)
    good_raw = _canonical(doc)
    doc["blobs"][0]["payload_base64"] = "eHg="  # two bytes, declaration stays one
    bad_raw = _canonical(doc)
    good = _candidate(tmp_path, good_raw, "good.json")
    bad = _candidate(tmp_path, bad_raw, "bad.json")
    limits = _limits(max_item_bytes=1)
    assert _load(good, _sha(good_raw), limits).report.matched_evidence == 1
    decoder, allocations = api.base64.b64decode, []

    def decode(*args, **kwargs):
        allocations.append(1)
        return decoder(*args, **kwargs)

    def oracle():
        allocations.clear()
        with monkeypatch.context() as patch:
            patch.setattr(api.base64, "b64decode", decode)
            try:
                _load(bad, _sha(bad_raw), limits)
            except api.TransportError:
                pass
        assert allocations == [], "predecode quota oracle"

    oracle()
    with monkeypatch.context() as patch:
        patch.setattr(api, "_charge_payload", lambda *a: None)
        with pytest.raises(AssertionError) as caught:
            oracle()
        assert str(caught.value).splitlines()[0] == "predecode quota oracle"
    oracle()
    assert _load(good, _sha(good_raw), limits).report.matched_evidence == 1


def test_bounded_n_plus_one_even_with_understated_stat(tiny, tmp_path, monkeypatch):
    api = _api()
    raw = _canonical(_document(tiny))
    path = _candidate(tmp_path, raw + b" ")
    original_fstat, original_read = api.os.fstat, api.os.read
    requests, returned = [], []
    monkeypatch.setattr(api, "_MAX_ARCHIVE_BYTES", len(raw))

    def fstat(fd):
        info = original_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_size=len(raw))

    def read(fd, size):
        requests.append(size)
        block = original_read(fd, size)
        returned.append(len(block))
        return block

    monkeypatch.setattr(api.os, "fstat", fstat)
    monkeypatch.setattr(api.os, "read", read)
    monkeypatch.setattr(api, "_decode_utf8", lambda *a: pytest.fail("N+1 decoded"))
    _refuses(lambda: _load(path, _sha(raw + b" ")))
    assert requests == returned == [len(raw) + 1]


@pytest.mark.parametrize("phase", ["open", "fstat", "read", "entry"])
def test_filesystem_faults_close_all_opened_fds(tiny, tmp_path, monkeypatch, phase):
    api = _api()
    path = _out(tmp_path)
    digest = _write(tiny, path)
    real_open, real_close = api.os.open, api.os.close
    real_stat, real_fstat, real_read = api.os.stat, api.os.fstat, api.os.read
    live, opens, closes = set(), [], []

    def open_fd(*args, **kwargs):
        if phase == "open" and opens:
            raise PermissionError("private ancestry fault")
        fd = real_open(*args, **kwargs)
        live.add(fd)
        opens.append(fd)
        return fd

    def close_fd(fd):
        real_close(fd)
        live.remove(fd)
        closes.append(fd)

    def fstat(fd):
        if phase == "fstat":
            raise OSError("private fstat fault")
        return real_fstat(fd)

    def read(fd, size):
        if phase == "read":
            raise OSError("private read fault")
        return real_read(fd, size)

    def stat(name, *args, **kwargs):
        if phase == "entry" and name == path.name:
            raise OSError("private final-entry fault")
        return real_stat(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(api.os, "open", open_fd)
        patch.setattr(api.os, "close", close_fd)
        patch.setattr(api.os, "fstat", fstat)
        patch.setattr(api.os, "read", read)
        patch.setattr(api.os, "stat", stat)
        _refuses(lambda: _load(path, digest))
    assert opens and live == set() and sorted(opens) == sorted(closes)


def test_cleanup_cancellation_not_masked_by_earlier_ordinary_close_error(monkeypatch):
    api = _api()
    cancellation = KeyboardInterrupt("synthetic cleanup cancellation")
    attempted = []

    def close(fd):
        attempted.append(fd)
        if fd == 100011:
            raise OSError("synthetic earlier ordinary cleanup error")
        assert fd == 100010
        raise cancellation

    with monkeypatch.context() as patch:
        patch.setattr(api.os, "close", close)
        with pytest.raises(KeyboardInterrupt) as caught:
            api._close_all([100010, 100011], False)
    assert caught.value is cancellation
    assert attempted == [100011, 100010]


def test_empty_opaque_bytes_are_lossless(tiny, tmp_path):
    plan = replace(tiny.plan, checkpoint_sha256=_sha(b""))
    pins = (replace(tiny.pins[0], byte_count=0, sha256=_sha(b"")),)
    batch = replace(tiny.batch, plan=plan, blobs=(core.EvidenceBlob("checkpoint", b""),))
    data = SimpleNamespace(plan=plan, pins=pins, batch=batch)
    path = _out(tmp_path)
    loaded = _load(path, _write(data, path))
    assert loaded.batch.blobs[0].payload == b""
    assert loaded.report.matched_evidence == 1
    assert loaded.report.observed_slots == 0 and not loaded.report.schedule_complete
    _authority(loaded.report)


def test_non_utf8_opaque_bytes_are_not_interpreted(tiny, tmp_path):
    payload = bytes(range(256))
    plan = replace(tiny.plan, checkpoint_sha256=_sha(payload))
    pins = (replace(tiny.pins[0], byte_count=len(payload), sha256=_sha(payload)),)
    batch = replace(tiny.batch, plan=plan, blobs=(core.EvidenceBlob("checkpoint", payload),))
    data = SimpleNamespace(plan=plan, pins=pins, batch=batch)
    path = _out(tmp_path)
    loaded = _load(path, _write(data, path))
    assert loaded.batch.blobs[0].payload == payload
    assert loaded.report.matched_evidence == 1
    _authority(loaded.report)
