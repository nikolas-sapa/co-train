"""F01–F18, synthetic fixture admission, not scientific/training evidence.

Stage 1's API-absence RED was accepted before implementation. Preparation uses
real retained publishers/admission. New producer/consumer calls must run no SQL,
scoring, generation, framework or trainer. No external scratch helper dependency.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import importlib
import importlib.abc
import importlib.util
import inspect
import json
import os
from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Actual retained dependencies are imported before the deliberate call-phase RED.
from bench import fixture as corpus_fixture  # noqa: E402
from bench import loader, prepare, score, suite  # noqa: E402
from bench.frontier.probe import (  # noqa: E402
    ProbeResult, dead_group_fraction, trainable_band,
)
from train import guards  # noqa: E402


EXTRA_SOURCES = {
    "bench/frontier/__init__.py", "bench/frontier/probe.py", "ptc/harness.py",
    "ptc/sql_arms.py", "ptc/sql_runtime.py", "train/__init__.py",
    "train/dead_group_probe.py", "train/ex_reward.py", "train/frontier_inputs.py",
    "train/grpo_ptc.py", "train/guards.py", "train/native_model.py",
    "train/native_runtime.py", "train/native_training.py", "train/sql_bridge.py",
    "train/verdict.py",
}
SOURCE_PATHS = tuple(sorted(set(prepare.SOURCE_KEYS) | EXTRA_SOURCES))
IDENTITY = {
    "policy": {
        "id": "synthetic-fixture-policy", "revision": "fixture-revision-1",
        "artifact_inventory_sha256": "1" * 64, "adapter_sha256": None,
    },
    "runtime": {
        "id": "synthetic-fixture-runtime", "revision": "fixture-runtime-1",
        "environment_sha256": "2" * 64,
    },
    "template": {
        "tokenizer_inventory_sha256": "3" * 64, "chat_template_sha256": "4" * 64,
        "renderer_sha256": "5" * 64, "tool_schema_sha256": "6" * 64,
    },
    "generation_route_id": "synthetic-records-no-generation",
    "generation_config_sha256": "7" * 64, "prompt_config_sha256": "8" * 64,
}
RAW_PIN = "9" * 64
AMENDMENT = "A8"
G = 4
CEILING = 0.6
FULL = {"simple": 2, "moderate": 3, "challenging": 3}
FRAMEWORKS = {
    "torch", "trl", "transformers", "unsloth", "verifiers", "openai",
    "anthropic", "litellm", "vllm",
}
FORBIDDEN_PROJECT_IMPORTS = {
    "train.native_model", "train.native_runtime", "train.native_training",
    "train.grpo_ptc", "ptc.sql_arms", "ptc.sql_runtime",
}


class _NoFramework(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in FRAMEWORKS or fullname in FORBIDDEN_PROJECT_IMPORTS:
            raise AssertionError("forbidden runtime/framework import: " + fullname)
        return None


@pytest.fixture(autouse=True)
def offline_framework_guard(monkeypatch):
    finder = _NoFramework()
    sys.meta_path.insert(0, finder)

    def denied(*args, **kwargs):
        raise AssertionError("external network is forbidden")

    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


def _api():
    spec = importlib.util.find_spec("train.frontier_inputs")
    assert spec is not None, (
        "F00 intended RED: actual train.frontier_inputs module/API is missing"
    )
    module = importlib.import_module("train.frontier_inputs")
    for name in ("write_fixture_frontier_sidecar", "load_fixture_frontier_inputs"):
        assert callable(getattr(module, name, None)), "missing actual API: " + name
    return module


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _slot(index, status):
    valid = status not in score.INVALID_STATUSES
    if status == "not_attempted_after_void":
        return dict(index=index, status=status, valid=None, score=None,
                    evidence_sha256=None)
    return dict(index=index, status=status, valid=valid,
                score=int(status == "match") if valid else None,
                evidence_sha256=_sha(f"synthetic-evidence-{index}-{status}".encode()))


def _records(admitted, retained=None, void=True):
    records = []
    for i, task in enumerate(admitted.eligible):
        if void and i == len(admitted.eligible) - 1:
            statuses = ["match", "mismatch", "gold_error", "not_attempted_after_void"]
        else:
            wins = (i % 3) + 1 if retained is None or i < retained else 0
            statuses = ["match"] * wins + ["mismatch"] * (G - wins)
        records.append({
            "id": task.name, "prompt_sha256": _sha(f"public-prompt-{i}".encode()),
            "samples": [_slot(j, status) for j, status in enumerate(statuses)],
        })
    return records


def _document(admitted, records, pins):
    by_id = {r["id"]: r for r in records}
    exclusions = {e.id: e for e in admitted.exclusions}
    ledger, rates, retained, voids = [], {}, [], {}
    for task in admitted.planned:
        entry = dict(
            id=task.name, task_sha256=prepare._task_sha256(task),
            db_id=task.db_id, tier=task.tier, state="preparation_excluded",
            exclusion=None, prompt_sha256=None, samples=[], successes=None,
            rate=None, retained=False,
        )
        if task.name in exclusions:
            e = exclusions[task.name]
            entry["exclusion"] = {"status": e.status, "category": e.category}
        else:
            record = by_id[task.name]
            slots = copy.deepcopy(record["samples"])
            entry.update(prompt_sha256=record["prompt_sha256"], samples=slots)
            invalid = [s for s in slots if s["valid"] is False]
            if invalid:
                entry["state"] = "measurement_void"
                voids[task.name] = invalid[0]["status"]
            else:
                wins = sum(s["score"] for s in slots)
                rate = wins / G
                keep = dead_group_fraction(rate, G) <= CEILING
                entry.update(state="measured", successes=wins, rate=rate, retained=keep)
                rates[task.name] = rate
                if keep:
                    retained.append(task.name)
        ledger.append(entry)
    lo, hi = trainable_band(CEILING, G)
    probe = ProbeResult(
        policy=IDENTITY["policy"]["id"], g=G, dead_ceiling=CEILING,
        band_lo=lo, band_hi=hi, rates=rates, retained=retained, void=voids,
        compare="set",
    )
    counts = dict(
        planned=len(admitted.planned), preparation_excluded=len(exclusions),
        eligible=len(admitted.eligible), measured=len(rates), measurement_void=len(voids),
        retained=len(retained), sample_slots=len(admitted.eligible) * G,
        attempted_samples=sum(s["status"] != "not_attempted_after_void"
                              for c in ledger for s in c["samples"]),
    )
    return dict(
        kind="cotrain-frontier-sidecar", version=1, fixture=True,
        evidence_kind="synthetic_fixture", run_id="synthetic-run-1",
        manifest_sha256=pins["manifest"], draw_sha256=pins["draw"],
        supplement_sha256=pins["supplement"], raw_evidence_sha256=RAW_PIN,
        identity=copy.deepcopy(IDENTITY),
        settings=dict(g=G, dead_ceiling=CEILING, comparison="set",
                      scorer="bench.score.execution_accuracy", extractor="bench.score.extract_sql",
                      timeout_s=admitted.timeout_s, max_rows=admitted.max_rows),
        sources={p: _sha((REPO / p).read_bytes()) for p in SOURCE_PATHS},
        candidates=ledger, diagnostic=probe.report(), counts=counts,
    ), probe


@dataclasses.dataclass
class _Fixture:
    root: Path
    corpus: Path
    draw: Path
    supplement: Path
    manifest: Path
    sidecar: Path
    pins: dict
    admitted: object
    records: list
    doc: dict

    def load_kwargs(self):
        return dict(
            expected_draw_sha256=self.pins["draw"],
            expected_supplement_sha256=self.pins["supplement"],
            expected_manifest_sha256=self.pins["manifest"],
            expected_sidecar_sha256=self.pins["sidecar"],
            expected_raw_evidence_sha256=RAW_PIN,
            expected_identity=copy.deepcopy(IDENTITY), expected_amendment=AMENDMENT,
            expected_g=G, expected_dead_ceiling=CEILING, fixture=True,
        )

    def load(self, module, **overrides):
        kw = self.load_kwargs()
        kw.update(overrides)
        return module.load_fixture_frontier_inputs(
            self.root, self.corpus, self.draw, self.supplement, self.manifest,
            self.sidecar, **kw,
        )

    def produce(self, module, output=None, **overrides):
        kw = self.load_kwargs()
        for key in ("expected_sidecar_sha256", "expected_g", "expected_dead_ceiling"):
            kw.pop(key)
        kw.update(samples=copy.deepcopy(self.records), run_id="synthetic-run-1",
                  g=G, dead_ceiling=CEILING)
        kw.update(overrides)
        return module.write_fixture_frontier_sidecar(
            self.root, self.corpus, self.draw, self.supplement, self.manifest,
            self.root / "produced.json" if output is None else output, **kw,
        )

    def rewrite(self, doc=None, raw=None, which="sidecar"):
        path = getattr(self, which)
        if raw is None:
            raw = _canonical(self.doc if doc is None else doc)
        path.write_bytes(raw)
        self.pins[which] = _sha(raw)


def _stage(tmp_path, *, n=None, retained=None, void=True, exclude=True, boundary_id=False):
    """Real fixture SQL only here, then real immutable preparation admission."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    corpus = corpus_fixture.materialize(tmp_path / "corpus")
    records = corpus_fixture.records()
    if n is not None:
        # Distinct task IDs over the same real fixture DB, no fabricated admission.
        original = records
        records = [{**original[i % len(original)], "question_id": i} for i in range(n)]
    records = copy.deepcopy(records)
    records[0]["question"] = "QUESTION_SENTINEL_DO_NOT_SERIALIZE"
    records[0]["evidence"] = "EVIDENCE_SENTINEL_DO_NOT_SERIALIZE"
    if boundary_id:
        # The real BIRD loader makes "bird-" + 251 decimal digits, exactly 256
        # bytes. A decimal STRING is corpus metadata, not an oversized JSON
        # numeric token in a retained preparation document.
        records[1]["question_id"] = "1" * 251
        records[1]["question"] = "ordinary question text " * 40
        records[1]["evidence"] = "ordinary evidence text " * 40
    if exclude:
        records[0]["SQL"] = "SELECT * FROM absent_GOLD_SENTINEL"
    (corpus / "dev.json").write_text(json.dumps(records), encoding="utf-8")
    tiers = Counter(r["difficulty"] for r in records)
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    draw_sha = prepare.freeze_draw(
        corpus, draw, seed=0, per_tier={t: tiers[t] for t in FULL},
        fixture=True, timeout_s=30.0, max_rows=500000,
    )
    supp_sha = prepare.validate_draw(
        corpus, draw, supplement, expected_draw_sha256=draw_sha,
    )
    admitted = prepare.load_validated_draw(
        corpus, draw, supplement, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supp_sha, fixture=True,
    )
    samples = _records(admitted, retained=retained, void=void)
    manifest, sidecar = tmp_path / "legacy-fixture.json", tmp_path / "sidecar.json"
    pins = {"draw": draw_sha, "supplement": supp_sha, "manifest": "0" * 64}
    doc, probe = _document(admitted, samples, pins)
    # Only a noncanonical, caller-owned legacy fixture. NEVER write_manifest().
    manifest.write_text(json.dumps(probe.manifest(AMENDMENT), indent=2) + "\n")
    pins["manifest"] = _sha(manifest.read_bytes())
    doc["manifest_sha256"] = pins["manifest"]
    sidecar.write_bytes(_canonical(doc))
    pins["sidecar"] = _sha(sidecar.read_bytes())
    return _Fixture(tmp_path, corpus, draw, supplement, manifest, sidecar,
                    pins, admitted, samples, doc)


def _patch_aliases(monkeypatch, modules, original, replacement):
    for module in modules:
        for name, value in list(vars(module).items()):
            if value is original:
                monkeypatch.setattr(module, name, replacement)


@contextmanager
def _sentries(monkeypatch, module, *, parse=False, corpus=False):
    """Install AFTER fixture setup. Admission may read/hash DBs, not execute SQL."""
    seen = Counter()
    modules = [module, prepare, score, suite, loader,
               importlib.import_module("bench.frontier.probe")]

    def trap(name):
        def denied(*args, **kwargs):
            seen[name] += 1
            raise AssertionError("forbidden project call: " + name)
        return denied

    targets = [
        (sqlite3, "connect"), (score, "execution_accuracy"),
        (score, "extract_sql"), (score, "validate_golds"), (suite, "select"),
        (importlib.import_module("bench.frontier.probe"), "write_manifest"),
    ]
    if parse:
        targets.extend([(json, "loads"), (json, "load")])
    if corpus:
        targets.extend([(loader, "load_bird"), (prepare, "_corpus")])
    with monkeypatch.context() as patch:
        for owner, name in targets:
            real = getattr(owner, name)
            replacement = trap(name)
            _patch_aliases(patch, modules, real, replacement)
            patch.setattr(owner, name, replacement)
        yield seen
    assert not seen, seen


def _refuse(call):
    with pytest.raises(_api().FrontierInputsError) as caught:
        call()
    assert 0 < len(str(caught.value)) <= 2048
    for sentinel in ("QUESTION_SENTINEL", "EVIDENCE_SENTINEL", "GOLD_SENTINEL",
                     "RAW_ERROR_SENTINEL"):
        assert sentinel not in str(caught.value)
    return caught.value


def _plain(value):
    if dataclasses.is_dataclass(value):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _assert_frozen(value):
    assert not isinstance(value, (dict, list, set, bytearray))
    if dataclasses.is_dataclass(value):
        assert value.__dataclass_params__.frozen
        for f in dataclasses.fields(value):
            _assert_frozen(getattr(value, f.name))
    elif isinstance(value, Mapping):
        for item in value.values():
            _assert_frozen(item)
        with pytest.raises(TypeError):
            value["__mutation__"] = 1
    elif isinstance(value, tuple):
        for item in value:
            _assert_frozen(item)
    assert not callable(value)


def test_F00_missing_actual_api_call_phase():
    """RED only: existing imports succeed; absence is an assertion in TEST call."""
    assert callable(prepare.freeze_draw)
    assert callable(prepare.load_validated_draw)
    assert callable(ProbeResult.manifest)
    assert guards.MIN_FRONTIER_TASKS == 59
    module = _api()
    for name, fields in {
        "write_fixture_frontier_sidecar": {"samples", "fixture", "expected_identity"},
        "load_fixture_frontier_inputs": {"expected_sidecar_sha256", "fixture", "expected_g"},
    }.items():
        assert fields <= set(inspect.signature(getattr(module, name)).parameters)
    assert {f.name for f in dataclasses.fields(module.FixtureFrontierInputs)} == {
        "planned", "eligible", "retained", "preparation_exclusions",
        "measurement_voids", "artifact_digests", "raw_evidence_sha256",
        "counts", "diagnostic", "count_qualified", "fixture",
    }
    assert issubclass(module.FrontierInputsError, ValueError)
    assert issubclass(module.FrontierPublicationIndeterminateError, module.FrontierInputsError)


@pytest.mark.parametrize("which", ["draw", "supplement", "manifest", "sidecar"])
@pytest.mark.parametrize("defect", ["changed-bytes", "wrong-digest"])
def test_F01_four_digests_before_zero_parses_or_corpus(tmp_path, monkeypatch, which, defect):
    module, fx = _api(), _stage(tmp_path)
    if defect == "changed-bytes":
        path = getattr(fx, which)
        path.write_bytes(path.read_bytes() + b" ")
    else:
        fx.pins[which] = "0" * 64
    with _sentries(monkeypatch, module, parse=True, corpus=True):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("which", ["draw", "supplement", "manifest"])
@pytest.mark.parametrize("defect", ["changed-bytes", "wrong-digest"])
def test_F01_producer_three_digests_before_zero_parses(tmp_path, monkeypatch, which, defect):
    module, fx = _api(), _stage(tmp_path)
    if defect == "changed-bytes":
        path = getattr(fx, which)
        path.write_bytes(path.read_bytes() + b" ")
    else:
        fx.pins[which] = "0" * 64
    with _sentries(monkeypatch, module, parse=True, corpus=True):
        _refuse(lambda: fx.produce(module))
    assert not (tmp_path / "produced.json").exists()


# Every schema object level, including dynamic maps and nested sample objects.
OBJECT_PATHS = [
    (), ("identity",), ("identity", "policy"), ("identity", "runtime"),
    ("identity", "template"), ("settings",), ("sources",),
    ("candidates", 0), ("candidates", "excluded", "exclusion"),
    ("candidates", "measured", "samples", 0), ("diagnostic",),
    ("diagnostic", "rates"), ("diagnostic", "void"), ("counts",),
]


def _at(doc, path):
    value = doc
    for key in path:
        if key in ("excluded", "measured"):
            state = "preparation_excluded" if key == "excluded" else "measured"
            value = next(c for c in value if c["state"] == state)
        else:
            value = value[key]
    return value


@pytest.mark.parametrize("path", OBJECT_PATHS, ids=lambda p: ".".join(map(str, p)) or "top")
@pytest.mark.parametrize("defect", ["unknown", "missing", "duplicate"])
def test_F02_exact_keys_every_object_level(tmp_path, monkeypatch, path, defect):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    target = _at(doc, path)
    if defect == "unknown":
        target["UNKNOWN_FIELD"] = 1
    elif defect == "missing":
        target.pop(next(iter(target)))
    else:
        key = next(iter(target))
        unique = "__DUPLICATE_OBJECT_MARKER__"
        target[unique] = target[key]
        # Same-level duplicate, not a duplicate manufactured in another object.
        raw = _canonical(doc).replace(
            json.dumps(unique).encode() + b":", json.dumps(key).encode() + b":", 1,
        )
        fx.rewrite(raw=raw)
    if defect != "duplicate":
        fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("path", [(), ("measurement",)], ids=["top", "measurement"])
@pytest.mark.parametrize("defect", ["unknown", "missing", "duplicate"])
def test_F02_legacy_manifest_exact_object_keys(tmp_path, monkeypatch, path, defect):
    module, fx = _api(), _stage(tmp_path)
    manifest = json.loads(fx.manifest.read_bytes())
    target = _at(manifest, path)
    key = next(iter(target))
    if defect == "unknown":
        target["UNKNOWN_FIELD"] = 1
    elif defect == "missing":
        target.pop(key)
    else:
        target["__DUPLICATE_MARKER__"] = target[key]
    raw = _canonical(manifest)
    if defect == "duplicate":
        raw = raw.replace(b'"__DUPLICATE_MARKER__":', json.dumps(key).encode() + b":")
    fx.rewrite(raw=raw, which="manifest")
    doc = copy.deepcopy(fx.doc)
    doc["manifest_sha256"] = fx.pins["manifest"]
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("case", [
    "noncanonical", "utf8", "nan", "infinity", "negative-infinity",
    "bool-version", "bool-g", "bool-count", "float-count", "bool-score",
    "float-index", "numeric-129", "integer-21", "depth-33",
])
def test_F02_strict_encoding_types_and_lexical_bounds(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    measured = _at(doc, ("candidates", "measured"))
    if case == "noncanonical":
        raw = json.dumps(doc, indent=2).encode()
    elif case == "utf8":
        raw = b"\xff" + _canonical(doc)
    elif case in ("nan", "infinity", "negative-infinity"):
        token = {"nan": b"NaN", "infinity": b"Infinity",
                 "negative-infinity": b"-Infinity"}[case]
        raw = _canonical(doc).replace(b'"dead_ceiling":0.6', b'"dead_ceiling":' + token, 1)
    elif case in ("numeric-129", "integer-21"):
        token = b"1." + b"0" * 127 if case == "numeric-129" else b"1" * 21
        raw = _canonical(doc).replace(b'"version":1', b'"version":' + token, 1)
    elif case == "depth-33":
        raw = b"[" * 33 + b"0" + b"]" * 33
    else:
        if case == "bool-version":
            doc["version"] = True
        elif case == "bool-g":
            doc["settings"]["g"] = True
        elif case == "bool-count":
            doc["counts"]["planned"] = True
        elif case == "float-count":
            doc["counts"]["planned"] = 8.0
        elif case == "bool-score":
            measured["samples"][0]["score"] = True
        else:
            measured["samples"][0]["index"] = 0.0
        raw = _canonical(doc)
    fx.rewrite(raw=raw)
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: fx.load(module))


def test_F03_F04_complete_8_1_6_1_ledger_G4_28_slots_27_attempts(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    with _sentries(monkeypatch, module):
        result = fx.load(module)
    assert len(result.planned) == 8
    assert len(result.eligible) == 7
    assert result.planned == fx.admitted.planned
    assert result.eligible == fx.admitted.eligible
    assert _plain(result.counts) == {
        "planned": 8, "preparation_excluded": 1, "eligible": 7, "measured": 6,
        "measurement_void": 1, "retained": 6, "sample_slots": 28,
        "attempted_samples": 27,
    }
    assert _plain(result.diagnostic) == fx.doc["diagnostic"]
    assert result.preparation_exclusions == fx.admitted.exclusions
    assert type(result.preparation_exclusions) is tuple
    assert result.measurement_voids == (
        module.FrontierVoid(
            fx.admitted.eligible[-1].name, "gold_error", "gold_execution_rejection",
        ),
    )
    assert type(result.measurement_voids) is tuple
    assert dict(result.artifact_digests) == fx.pins
    assert result.raw_evidence_sha256 == RAW_PIN
    assert [c["id"] for c in fx.doc["candidates"]] == [t.name for t in result.planned]
    void = next(c for c in fx.doc["candidates"] if c["state"] == "measurement_void")
    assert void["rate"] is void["successes"] is None
    assert [s["status"] for s in void["samples"]] == [
        "match", "mismatch", "gold_error", "not_attempted_after_void",
    ]
    _assert_frozen(result)


def test_F03_producer_consumer_real_prepare_roundtrip_27_attempted(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    manifest_before = fx.manifest.read_bytes()
    with _sentries(monkeypatch, module):
        digest = fx.produce(module)
    produced = tmp_path / "produced.json"
    assert digest == _sha(produced.read_bytes())
    assert json.loads(produced.read_bytes()) == fx.doc
    fx.sidecar, fx.pins["sidecar"] = produced, digest
    with _sentries(monkeypatch, module):
        result = fx.load(module)
    assert _plain(result.counts)["attempted_samples"] == 27
    assert fx.manifest.read_bytes() == manifest_before


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "reordered",
                                 "excluded", "missing-prompt", "null-prompt", "bad-prompt",
                                 "extra-summary", "callback"])
def test_F04_producer_corrected_eligible_record_schema(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    records = copy.deepcopy(fx.records)
    if case == "missing":
        records.pop()
    elif case == "extra":
        records.append({**records[0], "id": "unknown-eligible"})
    elif case == "duplicate":
        records[-1] = copy.deepcopy(records[0])
    elif case == "reordered":
        records.reverse()
    elif case == "excluded":
        records[0]["id"] = fx.admitted.exclusions[0].id
    elif case == "missing-prompt":
        records[0].pop("prompt_sha256")
    elif case == "null-prompt":
        records[0]["prompt_sha256"] = None
    elif case == "bad-prompt":
        records[0]["prompt_sha256"] = "A" * 64
    elif case == "extra-summary":
        records[0]["successes"] = 4
    else:
        records[0]["samples"] = lambda: pytest.fail("callback invoked")
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.produce(module, samples=records))
    assert not (tmp_path / "produced.json").exists()


def test_F04_producer_snapshots_mutable_records_before_admission(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    records = copy.deepcopy(fx.records)
    real = prepare.load_validated_draw
    calls = []

    def mutate_after_snapshot(*args, **kwargs):
        calls.append(1)
        records[0]["prompt_sha256"] = "0" * 64
        records[0]["samples"][0]["score"] = 99
        return real(*args, **kwargs)

    _patch_aliases(monkeypatch, [module, prepare], real, mutate_after_snapshot)
    with _sentries(monkeypatch, module):
        digest = fx.produce(module, samples=records)
    assert calls
    raw = (tmp_path / "produced.json").read_bytes()
    assert digest == _sha(raw)
    assert json.loads(raw) == fx.doc


@pytest.mark.parametrize("level", ["record", "slot"])
@pytest.mark.parametrize("defect", ["unknown", "missing"])
def test_F04_producer_record_and_slot_exact_keys(tmp_path, monkeypatch, level, defect):
    module, fx = _api(), _stage(tmp_path)
    records = copy.deepcopy(fx.records)
    node = records[0] if level == "record" else records[0]["samples"][0]
    if defect == "unknown":
        node["RAW_ERROR_SENTINEL"] = "RAW_ERROR_SENTINEL"
    else:
        node.pop(next(iter(node)))
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.produce(module, samples=records))
    assert not (tmp_path / "produced.json").exists()


@pytest.mark.parametrize("case", ["include", "exclude", "reorder", "duplicate"])
def test_F05_retained_membership_exact_and_ordered(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    ids = doc["diagnostic"]["retained"]
    if case == "include":
        ids.append(next(c["id"] for c in doc["candidates"] if c["state"] == "measurement_void"))
    elif case == "exclude":
        ids.pop()
    elif case == "reorder":
        ids.reverse()
    else:
        ids.append(ids[0])
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module))


def test_F05_projects_original_retained_SqlTask_values(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    with _sentries(monkeypatch, module):
        result = fx.load(module)
    expected = tuple(t for t in fx.admitted.planned
                     if t.name in fx.doc["diagnostic"]["retained"])
    assert type(result.retained) is tuple
    assert result.retained == expected
    for actual, original in zip(result.retained, expected):
        assert dataclasses.asdict(actual) == dataclasses.asdict(original)


@pytest.mark.parametrize("case", [
    "score", "validity", "status", "rate", "successes", "diagnostic-void",
    "retained-flag", "count", "missing-slot", "duplicate-index",
    "attempt-after-void", "two-invalid", "void-rate-zero", "excluded-sample",
    "no-evidence", "unattempted-evidence", "db-missing",
])
def test_F06_independent_ledger_and_diagnostic_corruptions(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    c = _at(doc, ("candidates", "measured"))
    v = next(c for c in doc["candidates"] if c["state"] == "measurement_void")
    if case == "score":
        c["samples"][0]["score"] = 0 if c["samples"][0]["score"] else 1
    elif case == "validity":
        c["samples"][0]["valid"] = False
    elif case == "status":
        c["samples"][0]["status"] = "invented-success"
    elif case == "rate":
        c["rate"] += 0.01
    elif case == "successes":
        c["successes"] += 1
    elif case == "diagnostic-void":
        doc["diagnostic"]["void"] = {}
    elif case == "retained-flag":
        c["retained"] = not c["retained"]
    elif case == "count":
        doc["counts"]["attempted_samples"] = 28
    elif case == "missing-slot":
        c["samples"].pop()
    elif case == "duplicate-index":
        c["samples"][1]["index"] = 0
    elif case == "attempt-after-void":
        v["samples"][3] = _slot(3, "match")
    elif case == "two-invalid":
        v["samples"][1] = _slot(1, "gold_timeout")
    elif case == "void-rate-zero":
        v["rate"] = 0
    elif case == "excluded-sample":
        _at(doc, ("candidates", "excluded"))["samples"] = [_slot(0, "match")]
    elif case == "no-evidence":
        c["samples"][0]["evidence_sha256"] = None
    elif case == "unattempted-evidence":
        v["samples"][3]["evidence_sha256"] = "1" * 64
    else:
        v["samples"][2]["status"] = "db_missing"
        doc["diagnostic"]["void"][v["id"]] = "db_missing"
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("status", ["mismatch", "pred_error", "pred_timeout",
                                  "pred_truncated", "pred_empty"])
def test_F06_real_scorer_valid_zero_statuses_not_void(tmp_path, monkeypatch, status):
    module, fx = _api(), _stage(tmp_path)
    assert status not in score.INVALID_STATUSES
    records = copy.deepcopy(fx.records)
    # Retain one success and three valid failures regardless of failure category.
    records[0]["samples"] = [_slot(0, "match")] + [_slot(j, status) for j in range(1, G)]
    doc, probe = _document(fx.admitted, records, fx.pins)
    fx.rewrite(probe.manifest(AMENDMENT), which="manifest")
    doc["manifest_sha256"] = fx.pins["manifest"]
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        result = fx.load(module)
    assert _plain(result.diagnostic)["rates"][records[0]["id"]] == 0.25
    assert _plain(result.counts)["measurement_void"] == 1


@pytest.mark.parametrize("field", [
    "planned", "preparation_excluded", "eligible", "measured",
    "measurement_void", "retained", "sample_slots", "attempted_samples",
])
@pytest.mark.parametrize("value", [True, 1.0, -1])
def test_F06_every_count_exact_nonnegative_int(tmp_path, monkeypatch, field, value):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    doc["counts"][field] = value
    fx.rewrite(doc)
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: fx.load(module))


IDENTITY_PATHS = [
    ("policy", "id"), ("policy", "revision"), ("policy", "artifact_inventory_sha256"),
    ("policy", "adapter_sha256"), ("runtime", "id"), ("runtime", "revision"),
    ("runtime", "environment_sha256"), ("template", "tokenizer_inventory_sha256"),
    ("template", "chat_template_sha256"), ("template", "renderer_sha256"),
    ("template", "tool_schema_sha256"), ("generation_route_id",),
    ("generation_config_sha256",), ("prompt_config_sha256",),
]


@pytest.mark.parametrize("path", IDENTITY_PATHS, ids=lambda p: ".".join(p))
def test_F07_complete_independent_identity_no_defaults(tmp_path, monkeypatch, path):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    parent = _at(doc["identity"], path[:-1])
    key = path[-1]
    parent[key] = "a" * 64 if key.endswith("sha256") else "different-fixture-identity"
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("case", ["draw", "supplement", "manifest", "raw", "task",
                                 "g", "ceiling", "amendment", "source-missing",
                                 "source-extra", "source-hash"])
def test_F07_independent_pins_settings_task_and_fixed_sources(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    kw = {}
    if case in ("draw", "supplement", "manifest", "raw"):
        doc[{"raw": "raw_evidence_sha256"}.get(case, case + "_sha256")] = "0" * 64
    elif case == "task":
        doc["candidates"][0]["task_sha256"] = "0" * 64
    elif case == "g":
        kw["expected_g"] = 8
    elif case == "ceiling":
        kw["expected_dead_ceiling"] = 0.5
    elif case == "amendment":
        kw["expected_amendment"] = "UNSIGNED_SYNTHETIC_NO_APPROVAL"
    elif case == "source-missing":
        doc["sources"].pop(SOURCE_PATHS[0])
    elif case == "source-extra":
        doc["sources"]["../outside.py"] = "0" * 64
    else:
        doc["sources"][SOURCE_PATHS[0]] = "0" * 64
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module, **kw))


@pytest.mark.parametrize("retained,n,qualified", [(59, 198, True), (58, 198, False)])
def test_F08_synthetic_count_gate_59_58_no_retention_floor(
        tmp_path, monkeypatch, retained, n, qualified):
    module = _api()
    fx = _stage(tmp_path, n=n, retained=retained, void=False, exclude=False)
    with _sentries(monkeypatch, module):
        result = fx.load(module)
    assert guards.MIN_FRONTIER_TASKS == 59
    assert len(result.retained) == retained
    assert result.count_qualified is qualified
    assert result.fixture is True
    assert not hasattr(result, "training_authorized")
    assert _plain(result.counts)["measured"] == n


def test_F08_existing_guard_only_198_of_19800_no_retention_floor(tmp_path):
    """Count policy only. No full 19,800-task artifact/projection is claimed."""
    lo, hi = trainable_band(CEILING, G)
    probe = ProbeResult(
        policy=IDENTITY["policy"]["id"], g=G, dead_ceiling=CEILING,
        band_lo=lo, band_hi=hi, rates={"synthetic": 0.5}, retained=["synthetic"],
    )
    manifest = probe.manifest(AMENDMENT)
    manifest["n_tasks"] = 198
    manifest["measurement"].update(n_candidates=19800, retention=198 / 19800)
    path = tmp_path / guards.FRONTIER_MANIFEST
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest))
    (tmp_path / "docs").mkdir()
    shutil.copyfile(REPO / "docs/pre-registration.md", tmp_path / "docs/pre-registration.md")
    assert guards.frontier_taskset_status(tmp_path) == guards.Precondition(True, ())


@pytest.mark.parametrize("field", ["trainable_band", "retention"])
@pytest.mark.parametrize("delta,accept", [(0.5e-6, True), (2e-6, False)])
def test_F09_existing_manifest_tolerance_only(tmp_path, monkeypatch, field, delta, accept):
    module, fx = _api(), _stage(tmp_path)
    manifest = json.loads(fx.manifest.read_bytes())
    if field == "trainable_band":
        manifest["measurement"][field][0] += delta
    else:
        # Stay <=1 so bounds do not mask the existing tolerance.
        manifest["measurement"][field] -= delta
    fx.rewrite(manifest, which="manifest")
    doc = copy.deepcopy(fx.doc)
    doc["manifest_sha256"] = fx.pins["manifest"]
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        if accept:
            assert fx.load(module).fixture is True
        else:
            _refuse(lambda: fx.load(module))


def test_F09_retention_inequality_never_expanded_by_tolerance(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    # p=.25 gives dead fraction .3203125 exactly. Declared threshold is lower.
    ceiling = dead_group_fraction(0.25, G) - 0.5e-6
    doc = copy.deepcopy(fx.doc)
    doc["settings"]["dead_ceiling"] = ceiling
    lo, hi = trainable_band(ceiling, G)
    diagnostic = doc["diagnostic"]
    probe = ProbeResult(
        policy=diagnostic["policy"], g=G, dead_ceiling=ceiling,
        band_lo=lo, band_hi=hi, rates=diagnostic["rates"],
        retained=diagnostic["retained"], void=diagnostic["void"], compare="set",
    )
    doc["diagnostic"] = probe.report()
    fx.rewrite(probe.manifest(AMENDMENT), which="manifest")
    doc["manifest_sha256"] = fx.pins["manifest"]
    # A tolerance-expanded <= check would wrongly retain p=.25/.75.
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module, expected_dead_ceiling=ceiling))


@pytest.mark.parametrize("status", ["gold_error", "gold_timeout", "gold_truncated"])
def test_F10_invalid_gold_after_two_attempts_preserves_prefix_no_rate(
        tmp_path, monkeypatch, status):
    module, fx = _api(), _stage(tmp_path)
    records = copy.deepcopy(fx.records)
    records[-1]["samples"][2] = _slot(2, status)
    doc, probe = _document(fx.admitted, records, fx.pins)
    fx.rewrite(probe.manifest(AMENDMENT), which="manifest")
    doc["manifest_sha256"] = fx.pins["manifest"]
    fx.rewrite(doc)
    with _sentries(monkeypatch, module):
        result = fx.load(module)
    diagnostic = _plain(result.diagnostic)
    victim = fx.admitted.eligible[-1].name
    assert victim not in diagnostic["rates"]
    assert diagnostic["void"] == {victim: status}
    assert _plain(result.counts)["attempted_samples"] == 27


def test_F11_two_equal_frozen_loads_zero_writes_SQL_selection(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    publications = []

    def trap(*args, **kwargs):
        publications.append(1)
        raise AssertionError("consumer publication")

    with monkeypatch.context() as patch:
        for name in ("link", "rename", "replace", "mkdir"):
            patch.setattr(os, name, trap)
        with _sentries(patch, module):
            first, second = fx.load(module), fx.load(module)
    assert first == second
    _assert_frozen(first)
    assert not publications
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    assert dict(first.artifact_digests) == fx.pins
    assert first.raw_evidence_sha256 == RAW_PIN


def test_F11_return_has_owned_recursive_backing(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    identity = copy.deepcopy(IDENTITY)
    with _sentries(monkeypatch, module):
        result = fx.load(module, expected_identity=identity)
    before = _plain(result)
    identity["policy"]["id"] = "caller-mutated"
    fx.pins["sidecar"] = "0" * 64
    fx.doc["diagnostic"]["rates"].clear()
    fx.doc["counts"]["planned"] = 999
    assert _plain(result) == before
    for mapping in (result.counts, result.diagnostic, result.artifact_digests,
                    result.diagnostic["rates"], result.diagnostic["void"]):
        with pytest.raises(TypeError):
            mapping["mutate"] = "forbidden"
    assert type(result.diagnostic["retained"]) is tuple


@pytest.mark.parametrize("drift", ["task", "database", "db-sidecar", "draw",
                                 "supplement", "manifest", "sidecar"])
def test_F12_drift_after_first_admission_zero_success(tmp_path, monkeypatch, drift):
    module, fx = _api(), _stage(tmp_path)
    real = prepare.load_validated_draw
    calls = []

    def drifting(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append(1)
        if len(calls) == 1:
            if drift == "task":
                records = json.loads((fx.corpus / "dev.json").read_bytes())
                records[0]["question"] += " drift"
                (fx.corpus / "dev.json").write_text(json.dumps(records))
            elif drift in ("database", "db-sidecar"):
                db = Path(fx.admitted.planned[0].db_path)
                if drift == "database":
                    db.write_bytes(db.read_bytes() + b"drift")
                else:
                    Path(str(db) + "-wal").write_bytes(b"")
            else:
                path = getattr(fx, drift)
                path.write_bytes(path.read_bytes() + b" ")
        return result

    _patch_aliases(monkeypatch, [prepare, module], real, drifting)
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.load(module))
    assert calls


@pytest.mark.parametrize("case", ["existing", "symlink", "concurrent",
                                 "precommit", "postcommit"])
def test_F13_create_only_publication_failure_boundaries(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    output = tmp_path / "publication.json"
    prior = b"PRIOR_BYTES_NEVER_OVERWRITE"
    target = tmp_path / "symlink-target"
    if case == "existing":
        output.write_bytes(prior)
    elif case == "symlink":
        target.write_bytes(prior)
        output.symlink_to(target)
    real_link, real_fsync = os.link, os.fsync
    commits = []

    def link(src, dst, *args, **kwargs):
        if Path(dst) == output:
            if case == "concurrent":
                output.write_bytes(prior)
            if case == "precommit":
                raise OSError("synthetic precommit")
            result = real_link(src, dst, *args, **kwargs)
            commits.append(1)
            return result
        return real_link(src, dst, *args, **kwargs)

    def fsync(fd):
        if case == "postcommit" and commits:
            raise OSError("synthetic postcommit")
        return real_fsync(fd)

    def no_overwrite(*args, **kwargs):
        raise AssertionError("overwrite-capable publication forbidden")

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", link)
        patch.setattr(os, "fsync", fsync)
        patch.setattr(os, "replace", no_overwrite)
        patch.setattr(os, "rename", no_overwrite)
        with _sentries(patch, module):
            with pytest.raises((ValueError, OSError)) as caught:
                fx.produce(module, output)
    if case in ("existing", "concurrent", "symlink"):
        assert output.read_bytes() == prior
        if case == "symlink":
            assert output.is_symlink() and target.read_bytes() == prior
    elif case == "precommit":
        assert not output.exists()
        assert not commits
    else:
        assert len(commits) == 1
        assert type(caught.value).__name__ == "FrontierPublicationIndeterminateError"
        assert "indeterminate" in str(caught.value).lower()
        assert json.loads(output.read_bytes()) == fx.doc
        assert output.read_bytes() == _canonical(fx.doc)


@pytest.mark.parametrize("which,limit", [("sidecar", 16 << 20), ("manifest", 64 << 10),
                                      ("draw", 16 << 20), ("supplement", 16 << 20)])
def test_F14_overflow_byte_before_zero_parses(tmp_path, monkeypatch, which, limit):
    module, fx = _api(), _stage(tmp_path)
    fx.rewrite(raw=b" " * (limit + 1), which=which)
    with _sentries(monkeypatch, module, parse=True, corpus=True):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("case", ["depth33", "number129", "integer21"])
@pytest.mark.parametrize("which", ["sidecar", "manifest", "draw", "supplement"])
def test_F14_lexical_preflight_before_zero_JSON_decodes(tmp_path, monkeypatch, case, which):
    module, fx = _api(), _stage(tmp_path)
    raw = {
        "depth33": b"[" * 33 + b"0" + b"]" * 33,
        "number129": b'{"x":1.' + b"0" * 127 + b"}",
        "integer21": b'{"x":' + b"1" * 21 + b"}",
    }[case]
    fx.rewrite(raw=raw, which=which)
    doc = copy.deepcopy(fx.doc)
    for artifact in ("manifest", "draw", "supplement"):
        doc[artifact + "_sha256"] = fx.pins[artifact]
    if which != "sidecar":
        fx.rewrite(doc)
    real_loads = json.loads
    decoded_target = []

    def checked_loads(data, *args, **kwargs):
        encoded = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if encoded == raw:
            decoded_target.append(1)
            raise AssertionError("oversized lexical token reached JSON decoder")
        return real_loads(data, *args, **kwargs)

    _patch_aliases(monkeypatch, [module, prepare], real_loads, checked_loads)
    monkeypatch.setattr(json, "loads", checked_loads)
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: fx.load(module))
    assert not decoded_target


@pytest.mark.parametrize("case", ["id-257", "id-utf8-258", "source-key-129",
                                 "planned-100001", "slots-1000001", "g-1",
                                 "g-bool", "ceiling-0", "ceiling-1", "timeout-0",
                                 "timeout-bool", "rows-0", "rows-bool", "run-id-empty"])
def test_F14_numeric_string_count_limits_before_corpus(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path)
    doc = copy.deepcopy(fx.doc)
    if case.startswith("id-"):
        doc["candidates"][0]["id"] = "x" * 257 if case == "id-257" else "é" * 129
    elif case == "source-key-129":
        doc["sources"]["x" * 129] = "0" * 64
    elif case == "planned-100001":
        doc["counts"]["planned"] = 100001
    elif case == "slots-1000001":
        doc["counts"]["sample_slots"] = 1000001
    elif case == "run-id-empty":
        doc["run_id"] = ""
    else:
        key, value = {
            "g-1": ("g", 1), "g-bool": ("g", True),
            "ceiling-0": ("dead_ceiling", 0), "ceiling-1": ("dead_ceiling", 1),
            "timeout-0": ("timeout_s", 0), "timeout-bool": ("timeout_s", True),
            "rows-0": ("max_rows", 0), "rows-bool": ("max_rows", True),
        }[case]
        doc["settings"][key] = value
    fx.rewrite(doc)
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("error", [RecursionError, OverflowError, MemoryError])
def test_F14_parser_resource_failures_neutral_domain_errors(tmp_path, monkeypatch, error):
    module, fx = _api(), _stage(tmp_path)
    real = json.loads
    calls = []

    def fault(*args, **kwargs):
        calls.append(1)
        raise error("RAW_ERROR_SENTINEL")

    _patch_aliases(monkeypatch, [module], real, fault)
    monkeypatch.setattr(json, "loads", fault)
    with _sentries(monkeypatch, module, corpus=True):
        caught = _refuse(lambda: fx.load(module))
    assert calls == [1]
    assert type(caught) is module.FrontierInputsError
    assert caught.__cause__ is None and caught.__suppress_context__


def test_F15_serialized_fixture_zero_private_text_SQL_paths_errors(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    with _sentries(monkeypatch, module):
        fx.produce(module)
    raw = (tmp_path / "produced.json").read_bytes()
    for sentinel in [
        b"QUESTION_SENTINEL", b"EVIDENCE_SENTINEL", b"GOLD_SENTINEL",
        b"RAW_ERROR_SENTINEL", b"SELECT ", str(tmp_path).encode(), str(REPO).encode(),
        b"/models/", b"gold_sql", b"db_path", b"completion", b"observation",
    ]:
        assert sentinel not in raw
    assert raw == _canonical(json.loads(raw))
    assert tuple(json.loads(raw)["sources"]) == SOURCE_PATHS


@pytest.mark.parametrize("opt_in", [False, None, 0, 1, "true"])
@pytest.mark.parametrize("operation", ["load", "produce"])
def test_F16_exact_fixture_opt_in_zero_runtime(tmp_path, monkeypatch, opt_in, operation):
    module, fx = _api(), _stage(tmp_path)
    with _sentries(monkeypatch, module, corpus=True):
        call = fx.load if operation == "load" else fx.produce
        _refuse(lambda: call(module, fixture=opt_in))


def test_F16_absent_opt_in_and_real_evidence_refuse(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    kw = fx.load_kwargs()
    kw.pop("fixture")
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: module.load_fixture_frontier_inputs(
            fx.root, fx.corpus, fx.draw, fx.supplement, fx.manifest, fx.sidecar, **kw,
        ))
    for key in ("expected_sidecar_sha256", "expected_g", "expected_dead_ceiling"):
        kw.pop(key)
    kw.update(samples=copy.deepcopy(fx.records), run_id="synthetic-run-1", g=G,
              dead_ceiling=CEILING)
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: module.write_fixture_frontier_sidecar(
            fx.root, fx.corpus, fx.draw, fx.supplement, fx.manifest,
            fx.root / "default-refused.json", **kw,
        ))
    assert not (fx.root / "default-refused.json").exists()
    doc = copy.deepcopy(fx.doc)
    doc["evidence_kind"] = "model_measurement"
    fx.rewrite(doc)
    with _sentries(monkeypatch, module, corpus=True):
        _refuse(lambda: fx.load(module))


@pytest.mark.parametrize("case", ["outside", "root-alias", "symlink-input",
                                 "hardlink-input", "symlink-parent",
                                 "canonical-output", "repository-root"])
def test_F16_protected_paths_no_canonical_writes(tmp_path, monkeypatch, case):
    module, fx = _api(), _stage(tmp_path / "fixture")
    canonical = REPO / "bench/frontier/manifest.json"
    before = canonical.read_bytes() if canonical.exists() else None
    if case == "outside":
        output = tmp_path / "outside.json"
    elif case == "root-alias":
        output = fx.draw
    elif case == "canonical-output":
        output = canonical
    elif case == "repository-root":
        fx.root = REPO
        output = tmp_path / "refused.json"
    elif case == "symlink-parent":
        alias = fx.root / "alias"
        alias.symlink_to(fx.root, target_is_directory=True)
        output = alias / "refused.json"
    else:
        alias = fx.root / "alias-draw.json"
        if case == "symlink-input":
            alias.symlink_to(fx.draw)
        else:
            os.link(fx.draw, alias)
        fx.draw = alias
        output = fx.root / "refused.json"
    original = fx.draw.read_bytes()
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.produce(module, output))
        # Consumer has no output argument. Only malformed INPUT paths/root apply.
        if case in ("symlink-input", "hardlink-input", "repository-root"):
            _refuse(lambda: fx.load(module))
    assert fx.draw.read_bytes() == original
    assert (canonical.read_bytes() if canonical.exists() else None) == before


def test_F16_other_repository_canonical_destination_refuses(tmp_path, monkeypatch):
    module, fx = _api(), _stage(tmp_path)
    other = tmp_path / "other-source"
    (other / "bench/frontier").mkdir(parents=True)
    (other / "train").mkdir()
    (other / "bench/prepare.py").write_text("# temporary repository marker\n")
    (other / "train/__init__.py").write_text("# temporary repository marker\n")
    output = other / "bench/frontier/manifest.json"
    with _sentries(monkeypatch, module):
        _refuse(lambda: fx.produce(module, output))
    assert not output.exists()


# Child guards are self-contained and run BEFORE pytest/project imports.
_CHILD_BOOT = r"""
import importlib.abc, os, socket, sys
sys.dont_write_bytecode = True
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "torch","trl","transformers","unsloth","verifiers","openai","anthropic",
            "litellm","vllm"
        } or fullname in {
            "train.native_model","train.native_runtime","train.native_training",
            "train.grpo_ptc","ptc.sql_arms","ptc.sql_runtime"
        }:
            raise RuntimeError("forbidden framework/runtime import")
        return None
sys.meta_path.insert(0, Deny())
def denied(*a, **k):
    raise RuntimeError("network forbidden")
for name in ("connect","connect_ex","bind","listen","sendto"):
    setattr(socket.socket, name, denied)
socket.getaddrinfo = socket.create_connection = denied
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
sys.path.insert(0, sys.argv[1])
import pytest
import hashlib, json, pathlib
class Receipt:
    def __init__(self):
        self.phases, self.warnings = [], []
    def pytest_runtest_logreport(self, report):
        self.phases.append({
            "nodeid":report.nodeid,"phase":report.when,"outcome":report.outcome,
            "failure":str(report.longrepr) if report.failed else None
        })
    def pytest_warning_recorded(self, warning_message, when, nodeid, location):
        self.warnings.append(str(warning_message.message))
receipt = Receipt()
code = pytest.main(sys.argv[2:], plugins=[receipt])
root = pathlib.Path(sys.argv[1])
print("CHILD_RECEIPT " + json.dumps({
    "exit":int(code), "optimized":sys.flags.optimize,
    "phases":receipt.phases, "warnings":receipt.warnings,
    "source":str(root / "train/frontier_inputs.py"),
    "source_sha256":hashlib.sha256((root / "train/frontier_inputs.py").read_bytes()).hexdigest(),
    "test_sha256":hashlib.sha256((root / "train/test_frontier_inputs.py").read_bytes()).hexdigest(),
    "pytest_args":sys.argv[2:], "interpreter":sys.executable
}))
raise SystemExit(int(code))
"""


def _child(repo, target, *, optimized=False):
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONDONTWRITEBYTECODE="1")
    args = [sys.executable, "-I", "-B"]
    if optimized:
        args.append("-O")
    args += ["-c", _CHILD_BOOT, str(repo), "-p", "no:cacheprovider",
             "-o", "addopts=", "--assert=plain", "-q", target]
    result = subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True,
                            timeout=60)
    print("CHILD_COMMAND", json.dumps({
        "interpreter":sys.executable, "isolated":True, "bytecode_disabled":True,
        "optimized":optimized, "pytest_args":args[args.index(str(repo)) + 1:],
        "bootstrap_sha256":_sha(_CHILD_BOOT.encode()), "timeout_s":60,
    }))
    print(result.stdout)
    if result.stderr:
        print("CHILD_STDERR", result.stderr)
    return result


def _child_receipt(child):
    rows = [line.removeprefix("CHILD_RECEIPT ") for line in child.stdout.splitlines()
            if line.startswith("CHILD_RECEIPT ")]
    assert len(rows) == 1, (child.stdout, child.stderr)
    receipt = json.loads(rows[0])
    assert all(r["outcome"] == "passed" for r in receipt["phases"] if r["phase"] != "call")
    assert not any(r["outcome"] == "skipped" for r in receipt["phases"])
    return receipt


def _copy_project(root):
    paths = set(SOURCE_PATHS) | {
        "train/test_frontier_inputs.py", "bench/fixture.py",
        "bench/fixtures/dev.json", "bench/fixtures/schema.sql",
        "docs/pre-registration.md", "pytest.ini",
    }
    for rel in paths:
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, destination)
    return root


def test_F12_source_drift_after_first_admission_disposable_copy(tmp_path):
    _api()
    project = _copy_project(tmp_path / "project")
    # Run the real copied source under the same pre-import guards. No source-root
    # override is passed to either API; all binding uses its actual module root.
    boot = _CHILD_BOOT.split("import pytest\n", 1)[0]
    program = boot + r'''
import pathlib, runpy
ns = runpy.run_path(str(pathlib.Path(sys.argv[1]) / "train/test_frontier_inputs.py"))
module = ns["_api"]()
fx = ns["_stage"](pathlib.Path(sys.argv[2]))
from bench import prepare
real = prepare.load_validated_draw
calls = []
def drift(*a, **k):
    result = real(*a, **k)
    calls.append(1)
    if len(calls) == 1:
        source = pathlib.Path(sys.argv[1]) / "train/ex_reward.py"
        source.write_bytes(source.read_bytes() + b"\n# disposable source drift\n")
    return result
for owner in (prepare, module):
    for name, value in list(vars(owner).items()):
        if value is real:
            setattr(owner, name, drift)
try:
    fx.load(module)
except ValueError:
    if not calls:
        raise SystemExit("no real first admission")
else:
    raise SystemExit("source drift admitted")
'''
    child = subprocess.run(
        [sys.executable, "-I", "-B", "-c", program, str(project), str(tmp_path / "fixture")],
        cwd=project, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                             PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"),
        capture_output=True, text=True, timeout=60,
    )
    assert child.returncode == 0, (child.stdout, child.stderr)


class _ContractMutant(ast.NodeTransformer):
    """Mutate actual implementation conditions, never replace APIs with fake ones."""
    def __init__(self, kind):
        self.kind, self.changed = kind, 0

    def visit_Compare(self, node):
        self.generic_visit(node)
        text = ast.unparse(node)
        digest = "expected_" in text and "sha256" in text
        membership = ("retained" in text and any(
            word in text for word in ("diagnostic", "report", "reconstruct", "result")))
        if (self.kind == "digest" and digest) or (self.kind == "membership" and membership):
            if any(isinstance(op, (ast.NotEq, ast.Eq)) for op in node.ops):
                self.changed += 1
                return ast.copy_location(ast.Constant(False), node)
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if self.kind == "create-only" and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                if node.func.attr == "link":
                    node.func.attr = "replace"
                    self.changed += 1
        return node


@pytest.mark.parametrize("kind,target", [
    ("digest", "test_F01_four_digests_before_zero_parses_or_corpus"),
    ("membership", "test_F05_retained_membership_exact_and_ordered"),
    ("create-only", "test_F13_create_only_publication_failure_boundaries"),
])
def test_F17_disposable_actual_source_mutants_red_restored_green(tmp_path, kind, target):
    _api()
    project = _copy_project(tmp_path / "project")
    source = project / "train/frontier_inputs.py"
    original = source.read_bytes()
    transformer = _ContractMutant(kind)
    tree = transformer.visit(ast.parse(original))
    assert transformer.changed == 1, "expected one actual implemented guard"
    source.write_text(ast.unparse(ast.fix_missing_locations(tree)) + "\n")
    selector = "train/test_frontier_inputs.py::" + target
    mutant = _child(project, selector)
    assert mutant.returncode == 1, (mutant.stdout, mutant.stderr)
    assert "FAILED" in mutant.stdout and "ERROR" not in mutant.stdout
    needles = {
        "digest": ("DID NOT RAISE", "forbidden project call: loads",
                   "forbidden project call: _corpus"),
        "membership": ("DID NOT RAISE",),
        "create-only": ("overwrite-capable publication forbidden",),
    }[kind]
    assert any(n in mutant.stdout for n in needles), mutant.stdout
    mutant_receipt = _child_receipt(mutant)
    assert any(r["phase"] == "call" and r["outcome"] == "failed"
               for r in mutant_receipt["phases"])
    assert not mutant_receipt["warnings"]
    assert mutant_receipt["source_sha256"] == _sha(source.read_bytes())
    source.write_bytes(original)
    restored = _child(project, selector)
    assert restored.returncode == 0, (restored.stdout, restored.stderr)
    restored_receipt = _child_receipt(restored)
    assert all(r["outcome"] == "passed" for r in restored_receipt["phases"])
    assert not restored_receipt["warnings"]
    assert restored_receipt["source_sha256"] == _sha(original)
    assert source.read_bytes() == original


@pytest.mark.parametrize("target", [
    "test_F01_four_digests_before_zero_parses_or_corpus",
    "test_F05_retained_membership_exact_and_ordered",
    "test_F16_exact_fixture_opt_in_zero_runtime",
])
def test_F18_optimized_process_digest_membership_opt_in_refuse(target):
    _api()
    # --assert=plain would erase test asserts under -O. The selected negatives
    # use pytest.raises() for refusal and fail if the production check vanished.
    child = _child(REPO, "train/test_frontier_inputs.py::" + target, optimized=True)
    assert child.returncode == 0, (child.stdout, child.stderr)
    assert "passed" in child.stdout and "ERROR" not in child.stdout
    receipt = _child_receipt(child)
    assert receipt["optimized"] >= 1
    assert receipt["source"] == str(REPO / "train/frontier_inputs.py")
    assert receipt["source_sha256"] == _sha((REPO / "train/frontier_inputs.py").read_bytes())
    assert all(r["outcome"] == "passed" for r in receipt["phases"])
    # Pytest explicitly warns that -O erases ordinary test asserts. These
    # negatives deliberately use pytest.raises(), which remains executable.
    assert receipt["warnings"] == [
        "ASSERTIONS ARE NOT EXECUTED and FAILING TESTS WILL PASS.  Are you using python -O?"
    ]


# Reviewer follow-up 01: preparation metadata bounds and real malformed corpus.
def _followup01_retain_preparation(fx, draw, supplement):
    """Update all independently retained fixture pins and dependent byte links."""
    fx.rewrite(draw, which="draw")
    supplement["draw_sha256"] = fx.pins["draw"]
    fx.rewrite(supplement, which="supplement")
    doc = copy.deepcopy(fx.doc)
    for artifact in ("draw", "supplement", "manifest"):
        doc[artifact + "_sha256"] = fx.pins[artifact]
    fx.rewrite(doc)
    assert json.loads(fx.supplement.read_bytes())["draw_sha256"] == fx.pins["draw"]
    admitted_links = json.loads(fx.sidecar.read_bytes())
    for artifact in ("draw", "supplement", "manifest", "sidecar"):
        assert _sha(getattr(fx, artifact).read_bytes()) == fx.pins[artifact]
        if artifact != "sidecar":
            assert admitted_links[artifact + "_sha256"] == fx.pins[artifact]
    print("FOLLOWUP01_ARTIFACT_BYTES", json.dumps({
        k: getattr(fx, k).stat().st_size for k in ("draw", "supplement", "manifest", "sidecar")
    }))


@pytest.mark.parametrize("operation", ["load", "produce"])
@pytest.mark.parametrize("value", ["x" * 257, "é" * 129], ids=["ascii257", "utf8-258"])
@pytest.mark.parametrize("field", ["planned-db", "database-db", "eligible-id", "excluded-id"])
def test_F14_followup01_preparation_id_bounds_before_corpus(
        tmp_path, monkeypatch, operation, value, field):
    module, fx = _api(), _stage(tmp_path)
    draw = json.loads(fx.draw.read_bytes())
    supplement = json.loads(fx.supplement.read_bytes())
    if field == "planned-db":
        draw["planned"][0]["db_id"] = value
    elif field == "database-db":
        draw["identity"]["databases"][0]["db_id"] = value
    else:
        original = (supplement["eligible_ids"][0] if field == "eligible-id"
                    else supplement["exclusions"][0]["id"])
        for entry in draw["planned"]:
            if entry["id"] == original:
                entry["id"] = value
        for key in ("planned_ids", "eligible_ids"):
            supplement[key] = [value if i == original else i for i in supplement[key]]
        for entry in supplement["exclusions"]:
            if entry["id"] == original:
                entry["id"] = value
    _followup01_retain_preparation(fx, draw, supplement)
    with _sentries(monkeypatch, module, corpus=True) as calls:
        _refuse(lambda: getattr(fx, operation)(module))
    assert not calls
    assert not (tmp_path / "produced.json").exists()


@pytest.mark.parametrize("operation", ["load", "produce"])
def test_F14_followup01_100001_preparation_entries_before_corpus(
        tmp_path, monkeypatch, operation):
    module, fx = _api(), _stage(tmp_path)
    draw = json.loads(fx.draw.read_bytes())
    supplement = json.loads(fx.supplement.read_bytes())
    ids = ["p" + str(i) for i in range(100001)]
    draw["planned"] = [
        dict(id=name, db_id="campus", task_sha256="0" * 64,
             tier="moderate" if i == 99999 else "challenging" if i == 100000 else "simple")
        for i, name in enumerate(ids)
    ]
    tiers = dict(simple=99999, moderate=1, challenging=1)
    draw["settings"]["per_tier"] = tiers.copy()
    draw["actual_per_tier"] = tiers.copy()
    draw["shortfall_per_tier"] = dict.fromkeys(FULL, 0)
    supplement["planned_ids"] = ids.copy()
    supplement["eligible_ids"] = ids.copy()
    supplement["exclusions"] = []
    supplement["counts"] = dict(planned=tiers.copy(), eligible=tiers.copy(),
                                excluded=dict.fromkeys(FULL, 0))
    _followup01_retain_preparation(fx, draw, supplement)
    assert len(draw["planned"]) == len(supplement["planned_ids"]) == 100001
    assert fx.draw.stat().st_size <= 16 << 20
    assert fx.supplement.stat().st_size <= 16 << 20
    with _sentries(monkeypatch, module, corpus=True) as calls:
        _refuse(lambda: getattr(fx, operation)(module))
    assert not calls
    assert not (tmp_path / "produced.json").exists()


@pytest.mark.parametrize("operation", ["load", "produce"])
def test_F14_followup01_256_byte_real_task_id_and_long_task_text_pass(
        tmp_path, monkeypatch, operation):
    module, fx = _api(), _stage(tmp_path, boundary_id=True)
    long_task = next(t for t in fx.admitted.eligible if len(t.name.encode()) == 256)
    assert len(long_task.question.encode()) > 256
    assert len(long_task.evidence.encode()) > 256
    with _sentries(monkeypatch, module):
        if operation == "produce":
            pin = fx.produce(module)
            fx.sidecar, fx.pins["sidecar"] = tmp_path / "produced.json", pin
        result = fx.load(module)
    assert long_task in result.eligible
    assert long_task in result.retained
    assert result.preparation_exclusions == fx.admitted.exclusions
    assert _plain(result.counts)["planned"] == 8


@pytest.mark.parametrize("operation", ["load", "produce"])
@pytest.mark.parametrize("defect", ["missing-question", "nonstring-evidence"])
def test_F12_followup01_actual_malformed_corpus_between_admissions_is_domain_error(
        tmp_path, monkeypatch, operation, defect):
    module, fx = _api(), _stage(tmp_path)
    real = prepare.load_validated_draw
    started, completed = [], []

    def corrupt_after_first_admission(*args, **kwargs):
        started.append(1)
        result = real(*args, **kwargs)
        completed.append(1)
        if len(completed) == 1:
            path = fx.corpus / "dev.json"
            records = json.loads(path.read_bytes())
            if defect == "missing-question":
                records[0].pop("question")
            else:
                records[0]["evidence"] = {"RAW_ERROR_SENTINEL": "private"}
            path.write_text(json.dumps(records))
        return result

    _patch_aliases(monkeypatch, [prepare, module], real, corrupt_after_first_admission)
    try:
        with _sentries(monkeypatch, module):
            error = _refuse(lambda: getattr(fx, operation)(module))
    finally:
        print("FOLLOWUP01_REAL_ADMISSIONS", json.dumps({
            "started": len(started), "completed": len(completed), "defect": defect,
        }))
    assert len(started) == 2 and len(completed) == 1
    assert type(error) is module.FrontierInputsError
    assert str(error) == "frontier corpus records rejected"
    assert error.__cause__ is None and error.__suppress_context__
    assert not (tmp_path / "produced.json").exists()


@pytest.mark.parametrize("fault", ["temporary-unlink", "directory-sync"])
def test_F13_followup01_postcommit_fault_preserves_final_without_retry(
        tmp_path, monkeypatch, fault):
    module, fx = _api(), _stage(tmp_path)
    output = tmp_path / "publication.json"
    real_link, real_unlink, real_sync, real_temp = os.link, os.unlink, os.fsync, tempfile.mkstemp
    calls = Counter()
    temporary = []

    def create_temp(*args, **kwargs):
        calls["temporary"] += 1
        fd, name = real_temp(*args, **kwargs)
        temporary.append(Path(name))
        return fd, name

    def link(source, destination, *args, **kwargs):
        calls["commit_attempt"] += 1
        result = real_link(source, destination, *args, **kwargs)
        calls["committed"] += 1
        return result

    def unlink(path, *args, **kwargs):
        if Path(path) == output:
            calls["final_delete"] += 1
            raise AssertionError("final deletion forbidden")
        if temporary and Path(path) == temporary[0]:
            calls["temporary_unlink"] += 1
            if fault == "temporary-unlink" and calls["committed"]:
                raise OSError("RAW_ERROR_SENTINEL")
        return real_unlink(path, *args, **kwargs)

    def sync(fd):
        if calls["committed"] and fault == "directory-sync":
            calls["directory_sync"] += 1
            raise OSError("RAW_ERROR_SENTINEL")
        return real_sync(fd)

    def overwrite(*args, **kwargs):
        calls["overwrite"] += 1
        raise AssertionError("overwrite forbidden")

    with monkeypatch.context() as patch:
        patch.setattr(tempfile, "mkstemp", create_temp)
        patch.setattr(os, "link", link)
        patch.setattr(os, "unlink", unlink)
        patch.setattr(os, "fsync", sync)
        patch.setattr(os, "rename", overwrite)
        patch.setattr(os, "replace", overwrite)
        with _sentries(patch, module):
            with pytest.raises(module.FrontierPublicationIndeterminateError) as caught:
                fx.produce(module, output)
    assert calls["temporary"] == calls["commit_attempt"] == calls["committed"] == 1
    assert calls["temporary_unlink"] == 1
    assert calls["final_delete"] == calls["overwrite"] == 0
    assert calls["directory_sync"] == int(fault == "directory-sync")
    assert output.read_bytes() == _canonical(fx.doc)
    assert json.loads(output.read_bytes()) == fx.doc
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert "indeterminate" in str(caught.value) and "RAW_ERROR_SENTINEL" not in str(caught.value)
    if fault == "temporary-unlink":
        # The injected unlink really failed. Do not promise forced cleanup or
        # silently remove/retry/delete the committed final document.
        assert temporary[0].exists() and temporary[0].samefile(output)
    else:
        assert not temporary[0].exists()
