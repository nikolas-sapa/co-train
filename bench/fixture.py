"""The committed offline fixture: a BIRD-layout corpus built from text at call time.

**The fixture goes through the real loader.** `materialize()` writes a directory tree
laid out exactly as BIRD ships -- `dev.json` beside `dev_databases/<db_id>/<db_id>.sqlite`
-- so `load_bird()` on the fixture exercises the same code path that `load_bird()` on the
346 MB download does. A fixture with its own parallel loader would prove that the fixture
loader works, which is not the claim anyone needs.

`materialize_spider()` does the same for Spider's layout (`database/` instead of
`dev_databases/`, gold SQL under `query` instead of `SQL`, no `difficulty` field). The
Spider corpus was not downloaded in this lane, so this is the only thing standing behind
`load_spider()`: it proves the loader matches the DOCUMENTED layout, not that the real
archive matches the documentation. That gap is recorded in `docs/bench-taskset.md`.

No binary in the repo: the sqlite file is built by executing `fixtures/schema.sql`, and
both it and `fixtures/dev.json` are committed as text.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SCHEMA_SQL = FIXTURE_DIR / "schema.sql"
DEV_JSON = FIXTURE_DIR / "dev.json"
DB_ID = "campus"


def records() -> list[dict]:
    """The fixture's BIRD-format records, as committed."""
    return json.loads(DEV_JSON.read_text())


def build_db(db_path: str | Path) -> Path:
    """Create the fixture sqlite database by executing the committed DDL."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL.read_text())
        conn.commit()
    finally:
        conn.close()
    return db_path


def materialize(dest: str | Path) -> Path:
    """Write a BIRD-layout fixture corpus under `dest` and return the corpus root."""
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    (root / "dev.json").write_text(json.dumps(records(), indent=1))
    build_db(root / "dev_databases" / DB_ID / f"{DB_ID}.sqlite")
    return root


def materialize_spider(dest: str | Path) -> Path:
    """Write a SPIDER-layout fixture corpus under `dest` and return the corpus root.

    The same questions, re-keyed into Spider's record format: `query` rather than `SQL`,
    and the `difficulty` field removed, because Spider ships none. Removing it is the
    point of this function -- it is what makes `load_spider()` produce
    `tier_source="derived"` tasks and so exercises `_derive_tier`.
    """
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    spider_records = [
        {"db_id": r["db_id"], "question": r["question"], "query": r["SQL"]}
        for r in records()
    ]
    (root / "dev.json").write_text(json.dumps(spider_records, indent=1))
    build_db(root / "database" / DB_ID / f"{DB_ID}.sqlite")
    return root
