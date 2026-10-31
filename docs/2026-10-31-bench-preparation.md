# Offline draw and gold-validation preparation

2026-10-31, base `8dc8d15`. Fixture-tested offline preparation.
The [test-first contract](../spec/bench-preparation.md) defines this follow-on.
This is not a completed baseline or experiment.

This prepares provenance, not model measurements. Stage 5 remains PARTIAL:
the current BIRD paired untrained baseline is missing, not zero. Stage 6
remains BLOCKED. No frontier manifest or policy outcomes are produced.

## Fixture-only example

This example uses the committed eight-question fixture. Its seed/counts are
test inputs, not experiment choices. Output directory must already exist.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from bench.fixture import materialize
from bench.prepare import freeze_draw, validate_draw

with TemporaryDirectory() as temporary:
    directory = Path(temporary)
    corpus = materialize(directory / "fixture")
    draw = directory / "draw.json"
    supplement = directory / "gold-validation.json"
    retained_digest = freeze_draw(
        corpus, draw, seed=7,
        per_tier={"simple": 2, "moderate": 3, "challenging": 3},
        fixture=True,
    )
    validation_digest = validate_draw(
        corpus, draw, supplement,
        expected_draw_sha256=retained_digest,
    )
```

Keep the returned draw digest independently. Validation checks it before
parsing or accessing the corpus. Do not derive the expected digest from the
file you are trying to validate. Digests bind content, not authority.

## Two separate, create-only documents

The draw freezes ordered planned IDs using the existing selector once.
It records explicit three-tier counts, seed, fixed fine granularity,
manifest/universe/task/source/runtime/database identities and scorer bounds.
It does not execute SQL. `usable=false` always, because gold validation has
not occurred. An underfilled draw preserves selected IDs and shortfalls;
validation refuses it without SQL. No redraw, replacement or backfill.

Validation resolves those frozen IDs directly, checks identities before
SQL, calls the existing gold-only validator, then checks identities again.
The supplement references the exact draw digest and preserves all planned
IDs. Eligible IDs and exclusions partition the plan, in planned order.
It records three-tier counts and distinct fine/coarse shape counts, not
effective sample sizes or policy outcomes.

| Status | Meaning |
|---|---|
| `gold_error` | Gold execution rejected, not policy failure. |
| `gold_timeout` | Configured deadline reached, not proof of nontermination. |
| `gold_truncated` | Configured row bound reached. |
| `db_missing` | Database availability/open failure; supplement blocked if post-identities remain valid, otherwise no publication. |

Complete with zero eligible tasks is unusable. `usable=true` means only that
completed gold validation left eligible tasks. It does not authorize an
experiment, authenticate weights or satisfy frontier/training gates.

Public fields never include question/evidence/gold text, absolute database
paths or raw scorer details. Task contents enter digests only.
`measurement=false`, `model_calls=0` and an explicit fixture declaration
separate preparation from model evidence. Fixture declaration is not proof
of origin.

## Publication and operating limits

Publication writes/fsyncs a private temporary file in the output directory,
then exclusively hard-links it to the final pathname. Existing files and
symlinks are never overwritten. Before-publication failure leaves no final
file. `PublicationIndeterminateError` means failure occurred after linking:
an intact document may exist. Inspect/recover; never automatically delete it
or retry assuming absence.

Require quiescent source/corpus/output directories and a fresh interpreter
after code edits. Databases must resolve inside the corpus database directory.
WAL/SHM/journal sidecars reject. Hashes stream in 1 MiB chunks and compare
file-descriptor/path metadata. Before/after checks detect ordinary drift,
not hostile change-and-restore or a guaranteed immutable SQLite snapshot.
Disk hashes do not authenticate already-loaded Python code.

Current source defaults are **30.0 seconds, 500,000 rows, set comparison**.
Only explicitly declared fixtures may use smaller bounds. Existing scorer
protections and soft limits are not hard process CPU/memory/wall-clock
containment. Row width, hashing, temporary IO and total duration remain
unbounded. Historical 100,000-row/multiset examples are not silently amended.

## Validation

Actual parent-run offline evidence:

- **239 passed in 9.84s**, three files: `bench/test_prepare.py`,
  `bench/test_bench.py`, `bench/test_score_queries.py`. This includes
  **98 new / 141 existing** cases, not a full-repository suite.
- **Three additional regressions passed in 0.08s**: real temporary database
  replacement between opening and stat, reversed real exclusions, and a
  same-ID/mismatched-content exclusion. Thus 101 new cases passed across
  separate runs, not one 242-case run. An interrupted joint rerun is excluded.
- The selector comparison exercised **100 seeds x 3 input orders**.
  Real fixture validation exercised 8/8 eligible, one broken gold with 7/8
  eligible, 2-row boundary, a 0.02-second recursive-gold timeout, source drift
  in copied trees, mid-validation drift/sidecars, strict decoding, isolation
  and atomic publication failures.
- Final fresh-interpreter controls: **3 baseline GREEN**; suppressing actual
  bad-gold exclusions gave **1 intended RED** (8 eligible instead of 7);
  bypassing identity equality gave **1 intended RED** after changing database
  bytes; replacing create-only publication with overwrite gave **1 intended
  RED**; **3 restored GREEN**. All were call-phase assertions/refusals.
  **14 source/test/spec hashes stayed unchanged** across the controls.
- Static security and final Python reviews approved. Reviewers used file
  inspection, not independent execution. Parent ran the tests and controls.

Actual SWE-2 High workers wrote the implementation/tests. Parent review
corrected the source identity map, exclusion admission/order, initial FD/path
comparison, freeze rechecks and endpoint source checks. Test-only fixes removed
an unsafe C-type monkeypatch and corrected source-map/invalid-status fixtures.
The first actual new-suite run had one invalid-status fixture failure
(95 passed); marking that injected outcome invalid allowed it to reach the
existing gold-validator rejection list. Production checks were not relaxed.

Local controls and exact bindings:
`~/scratch/co-train-2026-10-31/bench-preparation-8dc8d15/controls-receipt-final.json`.
Hashes detect content changes, not authenticity.

No real corpus, product-provider call, training, install/download or native
job ran. No such execution is authorized by this document.
