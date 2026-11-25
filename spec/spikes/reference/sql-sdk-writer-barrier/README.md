# Writer / late-sibling feasibility spike

**Strong late race BLOCKED. Independent Env writer barrier measured in COMPOSITION.**
No native execution, ACK, SAFE, provider, model, training, SQL accuracy or
publication qualification. Runtime tests use controlled synthetic SQLite
preparation before the inherited native/SQL denials. The standalone source CLI
does not execute the SDK.

## PROVES

Installed `verifiers==0.3.2.dev137`, read-only source under the qualified
environment's `site-packages/verifiers/v1/`:

## Numeric test plan (recorded before runtime implementation)

Approved clarification: unchanged `_prepare` may create controlled synthetic
first-party SQLite fixtures BEFORE denials. SQLite/native/process/signal/external
access remains denied throughout actual SDK execution. The earlier fixture-gap
conclusion below is superseded by this clarification.

1. Preserve the 3 existing source/stdlib checks and all 22 snapshot hashes.
2. Baseline within 3s: one exact admitted target uses original ScriptedClient
   with zero scripted steps, 1 original generation error, 0 target score calls,
   0 target rewards. Original Agent completes; one public scorer close is held.
   At original Env cleanup await: cleanup pending, live/token retained, 0 actual
   target JSONL rows. Release only close gate; original cleanup completes.
3. ONE-edge mutant within 3s: bypass `_settle` ONLY when caller code is original
   OwnedSqlEnv.run, current task is its observed target invocation, and argument
   IS that target's retained cleanup task. Original Task/Harness/Env/SDK/writer
   code identities and AST await site stay unchanged. Every other settle
   delegates unchanged. Same natural generation fault, no omitted injection.
4. RED must be the named actual-writer assertion: exactly 1 failed target
   serialized row appears BEFORE held close/cleanup finish. No target rewards
   or success. Do not fabricate a row or alter writer. Assert exact error
   code/AST raise site, not timeout/unrelated refusal.
5. Release only test close gate. Join ALL observed real tasks/closes, zero native
   jobs/forbidden attempts, 7 final JSONL rows / 6 ordinary successful MOCK
   siblings. If mutant irreparably skips original live/token revocation, record
   that defect, never repair authority or claim normal scope retirement.
6. Restored baseline repeats item 2. Command timeout <=30s, scenario cap 3s.

Non-goals: strong late-sibling unblock, native ACK/SAFE, production/API/SDK edits,
generation-track edits/imports, fault omission, Task-score barrier bypass,
manual authority repair, installs, git/deploy or activation approval.

| Source | Actual relevant path |
| --- | --- |
| `rollout.py:497-505` | Stock gather schedules Task.score then Harness.score. |
| `harness.py:214-228` | Base Harness.score discovers metrics, awaits invoke_all, then records results. |
| `utils/decorators.py:11-26,41-45` | MRO metric discovery; invoke_all awaits gather of its handlers. Zero handlers means gather of zero children. |
| `errors.py:75-89` | Boundary generator yields once, has no await. Enter/exit adds no suspension here. |
| `agent.py:387-436,655-673` | Original Agent run / episode run path; completed trace appended after base run. |
| `task.py:203-274` | Base scoring handles metrics/rewards/judges, not an extra Harness awaiter. Owned Task overrides this method. |

Worktree `cotrain_owned_sql.py`:

- `804-816`: admission rejects decorated metric/reward/stop/intercept methods
  throughout supported class MROs. `847-849` also rejects configured task
  judges, metrics, rewards and stops.
- `677-691`: original Harness.score directly awaits super.score, immediately
  calls scope.check, then marks success; finally sets harness_done.
- `523-526`: original Task retains result, awaits public scorer join, then
  awaits harness_done. `543-544` publishes only after those gates.
- `192-205,566-570`: a new scorer public-close task is scheduled, not executed
  inline; `_settle` shields/awaits it. Existing default gather scheduling has
  already queued Harness before this newly created close task.

Thus both ordinary schedules miss the requested **completed-close before
late-original-Harness-failure**:

1. Scorer suspends: Harness reaches post-base check before result.
2. Scorer returns inline: Task retains result and yields to its newly scheduled
   public close; already queued Harness reaches post-base check before close.

The base Harness await chain has no suspension with zero metrics. A successful
empty `asyncio.gather()` is already done: measured **0 scheduler turns** during
its await. Async syntax alone is not an awaiter seam. The existing pending
pre-result sibling proof and a held-close/result-retained proof are strictly
weaker, not substitutes.

Minimal missing capability for the strong race: an **approved original
suspending Harness operation** before its post-base check (or a separately
approved scheduling-contract change). Adding metrics, patching SDK invoke_all,
delaying a protected Harness method, or replacing the task factory would change
the frozen experiment. This spike does none of those.

## Independent Env writer barrier: composition sensitivity

This snapshot has **no OwnedSqlEnv.__aexit__**. Its actual per-episode barrier is
`OwnedSqlEnv.run` at `cotrain_owned_sql.py:772-796`:

1. Stop authority.
2. Start ALL closes.
3. Create retained `_drain_scope` task.
4. Await `_settle(scope.cleanup_task)` at **776**.
5. Revoke live/token only when cleanup_task.done().

`_settle` is unsealed. The runtime control bypasses only this target Env await,
using original caller code/AST line, current task and cleanup-task identity.
Every other settle call delegates unchanged. Task's pre-reward join and the
original Task/Harness/Env/Agent/evaluator/writer methods stay unchanged.

Actual persistence chain:

- SDK `env.py:269-288`: run_episode awaits self.run, records failures.
- SDK `env.py:350-355`: run_slot awaits attempt/retries, then on_complete.
- SDK `cli/eval/runner.py:148-151`: on_complete invokes original append_episode.
- SDK `cli/output.py:147-154,176-191`: original serialization/file append runs
  in a worker, retained by run_shielded.

The writer does not independently consult scope.cleanup_task. Returning past
the Env edge can therefore make a **failed target row** eligible for writing
while cleanup is pending. The control observed exactly one such failed target
row, with zero target rewards and no successful target publication. Original wrapper checks at
`cotrain_owned_sql.py:918-927` occur after run_eval, after streaming writes, and
only examine successful episode/trace records.

The unchanged `_prepare` creates controlled synthetic SQLite files before
installing denials. That preparation is permitted; SQL/native execution remains
denied during the SDK run. Six siblings use explicit ExResult MOCKs. The exact
admitted target uses original `ScriptedClient([])` and never scores. Its original
generation exception identity/code/AST raise site is preserved, including in
the bypass control. No failure is omitted and no row is manually written.

Baseline: actual target scorer-close and Env-cleanup tasks remain pending,
token/live state retained, authority stopped, zero target rewards/rows.
Bypass: original writer emits one failed target row before those tasks finish;
the unchanged oracle raises `SDK_WRITER_BEFORE_ENV_DRAIN`.
Releasing only the test close gate joins all original tasks/resources. All
seven rows exist, six ordinary MOCK successes and one failed target.
The mutant's skipped token/live revocation remains visible AFTER cleanup,
while authority and admission are inactive. The fixture never repairs it or
claims normal scope retirement for that mutant. Restored baseline revokes all
tokens normally. This is not native ownership/unknown-cleanup qualification.

## Runnable evidence and limits

`probe.py` reads ten exact source files and emits portable relative source
labels with their SHA-256 provenance, not private installed-source paths.
It never imports/executes verifiers or production root code. Therefore no SDK
execution requires a native-denial fixture; no native calls occur.

`ptc/test_owned_sql_sdk_writer_barrier_probe.py` has **4 source/stdlib checks**:
source topology, zero-turn empty gather, and an in-memory one-edge AST deletion
that the source detector rejects. That deletion is never compiled/executed.
Those source checks alone are **not** runtime writer proof. First run found a quote-sensitive
source assertion (1 failed / 2 passed); fixed to structural AST equality.
Initial source-only run: **3 passed in 0.04s**. The new fourth check rejected
absolute source paths at `PRIVATE_SOURCE_PATH_DISCLOSURE` (exit1, 2.94s),
then passed after portable labels replaced them; source hashes are retained.

Three separate runtime cases test original barrier, exact one-edge bypass and
fresh restored barrier. An uncaught mutation changed only the new helper's
`writer_bypass` default to True: original baseline failed at the real writer
oracle, exit1, **1 failed in 3.24s**, not a timeout. Restoring that default False
gave exit0, **7 passed in 3.71s**. The caught negative case additionally checks
the exact original oracle code and AST line. No source/SDK/production mutation.

Run all seven using
`ptc/test_owned_sql_sdk_writer_barrier_probe.py`. The standalone `probe.py`
remains source-only; its unmeasured-runtime field describes that CLI, not the
separately executed composition tests.

Run from the isolated worktree with qualified Python, offline environment,
`-I -B -m pytest -p no:cacheprovider`, command timeout 30s. No runtime UNIT
watchdog was added or increased. No production/snapshot/SDK file was edited.

**SHORTCUT:** source/stdlib facts plus original SDK composition with ordinary
MOCK results and an event-held empty-job scorer close.
**MISSING:** strong late-sibling race, independent full writer-payload privacy
qualification, actual-owned/native ACK/SAFE and unknown-at-deadline proofs.
Do not promote this spike into an activation/acceptance gate.
