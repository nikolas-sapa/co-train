# Registered owned SQL SDK binding

2026-10-31, base a718cf5. Architecture selected by source review and bounded
feasibility spikes. Not implemented or production-approved.

## Tests first

Unit contracts precede implementation. Missing symbols fail in the call phase,
not by skip or collection failure.

| Gate | Numeric acceptance |
| --- | --- |
| Admission/settings | Actual load_validated_draw with independently retained digests; 8 planned, 7 eligible, 1 exclusion in original order; all planned DB records including excluded-only DBs. Wrong digest/settings: 0 policy/dispatch. |
| Registration/config | Stock JSON resolves exact registered classes. Unbound/forged/reused admission and unsupported config refuse before evaluation entry. No agent.harness replacement or global name-to-private-task lookup. |
| Coverage | Every exact admitted eligible Task is selected in original order. For 7 eligible Tasks, num_tasks=6 or 8 and shuffle=True refuse before eval/policy/dispatch; None or exactly 7 is supported. Declared positive integer num_rollouts applies equally to every eligible Task. |
| Association | Two concurrent distinct Tasks and two concurrent samples of one Task: four isolated scopes/traces/scorers. Cross/stale/substituted token, Task, Data, harness or Trace, including equal nonidentical replacements: 0 unauthorized dispatch/reward. |
| PROGRAM proxy | Second overlapping run_program refuses before delegation. Synchronous timeout delegation. Exactly 1 actual close task shared by harness/scope; reject new work after failure/closing. |
| All-close ordering | Hold first active runner cleanup; every other actual retained close enters before first release. Already-completed close reuse is insufficient. |
| Score lifecycle | Per success setup/finalize/score/extract/scorer dispatch/reward each exactly 1, finalize before score, scorer close before reward. Four invalid statuses: 0 rewards; valid zero is native only. |

Original SDK/canonical-actor integration must retain registered classes, Agent,
scoring gather/wait_for, evaluator and original JSONL writer:

1. Repeat concurrency/identity gates through SDK; original task identity and one
   valid reward per successful trace. No oracle SQL/host DB paths in policy data.
2. PROGRAM and SCORER each: 3 actual caller cancellations, 2 during held cleanup,
   acknowledge each delivered interruption before next cancel. Original owner,
   intent/deadline/close-task/ACK authority retained; dispatch and public owner
   close each once.
3. Stock scoring wait_for(0.1) cancellation retains held cleanup before scope
   exit/writer; 0 rewards/successful rows. Failure rows allowed after drain.
4. Failing Harness.score sibling leaves actual Task.score child retained,
   cancelled and joined. No late reward or surviving score task after exit.
5. Real original cancellation deadline plus 30ms (12s+30ms): pending, no reward/
   writer callback/revocation. Independent shared 19.5s canonical SAFE teardown
   does not substitute for public owner completion.
6. Setup/generation failure after scorer admission drains scorer before writer,
   0 successful rows. Invalid gold_error/gold_timeout/gold_truncated/db_missing
   each: 0 rewards/successful rows. Success means episode OR any trace ok.
7. Association, invalid-to-zero, score-close-before-reward and SEPARATE Env
   writer-barrier bypasses each hit once, fail named acceptance, then pass fresh
   restored positives. Reward-barrier sensitivity is not writer-barrier proof.

## Selected layout/API

One production module, `cotrain_owned_sql.py`; no support module/new manifest.

```python
@dataclass(frozen=True)
class OwnedSqlDrawInput:
    root: Path
    draw_path: Path
    supplement_path: Path
    expected_draw_sha256: str
    expected_supplement_sha256: str
    fixture: bool = False

def build_registered_owned_sql_binding(
    *, draw: OwnedSqlDrawInput, executor: PilotExecutor,
    instrument: InstrumentSettings, public_data: tuple[TaskData, ...],
) -> RegisteredOwnedSqlBinding: ...

async def run_registered_owned_sql_eval(
    config: EvalConfig, *, binding: RegisteredOwnedSqlBinding,
) -> list[Episode]: ...
```

Opaque single-use host holder, not authority by matching type/reconstructed
metadata. Builder calls actual load_validated_draw with both retained expected
digests; never freshly hash supplied documents as authorization or accept a
manufactured ValidatedDraw. Associate original eligible SqlTask objects directly
with exact caller-associated TaskData in order; retain complete planned/excluded/
DB partition privately. Public association is not semantic prompt provenance.

Require instrument.scorer_timeout_s/max_rows/compare equal admitted timeout_s/
max_rows/comparison. Registered program_timeout == instrument.program_timeout_s
== 5; max_turns == instrument.action_cap. PROGRAM receives action_max_rows,
SCORER receives scorer_max_rows. Do not conflate them.

Wrapper validates supported registered pairing before stock run_eval. Reject
retry/resume/push/clean, deferred/custom scoring, judges/plugged rewards,
custom toolsets, QA/MCP and task/interceptor rewrites outside this contract.
No silent rewriting or policy/provider/profile selection.

Selection contract: `num_tasks` must be None (stock all) or an exact integer
equal to admitted eligible count; `shuffle` must be False. Reject smaller/larger
counts, filters, substitutions and taskset system-prompt overrides before
evaluation entry. Seal declared positive exact-integer `num_rollouts`; retain
the exact complete Taskset and ensure each eligible Task is played that many
times, with no omission/duplication beyond the declared samples. Concurrent
single-Task sample isolation is observed within that complete selection, not
by truncating the admitted Taskset.

The binding preserves planned/excluded membership, but returns eligible SDK
episodes. Stock eligible-task reward mean is NOT planned-denominator BIRD
accuracy. Even full eligible coverage establishes neither an eight-item BIRD
metric nor the paired runner; no aggregate estimator is added here.

## Registration and scope

OwnedSqlHarnessConfig extends PTCHarnessConfig; OwnedSqlTasksetConfig extends
TasksetConfig; OwnedSqlEnvConfig extends SingleAgentEnvConfig. Each id is literal
`cotrain_owned_sql`. Registered subclasses:
OwnedSqlHarness(PTCHarness, Harness[OwnedSqlHarnessConfig]),
OwnedSqlTaskset(Taskset[OwnedSqlTask, OwnedSqlTasksetConfig]),
OwnedSqlEnv(Env[OwnedSqlEnvConfig]).
`__all__` exports exactly those three registered implementation classes.
Config loading alone grants no execution authority.

Taskset yields original Tasks holding original private associations. Env.run
creates one rollout scope binding live token, admission, exact Task/Data/harness
and setup-bound exact Trace/runtime. ContextVar routes lookup, not authorization.
All sensitive hooks revalidate associations. No rollout state on reused Task/
shared harness. Await original agents.agent.run(task), never swap harness.

## PROGRAM retention

Build fresh ordinary owned PROGRAM harness with exact ordinary PTCHarnessConfig,
preserving admitted fields with explicit base-config ID. Capture original public
program_runner_factory once; synchronous wrapper delegates unchanged, retains
actual returned runner before validation/await, returns private protocol proxy.

Proxy delegates synchronous validate_program_timeout; run_program guards one
active call and sticky failure/closing; start_close creates exactly one actual
runner.aclose task; every aclose caller joins that task through repeated cancel.
Single active call prevents a second live job behind original sequential close
traversal. No closure/private-job inspection, executor replacement, global owner
registry or new PROGRAM-builder parameter.

Private unit seams inside this same module: `_ProgramLease(actual, check)`
implements the proxy protocol above, with a synchronous no-argument scope check.
`_CloseSet` retains resources by identity via `retain(resource)`, starts/shares
one actual resource-aclose task via `start(resource)`, and `start_all()` creates
all known close tasks before returning their tuple. `join_all()` starts all,
then retains/join-drains every task through caller cancellation, rejecting failed
or non-None closes without replay. New resources refuse after start_all seals
the set; existing task reuse remains allowed. This helper is cleanup bookkeeping,
never association/ACK authority. Scope retains scorer and PROGRAM proxies here;
Task.score and Env cleanup share the scorer's one close task.

## Hooks and publication

Task.setup binds exact Trace/runtime once; construct and retain scorer BEFORE
potentially failing synchronous admit, before policy. Harness.setup validates
association; launch delegates fresh ordinary owned harness/real SQL catalog.
Harness.score retains its actual current stock-gather task before base scoring.
It latches success/failure and signals completion in finally. With custom
metrics forbidden, Task.score also waits for successful harness scoring before
publication; an immediately completed scorer must not reward ahead of a
failing sibling. Test this fast-scorer/late-sibling-failure race explicitly.

Task.finalize validates/latches once and NEVER closes scorer: SDK finalizes
before scoring. Task.score retains actual stock child before first await,
requires finalize/latches once, extracts SQL once, awaits owned score and shared
scorer close before reward. Preserve actual decoded ExResult/infrastructure
exception. Invalid/infrastructure branches never manufacture zero or reward.
Recheck live publication authority, sticky failure and current cancellation
immediately before trace.record_reward("execution_accuracy", result.score).

Env.run owns one retained cleanup task in its own finally: synchronously stop
new work/rewards; start ALL retained proxy/scorer closes before joining ANY;
cancel unfinished retained scoring children; join closes/children and observe
failures; revoke/reset context only after resolution; propagate failure/cancel.
Unknown remains pending, no extra deadline. Harness.cleanup is not the barrier:
SDK suppresses its ordinary exceptions after trace.ok assignment.

## Reference, evidence limits and implementation order

[Working reference](spikes/reference/sql-sdk-owned-scope/) preserves the pattern.
Scratch PROGRAM 3 passed/2.17s, strengthened SDK 5 passed/2.53s; fresh reward
negative/restored each passed. Portable combined reference: 8 passed/2.54s.
Python/security approved bounded synthetic scope. PROGRAM was inert with
completed-close reuse; SDK used cooperative events/text-only empty catalog.
Neither proves active owned ACK, real SQL, production catalog, concurrency or
Env writer-barrier sensitivity.

The [pending-before-result sibling reference](spikes/reference/sql-sdk-owned-scope/sibling_probe.py)
retains the original guarded scheduling probe (1 passed/3.95s, 2026-11-01).
Original SDK Harness.score fails while Task.score waits before a result;
unchanged Env cancels/joins it through held public cleanup. This is MOCK-result
composition only, not actual-owned sibling/ACK/SAFE qualification or the
fast-completed-close/late-sibling race required above.

Architecture has no unresolved API/layout alternative. Production approval is
BLOCKED on all named actual-owned/canonical-actor gates. If unchanged SDK
cancellation/timeouts escape scope into success/unowned score work, report
architectural failure. Never patch SDK/remove wait_for/relax caps or authority.

Order: minimal admission/registration unit tests RED; remaining protocol units
RED; implement selected module; unit mutations/restores; original SDK/canonical
actors including active all-close/independent writer fault; reviews/publication.
Already-authorized bounded first-party scripted loopback needs no new approval.

## Non-goals

No real native/profile/provider/model/corpus/spend activation, source repinning,
install/download/new manifest/SDK modifications. No SQL-correctness claim;
SQLite42/EX1/VM-progress remains separate. Research4/5 PARTIAL,6 BLOCKED, BIRD
baseline missing, not zero.
