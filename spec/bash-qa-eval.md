# Bash QA evaluation integration, test-first contract

2026-10-31. Base `95a4596`, branch `feat/bash-qa-eval`.
Architecture APPROVED after actual lifecycle/persistence spike.
Implemented; bounded acceptance recorded in the
[usage/evidence](../docs/2026-10-31-bash-qa-eval.md). No bare stock CLI support claim.

## Required tests before implementation

| Named test | Numeric pass criterion |
|---|---|
| Real Env loading | Exactly 1 intended Env/config and Taskset resolve through actual EvalConfig JSON; canonical harness preserved across round-trip. |
| Real evaluation activation | 1 synthetic episode through actual SDK evaluation/episode agent, with 1 configured runner invocation and 1 fresh channel. Zero manual harness swaps. |
| Receipt before action | 1 report consumed; receipt present in the request preceding the next scripted policy action, not merely in final history. |
| Explicit task preservation | Builder receives 1 fresh binding. Paired Task preserves exact seed data/config and framework-valid concrete task behavior; overrides score identically. No arbitrary automatic wrapping. |
| Clone preservation | Every clone/system-prompt transformation traversed by actual evaluation preserves task semantics and fresh binding admission. Zero dropped intent or scoring overrides. |
| Sequential isolation | 2 episodes use 2 distinct bindings/channels, with zero cross-episode reports. |
| Concurrent isolation | 2 barrier-proven overlapping episodes use separate Agents and channels; zero cross-episode reports or process-global PATH mutation. |
| Persisted telemetry | Successful and failing supported episode each recover bounded QA metadata from actual SDK-written output. Zero reward/gold/validity changes. |
| Admission refusal | Each forbidden wrapper flag/config tested separately: zero SDK calls. Unsupported seed/callback/identity/settings: zero policy/tool actions. |
| Scoped admission | Bare/direct Env execution, nested wrapper and unrelated Env refuse with zero builder/factory/policy calls. One admitted Env instance only. |
| Revoked admission | Success, exception and cancellation leave zero usable admissions, including child tasks inheriting the old context. Subsequent normal fresh wrapper call succeeds. |
| Metadata failure | Existing fixed-key collision, export and attachment failures propagate, never overwrite or silently succeed. Prelaunch failure creates zero fabricated QA entries. |
| Pre-start toolset refusal | Custom seed/taskset toolset hooks, inherited/stateful overrides and custom task-type selector refuse at construction: zero overridden hook/selector calls, zero MCP/shared starts and zero policy/tool calls. |
| Cleanup | Success/failure/cancellation restore original harnesses and release owned routes/wrappers; subsequent fresh episode succeeds. |
| Bounds | Existing collector max/max-plus-1 behavior remains unchanged; telemetry never exceeds existing bounded export limits. |
| Ordinary evaluation | Existing ordinary evaluation remains unchanged and does not import QA plugins or allocate channels. |

Required actual controls, with immutable source/test/spec hashes:

1. Suppress the new Env-to-configured-runner activation boundary. Intended
   call-phase activation assertion RED, baseline/restored GREEN.
2. Suppress receipt forwarding after collector consumption. Intended call-phase
   receipt assertion RED, baseline/restored GREEN.
3. Suppress the new QA attachment helper. Intended call-phase `QA telemetry`
   assertion RED, baseline/restored GREEN. Collector/receipt still work.
4. Suppress `_check_tool_free(taskset_class)`. The startup-sentinel test must fail an
   intended `pre-start toolset` assertion, restored GREEN. Never actually start
   a provider/MCP service in this negative fixture.

Neither setup/collection errors nor unrelated network/runtime exceptions count.
No warning suppression, fake process, private permit bypass or mocked forwarding
in the baseline. Temporary listeners bind only 127.0.0.1:0, scripted clients,
zero external fixture provider/platform calls, <=20s outer fixture bound.

## Confirmed references

[Construction-only reference](spikes/reference/bash-qa-eval-loader/probe_env_loader.py)
proves actual EvalConfig JSON narrowing, flat Env/config specialization,
synthetic Taskset loading and canonical unbound reporting harness construction.
It deliberately refuses execution. Parent also executed and promoted the
[real evaluation reference](spikes/reference/bash-qa-eval-execution/probe_eval_execution.py):
actual `run_eval` -> SDK `_EpisodeAgent` -> existing configured runner -> real
child HTTP/tool gate -> 1 report, receipt at call 2 -> identical QA in actual
SDK JSONL. Original harness restored; seed/trace task hashes equal; owned
listener/runtime torn down. Parent socket/DNS guard observed zero external
attempts. Both scratch and promoted execution runs GREEN.

Confirmed: stock SingleAgentEnv calls bare Agent.run and cannot activate the
existing enforced QA composition. SDK creates episode Agent subclasses; their
runner compatibility and trace persistence now have actual spike proof.
Source-confirmed Taskset system-prompt copy precedes the explicit builder;
override-rich clone/scoring acceptance tests remain required.

## Exact implementation contract

Only new product `cotrain_bash_qa_env.py`, flat canonical Env ID
`cotrain_bash_qa_env`. Existing product/SDK/collector/training guards unchanged.
Tests `ptc/test_bash_qa_eval.py`, `ptc/test_bash_qa_eval_integration.py`,
`ptc/test_bash_qa_eval_startup.py`.

```python
class ReportingBashEnvConfig(SingleAgentEnvConfig):
    id: Literal["cotrain_bash_qa_env"] = "cotrain_bash_qa_env"

class ReportingBashEnv(Env[ReportingBashEnvConfig]):
    async def run(self, task: Task, agents: Agents) -> None: ...

async def run_bash_qa_eval(config: EvalConfig) -> list[Episode]: ...

__all__ = ["ReportingBashEnv"]
```

Explicit generic specialization must resolve this config through real loader.
Config overrides ID only; inherit agent/other defaults unchanged. Caller must
explicitly select supported values, no invented finite turn default.
Factory/binding/channel/credentials/export paths never enter serialized config.
Reporting remains unverified allegation telemetry, not callback authentication
or a reward/validity signal.

### Fresh evaluation entry point

`run_bash_qa_eval` requires actual EvalConfig, exact canonical EnvConfig type/ID
and exact canonical ReportingBashConfig type/ID, including forged copy checks.
Before calling SDK `run_eval`, reject each independently:

- `resume` or `clean` or `push` not exactly False; `run.attach` not None.
- Env retry count not zero.
- Unsupported effective seat: non-subprocess, absent/non-positive turns,
  agent retries not zero, edit/search enabled, skills or compaction.
- Missing model and unbounded/non-positive task, rollout or concurrent counts.
  Require explicit finite positive `num_tasks`, `num_rollouts`,
  `max_concurrent`; do not choose or normalize these for callers.

Delegate actual SDK `run_eval` exactly once, retaining its ordinary episode
creation/scoring/output/persistence lifecycle. No second loop/writer/complete
policy. Normal SDK run-ID assignment and VF_RUN_ID behavior remain SDK-owned;
do not claim this wrapper removes those existing effects.

Bare stock CLI/direct SDK run lacks admission and must refuse QA execution.
The supported API is the project wrapper, not bare `vf-eval`/`run_eval`.
This wrapper prevents forbidden modes before SDK output/listener/platform work.

### Pre-start resource guard

SDK `Env.serving` starts Taskset shared tools before `Env.run`; relying only on
the old runner's MCP refusal is too late. Base Env construction also invokes
the Taskset's selector. After claiming admission, BEFORE base Env construction,
resolve the class through actual SDK `taskset_class(config.taskset.id)` and call
`_check_tool_free(taskset_class)`, without constructing a duplicate Taskset:

1. Require canonical SDK `Taskset.task_type.__func__` identity BEFORE invoking
   the selector. A custom/stateful selector is unsupported.
2. Require canonical SDK `Taskset.toolsets.__func__` identity.
3. Resolve the declared seed through the canonical selector, require a Task
   subclass and canonical SDK `Task.toolsets.__func__` identity.

Missing/unexpected hook shape and every override, including empty,
inherited-custom or stateful overrides, refuse. Never invoke an overridden
declaration/selector to inspect its result. Thus later SDK serving uses stable
canonical empty hooks, not a first-empty/second-MCP check-then-start race.
This is an intentional new Env API restriction; old runner behavior stays
unchanged. No SDK resource-manager override or duplicate lifecycle.
Trusted plugin constructors and post-admission monkeypatching are not sandboxed.
Apply the same canonical Task-toolsets check to the actual seed and builder's
paired Task class before existing runner admission invokes any declaration.
An explicitly paired subclass may not reintroduce custom/stateful toolsets.

### Scoped admission

Use a private ContextVar containing a wrapper-owned admission record, not a
boolean. Record has mutable `active` flag, the admitted Env config association
and one claimed Env-instance identity. No channel/binding on this record.
Claim the Env instance without an intervening await; refuse unrelated instances.
Parent loader spike must assert `env.config is config.env` before identity-based
association is used. Constructor remains usable without admission for loading,
but `Env.run` requires active, matching config association and exact owner Env.

Reject nested/inherited wrapper calls while any inherited admission record
exists. In wrapper finally set active False before resetting the ContextVar
token. Inherited child contexts retain a revoked record, never authority.
Success, exception and cancellation all revoke. Separate top-level wrappers
can run concurrently under their own contexts. API activation guard only,
not a sandbox against malicious same-process Python.
Never import/set/expose the existing Bash QA private permit.

### Explicit seed builder and local channel

Seed Task must expose synchronous `build_bash_qa_task(binding)`. Validate this
original method using existing `_check_sync_callable` before wrapping, preserving
async/async-generator/partial/async-__call__ rejection.

Wrapped builder invokes the original once. Preserve existing runner rejection
and owned-coroutine close behavior for unsupported result shapes. For actual
Task results additionally require:

- `isinstance(result, type(seed))`
- `result.data is seed.data`
- `result.config is seed.config`

Existing configured runner still enforces Task+mixin, exact new binding and all
execution restrictions. No automatic arbitrary Task adaptation. Seed owner
explicitly constructs its paired subclass and preserves any custom state and
scoring behavior; identity checks do not prove arbitrary scoring equivalence.
Tests must verify override-rich behavior, including system-prompt clones.

One per-Env.run local factory creates/retains fresh exact QaChannel, receives
the exact seed data, never preflight-called. No channel/binding stored on seed,
Env instance, admission record or process-global registry. More than one
factory call is a loud error. Two interleaved episodes must remain isolated.

### Telemetry and errors

Fixed key `trace.info["cotrain_bash_qa"]`, containing only
`json.loads(channel.export())`, bounded by existing collector export limit.
Use internal `_attach_qa(trace, channel)` helper for the explicit attachment
boundary and its actual control.

- Existing key, even equal: refuse, never overwrite or merge.
- Factory never called: attach nothing, no fabricated empty report channel.
- Factory called once and Trace returned: attach actual export, even when
  trace reports failure.
- Runner raises without returning Trace: propagate, never search SDK private
  state or invent another writer/finalizer.
- Export/collision/attachment error: propagate as Env failure. Preserve
  existing trace/scoring state; no fallback success.
- Cancellation propagates after ordinary runner cleanup and admission revocation.

Toolset-bearing Ledger and all old unsupported task settings remain refused.
No Env start/stop override, special trace registration or success reinterpretation.
Bounded export is not redacted: report details may contain sensitive, untrusted
text. Keep existing SDK output access controls; add no credentials, config dumps,
bindings, runtime objects or endpoints. `push=False` prevents this SDK platform
upload path, not every possible network call. Fixtures separately block/count
external connections and use only synthetic data and a loopback policy.

## Non-goals

No SDK edits, training/native jobs, real provider/model/corpus experiments,
downloads/installs, public listeners, new persistence service or callback paths,
toolset-bearing Ledger support, gate/frontier/reward/gold changes, historical
receipt repinning, main merge, app deployment or full-suite/campaign claims.
