"""Caller-authored SQLite file workflow contracts, without demo fixture imports."""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench.task import SqlTask
from train import sql_capture as capture
from train import sql_episodes as evidence
from train import sql_pilot_assets as assets
from train import sql_skill_eval as evaluator
from train import sql_skills as skills


def api():
    try:
        return importlib.import_module("train.sql_skill_workflow")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_skill_workflow":
            raise
        pytest.fail("train.sql_skill_workflow is not implemented", pytrace=False)


def ids(label, split="origin", family="payments"):
    return evidence.EpisodeIds(
        "caller-" + family, split, "workflow-run", label, "caller-policy", "r1",
    )


def payment_task(directory, label, seed):
    """Family one: signed payments with a positive-only sum."""
    path = directory / (label + ".sqlite")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE payments (amount INTEGER)")
        db.executemany("INSERT INTO payments VALUES (?)",
                       [(seed,), (-seed * 3,), (seed + 2,)])
    return SqlTask(
        label, "Sum positive payments.", "", "SELECT SUM(amount) FROM payments WHERE amount > 0",
        label, str(path), "simple", "derived", "positive-sum", "aggregate", "fixture",
    )


def membership_task(directory, label, seed):
    """Family two: joined active-member activity, independently constructed."""
    path = directory / (label + ".sqlite")
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE members (id INTEGER, active INTEGER);"
            "CREATE TABLE visits (member_id INTEGER, day INTEGER);"
        )
        db.executemany("INSERT INTO members VALUES (?, ?)", [(seed, 1), (seed + 1, 0)])
        db.executemany("INSERT INTO visits VALUES (?, ?)",
                       [(seed, n) for n in range(seed)] + [(seed + 1, 99)])
    return SqlTask(
        label, "Count visits by active members.", "",
        "SELECT COUNT(*) FROM visits JOIN members ON member_id = id WHERE active = 1",
        label, str(path), "simple", "derived", "active-join-count", "join", "fixture",
    )


def world(directory, family="payments", *, fail_second=False):
    module = api()
    build = payment_task if family == "payments" else membership_task
    source_task = build(directory, family + "-source", 2)
    source_ids = ids("source", family=family)
    source = capture.start_capture(
        source_task, ids=source_ids, allow_execution=True,
    ).finish("SELECT -999")
    assert source.result.valid is True and source.result.score == 0
    program = "print(" + repr("FINAL_SQL:" + source_task.gold_sql) + ")"
    candidate_path = module.create_candidate_file(
        source, source_task=source_task, source_ids=source_ids,
        skill_id=family + "-v1", program=program, output_dir=directory / "candidate",
    )
    source_path = directory / "source.json"
    assets.write_new(source_path, capture.encode_capture(source))
    cases = []
    for n in range(4):
        task = build(directory, family + "-q" + str(n), n + 4)
        if fail_second and n == 1:
            task = dataclasses.replace(task, gold_sql="SELECT -123")
        cases.append(evaluator.SkillCase(
            "qualification", task, ids("q" + str(n), "qualification", family),
        ))
    return SimpleNamespace(
        module=module, build=build, family=family, candidate_path=candidate_path,
        source_path=source_path, source=source,
        source_case=evaluator.SkillCase("source_failure", source_task, source_ids),
        cases=tuple(cases), approval_ids=ids("approval", "approval", family),
        source_pin=hashlib.sha256(capture.encode_capture(source)).hexdigest(),
    )


def qualify(state, directory, **changes):
    kwargs = dict(
        expected_source_capture_sha256=state.source_pin, source_case=state.source_case,
        qualification_cases=state.cases, ids=state.approval_ids,
        output_dir=directory, allow_execution=True,
    )
    kwargs.update(changes)
    return state.module.qualify_candidate_files(
        state.candidate_path, state.source_path, **kwargs,
    )


def reuse_case(state, directory, index=0):
    return evaluator.SkillCase(
        "reuse", state.build(directory, state.family + "-r" + str(index), 11 + index),
        ids("reuse" + str(index), "reuse", state.family),
    )


def reuse(state, receipt, case, directory, **changes):
    kwargs = dict(
        expected_promotion_sha256=hashlib.sha256(assets.read_file(receipt)).hexdigest(),
        ids=state.approval_ids, output_dir=directory, allow_execution=True,
    )
    kwargs.update(changes)
    return state.module.reuse_approved_files(state.candidate_path, receipt, case, **kwargs)


def sentries(monkeypatch):
    from ptc import sql_arms
    counts = dict(program=0, score=0)
    original_run, original_score = sql_arms.ArmPair.run, evidence.execution_accuracy

    def run(*args, **kwargs):
        counts["program"] += 1
        return original_run(*args, **kwargs)

    def score(*args, **kwargs):
        counts["score"] += 1
        return original_score(*args, **kwargs)

    monkeypatch.setattr(sql_arms.ArmPair, "run", run)
    monkeypatch.setattr(evidence, "execution_accuracy", score)
    return counts


@pytest.mark.parametrize("family", ("payments", "membership"))
def test_two_real_families_canonical_qualification_and_reuse(tmp_path, monkeypatch, family):
    state = world(tmp_path, family)
    counts = sentries(monkeypatch)
    result = qualify(state, tmp_path / "qualification")
    assert result.promotion_path is not None
    assert len(result.capture_paths) == 4
    for path in result.capture_paths:
        raw = assets.read_file(path)
        actual = capture.decode_capture(raw)
        assert capture.encode_capture(actual) == raw
        assert actual.result.valid is True and actual.result.score == 1
        assert len(actual.steps) == 1
    for n in range(2):
        path = reuse(state, result.promotion_path, reuse_case(state, tmp_path, n),
                     tmp_path / ("reuse-" + str(n)))
        actual = capture.decode_capture(assets.read_file(path))
        assert actual.result.valid is True and actual.result.score == 1
    assert counts == dict(program=6, score=7)
    for path, decode, encode in (
        (state.candidate_path, skills.decode_candidate, skills.encode_candidate),
        (result.promotion_path, skills.decode_promotion, skills.encode_promotion),
    ):
        raw = assets.read_file(path)
        assert encode(decode(raw)) == raw


def test_qualification_two_failure_retains_two_captures_without_promotion(tmp_path, monkeypatch):
    state = world(tmp_path, fail_second=True)
    counts = sentries(monkeypatch)
    result = qualify(state, tmp_path / "qualification")
    assert counts == dict(program=2, score=3)
    assert len(result.capture_paths) == 2
    assert [capture.decode_capture(assets.read_file(p)).result.score
            for p in result.capture_paths] == [1, 0]
    assert result.promotion_path is None, "failed qualification must never publish promotion"
    assert not (tmp_path / "qualification" / "promotion.json").exists()
    assert len(list((tmp_path / "qualification").iterdir())) == 2


@pytest.mark.parametrize("bad", ("pin", "ids", "candidate", "optin"))
def test_reuse_authority_rejected_before_dispatch(tmp_path, monkeypatch, bad):
    state = world(tmp_path)
    receipt = qualify(state, tmp_path / "qualification").promotion_path
    case = reuse_case(state, tmp_path)
    kwargs = {}
    if bad == "pin":
        kwargs["expected_promotion_sha256"] = "0" * 64
    elif bad == "ids":
        kwargs["ids"] = ids("impostor", "approval")
    elif bad == "optin":
        kwargs["allow_execution"] = False
    else:
        changed = dataclasses.replace(skills.decode_candidate(assets.read_file(state.candidate_path)),
                                      program="print('FINAL_SQL:SELECT 0')")
        other = tmp_path / "changed.json"
        assets.write_new(other, skills.encode_candidate(changed))
        state.candidate_path = other
    counts = sentries(monkeypatch)
    rejected = False
    try:
        reuse(state, receipt, case, tmp_path / "reuse", **kwargs)
    except (ValueError, TypeError):
        rejected = True
    assert counts == dict(program=0, score=0), "invalid approval reached execution"
    assert rejected, "invalid external approval was accepted"


@pytest.mark.parametrize("bad", (
    "oversize", "malformed", "symlink", "db-symlink", "checkout", "existing", "output-symlink",
))
def test_asset_and_output_preflight_before_any_execution(tmp_path, monkeypatch, bad):
    state = world(tmp_path)
    out = tmp_path / "qualification"
    original = assets.read_file(state.candidate_path)
    if bad in ("oversize", "malformed"):
        other = tmp_path / "bad.json"
        other.write_bytes(b"x" * (8 * 1024 * 1024 + 1) if bad == "oversize" else b"{}")
        state.candidate_path = other
    elif bad == "symlink":
        other = tmp_path / "link.json"
        other.symlink_to(state.candidate_path)
        state.candidate_path = other
    elif bad == "db-symlink":
        other = tmp_path / "db-link.sqlite"
        other.symlink_to(state.cases[3].task.db_path)
        state.cases = state.cases[:3] + (dataclasses.replace(
            state.cases[3], task=dataclasses.replace(state.cases[3].task, db_path=str(other)),
        ),)
    elif bad == "checkout":
        out = Path(__file__).resolve().parent / "workflow-must-not-exist"
    elif bad == "existing":
        out.mkdir()
        (out / "sentinel").write_bytes(b"preserve")
    else:
        (tmp_path / "out-link").symlink_to(tmp_path, target_is_directory=True)
        out = tmp_path / "out-link" / "nested"
    counts = sentries(monkeypatch)
    with pytest.raises((ValueError, TypeError, FileExistsError)):
        qualify(state, out)
    assert counts == dict(program=0, score=0)
    assert assets.read_file(tmp_path / "candidate" / "candidate.json") == original
    if bad == "existing":
        assert (out / "sentinel").read_bytes() == b"preserve"


def test_program_utf8_bound_and_existing_candidate_bytes(tmp_path, monkeypatch):
    state = world(tmp_path)
    original = assets.read_file(state.candidate_path)
    counts = sentries(monkeypatch)
    with pytest.raises(ValueError, match="65536"):
        state.module.create_candidate_file(
            state.source, source_task=state.source_case.task, source_ids=state.source.ids,
            skill_id="too-large", program="α" * 32769, output_dir=tmp_path / "oversize",
        )
    with pytest.raises(FileExistsError):
        state.module.create_candidate_file(
            state.source, source_task=state.source_case.task, source_ids=state.source.ids,
            skill_id="other", program="print('x')", output_dir=state.candidate_path.parent,
        )
    assert counts == dict(program=0, score=0)
    assert assets.read_file(state.candidate_path) == original
    assert not (tmp_path / "oversize").exists()


@pytest.mark.parametrize("has_capture", (True, False))
def test_exception_evidence_never_fabricated(tmp_path, monkeypatch, has_capture):
    state = world(tmp_path)
    actual = capture.start_capture(
        state.cases[0].task, ids=state.cases[0].ids, allow_execution=True,
    ).abort()
    error = capture.CaptureError(actual) if has_capture else RuntimeError("no evidence")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(evaluator, "promote_candidate", fail)
    with pytest.raises(type(error)) as caught:
        qualify(state, tmp_path / "qualification")
    assert caught.value is error
    paths = list((tmp_path / "qualification").iterdir())
    assert len(paths) == int(has_capture)
    if has_capture:
        assert capture.decode_capture(assets.read_file(paths[0])) == actual
    assert not (tmp_path / "qualification" / "promotion.json").exists()


def test_failed_capture_write_cannot_publish_receipt(tmp_path, monkeypatch):
    state = world(tmp_path)
    original = assets.write_new

    def fail(path, raw):
        if path.name == "qualification-2.json":
            raise OSError("storage failure")
        return original(path, raw)

    monkeypatch.setattr(assets, "write_new", fail)
    with pytest.raises(OSError, match="storage failure"):
        qualify(state, tmp_path / "qualification")
    assert (tmp_path / "qualification" / "qualification-1.json").exists()
    assert not (tmp_path / "qualification" / "promotion.json").exists()


def test_pending_receipt_write_failure_never_publishes_promotion(tmp_path, monkeypatch):
    state = world(tmp_path)
    original = assets.write_new

    def fail(path, raw):
        if path.name == ".promotion.pending":
            original(path, raw[:100])
            raise OSError("partial receipt")
        return original(path, raw)

    monkeypatch.setattr(assets, "write_new", fail)
    with pytest.raises(OSError, match="partial receipt"):
        qualify(state, tmp_path / "qualification")
    assert len(list((tmp_path / "qualification").glob("qualification-*.json"))) == 4
    assert (tmp_path / "qualification" / ".promotion.pending").stat().st_size == 100
    assert not (tmp_path / "qualification" / "promotion.json").exists()


@pytest.mark.parametrize("operation", ("qualify", "reuse"))
def test_missing_optin_defaults_to_no_execution(tmp_path, monkeypatch, operation):
    state = world(tmp_path)
    receipt = qualify(state, tmp_path / "qualification").promotion_path
    case = reuse_case(state, tmp_path)
    counts = sentries(monkeypatch)
    with pytest.raises(ValueError, match="allow_execution"):
        if operation == "qualify":
            state.module.qualify_candidate_files(
                state.candidate_path, state.source_path,
                expected_source_capture_sha256=state.source_pin,
                source_case=state.source_case, qualification_cases=state.cases,
                ids=state.approval_ids, output_dir=tmp_path / "missing-optin",
            )
        else:
            state.module.reuse_approved_files(
                state.candidate_path, receipt, case,
                expected_promotion_sha256=hashlib.sha256(assets.read_file(receipt)).hexdigest(),
                ids=state.approval_ids, output_dir=tmp_path / "missing-optin",
            )
    assert counts == dict(program=0, score=0)
    assert not (tmp_path / "missing-optin").exists()


@pytest.mark.parametrize("bad", ("source-pin", "source-file", "three-cases", "case-scope"))
def test_bad_qualification_inputs_never_reach_source_scorer(tmp_path, monkeypatch, bad):
    state = world(tmp_path)
    kwargs = {}
    if bad == "source-pin":
        kwargs["expected_source_capture_sha256"] = "0" * 64
    elif bad == "source-file":
        other = tmp_path / "source-link.json"
        other.symlink_to(state.source_path)
        state.source_path = other
    elif bad == "three-cases":
        state.cases = state.cases[:3]
    else:
        state.cases = state.cases[:3] + (dataclasses.replace(
            state.cases[3], task=dataclasses.replace(state.cases[3].task, shape="wrong"),
        ),)
    counts = sentries(monkeypatch)
    with pytest.raises((ValueError, TypeError)):
        qualify(state, tmp_path / "bad-qualification", **kwargs)
    assert counts == dict(program=0, score=0)


@pytest.mark.parametrize("bad", ("oversize", "symlink", "existing", "checkout", "noncanonical"))
def test_reuse_file_preflight_before_dispatch(tmp_path, monkeypatch, bad):
    state = world(tmp_path)
    receipt = qualify(state, tmp_path / "qualification").promotion_path
    case = reuse_case(state, tmp_path)
    pin = hashlib.sha256(assets.read_file(receipt)).hexdigest()
    out = tmp_path / "reuse"
    if bad in ("oversize", "noncanonical"):
        other = tmp_path / "bad-promotion.json"
        other.write_bytes(b"x" * (8 * 1024 * 1024 + 1) if bad == "oversize"
                          else assets.read_file(receipt) + b"\n")
        receipt = other
    elif bad == "symlink":
        other = tmp_path / "promotion-link.json"
        other.symlink_to(receipt)
        receipt = other
    elif bad == "checkout":
        out = Path(__file__).resolve().parent / "workflow-must-not-exist"
    else:
        out.mkdir()
        (out / "sentinel").write_bytes(b"preserve")
    counts = sentries(monkeypatch)
    with pytest.raises((ValueError, TypeError, FileExistsError)):
        reuse(state, receipt, case, out, expected_promotion_sha256=pin)
    assert counts == dict(program=0, score=0)
    if bad == "existing":
        assert (out / "sentinel").read_bytes() == b"preserve"


@pytest.mark.parametrize("executor", (None, object()))
def test_caller_executor_forwarded_without_selection(tmp_path, monkeypatch, executor):
    state = world(tmp_path)
    receipt = qualify(state, tmp_path / "qualification").promotion_path
    case = reuse_case(state, tmp_path)
    actual = capture.start_capture(case.task, ids=case.ids, allow_execution=True).abort()
    seen = []

    def promote(*args, **kwargs):
        seen.append(kwargs["executor"])
        return None, ()

    def approved(*args, **kwargs):
        seen.append(kwargs["executor"])
        return actual

    monkeypatch.setattr(evaluator, "promote_candidate", promote)
    monkeypatch.setattr(evaluator, "reuse_promoted", approved)
    qualify(state, tmp_path / "forward-qualification", executor=executor)
    reuse(state, receipt, case, tmp_path / "forward-reuse", executor=executor)
    assert len(seen) == 2 and all(item is executor for item in seen)


@pytest.mark.parametrize("has_capture", (True, False))
def test_reuse_exception_evidence_retained_without_fabrication(tmp_path, monkeypatch, has_capture):
    state = world(tmp_path)
    receipt = qualify(state, tmp_path / "qualification").promotion_path
    case = reuse_case(state, tmp_path)
    actual = capture.start_capture(case.task, ids=case.ids, allow_execution=True).abort()
    error = capture.CaptureError(actual) if has_capture else RuntimeError("no evidence")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(evaluator, "reuse_promoted", fail)
    with pytest.raises(type(error)) as caught:
        reuse(state, receipt, case, tmp_path / "reuse")
    assert caught.value is error
    paths = list((tmp_path / "reuse").iterdir())
    assert len(paths) == int(has_capture)
    if has_capture:
        assert capture.decode_capture(assets.read_file(paths[0])) == actual


def test_fresh_process_qualification_then_external_approval_reuse(tmp_path):
    api()
    root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=root)
    # Phase A and phase B do not share Python objects or evaluator monkeypatches.
    phase_a = """
import dataclasses, json, sys
from pathlib import Path
from train.test_sql_skill_workflow import world, qualify, reuse_case
p = Path(sys.argv[1])
s = world(p)
r = qualify(s, p / 'qualification')
cases = [reuse_case(s, p, n) for n in range(2)]
(p / 'caller-cases.json').write_text(json.dumps([dataclasses.asdict(c) for c in cases]))
print(str(r.promotion_path))
"""
    a = subprocess.run([sys.executable, "-c", phase_a, str(tmp_path)], cwd=root,
                       env=env, text=True, capture_output=True)
    assert a.returncode == 0, a.stderr
    receipt = Path(a.stdout.strip())
    # Parent caller supplies authority externally, not from the envelope payload.
    approved_pin = hashlib.sha256(assets.read_file(receipt)).hexdigest()
    approved_ids = dataclasses.asdict(ids("approval", "approval"))
    for path in tmp_path.glob("payments-*.sqlite"):
        if "-r" not in path.name:
            path.rename(path.with_suffix(".unavailable"))
    assert len(list(tmp_path.glob("*.unavailable"))) == 5
    phase_b = """
import json, sys
from pathlib import Path
from bench.task import SqlTask
from train.sql_episodes import EpisodeIds
from train.sql_skill_eval import SkillCase
from train.sql_skill_workflow import reuse_approved_files
from train.sql_capture import decode_capture
from train.sql_pilot_assets import read_file
p = Path(sys.argv[1])
for n, data in enumerate(json.loads((p / 'caller-cases.json').read_text())):
    case = SkillCase(data['role'], SqlTask(**data['task']), EpisodeIds(**data['ids']))
    out = reuse_approved_files(
        p / 'candidate' / 'candidate.json', Path(sys.argv[2]), case,
        expected_promotion_sha256=sys.argv[3], ids=EpisodeIds(**json.loads(sys.argv[4])),
        output_dir=p / ('process-reuse-' + str(n)), allow_execution=True)
    c = decode_capture(read_file(out))
    assert c.result.valid is True and c.result.score == 1
print('2/2')
"""
    b = subprocess.run([sys.executable, "-c", phase_b, str(tmp_path), str(receipt),
                        approved_pin, json.dumps(approved_ids)], cwd=root, env=env,
                       text=True, capture_output=True)
    assert b.returncode == 0, b.stderr
    assert b.stdout.strip() == "2/2"
