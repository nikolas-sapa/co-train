"""Offline paired quality audit, real SQLite outcomes and estimator oracle."""
from __future__ import annotations

import builtins
import dataclasses
import importlib
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import types

import pytest


CANARIES = ("QUESTION_PRIVATE_817", "SCHEMA_PRIVATE_818", "SQL_PRIVATE_819",
            "OBS_PRIVATE_820", "DETAIL_PRIVATE_821", "PATH_PRIVATE_822")
IDS = ("both-1", "both-2", "improved", "regressed-1", "regressed-2", "neither")
BASELINE = (1, 1, 0, 1, 1, 0)
TREATMENT = (1, 1, 1, 0, 0, 0)


def _api():
    try:
        return importlib.import_module("train.sql_capture_comparison")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_capture_comparison":
            raise
        pytest.fail("comparison implementation absent", pytrace=False)


@pytest.fixture(scope="module")
def captures(tmp_path_factory):
    from bench.fixture import materialize
    from bench.loader import load_bird
    from train.sql_capture import encode_capture, start_capture
    from train.sql_episodes import ActionObservation, EpisodeIds

    root = tmp_path_factory.mktemp(CANARIES[-1])
    corpus = root / "corpus"
    tasks = load_bird(materialize(corpus))
    mappings = ({}, {})
    for arm, scores in enumerate((BASELINE, TREATMENT)):
        for index, (case_id, solved) in enumerate(zip(IDS, scores)):
            task = dataclasses.replace(tasks[index],
                                       question=tasks[index].question + CANARIES[0])
            ids = EpisodeIds("fixture", "engineering", f"arm-{arm}",
                             case_id, "caller", "v1")
            session = start_capture(task, ids=ids, allow_execution=True)
            capture = session.finish(
                task.gold_sql + f" /* {CANARIES[2]} */" if solved
                else f"SELECT 'wrong {CANARIES[2]}'"
            )
            assert capture.result.valid and capture.result.score == solved
            capture = dataclasses.replace(
                capture, schema=capture.schema + CANARIES[1],
                steps=(ActionObservation("print('private')", CANARIES[3]),),
                result=dataclasses.replace(capture.result, detail=CANARIES[4]),
            )
            path = root / f"{arm}-{index}.json"
            path.write_bytes(encode_capture(capture))
            mappings[arm][case_id] = path
    # Retain fixture DBs, but make every original DB path unavailable.
    corpus.rename(root / "retained-corpus")
    assert all(not Path(task.db_path).exists() for task in tasks)
    return mappings


def _changed(captures, tmp_path, case_id=IDS[0], **changes):
    from train.sql_capture import decode_capture, encode_capture

    baseline, treatment = map(dict, captures)
    capture = decode_capture(treatment[case_id].read_bytes())
    altered = dataclasses.replace(capture, **changes)
    path = tmp_path / "changed.json"
    path.write_bytes(encode_capture(altered))
    treatment[case_id] = path
    return baseline, treatment


def _native(capture, *, abort=False):
    """Typed protocol fixture only, never native execution evidence."""
    from ptc import sql_isolation as isolation

    pins = (isolation.SourcePin("fixture.py", "a" * 64),)
    binding = isolation.ExecutionBinding(
        program=isolation.RoleBinding(
            "program", isolation.IMAGE_MANIFEST_SHA256,
            isolation.IMAGE_CONFIG_SHA256, "linux/arm64", pins, "b" * 64,
            isolation.limits_for("program")),
        scorer=isolation.RoleBinding(
            "scorer", isolation.IMAGE_MANIFEST_SHA256,
            isolation.IMAGE_CONFIG_SHA256, "linux/arm64", pins, "b" * 64,
            isolation.limits_for("scorer")),
        controller_sources=pins, policy_sha256="c" * 64,
    )
    receipts = tuple(isolation.RuntimeReceipt(
        role, "a" * 64, "fixture", "fixture", "b" * 64, "c" * 64)
        for role in ("program", "scorer"))
    changes = dict(schema_version=2, execution_binding=binding,
                   runtime_receipts=receipts)
    if abort:
        changes.update(terminal_label="execution_aborted", result=None,
                       execution_abort=isolation.AbortInfo("scorer", "transport"))
    return dataclasses.replace(capture, **changes)


def test_six_real_pairs_and_real_paired_export(captures):
    from ptc.paired import paired

    api = _api()
    result = api.compare_capture_files(IDS, *captures)
    oracle = paired(dict(zip(IDS, TREATMENT)), dict(zip(IDS, BASELINE)))
    assert result.denominator == 6 and len(result.cases) == 6
    assert result.complete and result.admissible and result.refusal_reasons == ()
    assert result.improvements == ("improved",)
    assert result.regressions == ("regressed-1", "regressed-2")
    stats = result.statistics
    assert stats.n == oracle["n"] == 6
    assert stats.baseline_successes == 4 and stats.treatment_successes == 3
    assert stats.baseline_accuracy == oracle["mean_b"] == 4 / 6
    assert stats.treatment_accuracy == oracle["mean_a"] == 3 / 6
    assert stats.delta == oracle["delta"] == -1 / 6
    assert stats.ci == oracle["ci"] and stats.p == oracle["p"]
    assert stats.treatment_only == oracle["a_only"] == 1
    assert stats.baseline_only == oracle["b_only"] == 2
    assert stats.ties == oracle["ties"] == 3
    assert result.cases[-1].baseline.state == "observed_failure"
    assert result.cases[-1].baseline.score == 0


@pytest.mark.parametrize("missing", ["baseline", "treatment", "both"])
def test_independent_planned_denominator(captures, missing):
    api = _api()
    _assert_missing(api, captures, missing)


def _assert_missing(api, captures, missing="both"):
    baseline, treatment = map(dict, captures)
    if missing in ("baseline", "both"):
        baseline.pop(IDS[-1])
    if missing in ("treatment", "both"):
        treatment.pop(IDS[-1])
    result = api.compare_capture_files(IDS, baseline, treatment)
    assert result.denominator == 6
    assert tuple(row.case_id for row in result.cases) == IDS
    assert not result.complete and not result.admissible
    assert result.statistics is None
    assert result.cases[-1].change == "unavailable"


@pytest.mark.parametrize("kind", [
    "duplicate", "empty_plan", "empty_id", "long_id", "non_string", "not_tuple",
    "undeclared_baseline", "undeclared_treatment", "bad_path", "bad_mapping",
])
def test_structural_errors_do_not_echo_inputs(captures, kind):
    api = _api()
    baseline, treatment = map(dict, captures)
    planned = IDS
    if kind == "duplicate":
        planned = IDS + (IDS[0],)
    elif kind == "empty_plan":
        planned = ()
    elif kind == "empty_id":
        planned = ("",)
    elif kind == "long_id":
        planned = ("x" * 257,)
    elif kind == "non_string":
        planned = (1,)
    elif kind == "not_tuple":
        planned = list(IDS)
    elif kind.startswith("undeclared"):
        (baseline if kind.endswith("baseline") else treatment)[CANARIES[0]] = next(iter(baseline.values()))
    elif kind == "bad_path":
        baseline[IDS[0]] = str(baseline[IDS[0]])
    else:
        baseline = [CANARIES[0]]
    with pytest.raises(ValueError) as error:
        api.compare_capture_files(planned, baseline, treatment)
    assert not any(canary in str(error.value) for canary in CANARIES)
    assert error.value.__cause__ is None and error.value.__suppress_context__


@pytest.mark.parametrize("field", [
    "task_id", "task_fingerprint", "db_sha256", "schema", "prompt", "backend",
    "instrument", "schema_version", "execution_binding",
])
def test_each_recorded_pair_binding_refuses(captures, tmp_path, field):
    _assert_binding(_api(), captures, tmp_path, field)


def _assert_binding(api, captures, tmp_path, field="task_fingerprint"):
    from train.sql_capture import decode_capture, encode_capture

    baseline, treatment = map(dict, captures)
    original = decode_capture(treatment[IDS[0]].read_bytes())
    if field in ("schema_version", "execution_binding"):
        native = _native(original)
        if field == "execution_binding":
            other = dataclasses.replace(native, execution_binding=dataclasses.replace(
                native.execution_binding, policy_sha256="d" * 64))
            base_path = tmp_path / "base-native.json"
            base_path.write_bytes(encode_capture(native))
            baseline[IDS[0]] = base_path
        else:
            other = native
    elif field == "instrument":
        other = dataclasses.replace(original, instrument=dataclasses.replace(
            original.instrument, compare="multiset"))
    else:
        value = "d" * 64 if field.endswith(("fingerprint", "sha256")) else "different"
        other = dataclasses.replace(original, **{field: value})
    path = tmp_path / "altered.json"
    path.write_bytes(encode_capture(other))
    treatment[IDS[0]] = path
    result = api.compare_capture_files(IDS, baseline, treatment)
    assert not result.admissible
    assert result.statistics is None
    assert f"{field}_mismatch" in result.cases[0].refusal_reasons
    assert len(result.cases) == result.denominator == 6


@pytest.mark.parametrize("reuse", ["path", "bytes"])
def test_capture_reuse_across_planned_cases_refuses(captures, tmp_path, reuse):
    api = _api()
    baseline, treatment = map(dict, captures)
    reused = baseline[IDS[0]]
    if reuse == "bytes":
        reused = tmp_path / "copy.json"
        reused.write_bytes(baseline[IDS[0]].read_bytes())
    baseline[IDS[1]] = reused
    result = api.compare_capture_files(IDS, baseline, treatment)
    assert not result.admissible and result.statistics is None
    assert "capture_reused" in result.refusal_reasons
    assert all("capture_reused" in result.cases[i].refusal_reasons for i in (0, 1))


def test_same_case_sharing_is_not_cross_case_reuse(captures):
    result = _api().compare_capture_files(IDS, captures[0], captures[0])
    assert result.admissible and result.statistics.delta == 0


@pytest.mark.parametrize("state", [
    "invalid_gold", "database_missing", "unscored_abort", "infrastructure_abort",
    "program_rejected",
])
def test_unscored_states_are_distinct(captures, tmp_path, state):
    from bench.score import ExResult
    from train.sql_capture import decode_capture, encode_capture

    api = _api()
    baseline, treatment = map(dict, captures)
    capture = decode_capture(treatment[IDS[0]].read_bytes())
    if state in ("invalid_gold", "database_missing"):
        capture = dataclasses.replace(capture, result=ExResult(
            0, "db_missing" if state == "database_missing" else "gold_error",
            False, CANARIES[4]))
    elif state == "unscored_abort":
        capture = dataclasses.replace(capture, terminal_label="aborted", result=None,
                                      final_answer=None, extracted_sql=None)
    elif state == "infrastructure_abort":
        capture = _native(capture, abort=True)
    else:
        capture = _native(capture)
        capture = dataclasses.replace(capture, terminal_label="program_rejected",
                                      result=None, runtime_receipts=capture.runtime_receipts[:1])
    path = tmp_path / "state.json"
    path.write_bytes(encode_capture(capture))
    treatment[IDS[0]] = path
    result = api.compare_capture_files(IDS, baseline, treatment)
    assert result.cases[0].treatment.state == state
    assert result.cases[0].treatment.score is None
    assert not result.complete and not result.admissible and result.statistics is None
    assert len(result.cases) == result.denominator == 6
    if state == "infrastructure_abort":
        assert result.cases[0].treatment.abort_stage == "scorer"
        assert result.cases[0].treatment.abort_reason == "transport"


def test_budget_refusals_do_not_hide_valid_zero(captures, tmp_path):
    from train.guards import TurnBudget
    from train.sql_capture import decode_capture
    from train.sql_episodes import ActionObservation

    original = decode_capture(captures[1][IDS[-1]].read_bytes())
    steps = original.steps * original.instrument.action_cap
    baseline, treatment = _changed(
        captures, tmp_path, IDS[-1], steps=steps,
        refusals=(ActionObservation("print('no execution')",
                                   TurnBudget(max_turns=len(steps)).exhausted_message()),))
    result = _api().compare_capture_files(IDS, baseline, treatment)
    assert result.admissible
    assert result.cases[-1].treatment.state == "observed_failure"
    assert result.cases[-1].treatment.budget_refusals == 1


@pytest.mark.parametrize("bad", [
    "missing", "garbage", "noncanonical", "digest", "oversize", "symlink", "hardlink",
])
def test_bounded_canonical_safe_reads(captures, tmp_path, bad):
    baseline, treatment = map(dict, captures)
    path = tmp_path / (CANARIES[-1] + ".json")
    raw = treatment[IDS[0]].read_bytes()
    if bad == "garbage":
        path.write_bytes(CANARIES[0].encode())
    elif bad == "noncanonical":
        path.write_bytes(raw + b"\n")
    elif bad == "digest":
        path.write_bytes(raw.replace(b'"incremental_execution"', b'"modified_execution"'))
    elif bad == "oversize":
        with path.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
    elif bad == "symlink":
        path.symlink_to(treatment[IDS[0]])
    elif bad == "hardlink":
        original = tmp_path / "hardlink-origin.json"
        original.write_bytes(raw)
        os.link(original, path)
    treatment[IDS[0]] = path
    result = _api().compare_capture_files(IDS, baseline, treatment)
    assert result.cases[0].treatment.state == (
        "missing_capture" if bad == "missing" else "invalid_capture")
    assert result.statistics is None and not result.complete
    rendered = _api().format_comparison(result)
    assert not any(canary in rendered for canary in CANARIES)


@pytest.mark.parametrize("arm", ["baseline", "treatment"])
def test_blocked_capture_reads_are_not_invalid_content(captures, tmp_path, monkeypatch, arm):
    api = _api()
    baseline, treatment = map(dict, captures)
    blocked_path = tmp_path / (CANARIES[-1] + ".json")
    (baseline if arm == "baseline" else treatment)[IDS[0]] = blocked_path
    original = api.read_file
    message = " ".join(CANARIES)
    for error in (PermissionError(13, message, str(blocked_path)),
                  OSError(5, message, str(blocked_path))):
        attempted = []

        def read_file(path):
            if path == blocked_path:
                attempted.append(path)
                raise error
            return original(path)

        with monkeypatch.context() as patch:
            patch.setattr(api, "read_file", read_file)
            result = api.compare_capture_files(IDS, baseline, treatment)
        outcome = getattr(result.cases[0], arm)
        assert outcome.state == "capture_read_blocked"
        assert attempted == [blocked_path]
        assert outcome.score is None and outcome.scorer_status is None
        assert result.denominator == len(result.cases) == 6
        assert tuple(row.case_id for row in result.cases) == IDS
        assert not result.complete and not result.admissible
        assert result.statistics is None
        assert f"{arm}_capture_read_blocked" in result.cases[0].refusal_reasons
        rendered = api.format_comparison(result)
        assert "Paired statistics: unavailable" in rendered
        assert "Paired delta" not in rendered and "CI:" not in rendered
        assert not any(canary in rendered for canary in CANARIES)
        assert str(blocked_path) not in rendered and str(error) not in rendered

    def programmer_bug(path):
        raise RuntimeError("reader programmer bug")

    with monkeypatch.context() as patch:
        patch.setattr(api, "read_file", programmer_bug)
        with pytest.raises(RuntimeError, match="reader programmer bug"):
            api.compare_capture_files(IDS, baseline, treatment)


def test_delegates_complete_maps_to_existing_paired(captures, monkeypatch):
    api = _api()
    original = api.paired
    calls = []

    def delegate(a, b):
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(api, "paired", delegate)
    api.compare_capture_files(IDS, *captures)
    assert calls == [(dict(zip(IDS, TREATMENT)), dict(zip(IDS, BASELINE)))]
    calls.clear()
    baseline = dict(captures[0])
    baseline.pop(IDS[0])
    api.compare_capture_files(IDS, baseline, captures[1])
    assert calls == []


@pytest.mark.parametrize("incomplete", [False, True])
def test_formatter_redacts_and_declares_unavailable(captures, incomplete):
    api = _api()
    baseline, treatment = map(dict, captures)
    if incomplete:
        baseline.pop(IDS[0])
    result = api.compare_capture_files(IDS, baseline, treatment)
    rendered = api.format_comparison(result)
    assert not any(canary in rendered for canary in CANARIES)
    assert all(label + ": unavailable" in rendered for label in (
        "Billing", "Token usage", "Model-request latency", "Approved-reuse attribution"))
    assert all(word not in rendered.lower() for word in (
        "savings", "break-even", "production-ready"))
    assert "regressed-1" in rendered and "improved" in rendered
    assert not any(str(path) in rendered for mapping in captures for path in mapping.values())


def test_case_ids_escape_controls(captures):
    api = _api()
    case_id = "case\nFORGED\r\x1b[31m\u202e"
    result = api.compare_capture_files((case_id,), {case_id: captures[0][IDS[0]]},
                                      {case_id: captures[1][IDS[0]]})
    rendered = api.format_comparison(result)
    assert "\\nFORGED\\r\\u001b[31m\\u202e" in rendered
    assert "\x1b" not in rendered and "\u202e" not in rendered


def test_no_execution_network_credentials_or_writes(captures, monkeypatch):
    from bench import score
    from ptc import sql_arms, sql_isolation
    import sqlite3
    from train import grpo_ptc, sql_capture

    api = _api()
    allowed = {path for mapping in captures for path in mapping.values()}
    attempted = []
    allowed_fds = set()
    originals = (builtins.open, io.open, os.open)

    def forbidden(*args, **kwargs):
        attempted.append("forbidden")
        raise AssertionError("forbidden comparison access")

    def check_path(path):
        if type(path) is int:
            if path not in allowed_fds:
                forbidden()
            return
        if Path(path) not in allowed:
            forbidden()

    def opened(path, mode="r", *args, **kwargs):
        check_path(path)
        if any(flag in mode for flag in "wax+"):
            forbidden()
        return originals[0](path, mode, *args, **kwargs)

    def io_opened(path, mode="r", *args, **kwargs):
        check_path(path)
        if any(flag in mode for flag in "wax+"):
            forbidden()
        return originals[1](path, mode, *args, **kwargs)

    def os_opened(path, flags, *args, **kwargs):
        check_path(path)
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            forbidden()
        fd = originals[2](path, flags, *args, **kwargs)
        allowed_fds.add(fd)
        return fd

    for owner, name in (
        (sqlite3, "connect"), (sql_capture, "start_capture"),
        (sql_capture, "rescore_capture"), (score, "execution_accuracy"),
        (grpo_ptc, "sql_environment"), (sql_arms, "build_sql_arms"),
        (sql_isolation, "build_execution_binding"), (socket, "socket"),
        (socket, "getaddrinfo"), (subprocess, "Popen"), (os, "getenv"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr(builtins, "open", opened)
    monkeypatch.setattr(io, "open", io_opened)
    monkeypatch.setattr(os, "open", os_opened)
    result = api.compare_capture_files(IDS, *captures)
    assert result.admissible and result.statistics.n == 6
    assert api.format_comparison(result)
    assert attempted == []
    # Prove the guard itself can fail without leaking a credential.
    with pytest.raises(AssertionError):
        os.open("/forbidden-credential-canary", os.O_RDONLY)
    assert attempted == ["forbidden"]


@pytest.mark.parametrize("guard", ["planned_denominator", "pair_fingerprint"])
def test_independent_mutation_controls(captures, tmp_path, monkeypatch, guard):
    api = _api()
    source = Path(api.__file__).read_text()
    if guard == "planned_denominator":
        old = "planned = planned_case_ids"
        new = ("planned = tuple(case_id for case_id in planned_case_ids "
               "if case_id in baseline_paths and case_id in treatment_paths)")
        assertion = lambda module: _assert_missing(module, captures)
    else:
        old = 'if getattr(baseline, field) != getattr(treatment, field):'
        new = ('if field != "task_fingerprint" and '
               'getattr(baseline, field) != getattr(treatment, field):')
        assertion = lambda module: _assert_binding(module, captures, tmp_path)
    assert source.count(old) == 1
    assertion(api)  # independent baseline, not merely expecting an exception
    name = f"train._comparison_mutant_{guard}"
    module = types.ModuleType(name)
    module.__file__ = api.__file__
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, name, module)
        exec(compile(source.replace(old, new), api.__file__, "exec"), module.__dict__)
        with pytest.raises(AssertionError):
            assertion(module)
    assertion(api)  # original restored and green
