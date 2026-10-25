"""Synthetic-only regression tests for the public frontier measurement gate.

No model, training framework, network, real manifest or scientific evidence.
The temporary amendment marker is synthetic parser input, NOT an owner signature
or scientific approval. Count-only admission remains the contract: retention
must agree with the counts, but must not acquire a separate minimum.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

from train import dead_group_probe as probe  # noqa: E402
from train import guards  # noqa: E402


@pytest.fixture
def synthetic_manifest():
    """Fresh, internally consistent synthetic data, never scientific evidence."""
    band = probe.viable_band(probe.NUM_GENERATIONS, probe.ABORT_CEILING)
    assert band is not None
    return {
        "policy": "synthetic-policy-not-scientific-evidence",
        "pre_registration_amendment": "SYNTHETIC_FRONTIER_TEST_ONLY",
        "n_tasks": 198,
        "solve_rate_min": 0.2,
        "solve_rate_max": 0.8,
        "measurement": {
            "g": probe.NUM_GENERATIONS,
            "dead_ceiling": probe.ABORT_CEILING,
            "trainable_band": list(band),
            "n_candidates": 198,
            "retention": 1.0,
        },
    }


def write_synthetic_manifest(root, manifest):
    """Write only under pytest's temporary root, including a fake parser marker."""
    path = root / guards.FRONTIER_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan deliberately exercises values Python's JSON reader accepts.
    path.write_text(json.dumps(manifest, allow_nan=True))
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "pre-registration.md").write_text(
        "# SYNTHETIC TEST FIXTURE, NOT SCIENTIFIC EVIDENCE\n"
        "### SYNTHETIC_FRONTIER_TEST_ONLY: synthetic parser fixture, signed\n"
        "The marker above is not an owner signature or scientific approval.\n"
    )


def check_measurement_refusal(root, manifest, needle):
    """Require a measurement-specific public refusal, not an unrelated closed gate."""
    write_synthetic_manifest(root, manifest)
    status = guards.frontier_taskset_status(root)
    assert status.ok is False, status
    assert any(needle in reason for reason in status.reasons), status.reasons
    assert all("measurement" in reason for reason in status.reasons), status.reasons


_MISSING = object()


@pytest.mark.parametrize(
    "block",
    [
        pytest.param(_MISSING, id="missing-block"),
        pytest.param(None, id="null-block"),
        pytest.param([], id="list-block"),
        pytest.param("synthetic-not-an-object", id="string-block"),
        pytest.param(False, id="bool-block"),
        pytest.param(0, id="numeric-block"),
    ],
)
def test_public_frontier_rejects_missing_or_malformed_measurement(
    tmp_path, synthetic_manifest, block,
):
    if block is _MISSING:
        synthetic_manifest.pop("measurement")
    else:
        synthetic_manifest["measurement"] = block
    check_measurement_refusal(tmp_path, synthetic_manifest, "measurement")


@pytest.mark.parametrize(
    "key", ["g", "dead_ceiling", "trainable_band", "n_candidates", "retention"],
)
def test_public_frontier_names_each_missing_measurement_key(
    tmp_path, synthetic_manifest, key,
):
    del synthetic_manifest["measurement"][key]
    check_measurement_refusal(tmp_path, synthetic_manifest, f"measurement is missing {key}")


@pytest.mark.parametrize(
    "key, value",
    [
        pytest.param("g", 8, id="wrong-g"),
        pytest.param("g", 4.0, id="float-g"),
        pytest.param("g", True, id="bool-g"),
        pytest.param("g", "4", id="string-g"),
        pytest.param("g", None, id="null-g"),
        pytest.param("g", float("nan"), id="nan-g"),
        pytest.param("g", float("inf"), id="infinite-g"),
        pytest.param("dead_ceiling", 0.5, id="wrong-ceiling"),
        pytest.param("dead_ceiling", True, id="bool-ceiling"),
        pytest.param("dead_ceiling", "0.6", id="string-ceiling"),
        pytest.param("dead_ceiling", None, id="null-ceiling"),
        pytest.param("dead_ceiling", float("nan"), id="nan-ceiling"),
        pytest.param("dead_ceiling", float("inf"), id="infinite-ceiling"),
        pytest.param("trainable_band", [0.2, 0.8], id="wrong-band"),
        pytest.param("trainable_band", None, id="null-band"),
        pytest.param("trainable_band", "0.12,0.88", id="string-band"),
        pytest.param("trainable_band", {}, id="object-band"),
        pytest.param("trainable_band", [], id="empty-band"),
        pytest.param("trainable_band", [0.2], id="short-band"),
        pytest.param("trainable_band", [0.2, 0.5, 0.8], id="long-band"),
        pytest.param("n_candidates", 0, id="zero-candidates"),
        pytest.param("n_candidates", -1, id="negative-candidates"),
        pytest.param("n_candidates", True, id="bool-candidates"),
        pytest.param("n_candidates", 198.0, id="float-candidates"),
        pytest.param("n_candidates", "198", id="string-candidates"),
        pytest.param("n_candidates", None, id="null-candidates"),
        pytest.param("n_candidates", float("nan"), id="nan-candidates"),
        pytest.param("n_candidates", float("inf"), id="infinite-candidates"),
        pytest.param("n_candidates", 197, id="retained-exceeds-candidates"),
        pytest.param("retention", 0.5, id="mismatched-retention"),
        pytest.param("retention", -0.1, id="negative-retention"),
        pytest.param("retention", 1.1, id="retention-above-one"),
        pytest.param("retention", True, id="bool-true-retention"),
        pytest.param("retention", False, id="bool-false-retention"),
        pytest.param("retention", "1.0", id="string-retention"),
        pytest.param("retention", None, id="null-retention"),
        pytest.param("retention", float("nan"), id="nan-retention"),
        pytest.param("retention", float("inf"), id="infinite-retention"),
        pytest.param("retention", -float("inf"), id="negative-infinite-retention"),
        pytest.param("retention", [], id="list-retention"),
    ],
)
def test_public_frontier_rejects_invalid_measurement_fields(
    tmp_path, synthetic_manifest, key, value,
):
    synthetic_manifest["measurement"][key] = value
    check_measurement_refusal(tmp_path, synthetic_manifest, f"measurement.{key}")


@pytest.mark.parametrize(
    "index, value",
    [
        pytest.param(0, "0.12", id="string-band-end"),
        pytest.param(0, None, id="null-band-end"),
        pytest.param(0, False, id="bool-band-low"),
        pytest.param(1, True, id="bool-band-high"),
        pytest.param(0, float("nan"), id="nan-band-low"),
        pytest.param(1, float("nan"), id="nan-band-high"),
        pytest.param(0, float("inf"), id="infinite-band-low"),
        pytest.param(1, -float("inf"), id="infinite-band-high"),
    ],
)
def test_public_frontier_rejects_invalid_measurement_band_endpoint(
    tmp_path, synthetic_manifest, index, value,
):
    # Keep the other endpoint exactly valid: a rounded partner would mask the
    # NaN hole in abs(declared - expected) > tolerance.
    synthetic_manifest["measurement"]["trainable_band"][index] = value
    check_measurement_refusal(tmp_path, synthetic_manifest, "measurement.trainable_band")


def test_valid_synthetic_g4_measurement_opens_public_gate(tmp_path, synthetic_manifest):
    assert probe.NUM_GENERATIONS == 4
    write_synthetic_manifest(tmp_path, synthetic_manifest)
    assert guards.frontier_taskset_status(tmp_path) == guards.Precondition(True, ())


@pytest.mark.parametrize("case", ["at-task-floor", "below-task-floor", "low-retention"])
def test_synthetic_count_only_boundary_has_no_new_retention_floor(
    tmp_path, synthetic_manifest, case,
):
    from ptc.paired import power_pairs

    minimum = power_pairs(0.25, 0.5)
    assert guards.MIN_FRONTIER_TASKS == minimum
    n_tasks = minimum - 1 if case == "below-task-floor" else minimum
    n_candidates = 198
    if case == "low-retention":
        n_tasks, n_candidates = 198, 19800
    synthetic_manifest["n_tasks"] = n_tasks
    synthetic_manifest["measurement"].update(
        n_candidates=n_candidates, retention=n_tasks / n_candidates,
    )
    write_synthetic_manifest(tmp_path, synthetic_manifest)
    status = guards.frontier_taskset_status(tmp_path)
    if case == "below-task-floor":
        assert status.ok is False
        assert len(status.reasons) == 1, status.reasons
        assert f"n_tasks {n_tasks} is below the {minimum} paired tasks" in status.reasons[0]
    else:
        assert status == guards.Precondition(True, ())


_OPTIMIZED_SYNTHETIC_CHECK = """
import json
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from train import guards

expected_source = pathlib.Path(sys.argv[1]) / "train" / "guards.py"
if sys.flags.optimize < 1 or pathlib.Path(guards.__file__).resolve() != expected_source:
    raise SystemExit("not the requested optimized worktree guard")

status = guards.frontier_taskset_status(sys.argv[2])
try:
    guards.require_frontier_taskset(sys.argv[2])
except guards.PreconditionUnmet as error:
    refused = True
    refusal = str(error)
else:
    refused = False
    refusal = ""

print(json.dumps({
    "optimized": sys.flags.optimize,
    "source": str(pathlib.Path(guards.__file__).resolve()),
    "ok": status.ok,
    "reasons": status.reasons,
    "refused": refused,
    "refusal": refusal,
}))
if status.ok or not refused or not any(sys.argv[3] in reason for reason in status.reasons):
    raise SystemExit(1)
"""


@pytest.mark.parametrize(
    "key, value",
    [
        pytest.param("g", 8, id="wrong-g"),
        pytest.param("trainable_band", float("nan"), id="nan-band"),
        pytest.param("retention", 0.5, id="mismatched-retention"),
    ],
)
def test_real_optimized_process_refuses_invalid_synthetic_measurement(
    tmp_path, synthetic_manifest, key, value,
):
    """Execute the live guard under -O; child uses explicit branches, not asserts."""
    if key == "trainable_band":
        synthetic_manifest["measurement"][key][0] = value
    else:
        synthetic_manifest["measurement"][key] = value
    write_synthetic_manifest(tmp_path, synthetic_manifest)
    result = subprocess.run(
        [
            sys.executable, "-B", "-O", "-c", _OPTIMIZED_SYNTHETIC_CHECK,
            str(guards.REPO_ROOT), str(tmp_path), f"measurement.{key}",
        ],
        cwd=guards.REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    observed = json.loads(result.stdout)
    assert observed["optimized"] >= 1
    assert observed["source"] == str(guards.REPO_ROOT / "train" / "guards.py")
    assert observed["ok"] is False
    assert observed["refused"] is True
    assert any(f"measurement.{key}" in reason for reason in observed["reasons"])
    assert f"measurement.{key}" in observed["refusal"]
