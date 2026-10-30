"""Explicit LOCAL TEST FIXTURE SDK/Timer acceptance, never product authorization.

No native execution on import, --help, default pytest collection or missing context.
Caller supplies an already approved, source-bound profile; no acquisition/setup.
After commit review, parent separately pins consent with fields checked by authorize.
Qualification exits UNAPPROVED. Parent reviews checkpoint.json and separately pins
the exact local fixture approval fields checked by verify_approval.

Portable invocation (all paths absolute, campaign outside checkout and NEW):
  python -B -m train.sql_skill_sdk_acceptance --phase qualify \
    --execution-profile "$PROFILE" --expected-profile-sha256 "$PROFILE_SHA" \
    --campaign-dir "$CAMPAIGN" --allow-native-execution \
    --consent-file "$CONSENT" --consent-sha256 "$CONSENT_SHA"
Then invoke the same command with --phase reuse --case-index 0, and separately 1,
adding --local-fixture-approval "$APPROVAL" \
       --local-fixture-approval-sha256 "$APPROVAL_SHA".
Each invocation must be a new interpreter. No child supervisor, signals or retries.
Job ceiling is 11+2+2=15. Source generation's two jobs are outside timed callbacks.
Timing proves callback wall scope only, not baseline, savings or model performance.
Failures retain claims, slots, STOP and all runtime evidence for parent inspection.
"""
from __future__ import annotations

import sys

if sys.flags.optimize:
    raise RuntimeError("optimized Python is forbidden for SDK acceptance proof gates")

import argparse
from contextlib import closing, contextmanager
from dataclasses import asdict
import fcntl
import hashlib
import os
from pathlib import Path
import re
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("program", "scorer", "scorer") + ("program", "scorer") * 6
PHASES = {"qualify": (0, 11), "reuse-0": (11, 13), "reuse-1": (13, 15)}


def _api():
    # Lazy even for --help. All exports are existing first-party implementations.
    from bench.sql_reuse_timing import Timer
    from ptc import sql_isolation as isolation
    from ptc.sql_isolation_acceptance import _inventory
    from train import sql_capture as capture, sql_episodes as evidence
    from train import sql_pilot_assets as assets, sql_skill_eval as evaluator
    from train import sql_skill_workflow as sdk, sql_skills as skills
    from train.sql_skill_isolation_acceptance import _PROGRAM, _ids, _forbid_host
    return SimpleNamespace(
        Timer=Timer, isolation=isolation, inventory=_inventory, capture=capture,
        evidence=evidence, assets=assets, evaluator=evaluator, sdk=sdk, skills=skills,
        program=_PROGRAM, fixture_task=_fixture_task, fixture_ids=_ids, forbid_host=_forbid_host,
    )


def _fixture_task(directory, label, rows, table):
    """Trusted fixture SQL, explicitly closed before returning its task."""
    import sqlite3
    from bench.task import SqlTask

    path = directory / (label + ".sqlite")
    quoted = '"' + table.replace('"', '""') + '"'
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute("CREATE TABLE " + quoted + " (value INTEGER)")
            connection.executemany(
                "INSERT INTO " + quoted + " VALUES (?)", ((i,) for i in range(rows)),
            )
    return SqlTask(
        name=label, question="Count rows in the only user table.", evidence="",
        gold_sql="SELECT COUNT(*) FROM " + quoted, db_id=label, db_path=str(path),
        tier="simple", tier_source="derived", shape="select-count",
        coarse_shape="aggregate", source="fixture",
    )


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    a = _api()
    return a.assets.strict_json(a.assets.read_file(path))


def _write_bytes(path, raw):
    _api().assets.write_new(path, raw)


def _write(path, value):
    _write_bytes(path, _api().assets.canonical_bytes(value) + b"\n")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def required_source_paths():
    a = _api()
    return sorted(set(a.isolation._PROGRAM_PATHS) | set(a.isolation._SCORER_PATHS)
                  | set(a.evidence.SOURCE_PATHS) | set(a.capture.SOURCE_PATHS)
                  | set(a.skills.SOURCE_PATHS) | {
                      "train/__init__.py", "train/guards.py", "train/sql_capture.py",
                      "train/sql_episodes.py", "train/sql_pilot_assets.py",
                      "train/sql_skill_workflow.py", "train/sql_skill_isolation_acceptance.py",
                      "train/sql_skill_sdk_acceptance.py", "train/test_sql_skill_sdk_acceptance.py",
                      "bench/sql_reuse_timing.py", "ptc/sql_isolation_acceptance.py",
                  })


def _pinned_json(path, pin):
    if path is None or pin is None:
        raise ValueError("separate local fixture approval/context and whole-file pin required")
    a = _api()
    raw = a.assets.read_file(path)
    _require(_sha(raw) == a.assets.sha(pin), "external whole-file pin mismatch")
    return a.assets.strict_json(raw)


def authorize(args):
    if args.allow_native_execution is not True:
        raise ValueError("explicit native opt-in required")
    a = _api()
    root = a.assets.safe_path(args.campaign_dir)
    a.assets.safe_path(root.parent, exists=True, directory=True)
    raw = a.assets.read_file(args.execution_profile)
    _require(_sha(raw) == a.assets.sha(args.expected_profile_sha256), "profile pin mismatch")
    consent = _pinned_json(args.consent_file, args.consent_sha256)
    expected = {
        "format": "co_train_sdk_native_local_test_consent",
        "issuer": "parent-reviewed-local-test-assignment", "campaign_dir": str(root),
        "profile_sha256": args.expected_profile_sha256, "max_native_jobs": 15,
        "phase_jobs": [11, 2, 2], "retries": 0, "model_calls": 0,
    }
    a.assets.closed(consent, (*expected, "reviewed_revision", "source_pins"))
    for key, value in expected.items():
        _require(a.assets.canonical_bytes(consent[key]) == a.assets.canonical_bytes(value),
                 "consent scope differs: " + key)
    _require(type(consent["reviewed_revision"]) is str
             and re.fullmatch("[0-9a-f]{40}", consent["reviewed_revision"]) is not None,
             "reviewed revision required")
    _require(type(consent["source_pins"]) is dict
             and set(consent["source_pins"]) == set(required_source_paths()),
             "complete reviewed controller source pins required")
    pins = tuple(a.isolation.SourcePin(n, sha) for n, sha in sorted(consent["source_pins"].items()))
    a.isolation.validate_source_pins(pins, source_root=ROOT)
    profile = a.isolation.load_execution_profile(args.execution_profile, source_root=ROOT)
    _require({p.path for p in profile.binding.program.sources} == set(a.isolation._PROGRAM_PATHS)
             and {p.path for p in profile.binding.scorer.sources} == set(a.isolation._SCORER_PATHS),
             "exact existing native role closures required")
    controller = {p.path: p.sha256 for p in profile.binding.controller_sources}
    _require(all(controller.get(p.path) == p.sha256 for p in pins),
             "profile controller missing reviewed helper/core pins")
    _require(profile.admission_bytes == 469762048 and profile.max_sample_age_ms == 4000,
             "original memory admission envelope required")
    for role in ("program", "scorer"):
        limit = a.isolation.limits_for(role)
        _require((limit.memory_bytes, limit.swap_bytes, limit.pids, limit.nofile, limit.deadline_ms)
                 == (268435456, 0, 1, 64, 10000 if role == "program" else 30000),
                 "original role envelope required")
    return SimpleNamespace(root=root, profile=profile, profile_pin=args.expected_profile_sha256,
                           consent_pin=args.consent_sha256, pins=pins,
                           profile_path=args.execution_profile, consent=consent)


def verify_approval(ctx, args):
    approval = _pinned_json(args.local_fixture_approval, args.local_fixture_approval_sha256)
    checkpoint = _read(ctx.root / "checkpoint.json")
    expected = {
        "format": "co_train_sdk_native_local_fixture_approval",
        "issuer": "parent-reviewed-local-test-fixture", "campaign_dir": str(ctx.root),
        "checkpoint_sha256": _sha(_api().assets.read_file(ctx.root / "checkpoint.json")),
        "consent_sha256": ctx.consent_pin, "profile_sha256": ctx.profile_pin,
        "candidate_sha256": checkpoint["candidate_sha256"],
        "promotion_sha256": checkpoint["promotion_sha256"],
        "approval_ids": asdict(_api().fixture_ids("approval", "approval")),
        "max_reuse_native_jobs": 4,
    }
    _require(_api().assets.canonical_bytes(approval) == _api().assets.canonical_bytes(expected)
             and checkpoint["approval_ids"] == expected["approval_ids"]
             and checkpoint["consent_sha256"] == ctx.consent_pin
             and checkpoint["profile_sha256"] == ctx.profile_pin
             and checkpoint["status"] == "UNAPPROVED_LOCAL_TEST_FIXTURE",
             "local fixture approval differs from exact checkpoint/IDs/pins")
    for name, key in (("candidate/candidate.json", "candidate_sha256"),
                      ("qualification/promotion.json", "promotion_sha256")):
        _require(_sha(_api().assets.read_file(ctx.root / name)) == expected[key],
                 "approved artifact pin mismatch")
    return checkpoint


def _slots(root):
    paths = sorted(root.glob("dispatch-*.json"))
    _require([p.name for p in paths] == [f"dispatch-{i:02d}.json" for i in range(1, len(paths) + 1)],
             "noncontiguous campaign slots")
    return paths


def _stop(root, reason):
    if not (root / "STOP.json").exists():
        _write(root / "STOP.json", {"status": "STOP_UNRESOLVED_NO_RETRY", "reason": reason})


class Guard:
    """One locked sequential phase; durable slots are never rolled back."""
    def __init__(self, ctx, phase, forward):
        self.ctx, self.phase, self.forward = ctx, phase, forward

    def reserve(self, role, request):
        root = self.ctx.root
        if (root / "STOP.json").exists():
            raise RuntimeError("campaign stopped; retained evidence, no retries")
        paths = _slots(root)
        if len(paths) >= 15:
            raise ValueError("15-job campaign budget exhausted")
        floor, ceiling = PHASES[self.phase]
        _require(floor <= len(paths) < ceiling, "phase native budget exhausted")
        _require(role == ROLES[len(paths)], "unexpected native dispatch role")
        a = _api()
        a.isolation.validate_source_pins(self.ctx.pins, source_root=ROOT)
        index = len(paths) + 1
        _write(root / f"dispatch-{index:02d}.json", {
            "phase": self.phase, "role": role, "pid": os.getpid(),
            "request_sha256": a.isolation.request_sha256(request),
            "profile_sha256": self.ctx.profile_pin,
        })
        return index

    def dispatch(self, executor, role, request, db_path):
        index = self.reserve(role, request)
        try:
            _require(executor.profile == self.ctx.profile, "dispatch profile changed")
            result = self.forward(executor, role, request, db_path)
            _write(self.ctx.root / f"outcome-{index:02d}.json", asdict(result))
            if result.abort is not None:
                raise RuntimeError("native abort; campaign stopped without retry")
            return result
        except BaseException:
            _stop(self.ctx.root, "native abort/exception after reserved slot")
            raise


@contextmanager
def phase_claim(ctx, phase):
    a = _api()
    _require(phase in PHASES, "unknown phase")
    if phase == "qualify":
        ctx.root.mkdir(mode=0o700)  # Exclusive new campaign, never overwrite/replay.
        a.assets.fsync_dir(ctx.root.parent)
    a.assets.safe_path(ctx.root, exists=True, directory=True)
    fd = os.open(ctx.root / "campaign.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    claimed = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (ctx.root / "STOP.json").exists():
            raise RuntimeError("campaign stopped; no phase retry")
        floor, _ = PHASES[phase]
        _require(len(_slots(ctx.root)) == floor, "phase start budget differs")
        previous = {"reuse-0": "qualify", "reuse-1": "reuse-0"}.get(phase)
        if previous:
            prior = _read(ctx.root / (previous + ".done.json"))
            _require(prior["status"] == "PHASE_COMPLETE"
                     and prior["consent_sha256"] == ctx.consent_pin,
                     "prior phase not complete")
            # Independent CLI invocation, distinct from EVERY preceding phase.
            predecessors = ("qualify",) if phase == "reuse-0" else ("qualify", "reuse-0")
            for predecessor in predecessors:
                identity = _read(ctx.root / (predecessor + ".done.json"))["process_identity"]
                _require(identity != _process_identity(), "fresh interpreter required")
        _write(ctx.root / (phase + ".claim.json"), {
            "consent_sha256": ctx.consent_pin, "process_identity": _process_identity(),
        })
        claimed = True
        yield Guard(ctx, phase, a.isolation._run_isolated)
    except BaseException:
        if claimed:
            _stop(ctx.root, "phase interrupted; retain owned resources/evidence")
        raise
    finally:
        os.close(fd)


def _process_identity():
    # PID plus interpreter start token: PID reuse never implies same interpreter.
    return {"pid": os.getpid(), "start_token": _START_TOKEN}


_START_TOKEN = time.time_ns()


def check_timing(observation):
    ticks, span, syncs = (observation[k] for k in ("ticks_ns", "span", "fsync_finished_ns"))
    _require(len(ticks) == 2 and all(type(t) is int for t in ticks)
             and span["completed"] is True and span["clock_valid"] is True
             and type(span["elapsed_ns"]) is int and span["elapsed_ns"] == ticks[1] - ticks[0]
             and span["elapsed_ns"] > 0 and observation["identity_preserved"] is True,
             "invalid callback timing/identity")
    _require(bool(syncs) and all(type(t) is int and ticks[0] <= t <= ticks[1] for t in syncs),
             "final SDK fsync outside timer")


def timed(kind, callback):
    a = _api()
    ticks, syncs, results = [], [], []
    real_fsync = a.assets.fsync_dir
    def clock():
        value = time.perf_counter_ns()
        ticks.append(value)
        return value
    def fsync(path):
        real_fsync(path)
        syncs.append(time.perf_counter_ns())
    def operation():
        result = callback()
        results.append(result)
        return result
    timer = a.Timer(clock=clock)
    with patch.object(a.assets, "fsync_dir", fsync):
        result = timer.run(kind, operation, allow_execution=True)
    observation = {"span": asdict(timer.observations[0]), "ticks_ns": ticks,
                   "fsync_finished_ns": syncs, "identity_preserved": result is results[0]}
    check_timing(observation)
    return result, observation


def _capture(path, score, profile):
    a = _api()
    raw = a.assets.read_file(path)
    item = a.capture.decode_capture(raw)
    _require(a.capture.encode_capture(item) == raw and item.schema_version == 2
             and item.execution_binding == profile.binding and item.execution_abort is None
             and item.result.valid is True and item.result.score == score
             and [r.role for r in item.runtime_receipts] == ["program", "scorer"],
             "canonical native capture/result/receipts required")
    return item


def test_real_sdk_timer_qualification(ctx):
    """Explicit CLI only: 2 source + 1 rescore + 8 qualification jobs."""
    a = _api()
    fixture = ctx.root / "fixtures"
    fixture.mkdir(mode=0o700)
    task = a.fixture_task(fixture, "origin", 2, "source table")
    executor = a.isolation.PilotExecutor(ctx.profile, state_dir=ctx.root / "qualify-jobs")
    session = a.capture.start_capture(
        task, ids=a.fixture_ids("origin", "development"),
        expected_db_sha256=_sha(Path(task.db_path).read_bytes()),
        allow_execution=True, executor=executor)
    observed = session.step("print('FINAL_SQL:SELECT -1')")
    _require(observed == "FINAL_SQL:SELECT -1", "source native observation differs")
    source = session.finish("SELECT -1")
    source_path = ctx.root / "source.json"
    _write_bytes(source_path, a.capture.encode_capture(source))
    _capture(source_path, 0, ctx.profile)
    _require(len(_slots(ctx.root)) == 2, "source generation must use exactly two jobs")
    candidate, prepare_span = timed("candidate_prepare", lambda: a.sdk.create_candidate_file(
        source, source_task=task, source_ids=source.ids, skill_id="local-sdk-rowcount-fixture",
        program=a.program, output_dir=ctx.root / "candidate"))
    _require(len(_slots(ctx.root)) == 2, "candidate creation must be data-only")
    cases = tuple(a.evaluator.SkillCase(
        "qualification", a.fixture_task(fixture, f"qualification-{i}", rows, table),
        a.fixture_ids(f"qualification-{i}", "qualification"),
    ) for i, (rows, table) in enumerate(((0, "empty"), (1, "one"), (3, 'odd " table'), (7, "seven"))))
    approval_ids = a.fixture_ids("approval", "approval")
    files, qualification_span = timed("qualification", lambda: a.sdk.qualify_candidate_files(
        candidate, source_path, expected_source_capture_sha256=_sha(source_path.read_bytes()),
        source_case=a.evaluator.SkillCase("source_failure", task, source.ids,
                                         expected_db_sha256=source.db_sha256),
        qualification_cases=cases, ids=approval_ids, output_dir=ctx.root / "qualification",
        allow_execution=True, executor=executor))
    _require(files.promotion_path is not None and len(files.capture_paths) == 4,
             "four qualification captures/promotion required")
    actuals = [_capture(p, 1, ctx.profile) for p in files.capture_paths]
    _require(len({v.db_sha256 for v in actuals}) == 4, "four distinct qualification DBs required")
    _require(not (ctx.root / "qualification/.promotion.pending").exists(), "pending promotion remains")
    candidate_raw, promotion_raw = candidate.read_bytes(), files.promotion_path.read_bytes()
    _require(a.skills.encode_candidate(a.skills.decode_candidate(candidate_raw)) == candidate_raw
             and a.skills.encode_promotion(a.skills.decode_promotion(promotion_raw)) == promotion_raw,
             "canonical candidate/promotion required")
    return {
        "status": "UNAPPROVED_LOCAL_TEST_FIXTURE", "consent_sha256": ctx.consent_pin,
        "profile_sha256": ctx.profile_pin, "candidate_sha256": _sha(candidate_raw),
        "promotion_sha256": _sha(promotion_raw), "source_sha256": _sha(source_path.read_bytes()),
        "approval_ids": asdict(approval_ids), "native_jobs": 11,
        "historical": [{"path": task.db_path, "sha256": source.db_sha256}] + [
            {"path": case.task.db_path, "sha256": item.db_sha256}
            for case, item in zip(cases, actuals, strict=True)],
        "spans": [prepare_span, qualification_span], "source_generation_excluded_jobs": 2,
        "model_calls": 0, "baseline_full_observations": 0,
    }


def test_real_sdk_timer_fresh_reuse(ctx, checkpoint, index):
    """One fresh CLI interpreter, 2 jobs; historical files only moved once."""
    a = _api()
    candidate = ctx.root / "candidate/candidate.json"
    promotion = ctx.root / "qualification/promotion.json"
    record = a.skills.decode_promotion(promotion.read_bytes())
    _require(record.ids == a.fixture_ids("approval", "approval")
             and record.schema_version == 2 and record.binding.execution_binding == ctx.profile.binding,
             "promotion exact IDs/native binding required")
    history = checkpoint["historical"]
    _require(len(history) == 5 and len({item["path"] for item in history}) == 5,
             "five historical databases required")
    preserved = ctx.root / "preserved-databases"
    if index == 0:
        preserved.mkdir(mode=0o700)
        for i, item in enumerate(history):
            source = a.assets.safe_path(Path(item["path"]), exists=True)
            _require(source.parent == ctx.root / "fixtures"
                     and _sha(a.assets.read_file(source)) == item["sha256"],
                     "historical DB path/hash differs")
            os.rename(source, preserved / f"{i}.sqlite")
        a.assets.fsync_dir(preserved)
        a.assets.fsync_dir(ctx.root / "fixtures")
    for i, item in enumerate(history):
        _require(not Path(item["path"]).exists()
                 and _sha(a.assets.read_file(preserved / f"{i}.sqlite")) == item["sha256"],
                 "historical DB absent/preserved proof failed")
    label, rows, table = (("fresh-eleven", 11, "new table"),
                          ("fresh-thirteen", 13, 'new " table'))[index]
    task = a.fixture_task(ctx.root / "fixtures", label, rows, table)
    case = a.evaluator.SkillCase("reuse", task, a.fixture_ids(label, "heldout"),
                                expected_db_sha256=_sha(Path(task.db_path).read_bytes()))
    executor = a.isolation.PilotExecutor(ctx.profile, state_dir=ctx.root / f"reuse-{index}-jobs")
    before = len(_slots(ctx.root))
    try:
        a.sdk.reuse_approved_files(
            candidate, promotion, case, expected_promotion_sha256="0" * 64,
            ids=record.ids, output_dir=ctx.root / f"bad-pin-{index}",
            allow_execution=True, executor=executor)
    except ValueError as exc:
        _require("external approved promotion pin" in str(exc), "bad pin failed for unrelated reason")
    else:
        raise ValueError("bad pin admitted")
    _require(len(_slots(ctx.root)) == before, "bad pin dispatched native work")
    path, span = timed("reuse", lambda: a.sdk.reuse_approved_files(
        candidate, promotion, case, expected_promotion_sha256=checkpoint["promotion_sha256"],
        ids=record.ids, output_dir=ctx.root / f"reuse-{index}",
        allow_execution=True, executor=executor))
    actual = _capture(path, 1, ctx.profile)
    _require(actual.ids == case.ids and actual.final_answer == task.gold_sql
             and actual.steps[0].action == a.skills.decode_candidate(candidate.read_bytes()).program,
             "fresh reuse provenance/answer/action differs")
    if index == 1:
        first = _capture(ctx.root / "reuse-0/reuse.json", 1, ctx.profile)
        _require(first.db_sha256 != actual.db_sha256, "fresh reuse DBs must differ")
    return {"span": span, "capture_sha256": _sha(path.read_bytes()),
            "db_sha256": actual.db_sha256, "bad_pin_dispatches": 0}


def _resources():
    # fstat excludes the transient descriptor used by listdir itself.
    descriptors = []
    for name in os.listdir("/dev/fd"):
        try:
            value = os.fstat(int(name))
            descriptors.append((int(name), value.st_dev, value.st_ino, value.st_mode))
        except OSError:
            pass
    return {"fds": sorted(descriptors),
            "threads": sorted((t.ident, t.name) for t in threading.enumerate())}


def verify_jobs(ctx, count):
    """Read original runtime finalization/actor evidence, never infer from EX."""
    a, root = _api(), ctx.root
    journals = sorted(root.glob("*-jobs/*/journal.json"))
    _require(len(journals) == count and len(_slots(root)) == count,
             "native journal/dispatch count differs")
    roles, requests, cids = [], [], []
    for path in journals:
        journal = _read(path)
        job, role = path.parent, journal["role"]
        roles.append(role)
        requests.append(journal["request_sha256"])
        cids.append(journal["cid"])
        _require(journal["state"] == "CLOSED" and "failure" not in journal
                 and journal["cleanup_elapsed"] <= 12
                 and journal["cleanup_deadline"] - journal["cleanup_trigger"] == 12
                 and journal["profile_sha256"] == ctx.profile_pin,
                 "native job not CLOSED inside original cleanup envelope")
        shared = ctx.profile.shared_state_dir
        pending = a.isolation._read_owned(shared / ("FINALIZATION-PENDING-" + journal["nonce"] + ".json"))
        committed = a.isolation._read_finalization_record(a.isolation._read_owned(
            shared / ("FINALIZATION-COMMITTED-" + journal["nonce"] + ".json")), "committed")
        _, _, outcome = a.isolation._validate_finalization(
            ctx.profile, pending, committed["terminal_ack"], job=job)
        _require(committed["pending_sha256"] == _sha(pending) and outcome.abort is None,
                 "native finalization abort/digest differs")
        events = [a.assets.strict_json(line) for line in a.assets.read_file(
            job / "events.jsonl").splitlines()]
        kinds = [e["kind"] for e in events]
        ordered = ["OBSERVER_QUIESCING", "OBSERVER_PARKED", "EXIT_GRANT_INTENT",
                   "EXIT_GRANT_SENT", "STOPPED", "OBSERVER_RETIRED",
                   "OBSERVER_THREAD_JOINED", "ACTOR_ABSENCE_PROOF", "OBSERVER_JOIN_ACK",
                   "DELETE", "ABSENCE"]
        positions = [kinds.index(k) for k in ordered]
        _require(positions == sorted(positions) and kinds.count("EXIT_GRANT_SENT") == 1,
                 "native cleanup/grant ordering differs")
        grant, stopped = kinds.index("EXIT_GRANT_SENT"), kinds.index("STOPPED")
        _require(not any(k in ("MEMORY_SAMPLE", "MEMORY_STATS_REJECTED",
                              "MEMORY_TERMINAL_DISCARDED") for k in kinds[grant:stopped + 1]),
                 "memory sampling crossed native exit grant")
        start = kinds.index("START_ATTEMPT")
        admission = [e for e in events[:start] if e["kind"] == "MEMORY_SAMPLE"]
        _require(bool(admission) and admission[-1]["available"] >= 469762048
                 and 0 <= events[start]["at"] - admission[-1]["finished"] <= 4,
                 "fresh native admission headroom unproven")
        for pid in journal["guardians"] + [e["pid"] for e in events if e["kind"] == "CLI_STARTED"]:
            try:
                os.kill(pid, 0)  # Existence query only, never a cleanup signal.
            except ProcessLookupError:
                pass
            else:
                raise ValueError("owned native actor still present")
    expected = list(ROLES[:count])
    _require(sorted(roles) == sorted(expected), "native PROGRAM/SCORER counts differ")
    slots = [_read(p) for p in _slots(root)]
    _require(sorted(requests) == sorted(s["request_sha256"] for s in slots),
             "dispatch requests differ from native journals")
    _require(len(list(root.glob("outcome-*.json"))) == count,
             "native outcomes incomplete")
    for i, slot in enumerate(slots, 1):
        data = _read(root / f"outcome-{i:02d}.json")
        outcome = (a.isolation.program_outcome_from_dict(data) if slot["role"] == "program"
                   else a.isolation.score_outcome_from_dict(data))
        _require(outcome.abort is None, "native outcomes aborted")
        if slot["role"] == "scorer":
            _require(outcome.result.valid is True and outcome.result.score == (0 if i <= 3 else 1),
                     "source/rescore/qualification/reuse EX differs")
    inventory = a.inventory(a.isolation._Daemon(ctx.profile))
    _require(inventory == _read(root / "baseline.json")
             and all(cid not in inventory for cid in cids),
             "owned absence/unrelated inventory changed")
    return {"closed_jobs": count, "program_jobs": roles.count("program"),
            "scorer_jobs": roles.count("scorer"), "unclosed_jobs": 0, "aborts": 0,
            "baseline_unchanged": True, "owned_actors_absent": True}


def _network_guard(profile):
    def audit(event, args):
        if event == "socket.connect":
            connection, target = args
            if connection.family != socket.AF_UNIX or target != str(profile.daemon_socket):
                raise PermissionError("only the explicit local daemon socket is permitted")
        if event in ("socket.getaddrinfo", "socket.bind", "socket.sendto"):
            raise PermissionError("external network forbidden")
    sys.addaudithook(audit)


def run(args):
    ctx = authorize(args)
    _require(args.phase == "reuse" or args.case_index is None, "case index only applies to reuse")
    checkpoint = verify_approval(ctx, args) if args.phase == "reuse" else None
    _require(args.phase != "reuse" or args.case_index in (0, 1), "reuse requires case index 0 or 1")
    phase = "qualify" if args.phase == "qualify" else f"reuse-{args.case_index}"
    a = _api()
    _network_guard(ctx.profile)
    with phase_claim(ctx, phase) as guard:
        resources = _resources()
        if phase == "qualify":
            _write(ctx.root / "baseline.json", a.inventory(a.isolation._Daemon(ctx.profile)))
        else:
            _require(a.inventory(a.isolation._Daemon(ctx.profile)) == _read(ctx.root / "baseline.json"),
                     "baseline changed before reuse")
        with patch.object(a.isolation, "_run_isolated", guard.dispatch), \
                patch.object(a.evidence, "_score", a.forbid_host), \
                patch.object(a.evidence.sql_arms.ArmPair, "run", a.forbid_host):
            result = (test_real_sdk_timer_qualification(ctx) if phase == "qualify"
                      else test_real_sdk_timer_fresh_reuse(ctx, checkpoint, args.case_index))
        proof = verify_jobs(ctx, PHASES[phase][1])
        _require(_resources() == resources, "raw descriptor/thread delta is nonzero")
        if phase == "qualify":
            _write(ctx.root / "checkpoint.json", result)
        else:
            _write(ctx.root / (phase + ".result.json"), result)
        _write(ctx.root / (phase + ".done.json"), {
            "status": "PHASE_COMPLETE", "consent_sha256": ctx.consent_pin,
            "process_identity": _process_identity(), "proof": proof,
            "raw_fd_delta": 0, "thread_delta": 0,
        })
        if phase == "reuse-1":
            _write(ctx.root / "campaign-receipt.json", {
                "status": "LOCAL_TEST_FIXTURE_NATIVE_SDK_PASS", **proof,
                "native_jobs": 15, "model_calls": 0, "retries": 0,
                "approval_scope": "LOCAL_TEST_FIXTURE_ONLY",
                "timing_scope": "synchronous_sdk_callback_wall_including_final_fsync",
                "source_generation_excluded_jobs": 2, "baseline_full_observations": 0,
                "consent_sha256": ctx.consent_pin, "profile_sha256": ctx.profile_pin,
                "raw_fd_delta": 0, "thread_delta": 0,
            })
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase", required=True, choices=("qualify", "reuse"))
    parser.add_argument("--case-index", type=int, choices=(0, 1))
    parser.add_argument("--execution-profile", required=True, type=Path)
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--campaign-dir", required=True, type=Path)
    parser.add_argument("--allow-native-execution", action="store_true")
    parser.add_argument("--consent-file", required=True, type=Path)
    parser.add_argument("--consent-sha256", required=True)
    parser.add_argument("--local-fixture-approval", type=Path)
    parser.add_argument("--local-fixture-approval-sha256")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
