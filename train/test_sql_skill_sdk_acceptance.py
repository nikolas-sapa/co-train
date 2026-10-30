"""Offline fixture guards. None of these tests establish native acceptance."""
from contextlib import closing
from dataclasses import asdict
import gc
import importlib
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import weakref

import pytest


@pytest.fixture
def api():
    return importlib.import_module("train.sql_skill_sdk_acceptance")


@pytest.fixture
def context(api, tmp_path):
    """Real current profile/codecs; owned inert observer, never executed."""
    a = api._api()
    binary = tmp_path / "inert-observer"
    binary.write_bytes(b"owned test data, not an executable\n")
    pins = {name: api._sha((api.ROOT / name).read_bytes())
            for name in api.required_source_paths()}
    source = lambda names: tuple(a.isolation.SourcePin(n, pins[n]) for n in sorted(names))
    profile = a.isolation.make_execution_profile(
        daemon_socket=tmp_path / "unused.sock",
        observer=a.isolation.MemoryObserver(binary=binary, binary_sha256=api._sha(binary.read_bytes())),
        program_sources=source(a.isolation._PROGRAM_PATHS),
        scorer_sources=source(a.isolation._SCORER_PATHS),
        controller_sources=source(pins),
    )
    profile_path = tmp_path / "profile.json"
    a.assets.write_new(profile_path, a.isolation.execution_profile_canonical_bytes(profile))
    consent = {
        "format": "co_train_sdk_native_local_test_consent",
        "issuer": "parent-reviewed-local-test-assignment",
        "reviewed_revision": "a" * 40,
        "campaign_dir": str(tmp_path / "campaign"),
        "profile_sha256": api._sha(profile_path.read_bytes()),
        "source_pins": pins, "max_native_jobs": 15, "phase_jobs": [11, 2, 2],
        "retries": 0, "model_calls": 0,
    }
    consent_path = tmp_path / "consent.json"
    a.assets.write_new(consent_path, a.assets.canonical_bytes(consent) + b"\n")
    args = SimpleNamespace(
        phase="qualify", case_index=None, allow_native_execution=True,
        campaign_dir=Path(consent["campaign_dir"]), execution_profile=profile_path,
        expected_profile_sha256=consent["profile_sha256"],
        consent_file=consent_path, consent_sha256=api._sha(consent_path.read_bytes()),
        local_fixture_approval=None, local_fixture_approval_sha256=None,
    )
    return args, api.authorize(args)


def test_missing_explicit_native_context_fails_before_dispatch(api, context, monkeypatch):
    args, ctx = context
    calls = []
    monkeypatch.setattr(api._api().isolation, "_run_isolated",
                        lambda *a, **k: calls.append(a))
    args.allow_native_execution = False
    with pytest.raises(ValueError, match="explicit native opt-in"):
        api.authorize(args)
    assert calls == [] and not ctx.root.exists()
    child = subprocess.run(
        [sys.executable, "-O", "-B", "-m", "train.sql_skill_sdk_acceptance", "--help"],
        cwd=api.ROOT, capture_output=True, text=True, check=False,
    )
    assert child.returncode != 0 and "optimized Python is forbidden" in child.stderr
    missing = subprocess.run(
        [sys.executable, "-B", "-m", "train.sql_skill_sdk_acceptance"],
        cwd=api.ROOT, capture_output=True, text=True, check=False,
    )
    assert missing.returncode != 0 and "required" in missing.stderr
    inert = subprocess.run(
        [sys.executable, "-B", "-c",
         "import sys; import train.sql_skill_sdk_acceptance; "
         "assert not any(n == 'ptc' or n == 'bench' or n.startswith('train.sql_skill_workflow') "
         "for n in sys.modules)"],
        cwd=api.ROOT, capture_output=True, text=True, check=False,
    )
    assert inert.returncode == 0, inert.stderr
    help_result = subprocess.run(
        [sys.executable, "-B", "-m", "train.sql_skill_sdk_acceptance", "--help"],
        cwd=api.ROOT, capture_output=True, text=True, check=False,
    )
    assert help_result.returncode == 0 and "--local-fixture-approval" in help_result.stdout
    assert not ctx.root.exists()


def test_changed_profile_or_source_pin_fails_before_dispatch(api, context, monkeypatch):
    args, ctx = context
    calls = []
    monkeypatch.setattr(api._api().isolation, "_run_isolated",
                        lambda *a, **k: calls.append(a))
    original = args.expected_profile_sha256
    args.expected_profile_sha256 = "0" * 64
    with pytest.raises(ValueError, match="profile pin"):
        api.authorize(args)
    args.expected_profile_sha256 = original
    consent = api._read(args.consent_file)
    consent["source_pins"]["train/sql_skill_sdk_acceptance.py"] = "0" * 64
    args.consent_file = args.consent_file.parent / "changed-consent.json"
    api._write(args.consent_file, consent)
    args.consent_sha256 = api._sha(args.consent_file.read_bytes())
    with pytest.raises(ValueError, match="source pin mismatch"):
        api.authorize(args)
    assert calls == [] and not ctx.root.exists()


def test_changed_capture_dependency_fails_before_dispatch(api, tmp_path, monkeypatch):
    """Authorize real owned source copies, then mutate without replacing consent."""
    a = api._api()
    source_root = api.ROOT
    owned = tmp_path / "reviewed-sources"
    for name in set(api.required_source_paths()) | set(a.capture.SOURCE_PATHS):
        target = owned / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / name).read_bytes())
    monkeypatch.setattr(api, "ROOT", owned)
    args, ctx = context.__wrapped__(api, tmp_path)
    calls = []
    monkeypatch.setattr(a.isolation, "_run_isolated", lambda *a, **k: calls.append(a))
    profile_raw = args.execution_profile.read_bytes()
    consent_raw = args.consent_file.read_bytes()
    api.authorize(args)  # Unchanged reviewed sources really authorize.
    dependency = next(p for p in a.capture.SOURCE_PATHS if p == "train/grpo_ptc.py")
    target = owned / dependency
    target.write_bytes(target.read_bytes() + b"\n# owned capture-dependency mutation\n")
    try:
        api.authorize(args)  # Same externally pinned consent/profile, never re-pinned.
    except ValueError as exc:
        assert "source pin mismatch" in str(exc)
    else:
        pytest.fail("capture-only dependency change admitted by source authorization")
    assert args.execution_profile.read_bytes() == profile_raw
    assert args.consent_file.read_bytes() == consent_raw
    assert calls == [] and not ctx.root.exists()


def test_missing_or_mismatched_local_fixture_approval_fails_before_reuse(api, context, monkeypatch):
    args, ctx = context
    a = api._api()
    ctx.root.mkdir()
    candidate, qualified, _ = _host_files(api, ctx.root)
    checkpoint = {
        "status": "UNAPPROVED_LOCAL_TEST_FIXTURE",
        "consent_sha256": ctx.consent_pin, "profile_sha256": ctx.profile_pin,
        "candidate_sha256": api._sha(candidate.read_bytes()),
        "promotion_sha256": api._sha(qualified.promotion_path.read_bytes()),
        "approval_ids": asdict(a.fixture_ids("approval", "approval")),
    }
    api._write(ctx.root / "checkpoint.json", checkpoint)
    calls = []
    monkeypatch.setattr(a.isolation, "_run_isolated", lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match="separate local fixture approval"):
        api.verify_approval(ctx, args)
    approval = {
        "format": "co_train_sdk_native_local_fixture_approval",
        "issuer": "parent-reviewed-local-test-fixture",
        "campaign_dir": str(ctx.root), "checkpoint_sha256": api._sha(
            (ctx.root / "checkpoint.json").read_bytes()),
        **{k: checkpoint[k] for k in ("consent_sha256", "profile_sha256",
                                     "candidate_sha256", "promotion_sha256", "approval_ids")},
        "max_reuse_native_jobs": 4,
    }
    approval["approval_ids"] = {**approval["approval_ids"], "episode_id": "wrong"}
    path = ctx.root.parent / "fixture-approval.json"
    api._write(path, approval)
    args.local_fixture_approval = path
    args.local_fixture_approval_sha256 = api._sha(path.read_bytes())
    with pytest.raises(ValueError, match="local fixture approval differs"):
        api.verify_approval(ctx, args)
    # Restore exact LOCAL fixture IDs; neither this nor the host SDK is native proof.
    approval["approval_ids"] = checkpoint["approval_ids"]
    path = ctx.root.parent / "correct-fixture-approval.json"
    api._write(path, approval)
    args.local_fixture_approval = path
    args.local_fixture_approval_sha256 = api._sha(path.read_bytes())
    assert api.verify_approval(ctx, args) == checkpoint
    assert calls == []


def test_claimed_phase_cannot_be_replayed(api, context):
    _, ctx = context
    with pytest.raises(RuntimeError, match="controlled interruption"):
        with api.phase_claim(ctx, "qualify"):
            with pytest.raises(BlockingIOError):
                with api.phase_claim(ctx, "reuse-0"):
                    pytest.fail("concurrent phase entered")
            raise RuntimeError("controlled interruption")
    assert (ctx.root / "STOP.json").exists()
    with pytest.raises(FileExistsError):
        with api.phase_claim(ctx, "qualify"):
            pytest.fail("phase replay admitted")
    assert (ctx.root / "qualify.claim.json").exists()


def test_sixteenth_dispatch_is_rejected(api, context):
    _, ctx = context
    ctx.root.mkdir()
    request = api._api().isolation.ProgramRequest("pass", 1, "a" * 64)
    for i, role in enumerate(api.ROLES, 1):
        api._write(ctx.root / f"dispatch-{i:02d}.json", {"role": role})
        if i in (11, 13):
            phase = "qualify" if i == 11 else "reuse-0"
            with pytest.raises(ValueError, match="phase native budget exhausted"):
                api.Guard(ctx, phase, None).reserve("program", request)
    guard = api.Guard(ctx, "reuse-1", None)
    with pytest.raises(ValueError, match="15-job campaign budget exhausted"):
        guard.reserve("program", request)
    assert len(list(ctx.root.glob("dispatch-*.json"))) == 15


def test_native_abort_stops_remaining_dispatches(api, context, monkeypatch):
    _, ctx = context
    a = api._api()
    request = a.isolation.ProgramRequest("pass", 1, "a" * 64)
    calls = []
    def abort(executor, role, request, db_path):
        calls.append(role)
        return a.isolation.ProgramOutcome(None, a.isolation.AbortInfo("program", "admission"), None)
    monkeypatch.setattr(a.isolation, "_run_isolated", abort)
    with pytest.raises(RuntimeError, match="native abort"):
        with api.phase_claim(ctx, "qualify") as guard:
            executor = a.isolation.PilotExecutor(ctx.profile, state_dir=ctx.root / "jobs")
            guard.dispatch(executor, "program", request, ctx.root / "unused.sqlite")
    assert calls == ["program"]
    assert len(list(ctx.root.glob("dispatch-*.json"))) == 1
    with pytest.raises(RuntimeError, match="campaign stopped"):
        api.Guard(ctx, "qualify", abort).dispatch(None, "program", request, Path("/unused"))
    assert calls == ["program"]


def test_fixture_factory_closes_connection_before_return(api, tmp_path, monkeypatch):
    """Real seven-case SQLite factory, zero raw FD delta with automatic GC off."""
    a = api._api()
    real_connect = sqlite3.connect
    references, closes = [], []
    class TrackedConnection(sqlite3.Connection):
        def close(self):
            closes.append(id(self))
            return super().close()
    def connect(*args, **kwargs):
        connection = real_connect(*args, factory=TrackedConnection, **kwargs)
        references.append(weakref.ref(connection))
        return connection
    enabled = gc.isenabled()
    gc.disable()
    try:
        before = api._resources()
        with monkeypatch.context() as change:
            change.setattr(sqlite3, "connect", connect)
            for i, (rows, table) in enumerate(((2, "source table"), (0, "empty"),
                    (1, "one"), (3, 'odd " table'), (7, "seven"),
                    (11, "new table"), (13, 'new " table'))):
                label = f"fixture-{i}"
                task = a.fixture_task(tmp_path, label, rows, table)
                assert api._resources() == before, "fixture factory retained raw DB FD before return"
                assert len(closes) == i + 1, "fixture factory did not explicitly close before return"
                quoted = '"' + table.replace('"', '""') + '"'
                assert asdict(task) == {
                    "name": label, "question": "Count rows in the only user table.",
                    "evidence": "", "gold_sql": "SELECT COUNT(*) FROM " + quoted,
                    "db_id": label, "db_path": str(tmp_path / (label + ".sqlite")),
                    "tier": "simple", "tier_source": "derived", "shape": "select-count",
                    "coarse_shape": "aggregate", "source": "fixture",
                }
                with closing(real_connect(Path(task.db_path).as_uri() + "?mode=ro", uri=True)) as db:
                    assert db.execute(task.gold_sql).fetchone() == (rows,)
                    assert db.execute("SELECT value FROM " + quoted).fetchall() == [
                        (n,) for n in range(rows)]
                assert api._resources() == before, "SQLite readback leaked raw resources"
        assert len(references) == len(closes) == 7
    finally:
        # Cleanup after assertions, never a prerequisite for the zero-FD check.
        gc.collect()
        if enabled:
            gc.enable()
    assert all(reference() is None for reference in references)


def _host_files(api, root):
    """Nonmock SQLite/file SDK proof only. Never calls the native boundary."""
    a = api._api()
    source_task = a.fixture_task(root, "origin", 2, 'source " table')
    ids = a.fixture_ids("origin", "development")
    source = a.capture.start_capture(source_task, ids=ids, allow_execution=True).finish("SELECT -1")
    assert source.result.valid and source.result.score == 0
    api._write_bytes(root / "source.json", a.capture.encode_capture(source))
    candidate, candidate_span = api.timed("candidate_prepare", lambda: a.sdk.create_candidate_file(
        source, source_task=source_task, source_ids=ids, skill_id="offline-fixture",
        program=a.program, output_dir=root / "candidate"))
    cases = tuple(a.evaluator.SkillCase(
        "qualification", a.fixture_task(root, f"q-{i}", n, table),
        a.fixture_ids(f"q-{i}", "qualification"),
    ) for i, (n, table) in enumerate(((0, "empty"), (1, "one"), (3, 'odd " table'), (7, "seven"))))
    qualified, span = api.timed("qualification", lambda: a.sdk.qualify_candidate_files(
        candidate, root / "source.json", expected_source_capture_sha256=api._sha(
            (root / "source.json").read_bytes()),
        source_case=a.evaluator.SkillCase("source_failure", source_task, ids),
        qualification_cases=cases, ids=a.fixture_ids("approval", "approval"),
        output_dir=root / "qualification", allow_execution=True))
    assert len(qualified.capture_paths) == 4 and qualified.promotion_path is not None
    assert all(a.capture.decode_capture(p.read_bytes()).result.score == 1 for p in qualified.capture_paths)
    return candidate, qualified, (candidate_span, span)


def test_timer_endpoint_follows_real_sdk_final_fsync(api, tmp_path, monkeypatch):
    a = api._api()
    def forbidden(*args, **kwargs):
        pytest.fail("offline SQLite proof reached native boundary")
    monkeypatch.setattr(a.isolation, "_run_isolated", forbidden)
    candidate, qualified, spans = _host_files(api, tmp_path)
    case = a.evaluator.SkillCase(
        "reuse", a.fixture_task(tmp_path, "fresh", 11, 'fresh " table'),
        a.fixture_ids("fresh", "heldout"),
    )
    path, span = api.timed("reuse", lambda: a.sdk.reuse_approved_files(
        candidate, qualified.promotion_path, case,
        expected_promotion_sha256=api._sha(qualified.promotion_path.read_bytes()),
        ids=a.fixture_ids("approval", "approval"), output_dir=tmp_path / "reuse",
        allow_execution=True))
    actual = a.capture.decode_capture(path.read_bytes())
    assert actual.result.valid and actual.result.score == 1
    assert actual.final_answer == case.task.gold_sql
    assert a.capture.encode_capture(actual) == path.read_bytes()
    for observation in (*spans, span):
        assert observation["identity_preserved"] is True
        assert observation["fsync_finished_ns"]
        api.check_timing(observation)


def test_final_fsync_order_control_detects_intended_red(api, tmp_path):
    _, _, spans = _host_files(api, tmp_path)
    original = spans[-1]
    mutant = {**original, "fsync_finished_ns": [original["ticks_ns"][1] + 1]}
    with pytest.raises(ValueError, match="final SDK fsync outside timer"):
        api.check_timing(mutant)
    api.check_timing(original)
