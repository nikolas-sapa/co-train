"""Pure accounting of caller-declared training and holdout task identities.

This is not semantic contamination detection or a split-clearance grant. Caller
membership is neither authenticated nor proof of complete training exposure.
Preparation's canonical identity includes name: renamed content can evade both
checks. Database paths are excluded from that identity and never inspected here.

Importing existing bench.prepare retains its existing module initialization
(including repository-path resolution). Accounting itself performs no I/O,
admission, selection, scoring, runtime construction or framework import.
"""

from __future__ import annotations

from dataclasses import dataclass

from bench import prepare
from bench.task import TIERS, SqlTask

_DIAGNOSTIC_LIMIT = 10


class HoldoutAccountingError(ValueError):
    """Malformed declared membership, with bounded content-free diagnostics."""


@dataclass(frozen=True)
class HoldoutAccounting:
    """Counts over complete declarations, not an admission or measurement receipt.

    Overlap counts are distinct shared names and shared canonical fingerprints,
    respectively, not their sum. Categories may describe the same members.
    Duplicate names within either declaration refuse before a result is returned.
    Diagnostics contain at most ten sorted digests per category. For shared IDs,
    the digest belongs to the training member, whose content may differ from the
    holdout member. No raw name, question, SQL or path is exposed.

    Ordinary construction of this data class supplies no authority.
    """

    training_count: int
    holdout_count: int
    id_overlap_count: int
    fingerprint_overlap_count: int
    shared_id_task_sha256: tuple[str, ...]
    shared_task_sha256: tuple[str, ...]

    @property
    def identities_disjoint(self) -> bool:
        """Only declared identity disjointness, never semantic split clearance."""
        return self.id_overlap_count == 0 and self.fingerprint_overlap_count == 0


def _task_identity(task: SqlTask) -> tuple[str, str]:
    if type(task) is not SqlTask:
        raise HoldoutAccountingError("invalid task membership")
    try:
        for field in prepare._TASK_FIELDS + ("db_path",):
            value = getattr(task, field)
            if type(value) is not str or (field != "evidence" and not value.strip()):
                raise HoldoutAccountingError("invalid task membership")
        if (
            task.tier not in TIERS
            or task.tier_source not in ("annotated", "derived")
            or task.source not in ("bird", "spider", "fixture")
        ):
            raise HoldoutAccountingError("invalid task membership")
        digest = prepare._task_sha256(task)
    except (AttributeError, TypeError, ValueError):
        raise HoldoutAccountingError("invalid task membership") from None
    return task.name, digest


def _membership(tasks: tuple[SqlTask, ...]) -> dict[str, str]:
    if type(tasks) is not tuple or not tasks:
        raise HoldoutAccountingError("membership must be a nonempty tuple")
    identities: dict[str, str] = {}
    for task in tasks:
        name, digest = _task_identity(task)
        if name in identities:
            raise HoldoutAccountingError("duplicate task identity")
        identities[name] = digest
    return identities


def account_holdout_membership(
    training: tuple[SqlTask, ...],
    holdout: tuple[SqlTask, ...],
) -> HoldoutAccounting:
    """Account complete, explicit, nonempty tuples of real SqlTask records.

    Each side must have unique nonblank names, correctly typed string fields,
    nonblank required fields (evidence may be empty), and declared SqlTask enum
    values. Malformed membership refuses with HoldoutAccountingError. Paths are
    caller strings only: existence, safety, DB bytes and SQL validity are not
    checked. No corpus eligibility or source authority is inferred.

    One shared name OR canonical fingerprint makes identities_disjoint false.
    Fingerprints use preparation's existing helper unchanged, including name and
    excluding db_path. Renaming otherwise identical content can therefore appear
    disjoint. This function cannot grant split clearance or establish complete
    training exposure, semantic diversity, scientific or runtime acceptance.
    """
    training_identities = _membership(training)
    holdout_identities = _membership(holdout)
    shared_ids = training_identities.keys() & holdout_identities.keys()
    shared_fingerprints = (
        set(training_identities.values()) & set(holdout_identities.values())
    )
    return HoldoutAccounting(
        training_count=len(training),
        holdout_count=len(holdout),
        id_overlap_count=len(shared_ids),
        fingerprint_overlap_count=len(shared_fingerprints),
        shared_id_task_sha256=tuple(sorted(
            training_identities[name] for name in shared_ids
        )[:_DIAGNOSTIC_LIMIT]),
        shared_task_sha256=tuple(sorted(shared_fingerprints)[:_DIAGNOSTIC_LIMIT]),
    )
