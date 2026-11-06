"""Query-free synthetic boundary tests, never preparation/scientific evidence."""

from __future__ import annotations

import copy
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from bench import prepare
from bench.task import SqlTask
from train import frontier_inputs as module
from train import test_frontier_inputs as helpers


offline_framework_guard = helpers.offline_framework_guard


@pytest.fixture(autouse=True)
def no_corpus_or_sql(monkeypatch):
    with helpers._sentries(monkeypatch, module, corpus=True):
        yield


@pytest.fixture
def synthetic(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    # Opaque digest fixtures, never presented as successfully prepared artifacts.
    draw.write_bytes(b"synthetic draw boundary bytes\n")
    supplement.write_bytes(b"synthetic supplement boundary bytes\n")
    pins = {
        "draw": helpers._sha(draw.read_bytes()),
        "supplement": helpers._sha(supplement.read_bytes()),
        "manifest": "0" * 64,
    }
    tasks = tuple(
        SqlTask(
            name="synthetic-" + name, question="synthetic question " + name,
            evidence="synthetic evidence", gold_sql="SELECT 1",
            db_id="synthetic-db", db_path=str(corpus / "never-opened.sqlite"),
            tier=("simple", "moderate", "challenging")[index % 3],
            tier_source="annotated", shape="synthetic-shape",
            coarse_shape="synthetic-coarse", source="fixture",
        )
        for index, name in enumerate(("z", "a", "m", "b", "y", "c"))
    )
    exclusion = prepare.DrawExclusion(
        id=tasks[1].name, status="gold_error", category="gold_execution_rejection",
    )
    admitted = prepare.ValidatedDraw(
        planned=tasks, eligible=tuple(t for t in tasks if t.name != exclusion.id),
        exclusions=(exclusion,), draw_sha256=pins["draw"],
        supplement_sha256=pins["supplement"], fixture=True,
        timeout_s=30.0, max_rows=500000, comparison="set", databases=(),
    )
    records = helpers._records(admitted, retained=2, void=True)
    doc, probe = helpers._document(admitted, records, pins)
    manifest, sidecar = tmp_path / "legacy-fixture.json", tmp_path / "sidecar.json"
    manifest.write_bytes(helpers._canonical(probe.manifest(helpers.AMENDMENT)))
    pins["manifest"] = helpers._sha(manifest.read_bytes())
    doc["manifest_sha256"] = pins["manifest"]
    sidecar.write_bytes(helpers._canonical(doc))
    pins["sidecar"] = helpers._sha(sidecar.read_bytes())
    fx = helpers._Fixture(
        tmp_path, corpus, draw, supplement, manifest, sidecar,
        pins, admitted, records, doc,
    )
    probe, counts, voids = _check(fx, doc)
    module._manifest(json.loads(manifest.read_bytes()), probe, helpers.AMENDMENT)
    module._join(doc, admitted)
    assert counts == {
        "planned": 6, "preparation_excluded": 1, "eligible": 5, "measured": 4,
        "measurement_void": 1, "retained": 2, "sample_slots": 20,
        "attempted_samples": 19,
    }
    assert len(voids) == 1
    return fx


def _check(fx, doc):
    return module._check_document(
        doc, fx.pins, helpers.RAW_PIN, copy.deepcopy(helpers.IDENTITY),
        helpers.G, helpers.CEILING, module._sources(),
    )


def _count_refusal(fx, doc):
    with pytest.raises(module.FrontierInputsError, match="^invalid frontier inputs$"):
        _check(fx, doc)


@pytest.mark.parametrize("field", [
    "planned", "eligible", "measured", "retained", "sample_slots", "attempted_samples",
])
def test_equal_float_counts_cannot_hide_behind_mapping_equality(synthetic, field):
    doc = copy.deepcopy(synthetic.doc)
    doc["counts"][field] = float(doc["counts"][field])
    assert doc["counts"] == synthetic.doc["counts"]
    _count_refusal(synthetic, doc)


@pytest.mark.parametrize("field", ["preparation_excluded", "measurement_void"])
def test_equal_bool_counts_cannot_hide_behind_mapping_equality(synthetic, field):
    admitted = synthetic.admitted
    if field == "preparation_excluded":
        admitted = replace(admitted, eligible=admitted.planned, exclusions=())
    records = helpers._records(
        admitted, retained=2, void=field != "measurement_void",
    )
    doc, _ = helpers._document(admitted, records, synthetic.pins)
    _check(synthetic, doc)
    original = copy.deepcopy(doc["counts"])
    doc["counts"][field] = False
    assert doc["counts"] == original
    _count_refusal(synthetic, doc)


@pytest.mark.parametrize("path,value", [
    (("n_tasks",), 2.0), (("measurement", "g"), 4.0),
    (("measurement", "n_candidates"), 4.0),
    (("measurement", "n_void_tasks"), 1.0),
    (("measurement", "n_void_tasks"), True),
])
def test_manifest_equal_numeric_count_aliases_refuse(synthetic, path, value):
    probe, _, _ = _check(synthetic, synthetic.doc)
    manifest = probe.manifest(helpers.AMENDMENT)
    baseline = copy.deepcopy(manifest)
    module._manifest(manifest, probe, helpers.AMENDMENT)
    target = manifest if len(path) == 1 else manifest[path[0]]
    target[path[-1]] = value
    assert manifest == baseline
    with pytest.raises(module.FrontierInputsError, match="^invalid frontier inputs$"):
        module._manifest(manifest, probe, helpers.AMENDMENT)


def test_escaped_nested_duplicate_reaches_duplicate_guard(synthetic):
    doc = copy.deepcopy(synthetic.doc)
    void = next(c for c in doc["candidates"] if c["state"] == "measurement_void")
    void["samples"][2]["__escaped_duplicate__"] = void["samples"][2]["status"]
    raw = helpers._canonical(doc).replace(
        b'"__escaped_duplicate__":', b'"\\u0073tatus":', 1,
    )
    assert raw.count(b'"\\u0073tatus":') == 1
    with pytest.raises(module.FrontierInputsError, match="^duplicate frontier field$"):
        module._parse(raw, canonical=True)


def test_numeric_token_exact_limit_and_quoted_lookalikes():
    at_limit = b"0." + b"0" * 126
    over_limit = at_limit + b"0"
    assert len(at_limit) == 128 and len(over_limit) == 129
    assert module._parse(b'{"number":' + at_limit + b"}") == {"number": 0.0}
    with pytest.raises(module.FrontierInputsError, match="numeric token exceeds bounds"):
        module._parse(b'{"number":' + over_limit + b"}")
    text = 'escaped quote: " [ ' + over_limit.decode("ascii") + ' ] \\ end'
    assert module._parse(helpers._canonical({"text": text})) == {"text": text}


def test_snapshot_exact_encoded_byte_budget_and_ownership():
    original = {"records": [{"text": 'quote"slash\\', "values": [0, False, None]}]}
    expected = copy.deepcopy(original)
    limit = len(helpers._canonical(original)) - 1
    snapshot = module._snapshot(original, limit=limit)
    assert snapshot == expected
    with pytest.raises(module.FrontierInputsError, match="document exceeds bounds"):
        module._snapshot(original, limit=limit - 1)
    original["records"][0]["text"] = "caller changed"
    original["records"][0]["values"].append(1)
    assert snapshot == expected
    assert snapshot is not original
    assert snapshot["records"] is not original["records"]


@pytest.mark.parametrize("kind", ["dict", "list"])
def test_snapshot_rejects_container_subclasses_without_hooks(kind):
    calls = []

    class HookDict(dict):
        def items(self):
            calls.append("items")
            raise AssertionError("caller items hook")

        def __deepcopy__(self, memo):
            calls.append("deepcopy")
            raise AssertionError("caller deepcopy hook")

    class HookList(list):
        def __iter__(self):
            calls.append("iter")
            raise AssertionError("caller iteration hook")

        def __deepcopy__(self, memo):
            calls.append("deepcopy")
            raise AssertionError("caller deepcopy hook")

    value = HookDict({"key": 1}) if kind == "dict" else HookList([1])
    with pytest.raises(module.FrontierInputsError):
        module._snapshot(value)
    assert calls == []


def test_identity_snapshot_precedes_signed_amendment_check(monkeypatch):
    identity = copy.deepcopy(helpers.IDENTITY)
    expected = copy.deepcopy(identity)
    real_signed = module.guards._amendment_is_signed
    calls = []

    def signed(amendment, root):
        result = real_signed(amendment, root)
        calls.append(result)
        identity["policy"]["id"] = "caller-mutated-policy"
        identity["template"]["renderer_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(module.guards, "_amendment_is_signed", signed)
    snapshot = module._parameters(
        identity, helpers.AMENDMENT, helpers.RAW_PIN,
        helpers.G, helpers.CEILING, True,
    )
    assert calls == [True]
    assert snapshot == expected
    assert snapshot["policy"] is not identity["policy"]
    assert snapshot["template"] is not identity["template"]
    assert identity["policy"]["id"] == "caller-mutated-policy"
    assert identity["template"]["renderer_sha256"] == "0" * 64


@pytest.mark.parametrize("void_index", [0, 3])
def test_void_at_first_or_last_slot_preserves_exact_attempt_count(void_index):
    slots = [
        helpers._slot(index, "match" if index < void_index else (
            "gold_timeout" if index == void_index else "not_attempted_after_void"
        ))
        for index in range(helpers.G)
    ]
    assert module._slots(slots, helpers.G) == (
        void_index, void_index + 1, "gold_timeout",
    )


@pytest.mark.parametrize("field,value", [
    ("valid", False), ("score", 0), ("evidence_sha256", ""),
])
def test_void_suffix_rejects_nonnull_false_values(field, value):
    slots = [helpers._slot(0, "gold_error")] + [
        helpers._slot(index, "not_attempted_after_void") for index in range(1, helpers.G)
    ]
    slots[-1][field] = value
    with pytest.raises(
        module.FrontierInputsError, match="^attempted sample after measurement void$",
    ):
        module._slots(slots, helpers.G)


def test_unattempted_prefix_with_digest_is_still_not_an_attempt():
    slots = [helpers._slot(index, "match") for index in range(helpers.G)]
    slots[0]["status"] = "not_attempted_after_void"
    assert len(slots[0]["evidence_sha256"]) == 64
    with pytest.raises(
        module.FrontierInputsError, match="^unsupported frontier sample status$",
    ):
        module._slots(slots, helpers.G)


def test_coherently_reordered_ledger_still_refuses_original_task_join(synthetic):
    doc = copy.deepcopy(synthetic.doc)
    doc["candidates"].reverse()
    probe, counts, _ = module._ledger(
        doc["candidates"], doc["identity"], helpers.G, helpers.CEILING,
    )
    doc["diagnostic"], doc["counts"] = probe.report(), counts
    _check(synthetic, doc)
    assert [c["id"] for c in doc["candidates"]] == [
        t.name for t in reversed(synthetic.admitted.planned)
    ]
    assert synthetic.admitted.exclusions[0].id == synthetic.admitted.planned[1].name
    with pytest.raises(
        module.FrontierInputsError, match="^frontier planned membership mismatch$",
    ):
        module._join(doc, synthetic.admitted)


@pytest.mark.parametrize("which", ["draw", "supplement", "manifest", "sidecar"])
def test_final_admission_artifact_drift_is_not_hidden(synthetic, monkeypatch, which):
    paths = {kind: getattr(synthetic, kind) for kind in synthetic.pins}
    sources = module._sources()
    calls = []

    def final_admission(corpus, retained_paths, pins):
        assert corpus == synthetic.corpus
        assert retained_paths == paths and pins == synthetic.pins
        calls.append("final-admission")
        path = paths[which]
        path.write_bytes(path.read_bytes() + b" ")
        return synthetic.admitted

    monkeypatch.setattr(module, "_admit", final_admission)
    with pytest.raises(
        module.FrontierInputsError, match="^retained artifact digest mismatch$",
    ):
        module._recheck(
            synthetic.corpus, paths, synthetic.pins, sources, synthetic.doc,
        )
    assert calls == ["final-admission"]


def test_final_source_snapshot_drift_is_not_hidden(synthetic, monkeypatch):
    paths = {kind: getattr(synthetic, kind) for kind in synthetic.pins}
    real_sources = module._sources
    baseline = real_sources()
    observations, admissions = [], []

    def observed_sources():
        observed = real_sources()
        assert observed == baseline
        observations.append(1)
        if len(observations) == 2:
            key = next(iter(observed))
            observed[key] = "0" * 64 if observed[key] != "0" * 64 else "1" * 64
            assert sum(observed[k] != baseline[k] for k in baseline) == 1
        return observed

    def final_admission(corpus, retained_paths, pins):
        admissions.append(1)
        return synthetic.admitted

    monkeypatch.setattr(module, "_sources", observed_sources)
    monkeypatch.setattr(module, "_admit", final_admission)
    with pytest.raises(module.FrontierInputsError, match="^frontier source drift$"):
        module._recheck(
            synthetic.corpus, paths, synthetic.pins, baseline, synthetic.doc,
        )
    assert len(observations) == 2 and len(admissions) == 1


@pytest.mark.parametrize("fault", ["file-sync", "directory-open", "directory-close"])
def test_publication_file_sync_vs_directory_open_close_faults(tmp_path, monkeypatch, fault):
    output = tmp_path / "publication.json"
    data = helpers._canonical({"fixture": True, "evidence_kind": "synthetic_fixture"})
    real_link, real_sync = os.link, os.fsync
    real_open, real_close, real_unlink = os.open, os.close, os.unlink
    calls = {"links": 0, "commits": 0, "final_delete": 0, "overwrite": 0, "fault": 0}
    directory_fds = []

    def link(source, destination, *args, **kwargs):
        calls["links"] += 1
        result = real_link(source, destination, *args, **kwargs)
        calls["commits"] += 1
        return result

    def sync(fd):
        if fault == "file-sync" and calls["commits"] == 0:
            calls["fault"] += 1
            raise OSError("RAW_ERROR_SENTINEL")
        return real_sync(fd)

    def open_path(path, flags, *args, **kwargs):
        if Path(path) == output.parent and flags == os.O_RDONLY:
            if fault == "directory-open":
                calls["fault"] += 1
                raise OSError("RAW_ERROR_SENTINEL")
            fd = real_open(path, flags, *args, **kwargs)
            directory_fds.append(fd)
            return fd
        return real_open(path, flags, *args, **kwargs)

    def close(fd):
        result = real_close(fd)
        if fault == "directory-close" and fd in directory_fds:
            calls["fault"] += 1
            raise OSError("RAW_ERROR_SENTINEL")
        return result

    def unlink(path, *args, **kwargs):
        if Path(path) == output:
            calls["final_delete"] += 1
            raise AssertionError("final document deletion")
        return real_unlink(path, *args, **kwargs)

    def overwrite(*args, **kwargs):
        calls["overwrite"] += 1
        raise AssertionError("overwrite-capable publication")

    expected_error = OSError if fault == "file-sync" else (
        module.FrontierPublicationIndeterminateError
    )
    with monkeypatch.context() as patch:
        patch.setattr(os, "link", link)
        patch.setattr(os, "fsync", sync)
        patch.setattr(os, "open", open_path)
        patch.setattr(os, "close", close)
        patch.setattr(os, "unlink", unlink)
        patch.setattr(os, "rename", overwrite)
        patch.setattr(os, "replace", overwrite)
        with pytest.raises(expected_error) as caught:
            module._publish(data, output)
    assert calls["fault"] == 1
    assert calls["final_delete"] == calls["overwrite"] == 0
    assert calls["links"] == calls["commits"] == int(fault != "file-sync")
    if fault == "file-sync":
        assert type(caught.value) is OSError
        assert not output.exists()
    else:
        assert type(caught.value) is module.FrontierPublicationIndeterminateError
        assert output.read_bytes() == data
        assert "RAW_ERROR_SENTINEL" not in str(caught.value)
        assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize("operation,which", [
    ("load", "manifest"), ("load", "sidecar"), ("produce", "manifest"),
])
@pytest.mark.parametrize("extra", [0, 1], ids=["exact-N", "N-plus-one"])
def test_exact_artifact_byte_limit_reaches_preparation_but_next_byte_refuses(
        synthetic, monkeypatch, operation, which, extra):
    limit = module._MANIFEST_BYTES if which == "manifest" else module._MAX_BYTES
    assert limit == (65536 if which == "manifest" else 16777216)
    raw = b" " * (limit + extra)
    synthetic.rewrite(raw=raw, which=which)
    reached = []

    class PreparationReached(RuntimeError):
        pass

    def stop_before_parsing(raws):
        assert raws[which] == raw
        reached.append("complete-digest-gate")
        raise PreparationReached()

    monkeypatch.setattr(module, "_preparation_documents", stop_before_parsing)
    with helpers._sentries(monkeypatch, module, parse=True, corpus=True):
        if extra == 0:
            with pytest.raises(PreparationReached):
                getattr(synthetic, operation)(module)
        else:
            with pytest.raises(
                module.FrontierInputsError, match="^frontier artifact exceeds bounds$",
            ):
                getattr(synthetic, operation)(module)
    assert len(reached) == int(extra == 0)
    assert not (synthetic.root / "produced.json").exists()


def test_equal_float_count_negative_control_reaches_assertion(synthetic, monkeypatch):
    _check(synthetic, synthetic.doc)
    doc = copy.deepcopy(synthetic.doc)
    doc["counts"]["planned"] = float(doc["counts"]["planned"])
    assert doc["counts"] == synthetic.doc["counts"]
    _count_refusal(synthetic, doc)
    real_integer = module._integer
    bypassed = []

    def allow_integral_float(value, lo=0, hi=10 ** 20 - 1):
        if type(value) is float and value.is_integer():
            bypassed.append(value)
            value = int(value)
        return real_integer(value, lo, hi)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_integer", allow_integral_float)
        with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
            _count_refusal(synthetic, doc)
    assert bypassed == [6.0]
