"""Offline fixture mechanics, NOT native acceptance, model learning or a sandbox.

Uses the same caller-authored catalog/identifier-quoting program and 0/1/3/7,
11/13-row fixtures as test_sql_skill_eval. Existing capture/evaluator/runtime
exports execute unchanged, with executor=None. No production adapter is added.
Only run with trusted local source/assets. Local self-approval is illustrative,
not independent authentication. Artifacts are retained, never deleted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch


PROGRAM = '''tables = execute_sql(query="SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
if len(tables) == 1:
    name = tables[0]["name"]
    quoted = '"'
    for character in name:
        quoted = quoted + ('""' if character == '"' else character)
    quoted = quoted + '"'
    print("FINAL_SQL:SELECT COUNT(*) FROM " + quoted)
'''
MODE = "offline-in-process-fixture-mechanics"


def deny_network():
    """Deny Python socket audit events in this process, including DNS/loopback.

    Not an OS sandbox or arbitrary-child telemetry. The two known Python
    children independently install this same hook before workflow imports.
    """
    attempts = []

    def audit(event, args):
        if event.startswith("socket."):
            attempts.append(event)
            raise RuntimeError("offline demo forbids socket activity")

    sys.addaudithook(audit)
    return attempts


@contextmanager
def dispatches():
    """Count real existing ArmPair.run calls, without replacing execution."""
    from ptc.sql_arms import ArmPair

    calls = []
    original = ArmPair.run

    def counted(pair, *args, **kwargs):
        calls.append(args)
        return original(pair, *args, **kwargs)

    with patch.object(ArmPair, "run", counted):
        yield calls


def _pin(data):
    return hashlib.sha256(data).hexdigest()


def _ids(label, split):
    from train.sql_episodes import EpisodeIds

    return EpisodeIds(
        corpus_id="caller-row-count-fixtures", split_id=split,
        run_id="offline-demo", episode_id=label,
        policy_id="trusted-caller", policy_revision="v1",
    )


def _task(directory, label, rows, table=None):
    from bench.task import SqlTask

    quoted = '"' + (table or label).replace('"', '""') + '"'
    path = directory / (label + ".sqlite")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE " + quoted + " (value INTEGER)")
        connection.executemany(
            "INSERT INTO " + quoted + " VALUES (?)", [(i,) for i in range(rows)],
        )
    return SqlTask(
        name="row-count-" + label, question="Count rows in the only user table.",
        evidence="", gold_sql="SELECT COUNT(*) FROM " + quoted,
        db_id=label, db_path=str(path), tier="simple", tier_source="derived",
        shape="select-count", coarse_shape="aggregate", source="fixture",
    )


def _success(capture):
    assert capture.result is not None
    assert capture.result.valid is True and capture.result.score == 1
    assert len(capture.steps) == 1 and capture.refusals == ()
    assert capture.steps[0].action == PROGRAM
    return asdict(capture.result)


def prepare(directory):
    """Create trusted fixtures, capture a real zero, qualify through real APIs."""
    from train import sql_capture as capture, sql_skill_eval as evaluate, sql_skills as skills

    assets = directory / "qualification-assets"
    assets.mkdir()
    source = _task(assets, "origin", 2)
    failed = capture.start_capture(
        source, ids=_ids("source", "origin"), allow_execution=True,
    ).finish("SELECT -1")
    assert failed.result.valid is True and failed.result.score == 0
    candidate = skills.create_candidate(
        failed, source_task=source, source_ids=failed.ids,
        skill_id="single-user-table-row-count", program=PROGRAM,
    )
    cases = tuple(
        evaluate.SkillCase(
            "qualification", _task(assets, label, rows), _ids(label, "qualification"),
        )
        for label, rows in (("empty", 0), ("singleton", 1), ("triple", 3), ("seven", 7))
    )
    approval_ids = _ids("approval", "approval")
    with dispatches() as calls:
        promotion, captures = evaluate.promote_candidate(
            candidate, source_capture=failed,
            expected_source_capture_sha256=_pin(capture.encode_capture(failed)),
            source_case=evaluate.SkillCase("source_failure", source, failed.ids),
            qualification_cases=cases, ids=approval_ids, allow_execution=True,
        )
    assert promotion is not None and len(captures) == 4 and len(calls) == 4
    results = [_success(item) for item in captures]
    candidate_bytes = skills.encode_candidate(candidate)
    promotion_bytes = skills.encode_promotion(promotion)
    (directory / "source-capture.json").write_bytes(capture.encode_capture(failed))
    (directory / "candidate.json").write_bytes(candidate_bytes)
    (directory / "promotion.json").write_bytes(promotion_bytes)
    for index, item in enumerate(captures):
        (directory / f"qualification-{index}.json").write_bytes(capture.encode_capture(item))
    reuse_assets = directory / "reuse-assets"
    reuse_assets.mkdir()
    reuse_cases = tuple(
        evaluate.SkillCase("reuse", _task(reuse_assets, label, rows, table), _ids(label, "reuse"))
        for label, rows, table in (
            ("eleven", 11, "new table"), ("thirteen", 13, 'fresh " identifier'),
        )
    )
    manifest = dict(
        ids=asdict(approval_ids),
        unavailable_paths=[case.task.db_path for case in (
            evaluate.SkillCase("source_failure", source, failed.ids), *cases,
        )],
        cases=[dict(task=asdict(case.task), ids=asdict(case.ids)) for case in reuse_cases],
    )
    (directory / "reuse-inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dict(
        candidate=candidate, promotion=promotion, case=reuse_cases[0],
        approval_ids=approval_ids, approved_pin=_pin(promotion_bytes),
        candidate_pin=_pin(candidate_bytes), qualifications=results,
        unavailable_paths=manifest["unavailable_paths"],
    )


def check_bad_pin(state):
    """A syntactically valid but unapproved whole-envelope pin must never run."""
    from train import sql_skill_eval

    bad_pin = ("0" if state["approved_pin"][0] != "0" else "1") + state["approved_pin"][1:]
    rejected = False
    with dispatches() as calls:
        try:
            sql_skill_eval.reuse_promoted(
                state["candidate"], state["promotion"], state["case"],
                expected_promotion_sha256=bad_pin, ids=state["approval_ids"],
                allow_execution=True,
            )
        except ValueError:
            rejected = True
    assert len(calls) == 0, "bad pin dispatched before rejection"
    assert rejected, "bad pin was accepted"
    return len(calls)


def _reuse(directory, index, approved_pin):
    from bench.task import SqlTask
    from train.sql_capture import encode_capture
    from train.sql_episodes import EpisodeIds
    from train.sql_skill_eval import SkillCase, reuse_promoted
    from train.sql_skills import decode_candidate, decode_promotion

    manifest = json.loads((directory / "reuse-inputs.json").read_text())
    assert all(not Path(path).exists() for path in manifest["unavailable_paths"])
    item = manifest["cases"][index]
    candidate = decode_candidate((directory / "candidate.json").read_bytes())
    promotion = decode_promotion((directory / "promotion.json").read_bytes())
    with dispatches() as calls:
        actual = reuse_promoted(
            candidate, promotion,
            SkillCase("reuse", SqlTask(**item["task"]), EpisodeIds(**item["ids"])),
            expected_promotion_sha256=approved_pin,
            ids=EpisodeIds(**manifest["ids"]), allow_execution=True,
        )
    result = _success(actual)
    assert len(calls) == 1
    (directory / f"reuse-{index}.json").write_bytes(encode_capture(actual))
    return dict(pid=os.getpid(), dispatches=len(calls), result=result)


def run_demo(directory):
    """Require a new directory; retain all assets, move old DB paths out of reach."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    state = prepare(directory)
    bad_pin_dispatches = check_bad_pin(state)
    (directory / "qualification-assets").rename(directory / "unavailable-assets")
    assert all(not Path(path).exists() for path in state["unavailable_paths"])
    reuses = []
    for index in range(2):
        child = subprocess.run(
            [sys.executable, "-B", "-m", "train.sql_skill_demo",
             "--reuse", str(directory), "--case-index", str(index),
             "--approved-pin", state["approved_pin"]],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=30, check=True,
        )
        reuses.append(json.loads(child.stdout))
    assert len({item["pid"] for item in reuses}) == 2
    return dict(
        mode=MODE, pid=os.getpid(), qualification_dispatches=4,
        qualifications=state["qualifications"], reuses=reuses,
        bad_pin_dispatches=bad_pin_dispatches,
        origin_and_qualification_paths_unavailable=True,
        candidate_sha256=state["candidate_pin"],
        approved_promotion_sha256=state["approved_pin"],
    )


def main():
    if not __debug__:
        raise RuntimeError("demo assertions require Python without -O")
    attempts = deny_network()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--work-dir", type=Path, help="new directory for retained fixture evidence")
    mode.add_argument("--reuse", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--case-index", type=int, choices=(0, 1), help=argparse.SUPPRESS)
    parser.add_argument("--approved-pin", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.reuse:
        if args.case_index is None or args.approved_pin is None:
            parser.error("fresh reuse requires case index and external approved pin")
        report = _reuse(args.reuse, args.case_index, args.approved_pin)
    else:
        report = run_demo(args.work_dir)
    assert not attempts
    report["network_attempts"] = len(attempts)
    if args.work_dir:
        (args.work_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
