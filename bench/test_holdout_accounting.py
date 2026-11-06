"""Source-only authored cases; execution belongs to the parent."""

import builtins
import sqlite3
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from bench import prepare
from bench.holdout_accounting import (
    HoldoutAccountingError,
    account_holdout_membership,
)
from bench.task import SqlTask


def _task(name):
    return SqlTask(
        name=name,
        question="Which declared row?",
        evidence="",
        gold_sql="SELECT value FROM declared_rows",
        db_id="declared-db",
        db_path="/unopened/declared-db.sqlite",
        tier="simple",
        tier_source="annotated",
        shape="select",
        coarse_shape="select",
        source="fixture",
    )


def _memberships():
    return (
        tuple(_task(f"training-{index}") for index in range(8)),
        tuple(_task(f"holdout-{index}") for index in range(7)),
    )


def _assert_overlap_refused(result):
    assert not result.identities_disjoint, "identity overlap must refuse disjointness"


def test_eight_training_seven_holdout_disjoint():
    training, holdout = _memberships()
    result = account_holdout_membership(training, holdout)
    assert (result.training_count, result.holdout_count) == (8, 7)
    assert (result.id_overlap_count, result.fingerprint_overlap_count) == (0, 0)
    assert result.shared_id_task_sha256 == ()
    assert result.shared_task_sha256 == ()
    assert result.identities_disjoint


def test_shared_id_changed_content_refuses():
    training, holdout = _memberships()
    changed = replace(training[0], question="Different declared question?")
    result = account_holdout_membership(training, (changed,) + holdout[1:])
    assert (result.training_count, result.holdout_count) == (8, 7)
    assert (result.id_overlap_count, result.fingerprint_overlap_count) == (1, 0)
    assert result.shared_id_task_sha256 == (prepare._task_sha256(training[0]),)
    assert result.shared_task_sha256 == ()
    _assert_overlap_refused(result)


def test_shared_canonical_identity_refuses():
    training, holdout = _memberships()
    result = account_holdout_membership(training, (replace(training[0]),) + holdout[1:])
    digest = prepare._task_sha256(training[0])
    assert (result.id_overlap_count, result.fingerprint_overlap_count) == (1, 1)
    assert result.shared_id_task_sha256 == (digest,)
    assert result.shared_task_sha256 == (digest,)
    _assert_overlap_refused(result)


def test_db_path_only_change_preserves_identity():
    task = _task("same-id")
    moved = replace(task, db_path="/another/unopened/location.sqlite")
    assert task.db_path != moved.db_path
    assert prepare._task_sha256(task) == prepare._task_sha256(moved)
    result = account_holdout_membership((task,), (moved,))
    assert (result.id_overlap_count, result.fingerprint_overlap_count) == (1, 1)
    _assert_overlap_refused(result)


def test_real_helper_used_once_per_member(monkeypatch):
    training, holdout = _memberships()
    holdout = (training[0],) + holdout[1:]
    real = prepare._task_sha256
    expected = real(training[0])
    calls = []

    def recording(task):
        calls.append(task)
        return real(task)

    monkeypatch.setattr(prepare, "_task_sha256", recording)
    result = account_holdout_membership(training, holdout)
    assert len(calls) == 15
    assert all(actual is original for actual, original in zip(calls, training + holdout))
    assert result.shared_id_task_sha256 == (expected,)
    assert result.shared_task_sha256 == (expected,)


@pytest.mark.parametrize("side", ["training", "holdout"])
@pytest.mark.parametrize("changed", [False, True])
def test_duplicate_ids_refuse(side, changed):
    training, holdout = _memberships()
    member = training[0] if side == "training" else holdout[0]
    duplicate = replace(member, question="Changed?" if changed else member.question)
    if side == "training":
        training += (duplicate,)
    else:
        holdout += (duplicate,)
    with pytest.raises(HoldoutAccountingError, match="^duplicate task identity$"):
        account_holdout_membership(training, holdout)


@pytest.mark.parametrize("side", ["training", "holdout", "both"])
def test_empty_membership_refuses(side):
    training, holdout = _memberships()
    if side in ("training", "both"):
        training = ()
    if side in ("holdout", "both"):
        holdout = ()
    with pytest.raises(HoldoutAccountingError, match="^membership must be a nonempty tuple$"):
        account_holdout_membership(training, holdout)


@pytest.mark.parametrize("side", ["training", "holdout"])
@pytest.mark.parametrize("bad", [[], None, "PRIVATE_MEMBERSHIP"])
def test_non_tuple_membership_refuses(side, bad):
    training, holdout = _memberships()
    if side == "training":
        training = bad
    else:
        holdout = bad
    with pytest.raises(HoldoutAccountingError, match="^membership must be a nonempty tuple$"):
        account_holdout_membership(training, holdout)


@pytest.mark.parametrize(
    "field,value",
    [(field.name, None) for field in fields(SqlTask)]
    + [(field.name, " ") for field in fields(SqlTask) if field.name != "evidence"]
    + [
        ("tier", "PRIVATE_TIER"),
        ("tier_source", "PRIVATE_TIER_SOURCE"),
        ("source", "PRIVATE_SOURCE"),
        ("question", "\ud800PRIVATE_CONTENT"),
        ("name", ["PRIVATE_NAME"]),
    ],
)
@pytest.mark.parametrize("side", ["training", "holdout"])
def test_malformed_tasks_refuse(field, value, side):
    malformed = _task("PRIVATE_TASK")
    # Deliberately corrupt a real frozen record, including constructor-checked fields.
    object.__setattr__(malformed, field, value)
    member = (malformed,)
    good = (_task("good"),)
    training, holdout = (member, good) if side == "training" else (good, member)
    with pytest.raises(HoldoutAccountingError, match="^invalid task membership$") as caught:
        account_holdout_membership(training, holdout)
    assert len(str(caught.value)) < 80
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_non_task_and_missing_field_refuse():
    malformed = _task("PRIVATE_TASK")
    object.__delattr__(malformed, "question")
    for bad in (None, "PRIVATE_TASK", malformed):
        with pytest.raises(HoldoutAccountingError, match="^invalid task membership$"):
            account_holdout_membership((bad,), (_task("good"),))


def test_diagnostics_bounded_without_truncating_counts():
    tasks = tuple(_task(f"PRIVATE_NAME_{index}") for index in range(13))
    result = account_holdout_membership(tasks, tuple(reversed(tasks)))
    assert (result.training_count, result.holdout_count) == (13, 13)
    assert (result.id_overlap_count, result.fingerprint_overlap_count) == (13, 13)
    expected = tuple(sorted(prepare._task_sha256(task) for task in tasks))[:10]
    assert result.shared_id_task_sha256 == expected
    assert result.shared_task_sha256 == expected
    assert len(result.shared_task_sha256) == 10
    assert "PRIVATE" not in repr(result)
    for task in tasks:
        for value in (task.name, task.question, task.gold_sql, task.db_path):
            assert value not in repr(result)
    _assert_overlap_refused(result)


def test_caller_data_untouched_and_result_frozen():
    training, holdout = _memberships()
    originals = training + holdout
    snapshots = tuple(tuple(getattr(task, field.name) for field in fields(SqlTask))
                      for task in originals)
    training_before, holdout_before = training, holdout
    result = account_holdout_membership(training, holdout)
    assert training is training_before
    assert holdout is holdout_before
    assert all(actual is original
               for actual, original in zip(training + holdout, originals))
    assert snapshots == tuple(
        tuple(getattr(task, field.name) for field in fields(SqlTask))
        for task in training + holdout
    )
    with pytest.raises(FrozenInstanceError):
        result.training_count = 0
    with pytest.raises(FrozenInstanceError):
        result.shared_task_sha256 = ("forged",)


def test_no_operational_io_or_execution(monkeypatch):
    training, holdout = _memberships()
    calls = []
    real_import = builtins.__import__

    def forbidden(*args, **kwargs):
        calls.append("forbidden")
        raise AssertionError("accounting reached an operational surface")

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in ("torch", "transformers", "trl", "unsloth", "vllm"):
            return forbidden()
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as guard:
        for name in (
            "select", "validate_golds", "load_bird", "freeze_draw", "validate_draw",
            "load_validated_draw", "_corpus", "_check_candidates", "_hash_file",
        ):
            guard.setattr(prepare, name, forbidden)
        guard.setattr(sqlite3, "connect", forbidden)
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(builtins, "__import__", guarded_import)
        for name in ("open", "read_bytes", "read_text", "resolve", "stat"):
            guard.setattr(Path, name, forbidden)
        result = account_holdout_membership(training, holdout)
    assert calls == []
    assert (result.training_count, result.holdout_count) == (8, 7)
    assert result.identities_disjoint


def test_renamed_content_is_not_semantic_clearance():
    task = _task("original-id")
    renamed = replace(task, name="renamed-id")
    assert prepare._task_sha256(task) != prepare._task_sha256(renamed)
    result = account_holdout_membership((task,), (renamed,))
    assert (result.id_overlap_count, result.fingerprint_overlap_count) == (0, 0)
    assert result.identities_disjoint


def test_wrong_guard_canary_reaches_disjointness_assertion():
    task = _task("same-id")
    changed = replace(task, question="Different declared content?")
    real = account_holdout_membership((task,), (changed,))
    assert (real.id_overlap_count, real.fingerprint_overlap_count) == (1, 0)
    _assert_overlap_refused(real)
    # Wrong fingerprint-only guard erases the independent name-overlap refusal.
    bypassed = replace(real, id_overlap_count=0)
    assert bypassed.identities_disjoint
    with pytest.raises(AssertionError) as caught:
        _assert_overlap_refused(bypassed)
    assert str(caught.value).partition("\n")[0] == "identity overlap must refuse disjointness"
