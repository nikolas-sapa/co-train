"""Portable offline mechanics acceptance, without native authorization."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_two_consecutive_fresh_demo_runs(tmp_path):
    for index in range(2):
        directory = tmp_path / f"run-{index}"
        result = subprocess.run(
            [sys.executable, "-B", "-m", "train.sql_skill_demo",
             "--work-dir", str(directory)],
            cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report == json.loads((directory / "report.json").read_text())
        assert report["mode"] == "offline-in-process-fixture-mechanics"
        assert report["qualification_dispatches"] == 4
        assert len(report["qualifications"]) == 4
        assert all(row["valid"] is True and row["score"] == 1
                   for row in report["qualifications"])
        assert report["bad_pin_dispatches"] == 0
        assert report["origin_and_qualification_paths_unavailable"] is True
        assert len(report["reuses"]) == 2
        pids = {row["pid"] for row in report["reuses"]}
        assert len(pids) == 2 and report["pid"] not in pids
        assert all(row["dispatches"] == 1 and row["result"]["valid"] is True
                   and row["result"]["score"] == 1 for row in report["reuses"])
        assert report["network_attempts"] == 0
        assert all(row["network_attempts"] == 0 for row in report["reuses"])
        assert not (directory / "qualification-assets").exists()
        assert len(list((directory / "unavailable-assets").glob("*.sqlite"))) == 5
        from train.sql_capture import decode_capture

        for reuse_index in range(2):
            capture = decode_capture((directory / f"reuse-{reuse_index}.json").read_bytes())
            assert capture.result.valid is True and capture.result.score == 1
            assert len(capture.steps) == 1


def test_demo_uses_existing_acceptance_program():
    from train.sql_skill_demo import PROGRAM
    from train.test_sql_skills import PROGRAM as accepted_program

    assert PROGRAM == accepted_program


def test_bad_pin_assertion_detects_bypassed_authority_guard(tmp_path, monkeypatch):
    from train import sql_skill_demo as demo, sql_skill_eval

    state = demo.prepare(tmp_path)
    # A real valid-pin call is substituted for the bad-pin call. Actual runtime
    # dispatch must make the demo's zero-dispatch assertion fail.
    original = sql_skill_eval.reuse_promoted

    def bypass(*args, **kwargs):
        kwargs["expected_promotion_sha256"] = state["approved_pin"]
        return original(*args, **kwargs)

    monkeypatch.setattr(sql_skill_eval, "reuse_promoted", bypass)
    with pytest.raises(AssertionError, match="bad pin dispatched"):
        demo.check_bad_pin(state)


def test_bad_pin_uses_real_guard_without_dispatch(tmp_path):
    from train import sql_skill_demo as demo

    assert demo.check_bad_pin(demo.prepare(tmp_path)) == 0


def test_existing_work_directory_is_not_overwritten(tmp_path):
    from train.sql_skill_demo import run_demo

    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        run_demo(tmp_path)
    assert sentinel.read_text() == "unchanged"


def test_network_guard_rejects_real_socket_operation():
    code = (
        "from train.sql_skill_demo import deny_network; deny_network(); "
        "import socket; socket.getaddrinfo('localhost', 80)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=ROOT,
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert "offline demo forbids socket activity" in result.stderr
