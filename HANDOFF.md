# Current feature checkpoint, 2026-10-30: PTC launch reporting

The follow-on to `1ded101` adds constructor-only `qa_factory` to the real
`PTCHarness.launch` route. Each launch gets a caller-owned channel; local/MCP
report-tool collisions and live-channel reuse on one harness refuse explicitly.
Tracking is weak and the registered model tool remains only `run_program`.
See [launch usage](docs/2026-10-30-agent-defect-escalation.md#opt-in-through-ptcharnesslaunch)
and the [test-first contract](spec/agent-defect-escalation-harness.md).

Stage 4 remains PARTIAL. CLI/config activation, production bash routing,
isolated reporting, sealed capture binding and TRL integration are unfinished.
Priority stays 4 -> 5 -> 6. No experiment/spending authority is added; historical
pins and native receipts are not reissued. Prior checkpoints follow unchanged.

---

# Current feature checkpoint, 2026-10-30: stage 4 reporting

This checkpoint supersedes the older “complete structured reporting” gap below.
The entire prior HANDOFF body follows unchanged as dated history.

- Stage 4 stays PARTIAL: opt-in in-process PTC catalog and actual shell-runner
  structured reporting now work, with a controlled real-SQLite shortcut fixture.
  See [usage, bounds and evidence](docs/2026-10-30-agent-defect-escalation.md)
  and [opt-in parity](docs/harness-parity.md#opt-in-defect-reporting-2026-10-30).
- Parent-recorded validation: 848 targeted passes, no skips; 639 keyword
  deselections in the selected isolation/SDK run. Two in-memory controls went
  RED and restored GREEN. No post-feature full suite; older 3,803-pass evidence
  is earlier source. This docs worker reran no tests.
- Next: production verifiers bash routing, isolated-wire reporting and
  capture/SqlEpisode configuration binding, then TRL integration before live
  experiments. Reports are untrusted allegations; shell markers are forgeable.
- Priority remains 4 -> 5 -> 6. Current BIRD paired baseline remains absent;
  stage 6 is blocked. SQL-native acceptance is not a stage 4 prerequisite.
- Base HEAD is `91336c8`; changed `ptc/sql_arms.py` bytes make historical pins
  stale. Do not repin/replay receipts. No new experiment or spending authority.

---

# Current project priorities, 2026-10-30

## Original research milestones: 4 -> 5 -> 6

The [current research milestone table](README.md#current-research-milestones-4-6)
replaces the historical “not started” rows as current status. Original stage
numbering and old verdicts remain historical evidence. Recent SQL reuse and
acceptance work was scope drift relative to this sequence, not its completion.

| Stage | Status | Next required work |
|---|---|---|
| 4: environment + escalation | **PARTIAL.** Runtime, independent scoring and isolation pieces exist. | Complete structured agent defect reporting/verifier-QA and test its route plus one instrumented rule-legal shortcut's deterministic telemetry. Signal/process cleanup escalation is not this feature. |
| 5: paired untrained harness baseline | **PARTIAL.** Both bash/PTC harnesses exist; the retired `ledger` premise check ran and the published gap did not reproduce. | Measure the current-taskset paired baseline with matched information/tools/budgets/metric, complete planned-task denominator, error categories and gold validity. Preserve the original preregistered negative result. |
| 6: co-training and harness swap | **BLOCKED, not complete.** Frontier manifest absent; native main CLI still refuses after preflight. | Satisfy legitimate frontier, stack and CLI gates before preregistered training/cross-harness evaluation. MLX sampling/updates are real partial work, not completed holdout/three-seed/harness-swap proof. |

See [harness parity](docs/harness-parity.md),
[untrained results](docs/results-untrained.md), [frontier measurement source](bench/frontier/probe.py)
and [native training constraints](spec/native-training.md). No preflight,
dependency probe or experiment was executed for this status correction.
Frontier measurement is stage 5 baseline preparation, not a reason to defer
stage 4 channel work.

The published code checkpoint used for this review is
`1501f0b62d0979e03aeec11d8b95363132e87eae`. The earlier
[19-job direct-evaluator](docs/2026-10-29-bounded-native-acceptance.md) and
[15-job SDK](docs/2026-10-29-native-sql-skill-workflow.md) native proofs remain
valid bounded historical evidence, with consumed permissions. The portable
helper's [recorded offline proof](docs/2026-10-30-portable-sql-skill-sdk-acceptance.md)
is separate; its native phases remain NOT_EXECUTED. Further SQL-native acceptance
is optional/off-critical-path and must not become an artificial stage 4 gate.
These engineering receipts do not establish full adversarial/kernel coverage
or original research milestone completion.

Preflight-only context preparation may exist outside checkout; it is not a
native campaign or new execution authority. This docs-only update grants no
native/model/training spend. Future work uses its applicable authorization;
paid trials need an explicit budget, not agent-session usage. No learned
benefit, economic savings or traction is established.

Everything below is the complete pre-update HANDOFF body, retained byte-for-byte.
Its dated current-state labels, profile-preparation statements and old “not
started” rows describe their recorded sessions, not this priority ordering.

---

# Current handoff, 2026-10-30

## Current state, closed-fixture portable SQL skill SDK offline acceptance

Read the [portable SDK verification receipt](docs/2026-10-30-portable-sql-skill-sdk-acceptance.md)
and [usage/contract guide](spec/sql-skill-sdk-acceptance.md). This section
supersedes earlier current-state checkpoints; the full original HANDOFF follows
byte-for-byte below.

- Final closed-fixture offline acceptance: 3,803 passed, zero failed, one optional
  missing-Torch skip, two existing tokenizer deselections, ten warnings and
  28 subtests; exit 0 in 741.59s. All 3,794 prior selected IDs retained, plus ten
  new default offline guards. All 268 bound files stayed frozen during that
  full run. This five-doc refresh is separately checked, not another full run.
- Independent 30 probes passed, including real non-native SQLite/file SDK source
  EX=0, four qualifications and one reuse EX=1. Seven real fixture tasks had
  raw FD delta 0, seven explicit closes and zero live connection weakrefs before
  GC, which was forbidden until after assertions (recorded FD baseline 11).
  Five call-phase REDs each restored ten guards GREEN. Counts are not additive.
- Portable-owned `_fixture_task` closes the SQLite connection before return;
  legacy `_task` is unchanged. Legacy-alias RED retained one FD before cleanup,
  not a demonstrated old native failure. Capture-dependency union including
  `train/grpo_ptc.py` remains guarded. Final Python/security reviews approved.
- Validation used base HEAD `c1dfb85476f77e817ec57adb3b015a74b690b816` with the
  two code files then uncommitted. Exact validated code/evidence hashes are in
  the linked receipt.
  After this refresh only five doc hashes change from the 268-file snapshot;
  263 other files, both code pins, 31 controller sources, 16 native-role files
  and four protected paths remain unchanged. Earlier 3,802/29/four-control
  proof is retained as pre-fixture-close history, not current-byte acceptance.
- Native qualification and both fresh-interpreter reuses: NOT_EXECUTED.
  Parent owns integrated-commit review, commit/push and later fresh 15-job
  authorization. No profile, consent, permission or claims created here.
  Before profile/consent and each phase, operator must externally compare actual
  HEAD and reviewed source pins. CLI `reviewed_revision` is format-only;
  file/profile pins are checked. Strict raw FD/thread equality must pass without
  forced GC; separate settled measurements belong to offline validation only.
- Caller collects approved unrelated configuration and PREMOVE inode/mode/mtime
  evidence outside the CLI; helper scope is IDs/state and DB hash/path/move
  proof, not all-host/private-workload clearance. Missing context fails, never
  skips. Consumed 15/19-job native authority cannot be replayed; old scratch-helper
  native success remains legitimate separate bounded evidence.
- New receipt records one resolved scratch pre-collection tuple/list comparison
  incident, not zero incidents. No new native/provider/model or infrastructure
  work. Two source-generation jobs are outside SDK Timer callbacks. No model,
  economic, customer or team-hour benefit; existing financial/traction gates
  and standing Git instructions remain unchanged.

---

# HANDOFF — model-harness co-training

**The first current-state section supersedes every earlier checkpoint below.**
Historical receipts, including non-green runs, are retained rather than rewritten.
The original body remains under [History](#history).

---

## Current state, 2026-10-29, bounded native file-SDK and Timer acceptance

Read the [native SDK workflow receipt](docs/2026-10-29-native-sql-skill-workflow.md).

- Actual file-SDK qualification and two fresh-process reuses passed natively:
  four qualifications/two reuses valid EX=1; source and SDK rescore valid EX=0.
  Separate caller review/pins preceded reuse, not automatic promotion approval.
  This is caller-authored fixture trust, not authenticated customer permission.
- New campaign: 15/15 CLOSED jobs (7 PROGRAM, 8 SCORER), matching finalization
  pairs, zero retries/model calls/incidents. Both phase-native and postproof
  processes exited 0. Wrong promotion pin dispatched nothing.
- All 15 owned containers and 75 recorded actors absent; zero active reservations
  or unclosed blocks. Owned containers deleted normally, five historical DBs
  moved/preserved before reuse, ten unrelated containers unchanged. VM left up.
- Actual synchronous SDK Timer spans include writes/rename/fsync, but exclude
  source generation, bootstrap, fixtures, approval and observation finalization.
  No baseline/speedup, billing, model benefit or team-hours claim follows.
- Production unchanged: 142 Python sources/16 native-role files match HEAD.
  Prior 3,793-pass offline suite, 28 probes and three controls remain separate
  completed evidence; older direct-evaluator/native receipts below are unchanged.
- Bounded native SDK happy path is now covered. Full adversarial OOM/timeout/
  guardian/kernel acceptance and economic/model benefit remain unproved.
  Fresh native budget exhausted; financial gates closed. This receipt grants
  no further native/paid/model/deployment permission; standing Git instructions
  remain unchanged.

---

## Current state, 2026-10-29, qualification evidence, timing and bounded native lifecycle

Read the [qualification receipt](docs/2026-10-29-sql-qualification-evidence.md),
[outer timing receipt](docs/2026-10-29-sql-reuse-timing.md) and
[bounded native receipt](docs/2026-10-29-bounded-native-acceptance.md).

- Final independent offline acceptance: 3,793 passed, zero failed, one optional
  missing-Torch skip, two configured tokenizer deselections, ten warnings,
  28 passing subtests, exit 0 in 725.24s. All 260 source bindings unchanged
  before this docs-only integration. Independent probes: 28/28; three intended
  assertion RED controls and restored GREEN. Counts overlap, never add them.
- Qualification preserves completed ordered captures on ordinary exceptions.
  Post-rename final fsync can leave a visible UNAPPROVED promotion with unknown
  durability; successful return and external review/pins are still required.
- Timing includes synchronous callback writes/fsync and failed setup. Callback
  and setup completeness are caller trust. Scenarios are not adoption forecasts;
  model/provider/customer/team end-to-end time and economics remain unproved.
- Retained history: interruption, then 3,792 passed/one isolated-bench failure.
  The unchanged SDK test moved to train (all 11 assertions retained), leaving
  19 pure bench tests. Corrected full pass follows; no test was removed.
- Separately completed direct-evaluator native trial: three tests, 19 CLOSED
  jobs (10 PROGRAM, 9 SCORER), four qualifications/two fresh reuses EX=1,
  zero model calls/retries. Owned containers deleted normally; five historical
  DBs preserved at moved paths; ten unrelated containers unchanged.
- Native SDK/full adversarial guardian acceptance and model/economic/team
  benefit remain unproved. See [reuse economics research](research/2026-10-29-team-reuse-economics.md).
  Financial gate stays closed; consumed permissions and separate standing Git
  instructions remain unchanged. Historical receipts below are preserved.

---

## Current state, 2026-10-29, read-only SQL capture comparison

Read the [comparison receipt](docs/2026-10-29-sql-capture-comparison.md).

- Typed comparison retains every independently planned case, including missing
  both arms. Missing, malformed, blocked-read, invalid-gold and infrastructure
  outcomes stay distinct; incomplete coverage or incompatible bindings withhold
  aggregates. Complete admissible pairs use unchanged `paired(treatment, baseline)`.
  No DB opening, fresh execution, scoring, writes or network during analysis.
- Final corrected-byte offline suite: 3,765 passed, one optional missing-Torch
  skip, two configured tokenizer deselections, 10 warnings, exit 0 in 768.39s.
  All 3,718 previous SDK selected IDs retained, plus 48 comparison cases.
  Comparison 48/48 and focused 1,036/1,036 passed twice; counts overlap.
  Two independent mutants fail intended assertions with green baselines/restores.
- Security review's blocked-read misclassification fixed after RED (2 fail,
  46 pass), then GREEN (48 pass). Python/security re-review closed; general
  review clean. Separate Devin CLI SWE-2 High static challenge found no issues;
  it did not execute tests and is not runtime validation.
- Illustrative six-pair test: baseline 4/6, treatment 3/6, delta -1/6,
  CI [-2/3,1/3], p=1. No model benefit, significance or savings claim.
  Billing, tokens, request latency and approved-reuse attribution unavailable;
  caller arm declarations are not authenticated provenance.
- Existing estimator/evaluator/runtime/budget/scorer unchanged. Native/kernel/
  guardian acceptance and model benefit remain unproved. Financial gate stays
  closed; consumed permissions and existing native/paid/push gates still apply.

---

## Current state, 2026-10-29, caller-owned SQL skill SDK

Read the [SDK verification receipt](docs/2026-10-29-sql-skill-workflow.md).
The earlier same-date demo receipt below remains unchanged.

- Typed file SDK adds candidate creation, qualification and separately approved
  reuse around existing APIs. Canonical artifacts use exclusive new directories
  outside checkout. Qualification receipts are UNAPPROVED; callers supply trusted
  assets, external pins and exact approval IDs. Execution defaults to disabled;
  caller-selected executor passes through unchanged.
- Independent complete default offline suite: 3,717 passed, one optional
  missing-Torch skip, two existing tokenizer deselections, exit 0 in 754.08s.
  All previous 3,683 selected IDs retained, plus 35 SDK cases. Focused checks:
  35/35 workflow and 719/719 combined; counts overlap, never add them.
- Two real SQLite test families: 8/8 qualifications and 4/4 reuses EX=1.
  Separate-process reuse: 2/2 EX=1 with five old DB paths unavailable.
  Wrong approval dispatches zero programs/scorers; second-qualification failure
  retains scores [1,0] after two submissions, with no promotion.
  Two mutation baselines pass; both mutants fail intended assertions.
- Python/security/general reviews found no actionable issues. Production
  evaluator/defaults/runtime and four protected budget/scorer files unchanged.
  No offline product failure reproduced. Native/container/guardian acceptance
  and model benefit remain unproved; SDK qualification is not trusted approval.
- Financial gate remains closed, prior one-shot permissions consumed. Existing
  native-trial, paid/model-call and push/deployment gates remain in force.

---

## Current state, 2026-10-29, portable offline SQL reuse

Read the [demo and verification receipt](docs/2026-10-29-sql-reuse-demo.md)
for the root-directory run command, local evidence and acceptance limits.

- Portable standard-library demo: caller-authored SQL program, four EX=1
  qualifications, then two distinct fresh-process EX=1 reuses after the five
  source/qualification DB paths become unavailable. Wrong promotion pin
  dispatches nothing. Independent system-Python execution passed twice.
- Complete configured offline suite: 3,682 passed, one optional missing-Torch
  skip, two existing tokenizer deselections, exit 0 in 702.86s. All original
  678 runtime IDs retained; now 701 runtime cases and 299 skills/demo cases.
  Independent Python/general/security static reviews found no actionable issues.
- Four passing controls became intended assertion failures under separate
  pin/admission/drain/digest mutations. Offline process/IPC fixtures use
  synthetic container metadata; no production defect was reproduced.
  Production and protected budget/scorer files remain unchanged.
- No new native/container/kernel acceptance or full guardian recovery proof.
  No automatic model discovery, learning/scientific benefit or independently
  authenticated approval was demonstrated. Original receipts are local scratch,
  not portable evidence; the runnable fixture demo itself is portable.
- Financial gate stays closed; earlier one-shot permissions remain consumed.
  No new native trial, model call, push or deployment is authorized by this
  checkpoint or by autonomous-team instructions.

---

## Current state, 2026-10-28, offline maintenance

Read the [maintenance receipt](docs/2026-10-27-maintenance.md) for executed
checks, failed validation attempts and remaining acceptance gaps.

- Coordinated SQL result/exit and durable pending/ACK/commit finalization pass
  678 offline runtime cases, retaining all original cases.
- Live wire schema is now 2. Old source/profile bindings must not silently
  authorize the changed protocol. Record/profile schema versions are unchanged.
- No new native lifecycle acceptance ran. The financial gate remains closed;
  prior one-shot permissions remain consumed. No model call or push occurred.
- CPU-only RSS instrumentation and controls passed in fresh scratch copies.
  The historical MLX timeout and training benefit remain unproven.

---

## Current state, 2026-10-25, SQL pilot session closed

**Read [SQL pilot next-session handoff](spec/sql-skill-pilot-handoff.md) first.**
This checkpoint covers the SQL pilot; earlier feature receipts remain below.

- Session scope complete: implementation, offline verification, authorized real
  trial, separately authorized cleanup and durable evidence are saved locally.
- Pilot NOT complete: native pair passed; real record lifecycle failed before
  reuse. Missing-usage RPC completed 4.796 ms before STOPPED; strict discard
  correctly refused. Full kernel acceptance and model benefit remain unproven.
- Current-source offline suite: 3,403 passed, one optional Torch skip, two
  tokenizer deselections, ten existing fork warnings. Reviews found no issues.
- Latest trial cleanup verified: all four owned containers and 18 actors absent,
  ten unrelated containers unchanged, no active reservation/unclosed block.
- Zero model calls. Billing gate closed. Trial/cleanup permissions consumed;
  no retries, new real trials or push authorized.
- Next session: bounded offline diagnosis/design for the pre-STOPPED stats gap,
  not another unchanged trial or infrastructure expansion.

---

## Current state, 2026-10-24, executable skills and fixture readiness

**Bounded offline acceptance receipt, 2026-10-24.** The implementation base is
`8efeb93b55f4435c7b6913156c082b87f4290fc1`, branch
`fix/nonfinite-dead-group-monitor`. Acceptance binds tested source bytes, not
future commit metadata or a permanent current-HEAD claim. Complete configured
default validation passed; independent Python/general/security static reviews
read all seven implementation files and found no issues. General static review
also found no issues in the four integration docs before this receipt update.
Execution validation was performed separately, not by those reviewers. No push
or deployment occurred.

### Implemented boundary

[Executable SQL skills](spec/sql-executable-skills.md) are caller-authored,
explicitly opt-in mechanics, not automatic AI learning:

- `create_candidate(source_capture, *, source_task, source_ids, skill_id,
  program)` is data-only. Required `source_task` corrects the original contract:
  capture fingerprints cannot recover routing fields. Exact task/ID consistency
  and declared valid EX=0 are checked; no source rescore or program runs here.
  Scope is exactly `source`, `shape`, `coarse_shape`, for routing only.
- `evaluate_candidate` is provisional. Literal `allow_execution is True`
  submits once through existing capture. Observation must begin at byte zero
  with `FINAL_SQL:` and a nonempty SQL suffix. Only the suffix reaches `finish`;
  malformed/runtime rejection aborts unscored, well-framed wrong SQL can score 0.
- `promote_candidate` checks an external whole-source-envelope SHA and
  independently rescores source to valid EX=0. It pre-admits exactly four
  externally supplied qualification cases with matching roles/scope/provenance,
  non-source splits, and scoped IDs/task fingerprints/DB digests distinct from
  source and each other. The same program actually runs once per case, at most
  four submissions, no retries. Only four valid EX=1 results yield a receipt.
  Actual captures return separately, not as embedded gold/transcripts.
- `reuse_promoted` checks externally approved whole-promotion-envelope SHA,
  candidate SHA, exact approval IDs, scope/source and current capture/runtime
  plus both new module bindings before dispatch. It need not reopen origin or
  qualification DBs. Payload self-digests and entire-envelope pins differ;
  neither authenticates approval. Caller owns trusted evaluator/assets/pins.

Programs: at most 65,536 UTF-8 bytes. Separate canonical frozen artifacts:
at most 8 MiB. No registry or automatic writes. Existing budget counts eight
PTC submissions, not internal SQL calls; this workflow uses one per case.
Five-second tracing/output bounds are not an OS sandbox, hard-memory bound or
hard deadline. Distinct DB bytes/IDs are not independent draws or semantic
diversity proof; selected source pins are not in-memory attestation.

Native discovery remains exactly one `run_program`; default arms, graders,
trainer and scientific preregistration are unchanged. No model/provider
generation, learned policy, weight update, GPU workflow, adaptive
context/delegation or T3 runtime was added. See [train usage](train/README.md)
and the [remaining research matrix](research/2026-10-24-prime-t3-opportunities.md).

### Targeted receipts

Evidence base:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/`.

- Skills: tests-first **185 failures**, then final **218 new passes**.
  `skills-regression-02.log`: **813 passed in 57.33s**, comprising skills,
  unchanged 276 capture and exact 319 legacy cases. Five baseline controls
  passed; separate source-rescore/disjointness/actual-rerun/scope/approved-pin
  bypasses each caused one intended assertion failure, not import/stale-binding
  errors (`skills-control-*-02.log`).
- Catalog-discovering, identifier-quoting code qualified on four differently
  named schemas with 0/1/3/7 rows and reused on fresh 11/13-row DBs.
  `skills-regression-temp-02/test_fresh_process_receipt_reu0/fresh-process-reuse-receipt.json`
  records two actual dispatches and two valid EX=1 results in a fresh process
  after origin and qualification DBs were deleted. This proves mechanics,
  not model-generated skill discovery, scientific generalization or a new win.
- Bench fixture repair requires real parent/grandchild ACKs and original
  PID/PGID/session before release. Startup is independently bounded to 5s;
  cleanup remains under 1s from the real trigger. Late-effect observation is
  at least 0.8s after return, with a separate 20s emergency supervisor.
  The 0.2s observer and production 30/45s deadlines are unchanged.
  `readiness-worker-qs2r82r0/complete-handshake-repeat-results.json`: **80/80**
  normal runs (four cases, startup delays 0/0.2s, ten repetitions) and
  **20/20** disabled-termination controls detected actual workers/late effects.
- `readiness-worker-qs2r82r0/final-baseline-results.json`: three actual fresh-copy
  isolated bench baselines, each **516 passed, one optional skip, two configured
  deselections**. Complete parity file: **56 passed**.
  `final-owned-and-evidence-audit.json` in that directory records 95 observer
  records with zero errors and 27 PIDs absent per baseline; aggregate 686
  recorded PIDs absent is not a global process proof. Ten earlier invalid
  harness runs failed with zero reports and were preserved/excluded.

These earlier targeted harness audits recorded zero network/cache/tokenizer/
loopback events. They are not the full-run audit below and do not claim
arbitrary-child telemetry. No dependency download or paid network was needed.

### Independent final acceptance

Evidence directory:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/final-validator-vdespsu0/`.
Primary files: `validation-receipt.json`, `full-suite.log` and
`evidence-manifest.json`; all 68 evidence files were read back by the validator.

Complete default offline pytest used
`-q -ra --tb=short -o faulthandler_timeout=60`, with no path selection, filters,
`-x`, retries or additional deselections: **2,446 passed, 1 skipped,
2 deselected in 251.42s**, exit **0**. The skip is unavailable optional torch;
the two deselections are the existing `tokenizer_integration` configuration.
`step2` is outside configured default testpaths. Actual nested baselines passed:
PTC **361**, ledger **30**, bench **516**, with the bench optional skip and two
configured deselections. Full nested output is retained; the bench receipt is
`nested-0002-ptc.stdout.log` (legacy filename, actual `bench/` arguments).

Pytest-process audit: external-network attempts **0**, cache accesses **0**,
tokenizer loads **0**, allowed loopback events **5**. Children inherited the
previously sensitivity-verified OS network-deny sandbox; pytest audit hooks do
not establish arbitrary-child telemetry. Implementation source bindings stayed
unchanged throughout validation.

Five fresh skill baseline controls passed. Five separate in-memory bypasses
each caused one intended assertion failure: source rescoring, disjointness,
actual qualification reruns, scope and approved promotion pin. The independent
validator reconstructed these controls against actual exports/tests because the
author's root scratch script was absent; no import, stale-binding or collection
failure counted. Four disabled-termination cleanup controls also failed ordinary
assertions before emergency cleanup, after real parent/grandchild ACKs and
PID/PGID/session checks. Late effects were observed at least 0.855s after return;
sentinels remained intact and all 14 recorded owned PIDs, including supervisors,
were absent afterward. Cleanup controls had 52 observer records, zero errors.
The full run recorded 27 outer and 27 nested bench fixture PIDs absent;
combined recorded fixture evidence covered 64 absent PIDs, 252 observations and
zero observer errors. These are owned recorded PIDs, not global process clearance.

The readiness gap was demonstrated against old source by two RED failures and
repaired without weakening the observer. The historical full run below had
**2,222 passed, one outer failure and two nested bench failures**. Only one
nested ID survived; the second ID and both assertion bodies were lost.
Fresh readiness evidence cannot explain or retroactively fix the unknown
historical failure. The current full pass clears the offline blocker without
proving those lost assertions' root causes or a production watchdog defect.

The bounded offline workflow/readiness gate is accepted. Model-generated
skills/held-out benefit, context/delegation economics and real native training
remain separate gates.
Historical 6.1–8.2× economics were setup-specific, no-cache results; the original
accuracy thesis failed. No new economic or scientific claim follows.

## Historical checkpoint, 2026-10-24, incremental SQL/PTC execution capture

`train/sql_capture.py` implements trusted host capture through the unchanged
canonical `train.grpo_ptc.sql_environment(task)`. `start_capture` requires
literal `allow_execution=True` and explicit `EpisodeIds`. `session.prompt` is
canonical; sequential `step(code)` returns actual observations. Eight dispatched
submissions are separate from later budget refusals. `finish(final_answer)`
scores protected final/gold SQL without replaying actions; `abort()` has no final
or score. Terminal/invalidated sessions reject reuse. Per-session locks serialize
host calls, not external effects or crash recovery.

Frozen `SqlCapture` records reuse existing IDs, action observations, instrument
settings and `ExResult`. The separate `sql_execution_capture` v1 JSON envelope
is strict, canonical and bounded to 8 MiB. Decode is data-only; rescore rechecks
external caller/task/DB/prompt/source/settings bindings and executes only
protected final/gold SQL. Source coverage includes the actual capture,
environment, budget and shared evidence owners. Existing scripted v1 origin
`scripted` / terminal `scripted_final` and native tool discovery stay unchanged.
No legacy tests were edited and no acceptance cases were weakened.

Python review found a real P2: sub-8-MiB quoted-semicolon input can make the
frozen shared extractor scan quadratic prefixes before query timeout applies.
Capture now calls `_bounded_extract_sql` from both validation and finish.
It admits UTF-8 byte length plus `sum(semicolon_byte_position + 1)` at most
`64 * 1024 * 1024` before invoking the existing extractor. Incremental byte
search exits as soon as the budget is exceeded. Quoted/comment semicolons,
discarded prose/fences and text after an early complete statement all count,
so some cheap-to-extract texts conservatively reject. This is per invocation,
not a whole-operation CPU/memory deadline; the independent 8 MiB format bound
and all API/schema/source fields remain unchanged. `bench/score.py` is frozen
and was not edited. Failed finish invalidates before scoring.

Validation used the existing read-only reference interpreter
`/Users/nikolassapalidis/Developer/misc/co-train/.venv-ptc/bin/python`
(Python 3.12.13, pytest 9.1.1), targeting this actual repository, not reference
source. The reviewed real offline harness used fresh caches, bytecode/pytest
cache disabled, inherited OS external-IP denial, and its native observer.

* RED: **252 failed in 4.09s**, exit 1, all expected missing-API failures from
  test bodies, not collection/dependency errors.
* Focused GREEN: **252 passed in 13.39s**, exit 0.
* Combined GREEN: **570 passed in 41.10s**, exit 0, no skips, across
  `train/test_sql_capture.py`, `train/test_sql_episodes.py`,
  `train/test_sql_bridge.py`, `train/test_execution_binding.py`, and
  `train/test_sql_reward_queries.py`.
* Every run's audit counters were zero: external network attempts, cache file
  accesses, tokenizer loads and loopback events. These counters are not
  arbitrary-child/native telemetry. Supplied baseline sensitivity controls
  were not rerun.

Logs, all under
`/Users/nikolassapalidis/scratch/co-train-capture-2026-10-24/`:
`capture-red-01.log`, `capture-green-01.log`, `capture-combined-01.log`.
`capture-regression-collection-01.log` records 239 scripted, 66 bridge,
10 execution-binding and 3 reward-query cases: **318 legacy cases**. The supplied
independent baseline used `train/test_learning_lab.py` (4 cases), not
`train/test_sql_reward_queries.py` (3). This explains 570 versus 571; no test
was lost. The exact original four legacy modules plus capture independently
passed **571 in 157.49s**, in `validator-exact-baseline-plus-capture-01.log`.
Parent's original DB/budget/replay/sealed controls caused **1/1/1/2** real
assertion failures against a **5-pass baseline**. Budget/replay's old report
string matcher missed rewritten `assert` traces; raw failures are actual
count mismatches (10 vs 8 dispatches, 6 vs 4 before finish).

Extraction-repair receipts, under the same scratch directory:

* `capture-extraction-red-01.log`: **17 failed, 7 passed, 252 deselected,
  31.02s**, exit 1. Fifteen extractor-sentry assertions and two missing
  +1-byte rejections, not source/digest/import/collection failures. No
  quadratic attack extraction was actually executed.
* `capture-extraction-green-01.log`: **24 passed, 252 deselected, 6.50s**.
* `capture-extraction-combined-01.log`: **595 passed, 149.43s**, no skips,
  exit 0. Exact legacy modules: SQL episodes, SQL bridge, execution binding,
  learning lab. Capture now has **276 cases**.
* `capture-extraction-probe-01.log`: real-code positive plus valid-digest
  4,003,379-byte attack decode in a fresh sandbox-inheriting child.
  Work-limit `ValueError` after **0.01664s**, child normal exit **0**,
  parent **0.31109s**, under its **10-second kill/reap deadline**.
  External pytest probe: **1 passed in 1.59s**.
* `capture-extraction-control-baseline-01.log`: **2 passed in 1.68s**.
  `capture-extraction-control-validation-01.log` and
  `capture-extraction-control-finish-01.log`: each independently bypassed
  its guard in memory and produced **1 extractor-sentry assertion failure**,
  exit 1, **1.86s / 2.35s**. No working source was mutated.

All extraction-harness runs recorded **zero** network/cache/tokenizer audit
violations and loopback events. Probe audit counters cover the parent pytest
process, not arbitrary child telemetry; the fresh child inherited the OS
sandbox. Original four runtime controls were not repeated for this guard fix.

General/security review found no actionable issues. Fresh Python static
re-review closed the P2: both extraction sites, all entrypoints, tests and docs
were checked; no new findings remained.

Final independent full default offline run completed **100% of 2,224 selected
tests across 38 modules**: **2,222 passed, 1 failed, 1 skipped, 2 deselected
in 428.41s**, exit **1**. All **276 capture** (including 24 extraction guards)
and **319 exact legacy** cases passed independently too. The optional skip is
unavailable torch; the two configured deselections are tokenizer integration
controls. No `-x`, retries, timer changes or additional deselection were used.
External-network/cache/tokenizer audit counts were **0/0/0**, with **5 permitted
loopback events**. Parent/child OS external-network denial and five audit-guard
RED controls were verified earlier; audit counters are not arbitrary-child
telemetry.

The unresolved failure is
`tests/test_mutation_harness.py::test_ptc_real_isolated_baseline_collects_and_passes[bench]`
at line 165: nested bench returned **1**, not 0 (**2 failed, 509 passed,
1 skipped, 2 deselected in 38.30s**). Retained inner detail identifies
`bench/test_sql_parity_sweep.py::test_interruption_cleans_owned_work_and_propagates`;
the other inner failure detail is abbreviated and unavailable. These isolated
baselines copy `ptc`/`ledger`/`bench`, not `train`, independently of capture.
Direct outer parity cases passed. An earlier run hit the existing 0.1s startup
PID-readiness fixture; a candidate 0.5s change passed isolated but broader file
timers failed. **All candidate edits were reverted**: the parity test and legacy
production files remain unchanged, with no weakened guards. Investigation ended;
the baseline infrastructure blocker remains unresolved, not a proven production
cleanup defect. All 17 probe PIDs were finally absent. **Full-suite GREEN and
release acceptance are not established.**

Use the interpreter above with the real offline harness documented in
`spec/offline-harness-reliability.md`; final default pytest arguments were
`-q -ra --tb=short -o faulthandler_timeout=60` (no path selection).
Optional local provenance: `validator-final-full-default-01.log`,
`validator-final-default-collection-01.log` and
`validator-final-integrity-after-01.log` under the scratch directory above.
Integrity checked unchanged **44 repository / 4,878 reference bytecodes** and
**23 repository / 10 reference source fingerprints**. All eight authored
artifacts were nonempty; no reference source was edited.

Research synthesis/backlog is saved in
`research/2026-10-24-prime-t3-opportunities.md`; the backend capture prerequisite
is complete and targeted-verified, not fully offline accepted. Skill generation/promotion,
adaptive context/delegation and native training remain deferred gates.

Limits: caller declarations and artifact digests are not authentication;
selected on-disk sources are not in-memory attestation; DB hashing needs a stable
caller-owned snapshot without sidecars and does not prevent malicious ABA
writes. PTC is not an OS sandbox. Incremental fixture execution is not
token-faithful provider capture, model authorship, learning or production
readiness. No native runtime/model generation/optimizer/checkpoint path was
verified. Training remains fail-closed; no default, gold-policy, scientific
manifest/protocol, dependency or reference source was changed. No push or
deployment occurred.

## Earlier checkpoint, 2026-10-23, offline harness reliability

The two immediate offline fixes from the
[round-2 research](research/2026-10-23-harness-round2.md) are implemented.
Each SQL differential now runs in a fresh isolated Python process, with JSON
request/result files and owned process-group cleanup. A timeout stops owned
work instead of abandoning a daemon. Arm deadlines remain 30s and the outer
allowance remains 45s. Unexpected cleanup failures abort, retain diagnostic
directories and prevent a success-summary write. Already-running pool jobs
keep their own bounds; queued jobs cancel.

Default pytest excludes exactly the two marked real-tokenizer contamination
controls. Explicit integration requires `--tokenizer-artifact` and the eight
frozen SHA256 values in `bench/tokenizer_artifact.json`. Admission precedes
the dependency import; loading is local-only with remote code disabled.
Missing artifacts/dependencies fail rather than skip. Fresh mutation copies
now carry `pytest.ini`, so their bench baseline preserves the same exclusion.
Both original scientific assertion bodies and inputs remain unchanged.
The manifest records a diagnostic baseline, not upstream authenticity or
native model/template approval. Symlinks are accepted after hashing; TOCTOU
and cache immutability are not guaranteed.

Parent reproduced behavioral RED on both paths before implementation.
Narrow checks passed 51 sweep tests, 40 tokenizer-admission tests and both
real tokenizer controls with zero integration skips. The overlapping sweep
and watchdog scope passed 130 tests under OS network denial. Actual SIGINT
propagates after owned work stops; normal leader exit also cleans descendants.
Disabling termination produces live work and a late marker, which the
independent liveness guard rejects. Independent in-memory digest/local-only
source mutations cause two/one failures. Python/security reviews found no
actionable issues, including the fresh-copy follow-up.

The full default suite passed **1947 tests, one optional torch skip and two
tokenizer-control deselections**, in **204.38s**, with fresh isolated HF,
Transformers, Datasets, modules and XDG caches. Python cache/network auditing
recorded zero cache accesses and external attempts in the pytest process;
main-thread tokenizer profiling recorded zero loads. Five allowed loopback
audit events came from local fixtures. Child sensitivity controls intentionally
attempt denied connections; these counters are not child/native telemetry.
OS external-network denial was inherited and separately verified in a child.

The first strict no-IP run timed out after 900s because existing tests serve
local MCP fixtures. It is retained as a failed validation attempt. The final
policy denies external IPv4/IPv6 networking but permits loopback and Unix IPC;
it is not local-proxy isolation. Parent/child external-denial probes and a real
loopback TCP positive passed. The MCP/fresh-marker scope passed 43 tests.
The macOS sandbox also blocks setuid `ps`; a validation-only native libproc
observer preserves real liveness checks without changing fixture deadlines.
API errors count as executing, not dead; its injected-denial control rejects.
See `spec/offline-harness-reliability.md` and
`research/2026-10-23-offline-harness-reliability.json` for source hashes,
embedded validation-harness sources, logs and limits. The preceding research
artifacts and their recorded hashes remain unchanged.

The commit scanner initially flagged eight public checksums as API keys.
Owner-approved `.gitleaks.toml` exceptions match only those exact values in
the generic rule; defaults stay enabled. Unrelated, uppercase and embedded
hash-shaped keys and a synthetic provider token still trigger detection.
An overbroad-exception mutation fails the negative-control check.

No native runtime, model generation, optimizer update or checkpoint restoration
was verified. Frozen/native dependency conflicts, exact-template rejection,
frontier evidence and invalid-gold policy remain blockers. Main remains
fail-closed. No scientific contract or evaluation membership changed.
No dependency/model download, GPU/paid/training job, push or deployment occurred.

## Earlier checkpoint, 2026-10-23, guarded native trainer construction

`train.native_runtime` now reports selected distribution constraints without
importing frameworks, running installers or granting approval. Enforcement
always reads fresh installed metadata; fixture reports cannot authorize it.
All six approval/verification/authorization fields stay false. The frozen
Transformers<5 rule is unchanged and conflicts with native TRL's >=5.2.
Local Transformers5.18 and datasets5 also violate selected Unsloth bounds.
The proposed core remains unapproved, with dependency graph and CUDA ABI open.

`train.native_training.build_sql_trainer` adds the explicit-task constructor
behind real preflight and runtime checks. It separates loader/PEFT/Trainer
arguments, requests pinned local-only fp16 loading and preserves existing SQL
bindings, G, optimizer ownership and eight-turn limits. It checks the actual
discovered tool/schema, selected native template, every row's context and the
native suffix-prefix contract. It configures checkpoints at requested steps,
but never invokes train/save. Main's post-preflight refusal remains.
Constructor failures after admission may leave allocated runtime resources.

Failure-first receipts contain 94 runtime and 45 constructor setup errors
solely for absent implementation modules, followed by **139 passing tests**.
The initial runtime fixture accidentally compared pytest's changing
`PYTEST_CURRENT_TEST`; that harness error was fixed before accepting RED.
Real SQLite 17/29 and real Dataset Arrow conversion passed; constructor/model
spies prove wiring only. Dataset5 interoperability is not Unsloth compatibility.
Six fresh-process in-memory source mutations caused **1, 1, 1, 1, 2, 1 failures**:
native floor, real preflight, fresh runtime gate, context bound, all-row checking
and one-tool discovery. All six baseline controls passed. Production files
were not mutated. Real preflight also refused under optimized Python.

The promoted `native_template.py` reference executes captured hash-checked
upstream helper/template bytes and pinned native methods. Conditional rendering
preserves a 29-token prefix in 48 tokens, with real SQLite 17 and 19 external
masked tokens. **Automatic helper selection rejects the cached template's
identity.** The positive branch's canonical identity view is hypothetical,
never production code. Stock-prefix, cached-selection, prefix-mutation and
mask-mutation controls each exit 1. Sampler logprobs remain absent; the parser
and final answer are scripted. Its 3537-token context minimum is fixture-only.

Python and security reviewers approved the source statically; the parent
executed validation. The full offline warm-cache default suite passed
**1861 tests, one optional torch skip**, in **291.67s**, including real isolated
mutation baselines. Cold-cache bootstrap remains unverified. The actual
`train.grpo_ptc --preflight-only` command still exits 1 for the absent manifest.
See `spec/native-training.md`, the reference README,
`research/2026-10-23-native-runtime-metadata.json` and
`research/2026-10-23-native-training.json`.

No real patched Trainer, sampling, gradients, changed weights or checkpoint
restoration was verified. Runtime resolution, cached-template support,
frontier evidence and invalid-gold policy remain blockers. No scientific
contract, manifest, model selection or evaluation membership changed.
No install/model download, GPU/paid job, push or deployment occurred.

## Earlier checkpoint, 2026-10-23, calibrated SQL evidence (`d6d04f0`)

Two additive offline modules are implemented:

- `bench.frontier.calibration` computes hypothetical IID screening diagnostics
  and validates/reduces explicit binary sample groups by task/arm/phase/config.
  Empirical all-equal frequency is separate from the plug-in estimate.
  Invalid groups remain visible and do not enter usable denominators.
- `train.sql_episodes` records trusted scripts through unchanged SQL arms,
  freezes actions/observations and complete scoring results, and encodes strict
  canonical JSON with a corruption digest. Rescore runs protected final/gold
  SQL only; action re-execution requires literal `allow_execution=True`.
  Caller IDs, task, DB snapshot, prompt, settings and selected sources must
  bind before either operation. Decode never executes actions.

The recorder allows eight actions plus separate FINAL text. It does not
redefine native model-round accounting. Existing defaults remain 200 action
rows versus 500,000 scorer rows, PTC timeout 5s and bash/scorer timeout 30s.
It rejects WAL/journal/shared-memory sidecars and checks DB content before
and after operations. Stable caller-owned snapshots are required.
Self-digests are not authentication; trusted bash remains a real shell.
Selected source/runtime bindings are not a full host snapshot or SBOM.

Test-first receipts: 160 calibration, 239 episode and four parent integration
tests initially failed before their implementation. Numeric review reproduced
boundary asymmetry, rounded input tails/ceilings, rational formatting, and
unsafe Decimal expansion before repair. Final narrow checks passed **445**.
Five isolated source mutations produced **2, 1, 1, 10 and 6 failures**, with
passing controls, for sample reuse, task pooling, marginal substitution,
task-fingerprint removal and Decimal-bound removal. No production source
was mutated. Python and security reviewers approved the final source;
their reviews were static, runtime checks were executed by the parent.

The final offline warm-cache default suite passed **1722 tests, one optional
torch skip**, in 157.63 seconds, including real isolated mutation baselines.
That adds 445 cases over `f817045`. Cold-cache bootstrap remains unverified.
See `spec/learning-lab.md`, `research/2026-10-23-learning-lab.json`, and
the runnable references under `spec/spikes/reference/`.

Additional pinned-source analysis covers Harbor, OpenEnv, Agent Lightning and
Reasoning Gym, plus Terminal-Bench release identity. The report separates
inspected source/tests from author claims and actual local execution:
`research/2026-10-23-harness-deep-analysis.md`. No upstream tests or learning
gains were reproduced.

**Main training remains unimplemented and fail-closed.** The frontier manifest,
frozen Transformers/native-TRL conflict, invalid-gold policy, optimizer and
checkpoint proof remain unresolved. Follow-on acceptance gates are in the spec.
No model generation, GPU/paid job, install, scientific contract change, push
or deployment occurred.

## Earlier checkpoint, 2026-10-23, mutation process lifetime (`f817045`)

All three mutation runners now use stdlib-only `process_watchdog.run_bounded`.
Each suite owns a POSIX session, has a
300-second deadline, and gets original-group TERM/KILL cleanup on completion,
timeout or interruption. Final pipe drain and direct-child reap have separate
bounded waits. Leader exit cannot skip descendant cleanup. A failed reap raises
an infrastructure error instead of looking like a killed mutant.

Six bounded real-process regressions failed against `91b90bd`: Step2/train
could wait indefinitely, PTC left a TERM-ignoring descendant after leader exit,
and all three left descendants after a successful leader exit. Independent
2.5-second supervisors cleaned the fixtures even when the runner failed.

Before review, all 67 lifecycle checks passed. The existing 69 mutation-harness cases,
including real isolated PTC/ledger/bench baselines and 52-anchor validation,
passed. Six additional isolated-import cases passed: every fresh sandbox
imports its own copied helper under Python `-I -B` outside the repository;
removing only that generated helper produces a real ModuleNotFoundError.

A real Darwin edge case was reproduced: killpg on an empty group containing
only an unreaped leader returned EPERM; after poll/reap, it returned ESRCH.
The helper retries the same group only after reaping, without swallowing a
real permission error. A separate regression prevents failed cleanup/reap
from being classified as an ordinary suite timeout.

The pre-review offline warm-cache default suite passed **1262 tests, one optional
torch skip**, in 369.91 seconds. Python review then found that escalation
interruptions/signaling errors could bypass stream closure/reap, and runner
adapters hid escaped-pipe notes. Ten failures and three passing controls
reproduced those findings before repair. A subsequent security finding exposed
lost secondary cleanup diagnostics through the public interruption path; two
more failures reproduced it. A guarded shared-exception case also failed before
notes were snapshotted. The final fixes passed 154 targeted checks; the three
real isolated baselines are included in the final suite being rerun.

The original exception now survives cleanup failures, both streams close,
and a bounded reap is attempted even when escalation fails. All three CLIs
retain incomplete-drain warnings, including PTC's killed-timeout path.
Python and security re-reviews approved the final fixes. The final offline
warm-cache default suite passed **1277 tests, one optional torch skip**, in
147.57 seconds. That includes 79 lifecycle cases and 78 mutation-harness cases;
the groups overlap with the default suite. This adds 88 cases over `91b90bd`.
The skipped contamination check requires the absent torch package.
Earlier provider failures are resolved.
`research/2026-10-23-process-watchdog.json` records the validation.

Timeout classifications are unchanged: PTC 124 means killed(timeout), while
Step2/train 124 is INVALID. Every nonzero baseline remains invalid.
This does not contain descendants that create another session, bound output
volume, support Windows, or cancel the bench sweep's daemon threads.
All training/frontier/framework gates remain closed. No paid service, model,
GPU job, dependency installation, scientific contract change or push occurred.
Tests/plan: `tests/test_process_watchdog.py`, `tests/test_mutation_harness.py`,
`spec/process-watchdog.md`.

## Earlier checkpoint, 2026-10-22, native SQL training inputs (`91b90bd`)

`train.sql_bridge.prepare_sql_training` now prepares plain conversational rows,
a zero-argument native environment factory, and the existing SQL execution
reward from explicitly supplied tasks. It does not choose a taskset or construct
a trainer. Only `run_program` is exported as a tool; reserved `reset` validates
the row against private frozen bindings and creates fresh execution state.
Failed resets clear the old executor first. Tool and scorer databases must be
the same physical file. The prompt and eight-submission budget match evaluation.

Native transcript normalization accepts only a final assistant string without
outstanding tool calls; observations and earlier SQL cannot become answers.
Strict metadata cardinality, missing-database exceptions and invalid-gold
mapping are unchanged. Requested positive integer `--steps` now reaches
preflight/configuration; it previously silently stayed at 200.

Before implementation, the step tests produced 12 failures and two controls
passed. All 66 bridge cases failed in fixture setup because the module was
absent, with pytest exit 1 rather than a collection failure. After implementation,
all 80 new cases passed. Four independent runtime mutations removed the
submission limit, stale-reset invalidation, corpus-identity check and unfinished
answer rejection: 1, 7, 2 and 1 assertions failed respectively. No production
file was mutated.

The actual production adapter also passed through the hash-verified
`GRPOTrainer._tool_call_loop` from official TRL v1.13.0: one real SQLite result
17, one exact tool schema, external mask positions zero, and final execution
reward 1. Changing only that method's mask in memory failed with exit 1.
Optimized Python is explicitly rejected. Tokenization, generation and response
parsing are fixtures; this is not complete trainer, gradient or CUDA evidence.
See `spec/spikes/reference/` and
`research/2026-10-22-training-bridge-contract.json`.

Python/security static reviews approved the bounded changes. The final offline
warm-cache default suite passed **1189 tests, one optional torch skip**, in
143.89 seconds. Cold-cache bootstrap remains unverified.

**Main training is still not runnable.** Real `--preflight-only --steps 17`
still exits 1 for the absent frontier manifest; the downstream
`NotImplementedError` remains. Native TRL environments require Transformers
at least 5.2, while the frozen project guard requires below 5. The local 5.18.0
schema utility does not establish a compatible stack; Unsloth's checked metadata
caps Transformers at 5.17.0. Resolve this conflict explicitly before a patched
trainer/optimizer/checkpoint smoke on approved hardware.

No dependency installation, model loading, GPU job, paid service, scientific
threshold, amendment, signature, manifest, push or release was performed.
The earlier SQL repair and all remaining process, bootstrap, invalid-gold and
measurement-contract gates still apply.

## Earlier checkpoint, 2026-10-22, SQL safety and scorer integrity (`3a86d60`)

The previously reproduced SQL file writes, rewards for no-result SQL, and
timed-out wrapper replacement are repaired. Both Python SQL paths install the
same fail-closed authorizer; both CLI invocations require `-safe`. The scorer
requires result metadata, preserving genuine empty queries. Sweep wrappers
belong to individual watched invocations and survive until their work ends.
Timeout and execution errors are no longer conflated.

Real SQLite/CLI regressions went red before the repairs. Four independent
negative controls then disabled the PTC guard, scorer guard, CLI count safe
flag, and CLI final safe flag: 20, 8, 2 and 2 assertion failures respectively.
Valid-query controls also passed. All 800 shipped gold queries remain valid
under the protected scorer at 30 seconds/500,000 rows per query; the local
metadata and code hashes are in
`research/2026-10-22-sql-safety-golds.json`. This is not a new full-corpus parity
sweep or proof of historical Kaggle database bytes.

Python review caught two dependency regressions that the repository-wide suite
missed. The guard now lives in stdlib-only `ptc.sqlite_safety`, keeping PTC
importable without bench. Three training integration cases live in `train/`,
so the real isolated bench mutation baseline passes without copying training
code into it. Both findings were reproduced, repaired, and re-reviewed.
The guard/standalone group passed 70 checks; scorer/reward/isolated-bench checks
passed 48. These are overlapping with the default suite.

The final default suite passed **1109 tests, with one optional torch test
skipped**, in 122.63 seconds: 136 more cases than `5bac4fc`. This was an offline
warm-cache run, not proof of cold-cache tokenizer bootstrap.

Co-training is still not runnable or experiment-ready. Main training and the
frontier gate remain closed. Watchdog cancellation, mutation process lifetime,
cold-cache tokenizer bootstrap, invalid-gold void policy, and the frozen
model/channel/data contract remain open. SQL guards do not sandbox the OS or
the wider bash shell. The eight historical channel divergences were not
silently repaired or remeasured. No GPU job, paid call, signature, threshold
change, push or release was performed. See `docs/completion-roadmap.md`.

## Earlier checkpoint, 2026-10-22, team hardening (`5bac4fc`)

The unresolved SQL/scoring findings below describe that earlier checkpoint;
the current section above supersedes them.

The five-lane audit led to four implementation tracks, with regression failures
executed before production changes. The branch now has real task-bound SQL
execution, required-telemetry checks that reject unevaluable runs, lossless
frontier diagnostic reports, corpus-order-independent seeded selection, and
mutation runners that distinguish invalid verification from killed mutants.
Literal SQLite paths cannot inject URI access modes; malformed tool argument
shapes return rejection data and permit retry. The diagnostic writer rejects
manifest aliases, including hard links.

Python review found three stale registered mutation anchors. All 52 anchors now
match exactly once, and the three repaired mutations were executed against a
real fresh baseline: all three died, with zero survivors or invalid runs.
Security review's hard-link finding was also reproduced and repaired.
The final post-review default suite passed **973 tests, with one optional
torch test skipped**. That is 329 additional test cases over the preceding
644-pass baseline. Python and security source reviews approved the bounded
patch; they did not establish whole-system safety.

**This does not make co-training runnable or the instrument experiment-ready.**
The actual preflight still exits 1 for the missing frontier manifest, and main
training remains unimplemented after that gate. Disposable fixtures also
confirmed two unresolved blockers: both SQL arms can create files with
`VACUUM INTO`, and comment-only SQL can receive execution reward against an
empty result. No channel/scoring policy was silently changed. Cold-cache
offline tokenizer controls also failed; warm-cache green is not a bootstrap.

[`docs/completion-roadmap.md`](docs/completion-roadmap.md) records the repairs,
reproductions, remaining safety/process/provenance gaps, and acceptance checks
from runnable training through the six-cell scientific comparison. Probe/run
thresholds, signed amendments and the 800 shipped prompt files are unchanged.
No GPU run, paid call, signature, push or release was performed.

## Earlier continuation, 2026-10-22

**v10 ran and aborted after three steps.** The local metrics and companion log were
found and re-read with the logged three-step window. Dead fractions were 1.00,
1.00 and 0.75; the third step had mean execution reward 0.34375 and gradient norm
0.413225. All clipping ratios were zero. The verdict is `PROBE ABORT`, not an
unobserved ten-step run or a frontier measurement. See `docs/probe-v10.md` for
artifact hashes, provenance gaps and the executed verdict.

All 800 shipped SQL prompt IDs, database references and gold queries matched the
local corpus; all 800 gold queries executed successfully under the scorer's
30-second deadline and 500,000-row cap. That does not establish byte identity with
the historical Kaggle upload.

The frontier manifest is still absent and preflight was verified to fail closed.
The downstream co-training entry point also remains deliberately unimplemented.
A11 is still unsigned. No new GPU run, scientific-criterion change, signature,
paid call or publication was performed.

`research/2026-10-22-continuation-review.md` records the current literature,
independently checked power/abort arithmetic, and the proposed frozen-policy
frontier measurement. It also distinguishes dormant manifest-validation code
from enforced requirements; do not wire in its unsigned retention floor.

The SQL extractor now preserves semicolons inside quotes/comments while retaining
only the first statement. Twenty fixture-backed failures were reproduced before
the fix; the final default suite passed 644 tests with one optional torch test
skipped. Python and security source reviews approved the change.

---

## Current state — 2026-10-19

**The probe now measures the policy, and the policy is weak.** v9 is the first run in nine
where generation, extraction and reward all worked: `clipped_ratio` 0.000,
`mean_terminated_length` == `mean_length` == 58.8, and `grad_norm` non-zero for the first
time. It aborted at step 0 on `frac_reward_zero_std` 1.000, and **that abort is a finding
rather than a fault** — but on four groups, one step, so it licenses "solve rate at or
below ~0.05", not a rate. Full write-up: `docs/probe-v9.md`.

- **The generation fault is closed, and its cause was the prompt's shape.** The prompt was
  a bare string, so TRL never applied the chat template: no `<|im_start|>assistant`, no stop
  token, every completion rode to the 3072 cap and was masked. Fixed by rendering prompts as
  one-message conversations plus `enable_thinking: False`, shared by both configs (#22).
- **A repeated signature finally explained.** `grad_norm` 0.0 appeared in v7 and v8 and was
  read against the reward both times. It meant the reward was never called.
- **The taskset's validity threat is now measured, not assumed.** First contamination check:
  question channel clean (AUC 0.455 / 0.508 against controls the instrument can *see* at
  0.764 / 0.825); gold-SQL channel INCONCLUSIVE because the fresh control's length was not
  matched to BIRD's, and length alone reproduced the whole signal. `docs/contamination.md`,
  A10 drafted unsigned.
- **The arm-parity gap has a check it did not have.** A differential sweep over all 1534
  BIRD golds finds 8 real divergences, including 4 where the bash channel loses a trailing
  all-NULL row. Closing those needs the channel to change — owner's call (#24).
- **ProgAgent (arXiv 2610.14774) is the paper that scooped this, and `docs/related-work.md`
  now says so.** It trains 8B/14B only, has no bash arm, and does not enter this project's
  band. The open cell is PTC-trained vs bash-trained at 0.6–1.7B with a bidirectional swap.
- **OSF `2hfzt` is public** as of 2026-10-18, files re-synced to the 26-defect ledger. There
  is no DOI: OSF mints those for registrations and preprints, not project nodes.
- **Still $0 spent, and the $6.29 main run remains unauthorised.** The pipeline gate is shut
  and `bench/frontier/manifest.json` still does not exist.

**The open decision, and it is the owner's:** v9's abort criterion (§282, any step over the
ceiling) collides with `GROUPS_PER_STEP = 4` at step 0 — the first unlucky batch ends the
probe before a rate exists. Three routes: more groups per step, a warm-up collecting k steps
before adjudicating, or a taskset higher on the policy's frontier. Each replaces the
measurement v9 produced.

---

## Current state — 2026-10-12

**A8 is signed and the instrument is replaced.** `ledger` is retired; BIRD-SQL dev is the
taskset; the paired SQL arms exist with parity measured rather than asserted; and the
co-training pipeline is built with its gate shut. 482 tests. Nothing has been measured on
the new instrument and no money has been spent.

- **`docs/pre-registration.md` gained A7 and A8, both appended, neither an edit.** A7
  restates A4's cost claim as two ratios and a floor and withdraws secondary 3 outright.
  A8 replaces the taskset. Both were signed under the owner's standing instruction this
  session that every decision not costing money is the agent's; that delegation is
  recorded in each amendment rather than implied. The file's md5 moved twice and the OSF
  node's copy was re-uploaded to match both times.
- **BIRD cannot test A6's mechanism, and that is the session's load-bearing finding.**
  N1's interaction needs the one-program-versus-forty-calls contrast; a BIRD task is one
  query, one call on either arm. BIRD's simple/moderate/challenging labels are a human
  annotation and 20 clause skeletons appear in all three tiers, so they are not even
  structural. **BIRD is admitted for H3/H4/H5 only and is inadmissible on N1.** Do not
  place a BIRD number beside an N1 prediction.
- **BIRD's numbers, measured against the real downloaded corpus:** 1534 questions, 277
  fine clause-skeleton shapes (25 coarse) against `ledger`'s 9. Gold validity 1530/1534
  clean; of the four rejected only **two** are genuine defects, the other two legitimately
  return 228,765 and 278,230 rows in ~1s. +25 pp needs 59 paired tasks and is reachable at
  any rho; +6.8 pp needs 859 and is reachable only below rho 0.164/0.179/0.101 per tier,
  so BIRD raises shapes 31x and still misses the project's own retired headline target.
- **`compare="set"` is the default and the headline; multiset is a sensitivity check.**
  Official BIRD `evaluation.py` uses `set()`, and comparability to the published sub-1B
  numbers is why a self-authored taskset was abandoned. Until 2026-10-12 nothing pinned
  the default: every comparison test passed `compare=` explicitly, so the one value a
  caller gets by saying nothing was the one value nothing checked.
- **`ptc/paired.py`'s `power_pairs` was crashing, and the band was invisible from both
  sides.** `comb(d, i) * p ** (d - i)` converts an exact big integer to float, which
  raises past d≈1030, so every delta in 0.02-0.04 died. delta ≥ 0.05 answers below that d
  and delta < 0.02 stops at d=1000 on the lower `hi` bound, so all four published figures
  -- 59, 398, 859, 1571 -- sat outside it and nine runs never touched it. Now computed in
  log space; the four values are unchanged and pinned. `_attained` deliberately did NOT
  get the same fix: it is demo()'s independent check, so it uses exact `Fraction`
  arithmetic instead, and an AST test keeps it from being routed through the helper.
- **The parity guard is twelve executable probes, not a claim.** Each capability carries a
  bash probe, a PTC probe and the answer both must reach; `expected` is the ANSWER, not
  the channel's bytes, because demanding byte-identical observations would demand the
  channels be the same channel. Two probes are run 1's defect 5 as tests. Five asymmetries
  are declared, four favouring bash. Emptying `SQL_PRIMITIVES` turns two capabilities and
  the one-sided check red, verified and restored byte-identical.
- **The pipeline gate is shut and says why.** `train/guards.py` requires a signed
  amendment (A8 now reads as signed; A7 deliberately does not), a per-task solve-rate band
  inside (0.120, 0.880), and `n_tasks >= 59` **derived** from `power_pairs` rather than
  stored. `bench/frontier/manifest.json` does not exist, so `preflight()` raises.
- **`solve_rate_min` must never be filled from the ~25% estimate.** That is a marginal
  over a corpus; the gate reads per-task rates. At the same marginal 0.25 and G=4, a suite
  where every task sits at p=0.25 reads 0.320 dead groups and is trainable, while one
  where a quarter are always solved and three quarters never are reads **1.000** and is
  not. Indistinguishable as a marginal.
- **The next action is the free dead-group probe, and it costs $0.** Free Kaggle T4, 12.59
  GB peak, `--steps 5`, `pip install "unsloth>=2026.10.3" "trl==1.13.0"`. Below unsloth
  2026.10.3 this is not a degraded run but another one. Wall-clock is deliberately
  unmeasured and the probe yields the step time so 20 steps is decided from data. It needs
  a prompts file from a BIRD draw first. **Download `probe_metrics.jsonl` immediately** --
  Kaggle's restart wipes `/kaggle/working`, which is how Step 2's metrics were lost once.
- **The $6.29 / 13.2 h main run is still unauthorised and is not the next thing.** The
  free probe answers whether a binary reward separates at all, and no taskset fixes a
  reward that cannot.
- **Spider is not admitted.** Never downloaded; `load_spider()` is verified against
  documentation and a layout fixture only. It needs its own amendment.
- **Contamination replaced self-authorship as the validity threat.** `ledger` could not
  have been pretrained on; BIRD dev has been public since 2023 and no check has been run.
  H3 is a within-instrument delta on both arms against the same corpus, which is what
  keeps BIRD usable, and that argument is written into A8 rather than assumed.

---

## Superseded — current state as of 2026-10-11

**Kept verbatim. Superseded by the section above; read it for what was true on 10-11, not
for what is true now.**

## Current state — 2026-10-11

Steps 1 and 2 are done, the PTC arm is built, and the untrained premise check has met a real
model fourteen times. **It is decided: the premise did not hold.** Nothing in the History
section below describes any of that.

- **Start with `docs/deviations.md`'s defect ledger** (new, at the top of that file).
  **Thirteen** distinct faults — nine in the harness, **four** in the tools that adjudicate
  the result — each with the run that exposed it and the observation that caught it. Every
  one was invisible to a green test suite, and the thirteenth was worse: the suite pinned the
  two failure-prefix strings against drift and so locked in the blindness it was meant to
  guard. Read it before believing any number in this repo. **The count moved 12 → 13 on
  2026-10-10; it is derived from the ledger's own tables, so derive it rather than quote
  this line.**
- **`docs/results-untrained.md` is the pre-committed output.** §6 fired: run 2h measured
  PTC 14/14 against bash 12/14 on the original 14 tasks, so H1 is wrong on **sign**. Not
  separable at n=14 — a non-reproduction, not a reversal.
- **The taskset was extended 14 → 29** (`pre-registration.md` §8/A5) because PTC's 14/14
  left no headroom for a training effect. A6 signs the new question before its data existed.
- **Only 2h, 3c and 3d are admissible.** Runs 1-2f carry instrument defects; 2g is
  unreadable (defect 6); 3a and 3b are void — 3a on `--max-retries 0`, which was my own
  launch error, and 3b on the rate limit that flag exists to survive.
- **Run 3d is the cleanest: zero voids, zero truncations, 29/29 completed on both arms, and
  an exact 23/23 tie.** Launched `--max-turns 150 --max-retries 20 --max-concurrent 1`.
- **The defensible finding is cost, not accuracy.** bash re-sends its transcript once per
  turn, so it reports **8.0-10.7x the prompt tokens** (**6.9-8.9x** once the relay's own
  token counter is corrected for). Cost per solved task is **6.1-8.2x** higher:
  **$0.0126-0.0243** against PTC's **$0.0017-0.0035** at the relay's measured rates.
  Structural, on a co-primary declared in advance, and it holds at a tie.
  **⚠ CORRECTED 2026-10-10.** The token ratio reproduces exactly; the dollars did not. They
  were computed at $0.09/$0.18 per M against a measured $0.2186/$0.670, and the published
  range `$0.0071-0.0099` mixed cost-per-task-*attempted* (3d, 0.2067/29 = $0.0071) into a
  per-*solved* range that also omitted run 2h, whose bash per-solved is $0.0051 — below the
  floor it published. **Keep the token ratio and the cost ratio separate; merging them is
  how the error happened.** Audit and derivation: `ptc/relay_audit.py`, `docs/deviations.md`.
- **The tier pattern is consistent and never significant.** bash +18.2 then +9.1 pp on the
  11 cheap tasks, PTC -5.6 pp on the 18 full-scan tasks in both clean runs, interaction
  -23.7 then -14.6 pp, both CIs including zero, against a signed -25 pp threshold missed
  twice. Point estimates on this n, not demonstrated effects.
- **Co-training was never run and H2-H5 are unadjudicated.** Step 3 stays unstarted.
- **Outreach:** author email sent 2026-10-07. OSF node `2hfzt` private, loaded and
  md5-verified; public + DOI held to a reply or 2026-10-17. Its title and description were
  replaced 2026-10-11 from `docs/outreach.md`'s derived block, and two of its three files
  have been re-uploaded twice as the audit corrected them. Harness-Bench licence request
  open, zero comments.
- **This repository is public as of 2026-10-11** (`nikolas-sapa/co-train`), by the owner's
  decision, before the OSF node. The node is still private and the 2026-10-17 hold stands,
  so the findings are readable here first and carry no DOI.
- **A relay and pricing audit on 2026-10-10/11 corrected published numbers.** Cost per
  solved task was priced at an assumed $0.09/M against a measured $0.2186/M, so every
  dollar figure was ~2.4x low; the published `$0.0071` floor was a cost-per-task-*attempted*
  figure in a per-*solved* range; `8.5x` was two rounded cells divided; and the cost claim
  is now two ratios, not one — tokens 8.0-10.7x (6.9-8.9x de-inflated) and dollars 6.1-8.2x
  with a stated floor. Secondary 3 is **withdrawn**: its failure predicate only ever matched
  one arm's error strings, so bash's 1.000 was a floor artifact. Defect count 13, eleven
  fixed, one structural, one withdrawn — all derived from the ledger tables by
  `tests/test_defect_ledger.py`, which also pins the run count and the repair states.
- `ptc/paired.py` adjudicates (paired CI, exact McNemar, required n, tier split, and a
  refusal to read a partial run). `ptc/audit.py` answers whether an arm computes or
  guesses. **Run the suite as `.venv-ptc/bin/python -m pytest`** — the system interpreter
  has no `verifiers` and dies during *collection*, not at the end. A bare `pytest` is now
  correct: as of **2026-10-10** `pytest.ini`'s `testpaths` covers `tests ptc ledger`. It
  used to read `testpaths = tests`, so `pytest` collected 51 and silently skipped the two
  suites that matter — and this file documented that workaround instead of fixing the
  config. `step2` stays a separate invocation (`-m pytest step2`); it reaches the HF hub.
- **Never run the suite while a real-mode run is in flight.** It serves MCP servers the
  live run is also spawning; contention fails a server-dependent test for ~3 minutes and
  reads as a regression. Suite time over ~30s is the tell.

---

# History

**Everything below this line predates 2026-10-08 and is superseded by [Current
state](#current-state--2026-10-08) above.** It is kept, unedited, because a build log that
quietly rewrites its own premises cannot be audited — and because the step-by-step plan, the
hard constraints and the "do NOT do these" list are still the operative reference for Steps
3-6, which have not started. Read it for *why things are shaped this way*; do not read it for
what is true now.

The original header of this file, verbatim:

**Read this first. Then `research/02-synthesis.md`, `research/07-prior-art-closure.md`, then
`research/08-gap-closure.md` — which supersedes `07`'s novelty assessment.**
Status as of 2026-09-25: **research complete. Step 1 BUILT** (branch
`step1-nonsolver-gate`, 18 commits, 51 tests). Next: **Step 2.**
See `docs/superpowers/specs/` and `docs/superpowers/plans/` for Step 1's spec and plan.

---

## The question

> **Does co-training a small model against a programmatic-tool-calling (PTC) harness reverse the
> bash-over-PTC ordering that arXiv 2609.11999 measured on untrained models — and does the winner
> survive a harness swap?**

Both halves have published baselines. Neither has been run.

**⚠ CORRECTED 2026-09-25 — the gap is smaller than this document originally claimed.**
The `+21.8-24.5 pp` figure cited below is **bash vs Tool-only** (`tokens.md:100-105`), not
bash vs PTC. Bash − PTC, recomputed from Table 1 (`tokens.md:69-92`):

| Arm | Bash | PTC | Bash − PTC | 95% CIs |
|---|---|---|---|---|
| TAC / Opus-4.8 | 69.4 | 52.9 | **+16.5** | disjoint |
| TAC / GPT-5.5 | 67.1 | 45.1 | **+22.0** | disjoint |
| APEX / Opus-4.8 | 48.5 | 40.1 | **+8.4** | disjoint |
| APEX / GPT-5.5 | 44.6 | 37.8 | **+6.8** | **overlap 40.8-41.5** |

Range to reverse is **+6.8 to +22.0 pp**, and one of four arms is not significant. Worse for the
framing: at TAC/GPT-5.5 PTC already wins on cost ($0.54 vs $0.56) and tokens (242k vs 377k).
**Under a cost-per-successful-task metric the ordering is already reversed in one untrained arm.**
Choose Step 5's metric *before* the untrained run or the result is unfalsifiable after the fact.

**Why it is worth doing** (after four papers of prior art narrowed it):
- Every harness-native RL paper compares tool-calling harnesses to *other tool-calling harnesses*.
  The bash-vs-PTC axis has the biggest measured untrained gap (bash +21.8-24.5 pp) and is untouched.
- DCAS measured cross-harness degradation without training. LEGO-RL and OpenForgeRL trained without
  measuring transfer. Nobody joined the two halves.
- Nobody has tried any of it at 0.6-1.7B on free hardware.
- **A negative result is publishable and cheap.**

**Non-goals** (explicit): not building a trainer · not building RL env plumbing · not beating
frontier models on SWE-bench · not shipping a usable coding agent · not pretraining from scratch
(quantified as a detour in `06` §6).

---

## Build sequence

### Step 1 — ✅ DONE (2026-09-25). Five adversarial non-solvers + the gate.
`src/cotrain/contract.py` · `src/cotrain/nonsolvers.py` · `tests/leaky_env.py` ·
`tests/test_gate.py` + 3 test files. 51 tests. **Read `docs/HANDOFF-STEP2.md` before continuing.**
Five, not four: RDI's checklist is "a minimum bar", and observation-channel leakage
(WebArena ~100%, OSWorld 73%) needed its own agent — the gate was measurably blind to it.

### Step 1 (original text) — Four adversarial toy agents (do this FIRST, before the environment exists)
From Berkeley RDI's Agent-Eval Checklist: **null, random, prompt-injection, state-tampering.**
Rule: *"if any non-solver scores above baseline, the benchmark is considered broken."*

This is the cheapest high-value work in the whole plan and it is the concrete form of R24. It also
inverts the usual order deliberately: **you cannot write the verifier correctly until you have
something trying to break it.**

### Step 2 — ✅ DONE (2026-09-30). Prove the loop on free hardware
Kaggle, accelerator `NvidiaTeslaT4` (= T4 x2), **Unsloth** (not raw TRL — see Hard Constraints),
fp16, LoRA rank 16-32, Qwen3-0.6B, `use_vllm=False`, 5 steps. Goal is only: does it run and is
fp16 stable.

**`STEP 2 PASS`. fp16 GRPO is stable on T4.** 5 steps, 298 s, `grad_norm` finite and
positive throughout (1.72–2.43), `reward_std` > 0 every step so the gradient was real,
`kl` rising 1.3e-05 → 2.5e-02 — **the KL curve nobody had published**, which is why
`beta` was set to 0.04 rather than 0. Full analysis, caveats and stack in
`step2/results/`. Re-checkable with no GPU:
`python step2/verdict.py step2/results/step2_metrics.jsonl`.

**Consequence: the free path holds.** Rented Ampere is not required for Step 3 — and
per `08`, prime-rl could not have used a T4 anyway, so the two paths were disjoint.

Caveats, stated: not a learning run (the reward is output length, and reward hacking is
visible by step 4); entropy is unobservable because Unsloth hardcodes
`compute_entropy=False`; single-GPU; five steps is not a trend. The committed JSONL is
**reconstructed from notebook stdout** — Kaggle wiped `/kaggle/working` before it could
be downloaded.

`step2/` — gate check, run script, pass criteria, 73 tests, 59 mutants / 0 survivors.

### Step 3 — Verifier before environment
Snapshot-restored verification instance · constrained replay · verdict bound to a fresh
verifier-minted token · role separation so the agent never holds keys to the ledger it is scored on.
**Complete set or ship nothing** — RECEIPT's ablation: 45% (self-judgment) → **9%** (partial) →
100% (full). Partial hardening scores *worse than none*.
Then **test it both ways**: reference solution must PASS, planted mutant must FAIL.
Then **source-audit** it with **BenchJack** — **it shipped**: `github.com/benchjack/benchjack`,
Apache-2.0, 46 stars, pushed 2026-05-25, paper arXiv 2605.12673. The RDI blog's "preparing for
public release" is stale, which is why `06` recorded it as unlocated. Know what it is (`08` §4c):
a static + LLM audit pipeline that scans a *repository* against V1-V8 and shells out to
`claude --print` / `codex`. It is **not** an adversarial rollout, and the four toy agents are
**not** in it — they are a checklist item from the RDI blog, which is why Step 1 builds them.
For the runtime half add **`moogician/trustworthy-env`** (MIT, 62 stars, Z3-backed,
`detect.py audit --run-cmd`). Take two things from Harness-Bench's design (`08` §5.2): the
model/state secret split, and `Security ∈ {0,1}` as a **multiplicative** gate so a hack zeroes
the whole task rather than costing a penalty term.

### Step 4 — Environment, minimal action space, escalation channel from day one
Reward computed from state the agent cannot write. Structured escalation channel (cut hacking
23.6%→5.3% across 8 models at no perf cost, *and* doubles as verifier-QA). Plant one instrumented
rule-legal shortcut so hack telemetry is deterministic.

### Step 5 — Two harnesses behind one interface, measure untrained first
bash and PTC. **Confirm the published gap reproduces in your setup before training anything** —
and target the conservative **+6.8 pp** APEX figure, not the TAC number. `08` §6: APEX's "bash"
arm is a real `sh -c` server (the MCP-confound fear is **refuted** by the paper's own Appendix
B.2), but TAC's typed catalog is author-built and self-declared *"not every shell-accessible
endpoint"*, so TAC's larger delta is the one to discount.
**Evaluate `verifiers` before building two harnesses** (`08` §2.5): it already ships `bash` and
`rlm(builtin_tools=["ipython"])` — which is 2609.11999's PTC definition — behind one `Harness`
ABC, selected by `--env.agent.harness.id`. Add two leading indicators: tool-call **success rate**
(untrained PTC 65.2% vs bash 92.1%, Table 2) and **shell-call share** (OpenForgeRL measured RL
moving it 22.6% → 13.9%, its §5.3 — the closest published result to this project's question).

### Step 6 — Co-train, then evaluate cross-harness
Cross-harness eval from run 1. Report **billed cost**, not tokens. `mask_truncated_completions=True`.
**Pre-register token cost and stability as primary outcomes alongside score** — 2603.01209 held
everything but one runtime property fixed and found *"solution quality is statistically
indistinguishable across conditions, but token cost and stability differ substantially"*. State
the GRPO **grouping boundary** and test under an unseen harness (2609.04518, whose sealed
24,000-evaluation result is that the *evaluation* harness moves solve rate 4.3x where the
training recipe moves it 1.16x). Hold action-space **altitude** comparable across arms or declare
the asymmetry (`08` §8): a deliberately minimal PTC vocabulary makes a PTC loss unattributable.

---

## Hard constraints (expensive to rediscover)

| Constraint | Detail |
|---|---|
| **No local training** | Dev machine is darwin/arm64. prime-rl requires NVIDIA. All training rented or Kaggle. Every prime-rl GPU dep is gated `sys_platform == 'linux'`. |
| **prime-rl is Ampere+, not just "NVIDIA"** | Source, not docs (`08` §3): `DTYPE_MAP` has **no float16** and FSDP hardcodes `param_dtype=torch.bfloat16` (`trainer/model.py:98-101,471`), so **prime-rl cannot train on a T4 at all** — not slowly, not at all. Tested floor is RTX 3090/A100+ (`README.md:68`); the pinned flash-attn wheels carry sm_80/90/100/120, **no sm_75**. A rented T4 does not unlock prime-rl: the Unsloth-on-T4 path and the prime-rl path are **disjoint**, not two rungs of one ladder. `verifiers` (MIT, pure Python, runs on darwin/arm64) is the part that carries across both. |
| **Kaggle reality** | T4 x2 (P100 retired 2026-09-15), **30 GPU-h/week**, **12 h/session**, **20-30 min idle timeout**, 20 GB persisted at `/kaggle/working`. No A100/H100 free. Multi-process vLLM+trainer in one session is demonstrated (`kaggle-vllm`). |
| **T4 = no bf16** | Compute capability 7.5. bf16 needs 8.0. fp16 only. vLLM floor is 7.5, so T4 just clears it; **P100 (6.0) cannot run vLLM at all.** |
| **Use Unsloth on T4, not raw TRL** | A TRL PR exists *solely* because "T4 in collab need fp16 and vllm defaults to bf16." Unsloth ships 40 Kaggle GRPO notebooks and has done the fp16-on-Turing work. Migrate to TRL/prime-rl only when renting proper hardware. |
| **TRL trainability gate** | ⚠ **CORRECTED by Step 2 — see `step2/README.md`.** The raise is guarded by `if self.tools`: it is inside the multi-turn tool loop, so a no-tools GRPO run never reaches it. It does not exist at all in TRL ≤ 0.24.0 (`trl/chat_template_utils.py` is 404 at that tag; `self.tools` appears zero times), and **Unsloth pins `trl<=0.24.0`** — so on the Step 2 stack the gate is absent, not merely unfired. Qwen3-0.6B **does fail** the check where it exists (it drops `<think></think>` from history), but TRL auto-repairs it via `get_training_chat_template`, verified False→True here. **The proxy escape hatch is not needed.** Steps 5-6 are a different matter: PTC *is* tool calling, and that path does not exist on the Unsloth stack. |
| **`verifiers` is pinned to a commit, not a tag** | `ptc/requirements.txt`: `69cc0f9` in `.venv-ptc` (py3.12, reports 0.3.2.dev137). No released tag works — `ptc/harness.py` imports `verifiers.v1.harnesses.utils.mcp`, which was only factored out of the per-harness `program.py` copies *after* the newest tag v0.3.1, so going back through the tags moves away from it. The ref was recovered from `docs/spike-verifiers.md` §Environment, which recorded it; it was **not** re-derived from matching module paths, and PyPI `verifiers` (0.1.5, no `v1/` tree) is a different package. The `glossary` taskset is pinned to the same commit as a `#subdirectory=` — it is `--taskset`'s default and is **not** on PyPI, and the spike had it installed from a since-orphaned `~/scratch/` clone. |
| **`NCCL_CUMEM_ENABLE=0`** | Set before any vLLM weight sync. 180 s → 4 s on 70B. One env var. |
| **Sandbox cost ≈ GPU cost** | 256 concurrent rollouts ≈ $42/hr (E2B/Daytona), $61 (Modal), $3.5-9 (Fly Machines). E2B Hobby caps at **20 concurrent** — unusable. Wall-clock billed, so idle environments cost money. |

## Budget
Smoke test $5-30 · first real experiment **$60-200** (probably conservative: Garg ran 20+ GRPO
ablations for ~$140 total; GRPO-Zero does Qwen2.5-3B on one A40 for $1-2/run) · serious $1,500-10,000.
**Free path exists**, capped at ~0.6-1.7B by the 12 h session and T4 speed (~15x slower than H100).

---

## Do NOT do these (learned the expensive way)

1. **Do not prompt the agent not to cheat.** Measured at zero effect or negative: BAITBENCH stays
   >50% under an explicit no-cheat prompt; a restrictive prompt was *fastest* to hack; Prime Agent
   defeated an explicit heartbeat.
2. **Do not read the score from state the agent can write.** WebArena scored ~100% by opening the
   task config over `file://`. Factorio's Production Score was read from the game's own counters and
   RCON wrote them directly.
3. **Do not audit only application state.** RDI's exploits include a fake binary on `$PATH`, a
   pytest plugin hook, and uninitialized GPU memory holding the evaluator's prior answer.
4. **Do not ship a partially hardened verifier.** 9% precision is worse than the 45% you get with
   none, because it produces confident wrong verdicts.
5. **Do not put an LLM judge in the reward.** Doubles compute per step, adds systematic bias, and is
   a documented hack surface (V4).
6. **Do not compress the observation to save tokens.** AgentOccam tripled success while *increasing*
   observation tokens 33%. The only token-reducing step was cutting the action space — which was
   also the biggest single accuracy gain. **But "shrink the action space" is a rule with an
   exception** (`08` §8): shrink same-altitude primitives, do **not** cap abstraction depth.
   SCAFFOLD, on the same 7B base, beat AgentOccam 42.7 vs 16.8 with a *larger* recursively
   composed vocabulary; flattening it to depth ≤ 1 cost 6.3 pp and leaving it unpruned cost 3.1 pp,
   so the optimum is interior. NapMem is the trained version of the same shape: the wide interface
   **prompted** (48.39) loses to the narrow one (54.08), the wide interface **trained** wins
   (62.74). Expect narrow to win at 0.6-1.7B anyway, and pre-register that.
7. **Do not trust vendor docs over vendor source.** Bit twice this research: Kaggle's docs still say
   P100; TRL's doc URLs 404'd while the source was fine. Check the repo or its test suite.
8. **Do not let a research agent own a file-writing contract.** The `research` agent type's tool
   grant changed mid-session; two lanes lost their reports. Have them return content, you write it.

## Health signals to log from run 1
Gradient norm · `mean_response_length` · token entropy · reward_std. Garg's collapse signatures:
lr 1e-4 → policy collapse and entropy to zero (3e-5 stable); off-policy reuse of 16 steps → collapse
mid-run; removing the group-mean baseline → gradient blowup. Stay on-policy.

---

## Known unknowns
Five of these closed on 2026-09-25. Detail and sourcing: `research/08-gap-closure.md`.

- **fp16 GRPO on Qwen3 — narrowed to the KL curve only** (`08` §7). A public Kaggle **2×T4**
  run settles the rest: `rkkzone/qwen3-0.6b-math-l45-grpo-adapter` ships `training_logs.json`
  and `hardware_profile.json` — `fp16=True`, `bf16=False`, `use_vllm=False`, dense Qwen3-0.6B,
  **314 steps over 5.9 h, 2.40 GB peak VRAM, zero non-finite values** in loss/grad_norm/reward.
  It logged no KL (`beta=0`); a sibling run with `beta=0.04` finished and merged but published
  no log. **Mechanism confirmed in source, and it flips one corpus assumption:** Unsloth
  force-float32s `qwen3_5` and `qwen3_moe` for *"NaN grad norms in float16 training"* but
  **not dense `qwen3`** (`loader.py:118-127`), and Qwen3 has **QK-norm** where Qwen2 has none
  (`modeling_qwen3.py:237-238`), bounding exactly the attention logits that used to overflow.
  So Gemma-3's failure does not transfer to *dense* Qwen3 — but it **does** transfer to Qwen3.5
  and MoE. **Model choice is load-bearing: pin dense Qwen3-0.6B/1.7B, never Qwen3.5 or MoE.**
  Unsloth's fp16-on-T4 path is by design (`rl.py`: *"V100/T4 never pick bf16"*) and carries
  no-bf16 regression tests; TRL's 5,073-line GRPO test file has **zero** `fp16` hits and its
  GPU CI left Turing (T4 → L40S). That asymmetry is why Step 2 stays on Unsloth.
- **Harness-Bench — FOUND**: `github.com/Qihoo360/harness-bench`, 112 stars, in **footnote 1**
  of the paper, invisible to arXiv metadata. 106 task dirs verified real (`task.yaml` ×106,
  `oracle_grade.py` ×106, 812 fixtures), plus 12 harness adapters. **No LICENSE file →
  all-rights-reserved.** Read it, do not vendor it. Also: *"106 oracle-checkable"* is
  overstated — the criterion is *"deterministic checks **or a specified rubric**"*, 86 tasks
  ship an `llm_rubric.py`, and the aggregate multiplies in an LLM judge, which rule #5 bars
  from a reward. Usable subset is `Security × Completion`.
- **OpenForgeRL code — FOUND**: `github.com/MSR-Orchard/OpenForge-RL`, 17 stars, default branch
  **`master`** (so `/main` 404s). The v3 "added github link" is the vanity redirect
  `aka.ms/OpenForge-RL`, which is why a `github.com` search missed it. Recording proxy is real
  (58 KB `vllm_proxy.py`). **No LICENSE.**
- **R33 dispersion+level screening** for continuous rewards — still unvalidated, publishable
  either way, and now **corroborated by that public run**: its reward went flat with
  `frac_reward_zero_std` at 0.56-1.00, i.e. most groups carried zero advantage. Signal
  starvation, not numerics. Log this metric from step 1.
- **Full texts of 2607.21557 and 2605.27922 — now read** (`08` §5). Three corpus claims fell,
  the largest being that OpenForgeRL **does** run a cross-harness transfer test (its §5.2,
  Table 5) — `07` read only the abstract.
- **Still genuinely open:** the KL curve at `beta>0` on T4; whether any of this reproduces at
  0.6-1.7B; and whether 2609.11999's untrained gap reproduces at all (zero citations, §6).

## Three publishable experiments sitting in the gaps
1. Token-meter ablation (with vs without charging the agent for its own output tokens) — never run.
2. RECEIPT-grade tamper-proof verifier ported to an economic environment — the bench lane's own
   synthesis, unpublished.
3. Dispersion+level screening for continuous-reward environments — no paper does it.

---

## Corpus map
| File | Read when |
|---|---|
| `research/02-synthesis.md` | **Start here.** The decision, + addendum folding in bench/browser. |
| `research/07-prior-art-closure.md` | Before committing to the thesis. Honest novelty assessment — **partly superseded by `08` §1**. |
| `research/08-gap-closure.md` | **Read with `07`.** Closes 8 gaps: novelty narrowed to one axis, four transfer scoops, three "missing" repos found, fp16 unknown narrowed to KL, counter-evidence to "shrink the action space", and `verifiers` vs our `contract.py`. |
| `research/06-perplexity-delta.md` | Before touching Kaggle or the verifier. fp16 + BenchJack + costs. |
| `research/03-free-compute.md` | Setting up the free path. |
| `research/05-delta-tierlist-and-rdi.md` | Verifier design. RDI broke 8/8 benchmarks. |
| `research/lanes/bench.md` | Environment design. **34 rules**, R1-R6 are the load-bearing ones. |
| `research/lanes/grpo.md` | GRPOTrainer API, loss masking, failure modes. 1,336 L. |
| `research/lanes/harness.md` | Harness-overfitting evidence. 1,661 L. |
| `research/lanes/tokens.md` | The bash-vs-PTC measurement this project is built on. 936 L. |
| `research/lanes/browser.md` | Only if the environment touches the web. 668 L. |
| `research/lanes/compute.md` | Pricing, VRAM, wall-clock. 793 L. |

## Standing caveat
Retrieval was degraded for the whole research phase: WebSearch broken, `exa_search` off, Semantic
Scholar 429'd, Twitter/Reddit unavailable. Every lane source is arXiv, GitHub, or a vendor doc.
**Practitioner evidence arrived only via user-supplied Perplexity reports** (`06`), and was not
independently verified beyond the load-bearing claims listed in that file's Verification section.
`08` ran under the same broken `WebSearch`, using `curl`/`gh`/arXiv-API/OpenAlex and repo clones;
every load-bearing claim there was re-verified against the primary artifact (paper full text,
repo, or committed run log) rather than a lane report.
**One risk unchanged and now quantified:** arXiv 2609.11999, the measurement this whole project
rests on, has **zero citations** by five independent routes (OpenAlex, Scholar, HF papers,
full-text grep, Semantic Scholar). It is unreplicated, uncriticised and first-party. Step 5's
untrained reproduction is not a formality — it is the experiment that decides whether the premise
is real.

## Starting the next session
**Read `docs/HANDOFF-STEP2.md` first.** It carries what Step 1 learned, the corrections it forced
into this document, and the constraints Step 1 now places on Steps 3-5.

Invoke `/superpowers:brainstorming` before writing code — the project-level skill gate requires it
for new feature work, and the environment design genuinely has undefined scope.
