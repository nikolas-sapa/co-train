# Bash QA evaluation integration

2026-10-31. Base `95a4596`, branch `feat/bash-qa-eval`.
**Implemented and verified with bounded synthetic fixtures.**
[Test-first contract](../spec/bash-qa-eval.md).

Parent executed a real synthetic evaluation spike:

- Actual EvalConfig JSON selected a flat custom Env and Taskset.
- SDK-created episode Agent ran the existing configured Bash QA composition.
- Real child HTTP/tool gate delivered 1 report and receipt before policy call 2.
- Bounded QA in `trace.info` survived normal SDK-written episode JSONL exactly.
- Seed/paired task hashes matched, original harness restored, shared listener
  and owned runtime torn down. Parent network guard observed 0 external attempts.

The [execution reference](../spec/spikes/reference/bash-qa-eval-execution/probe_eval_execution.py)
documents fixture-only seams and intentionally missing production checks.
This proves the reference path, not complete product acceptance.

## Supported entry point

Use `run_bash_qa_eval(config)` with the normal SDK `EvalConfig` and this Env ID:
`cotrain_bash_qa_env`. The caller selects the model/client, source-root-importable
Taskset, output directory and finite positive task/rollout/concurrent/turn counts.
The seat must explicitly use:

```json
{
  "harness": {"id": "cotrain_bash_qa", "edit": false, "search": false},
  "runtime": {"type": "subprocess"},
  "retries": {"max_retries": 0}
}
```

Also select finite positive `max_turns`, Env retries zero, `push=False`,
`resume=False`, `clean=False`, and no `run.attach`. No settings are normalized
or invented. Inherited defaults remain unchanged and unsupported defaults refuse.
The local subprocess executes on the host, not an isolated production sandbox.

```python
from cotrain_bash_qa_env import run_bash_qa_eval

episodes = await run_bash_qa_eval(config)
```

The [project JSON CLI](2026-10-31-bash-qa-eval-cli.md) delegates an explicit
config file to this same API; it does not enable stock `vf-eval`.

The SDK still creates/scores episodes, assigns its run identity and writes its
normal output. No alternate evaluation loop, JSONL writer or completion policy.

### Explicit Task integration

The seed Task owns a synchronous `build_bash_qa_task(binding)` method and its
explicit paired subclass:

```python
from ptc.bash_qa import BashQaTaskMixin
from verifiers.v1.task import Task

class SeedTask(Task):
    def build_bash_qa_task(self, binding):
        return PairedTask(self.data, self.config, qa_binding=binding)

class PairedTask(BashQaTaskMixin, SeedTask):
    pass
```

Preserve any custom instance state and scoring behavior explicitly in that
builder. The Env requires the seed's concrete type, exact data/config objects
and the existing runner's exact binding/mixin contract; it does not wrap
arbitrary Task classes or prove arbitrary scoring equivalence.

Only canonical inherited SDK Taskset/Task toolset hooks and Taskset task-type
selection are supported. Even an empty custom override refuses before base
Env construction; custom paired Task toolset hooks also refuse. This prevents
SDK shared-tool startup preceding a later MCP refusal. Toolset-bearing Ledger
tasks remain unsupported. Trusted plugin import/constructor side effects and
post-admission monkeypatching are outside this API guard, not sandboxed.

### Telemetry and lifetime

Each admitted episode gets a fresh local channel. When a Trace returns after
factory invocation, its actual collector export lands at
`trace.info["cotrain_bash_qa"]`, including for a failed Trace. No factory call
means no fabricated empty telemetry. Existing-key collision, export or
attachment failure makes the Env fail rather than overwriting or reporting
success. Normal SDK JSONL serialization retains this field.

Bounded is **not redacted**. Report details are untrusted text and may contain
sensitive information. Keep existing output access controls. No credential,
config dump, binding, runtime or endpoint is added. Public markers remain
forgeable allegations; QA changes no reward, metric, gold or validity outcome.
`push=False` disables this SDK platform-upload path, not all network activity.

Admission belongs to one Env/config and expires before its ContextVar token
resets. Nested calls and stale inherited child contexts refuse. Distinct
top-level evaluations need their own configs/output paths. This does not make
arbitrary concurrent host mutation or callback-scheduled work safe.

Architect approved a fresh-only `run_bash_qa_eval` wrapper plus canonical Env.
The wrapper rejects unsupported EvalConfig flags before SDK execution; scoped,
revocable admission prevents bare Env execution and stale child-context reuse.
Env-only code cannot see every parent EvalConfig flag, so bare stock
`vf-eval`/`run_eval` remains unsupported, not silently enabled.
Actual SWE-2 High product and unit deliveries were inspected and repaired.
The integration worker produced no file and was stopped; parent implemented
and executed the eight real evaluation cases. File-only worker instructions
are not a capability sandbox. Independent SDK findings informed the contract;
the separate strategy report remains advisory because it read an unqualified
SDK clone. Actual installed-source findings and executed probes take precedence.

## Acceptance evidence

- Actual product-wrapper smoke GREEN: 1 real report, receipt at policy call 2,
  exact QA in SDK JSONL, zero external attempts under the fixture network guard.
- Complete new suite: **114 passed in 11.08s**, comprising 100 unit,
  six startup and eight real SDK evaluation integrations.
  Startup guards invoke zero unsupported declarations/selectors; paired-Task
  toolset reintroduction also refuses.
- Unit matrix passed after parent repaired a callback-shape
  assumption and three masked identity/binding refusals. Exact refusal reasons
  now required. Actual targeted data/config/binding counterfactuals each RED
  with one hit, original/restored three GREEN; five bound source hashes unchanged.
- 161 existing activation/reporting/collector/launch checks passed in 24.29s,
  separate run. Fifteen existing product/fixture/guard/SDK hashes unchanged.
- Final product, unit and real-integration Python/security source reviews
  approved. Source reviews did not independently execute the tests.

Four actual evaluation-level controls each hit the suppressed boundary once
and produced the intended **call-phase assertion RED**, with baseline/restored
GREEN: Env-to-configured-runner activation, consumed-report receipt forwarding,
QA attachment, and pre-base Taskset resource admission. Fourteen bound
product/test/spec/reference hashes remained unchanged within the control run.
Earlier failed logs and control receipts remain separate, never repinned.

The real suite checks receipt in the request preceding the next ordinary Bash
action, exact actual SDK JSONL telemetry, sequential and barrier-overlapping
two-episode isolation, explicit custom-state/scoring preservation through the
actual Taskset system-prompt clone, failed scoring with QA retained, missing
builder/direct-SDK refusal with zero policy/runtime/channel activity, and
cancellation after a real report/receipt followed by a fresh successful eval.

Only declared fixture seams: delegated interception creation/preseeded scripted
clients; delegated Agent/channel constructor observers; unchanged cached-source
ScratchRuntime helper and ownership-filtered foreground transport drain.
No baseline loader, Env/Agent execution, configured runner, QA rewrite,
attachment, private permit or SDK writer replacement. The parent socket/DNS
guard observed zero external attempts. Child used the real bundled program and
owned endpoint; this is not a general child-process network sandbox. Fixture
transport draining compensates installed SDK behavior, not product reaping.

No full-suite rerun or real model/corpus campaign. Prior 161 regressions are a
separate run, not an invented 275-test combined run.

Only approved temporary 127.0.0.1 scripted fixtures. No external model/platform
calls, corpus, training/native jobs, installations/downloads, gate changes,
historical receipt repinning, main merge or app deployment.
Stages remain 4 PARTIAL / 5 PARTIAL / 6 BLOCKED.
