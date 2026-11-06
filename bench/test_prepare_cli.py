"""Offline CLI contracts. Execution and mutation evidence are parent-owned."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bench import fixture
from bench.loader import CorpusMissing
from bench.score import ExResult

REPO = Path(__file__).resolve().parent.parent
SUMMARY = (
    "planned=8 eligible={eligible} excluded={excluded} mode={mode} "
    "measurement=false model_calls=0\n"
)


def _cli():
    return importlib.import_module("bench.prepare_cli")


def _prep():
    return importlib.import_module("bench.prepare")


def _freeze_args(root, draw, mode="--fixture"):
    return [
        "freeze", "--root", str(root), "--output", str(draw), "--seed", "17",
        "--simple", "2", "--moderate", "3", "--challenging", "3", mode,
    ]


def _validate_args(root, draw, supplement, draw_sha):
    return [
        "validate", "--root", str(root), "--draw", str(draw),
        "--output", str(supplement), "--expected-draw-sha256", draw_sha,
    ]


def _check_args(root, draw, supplement, draw_sha, supplement_sha,
                mode="--fixture"):
    return [
        "check", "--root", str(root), "--draw", str(draw),
        "--supplement", str(supplement), "--expected-draw-sha256", draw_sha,
        "--expected-supplement-sha256", supplement_sha, mode,
    ]


def _digest_call(args, output, capsys):
    assert _cli().main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    digest = captured.out.removesuffix("\n")
    assert len(digest) == 64
    assert captured.out == digest + "\n"
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    return digest


def _pair(tmp_path, capsys, *, invalid=False, mode="--fixture"):
    root = fixture.materialize(tmp_path / "corpus")
    if invalid:
        records = fixture.records()
        records[0]["SQL"] = "SELECT * FROM absent_cli_gold_table"
        (root / "dev.json").write_text(json.dumps(records))
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    draw_sha = _digest_call(_freeze_args(root, draw, mode), draw, capsys)
    supplement_sha = _digest_call(
        _validate_args(root, draw, supplement, draw_sha), supplement, capsys)
    return root, draw, supplement, draw_sha, supplement_sha


def _forbid(monkeypatch, target, name, calls):
    # Fault boundary: forbidden work must fail loudly, never fake success.
    def forbidden(*args, **kwargs):
        calls.append(name)
        raise AssertionError(f"forbidden boundary: {name}")

    monkeypatch.setattr(target, name, forbidden)


@pytest.mark.parametrize("invalid,eligible,excluded", [(False, 8, 0), (True, 7, 1)])
@pytest.mark.parametrize("mode", ["--fixture", "--production"])
def test_real_fixture_round_trip(tmp_path, capsys, invalid, eligible, excluded, mode):
    root, draw, supplement, draw_sha, supplement_sha = _pair(
        tmp_path, capsys, invalid=invalid, mode=mode)
    admitted = _prep().load_validated_draw(
        root, draw, supplement, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supplement_sha, fixture=mode == "--fixture")
    assert (len(admitted.planned), len(admitted.eligible),
            len(admitted.exclusions)) == (8, eligible, excluded)
    if invalid:
        assert admitted.exclusions[0].status == "gold_error"
    assert _cli().main(_check_args(
        root, draw, supplement, draw_sha, supplement_sha, mode)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == SUMMARY.format(
        eligible=eligible, excluded=excluded, mode=mode[2:])


def test_check_is_read_only(tmp_path, capsys, monkeypatch):
    pair = _pair(tmp_path, capsys)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    prep, calls = _prep(), []
    for name in ("select", "validate_golds", "_publish"):
        _forbid(monkeypatch, prep, name, calls)
    _forbid(monkeypatch, sqlite3, "connect", calls)
    for _ in range(2):
        assert _cli().main(_check_args(*pair)) == 0
        captured = capsys.readouterr()
        assert captured.out == SUMMARY.format(eligible=8, excluded=0, mode="fixture")
        assert captured.err == ""
    assert calls == []
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("command,digest", [
    ("validate", "draw"), ("check", "draw"), ("check", "supplement"),
])
def test_wrong_digest_before_corpus_sql_publication(
        tmp_path, capsys, monkeypatch, command, digest):
    root, draw, supplement, draw_sha, supplement_sha = _pair(tmp_path, capsys)
    wrong = "f" * 64 if draw_sha != "f" * 64 else "e" * 64
    if digest == "supplement" and wrong == supplement_sha:
        wrong = "d" * 64
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    prep, calls = _prep(), []
    for name in ("load_bird", "_corpus", "_publish"):
        _forbid(monkeypatch, prep, name, calls)
    _forbid(monkeypatch, sqlite3, "connect", calls)
    if command == "validate":
        output = tmp_path / "must-not-exist.json"
        args = _validate_args(root, draw, output, wrong)
    else:
        args = _check_args(
            root, draw, supplement,
            wrong if digest == "draw" else draw_sha,
            wrong if digest == "supplement" else supplement_sha)
    assert _cli().main(args) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert 0 < len(captured.err) <= 256
    assert calls == []
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("command", ["freeze", "validate"])
def test_existing_destination_preserved(tmp_path, capsys, command):
    root, draw, supplement, draw_sha, _ = _pair(tmp_path, capsys)
    output = draw if command == "freeze" else supplement
    before = output.read_bytes()
    args = (_freeze_args(root, output) if command == "freeze"
            else _validate_args(root, draw, output, draw_sha))
    assert _cli().main(args) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err
    assert output.read_bytes() == before


@pytest.mark.parametrize("command", ["freeze", "validate"])
def test_post_link_fault_is_indeterminate_without_retry_or_final_delete(
        tmp_path, capsys, monkeypatch, command):
    root, draw, _, draw_sha, _ = _pair(tmp_path, capsys)
    output = tmp_path / "indeterminate.json"
    prep, publications, deletions = _prep(), [], []
    real_publish, real_unlink = prep._publish, os.unlink

    def publish(*args, **kwargs):
        publications.append(args[1])
        return real_publish(*args, **kwargs)

    def unlink(path, *args, **kwargs):
        deletions.append(Path(path))
        return real_unlink(path, *args, **kwargs)

    def sync_fault(*args):
        # Infrastructure fault after exclusive hard-link commit point.
        raise OSError("PRIVATE_PATH_AND_SQL_SENTINEL")

    monkeypatch.setattr(prep, "_publish", publish)
    monkeypatch.setattr(prep, "_sync_dir", sync_fault)
    monkeypatch.setattr(os, "unlink", unlink)
    args = (_freeze_args(root, output) if command == "freeze"
            else _validate_args(root, draw, output, draw_sha))
    assert _cli().main(args) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "indeterminate" in captured.err.lower()
    assert "do not auto-retry" in captured.err.lower()
    assert "PRIVATE_PATH_AND_SQL_SENTINEL" not in captured.err
    assert len(captured.err) <= 256
    assert publications == [str(output)]
    assert output not in deletions
    assert json.loads(output.read_bytes())["stage"] == (
        "draw" if command == "freeze" else "gold-validation")


@pytest.mark.parametrize("change", [
    "no-command", "no-root", "no-output", "no-seed", "no-simple",
    "no-moderate", "no-challenging", "no-mode", "both-modes",
    "zero-count", "negative-count", "fraction-count", "noninteger-count",
    "bad-seed", "bad-mode",
    "validate-no-digest", "validate-no-draw", "validate-no-output", "validate-no-root",
    "check-no-draw-digest", "check-no-supplement-digest",
    "check-no-supplement", "check-no-root", "check-no-draw",
    "check-no-mode", "check-both-modes",
])
def test_bad_arguments_before_work(tmp_path, capsys, monkeypatch, change):
    root, draw, supplement = tmp_path / "root", tmp_path / "draw", tmp_path / "supp"
    args = _freeze_args(root, draw)
    if change.startswith("validate-"):
        args = _validate_args(root, draw, supplement, "a" * 64)
        option = {"digest": "--expected-draw-sha256",
                  "draw": "--draw", "output": "--output",
                  "root": "--root"}[change[12:]]
        index = args.index(option)
        del args[index:index + 2]
    elif change.startswith("check-"):
        args = _check_args(root, draw, supplement, "a" * 64, "b" * 64)
        option = {
            "check-no-draw-digest": "--expected-draw-sha256",
            "check-no-supplement-digest": "--expected-supplement-sha256",
            "check-no-supplement": "--supplement",
            "check-no-root": "--root",
            "check-no-draw": "--draw",
        }.get(change)
        if option:
            index = args.index(option)
            del args[index:index + 2]
        elif change == "check-no-mode":
            args.remove("--fixture")
        else:
            args.append("--production")
    elif change == "no-command":
        args = []
    elif change == "no-mode":
        args.remove("--fixture")
    elif change == "both-modes":
        args.append("--production")
    elif change == "bad-mode":
        args[-1] = "--PRIVATE_PAYLOAD"
    elif change == "bad-seed":
        args[args.index("--seed") + 1] = "PRIVATE_PAYLOAD"
    elif change.endswith("-count"):
        args[args.index("--simple") + 1] = {
            "zero-count": "0", "negative-count": "-1",
            "fraction-count": "1.5", "noninteger-count": "PRIVATE_PAYLOAD",
        }[change]
    else:
        index = args.index("--" + change[3:])
        del args[index:index + 2]
    calls, prep = [], _prep()
    for name in ("freeze_draw", "validate_draw", "load_validated_draw"):
        _forbid(monkeypatch, prep, name, calls)
    assert _cli().main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert 0 < len(captured.err) <= 256
    assert "PRIVATE_PAYLOAD" not in captured.err
    assert calls == []


def test_fixture_bounds_and_production_policy(tmp_path, capsys, monkeypatch):
    root = fixture.materialize(tmp_path / "corpus")
    draw = tmp_path / "fixture-draw.json"
    args = _freeze_args(root, draw) + ["--timeout-s", "1", "--max-rows", "2"]
    _digest_call(args, draw, capsys)
    settings = json.loads(draw.read_bytes())["settings"]
    assert settings["timeout_s"] == 1.0
    assert settings["max_rows"] == 2
    calls, prep = [], _prep()
    _forbid(monkeypatch, prep, "_corpus", calls)
    _forbid(monkeypatch, sqlite3, "connect", calls)
    output = tmp_path / "production-draw.json"
    args = _freeze_args(root, output, "--production") + [
        "--timeout-s", "1", "--max-rows", "2"]
    assert _cli().main(args) != 0
    assert capsys.readouterr().out == ""
    assert calls == []
    assert not output.exists()


def test_check_binds_explicit_mode(tmp_path, capsys):
    pair = _pair(tmp_path, capsys)
    assert _cli().main(_check_args(*pair, mode="--production")) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err


@pytest.mark.parametrize("diagnostic", ["underfilled", "zero-eligible"])
def test_diagnostic_artifacts_are_not_admitted(tmp_path, capsys, diagnostic):
    root = fixture.materialize(tmp_path / "corpus")
    if diagnostic == "zero-eligible":
        records = fixture.records()
        for record in records:
            record["SQL"] = "SELECT * FROM absent_cli_gold_table"
        (root / "dev.json").write_text(json.dumps(records))
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    args = _freeze_args(root, draw)
    if diagnostic == "underfilled":
        args[args.index("--simple") + 1] = "3"
    draw_sha = _digest_call(args, draw, capsys)
    args = _validate_args(root, draw, supplement, draw_sha)
    if diagnostic == "underfilled":
        assert _cli().main(args) != 0
        assert capsys.readouterr().out == ""
        assert not supplement.exists()
        supplement_sha = "a" * 64
    else:
        supplement_sha = _digest_call(args, supplement, capsys)
        assert json.loads(supplement.read_bytes())["usable"] is False
    assert _cli().main(_check_args(
        root, draw, supplement, draw_sha, supplement_sha)) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err


def test_missing_corpus_has_generic_bounded_error(tmp_path, capsys):
    output = tmp_path / "draw.json"
    assert _cli().main(_freeze_args(
        tmp_path / "PRIVATE_PATH_SENTINEL", output)) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert 0 < len(captured.err) <= 256
    assert "PRIVATE_PATH_SENTINEL" not in captured.err
    assert not output.exists()


def test_blocked_supplement_is_not_admitted(tmp_path, capsys, monkeypatch):
    root = fixture.materialize(tmp_path / "corpus")
    draw, supplement = tmp_path / "draw.json", tmp_path / "supplement.json"
    draw_sha = _digest_call(_freeze_args(root, draw), draw, capsys)
    prep = _prep()
    real_validate = prep.validate_golds

    def database_fault(tasks, **kwargs):
        # Explicit database-availability fault; all gold SQL still executes.
        broken = real_validate(tasks, **kwargs)
        assert broken == []
        return [(tasks[0], ExResult(0.0, "db_missing", False, "injected fault"))]

    with monkeypatch.context() as fault:
        fault.setattr(prep, "validate_golds", database_fault)
        supplement_sha = _digest_call(
            _validate_args(root, draw, supplement, draw_sha), supplement, capsys)
    document = json.loads(supplement.read_bytes())
    assert document["status"] == "blocked"
    assert document["usable"] is False
    assert len(document["eligible_ids"]) == 7
    assert _cli().main(_check_args(
        root, draw, supplement, draw_sha, supplement_sha)) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err


@pytest.mark.parametrize("error_type", ["PreparationError", "CorpusMissing", "OSError"])
def test_known_faults_do_not_disclose_payload(tmp_path, capsys, monkeypatch, error_type):
    prep = _prep()
    error = {"PreparationError": prep.PreparationError,
             "CorpusMissing": CorpusMissing, "OSError": OSError}[error_type]

    def fault(*args, **kwargs):
        # Explicit infrastructure/preparation fault, not a mocked happy path.
        raise error("/PRIVATE_PATH SELECT PRIVATE_SQL PRIVATE_PAYLOAD")

    monkeypatch.setattr(prep, "freeze_draw", fault)
    assert _cli().main(_freeze_args(tmp_path / "root", tmp_path / "draw")) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert 0 < len(captured.err) <= 256
    assert "PRIVATE" not in captured.err
    assert "Traceback" not in captured.err


def _assert_digest_refusal(args, capsys):
    result = _cli().main(args)
    capsys.readouterr()
    assert result != 0, "wrong retained digest must refuse"


def test_guard_loss_canary_hits_intended_assertion(tmp_path, capsys, monkeypatch):
    root, draw, supplement, draw_sha, supplement_sha = _pair(tmp_path, capsys)
    wrong = "a" * 64 if draw_sha != "a" * 64 else "b" * 64
    args = _check_args(root, draw, supplement, wrong, supplement_sha)
    _assert_digest_refusal(args, capsys)
    prep = _prep()
    real_consumer = prep.load_validated_draw

    def lose_digest_guard(*args, **kwargs):
        # Intentional guard-loss mutation at CLI/consumer boundary.
        kwargs["expected_draw_sha256"] = draw_sha
        return real_consumer(*args, **kwargs)

    with monkeypatch.context() as mutation:
        mutation.setattr(prep, "load_validated_draw", lose_digest_guard)
        with pytest.raises(AssertionError, match="wrong retained digest must refuse"):
            _assert_digest_refusal(args, capsys)
    _assert_digest_refusal(args, capsys)


def test_isolated_import_and_real_flow_forbid_network_and_repo_writes(tmp_path):
    script = r'''
import hashlib
import importlib
import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

repo, temporary = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo))
forbidden = {"torch", "trl", "train", "transformers", "verifiers",
             "anthropic", "openai", "requests", "httpx"}
events = []

def audit(event, args):
    if event == "import" and args[0].split(".")[0] in forbidden:
        events.append(event)
        raise AssertionError("forbidden optional import")
    if event.startswith("socket.") or event.startswith("http.client."):
        events.append(event)
        raise AssertionError("network forbidden")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1], args[2]
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+"))
        writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT |
                                          os.O_TRUNC | os.O_APPEND))
        if writing and (path == repo or repo in path.parents):
            events.append(event)
            raise AssertionError("repository/protected manifest write")
    if event in {"os.link", "os.rename", "os.remove", "os.rmdir", "os.mkdir"}:
        paths = args[:2] if event in {"os.link", "os.rename"} else args[:1]
        for value in paths:
            if isinstance(value, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(value)).resolve()
                if path == repo or repo in path.parents:
                    events.append(event)
                    raise AssertionError("repository mutation")

sys.addaudithook(audit)
cli = importlib.import_module("bench.prepare_cli")
fixture = importlib.import_module("bench.fixture")
root = fixture.materialize(temporary / "corpus")
draw, supplement = temporary / "draw.json", temporary / "supplement.json"

def invoke(args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = cli.main(args)
    assert result == 0
    assert stderr.getvalue() == ""
    return stdout.getvalue()

draw_sha = invoke(["freeze", "--root", str(root), "--output", str(draw),
                   "--seed", "17", "--simple", "2", "--moderate", "3",
                   "--challenging", "3", "--fixture"]).strip()
assert draw_sha == hashlib.sha256(draw.read_bytes()).hexdigest()
supplement_sha = invoke(["validate", "--root", str(root), "--draw", str(draw),
                        "--output", str(supplement),
                        "--expected-draw-sha256", draw_sha]).strip()
assert supplement_sha == hashlib.sha256(supplement.read_bytes()).hexdigest()
summary = invoke(["check", "--root", str(root), "--draw", str(draw),
                  "--supplement", str(supplement),
                  "--expected-draw-sha256", draw_sha,
                  "--expected-supplement-sha256", supplement_sha, "--fixture"])
assert summary == ("planned=8 eligible=8 excluded=0 mode=fixture "
                   "measurement=false model_calls=0\n")
assert events == []
assert not forbidden.intersection(sys.modules)
'''
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(REPO), str(tmp_path)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
