"""Operator command tests with scripted finals and real SQLite capture files."""
from __future__ import annotations

import builtins
import dataclasses
import importlib
import io
import os
from pathlib import Path
import socket
import sqlite3
import subprocess

import pytest


IDS = ("both-1", "both-2", "improved", "regressed-1", "regressed-2", "neither")
PLAN = (IDS[4], IDS[2], IDS[0], IDS[5], IDS[1], IDS[3])
BASELINE = (1, 1, 0, 1, 1, 0)
TREATMENT = (1, 1, 1, 0, 0, 0)
CANARIES = ("SQL_PRIVATE_901", "QUESTION_PRIVATE_902", "PATH_PRIVATE_903",
            "EXCEPTION_PRIVATE_904")


def _command():
    try:
        module = importlib.import_module("train.sql_capture_compare_cli")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_capture_compare_cli":
            raise
        pytest.fail("missing feature: capture comparison operator command", pytrace=False)
    assert callable(getattr(module, "main", None)), "missing feature: main(argv=None)"
    return module


@pytest.fixture(scope="module")
def capture_files(tmp_path_factory):
    from bench.fixture import materialize
    from bench.loader import load_bird
    from train.sql_capture import decode_capture, encode_capture, start_capture
    from train.sql_episodes import EpisodeIds

    root = tmp_path_factory.mktemp("capture-compare-cli").resolve()
    corpus = root / "corpus"
    tasks = load_bird(materialize(corpus))
    assert len(tasks) >= 6
    mappings = ({}, {})
    for arm, scores in enumerate((BASELINE, TREATMENT)):
        for index, (case_id, solved) in enumerate(zip(IDS, scores)):
            task = dataclasses.replace(
                tasks[index], question=tasks[index].question + CANARIES[1],
            )
            ids = EpisodeIds("fixture", "engineering", f"arm-{arm}",
                             case_id, "scripted-caller", "v1")
            session = start_capture(task, ids=ids, allow_execution=True)
            final = (task.gold_sql + f" /* {CANARIES[0]} */" if solved
                     else f"SELECT 'wrong {CANARIES[0]}'")
            capture = session.finish(final)
            assert capture.result.valid and capture.result.score == solved
            raw = encode_capture(capture)
            assert encode_capture(decode_capture(raw)) == raw
            path = root / f"{arm}-{index}-{CANARIES[2]}.json"
            path.write_bytes(raw)
            mappings[arm][case_id] = path
    corpus.rename(root / "retained-corpus")
    assert all(not Path(task.db_path).exists() for task in tasks)
    return mappings


def _argv(baseline, treatment, plan=PLAN):
    args = [item for case_id in plan for item in ("--case", case_id)]
    for option, mapping in (("--baseline", baseline), ("--treatment", treatment)):
        for case_id, path in reversed(tuple(mapping.items())):
            args.extend((option, case_id, str(path)))
    return args


def _spy_apis(monkeypatch, command):
    from train import sql_capture_comparison as comparison

    calls = {"compare": [], "format": []}
    originals = (comparison.compare_capture_files, comparison.format_comparison)

    def compare(planned_case_ids, baseline_paths, treatment_paths):
        args = (planned_case_ids, dict(baseline_paths), dict(treatment_paths))
        calls["compare"].append(args)
        result = originals[0](*args)
        calls["result"] = result
        return result

    def render(result):
        calls["format"].append(result)
        return originals[1](result)

    for original, replacement, name in zip(
        originals, (compare, render), ("compare_capture_files", "format_comparison")
    ):
        monkeypatch.setattr(comparison, name, replacement)
        for alias, value in tuple(vars(command).items()):
            if value is original:
                monkeypatch.setattr(command, alias, replacement)
    return calls, originals[1]


def _readonly_guard(monkeypatch, allowed):
    from bench import score
    from train import sql_capture, sql_episodes

    attempted = []
    fds = set()
    originals = (builtins.open, io.open, os.open)

    def forbidden(*args, **kwargs):
        attempted.append("forbidden")
        raise AssertionError("command attempted forbidden I/O or execution")

    def check(path):
        if isinstance(path, int):
            if path not in fds:
                forbidden()
        elif Path(path) not in allowed:
            forbidden()

    def opened(path, mode="r", *args, **kwargs):
        check(path)
        if any(flag in mode for flag in "wax+"):
            forbidden()
        return originals[0](path, mode, *args, **kwargs)

    def io_opened(path, mode="r", *args, **kwargs):
        check(path)
        if any(flag in mode for flag in "wax+"):
            forbidden()
        return originals[1](path, mode, *args, **kwargs)

    def os_opened(path, flags, *args, **kwargs):
        check(path)
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            forbidden()
        fd = originals[2](path, flags, *args, **kwargs)
        fds.add(fd)
        return fd

    for owner, name in (
        (sqlite3, "connect"), (sql_capture, "start_capture"),
        (sql_capture, "rescore_capture"), (score, "execution_accuracy"),
        (sql_episodes, "execution_accuracy"), (sql_episodes, "rescore_sql"),
        (socket, "socket"), (socket, "getaddrinfo"), (subprocess, "Popen"),
        (os, "mkdir"), (os, "rename"), (os, "replace"),
        (os, "scandir"), (os, "listdir"), (Path, "glob"), (Path, "rglob"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr(builtins, "open", opened)
    monkeypatch.setattr(io, "open", io_opened)
    monkeypatch.setattr(os, "open", os_opened)
    return attempted


def _status(command, argv):
    try:
        return command.main(argv)
    except SystemExit as exc:
        return exc.code


def _assert_refusal(output, inputs):
    assert output.out == ""
    assert len(output.err.splitlines()) == 1
    assert 0 < len(output.err.strip()) <= 160
    assert not any(value in output.err for value in (*CANARIES, *inputs))


def test_existing_capture_comparison_control(capture_files):
    from train.sql_capture_comparison import compare_capture_files, format_comparison

    result = compare_capture_files(PLAN, *capture_files)
    assert result.denominator == len(result.cases) == 6
    assert tuple(row.case_id for row in result.cases) == PLAN
    assert result.complete and result.admissible
    assert result.regressions == (IDS[4], IDS[3])
    assert result.improvements == (IDS[2],)
    stats = result.statistics
    assert stats.n == 6
    assert stats.baseline_successes == 4 and stats.treatment_successes == 3
    assert stats.baseline_accuracy == 4 / 6 and stats.treatment_accuracy == 3 / 6
    assert stats.delta == -1 / 6
    assert stats.baseline_only == 2 and stats.treatment_only == 1
    assert format_comparison(result)


def test_command_compares_real_capture_files(capture_files, monkeypatch, capsys):
    from train import sql_capture

    command = _command()
    calls, formatter = _spy_apis(monkeypatch, command)
    allowed = {path for mapping in capture_files for path in mapping.values()}
    with monkeypatch.context() as patch:
        attempted = _readonly_guard(patch, allowed)
        assert command.main(_argv(*capture_files)) == 0
        assert attempted == []
        probes = (
            lambda: sqlite3.connect(":memory:"),
            lambda: sql_capture.rescore_capture(None, None, ids=None),
            lambda: socket.socket(),
            lambda: next(iter(allowed)).open("wb"),
        )
        for probe in probes:
            with pytest.raises(AssertionError, match="command attempted forbidden"):
                probe()
        assert attempted == ["forbidden"] * 4
    output = capsys.readouterr()
    assert calls["compare"] == [(PLAN, *capture_files)]
    assert calls["format"] == [calls["result"]]
    assert output.out == formatter(calls["result"]) + "\n"
    assert output.err == ""
    assert calls["result"].statistics.baseline_successes == 4
    assert calls["result"].statistics.treatment_successes == 3
    assert calls["result"].statistics.delta == -1 / 6
    assert not any(canary in output.out for canary in CANARIES)
    assert all(str(path) not in output.out for path in allowed)


def test_command_keeps_cases_missing_both_arms(capture_files, monkeypatch, capsys):
    command = _command()
    baseline, treatment = map(dict, capture_files)
    baseline.pop(IDS[-1])
    treatment.pop(IDS[-1])
    calls, formatter = _spy_apis(monkeypatch, command)
    assert command.main(_argv(baseline, treatment)) == 0
    result = calls["result"]
    assert calls["compare"] == [(PLAN, baseline, treatment)]
    assert calls["format"] == [result]
    assert result.denominator == len(result.cases) == 6
    assert tuple(row.case_id for row in result.cases) == PLAN
    row = next(row for row in result.cases if row.case_id == IDS[-1])
    assert row.baseline.state == row.treatment.state == "missing_capture"
    assert not result.complete and not result.admissible
    assert result.statistics is None
    output = capsys.readouterr()
    assert output.out == formatter(result) + "\n" and output.err == ""


def test_command_formats_inadmissible_evidence(capture_files, monkeypatch, capsys):
    command = _command()
    baseline, treatment = map(dict, capture_files)
    baseline[IDS[1]] = baseline[IDS[0]]
    treatment[IDS[1]] = treatment[IDS[0]]
    calls, formatter = _spy_apis(monkeypatch, command)
    assert command.main(_argv(baseline, treatment)) == 0
    result = calls["result"]
    assert calls["compare"] == [(PLAN, baseline, treatment)]
    assert calls["format"] == [result]
    assert result.denominator == len(result.cases) == 6
    assert result.complete and not result.admissible
    assert "capture_reused" in result.refusal_reasons
    assert result.statistics is None
    output = capsys.readouterr()
    assert output.out == formatter(result) + "\n" and output.err == ""


@pytest.mark.parametrize("kind", [
    "duplicate_case", "duplicate_baseline", "duplicate_treatment",
    "unknown_option", "incomplete_arm",
])
def test_command_rejects_invalid_cli_arguments(monkeypatch, capsys, kind):
    command = _command()
    calls, _ = _spy_apis(monkeypatch, command)
    args = ["--case", IDS[0]]
    if kind == "duplicate_case":
        args.extend(("--case", IDS[0]))
    elif kind in ("duplicate_baseline", "duplicate_treatment"):
        option = "--baseline" if kind == "duplicate_baseline" else "--treatment"
        args.extend((option, IDS[0], "/first.json", option, IDS[0], "/second.json"))
    elif kind == "unknown_option":
        args.append("--discover")
    else:
        args.extend(("--baseline", IDS[0]))
    assert _status(command, args) == 2
    assert calls["compare"] == [] and calls["format"] == []
    output = capsys.readouterr()
    assert output.out == "" and output.err


def _invalid_comparison_args(kind, suffix):
    marker = CANARIES[2] + suffix
    if kind == "relative_path":
        return ["--case", IDS[0], "--baseline", IDS[0], marker + ".json"]
    return ["--case", IDS[0], "--baseline", marker, "/" + marker + ".json"]


@pytest.mark.parametrize("kind", ["relative_path", "undeclared_case"])
def test_command_bounds_known_argument_refusals(monkeypatch, capsys, kind):
    command = _command()
    calls, _ = _spy_apis(monkeypatch, command)
    errors = []
    for suffix in ("-first", "-second"):
        args = _invalid_comparison_args(kind, suffix)
        assert command.main(args) == 1
        output = capsys.readouterr()
        _assert_refusal(output, (args[-1],))
        errors.append(output.err)
    assert errors[0] == errors[1]
    assert len(calls["compare"]) == 2 and calls["format"] == []


def _replace_comparator(monkeypatch, command, replacement):
    from train import sql_capture_comparison as comparison

    original = comparison.compare_capture_files
    monkeypatch.setattr(comparison, "compare_capture_files", replacement)
    for alias, value in tuple(vars(command).items()):
        if value is original:
            monkeypatch.setattr(command, alias, replacement)


def test_command_does_not_echo_known_exception_detail(monkeypatch, capsys):
    command = _command()
    args = _invalid_comparison_args("relative_path", "-reference")
    assert command.main(args) == 1
    expected = capsys.readouterr()
    _assert_refusal(expected, (args[-1],))
    other_args = _invalid_comparison_args("undeclared_case", "-reference")
    assert command.main(other_args) == 1
    other = capsys.readouterr()
    _assert_refusal(other, (other_args[-1],))
    assert other.err == expected.err
    calls = []

    def refuse(*args, **kwargs):
        calls.append("comparison")
        raise ValueError(" ".join(CANARIES))

    _replace_comparator(monkeypatch, command, refuse)
    assert command.main(["--case", IDS[0]]) == 1
    output = capsys.readouterr()
    _assert_refusal(output, ())
    assert output.err == expected.err
    assert calls == ["comparison"]


def test_command_preserves_unexpected_programmer_errors(monkeypatch):
    command = _command()
    error = RuntimeError("scripted programmer error")
    calls = []

    def fail(*args, **kwargs):
        calls.append("comparison")
        raise error

    _replace_comparator(monkeypatch, command, fail)
    with pytest.raises(RuntimeError) as caught:
        command.main(["--case", IDS[0]])
    assert caught.value is error
    assert calls == ["comparison"]


def test_command_help_is_side_effect_free(monkeypatch, capsys):
    command = _command()
    calls, _ = _spy_apis(monkeypatch, command)
    with monkeypatch.context() as patch:
        attempted = _readonly_guard(patch, set())
        assert _status(command, ["--help"]) == 0
        assert attempted == []
    output = capsys.readouterr()
    assert output.err == ""
    assert all(option in output.out for option in ("--case", "--baseline", "--treatment"))
    assert calls["compare"] == [] and calls["format"] == []
