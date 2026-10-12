"""Loaders for BIRD dev and Spider dev, against their real documented layouts.

**This module fails loudly and names the path it wanted.** A loader that returns `[]`
when the corpus is absent produces a suite of zero tasks, which scores 0/0 on both arms
and reads as a tie -- and run 3d's exact 23/23 tie is already in this project's history
as the failure mode that killed an instrument. An empty taskset must be an exception,
not a result.

Layouts, as shipped. Verified against the real BIRD archive on 2026-10-11 (`dev.zip`,
346 MB, 1534 records over 11 databases); the Spider layout is as documented by the
dataset, not verified against a download here -- see `docs/bench-taskset.md`.

    BIRD dev   (`dev.zip` -> `dev_20240627/`, with `dev_databases.zip` NESTED inside)
      <root>/dev.json
      <root>/dev_databases/<db_id>/<db_id>.sqlite
      records: {question_id, db_id, question, evidence, SQL, difficulty}

    Spider dev (`spider.zip` -> `spider/`)
      <root>/dev.json
      <root>/database/<db_id>/<db_id>.sqlite
      records: {db_id, question, query, query_toks, sql, ...}   -- no difficulty field

Note the two differences a single loader would get wrong: the gold SQL lives under `SQL`
in BIRD and `query` in Spider, and the database directory is `dev_databases` in BIRD and
`database` in Spider. They are separate functions for that reason rather than one
function with a flag.
"""

from __future__ import annotations

import json
from pathlib import Path

from bench.shapes import shape, skeleton
from bench.task import TIERS, SqlTask


class CorpusMissing(FileNotFoundError):
    """The corpus is not where it was expected. Carries the paths that were tried, so
    the message is actionable rather than `[Errno 2]`."""


def _resolve(root: Path, manifest: str, db_dir: str, label: str) -> Path:
    """Find the directory that actually holds both `manifest` and `db_dir`.

    Tolerates one level of nesting, because the real BIRD archive does not extract to a
    flat root: `dev.zip` produces `dev_20240627/dev.json`, so a caller pointing at the
    extraction directory is pointing one level above the corpus. One level, by exact
    containment test -- not a recursive search, which would happily find a `dev.json`
    belonging to something else entirely.
    """
    root = Path(root).expanduser()
    tried: list[Path] = []
    candidates = [root]
    if root.is_dir():
        candidates += sorted(p for p in root.iterdir() if p.is_dir())
    for cand in candidates:
        tried.append(cand / manifest)
        if (cand / manifest).is_file() and (cand / db_dir).is_dir():
            return cand
    note = "" if root.is_dir() else "  (root is not a directory)\n"
    raise CorpusMissing(
        f"{label} corpus not found under {root}\n"
        f"  expected a directory containing BOTH:\n"
        f"    <root>/{manifest}\n"
        f"    <root>/{db_dir}/<db_id>/<db_id>.sqlite\n"
        f"  looked for {manifest} at:\n"
        + "\n".join(f"    {p}" for p in tried) + "\n" + note
        + "  An absent corpus raises rather than returning an empty taskset: a "
          "zero-task suite scores 0/0 on both arms and reads as a tie."
    )


def _derive_tier(sql: str) -> str:
    """Structural difficulty tier for a corpus that ships no annotation (Spider).

    Counts the structural features a solution has to produce, and buckets the total.
    This is a HEURISTIC, and it is labelled `tier_source="derived"` everywhere it is
    used precisely so it is never averaged with BIRD's human annotation.

    The rule, stated rather than tuned: a flat filtered read with none of these features
    is `simple`; exactly one feature beyond that is `moderate`; two or more, or any
    nesting or set operation at all, is `challenging`.
    """
    sk = skeleton(sql)
    features = sum((
        bool(sk.joins),
        bool(sk.aggregates),
        sk.group,
        sk.having,
        bool(sk.setops),
        sk.nest_depth > 0,
        sk.case,
    ))
    if sk.nest_depth > 0 or sk.setops or features >= 2:
        return "challenging"
    return "moderate" if features == 1 else "simple"


def _build(records: list[dict], root: Path, db_dir: str, sql_key: str,
           source: str, prefix: str, require_db: bool) -> list[SqlTask]:
    """Shared record -> `SqlTask` conversion.

    Skips nothing silently: a record whose sqlite file is absent raises, because a
    corpus with missing databases would otherwise quietly shrink the suite and change
    what the power report describes.
    """
    tasks: list[SqlTask] = []
    missing: list[str] = []
    for i, r in enumerate(records):
        db_id = r["db_id"]
        db_path = (root / db_dir / db_id / f"{db_id}.sqlite").resolve()
        if require_db and not db_path.is_file():
            missing.append(f"{db_id} -> {db_path}")
            continue
        gold = r[sql_key]
        annotated = r.get("difficulty")
        if annotated in TIERS:
            tier, tier_source = annotated, "annotated"
        else:
            tier, tier_source = _derive_tier(gold), "derived"
        # `question_id` where the corpus supplies one (BIRD), else the file position.
        # Either way the id is stable under filtering, which an enumeration over an
        # already-filtered list is not -- and `ptc/paired.py` pairs the arms on it.
        qid = r.get("question_id", i)
        tasks.append(SqlTask(
            name=f"{prefix}-{int(qid):04d}",
            question=r["question"],
            evidence=(r.get("evidence") or "").strip(),
            gold_sql=gold,
            db_id=db_id,
            db_path=str(db_path),
            tier=tier,
            tier_source=tier_source,
            shape=shape(gold, "fine"),
            coarse_shape=shape(gold, "coarse"),
            source=source,
        ))
    if missing:
        more = f"\n    ... and {len(missing) - 10} more" if len(missing) > 10 else ""
        raise CorpusMissing(
            f"{len(missing)} of {len(records)} {source} records name a sqlite file that "
            f"is not present:\n"
            + "\n".join(f"    {m}" for m in missing[:10]) + more
            + "\n  For BIRD, the databases arrive as a NESTED archive: extract "
              "`dev_databases.zip` from inside the extracted `dev.zip` before loading."
        )
    if not tasks:
        raise CorpusMissing(
            f"{source} manifest parsed but produced zero tasks -- refusing to return an "
            "empty taskset."
        )
    names = [t.name for t in tasks]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(
            f"{source}: duplicate task names {dupes[:5]} -- `ptc/paired.py` pairs arms "
            "by name, so a duplicate silently drops one of the pair."
        )
    return tasks


def load_bird(root: str | Path, require_db: bool = True) -> list[SqlTask]:
    """BIRD dev. `root` may be the corpus directory or its parent (see `_resolve`)."""
    base = _resolve(Path(root), "dev.json", "dev_databases", "BIRD dev")
    records = json.loads((base / "dev.json").read_text())
    return _build(records, base, "dev_databases", "SQL", "bird", "bird", require_db)


def load_spider(root: str | Path, require_db: bool = True) -> list[SqlTask]:
    """Spider dev. Gold SQL is `query`, databases live under `database/`, and there is
    no difficulty annotation -- tiers come out `derived`."""
    base = _resolve(Path(root), "dev.json", "database", "Spider dev")
    records = json.loads((base / "dev.json").read_text())
    return _build(records, base, "database", "query", "spider", "spider", require_db)
