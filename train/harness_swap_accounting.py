"""In-memory accounting of caller-declared, scripted harness-swap inputs.

This projection neither authenticates declarations nor qualifies a backend.
SqlEpisode lacks explicit Budget.max_turns/max_retries/retry_on/rollout_timeout
bindings. Matching its recorded subset cannot establish full swap comparability,
measurement, runtime behavior, checkpoint identity or scientific acceptance.
An ID-only plan cannot detect a shared substituted fingerprint on both sides.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from train import sql_episodes
from train.sql_episodes import SqlEpisode


_INVARIANTS = (
    "corpus_id", "split_id", "policy_id", "policy_revision", "schema_version",
    "origin", "arm", "task_fingerprint", "db_sha256", "schema", "prompt",
    "instrument", "reporting",
)


@dataclass(frozen=True)
class HarnessSwapProjection:
    """Complete membership counts and fixed-size recorded-field diagnostics.

    Duplicate counts count occurrences beyond the first, including unexpected
    IDs. Unexpected/missing/overlap counts count unique IDs. Overlap includes
    unexpected IDs; paired_count includes only scheduled, unambiguous pairs.
    invariant_mismatch_count counts differing fields, not differing episodes.
    No task identifiers, payloads or backend labels are retained in the result.
    """

    planned_count: int
    planned_unique_count: int
    planned_duplicate_count: int
    left_count: int
    right_count: int
    left_duplicate_count: int
    right_duplicate_count: int
    left_unexpected_count: int
    right_unexpected_count: int
    left_missing_count: int
    right_missing_count: int
    missing_both_count: int
    overlap_count: int
    paired_count: int
    left_backend_count: int
    right_backend_count: int
    same_backend_pair_count: int
    distinct_backend_pair_count: int
    field_mismatch_counts: tuple[tuple[str, int], ...]

    @property
    def invariant_mismatch_count(self) -> int:
        return sum(count for _, count in self.field_mismatch_counts)

    @property
    def coverage_complete(self) -> bool:
        return (
            self.planned_count > 0
            and self.planned_duplicate_count == 0
            and self.left_duplicate_count == 0
            and self.right_duplicate_count == 0
            and self.left_unexpected_count == 0
            and self.right_unexpected_count == 0
            and self.left_missing_count == 0
            and self.right_missing_count == 0
            and self.paired_count == self.planned_count
        )

    @property
    def recorded_declarations_compatible(self) -> bool:
        """Only the expressible declaration subset, never full comparability."""
        return (
            self.coverage_complete
            and self.invariant_mismatch_count == 0
            and self.left_backend_count == self.right_backend_count == 1
            and self.distinct_backend_pair_count == self.planned_count
        )

    @property
    def unrepresented_invariants(self) -> tuple[str, ...]:
        return (
            "Budget.max_turns", "Budget.max_retries", "Budget.retry_on",
            "Budget.rollout_timeout",
        )


def _snapshot(value):
    if type(value) not in (list, tuple):
        raise ValueError("invalid harness-swap declarations")
    return tuple(value)


def _validated_inputs(planned_task_ids, left, right):
    try:
        planned = _snapshot(planned_task_ids)
        first = _snapshot(left)
        second = _snapshot(right)
        for task_id in planned:
            sql_episodes._text(task_id, "task_id", nonempty=True)
        for collection in (first, second):
            for episode in collection:
                sql_episodes._validate_episode(episode)
    except (TypeError, ValueError, AttributeError, RecursionError, OverflowError):
        raise ValueError("invalid harness-swap declarations") from None
    return planned, first, second


def _group(episodes):
    groups = {}
    for episode in episodes:
        groups.setdefault(episode.task_id, []).append(episode)
    return groups


def _invariants(episode):
    return (
        episode.ids.corpus_id, episode.ids.split_id, episode.ids.policy_id,
        episode.ids.policy_revision, episode.schema_version, episode.origin,
        episode.arm, episode.task_fingerprint, episode.db_sha256, episode.schema,
        episode.prompt, episode.instrument, episode.reporting,
    )


def project_harness_swap(
    planned_task_ids: list[str] | tuple[str, ...],
    left: list[SqlEpisode] | tuple[SqlEpisode, ...],
    right: list[SqlEpisode] | tuple[SqlEpisode, ...],
) -> HarnessSwapProjection:
    """Compare a non-authoritative declared subset against an independent plan.

    Inputs must be plain lists/tuples of existing valid records and nonempty
    string task IDs. Empty/duplicate plans are reported as incomplete, not
    repaired. Duplicate observations are never selected or compared. All input
    members are validated, including extras. Invalid input raises a bounded,
    generic ValueError without including payloads or chained validator errors.
    Outcomes (including SQL, actions, observations, results and telemetry) are
    validated as record structure only, never compared, executed or scored.

    Caller-declared backend names must be homogeneous within each side and
    different across sides for recorded_declarations_compatible. This does not
    establish that two actual implementations exist or meet HarnessBackend or
    SECOND_HARNESS_REQUIREMENTS, nor that unrepresented budgets match.
    """
    planned, first, second = _validated_inputs(planned_task_ids, left, right)
    planned_counts = Counter(planned)
    planned_ids = set(planned_counts)
    first_groups = _group(first)
    second_groups = _group(second)
    first_ids = set(first_groups)
    second_ids = set(second_groups)
    mismatch_counts = [0] * len(_INVARIANTS)
    paired_count = 0
    same_backend_count = 0
    distinct_backend_count = 0
    for task_id in planned_ids:
        first_matches = first_groups.get(task_id, ())
        second_matches = second_groups.get(task_id, ())
        if len(first_matches) != 1 or len(second_matches) != 1:
            continue
        paired_count += 1
        first_episode = first_matches[0]
        second_episode = second_matches[0]
        for index, (first_value, second_value) in enumerate(zip(
            _invariants(first_episode), _invariants(second_episode),
        )):
            mismatch_counts[index] += int(first_value != second_value)
        if first_episode.backend == second_episode.backend:
            same_backend_count += 1
        else:
            distinct_backend_count += 1
    return HarnessSwapProjection(
        planned_count=len(planned),
        planned_unique_count=len(planned_ids),
        planned_duplicate_count=sum(count - 1 for count in planned_counts.values()),
        left_count=len(first),
        right_count=len(second),
        left_duplicate_count=sum(len(group) - 1 for group in first_groups.values()),
        right_duplicate_count=sum(len(group) - 1 for group in second_groups.values()),
        left_unexpected_count=len(first_ids - planned_ids),
        right_unexpected_count=len(second_ids - planned_ids),
        left_missing_count=len(planned_ids - first_ids),
        right_missing_count=len(planned_ids - second_ids),
        missing_both_count=len(planned_ids - (first_ids | second_ids)),
        overlap_count=len(first_ids & second_ids),
        paired_count=paired_count,
        left_backend_count=len({episode.backend for episode in first}),
        right_backend_count=len({episode.backend for episode in second}),
        same_backend_pair_count=same_backend_count,
        distinct_backend_pair_count=distinct_backend_count,
        field_mismatch_counts=tuple(zip(_INVARIANTS, mismatch_counts)),
    )


__all__ = ["HarnessSwapProjection", "project_harness_swap"]
