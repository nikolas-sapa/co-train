"""Integration contracts for source-bound reporting evidence records.

Covers spec/sql-reporting-evidence.md: scripted episode v2 and incremental
capture v3 over real temporary SQLite, the real PTC runtime and the actual
host Bash wrapper. Dispatch and scorer calls are counted through observation
wrappers; nothing fabricates results. The three named controls —
`test_expected_reporting_binding`, `test_reporting_source_binding` and
`test_replay_telemetry_comparison` — exercise the shared seams
(require_expected, instrument_sources, snapshots_equal) so bypassing them in
memory fails a call-phase assertion. Missing implementation fails inside
test bodies, never during collection.
"""

from __future__ import annotations

import builtins
import dataclasses
import hashlib
import importlib
import inspect
import io
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bench import fixture, score
from bench.loader import load_bird
from ptc import sql_arms, sql_qa
from ptc.sql_qa import QaChannel, report_ack
from train import grpo_ptc

REJECT = (TypeError, ValueError)
MAX_BYTES = 8 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
ID_FIELDS = (
    "corpus_id", "split_id", "run_id", "episode_id", "policy_id",
    "policy_revision",
)
REPORTING_SOURCE_PATHS = ("ptc/sql_qa.py", "train/sql_reporting.py")
SQL_PROGRAM = 'print(execute_sql(query="SELECT COUNT(*) AS n FROM school")[0]["n"])'
REPORT_DETAIL = "fixture allegation detail"
REPORT_PROGRAM = (
    f'print(report_defect(kind="task_defect", detail="{REPORT_DETAIL}"))'
)
BASH_SQL_ACTION = 'execute_sql "SELECT COUNT(*) AS n FROM school"'
BASH_REPORT_ACTION = (
    "report_defect '"
    + json.dumps({"kind": "task_defect", "detail": REPORT_DETAIL},
                 separators=(",", ":"))
    + "'"
)


def _episodes():
    try:
        return importlib.import_module("train.sql_episodes")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_episodes":
            raise
        pytest.fail("train.sql_episodes is not implemented", pytrace=False)


def _captures():
    try:
        return importlib.import_module("train.sql_capture")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_capture":
            raise
        pytest.fail("train.sql_capture is not implemented", pytrace=False)


def _reporting():
    try:
        return importlib.import_module("train.sql_reporting")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_reporting":
            raise
        pytest.fail("train.sql_reporting is not implemented", pytrace=False)


def _comparison():
    try:
        return importlib.import_module("train.sql_capture_comparison")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_capture_comparison":
            raise
        pytest.fail("train.sql_capture_comparison is not implemented",
                    pytrace=False)


def _ids(episodes, **changes):
    values = dict(zip(ID_FIELDS, (
        "committed-bird-fixture", "reporting-engineering", "reporting-run",
        "reporting-episode", "trusted-host-policy", "reporting-fixture-v1",
    )))
    values.update(changes)
    return episodes.EpisodeIds(**values)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _episode_envelope(payload, *, version):
    return _canonical({
        "schema_version": version, "payload": payload,
        "sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
    })


def _capture_envelope(payload, *, version):
    return _canonical({
        "format": "sql_execution_capture", "schema_version": version,
        "payload": payload,
        "sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
    })


def _as_snapshot(value, reporting):
    if type(value) is reporting.ReportingSnapshot:
        return value
    return reporting.snapshot_from_dict(value)


def _telemetry_dict(record, reporting):
    return reporting.snapshot_to_dict(_as_snapshot(record.telemetry, reporting))


def _report_events(doc, arm="ptc"):
    return [e for e in doc["arms"][arm]["events"] if e["type"] == "report"]


def _dispatch_spy(monkeypatch):
    original = sql_arms.ArmPair.run
    calls = []

    def run(pair, arm, action, *, bindir=None):
        calls.append((arm, action, bindir))
        return original(pair, arm, action, bindir=bindir)

    monkeypatch.setattr(sql_arms.ArmPair, "run", run)
    return calls


def _score_spy(monkeypatch, *modules, forbidden=False):
    original = score.execution_accuracy
    calls = []

    def execute(*args, **kwargs):
        calls.append((args, kwargs))
        if forbidden:
            raise AssertionError("protected scorer called before validation")
        return original(*args, **kwargs)

    for module in (score, *modules):
        if getattr(module, "execution_accuracy", None) is original:
            monkeypatch.setattr(module, "execution_accuracy", execute)
    return calls


def _environment_sentry(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("execution environment built during decode")

    monkeypatch.setattr(grpo_ptc, "sql_environment", forbidden)
    monkeypatch.setattr(sql_arms, "build_sql_arms", forbidden)


def _reported_actions(arm):
    if arm == "ptc":
        return (SQL_PROGRAM, REPORT_PROGRAM)
    return (BASH_SQL_ACTION, BASH_REPORT_ACTION)


def _reported_episode(episodes, task, config, *, arm="ptc", ids=None):
    return episodes.record_scripted(
        task, arm=arm, actions=_reported_actions(arm),
        final_answer=task.gold_sql,
        ids=_ids(episodes) if ids is None else ids, reporting=config,
    )


def _reported_session(captures, task, config, *, ids=None):
    return captures.start_capture(
        task, ids=_ids(_episodes()) if ids is None else ids,
        allow_execution=True, reporting=config,
    )


def _reported_capture(captures, task, config, *, ids=None, actions=()):
    session = _reported_session(captures, task, config, ids=ids)
    for action in actions:
        session.step(action)
    return session, session.finish(task.gold_sql)


def _mutate_database(task):
    conn = sqlite3.connect(task.db_path)
    try:
        conn.execute(
            "UPDATE school SET name = name || '-changed' WHERE school_id = 1")
        conn.commit()
    finally:
        conn.close()


def _invalidated(session):
    for operation in (
        lambda: session.step("print('must-not-run')"),
        lambda: session.finish("SELECT 1"),
        session.abort,
    ):
        with pytest.raises(RuntimeError):
            operation()


@pytest.fixture(autouse=True)
def no_model_stack(monkeypatch):
    original_import = builtins.__import__
    original_module = importlib.import_module
    attempted = []
    forbidden = {
        "torch", "transformers", "trl", "unsloth", "vllm", "verifiers",
        "datasets", "huggingface_hub", "httpx", "pydantic",
    }

    def check(name):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"model/framework import attempted: {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return original_import(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        check(name)
        return original_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    yield
    assert attempted == []


@pytest.fixture
def tasks(tmp_path):
    return load_bird(fixture.materialize(tmp_path / "corpus"))


@pytest.fixture
def task(tasks):
    return tasks[0]


def _isolation_executor(tmp_path):
    """Concrete, locally bound configuration. Neither constructor contacts Docker."""
    from ptc import sql_isolation as isolation

    def pins(names):
        return tuple(isolation.SourcePin(
            name, hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
        ) for name in names)

    binary = tmp_path / "observer-fixture"
    binary.write_bytes(b"data-only observer fixture, never executed\n")
    profile = isolation.make_execution_profile(
        daemon_socket=(tmp_path / "daemon.sock").resolve(),
        observer=isolation.MemoryObserver(
            binary=binary,
            binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        ),
        program_sources=pins(("ptc/runtime.py", "ptc/sql_runtime.py")),
        scorer_sources=pins(("bench/score.py", "bench/task.py")),
        controller_sources=pins(("train/sql_capture.py", "train/sql_skills.py",
                                 "train/sql_skill_eval.py", "ptc/sql_isolation.py")),
    )
    return isolation.PilotExecutor(profile, state_dir=tmp_path / "run")


def _isolation_score_receipt(sql, task, kwargs):
    from ptc.sql_isolation import RuntimeReceipt, ScoreRequest, request_sha256

    instrument = kwargs["instrument"]
    return RuntimeReceipt(
        "scorer",
        request_sha256(ScoreRequest(
            dataclasses.replace(task, db_path="/db.sqlite"), sql,
            instrument.scorer_timeout_s, instrument.scorer_max_rows,
            instrument.compare, kwargs["db_sha256"],
        )),
        "guest-python", "guest-sqlite", "b" * 64, "c" * 64,
    )


def _isolated_v2_capture(captures, task, tmp_path, monkeypatch):
    """A real schema-v2 capture produced through a patched concrete executor."""
    from ptc import sql_isolation as isolation

    executor = _isolation_executor(tmp_path)

    def scorer(self, sql, task, **kwargs):
        return isolation.ScoreOutcome(
            score.ExResult(1.0, "match", True, "", 1, 1), None,
            _isolation_score_receipt(sql, task, kwargs),
        )

    monkeypatch.setattr(isolation.PilotExecutor, "score_sql", scorer)
    session = captures.start_capture(
        task, ids=_ids(_episodes()), allow_execution=True, executor=executor)
    return session.finish("SELECT 1")


# --------------------------------------------------------------------------
# Additive signatures and legacy compatibility.
# --------------------------------------------------------------------------

def test_reporting_parameters_are_keyword_only_and_additive():
    episodes, captures = _episodes(), _captures()
    for function, name in (
        (episodes.record_scripted, "reporting"),
        (captures.start_capture, "reporting"),
        (episodes.rescore_sql, "expected_reporting"),
        (episodes.reexecute_sql, "expected_reporting"),
        (captures.rescore_capture, "expected_reporting"),
    ):
        parameter = inspect.signature(function).parameters.get(name)
        assert parameter is not None, f"{function.__name__} lacks {name}"
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is None
    assert [f.name for f in dataclasses.fields(episodes.SqlEpisode)][-2:] == [
        "reporting", "telemetry",
    ]
    assert [f.name for f in dataclasses.fields(captures.SqlCapture)][-2:] == [
        "reporting", "telemetry",
    ]
    assert [f.name for f in dataclasses.fields(
        episodes.ReexecutionResult)][-2:] == ["telemetry", "telemetry_matches"]


def test_legacy_records_decode_byte_identically_and_omit_reporting(
    task, tmp_path, monkeypatch,
):
    episodes, captures = _episodes(), _captures()
    episode = episodes.record_scripted(
        task, arm="ptc", actions=(SQL_PROGRAM,), final_answer=task.gold_sql,
        ids=_ids(episodes),
    )
    assert episode.schema_version == 1
    assert episode.reporting is None and episode.telemetry is None
    encoded_episode = episodes.encode_episode(episode)
    payload = json.loads(encoded_episode)["payload"]
    assert "reporting" not in payload and "telemetry" not in payload
    restored = episodes.decode_episode(encoded_episode)
    assert restored == episode
    assert episodes.encode_episode(restored) == encoded_episode

    session = captures.start_capture(
        task, ids=_ids(episodes), allow_execution=True)
    capture_v1 = session.finish(task.gold_sql)
    capture_v2 = _isolated_v2_capture(captures, task, tmp_path, monkeypatch)
    assert capture_v1.schema_version == 1 and capture_v2.schema_version == 2
    for capture in (capture_v1, capture_v2):
        assert capture.reporting is None and capture.telemetry is None
        encoded = captures.encode_capture(capture)
        wire = json.loads(encoded)["payload"]
        assert "reporting" not in wire and "telemetry" not in wire
        assert captures.decode_capture(encoded) == capture
        assert captures.encode_capture(captures.decode_capture(encoded)) == encoded


def test_disabled_calls_and_observations_stay_unchanged(task):
    episodes, captures = _episodes(), _captures()
    episode = episodes.record_scripted(
        task, arm="ptc", actions=(SQL_PROGRAM,), final_answer=task.gold_sql,
        ids=_ids(episodes),
    )
    assert sql_qa.REPORT_PROMPT not in episode.prompt
    assert sql_qa.REPORT_TOOL not in episode.prompt
    assert episodes.rescore_sql(episode, task, ids=episode.ids) == episode.result
    replay = episodes.reexecute_sql(
        episode, task, ids=episode.ids, allow_execution=True)
    assert replay.observations_match is True and replay.score_matches is True
    assert replay.telemetry is None and replay.telemetry_matches is None
    session = captures.start_capture(
        task, ids=_ids(episodes), allow_execution=True)
    assert session.reporting_snapshot is None
    capture = session.finish(task.gold_sql)
    assert capture.reporting is None and capture.telemetry is None


def test_disabled_execution_imports_zero_reporting_modules(tmp_path):
    """A fresh interpreter runs the whole disabled record/rescore/replay path
    without `ptc.sql_qa` or `train.sql_reporting` entering `sys.modules`."""
    db = tmp_path / "fresh-interp.sqlite"
    child = (
        "import sqlite3, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "db_path = sys.argv[1]\n"
        "conn = sqlite3.connect(db_path)\n"
        "try:\n"
        "    conn.execute('CREATE TABLE readings (amount INTEGER NOT NULL)')\n"
        "    conn.execute('INSERT INTO readings (amount) VALUES (41)')\n"
        "    conn.commit()\n"
        "finally:\n"
        "    conn.close()\n"
        "from bench.task import SqlTask\n"
        "task = SqlTask(\n"
        "    name='fresh-interp', question='What amount is recorded?',\n"
        "    evidence='', gold_sql='SELECT amount FROM readings',\n"
        "    db_id='fresh-interp', db_path=db_path, tier='simple',\n"
        "    tier_source='derived', shape='fixture',\n"
        "    coarse_shape='fixture', source='fixture')\n"
        "from train.sql_episodes import (\n"
        "    EpisodeIds, record_scripted, rescore_sql, reexecute_sql)\n"
        "ids = EpisodeIds('c', 's', 'r', 'e', 'p', 'v')\n"
        "episode = record_scripted(\n"
        "    task, arm='ptc',\n"
        "    actions=('print(execute_sql(query=\"SELECT amount FROM readings\")"
        "[0][\"amount\"])',),\n"
        "    final_answer=task.gold_sql, ids=ids)\n"
        "rescore_sql(episode, task, ids=ids)\n"
        "reexecute_sql(episode, task, ids=ids, allow_execution=True)\n"
        "leaked = sorted(\n"
        "    m for m in sys.modules\n"
        "    if 'sql_qa' in m or 'sql_reporting' in m)\n"
        "assert not leaked, f'disabled path imported {leaked}'\n"
        "print('CHILD_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child, str(db)],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert "CHILD_OK" in result.stdout


# --------------------------------------------------------------------------
# Scripted reporting evidence (episode v2): real actions, real telemetry.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("arm", ("ptc", "bash"))
def test_scripted_reporting_records_and_replays_two_real_actions(
    task, arm, monkeypatch,
):
    episodes, reporting = _episodes(), _reporting()
    config = reporting.ReportingConfig()
    actions = _reported_actions(arm)
    calls = _dispatch_spy(monkeypatch)
    episode = _reported_episode(episodes, task, config, arm=arm)
    assert episode.schema_version == 2
    assert len(episode.steps) == len(calls) == 2
    assert reporting.require_expected(episode.reporting, config) is None
    assert set(REPORTING_SOURCE_PATHS) <= set(episode.instrument.source_paths)
    assert sql_qa.REPORT_PROMPT in episode.prompt
    assert episode.prompt == (
        sql_arms.build_sql_arms(task, qa=QaChannel()).prompt(arm))
    assert report_ack() in episode.steps[1].observation
    doc = _telemetry_dict(episode, reporting)
    reports = _report_events(doc, arm)
    assert len(reports) == 1 and reports[0]["detail"] == REPORT_DETAIL
    assert reports[0]["provenance"] == (
        "catalog_callback" if arm == "ptc" else "agent_output")
    other = "bash" if arm == "ptc" else "ptc"
    assert doc["arms"][other]["events"] == []
    assert doc["arms"][other]["reports"] == doc["arms"][other]["dropped"] == 0
    encoded = episodes.encode_episode(episode)
    wire = json.loads(encoded)["payload"]
    assert "reporting" in wire and "telemetry" in wire
    assert episodes.encode_episode(episodes.decode_episode(encoded)) == encoded

    restored = episodes.decode_episode(encoded)
    calls.clear()
    replay = episodes.reexecute_sql(
        restored, task, ids=episode.ids, allow_execution=True,
        expected_reporting=config)
    assert len(calls) == 2
    assert tuple(action for _, action, _ in calls) == actions
    assert replay.observations == tuple(
        step.observation for step in episode.steps)
    assert replay.observations_match is True
    assert replay.score_matches is True
    assert type(replay.telemetry_matches) is bool
    assert replay.telemetry_matches is True
    assert reporting.snapshot_to_dict(
        _as_snapshot(replay.telemetry, reporting)) == doc
    scores = _score_spy(monkeypatch, episodes)
    assert episodes.rescore_sql(
        episode, task, ids=episode.ids,
        expected_reporting=config) == episode.result
    assert len(scores) == 1


# --------------------------------------------------------------------------
# Incremental reporting evidence (capture v3): lifecycle and quotas.
# --------------------------------------------------------------------------

def test_reporting_capture_lifecycle_preserves_exact_telemetry(task, monkeypatch):
    captures, reporting = _captures(), _reporting()
    config = reporting.ReportingConfig()
    session = _reported_session(captures, task, config)
    assert type(_as_snapshot(
        session.reporting_snapshot, reporting)) is reporting.ReportingSnapshot
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, captures, _episodes())
    assert session.step(REPORT_PROGRAM) == report_ack()
    session.step(SQL_PROGRAM)
    assert len(calls) == 2
    capture = session.finish(task.gold_sql)
    assert len(calls) == 2 and len(scores) == 1
    assert capture.schema_version == 3
    assert capture.terminal_label == "final_submitted"
    assert capture.result.score == 1.0
    assert sql_qa.REPORT_PROMPT in capture.prompt
    assert set(REPORTING_SOURCE_PATHS) <= set(capture.instrument.source_paths)
    wire = json.loads(captures.encode_capture(capture))["payload"]
    assert "reporting" in wire and "telemetry" in wire
    assert "execution_binding" not in wire
    assert "runtime_receipts" not in wire
    assert "execution_abort" not in wire
    assert reporting.require_expected(capture.reporting, config) is None
    doc = _telemetry_dict(capture, reporting)
    reports = _report_events(doc)
    assert len(reports) == 1 and reports[0]["detail"] == REPORT_DETAIL
    assert doc["arms"]["bash"]["events"] == []
    current = reporting.snapshot_to_dict(
        _as_snapshot(session.reporting_snapshot, reporting))
    assert current == doc
    calls.clear()
    assert captures.rescore_capture(
        capture, task, ids=capture.ids,
        expected_reporting=config) == capture.result
    assert calls == [] and len(scores) == 2
    _invalidated(session)
    assert calls == [] and len(scores) == 2


def test_reporting_abort_scores_zero_and_keeps_diagnostic_telemetry(
    task, monkeypatch,
):
    captures, reporting = _captures(), _reporting()
    config = reporting.ReportingConfig()
    session = _reported_session(captures, task, config)
    session.step(REPORT_PROGRAM)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, captures, _episodes(), forbidden=True)
    capture = session.abort()
    assert capture.schema_version == 3
    assert capture.terminal_label == "aborted"
    assert capture.result is None and capture.final_answer is None
    assert calls == scores == []
    doc = _telemetry_dict(capture, reporting)
    assert len(_report_events(doc)) == 1
    retained = _as_snapshot(session.reporting_snapshot, reporting)
    assert reporting.snapshot_to_dict(retained) == doc
    _invalidated(session)
    with pytest.raises(REJECT):
        captures.rescore_capture(
            capture, task, ids=capture.ids, expected_reporting=config)
    assert calls == scores == []


def test_independent_reporting_sessions_have_separate_quotas(task):
    captures, reporting = _captures(), _reporting()
    config = reporting.ReportingConfig()
    first = _reported_session(captures, task, config)
    second = _reported_session(captures, task, config)
    flood = "\n".join(
        f'print(report_defect(kind="other", detail="flood-{index}"))'
        for index in range(9)
    )
    first.step(flood)
    second.step(REPORT_PROGRAM)
    first_doc = reporting.snapshot_to_dict(
        _as_snapshot(first.reporting_snapshot, reporting))
    second_doc = reporting.snapshot_to_dict(
        _as_snapshot(second.reporting_snapshot, reporting))
    assert len(_report_events(first_doc)) == 8
    assert any(
        e["type"] == "overflow" for e in first_doc["arms"]["ptc"]["events"])
    assert len(_report_events(second_doc)) == 1
    first.abort()
    second.abort()


def test_invalidated_reporting_session_retains_diagnostic_telemetry(
    task, monkeypatch,
):
    captures, reporting = _captures(), _reporting()
    config = reporting.ReportingConfig()
    session = _reported_session(captures, task, config)
    session.step(REPORT_PROGRAM)
    _mutate_database(task)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, captures, _episodes(), forbidden=True)
    with pytest.raises(REJECT):
        session.step(SQL_PROGRAM)
    # Invalidated sessions keep diagnostic telemetry without sealing success.
    doc = reporting.snapshot_to_dict(
        _as_snapshot(session.reporting_snapshot, reporting))
    assert len(_report_events(doc)) == 1
    assert _report_events(doc)[0]["detail"] == REPORT_DETAIL
    _invalidated(session)
    assert calls == scores == []


# --------------------------------------------------------------------------
# Control: independent expected reporting configuration.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("operation", (
    "episode_rescore", "episode_reexecute", "capture_rescore",
))
@pytest.mark.parametrize("kind", ("missing", "different", "disabled"))
def test_expected_reporting_binding(task, operation, kind, monkeypatch):
    episodes, captures, reporting = _episodes(), _captures(), _reporting()
    config = reporting.ReportingConfig(shortcut_ids=("fixture_alpha",))
    different = reporting.ReportingConfig(shortcut_ids=("fixture_beta",))
    if kind == "disabled":
        episode = episodes.record_scripted(
            task, arm="ptc", actions=(SQL_PROGRAM,),
            final_answer=task.gold_sql, ids=_ids(episodes))
        plain = captures.start_capture(
            task, ids=_ids(episodes), allow_execution=True)
        capture = plain.finish(task.gold_sql)
        expected = config
    else:
        episode = _reported_episode(episodes, task, config)
        _, capture = _reported_capture(
            captures, task, config, actions=(REPORT_PROGRAM,))
        episode = episodes.decode_episode(episodes.encode_episode(episode))
        capture = captures.decode_capture(captures.encode_capture(capture))
        expected = None if kind == "missing" else different
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, episodes, captures, forbidden=True)
    with pytest.raises(REJECT):
        if operation == "episode_rescore":
            episodes.rescore_sql(
                episode, task, ids=episode.ids, expected_reporting=expected)
        elif operation == "episode_reexecute":
            episodes.reexecute_sql(
                episode, task, ids=episode.ids, allow_execution=True,
                expected_reporting=expected)
        else:
            captures.rescore_capture(
                capture, task, ids=capture.ids, expected_reporting=expected)
    assert calls == scores == []


# --------------------------------------------------------------------------
# Control: real changed selected-source bytes and the enabled prompt.
# --------------------------------------------------------------------------

def _redirect_reads(monkeypatch, redirect):
    real_read_bytes = Path.read_bytes
    real_open = builtins.open
    real_io_open = io.open

    def read_bytes(self, *args, **kwargs):
        return real_read_bytes(
            redirect.get(self.resolve(), self), *args, **kwargs)

    def wrap(original):
        def wrapped(file, *args, **kwargs):
            try:
                target = redirect.get(Path(file).resolve())
            except TypeError:
                target = None
            return original(target if target is not None else file,
                            *args, **kwargs)
        return wrapped

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(builtins, "open", wrap(real_open))
    monkeypatch.setattr(io, "open", wrap(real_io_open))


@pytest.mark.parametrize("operation", (
    "episode_rescore", "episode_reexecute", "capture_step", "capture_rescore",
))
@pytest.mark.parametrize("target", (
    "ptc/sql_qa.py", "train/sql_reporting.py", "train/sql_episodes.py", "prompt",
))
def test_reporting_source_binding(task, operation, target, tmp_path, monkeypatch):
    episodes, captures, reporting = _episodes(), _captures(), _reporting()
    config = reporting.ReportingConfig()
    episode = _reported_episode(episodes, task, config)
    session = _reported_session(captures, task, config)
    session.step(REPORT_PROGRAM)
    capture = session.finish(task.gold_sql)
    probe = _reported_capture(
        captures, task, config, actions=(REPORT_PROGRAM,))[1]
    live = _reported_session(captures, task, config)
    paths = (
        episode.instrument.source_paths if operation.startswith("episode")
        else probe.instrument.source_paths
    )
    if target == "prompt":
        for attr, original in (
            ("prompt", sql_arms.ArmPair.prompt),
        ):
            def changed(self, arm, _original=original):
                return _original(self, arm) + "\nchanged reporting prompt"
            monkeypatch.setattr(sql_arms.ArmPair, attr, changed)
        original_for = sql_arms.prompt_for

        def changed_for(*args, **kwargs):
            return original_for(*args, **kwargs) + "\nchanged reporting prompt"
        monkeypatch.setattr(sql_arms, "prompt_for", changed_for)
    else:
        assert target in paths, f"{target} is not a bound reporting source"
        copied = tmp_path / "source-root"
        redirect = {}
        for name in paths:
            source, destination = ROOT / name, copied / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            redirect[source.resolve()] = destination
        real_sources = reporting.instrument_sources
        recorded_sha = (
            episode.instrument.source_sha256 if operation.startswith("episode")
            else probe.instrument.source_sha256
        )
        clean_paths, clean_sha = real_sources(copied, tuple(paths))
        assert clean_paths == tuple(paths)
        assert clean_sha == recorded_sha
        changed = copied / target
        changed.write_bytes(
            changed.read_bytes() + b"\n# reporting binding control\n")
        moved_paths, moved_sha = real_sources(copied, tuple(paths))
        assert moved_paths == tuple(paths)
        assert moved_sha != recorded_sha
        monkeypatch.setattr(
            reporting, "instrument_sources",
            lambda _root, base: real_sources(copied, base))
        for module in (episodes, captures):
            if getattr(module, "instrument_sources", None) is real_sources:
                monkeypatch.setattr(
                    module, "instrument_sources",
                    lambda _root, base: real_sources(copied, base))
        _redirect_reads(monkeypatch, redirect)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, episodes, captures, forbidden=True)
    with pytest.raises(REJECT):
        if operation == "episode_rescore":
            episodes.rescore_sql(
                episode, task, ids=episode.ids, expected_reporting=config)
        elif operation == "episode_reexecute":
            episodes.reexecute_sql(
                episode, task, ids=episode.ids, allow_execution=True,
                expected_reporting=config)
        elif operation == "capture_step":
            live.step(SQL_PROGRAM)
        else:
            captures.rescore_capture(
                capture, task, ids=capture.ids, expected_reporting=config)
    assert calls == scores == []


def test_artifact_source_paths_are_never_used_to_read_files(task, monkeypatch):
    episodes, reporting = _episodes(), _reporting()
    config = reporting.ReportingConfig()
    episode = _reported_episode(episodes, task, config)
    payload = json.loads(episodes.encode_episode(episode))["payload"]
    sentinels = [
        "artifact-sentinel-path.py",
        "../artifact-sentinel-escape.py",
        "/tmp/artifact-sentinel-absolute.py",
    ]
    payload["instrument"]["source_paths"] = (
        list(payload["instrument"]["source_paths"]) + sentinels)
    forged = episodes.decode_episode(
        _episode_envelope(payload, version=episode.schema_version))
    reads = []

    def wrap(original):
        def wrapped(file, *args, **kwargs):
            try:
                resolved = str(Path(file).resolve())
            except TypeError:
                resolved = ""
            if "artifact-sentinel" in resolved:
                reads.append(resolved)
            return original(file, *args, **kwargs)
        return wrapped

    monkeypatch.setattr(builtins, "open", wrap(builtins.open))
    monkeypatch.setattr(io, "open", wrap(io.open))
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, episodes, forbidden=True)
    with pytest.raises(REJECT):
        episodes.rescore_sql(
            forged, task, ids=episode.ids, expected_reporting=config)
    assert calls == scores == []
    assert reads == []


# --------------------------------------------------------------------------
# Control: replay telemetry comparison tracks real callback telemetry.
# --------------------------------------------------------------------------

def test_replay_telemetry_comparison(task, monkeypatch):
    episodes, reporting = _episodes(), _reporting()
    config = reporting.ReportingConfig()
    episode = _reported_episode(episodes, task, config)
    real_submit = QaChannel.submit

    def altered(self, arm, *, kind, detail):
        return real_submit(
            self, arm, kind=kind, detail=detail + " (telemetry changed)")

    monkeypatch.setattr(QaChannel, "submit", altered)
    replay = episodes.reexecute_sql(
        episode, task, ids=episode.ids, allow_execution=True,
        expected_reporting=config)
    assert replay.observations_match is True
    assert replay.score_matches is True
    assert type(replay.telemetry_matches) is bool
    assert replay.telemetry_matches is False
    doc = reporting.snapshot_to_dict(
        _as_snapshot(replay.telemetry, reporting))
    assert any(
        "(telemetry changed)" in event.get("detail", "")
        for event in doc["arms"]["ptc"]["events"]
    )


# --------------------------------------------------------------------------
# Admission/downgrade: reporting never coexists with isolated execution, and
# reporting fields never downgrade into legacy versions.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("operation", ("start_capture", "rescore_capture"))
def test_reporting_with_executor_rejects_before_binding_or_dispatch(
    task, operation, tmp_path, monkeypatch,
):
    from ptc import sql_isolation as isolation

    captures, reporting = _captures(), _reporting()
    config = reporting.ReportingConfig()
    executor = _isolation_executor(tmp_path)

    def binding_sentry(*args, **kwargs):
        raise AssertionError("executor binding was inspected")

    def dispatch_sentry(*args, **kwargs):
        raise AssertionError("isolated job dispatched")

    monkeypatch.setattr(
        isolation, "build_execution_binding", binding_sentry)
    monkeypatch.setattr(
        isolation.PilotExecutor, "run_program", dispatch_sentry)
    monkeypatch.setattr(
        isolation.PilotExecutor, "score_sql", dispatch_sentry)
    with pytest.raises(REJECT):
        if operation == "start_capture":
            captures.start_capture(
                task, ids=_ids(_episodes()), allow_execution=True,
                executor=executor, reporting=config)
        else:
            _, capture = _reported_capture(
                captures, task, config, actions=(REPORT_PROGRAM,))
            captures.rescore_capture(
                capture, task, ids=capture.ids, executor=executor,
                expected_reporting=config)


def _reporting_wire(reporting, shortcut_ids=()):
    return reporting.config_to_dict(
        reporting.ReportingConfig(shortcut_ids=shortcut_ids))


def _telemetry_wire(reporting, channel=None):
    channel = QaChannel() if channel is None else channel
    return reporting.snapshot_to_dict(reporting.ReportingSnapshot(channel.export()))


def test_reported_metadata_never_downgrades_into_legacy_records(
    task, tmp_path, monkeypatch,
):
    episodes, captures, reporting = _episodes(), _captures(), _reporting()
    config = reporting.ReportingConfig()
    episode_v1 = episodes.record_scripted(
        task, arm="ptc", actions=(SQL_PROGRAM,), final_answer=task.gold_sql,
        ids=_ids(episodes))
    episode_v2 = _reported_episode(episodes, task, config)
    plain = captures.start_capture(
        task, ids=_ids(episodes), allow_execution=True)
    capture_v1 = plain.finish(task.gold_sql)
    capture_v2 = _isolated_v2_capture(captures, task, tmp_path, monkeypatch)
    _, capture_v3 = _reported_capture(
        captures, task, config, actions=(REPORT_PROGRAM,))
    episode_payload = json.loads(episodes.encode_episode(episode_v1))["payload"]
    v2_payload = json.loads(episodes.encode_episode(episode_v2))["payload"]
    v1_cap = json.loads(captures.encode_capture(capture_v1))["payload"]
    v2_cap = json.loads(captures.encode_capture(capture_v2))["payload"]
    v3_cap = json.loads(captures.encode_capture(capture_v3))["payload"]
    wire_cfg = _reporting_wire(reporting)
    wire_telemetry = _telemetry_wire(reporting)
    foreign_telemetry = _telemetry_wire(reporting, _foreign_arm_channel())
    accepted = []

    def reject(decoder, data):
        with pytest.raises(REJECT):
            decoder(data)

    one = dict(episode_payload, reporting=wire_cfg)
    reject(episodes.decode_episode, _episode_envelope(one, version=1))
    two = dict(episode_payload, reporting=wire_cfg, telemetry=wire_telemetry)
    reject(episodes.decode_episode, _episode_envelope(two, version=1))
    missing = dict(v2_payload)
    del missing["reporting"]
    reject(episodes.decode_episode, _episode_envelope(missing, version=2))
    missing = dict(v2_payload)
    del missing["telemetry"]
    reject(episodes.decode_episode, _episode_envelope(missing, version=2))
    null = dict(v2_payload, reporting=None)
    reject(episodes.decode_episode, _episode_envelope(null, version=2))
    null = dict(v2_payload, telemetry=None)
    reject(episodes.decode_episode, _episode_envelope(null, version=2))
    mixed = dict(v2_payload, telemetry=foreign_telemetry)
    reject(episodes.decode_episode, _episode_envelope(mixed, version=2))
    one = dict(v1_cap, reporting=wire_cfg)
    reject(captures.decode_capture, _capture_envelope(one, version=1))
    two = dict(v1_cap, reporting=wire_cfg, telemetry=wire_telemetry)
    reject(captures.decode_capture, _capture_envelope(two, version=1))
    reported_v2 = dict(v2_cap, reporting=wire_cfg, telemetry=wire_telemetry)
    reject(captures.decode_capture, _capture_envelope(reported_v2, version=2))
    isolated_v3 = dict(v3_cap, execution_binding=v2_cap["execution_binding"])
    reject(captures.decode_capture, _capture_envelope(isolated_v3, version=3))
    missing = dict(v3_cap)
    del missing["reporting"]
    reject(captures.decode_capture, _capture_envelope(missing, version=3))
    missing = dict(v3_cap)
    del missing["telemetry"]
    reject(captures.decode_capture, _capture_envelope(missing, version=3))
    assert accepted == []

    with pytest.raises(REJECT):
        dataclasses.replace(episode_v1, reporting=wire_cfg)
    with pytest.raises(REJECT):
        dataclasses.replace(episode_v2, reporting=None)
    with pytest.raises(REJECT):
        dataclasses.replace(episode_v2, telemetry=None)
    with pytest.raises(REJECT):
        dataclasses.replace(capture_v1, telemetry=wire_telemetry)
    with pytest.raises(REJECT):
        dataclasses.replace(
            capture_v3, execution_binding=capture_v2.execution_binding)


def _foreign_arm_channel():
    channel = QaChannel()
    channel.consume_output(
        "bash",
        sql_qa.REPORT_MARKER
        + '{"kind":"other","detail":"foreign arm event"}')
    return channel


def test_decoding_reported_artifacts_builds_nothing_and_stays_bounded(
    task, monkeypatch,
):
    episodes, captures, reporting = _episodes(), _captures(), _reporting()
    config = reporting.ReportingConfig()
    episode = _reported_episode(episodes, task, config)
    _, capture = _reported_capture(captures, task, config,
                                   actions=(REPORT_PROGRAM,))
    encoded_episode = episodes.encode_episode(episode)
    encoded_capture = captures.encode_capture(capture)
    _environment_sentry(monkeypatch)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, episodes, captures, forbidden=True)

    def blocked(*args, **kwargs):
        raise AssertionError("arm dispatch during decode")

    monkeypatch.setattr(sql_arms.ArmPair, "run", blocked)
    assert episodes.decode_episode(encoded_episode) == episode
    assert captures.decode_capture(encoded_capture) == capture
    assert calls == scores == []
    with pytest.raises(REJECT):
        episodes.decode_episode(b" " * (MAX_BYTES + 1))
    with pytest.raises(REJECT):
        captures.decode_capture(b" " * (MAX_BYTES + 1))


# --------------------------------------------------------------------------
# Capture comparison boundary and strict config admission before execution.
# --------------------------------------------------------------------------

def test_capture_comparison_refuses_reporting_mismatch_keeps_legacy(
    task, tmp_path,
):
    captures, comparison, reporting = (
        _captures(), _comparison(), _reporting())
    config_a = reporting.ReportingConfig()
    config_b = reporting.ReportingConfig(shortcut_ids=("fixture_alpha",))
    episodes = _episodes()
    _, first = _reported_capture(captures, task, config_a,
                                 actions=(REPORT_PROGRAM,))
    _, second = _reported_capture(
        captures, task, config_b,
        ids=_ids(episodes, episode_id="different-config"))
    one, two = tmp_path / "one.capture", tmp_path / "two.capture"
    one.write_bytes(captures.encode_capture(first))
    two.write_bytes(captures.encode_capture(second))
    crossed = comparison.compare_capture_files(
        ("case",), baseline_paths={"case": one}, treatment_paths={"case": two})
    assert crossed.cases[0].refusal_reasons
    assert any(
        "reporting" in reason
        for reason in crossed.cases[0].refusal_reasons)
    assert crossed.statistics is None
    assert crossed.admissible is False
    _, third = _reported_capture(
        captures, task, config_a,
        ids=_ids(episodes, episode_id="same-config"))
    three = tmp_path / "three.capture"
    three.write_bytes(captures.encode_capture(third))
    paired = comparison.compare_capture_files(
        ("case",), baseline_paths={"case": one}, treatment_paths={"case": three})
    assert not any(
        "reporting" in reason
        for reason in paired.cases[0].refusal_reasons)
    assert paired.admissible is True
    assert paired.statistics is not None
    first_plain = captures.start_capture(
        task, ids=_ids(episodes, episode_id="legacy-a"), allow_execution=True)
    second_plain = captures.start_capture(
        task, ids=_ids(episodes, episode_id="legacy-b"), allow_execution=True)
    left, right = tmp_path / "left.capture", tmp_path / "right.capture"
    left.write_bytes(captures.encode_capture(first_plain.finish(task.gold_sql)))
    right.write_bytes(captures.encode_capture(second_plain.finish(task.gold_sql)))
    legacy = comparison.compare_capture_files(
        ("case",), baseline_paths={"case": left}, treatment_paths={"case": right})
    assert legacy.admissible is True
    assert legacy.statistics is not None


@pytest.mark.parametrize("bad", (
    pytest.param(True, id="bool"),
    pytest.param({}, id="dict"),
    pytest.param("defect_reports", id="mode-string"),
    pytest.param(object(), id="object"),
))
@pytest.mark.parametrize("operation", ("record_scripted", "start_capture"))
def test_invalid_reporting_config_rejected_before_any_execution(
    task, operation, bad, monkeypatch,
):
    episodes, captures = _episodes(), _captures()
    _environment_sentry(monkeypatch)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, episodes, captures, forbidden=True)
    with pytest.raises(REJECT):
        if operation == "record_scripted":
            episodes.record_scripted(
                task, arm="ptc", actions=(SQL_PROGRAM,),
                final_answer=task.gold_sql, ids=_ids(episodes), reporting=bad)
        else:
            captures.start_capture(
                task, ids=_ids(episodes), allow_execution=True, reporting=bad)
    assert calls == scores == []
