# Completion roadmap

Updated 2026-10-22. This is a research-software completion plan. A positive
scientific result is not a completion requirement.

## Current boundary

The repository has a working SQL execution instrument and offline training
components. `train.grpo_ptc.sql_environment(task)` now binds a fresh PTC
environment to a real task using the existing paired-arm implementation.
It is not a TRL rollout adapter.

Main co-training is still unimplemented after preflight. The actual
`--preflight-only` command still exits 1 because the frontier manifest is absent.
Historical v10 aborted after three steps; it is neither a completed five-step
probe nor a frozen-policy frontier measurement. See [v10](probe-v10.md).

## SQL safety and measurement repairs

The advertised read-only SQL-action and result-set scoring contracts are now
enforced. These repairs supersede the three open SQL/scoring/wrapper findings
recorded at `5bac4fc`.

| Check | Required behavior | Observed before repair |
| --- | --- | --- |
| SQL-action file access | Reject external file writes/reads through SQL while ordinary SELECTs still work | 36 failed, 24 controls passed |
| Result-set scoring | Reject comments and no-result PRAGMAs; retain genuine empty SELECT/CTE results | 27 failed, 7 controls passed |
| Scorer file access | Protect prediction and gold execution before any filesystem side effect | 8 failed, 2 controls passed |
| Timed-out sweep invocation | A late task cannot replace the next task's wrapper; clean up after actual completion | 3 failures, plus a separate error-cause failure |
| CLI error framing | Preserve the database message when option count changes its ordinal prefix | 12 failed, 3 controls passed |
| Package isolation | PTC imports without bench/frameworks; the real isolated bench mutation baseline passes | Standalone import failed; bench collection failed, then exposed one older training-dependent test |

`ptc.sqlite_safety.protect_connection` installs a shared stdlib authorizer before
untrusted SQL in both Python paths. It denies ATTACH, including VACUUM INTO,
and the named file/extension helpers; missing protection raises an infrastructure
error and closes the connection. The main database must still be opened with
`mode=ro`. The CLI requires `-safe` on both the count probe and final execution,
without an unsafe fallback. Unsupported SQLite CLI versions fail closed.
Neither path is an OS sandbox or restricts the wider bash shell, ordinary SQLite
temporary IO, or arbitrary future native functions.

The scorer checks SQLite result metadata rather than parsing SQL keywords.
No-result predictions become `pred_error`; no-result golds become invalid
`gold_error`. Empty queries and row-returning PRAGMAs retain their existing
behavior. Set/multiset comparison, limits, and invalid-gold reward mapping are
unchanged. Freeze this scorer version before future measurement.

Each watched sweep invocation owns its wrapper directory until the underlying
thread actually ends. Timeout and execution errors have separate causes.
Timed-out threads still are not cancelled.

The guard/standalone-import group passed 70 checks; scoring, training-reward
integration, and the real isolated bench baseline passed 48. Three integration
cases now live in `train/`, without dropping their assertions. Independent
runtime negative controls removed each Python integration and each CLI safe
flag separately: 20, 8, 2 and 2 checks failed respectively, with pytest exit 1,
not collection errors. Python/security source reviews closed both dependency
findings and approved the bounded repair.

The final default suite passed **1109 tests, with one optional torch test
skipped**, in 122.63 seconds. That is 136 more cases than `5bac4fc`. Offline
flags were set, but tokenizer tests used the existing cache; cold-cache
bootstrap remains open.

All 800 shipped golds also passed local protected execution at 30 seconds and
500,000 rows per query. This is scorer compatibility, not a new full-corpus
channel-parity measurement or proof of historical Kaggle bytes.
See [the validation record](../research/2026-10-22-sql-safety-golds.json)
and [the SQL boundary](harness-parity.md#9-sql-safety-repair-2026-10-22).

## Earlier regression-first hardening (`5bac4fc`)

Tests were added before production changes, and the parent process executed
the failures against the old implementation.

| Check | Required behavior | Observed before repair |
| --- | --- | --- |
| Frontier evidence | All measured IDs, rates, retained IDs, void reasons and existing provenance survive JSON; duplicate IDs cause zero sampling calls | 15 failures, including the selector checks below |
| Seeded selection | Identical ordered output for three corpus orders across 100 seeds, at both shape granularities | 100 differing seeds at each granularity |
| SQL target and tool arguments | Literal filenames resolve to the intended read-only database; malformed argument shapes return rejection data and allow retry | 26 failures, 13 controls passed |
| Training evidence and execution | Incomplete/nonfinite required telemetry cannot yield RUN PASS; real task execution has fresh state and refuses a ninth submission after eight | 192 failures, 6 controls passed |
| Mutation verification | Genuine test failures can kill mutants; collection/internal/usage/no-tests exits are invalid; both PTC and ledger sandboxes collect correctly | 36 failures, 31 controls passed |
| Manifest hard-link alias | Diagnostic output must reject a hard-linked manifest without changing either file's bytes | 1 failure |
| Registered training mutations | All 52 anchors match exactly once; execute the three repaired mutations against real fresh suites | 3 stale anchors; the new invariant failed |

After repair, the training/execution/mutation group passed 431 tests, the
SQL-boundary/frontier/bench group passed 167, and the frontier group including
the hard-link correction passed 32. These groups overlap; do not add their
counts. The final default suite passed **973 tests, with one optional torch
test skipped**. All three repaired registered mutants died; the remaining 49
were not rerun. Python/security source reviews approved this bounded patch.
See [HANDOFF](../HANDOFF.md).

## Interfaces now available

- `train.grpo_ptc.sql_environment(task)` returns the existing PTC arm prompt and
  a task-bound environment. Each call creates a fresh budget. Unbound execution
  still fails loudly; attempts consume the budget before dispatch, including
  executor errors. This does not register a tool with TRL or collect training
  log-probabilities.
- `ProbeResult.report()` preserves every existing dataclass field.
  `bench.frontier.probe.write_report(result, path)` requires an explicit
  diagnostic destination and refuses canonical-manifest aliases, including
  symlinks and existing hard links. It does not call `manifest()` or authorize
  training. Model revisions, corpus hashes and sampling settings not already
  stored in `ProbeResult` are still absent.
- Mutation runners distinguish invalid verification from killed mutants.
  PTC's existing watchdog exit 124 remains an explicitly labelled timeout
  kill; exit 124 is invalid in the other two runners.
- SQL connections encode literal paths before adding `mode=ro`. The catalog's
  print observer no longer imports the framework harness. Valid JSON with an
  invalid argument shape becomes rejection data instead of a rollout crash.
- Required run telemetry preserves logged-row positions. Missing/nonfinite
  observations cannot reset A into a pass or compress B into a consecutive
  window. Optional short-probe B remains informational. The five-step probe
  minimum, ten-step window, 0.60 ceiling, 3.0 multiplier and nonpositive-baseline
  policy are unchanged.

Canonical bucket traversal makes future seeded selection independent of corpus
input order. It can change a newly generated selection relative to the old
algorithm. The 800 shipped prompt files were not regenerated; record and freeze
actual IDs rather than assuming an old seed identifies the same draw.

## Blocking findings still open

1. **Sweep timeouts still leave work alive.** Wrapper isolation fixes the
   reproduced wrong-database race, not cancellation. A daemon can retain CPU
   and its private directory until the query finishes or the process exits.
2. **Mutation subprocess lifetime is incompletely bounded.** Step2/train lack
   subprocess timeouts; PTC descendant cleanup also needs a bounded regression.
   Outcome classification does not repair process lifetime.
3. **The default suite is not cold-cache offline.** With fresh temporary HF
   caches and offline flags, both tokenizer-backed contamination controls
   failed with `LocalEntryNotFoundError`/`OSError`. Warm-cache green does not
   establish a reproducible bootstrap. A complete development dependency
   contract and explicit tokenizer-integration path remain to be chosen.
4. **Invalid-gold reward policy remains unresolved.** The reward still maps
   invalid golds to zero. Result-set validation does not decide whether future
   training should void or mask those tasks.

These findings block an experiment-ready claim. No new GPU job or paid call is
needed to reproduce them.

## Completion order and acceptance checks

### 1. Close remaining process and bootstrap gaps

Bound timed-out work and mutation descendants; choose a reproducible tokenizer
integration path. Resolve invalid-gold void/masking policy separately from the
completed SQL-action and result-set repairs. Preserve the failing controls and
valid-query parity tests. Do not silently repair the eight historical channel
divergences.

### 2. Freeze the measurement contract

Record the exact model/revision, intended action channel, group size, candidate
IDs, corpus identity, sampling settings, scorer version and evaluation
membership before generation. G=4 in the specification and G=8 in historical
v10 are not interchangeable. Save taskwise diagnostic evidence, not just an
aggregate manifest.

Approve the manifest contract separately. The active guard does not enforce
all fields suggested by the dormant measurement helper. Do not activate that
whole helper: it contains an unsigned retention floor. Do not assume the
existing nonempty policy field binds a manifest to the training model.

### 3. Complete the actual training path

Verify the operative patched TRL source and compatible framework versions
before selecting the integration route. Then connect task-bound execution to
generation, exact token/log-probability alignment, environment masking, reward,
step limits and checkpointing. The current model metadata/reward mismatch and
unused CLI step setting also need correction.

Acceptance requires a real optimizer/checkpoint smoke test on approved
hardware, complete metrics, and zero reachable placeholders in that workflow.
A mocked trainer constructor or successful preflight is insufficient.

### 4. Produce authorized frontier evidence

Measure frozen-policy taskwise rates in the intended channel. Preserve every
candidate, measured/void outcome and retained identity, with the frozen
provenance. Audit manifest consistency before allowing it to open the gate.
If the taskset is outside the model's frontier, report that result.

### 5. Complete the scientific comparison

Evaluate base, PTC-trained and bash-trained policies under both evaluation
harnesses: six cells. Report paired outcomes, uncertainty, token/dollar costs,
contamination limits and channel divergences. A null or inconclusive result
can complete the research.

BIRD remains admitted for H3/H4/H5, not N1. H1 is closed; do not revive H2.
The checked arithmetic and literature boundaries are in the
[continuation review](../research/2026-10-22-continuation-review.md).

## Non-goals of this hardening slice

No framework upgrade or rollout integration, new dependencies, GPU job, paid
endpoint, criterion/amendment/signature change, frontier authorization, public
release, push, or SaaS repositioning.
