# Configured PTC QA activation, test-first contract

2026-10-31. Base `f5fb387`, branch `feat/ptc-qa-activation`.
Additive plugin/runner only. No Env, evaluation writer or stock CLI claim.
Architecture/security design approved after actual installed-SDK spike.
Implementation acceptance requires the lifecycle and snapshot checks below.

## Tests before implementation

| Test | Numeric pass criteria |
|---|---|
| Loader | Exactly 1 canonical harness/config resolves through real AgentConfig JSON; inherited serialized fields/defaults unchanged except ID; no serialized activation objects. |
| Unbound refusal | Direct setup/launch: 0 factory/policy calls. Bare Agent.run fails before policy/factory, but may provision runtime and execute Task setup. |
| Actual activation | Real SDK Agent.run/Task/runtime/PTC/SSE: 1 factory, exact original TaskData and trace data, 1 ptc/catalog_callback report, receipt in request 2, original harness restored. |
| Ordinary Task | Exact Task instance/subclass/config/data/custom state/scoring preserved; 0 automatic wrapping, no Task mixin required. |
| Sequential/concurrent | Two sequential runs and two barrier-overlapping distinct Agents: 2 distinct channels, one own report each. Same-Agent async and two-thread overlap: exactly 1 admitted. |
| Mode refusal | Each invalid effective config independently: 0 Agent.run, factory, policy or runtime calls. Wrong/forged types/IDs and premarked configs refuse. |
| Hook refusal | Custom/inherited/stateful toolsets and discovered interceptors refuse without invoking declarations/interceptors, before Agent.run; recheck at setup after Task setup. |
| Lifecycle | Repeated setup/launch/factory, copied harness and active/stale inherited contexts produce 0 extra activations. Runtime/trace/data identities pinned. |
| Snapshot mutation | Individually mutate each admitted config/live reference or nested value, including inside factory: 0 subsequent policy calls; factory invoked at most once. |
| Inspection mutation | Before binding: equal-valued original harness replacement and invalid/valid timeout edits refuse before Agent.run. After factory: Task inspection changing bound config, transport, catalog or factory yields 0 subsequent delegate-policy dispatches. |
| Cleanup | Success, returned failure, raised exception and cancellation revoke, restore exact original harness and release claim. Fresh retry succeeds. |
| Bounds/semantics | Ninth report: exactly 8 accepted and overflow rejected. Accepted report survives later program error. Finite turn budget unchanged. No reward/metric changes. |
| Privacy/default compatibility | Guard errors contain 0 private sentinels; root ptc export and disabled behavior unchanged. No caller-owned channel retained by activation record after revocation. |

Actual controls, immutable source/test/spec bindings:
1. Suppress `_bind_harness`: intended activation call-phase assertion RED;
   baseline/restored GREEN, one hit.
2. Suppress accepted report storage while keeping receipt: intended collector
   call-phase assertion RED; restored GREEN, actual submit boundary hit.
3. Suppress returned receipt after real submit: intended receipt-before-next-
   action assertion RED; restored GREEN. No setup/collection errors count.
4. Delegate actual Agent.run with a shallow Task copy: custom-task hook receiver
   identity assertion RED; same-case baseline/restored GREEN.

Synthetic fixtures only, actual SDK/SSE loopback 127.0.0.1:0, scripted clients,
zero external attempts. Reuse qualified runtime/network fixture helpers.
Outer fixture 20s, barrier waits <=10s; no warning suppression or fake processes.
These timeouts do not establish hard containment of hostile Python operations.

## Proven reference

[Loader/Agent reference](spikes/reference/ptc-qa-loader/probe_ptc_agent.py):
actual AgentConfig JSON resolves exact generic config/harness; actual Agent.run
on ordinary Task reaches old PTC loop and real owned SSE listener. One report,
catalog_callback provenance, receipt before call 2, exact task/trace/factory data
and task hash, original harness restored. Scratch and promoted copies GREEN.
Reference deliberately binds manually and omits production guards. Do not copy
those shortcuts into tests of the configured activation boundary.

## Product API

Only new product `cotrain_ptc_qa.py`:

```python
class ReportingPTCConfig(PTCHarnessConfig):
    id: Literal["cotrain_ptc_qa"] = "cotrain_ptc_qa"
class ReportingPTCHarness(PTCHarness, Harness[ReportingPTCConfig]): ...
async def run_configured_ptc_qa(
    agent: Agent, task: Task, *, qa_factory: Callable[[TaskData], QaChannel],
) -> Trace: ...
__all__ = ["ReportingPTCHarness"]
```

ID-only serialized config override, inherited PTC max_turns/program_timeout and
other defaults unchanged. Private intent marker permitted, never serialized.
Do not change old ptc/Bash/collector/SDK/training code or root ptc export.
Canonical constructor accepts config only and a private runner-owned binding,
not public factory/catalog/transport injection. Config-only loading is inert;
setup and launch refuse without the scoped runner. Marked config reconstructed
without binding refuses rather than silently losing reporting.

Exact base Agent only, deliberately excluding Env subclasses for this increment.
Accept original Task subclasses unchanged. No Task builder/mixin/private Bash
permit. Empty owned catalog, transport None, SUPPORTS_MCP=False, no resume.

## Admission and supported subset

Claim the actual Agent before discovery/snapshot work that can execute Python.
A short module-level threading.Lock serializes claim/release; no global Agent
registry. Unique per-invocation owner attribute, owner-checked release.
Any nested/inherited wrapper record, even revoked, refuses.

Require exact canonical unbound ReportingPTCHarness and canonical config type/ID
on both live harness and Agent.config, public values equal, unmarked. Require
fresh/unentered/unclosed Agent, no borrowed server/gate; externally injected
interception object is allowed and pinned.

Validate BOTH declared config and actual live Agent fields:
- subprocess runtime; positive actual-int Agent max_turns and PTC max_turns;
- retries exact int zero; token limits None or positive actual ints;
- explicit positive finite setup/rollout/finalize/scoring Agent timeouts,
  finite positive PTC program_timeout and inherited tool_timeout;
- explicit nonblank model and client; live context/runtime/limit/timeout values
  agree with their declared Agent config (SDK-filled sampling allowed);
- no Task/harness skills, compaction, TaskData timeout overrides or container
  requirement; string prompt and None/string system prompt;
- canonical Task.toolsets.__func__ identity, no custom declarations invoked;
  no hooks from canonical SDK discover_decorated(task, "intercept").

Use actual ModelContext fields model/client/sampling (frozen dataclass) and
RolloutLimits' four fields (frozen dataclass), not invented model_dump methods.
Client/sampling/runtime/configs are Pydantic objects with serialization APIs.
Task attributes/discovery/constructors are trusted Python, not sandboxed.

## Scoped lifecycle and snapshots

Private ContextVar record owns active flag, Agent/Task/original TaskData/config
associations, admitted independent value snapshots, bound harness/runtime/trace
identities and original caller factory. No channel on record/harness/Task.
One record-local lock makes lifecycle/occurrence transitions atomic:
unstarted -> setup-started -> ready -> launch-consumed -> finished -> revoked.
No repeated setup. Pin runtime once. Consume launch BEFORE factory, pin exact
Trace once. Factory occurrence consumed BEFORE caller invocation, at most one.
Failed setup/launch is terminal, never rearmed.

At setup, launch, immediately before AND after factory: require current record
identity/active, exact bound harness and Agent.harness, original Task/data/config,
all admitted references and independent nested snapshots unchanged. Recheck
toolsets/interceptor exclusions after Task setup. At launch require identical
setup runtime, trace.task.data is original data and launch data is original data,
empty MCP URLs, unchanged empty owned catalog, transport None and protected
factory identity. Factory receives exactly the original data. Reject async
functions/generators/async __call__/partials before invoking; close owned native
coroutine return before exact-channel refusal. Old PTC keeps actual channel
type, atomic one-shot ownership, quotas, callback, program errors and receipt.

Use internal `_bind_harness` for the actual activation-control boundary.
Snapshot before callback-capable admission inspection and temporary binding,
then compare original harness/config identities and independently retained
values again before binding. Task inspection runs before the complete bound
wiring checks, so inspection-triggered mutation cannot follow the last check.
Never merely compare two post-callback
aliased objects. Snapshot public config plus live runtime_config/limits/timeout/
ctx client+sampling and interception reference; keep snapshots out of errors,
serialized config and telemetry. Recheck private marker/record/protected wiring.
Only runner assigns agent.harness. Await actual agent.run(original_task) once.

Finally: revoke first (before token reset), clear retained caller factory and
Agent/Task/runtime/harness/snapshot references, restore exact original harness,
owner-checked release under nested finally. Inherited contexts keep a revoked
tombstone. Cleanup must remain callable after revocation.
Guarding setup/launch does not promise continuous monitoring during an arbitrary
trusted callback, and detecting mutations does not undo callback side effects.

## Non-goals and claims

No Env, SDK evaluation/persistence/CLI support, arbitrary catalog, MCP, request
rewriting, skills, resumption, SDK changes, new defaults/budgets/result policy,
gold/reward/validity changes, provider/corpus/training/native campaigns, installs,
public listeners, gate changes, historical repinning or other-worktree edits.
No arbitrary same-process Python, CPU/memory or synchronous factory containment.
New guard errors are generic; ordinary SDK/callback errors and model request
arguments may contain sensitive data. Receipt-only feedback is not report
secrecy or authenticity/truth. Caller storage/tracebacks may retain channels;
promise no added channel history, not universal garbage collection.
