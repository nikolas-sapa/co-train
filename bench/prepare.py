"""Offline draw and gold-validation preparation for the bench instrument.

Two artifacts, both published as canonical JSON and addressed by the SHA-256 of
their exact bytes:

- `freeze_draw` freezes a seeded stratified draw over the BIRD corpus. It calls
  the existing selector exactly once, records task and code/runtime identities,
  hashes the selected databases, and publishes one draw document. An underfilled
  draw is published as a diagnostic (`status="underfilled"`) and refused by
  validation; it is never silently backfilled.
- `validate_draw` checks a frozen draw against a caller-retained digest, re-runs
  gold validation on the planned tasks only, and publishes a supplement naming
  the eligible tasks and every exclusion with a bounded category. It never calls
  the selector: the frozen plan is re-resolved by task id, not redrawn.

The security posture mirrors the spec (`spec/bench-preparation.md`): no
artifact-provided filesystem path is ever followed, all corpora and databases
are re-derived from `root`, identity is hashed before and after validation, and
publication is a create-only hard link -- never an overwrite-capable rename. The
serialized documents carry ids, digests, statuses and counts only; questions,
evidence, gold SQL, database paths and raw error details enter `task_sha256`
and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sqlite3
import stat
import tempfile
from pathlib import Path, PureWindowsPath

from bench.loader import CorpusMissing, _resolve, load_bird
from bench.score import ExResult, validate_golds
from bench.suite import select
from bench.task import TIERS, SqlTask

KIND = "bench-preparation"
VERSION = 1
GRANULARITY = "fine"
COMPARISON = "set"
PRODUCTION_TIMEOUT_S = 30.0
PRODUCTION_MAX_ROWS = 500_000
_CHUNK = 1 << 20  # 1 MiB streaming unit for file hashing

# The twelve code-owned repository paths hashed into `source_sha256`. Static:
# never derived from an artifact or an argument.
SOURCE_KEYS = (
    "bench/__init__.py",
    "bench/loader.py",
    "bench/suite.py",
    "bench/task.py",
    "bench/shapes.py",
    "bench/score.py",
    "bench/prepare.py",
    "ptc/__init__.py",
    "ptc/runtime.py",
    "ptc/paired.py",
    "ptc/metrics.py",
    "ptc/sqlite_safety.py",
)

# Every `SqlTask` field that enters `task_sha256`: everything except the
# machine-local `db_path`, which a digest cannot portably commit to.
_TASK_FIELDS = (
    "name", "question", "evidence", "gold_sql", "db_id",
    "tier", "tier_source", "shape", "coarse_shape", "source",
)

_EXCLUSION_CATEGORIES = {
    "gold_error": "gold_execution_rejection",
    "gold_timeout": "configured_deadline",
    "gold_truncated": "configured_row_bound",
    "db_missing": "database_availability",
}

_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

_DRAW_KEYS = frozenset({
    "kind", "version", "stage", "measurement", "fixture", "model_calls",
    "status", "usable", "settings", "actual_per_tier", "shortfall_per_tier",
    "planned", "identity",
})
_SETTINGS_KEYS = frozenset({
    "seed", "per_tier", "granularity", "timeout_s", "max_rows", "comparison",
})
_PLANNED_KEYS = frozenset({"id", "tier", "db_id", "task_sha256"})
_IDENTITY_KEYS = frozenset({
    "universe_sha256", "manifest_sha256", "source_sha256", "databases", "runtime",
})
_DB_KEYS = frozenset({"db_id", "sha256", "size_bytes"})
_RUNTIME_KEYS = frozenset({
    "python_implementation", "python_version", "sqlite_version",
})

_REPO_ROOT = Path(__file__).resolve().parent.parent

__all__ = [
    "PreparationError",
    "PublicationIndeterminateError",
    "freeze_draw",
    "validate_draw",
]


class PreparationError(ValueError):
    """A semantic failure of preparation: bad input, bad artifact, drifted
    corpus. Messages are deliberately neutral -- they name the check that
    failed, not corpus content or filesystem paths."""


class PublicationIndeterminateError(PreparationError):
    """Publication failed after the commit point: the final document was linked
    but a post-link step (unlinking the temporary name, syncing the directory)
    could not be confirmed. The final document is left intact and never
    automatically deleted or retried."""


# --- canonical serialization -------------------------------------------------


def _canonical_bytes(doc: object) -> bytes:
    """The one serialization both functions publish and validation re-derives."""
    return (
        json.dumps(doc, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


# --- input and document-shape validation -------------------------------------


def _check_settings(seed, per_tier, fixture, timeout_s, max_rows) -> float:
    """Freeze's argument contract and the draw document's settings contract.
    Returns the normalized timeout as a float."""
    if type(seed) is not int:
        raise PreparationError("seed must be an exact int")
    if type(per_tier) is not dict or set(per_tier) != set(TIERS):
        raise PreparationError("per_tier must name exactly the three tiers")
    for n in per_tier.values():
        if type(n) is not int or n <= 0:
            raise PreparationError("per_tier counts must be positive exact ints")
    if type(fixture) is not bool:
        raise PreparationError("fixture must be an exact bool")
    if (
        type(timeout_s) not in (int, float)
        or not math.isfinite(timeout_s)
        or not 0 < timeout_s <= PRODUCTION_TIMEOUT_S
    ):
        raise PreparationError("timeout_s must be finite and in (0, 30.0]")
    timeout = float(timeout_s)
    if (
        type(max_rows) is not int
        or not 1 <= max_rows <= PRODUCTION_MAX_ROWS
    ):
        raise PreparationError("max_rows must be an exact int in [1, 500000]")
    if not fixture and (timeout != PRODUCTION_TIMEOUT_S
                        or max_rows != PRODUCTION_MAX_ROWS):
        raise PreparationError("nondefault bounds require fixture=True")
    return timeout


def _keys(d: object, want: frozenset, where: str) -> None:
    if type(d) is not dict or set(d) != want:
        raise PreparationError(f"{where}: unexpected keys")


def _check_draw_shape(doc: object) -> None:
    """Structural validation of a parsed draw document: exact keys, exact
    types, exact constants. Runs entirely before any corpus access."""
    _keys(doc, _DRAW_KEYS, "draw")
    if doc["kind"] != KIND or type(doc["version"]) is not int \
            or doc["version"] != VERSION:
        raise PreparationError("draw kind or version mismatch")
    if doc["stage"] != "draw" or doc["measurement"] is not False \
            or type(doc["model_calls"]) is not int or doc["model_calls"] != 0 \
            or doc["usable"] is not False:
        raise PreparationError("draw constants mismatch")
    if type(doc["fixture"]) is not bool:
        raise PreparationError("fixture must be an exact bool")
    if doc["status"] not in ("frozen", "underfilled"):
        raise PreparationError("unknown draw status")
    settings = doc["settings"]
    _keys(settings, _SETTINGS_KEYS, "settings")
    _check_settings(settings["seed"], settings["per_tier"], doc["fixture"],
                    settings["timeout_s"], settings["max_rows"])
    if type(settings["timeout_s"]) is not float:
        raise PreparationError("timeout_s must be a float")
    if settings["granularity"] != GRANULARITY \
            or settings["comparison"] != COMPARISON:
        raise PreparationError("settings mismatch")
    for field in ("actual_per_tier", "shortfall_per_tier"):
        _keys(doc[field], set(TIERS), field)
        for n in doc[field].values():
            if type(n) is not int or n < 0:
                raise PreparationError(f"{field}: counts must be non-negative ints")
    if type(doc["planned"]) is not list:
        raise PreparationError("planned must be a list")
    for entry in doc["planned"]:
        _keys(entry, _PLANNED_KEYS, "planned entry")
        if type(entry["id"]) is not str or type(entry["db_id"]) is not str \
                or entry["tier"] not in TIERS \
                or not _is_sha256(entry["task_sha256"]):
            raise PreparationError("bad planned entry")
    identity = doc["identity"]
    _keys(identity, _IDENTITY_KEYS, "identity")
    for key in ("universe_sha256", "manifest_sha256"):
        if not _is_sha256(identity[key]):
            raise PreparationError("bad identity digest")
    sources = identity["source_sha256"]
    if type(sources) is not dict or set(sources) != set(SOURCE_KEYS):
        raise PreparationError("bad source identity")
    for rel in SOURCE_KEYS:
        if not _is_sha256(sources[rel]):
            raise PreparationError("bad source digest")
    if type(identity["databases"]) is not list:
        raise PreparationError("databases must be a list")
    for entry in identity["databases"]:
        _keys(entry, _DB_KEYS, "database entry")
        if type(entry["db_id"]) is not str \
                or not _is_sha256(entry["sha256"]) \
                or type(entry["size_bytes"]) is not int \
                or entry["size_bytes"] < 0:
            raise PreparationError("bad database entry")
    _keys(identity["runtime"], _RUNTIME_KEYS, "runtime")
    for value in identity["runtime"].values():
        if type(value) is not str:
            raise PreparationError("bad runtime entry")


def _check_draw_consistency(doc: dict, planned_tasks: list[SqlTask]) -> None:
    """The recorded counts must be the counts the planned list implies."""
    actual = {tier: 0 for tier in TIERS}
    for task in planned_tasks:
        actual[task.tier] += 1
    shortfall = {
        tier: doc["settings"]["per_tier"][tier] - actual[tier] for tier in TIERS
    }
    if doc["actual_per_tier"] != actual or doc["shortfall_per_tier"] != shortfall:
        raise PreparationError("draw counts are inconsistent")
    expected = "underfilled" if any(shortfall.values()) else "frozen"
    if doc["status"] != expected:
        raise PreparationError("draw status is inconsistent")


# --- canonical hashing --------------------------------------------------------


def _task_sha256(task: SqlTask) -> str:
    """Canonical digest over every task field except machine-local `db_path`."""
    return hashlib.sha256(
        _canonical_bytes({k: getattr(task, k) for k in _TASK_FIELDS})
    ).hexdigest()


def _universe_sha256(tasks: list[SqlTask]) -> str:
    """Order-independent digest over the unique candidate task identities."""
    return hashlib.sha256(
        _canonical_bytes(sorted({_task_sha256(t) for t in tasks}))
    ).hexdigest()


def _hash_file(path: Path) -> str:
    """Streamed SHA-256 of one file, in 1 MiB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_sha256() -> dict:
    """The exact twelve-key map of logical source names to content digests.
    Only code-owned `SOURCE_KEYS` are read -- never an artifact-supplied path."""
    entries = {}
    for rel in SOURCE_KEYS:
        try:
            entries[rel] = _hash_file(_REPO_ROOT / rel)
        except OSError:
            raise PreparationError("source artifact unavailable") from None
    return entries


def _runtime() -> dict:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
    }


# --- corpus -------------------------------------------------------------------


def _within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_db_id(db_id: str) -> bool:
    """A database id must be a nonempty single path component: no separators,
    no absolute form on either platform, no `.`/`..`, no control characters
    or NUL."""
    if not db_id or db_id in (".", "..") or "/" in db_id or "\\" in db_id:
        return False
    if os.path.isabs(db_id) or PureWindowsPath(db_id).is_absolute():
        return False
    return all(c.isprintable() for c in db_id)


def _check_candidates(tasks: list[SqlTask], db_root: Path) -> None:
    """Every candidate must be a well-typed, uniquely named, annotated BIRD
    task whose database id is a safe single component resolving inside the
    corpus database directory."""
    names: set[str] = set()
    for task in tasks:
        if not isinstance(task, SqlTask):
            raise PreparationError("candidate is not a SqlTask")
        for field in _TASK_FIELDS + ("db_path",):
            if type(getattr(task, field)) is not str:
                raise PreparationError("candidate field has unexpected type")
        if task.source != "bird" or task.tier_source != "annotated":
            raise PreparationError("only annotated BIRD tasks qualify")
        if not task.name or task.name in names:
            raise PreparationError("duplicate or empty task name")
        names.add(task.name)
        if not _safe_db_id(task.db_id):
            raise PreparationError("database id is not a safe single component")
        if not _within(Path(task.db_path).resolve(), db_root):
            raise PreparationError(
                "database resolves outside the corpus database directory")


def _corpus(root) -> tuple[str, list[SqlTask]]:
    """Resolve the corpus base and load it, hashing `dev.json` before and
    after the read. Returns the manifest digest and the candidate tasks.
    Missing or corrupt corpora are neutral semantic failures, unchained from
    the loader's path-bearing diagnostics."""
    try:
        base = _resolve(Path(root), "dev.json", "dev_databases", "BIRD dev")
    except CorpusMissing:
        raise PreparationError("corpus unavailable") from None
    manifest = base / "dev.json"
    try:
        before = _hash_file(manifest)
    except OSError:
        raise PreparationError("manifest unavailable") from None
    try:
        tasks = load_bird(base)
    except CorpusMissing:
        raise PreparationError("corpus unavailable") from None
    except ValueError:
        raise PreparationError("corpus records rejected") from None
    try:
        after = _hash_file(manifest)
    except OSError:
        raise PreparationError("manifest unavailable") from None
    if after != before:
        raise PreparationError("manifest changed during load")
    _check_candidates(tasks, (base / "dev_databases").resolve())
    return before, tasks


# --- database hashing ---------------------------------------------------------


def _check_sidecars(db_path: Path) -> None:
    for suffix in _SIDECAR_SUFFIXES:
        if os.path.lexists(str(db_path) + suffix):
            raise PreparationError("database sidecar present")


def _file_key(st: os.stat_result) -> tuple:
    """Metadata identifying one unchanged file: same inode, same content.
    `st_atime` is excluded because hashing the file updates it, and `st_ctime`
    follows atime updates on some filesystems."""
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def _hash_db(db_path: Path) -> tuple[str, int]:
    """Streamed SHA-256 of one quiescent database. Rejects sidecars, and
    requires the descriptor and the path to identify the SAME unchanged file
    at open time and again after streaming -- a replacement between `open`
    and `stat` compares unequal in either direction."""
    _check_sidecars(db_path)
    try:
        fh = open(db_path, "rb")
    except OSError:
        raise PreparationError("database unavailable") from None
    try:
        first = os.fstat(fh.fileno())
        if not stat.S_ISREG(first.st_mode):
            raise PreparationError("database is not a regular file")
        first_key = _file_key(first)
        if _file_key(os.stat(db_path)) != first_key:
            raise PreparationError("database changed during hashing")
        h = hashlib.sha256()
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
        last_key = _file_key(os.fstat(fh.fileno()))
        if last_key != first_key or _file_key(os.stat(db_path)) != last_key:
            raise PreparationError("database changed during hashing")
    finally:
        fh.close()
    _check_sidecars(db_path)
    return h.hexdigest(), first.st_size


def _database_entries(planned_tasks: list[SqlTask]) -> list[dict]:
    """One `{db_id, sha256, size_bytes}` entry per selected database."""
    paths: dict[str, Path] = {}
    for task in planned_tasks:
        resolved = Path(task.db_path).resolve()
        if task.db_id in paths and paths[task.db_id] != resolved:
            raise PreparationError("conflicting database paths for one db_id")
        paths[task.db_id] = resolved
    entries = []
    for db_id in sorted(paths):
        sha, size = _hash_db(paths[db_id])
        entries.append({"db_id": db_id, "sha256": sha, "size_bytes": size})
    return entries


def _code_identity() -> dict:
    """Code/runtime identity, snapshotted independently of the corpus so
    ordinary drift during a load or hash is caught at the next comparison."""
    return {"source_sha256": _source_sha256(), "runtime": _runtime()}


def _identity(tasks: list[SqlTask], planned_tasks: list[SqlTask],
              manifest_sha: str, code: dict) -> dict:
    identity = {
        "universe_sha256": _universe_sha256(tasks),
        "manifest_sha256": manifest_sha,
        "source_sha256": code["source_sha256"],
        "databases": _database_entries(planned_tasks),
        "runtime": code["runtime"],
    }
    _require_identity(code, _code_identity())
    return identity


def _require_identity(expected: dict, actual: dict) -> None:
    """Canonical identity equality. The single before/post comparison point:
    every recheck funnels through here rather than per-field shortcuts."""
    if _canonical_bytes(expected) != _canonical_bytes(actual):
        raise PreparationError("identity mismatch")


def _resolve_planned(entries: list[dict], tasks: list[SqlTask]) -> list[SqlTask]:
    """Re-resolve frozen task ids against the freshly loaded candidates. Never
    calls the selector; a missing, duplicated or mismatched id rejects."""
    by_name = {t.name: t for t in tasks}
    planned: list[SqlTask] = []
    seen: set[str] = set()
    for entry in entries:
        if entry["id"] in seen:
            raise PreparationError("duplicate planned id")
        task = by_name.get(entry["id"])
        if task is None:
            raise PreparationError("planned task not in corpus")
        if entry["tier"] != task.tier or entry["db_id"] != task.db_id \
                or entry["task_sha256"] != _task_sha256(task):
            raise PreparationError("planned task identity mismatch")
        seen.add(entry["id"])
        planned.append(task)
    return planned


def _check_sidecars_for(tasks: list[SqlTask]) -> None:
    for db_path in {t.db_path for t in tasks}:
        _check_sidecars(Path(db_path))


def _exclusions(broken: list, planned_tasks: list[SqlTask]) -> list[dict]:
    """Turn the scorer's defective-task outcomes into ordered disclosures.

    Every outcome must pair the exact planned `SqlTask` with an invalid
    `ExResult` whose status maps to a bounded category. Unknown, duplicated,
    mismatched or unexpectedly shaped outcomes abort publication; raw result
    detail never reaches the document. Exclusions are emitted in planned
    order whatever order the scorer returned, so `planned` stays the
    disjoint union of `eligible_ids` and `exclusions`.
    """
    planned_by_name = {t.name: t for t in planned_tasks}
    outcomes: dict[str, tuple[str, str]] = {}
    for pair in broken:
        if not (isinstance(pair, tuple) and len(pair) == 2):
            raise PreparationError("unexpected validation outcome")
        task, result = pair
        if not isinstance(task, SqlTask) or not isinstance(result, ExResult):
            raise PreparationError("unexpected validation outcome")
        if result.valid is not False or type(result.status) is not str:
            raise PreparationError("unexpected validation outcome")
        category = _EXCLUSION_CATEGORIES.get(result.status)
        if category is None:
            raise PreparationError("unexpected validation outcome")
        if task.name in outcomes:
            raise PreparationError("duplicate exclusion id")
        planned = planned_by_name.get(task.name)
        if planned is None or planned != task:
            raise PreparationError("unknown or mismatched exclusion id")
        outcomes[task.name] = (result.status, category)
    return [
        {
            "id": task.name,
            "status": outcomes[task.name][0],
            "category": outcomes[task.name][1],
        }
        for task in planned_tasks
        if task.name in outcomes
    ]


# --- publication ---------------------------------------------------------------


def _sync_dir(parent: Path) -> None:
    fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _quiet_unlink(path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _publish(doc: dict, output) -> str:
    """Publish canonical bytes atomically and create-only.

    Serialize in memory, write+fsync a private temporary file in the
    caller-owned output directory, hard-link it to the final name (the commit
    point), drop the temporary link and sync the directory. A failure before
    the link leaves nothing; a failure after it raises
    `PublicationIndeterminateError` with the final document intact.
    """
    data = _canonical_bytes(doc)
    out_path = Path(output)
    parent = out_path.parent
    if not parent.is_dir():
        raise PreparationError("output directory does not exist")
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".prepare-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        _quiet_unlink(tmp)
        raise
    try:
        os.link(tmp, out_path)  # commit point; FileExistsError propagates
    except BaseException:
        _quiet_unlink(tmp)
        raise
    try:
        os.unlink(tmp)
        _sync_dir(parent)
    except Exception as exc:
        raise PublicationIndeterminateError(
            "publication outcome is indeterminate; final document preserved"
        ) from exc
    return hashlib.sha256(data).hexdigest()


# --- public API ----------------------------------------------------------------


def freeze_draw(
    root,
    output,
    *,
    seed,
    per_tier,
    fixture,
    timeout_s=PRODUCTION_TIMEOUT_S,
    max_rows=PRODUCTION_MAX_ROWS,
) -> str:
    """Freeze a seeded stratified draw and publish it under `output`.

    Returns the SHA-256 of the exact published bytes. The selector is called
    exactly once; a shortfall produces a published `underfilled` diagnostic,
    never a backfilled draw.
    """
    timeout = _check_settings(seed, per_tier, fixture, timeout_s, max_rows)
    # Code/runtime identity is captured before the corpus is touched; after
    # the draw is built, the whole identity is rechecked against a fresh
    # corpus load and the selected ids re-resolved -- never re-selected.
    code = _code_identity()
    manifest_sha, tasks = _corpus(root)
    selected = select(tasks, dict(per_tier), seed=seed, granularity=GRANULARITY)
    actual = {tier: 0 for tier in TIERS}
    for task in selected:
        actual[task.tier] += 1
    shortfall = {tier: per_tier[tier] - actual[tier] for tier in TIERS}
    planned_entries = [
        {
            "id": task.name,
            "tier": task.tier,
            "db_id": task.db_id,
            "task_sha256": _task_sha256(task),
        }
        for task in selected
    ]
    expected_identity = _identity(tasks, selected, manifest_sha, code)
    code2 = _code_identity()
    manifest_sha2, tasks2 = _corpus(root)
    selected2 = _resolve_planned(planned_entries, tasks2)
    _require_identity(expected_identity,
                      _identity(tasks2, selected2, manifest_sha2, code2))
    doc = {
        "kind": KIND,
        "version": VERSION,
        "stage": "draw",
        "measurement": False,
        "fixture": fixture,
        "model_calls": 0,
        "status": "underfilled" if any(shortfall.values()) else "frozen",
        "usable": False,
        "settings": {
            "seed": seed,
            "per_tier": {tier: per_tier[tier] for tier in TIERS},
            "granularity": GRANULARITY,
            "timeout_s": timeout,
            "max_rows": max_rows,
            "comparison": COMPARISON,
        },
        "actual_per_tier": actual,
        "shortfall_per_tier": shortfall,
        "planned": planned_entries,
        "identity": expected_identity,
    }
    return _publish(doc, output)


def validate_draw(
    root,
    draw_path,
    output,
    *,
    expected_draw_sha256,
) -> str:
    """Validate a frozen draw's gold queries and publish a supplement.

    Requires the caller-retained digest of the draw's exact published bytes;
    a mismatch rejects before parsing or any corpus access. Recomputes the
    full identity before running any SQL and rechecks it after, and publishes
    nothing unless every check holds. Returns the SHA-256 of the exact
    published supplement bytes.
    """
    if not _is_sha256(expected_draw_sha256):
        raise PreparationError("expected draw digest must be a sha256 hex string")
    raw = Path(draw_path).read_bytes()
    draw_sha = hashlib.sha256(raw).hexdigest()
    if draw_sha != expected_draw_sha256:
        raise PreparationError("retained draw digest mismatch")
    doc = _parse_draw(raw)
    if doc["status"] != "frozen":
        raise PreparationError("underfilled draws are not validatable")

    # Everything up to the scorer runs without a single query: corpus reload,
    # candidate checks, planned-id resolution and the full identity recompute.
    # Code/runtime is snapshotted before the load so drift during it is caught.
    code = _code_identity()
    manifest_sha, tasks = _corpus(root)
    planned_tasks = _resolve_planned(doc["planned"], tasks)
    _check_draw_consistency(doc, planned_tasks)
    _require_identity(doc["identity"],
                      _identity(tasks, planned_tasks, manifest_sha, code))

    settings = doc["settings"]
    _check_sidecars_for(planned_tasks)
    broken = validate_golds(
        planned_tasks,
        timeout_s=settings["timeout_s"],
        max_rows=settings["max_rows"],
    )
    _check_sidecars_for(planned_tasks)
    exclusions = _exclusions(broken, planned_tasks)

    # Post-validation: snapshot code/runtime, reload and recheck every recorded
    # identity before publishing. A blocked supplement is admissible only when
    # all post-validation identities remain available and unchanged.
    code2 = _code_identity()
    manifest_sha2, tasks2 = _corpus(root)
    planned_tasks2 = _resolve_planned(doc["planned"], tasks2)
    _require_identity(doc["identity"],
                      _identity(tasks2, planned_tasks2, manifest_sha2, code2))

    excluded_names = {e["id"] for e in exclusions}
    eligible = [t for t in planned_tasks if t.name not in excluded_names]
    excluded = [t for t in planned_tasks if t.name in excluded_names]
    status = ("blocked" if any(e["status"] == "db_missing" for e in exclusions)
              else "complete")
    supplement = {
        "kind": KIND,
        "version": VERSION,
        "stage": "gold-validation",
        "measurement": False,
        "fixture": doc["fixture"],
        "model_calls": 0,
        "status": status,
        "usable": status == "complete" and bool(eligible),
        "draw_sha256": draw_sha,
        "planned_ids": [e["id"] for e in doc["planned"]],
        "eligible_ids": [t.name for t in eligible],
        "exclusions": exclusions,
        "settings": {
            "timeout_s": settings["timeout_s"],
            "max_rows": settings["max_rows"],
            "comparison": settings["comparison"],
        },
        "identity_checked": True,
        "counts": {
            "planned": _tier_counts(planned_tasks),
            "eligible": _tier_counts(eligible),
            "excluded": _tier_counts(excluded),
        },
        "shapes": {
            "planned": _shape_counts(planned_tasks),
            "eligible": _shape_counts(eligible),
        },
    }
    return _publish(supplement, output)


def _tier_counts(tasks: list[SqlTask]) -> dict:
    return {tier: sum(1 for t in tasks if t.tier == tier) for tier in TIERS}


def _shape_counts(tasks: list[SqlTask]) -> dict:
    """Distinct shape counts at both granularities -- not effective n."""
    return {
        "fine": len({t.shape for t in tasks}),
        "coarse": len({t.coarse_shape for t in tasks}),
    }


# --- strict parsing -------------------------------------------------------------


def _no_dup_keys(pairs: list) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise PreparationError("duplicate JSON key")
        out[key] = value
    return out


def _reject_constant(value: str):
    raise PreparationError("non-finite number in document")


def _parse_draw(raw: bytes) -> dict:
    """Strictly parse a draw document: UTF-8, no duplicate keys, no non-finite
    numbers, and byte-exact canonical serialization."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreparationError("draw is not UTF-8") from exc
    try:
        doc = json.loads(text, object_pairs_hook=_no_dup_keys,
                         parse_constant=_reject_constant)
    except PreparationError:
        raise
    except ValueError as exc:
        raise PreparationError("draw is not valid JSON") from exc
    try:
        canonical = _canonical_bytes(doc)
    except (ValueError, OverflowError) as exc:
        raise PreparationError("draw cannot be canonically serialized") from exc
    if canonical != raw:
        raise PreparationError("draw is not canonically serialized")
    _check_draw_shape(doc)
    return doc
