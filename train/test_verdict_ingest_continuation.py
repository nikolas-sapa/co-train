import json
import math

import pytest

from train import verdict as V


def _step(zero_std=0.4, logp_diff=1.0):
    return {"loss": 0.1, V.ZERO_STD_KEY: zero_std, V.LOGP_DIFF_KEY: logp_diff}


def _probe_rows():
    return [{"taskset_id": "synthetic-verdict-ingest"}] + [
        _step() for _ in range(5)
    ]


def _load_rows(tmp_path, rows):
    path = tmp_path / "metrics.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return V.load(str(path))


@pytest.mark.parametrize(
    "duplicate_key",
    ['"frac_reward_zero_std"', r'"\u0066rac_reward_zero_std"'],
    ids=["literal", "escaped"],
)
def test_duplicate_metric_keys_cannot_hide_probe_breach(tmp_path, duplicate_key):
    rows = _probe_rows()
    lines = [json.dumps(row) for row in rows]
    lines[1] = (
        '{"loss": 0.1, "frac_reward_zero_std": 1.0, '
        + duplicate_key + ": 0.0}"
    )
    path = tmp_path / "duplicate-metric.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert len(rows) == 6
    assert len(V.training_steps(rows)) == 5
    with pytest.raises(ValueError, match="(?i)duplicate"):
        V.load(str(path))


@pytest.mark.parametrize(
    "mode,key",
    [("probe", V.ZERO_STD_KEY), ("run", V.ZERO_STD_KEY), ("run", V.LOGP_DIFF_KEY)],
    ids=["probe-A", "run-A", "run-B"],
)
@pytest.mark.parametrize("sign", [1, -1], ids=["positive", "negative"])
def test_huge_integer_telemetry_is_unadjudicable(tmp_path, mode, key, sign):
    rows = _probe_rows() if mode == "probe" else [_step() for _ in range(10)]
    V.training_steps(rows)[2][key] = sign * 10**400
    loaded = _load_rows(tmp_path, rows)
    assert V.training_steps(loaded)[2][key] == sign * 10**400

    adjudicate = V.probe_verdict if mode == "probe" else V.run_verdict
    try:
        ok, reasons = adjudicate(loaded)
    except OverflowError as exc:
        pytest.fail(f"unusable {key} telemetry escaped as OverflowError: {exc}")

    assert ok is False
    assert any(
        key in reason and "step 2:" in reason
        and "not a finite number" in reason
        for reason in reasons
    ), reasons


@pytest.mark.parametrize("mode", ["probe", "run"])
def test_healthy_probe_and_run_unchanged(tmp_path, mode):
    rows = _probe_rows() if mode == "probe" else [_step() for _ in range(10)]
    loaded = _load_rows(tmp_path, rows)
    assert loaded == rows
    assert len(V.training_steps(loaded)) == (5 if mode == "probe" else 10)
    adjudicate = V.probe_verdict if mode == "probe" else V.run_verdict
    assert adjudicate(loaded) == (True, [])


@pytest.mark.parametrize(
    "mode,key",
    [("probe", V.ZERO_STD_KEY), ("run", V.ZERO_STD_KEY), ("run", V.LOGP_DIFF_KEY)],
    ids=["probe-A", "run-A", "run-B"],
)
def test_nan_diagnostics_remain_visible(tmp_path, mode, key):
    rows = _probe_rows() if mode == "probe" else [_step() for _ in range(10)]
    V.training_steps(rows)[2][key] = float("nan")
    loaded = _load_rows(tmp_path, rows)
    assert math.isnan(V.training_steps(loaded)[2][key])

    adjudicate = V.probe_verdict if mode == "probe" else V.run_verdict
    ok, reasons = adjudicate(loaded)
    assert ok is False
    assert any(
        key in reason and "step 2:" in reason and "nan" in reason.lower()
        and "not a finite number" in reason
        for reason in reasons
    ), reasons


def test_unique_saved_metrics_preserve_exact_fields(tmp_path):
    rows = _probe_rows()
    rows[0].update({"abort_window": 1, "metadata": {"label": "offline", "count": 5}})
    rows[1][V.COMPLETION_SAMPLES_KEY] = [
        {"chars": 8, "completion": "SELECT 1", "extracted": "SELECT 1", "reward": 1.0}
    ]
    rows[2]["extra_telemetry"] = [0, None, True, {"note": "unchanged"}]
    text = "\n".join(json.dumps(row) for row in rows)
    text = text.replace('"frac_reward_zero_std"', r'"\u0066rac_reward_zero_std"')
    path = tmp_path / "unique-metrics.jsonl"
    path.write_text("\n" + text + "\n\n", encoding="utf-8")

    loaded = V.load(str(path))
    assert loaded == rows
    assert V.header(loaded) == rows[0]
    assert V.completion_samples(loaded) == [(0, rows[1][V.COMPLETION_SAMPLES_KEY][0])]
    assert V.probe_verdict(loaded) == (True, [])


def test_thresholds_and_windows_unchanged(tmp_path):
    assert V.MIN_PROBE_STEPS == 5
    assert V.SUSTAINED_WINDOW == 10
    assert V.ZERO_STD_CEILING == 0.60
    assert V.LOGP_RATIO_MULTIPLE == 3.0

    rows = [{"taskset_id": "synthetic-verdict-ingest"}] + [
        _step(0.60) for _ in range(5)
    ]
    assert V.probe_verdict(_load_rows(tmp_path, rows)) == (True, [])
    rows[1][V.ZERO_STD_KEY] = 0.61
    assert V.probe_verdict(_load_rows(tmp_path, rows))[0] is False
    assert V.probe_verdict(_load_rows(tmp_path, _probe_rows()[:-1]))[0] is False
    assert V.probe_verdict(_load_rows(tmp_path, _probe_rows()[1:]))[0] is False

    rows = [{"taskset_id": "synthetic-verdict-ingest"}] + [
        _step(value) for value in [0.9, 0.9, 0.4, 0.9, 0.9]
    ]
    assert V.probe_verdict(_load_rows(tmp_path, rows), window=3) == (True, [])
    rows[3][V.ZERO_STD_KEY] = 0.9
    ok, reasons = V.probe_verdict(_load_rows(tmp_path, rows), window=3)
    assert ok is False
    assert any("steps 0-2 (3 consecutive)" in reason for reason in reasons), reasons

    rows = [_step(0.9) for _ in range(9)] + [_step(0.4)] + [
        _step(0.9) for _ in range(9)
    ]
    assert V.run_verdict(_load_rows(tmp_path, rows)) == (True, [])
    ok, reasons = V.run_verdict(_load_rows(tmp_path, [_step(0.9) for _ in range(10)]))
    assert ok is False
    assert any("steps 0-9" in reason and "10 consecutive" in reason for reason in reasons)
    assert V.run_verdict(_load_rows(tmp_path, [_step() for _ in range(9)]))[0] is False

    baseline = [_step() for _ in range(10)]
    assert V.run_verdict(
        _load_rows(tmp_path, baseline + [_step(logp_diff=3.0)])
    ) == (True, [])
    ok, reasons = V.run_verdict(
        _load_rows(tmp_path, baseline + [_step(logp_diff=3.01)])
    )
    assert ok is False
    assert any("above 3.0x" in reason and "first-10-step median" in reason for reason in reasons)

    rising = [_step(logp_diff=(i + 1) / 10) for i in range(10)]
    ok, reasons = V.run_verdict(_load_rows(tmp_path, rising))
    assert ok is False
    assert any("steps 0-9" in reason and "monotonically" in reason for reason in reasons)
    for baseline_value in (0.0, -1.0):
        rows = [_step(logp_diff=baseline_value) for _ in range(10)]
        assert V.run_verdict(_load_rows(tmp_path, rows)) == (True, [])
