# Offline draw and gold-validation preparation

2026-10-31. Base `8dc8d15`. Architect-reviewed test-first contract.
Implement only `bench/prepare.py` and `bench/test_prepare.py`; documentation is
parent-owned. Existing loader, selector, scorer, consumers and gates stay unchanged.
Only temporary fixture corpora may be exercised during this implementation.

## Test plan, before implementation

| ID | Test and numeric acceptance criterion |
|---|---|
| T01 | Missing/bool seed; missing/extra tier; zero, negative, fractional or bool count; non-bool fixture declaration: reject with **0 SQL queries**. All **3** tier counts are explicit positive exact ints. |
| T02 | For **100 seeds x 3 input orders**, frozen IDs equal direct existing `select(..., granularity="fine")` output exactly: **0 ordering differences**. Freeze calls selector exactly **1 time**; validation calls it **0 times**. |
| T03 | Real committed BIRD-layout fixture, request **2/3/3**: **8 unique planned IDs**. Validation retains all **8** planned IDs, **8 eligible**, **0 exclusions**; three-tier counts **2/3/3**. |
| T04 | Same fixture, request **3/3/3**: **8 planned**, simple shortfall **1**, other shortfalls **0**. Publish diagnostic underfilled draw; validation rejects with **0 SQL queries**, **0 supplements**. |
| T05 | One derived-tier task, Spider task or duplicate name: reject before **0 queries**. A database resolving outside corpus database directory also rejects before hashing/querying that database. |
| T06 | Corrupt **1** fixture gold to name an absent table before freezing: exactly **1 gold_error**, **7 eligible**, **8 planned**, **0 policy outcomes**. |
| T07 | Fixture row cap **2**: **2 rows** eligible, **3 rows** yields exactly **1 gold_truncated** with configured-row-bound category. |
| T08 | Recursive gold with **0.02s** timeout: exactly **1 gold_timeout**, overall test elapsed **<2s**. This is a test ceiling, not a hard-process guarantee. |
| T09 | Independently change manifest, selected database, source file or frozen setting: reject; **0 complete supplements**. Wrong retained digest: **0 corpus loads, 0 SQL queries**. |
| T10 | Change manifest/database or introduce WAL/SHM/journal during validation: **0 supplements published**. Check database file-descriptor/path metadata around streaming hash operations. |
| T11 | Unique question/evidence/SQL/path/error sentinels: serialized documents contain **0 occurrences**, **0 absolute DB paths**, **0 raw error details**, **0 solve-rate/frontier-result fields**. |
| T12 | Repeat publication to existing file or symlink: fail with **0 existing bytes changed**. A target-creation race also changes **0 existing bytes**. |
| T13 | Inject prepublication write/fsync failure: **0 final files**. Postpublication directory-sync failure: explicit publication-indeterminate error and **1 complete parseable document**, never partial JSON. |
| T14 | Isolated `-I -B` import and complete fixture flow with train/verifiers/provider modules and networking blocked: **0 forbidden imports/calls**. No installs or optional runtime dependencies. |
| T15 | Duplicate JSON keys, noncanonical JSON, unknown/missing keys, bool-as-int or nonfinite settings: reject before **0 SQL queries**. Production bounds exactly **30.0s/500000 rows/set**; smaller bounds only for explicit fixtures. |
| T16 | Zero eligible tasks: complete but unusable; scorer `db_missing`: blocked/unusable only with unchanged available post-identities. Unexpected/duplicate/unknown exclusions or infrastructure errors: **0 successful supplements**. |

Required actual failing controls, each followed by restored GREEN:

1. Suppress exclusion propagation; T06 must fail on the real bad-gold fixture.
2. Bypass identity comparison; T09 must fail after a real database byte change.
3. Bypass exclusive publication or export a raw record; T11/T12 must fail.

An import/setup error is not a valid control. Observe intended call-phase
assertion/refusal failure, mutation hits, restored passing behavior and unchanged
source files. No proposed control counts as executed evidence.

## Non-goals

No real corpus inspection/draw/query, policy/model/provider selection or calls,
training, downloads, installs, native jobs, frontier manifest, solve rates,
baseline claims, protocol/signature changes, tier collapse, CLI integration,
existing consumer/schema changes or `train` dependencies.
The fixture seeds/counts above are test parameters, not experiment settings.

## API and byte contract

```python
freeze_draw(
    root, output, *, seed, per_tier, fixture,
    timeout_s=30.0, max_rows=500000,
) -> str
validate_draw(
    root, draw_path, output, *, expected_draw_sha256,
) -> str
```

Both return the lowercase SHA-256 of the exact published bytes. Callers retain
the draw digest independently. Validation requires that digest before parsing
or accessing the corpus; deriving it from the file defeats this check.

Canonical bytes are UTF-8:
`json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"`.
Reject duplicate keys, noncanonical serialization and unknown/missing fields.
Use explicit serialization allowlists, never `asdict(SqlTask)` or `ExResult.detail`.
No artifact-provided filesystem paths are read.

Require `type(seed) is int`, exact dict counts for all and only `TIERS` with
positive exact ints, and `type(fixture) is bool`. Fixed fine granularity.
Bounds are finite `0 < timeout_s <= 30.0`, exact integer
`1 <= max_rows <= 500000`; nondefault bounds require `fixture=True`.
Normalize valid timeout to float. Validation accepts no overrides.
`fixture=True` is an operator declaration, not authenticated fixture origin.

Semantic failures use neutral `PreparationError(ValueError)` messages.
An existing output raises `FileExistsError` without clobbering it.
Expose `PublicationIndeterminateError(PreparationError)` for failure after the
exclusive publication commit point; never automatically delete or retry it.

## Draw document

Exact top-level keys:
`kind`, `version`, `stage`, `measurement`, `fixture`, `model_calls`, `status`,
`usable`, `settings`, `actual_per_tier`, `shortfall_per_tier`, `planned`, `identity`.

- Constants: `kind="bench-preparation"`, exact integer `version=1`,
  `stage="draw"`, `measurement=false`, exact integer `model_calls=0`.
- `status="frozen"` or `"underfilled"`; `usable=false` always, since no gold
  validation has occurred.
- `settings`: exactly `seed`, `per_tier`, `granularity="fine"`, `timeout_s`,
  `max_rows`, `comparison="set"`.
- Actual and shortfall counts contain exactly the three tiers.
- Ordered `planned` entries contain exactly `id`, `tier`, `db_id`, `task_sha256`.
  Freeze delegates to existing selector once, never redraws or backfills.
- `identity`: exactly `universe_sha256`, `manifest_sha256`, `source_sha256`,
  `databases`, `runtime`.
- Database entries: exactly `db_id`, `sha256`, `size_bytes`, once per selected DB.
  Runtime: exactly `python_implementation`, `python_version`, `sqlite_version`.

Hash task content canonically, including all `SqlTask` fields except machine-local
`db_path`. Questions/evidence/golds only enter this digest, never public fields.
Universe digest is canonical and order-independent over unique candidate task
identities. Only annotated BIRD tasks qualify. Validate all candidate types/names,
database IDs and resolved path containment before database hashing.

## Gold-validation supplement

Exact top-level keys:
`kind`, `version`, `stage`, `measurement`, `fixture`, `model_calls`, `status`,
`usable`, `draw_sha256`, `planned_ids`, `eligible_ids`, `exclusions`, `settings`,
`identity_checked`, `counts`, `shapes`.

- Same common constants; `stage="gold-validation"`, `draw_sha256` is the retained
  exact-byte parent digest; `identity_checked=true` after all checks.
- `settings`: exactly `timeout_s`, `max_rows`, `comparison`, matching draw.
- `planned_ids` preserves all frozen IDs. Eligible IDs preserve planned order;
  exclusions are disjoint, ordered and exhaustive with eligible IDs.
- Exclusions contain only `id`, `status`, `category`:
  `gold_error -> gold_execution_rejection`,
  `gold_timeout -> configured_deadline`,
  `gold_truncated -> configured_row_bound`,
  `db_missing -> database_availability`.
- `counts`: exactly `planned`, `eligible`, `excluded`, each an exact three-tier
  count dictionary. `shapes`: exactly `planned`, `eligible`, each containing
  distinct `fine` and `coarse` shape counts, not effective sample sizes.
- `status="complete"` except any `db_missing` makes it `"blocked"`.
  `usable = status == "complete" and len(eligible_ids) > 0`, meaning only
  gold-validation usability, never experiment authorization/frontier eligibility.
- Unexpected statuses, duplicate/unknown exclusion IDs or infrastructure
  exceptions abort publication. A blocked DB supplement is possible only if
  every post-validation identity remains available and unchanged.

## Identity, sequencing and limitations

Reuse loader `_resolve(root, "dev.json", "dev_databases", "BIRD dev")` to establish
the base, then real `load_bird(base)`. Hash `base/dev.json` before/after loading.
Freeze records code/runtime identity and hashes selected quiescent DBs before
publication. Underfilled draws remain diagnostic; validation refuses them.

Validation re-resolves stored IDs directly, never calls selector. Recompute and
compare the entire expected draw identity/structure before any SQL. Pass exactly
those tasks to existing `validate_golds()` with frozen explicit bounds. Reload
corpus afterward and recheck manifest/universe/planned-task/source/runtime/DB
identities and sidecars before publication. Never follow artifact-supplied paths.

Static source keys are precisely:
`bench/__init__.py`, `bench/loader.py`, `bench/suite.py`, `bench/task.py`,
`bench/shapes.py`, `bench/score.py`, `bench/prepare.py`,
`ptc/__init__.py`, `ptc/runtime.py`, `ptc/paired.py`, `ptc/metrics.py`,
`ptc/sqlite_safety.py`. Read code-owned repository paths only.

Stream DB hashing in **1 MiB chunks**, checking file-descriptor/path metadata
before/after. Require resolved DB paths inside the resolved corpus DB directory.
Reject `-wal`, `-shm`, `-journal` before and after validation/hashing.
Source/corpus trees and output directories must be quiescent. Before/after
checks detect ordinary drift, not transient change-and-restore or hostile
writers. The scorer reopens paths, so this is not one guaranteed immutable
SQLite snapshot. Fresh interpreter required after source edits; disk hashes
do not authenticate already-loaded code, weights or authority.

Publish only after all work succeeds: serialize in memory, private temporary file
in caller-owned existing output directory, write/flush/fsync, exclusive hard link
to final pathname, remove own temporary link, sync directory. Never use an
overwrite-capable rename. Precommit failure leaves final absent; failure after
linking raises publication-indeterminate with intact final document preserved.

Current scorer has read-only/query-only/authorizer protections and soft
deadline/row limits, not hard process CPU/memory/wall-clock bounds. Hashing,
row width, temporary IO and total validation duration remain unbounded.
No whole-process/resource containment or authenticated provenance claim.
Current source defaults are 30s/500000/set; stale historical 100000/multiset
examples are not silently amended by this module.
