# Incremental SQL/PTC execution capture

2026-10-24. Implemented and targeted-test verified, including extraction-work
admission. Independent controls passed and Python re-review closed the P2.
The completed full default suite is RED on an unresolved existing isolated bench
baseline blocker. This document does not open the native-training gate.

## Purpose and evidence boundary

Allow a trusted caller to submit program B after reading actual observation A.
Capture the existing SQL/PTC execution seam, not a predeclared complete script.
Finishing scores only the submitted final SQL. It never replays program actions.

The capture proves which trusted programs were submitted and which observations
this local instrument returned. It does not establish model authorship, exact
provider messages, tokens, logprobs, learning, strategy quality, or secure execution.
Fixture gold answers are test-oracle inputs, never model-prompt inputs.
`EpisodeIds` are caller declarations, not authenticated identities. An artifact
SHA-256 detects corruption, not forgery.

## Test plan, before implementation plan

`train/test_sql_capture.py` is the acceptance suite. Missing API imports happen
inside tests, not during collection. Existing tests remain unchanged.

| Check | Numeric pass criterion |
|---|---|
| Reactive execution | All committed fixture tasks, at least 8, each complete 2 real SQLite/PTC steps; step 2 incorporates observation 1; exactly 2 backend dispatches per task; final EX is 1. |
| Prompt and observations | Captured prompt and both observations equal direct `sql_environment(task)` UTF-8 bytes on every fixture task; 0 gold-only sentinels, scoring metadata, or capture metadata added to prompt. |
| Budget | Exactly 8 dispatches accepted per session; ninth and tenth attempts produce the existing refusal with 0 extra dispatches; 8 executed records and 2 separate refusal records; final SQL spends 0 actions. |
| Final scoring | Correct, wrong, empty, malformed, and fenced finals preserve all 6 existing `ExResult` fields, including invalid-gold `valid=False`; abort has 0 scorer calls and no result. Finish/encode/decode/rescore dispatch 0 actions. |
| Binding | Every caller ID and non-mount task field, DB-byte mutation, WAL/journal/SHM sidecar, canonical prompt, selected source, and instrument-setting mismatch rejects before the next action or scorer call. Recomputing the artifact digest does not bypass those external checks. |
| Lifecycle | Finished, aborted, and invalidated sessions permit 0 later step/finish successes; independent sessions have distinct budgets. Unexpected executor/scorer exceptions propagate and permit 0 later successful finals. |
| Format | Frozen dataclasses and tuples round-trip to identical canonical UTF-8 bytes. Decode builds 0 environments, dispatches 0 actions, and makes 0 scorer calls. Duplicate/unknown keys, versions, wrong types, nonfinites, and evidence over 8 MiB all reject. Oversized inputs/observations fail loudly, never truncate. |
| Compatibility | Existing scripted v1 origin `scripted` / terminal `scripted_final` unchanged. Native discovery still exposes exactly 1 tool, `run_program`; capture/finish/abort are not native tools. |

### Extraction-work repair test plan, before implementation

Independent Python review found quadratic prefix scanning in the unchanged
shared extractor. Two million quoted semicolons fit the 8 MiB capture envelope
but can cause roughly two trillion prefix characters of completeness checks,
outside the SQL query timeout. Repair only capture admission, not the frozen
scorer/extractor.

Before either capture extraction call, compute a conservative byte-work proxy:
`W = len(text.encode("utf-8")) + sum(pos + 1 for each raw semicolon byte position)`.
Admit `W <= 64 * 1024 * 1024`; reject above it incrementally, before the shared
extractor. This is a 64 MiB cumulative-prefix-work budget per extraction call,
not a whole-operation CPU/memory guarantee. The 8 MiB encoded-format cap stays
independent. Raw counting includes quoted/comment semicolons, discarded prose,
fences and text after an early complete statement, so some cheap-to-extract
texts can conservatively reject. Admitted extraction semantics stay unchanged.

Tests first: bare/tagged/prose 2,000,000-semicolon payloads with recomputed valid
digests must raise work-limit `ValueError` with 0 extractor/scorer/dispatch calls.
Constructor, encode, finish and rescore must all reject before extraction;
finish must invalidate. Stubbed extraction tests admit exactly 64 MiB proxy
work, reject +1 byte, and distinguish UTF-8 bytes from characters. Real
ordinary/fenced/quoted/comment/large-no-semicolon cases retain existing output.
After GREEN, run a real-extractor attack decode in a fresh sandboxed child under
a 10-second parent kill/reap deadline. Independently bypass each of the two
capture guards in memory; require real sentry assertion failures in fresh
pytest processes, never execute the old unbounded attack extractor.

### Required independent negative controls, after GREEN

Executed independently before the extraction repair: 5 baseline passes, then
DB/budget/replay/sealed controls caused 1/1/1/2 real assertion failures.
The fresh processes mutated code in memory, not the working repository, and
retained on-disk source bindings. The requirements below remain the rerun
contract: never reuse a warm imported module or count import/syntax errors or
unrelated source-binding rejection as a killed mutant. Require at least 1 actual
assertion failure per mutant:

1. Remove DB-content binding while leaving source binding intact.
   `test_changed_database_rejected_before_next_operation` must fail.
2. Bypass pre-dispatch `TurnBudget` enforcement.
   `test_eight_dispatches_then_separate_refusals` must fail.
3. Replay recorded actions inside `finish`.
   `test_reactive_capture_matches_direct_environment_for_all_tasks` must fail
   its exact dispatch count.
4. Permit `step` or `finish` after a sealed terminal.
   `test_terminal_sessions_reject_later_calls` must fail.

Any temporary-copy runner must account for source fingerprints so a mutant is
tested against artifacts created by that same mutant. A binding rejection caused
only by stale artifacts is not evidence that the intended assertion works.
Parent receipts are `validator-mutation-*.log`; the raw budget/replay traces show
rewritten `assert` failures even though their original string-based reporter
counted zero. No existing runtime controls were repeated for this local guard fix.

### Execution gate

No dependency installation, paid calls, model downloads, GPU use, or training.
Repository-local virtualenvs are absent; system Python 3.15 is unsuitable.
Validation used the existing read-only reference interpreter
`/Users/nikolassapalidis/Developer/misc/co-train/.venv-ptc/bin/python`,
Python 3.12.13 with pytest 9.1.1. No reference source was edited. The actual
repository remained `/Users/nikolassapalidis/Developer/co-train`.

Run with a verified existing interpreter and the real offline harness described in
[offline harness reliability](offline-harness-reliability.md), not bare pytest
as a substitute for network/cache auditing. The harness receives these pytest
arguments:

```sh
-q -ra --tb=short -o faulthandler_timeout=60 train/test_sql_capture.py
```

Observed initial RED: **252 failures in 4.09s**, pytest exit 1. All 252 named
missing `train.sql_capture` from test bodies (`ModuleNotFoundError` handled by
`pytest.fail`); no collection/environment errors. Production followed that RED.
Focused GREEN: **252 passed in 13.39s**, exit 0. Combined GREEN:
**570 passed in 41.10s**, exit 0, across capture plus
`test_sql_episodes.py`, `test_sql_bridge.py`, `test_execution_binding.py`,
and `test_sql_reward_queries.py` in `train/`. No skips.

All three runs used fresh caches, bytecode/pytest-cache disabled, inherited OS
external-network denial and the reviewed native observer. Each recorded zero
network attempts, cache accesses, tokenizer loads, and loopback events in the
pytest audit. These are not arbitrary-child/native telemetry. Logs:
`capture-red-01.log`, `capture-green-01.log`, `capture-combined-01.log` under the
session's `co-train-capture-2026-10-24` scratch directory. The selection discrepancy
is resolved: `test_learning_lab.py` has 4 cases versus the 3 reward-query cases.
The independent exact-original scope passed **571 in 157.49s**, exit 0,
in `validator-exact-baseline-plus-capture-01.log`. No test was lost.

Extraction repair receipts:

* RED: **17 failed, 7 passed, 252 deselected in 31.02s**, exit 1. Fifteen
  failures were extractor sentry assertions; two were missing +1-byte rejection.
  The unbounded attack extractor was never run.
* GREEN: **24 passed, 252 deselected in 6.50s**, exit 0.
* Current exact legacy + capture scope: **595 passed in 149.43s**, exit 0,
  no skips, including 276 capture and 319 legacy cases. Legacy modules are
  `train/test_sql_episodes.py`, `train/test_sql_bridge.py`,
  `train/test_execution_binding.py`, and `train/test_learning_lab.py`.
* Fresh-process real-code attack: legitimate-digest 4,003,379-byte envelope
  with 2,000,000 quoted semicolons rejected with work-limit `ValueError`;
  decode 0.01664s, normal child exit 0, parent 0.31109s, under its 10-second
  kill/reap deadline. The external pytest probe passed in 1.59s.
* Independent in-memory bypasses of validation and finish guards: baseline
  2 passed (1.68s); each mutant caused 1 extractor-sentry assertion failure
  (1.86s / 2.35s), pytest exit 1. No syntax/import/digest/binding failure.

New logs have prefix `capture-extraction-`: `red-01.log`, `green-01.log`,
`combined-01.log`, `probe-01.log`, and
`control-{baseline,validation,finish}-01.log`. Every new harness run recorded
zero network/cache/tokenizer audit violations and zero loopback events.
Probe counters cover the parent pytest process, not arbitrary child telemetry;
the fresh child inherited the separately verified OS sandbox.

General/security reviews reported no actionable issues. Fresh Python static
re-review closed the extraction P2, checking both guarded sites, all entrypoints,
tests and docs; no new findings remained.

The final independent full default offline run completed all **2,224 selected
tests in 38 modules**: **2,222 passed, 1 failed, 1 skipped, 2 deselected in
428.41s**, exit **1**. All 276 capture cases (including all 24 extraction checks)
and 319 exact legacy cases passed independently. The skip is optional torch
unavailable; the two deselections are configured tokenizer integration controls.
The real offline harness received `-q -ra --tb=short -o faulthandler_timeout=60`
with no path selection, `-x`, retries, timer changes or additional deselection.
Audit counts: external network/cache/tokenizer **0/0/0**, permitted loopback **5**.
Parent/child OS network-denial and five audit-guard RED controls were verified
earlier; counters are not arbitrary-child/native telemetry.

Unresolved failure:
`tests/test_mutation_harness.py::test_ptc_real_isolated_baseline_collects_and_passes[bench]`,
line 165, nested bench exit 1 instead of 0 (**2 failed, 509 passed, 1 skipped,
2 deselected in 38.30s**). Retained inner detail names
`bench/test_sql_parity_sweep.py::test_interruption_cleans_owned_work_and_propagates`;
the other inner failure detail was abbreviated and is unavailable.
Isolated baselines copy `ptc`/`ledger`/`bench`, not `train`, so are independent
of new capture code. Direct outer parity cases passed. Earlier investigation
hit the existing 0.1s startup PID-readiness fixture: a candidate 0.5s change passed
isolated, but broader file timers failed. All candidate edits were reverted;
the parity test, production legacy files and guards remain unchanged.
Investigation ended with all 17 probe PIDs absent. This remains a baseline
infrastructure blocker, not a proven production cleanup defect or full acceptance.

Optional local provenance under the scratch directory above:
`validator-final-full-default-01.log`, `validator-final-default-collection-01.log`,
`validator-final-integrity-after-01.log`. Integrity found no changes in
44 repository / 4,878 reference bytecodes or 23 repository / 10 reference source
fingerprints; all eight authored artifacts were nonempty.

## API and immutable evidence

New module: `train/sql_capture.py`. No new dependencies.

```python
start_capture(task: SqlTask, *, ids: EpisodeIds, allow_execution=False)
session.prompt: str
session.step(code: str) -> str
session.finish(final_answer: str) -> SqlCapture
session.abort() -> SqlCapture
encode_capture(capture: SqlCapture) -> bytes
decode_capture(data: bytes) -> SqlCapture
rescore_capture(capture: SqlCapture, task: SqlTask, *, ids: EpisodeIds) -> ExResult
```

`start_capture` requires `allow_execution is True`. Truthy substitutes reject.
Session methods are trusted host APIs; do not pass the session into native TRL
method discovery or append its methods to a tool schema.

`SqlCapture` is a distinct frozen record. Reuse `EpisodeIds`,
`ActionObservation`, `InstrumentSettings`, and existing `ExResult`. Fields:

* `schema_version=1`, `origin="incremental_execution"`, `arm="ptc"`;
* `ids`, `task_id`, `task_fingerprint`, `db_sha256`, `schema`, `prompt`,
  `backend`, `instrument`;
* `steps: tuple[ActionObservation, ...]`, dispatched submissions only;
* `refusals: tuple[ActionObservation, ...]`, budget refusals only, after 8
  dispatched submissions. A program returning `rejected: ...` still dispatched,
  so it belongs to `steps`, not `refusals`;
* `terminal_label`, either `final_submitted` or `aborted`;
* `final_answer`, `extracted_sql`, `result`, all `None` when aborted.
  A submitted empty string is a real final and preserves the scorer's outcome.

The canonical JSON envelope has exactly `format="sql_execution_capture"`,
`schema_version=1`, `payload`, and `sha256`. Payload is the record's dataclass
representation, including its own schema version. The digest is SHA-256 of
canonical payload bytes. Canonical means sorted keys, compact separators,
unescaped UTF-8, and nonfinite numbers forbidden. Bound both input and canonical
envelope to 8 * 1024 * 1024 bytes. Validate every record layer and lifecycle
invariant; reject booleans where integers/numbers are required. Do not deserialize
code, pickle, callables, or mutable containers into evidence.

## Lifecycle and validation

`start -> active -> final_submitted | aborted`; validation, oversized evidence,
or unexpected execution/scoring failure takes active to invalidated instead.
Terminal and invalidated sessions reject later `step`, `finish`, and `abort`
with `RuntimeError`. A refusal is an observation, not terminal completion.
Finalizing twice is an error, not an idempotent second score.

Start captures the canonical `train.grpo_ptc.sql_environment(task)` prompt and a
fresh task-bound `PTCEnvironment`. Each admitted step invokes that environment's
`step` exactly once, preserving its pre-dispatch budget and observation text.
No reconstruction of an action sequence through `record_scripted`.

Before every later step and every final scoring/rescoring operation, validate
the caller declarations, all task metadata except the relocatable DB mount path,
stable DB bytes with no sidecars, current schema/backend/canonical prompt,
selected source bytes, and runtime/scorer/action settings. Reuse stable DB and
protected scorer helpers from `sql_episodes`; do not duplicate a weaker checker.
Check DB stability again after execution and scoring. Snapshot caller declarations
and task metadata rather than trusting a retained reference as its own baseline.

Selected-source coverage must include all existing scripted-instrument sources
plus `train/sql_capture.py`, `train/sql_episodes.py`, `train/grpo_ptc.py`,
`train/guards.py`, and `bench/task.py`. The actual environment and budget owners
must be bound, not only historical scorer/runtime paths. These are selected
on-disk audit bindings, not an SBOM or in-memory-code attestation.

Finish extracts with `bench.score.extract_sql`, calls the protected existing
scorer once, checks stability, and seals only after evidence validation/size
checks succeed. Preserve invalid gold as invalid evidence, never a usable zero.
Abort seals without scoring; rescore rejects aborted captures without scoring.
Decode validates data only. Rescore may execute protected final/gold SQL, never
recorded actions. No replay API is added.

This requires a stable caller-owned DB snapshot. It does not prevent malicious
concurrent ABA writes or provide filesystem snapshot isolation. Trusted PTC
programs run through the existing restricted runtime, which is not an OS sandbox.

## Implementation sequence and remaining acceptance

1. Implemented only the new capture module, reusing current records, DB/scorer
   helpers, canonical environment, and the existing budget. Old APIs unchanged.
2. Implemented strict distinct serialization and current-environment bindings.
   A per-session lock serializes host submissions; it is not crash recovery.
3. Focused and exact legacy regressions passed as recorded above, including the
   extraction guard, independent guard bypasses and fresh-process attack probe.
   General/security/Python re-review and the original four controls are complete.
   The full default run completed RED on the existing isolated bench baseline;
   resolving that infrastructure blocker and full offline acceptance remain open.
4. Training README, roadmap, research status, and HANDOFF record those actual
   outcomes and limits. Parent owns review, final acceptance, and git boundary.

## Non-goals

No bash capture, provider adapter/traces, live LLMs, training, GPU use,
dependencies, generated/promoted skills, adaptive retrieval, automatic retries,
general orchestrator, crash recovery, exactly-once effects, prompt/tool-schema
changes, protocol membership changes, gold-policy changes, or scientific-manifest
changes. Incremental fixture execution is not token-faithful model capture.
