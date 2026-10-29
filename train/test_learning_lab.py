"""Real fixture scores cross the evidence/calibration boundary without generation.

G=4 here is a synthetic diagnostic, not a training-G or independence claim.
Fingerprints and policy labels are explicit fixture declarations.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import shlex
from pathlib import Path

import pytest

from bench.fixture import materialize
from bench.loader import load_bird


def _apis():
    try:
        episodes = importlib.import_module("train.sql_episodes")
        calibration = importlib.import_module("bench.frontier.calibration")
    except ModuleNotFoundError as exc:
        if exc.name not in {"train.sql_episodes", "bench.frontier.calibration"}:
            raise
        pytest.fail(f"learning-lab implementation absent: {exc.name}", pytrace=False)
    return episodes, calibration


@pytest.fixture
def tasks(tmp_path):
    return load_bird(materialize(tmp_path / "fixture"))


def _samples(episodes, calibration, task, arm, scores, *, phase="screen", actions=True):
    fields = dataclasses.asdict(task)
    fields.pop("db_path")
    fingerprint = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    scorer = hashlib.sha256(
        (Path(__file__).resolve().parents[1] / "bench/score.py").read_bytes()
    ).hexdigest()
    group = f"{task.name}:{arm}:{phase}"
    action = (f"print(execute_sql(query={task.gold_sql!r}))" if arm == "ptc"
              else "execute_sql " + shlex.quote(task.gold_sql))
    result = []
    for index, want_correct in enumerate(scores):
        sample_id = f"{group}:{index}"
        ids = episodes.EpisodeIds(
            corpus_id="committed-sql-fixture", split_id="diagnostic-only",
            run_id="learning-lab-test", episode_id=sample_id,
            policy_id="scripted-fixture", policy_revision="fixture-v1",
        )
        episode = episodes.record_scripted(
            task, arm=arm, actions=(action,) if actions else (),
            final_answer=task.gold_sql if want_correct else "SELECT 'wrong-fixture-answer'",
            ids=ids,
        )
        loaded = episodes.decode_episode(episodes.encode_episode(episode))
        score = episodes.rescore_sql(loaded, task, ids=ids)
        result.append(calibration.SampleEvidence(
            sample_id=sample_id, group_id=group, task_id=task.name,
            task_fingerprint=fingerprint, arm=arm, phase=phase,
            corpus_id=ids.corpus_id, split_id=ids.split_id, run_id=ids.run_id,
            policy_revision=ids.policy_revision, scorer_id=scorer,
            score=score.score, status=score.status, valid=score.valid,
        ))
    return result


def test_all_fixture_task_arm_scores_cross_into_taskwise_groups(tasks, monkeypatch):
    episodes, calibration = _apis()
    from ptc.sql_arms import ArmPair

    dispatched = []
    original = ArmPair.run

    def tracked(self, arm, action, *args, **kwargs):
        dispatched.append((arm, action))
        return original(self, arm, action, *args, **kwargs)

    monkeypatch.setattr(ArmPair, "run", tracked)
    assert len(tasks) == 8
    samples = []
    for task in tasks:
        for arm in ("ptc", "bash"):
            samples.extend(_samples(episodes, calibration, task, arm, (0, 0, 1, 1)))
    summary = calibration.summarize_groups(
        samples, group_g=4, evaluation_task_ids={"held-out-not-a-fixture"}
    )
    assert len(dispatched) == len(samples) == 64  # rescoring dispatched nothing
    assert summary["all_group_count"] == summary["usable_group_count"] == 16
    assert summary["invalid_group_count"] == 0
    assert summary["valid_successes"] == 32
    assert summary["status_counts"] == {"match": 32, "mismatch": 32}
    assert len(summary["strata"]) == 16
    for stratum in summary["strata"]:
        assert stratum["empirical_dead_group_fraction"] == 0
        assert stratum["plugin_dead_estimate"] == .125


def test_actual_invalid_gold_scores_stay_visible_not_valid_zeroes(tasks):
    episodes, calibration = _apis()
    task = dataclasses.replace(tasks[0], gold_sql="SELECT FROM broken_gold")
    samples = _samples(episodes, calibration, task, "ptc", (1, 1, 1, 1), actions=False)
    assert all(not sample.valid and sample.status == "gold_error" for sample in samples)
    summary = calibration.summarize_groups(samples, group_g=4, evaluation_task_ids=())
    assert summary["invalid_group_count"] == 1
    assert summary["usable_group_count"] == summary["valid_successes"] == 0
    assert summary["invalid_sample_count"] == 4
    assert summary["status_counts"] == {"gold_error": 4}
    assert summary["groups"][0]["dead"] is None
    assert summary["strata"][0]["empirical_dead_group_fraction"] is None


def test_actual_episode_ids_cannot_be_reused_as_confirmation_evidence(tasks):
    episodes, calibration = _apis()
    samples = _samples(episodes, calibration, tasks[0], "ptc", (0, 0, 1, 1), actions=False)
    reused = [dataclasses.replace(s, group_id="confirmation", phase="confirmation")
              for s in samples]
    with pytest.raises((TypeError, ValueError)):
        calibration.summarize_groups(samples + reused, group_g=4, evaluation_task_ids=())


def test_actual_task_strata_do_not_become_one_pooled_marginal(tasks):
    episodes, calibration = _apis()
    samples = _samples(episodes, calibration, tasks[0], "ptc", (0, 0, 0, 0), actions=False)
    samples += _samples(episodes, calibration, tasks[1], "ptc", (1, 1, 1, 1), actions=False)
    summary = calibration.summarize_groups(samples, group_g=4, evaluation_task_ids=())
    assert summary["valid_successes"] == 4
    assert len(summary["strata"]) == 2
    assert {s["plugin_dead_estimate"] for s in summary["strata"]} == {1}
    assert {s["empirical_dead_group_fraction"] for s in summary["strata"]} == {1}
