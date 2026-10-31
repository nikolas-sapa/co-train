# Production Bash reporting, test-first contract

2026-10-31, base `28570dc`. Initial scope: fresh non-resumed subprocess
rollouts, no compaction or skills. User approved temporary **127.0.0.1-only**
framework fixture listeners, automatically stopped, zero external model calls.

## Required tests before implementation

| Test | Numeric pass criterion |
|---|---|
| Real fixture | Actual bundled Bash harness/program and SubprocessRuntime; scripted client behind framework listener; **0 external model/provider/Docker calls**, loopback only, resources closed within **20s** outer fixture bound. |
| Valid report | **1** real `report_defect` invocation, **1** Bash `agent_output` report; fixed receipt visible to scripted client **before next action**. Post-run scanning is insufficient. |
| Rejection | **1** invalid schema/JSON report gives **0 accepted reports**, bounded refusal; original tool framing/status preserved, no submitted sentinel in added refusal. |
| Quota | **9** attempts produce exactly **8** accepted reports; ninth gets refusal, not success receipt; **0 extra model turns** beyond configured script. |
| Forgery | **1** valid stdout marker is recorded as `agent_output`, never callback provenance; **1** near-prefix line gives **0 events**. |
| Isolation | Barrier proves **2 overlapping launches**, unique wrapper locations, exactly each channel's own report/receipt, **0 cross-channel events**, parent PATH unchanged. |
| Admission | Missing pairing, wrong channel type/subclass, same/cross-instance spent channel, unsupported runtime/skills/resumption/compaction refuse before **0 policy/tool actions**. |
| Occurrences | Repeated request history does not rescan prior tool results; **2 distinct identical outputs** yield **2 events**, even with repeated call ID, not one or three. |
| Bounds | Test actual framework observation limits: oversized feedback never changes tool count/budget; never claim arbitrary-size outputs retain acknowledgment. |
| Lifetime | Setup failure, normal completion, exception and cancellation leave **0 owned wrappers / active routing entries**, **0 late channel mutations**; spent channel stays spent. |
| Disabled | Baseline Bash path has **0 QA imports/factory calls/wrapper writes/scans/prompt additions/tracking allocations**. |
| Clone failure | Framework skills reconstruction cannot silently drop reporting factory/router and run: **0 actions** on unsupported composition. |

Actual required control: suppress forwarding of `consume_output` return into
the outgoing Request. Receipt-dependent real scripted-client test must become
intended call-phase RED; restored path GREEN with source hashes unchanged.

## Confirmed constraints

Installed verifiers `0.3.2.dev137` discovers request interceptors on tasks,
not harness instances. A paired task interceptor receives Request and Trace,
rewrites only newly arrived Bash ToolMessage content and returns replacement
Request before model dispatch. Framework pins changed messages across history.
Pairing/router lifecycle must key on Trace identity, not a shared current task.

Wrapper/PATH/prompt setup precedes first program action; channel uses existing
one-shot atomic claim. Preserve tool names/counts/call IDs, exit status,
framing, existing runtime limits and task setup/scoring behavior. No post-hoc
telemetry-only substitute, fake process, or existing SQL-shell route substitute.

## Non-goals

No real corpus, product model/provider calls, training, native SQL campaigns,
Docker, installs/downloads, public listener, CLI/config activation, SQL task/
tool addition, isolated reporting wire, TRL, persistence service, authenticated
reports, rewards/gold/gates/frontier changes or unsupported resumption/skills.
## Concrete implementation, architect-approved

Only product module `ptc/bash_qa.py`. No framework/reference edits or changes
to existing PTC/collector code. Unit tests `ptc/test_bash_qa.py`; real subprocess
integration tests `ptc/test_bash_qa_integration.py`, separate ownership.

```python
class QaBashHarnessConfig(BashHarnessConfig):
    _qa_required: bool = PrivateAttr(default=False)

class BashQaBinding:
    def __init__(self) -> None: ...

class BashQaTaskMixin:
    def __init__(self, *args, qa_binding: BashQaBinding, **kwargs): ...
    async def setup(self, trace: Trace, runtime: Runtime) -> None: ...
    async def finalize(self, trace: Trace, runtime: Runtime) -> None: ...
    @intercept
    def _qa_rewrite(self, request: Request, trace: Trace) -> Request | None: ...

class QaBashHarness(BashHarness):
    SUPPORTS_RESUME = False
    def __init__(self, config: QaBashHarnessConfig, *,
                 qa_factory=None, qa_binding=None): ...
    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls,
                     data, tool_interception_url=None) -> ProgramResult: ...

async def run_bash_qa(agent: Agent, task: Task) -> Trace: ...
```

Caller mixes `BashQaTaskMixin` before its existing Task class, creates one
binding shared by task/harness, supplies factory and config, and calls
`run_bash_qa(agent, task)`. Retain original `task.data` in setup registration
and give that exact object to factory, not rewritten harness data.

### Entry point and lifecycle

Before `agent.run(task)`, validate identical intended binding on task/harness,
enabled callable factory, SubprocessConfig with no borrowed runtime, string
opening prompt/no replay, empty task/harness skills, `compaction is None`,
`edit is False`, `search is False`, no MCP toolsets, finite positive configured
`agent.limits.max_turns`, `agent.config.retries == 0`. Refuse unsupported
settings, never silently modify them.

Private ContextVar permit contains task/harness/binding identity. Task setup
requires it BEFORE underlying setup, making direct `Agent.run` bypass refuse.
Entry-point finally clears every registration belonging to its permit, including
aborted setup when framework never finalizes.

Task setup/finalize are ordinary overrides, not decorated: register Trace,
await `super().setup(trace,runtime)`, mark ready, remove registration on failure.
Finalize invalidates first, awaits `super().finalize`, removes in finally.
Only request rewrite is decorated. Keep inherited scoring/metrics/hooks.

Router uses `id(trace)` plus exact retained Trace identity, never task/data/current
channel. Explicit registration retains identity only until cleanup. Disabled
path creates no per-launch tracking state/locks and imports no `ptc.sql_qa`.

### Cloning and launch

Enabled harness copies supplied config and sets its own private `_qa_required`.
PrivateAttr survives installed Pydantic `model_copy` and is absent from dump/
schema. Constructor refuses marked config without factory AND binding, so
framework skills reconstruction cannot silently drop intent. Refuse skills/
compaction at construction and all remaining unsupported settings at entry.
Existing separate PTC skills-cloning hazard is outside this change.

Launch requires ready registration, fresh Trace, subprocess runtime/workdir,
nonempty tool-interception URL. Factory once, exact QaChannel type, then existing
atomic `_claim_launch`. Reject same runtime object used concurrently.

Create unique owned directory under started runtime.workdir; lazy existing
`install_report_wrapper`. Reject enabled harness-config PATH override.
Effective PATH precedence is harness resolved_env, runtime.env, host/default.
Save runtime PATH presence/value, prepend owned directory, never mutate host
environment or harness config. Activate only after setup succeeds. Add reporting
prompt using launch-local TaskData.model_copy. Delegate actual BashHarness and
forward interception URL. Finally invalidate synchronously, restore exact PATH
presence/value, remove only owned directory, release runtime ownership. Surface
cleanup failure; channel remains spent.

### Rewrite and occurrence cache

Framework invokes hooks on empty synthetic tool-result probes before execution.
Ignore non-tool tails/empty content; do not cache probes. Match current tail
ToolMessage to issuing assistant `bash` call.

Occurrence key is issuing assistant absolute position plus call ID, with
issuing-message fingerprint checked. Fresh/no compaction keeps positions stable.
Cache original/rewritten content for uncommitted occurrences: repeated original
returns cached rewrite without resubmission; already rewritten returns unchanged.
Prune committed prefix; maximum **64 uncommitted rewritten occurrences**.
65th raises TaskError BEFORE collector mutation.

Rewrite only current tail, preserving IDs/name/types/tools/message count. Return
None when unchanged. Consume/cache synchronously, no intervening await. Missing/
closed registration receiving actual tool result raises TaskError; no silent
drop/recreation. Let framework pin results, never alter session internals or
scan trace afterward.

### Additional numeric acceptance

- Empty gate probe then real result: exactly 1 event; replay adds 0.
- Two identical results under distinct issuing occurrences: exactly 2 events.
- Two tool results in one request are each consumed once, boundary-safe.
- Raw later subprocess history receives pinned receipt-bearing rewrite,
  unchanged report count.
- Exact config clone `type(h)(h.config.model_copy(update={"skills":[...]}))`
  raises before 0 actions/factory calls; private marker absent from dump/schema.
- At most 64 pending cached rewrites; 65th refuses before mutation; committed
  entries evicted. Cleanup leaves 0 cached entries.
- Original observation <=18000 bytes plus feedback stays <20000 bytes with
  exact original prefix. Actual framework rebounding retains 20000 head/tail
  payload bytes plus warning/separator metadata (not a 20000-byte wire ceiling)
  and preserves appended receipt in the oversized retained-marker test.

Scan only complete marker lines delivered after initial framework truncation,
not removed raw output. No arbitrary-size raw preservation guarantee.
Prototype confirms real framework listener/client construction before integration
tests finalize. Server binds only127.0.0.1 with ephemeral port, context teardown,
scripted in-process Client; normal child AsyncOpenAI and `/tool` gate stay real.
Installed SDK foreground cancellation kills but does not await its subprocess
transport. The fixture records only its real foreground processes through a
delegating creation wrapper and drains them at teardown within 5s. This explicit
fixture bookkeeping is not evidence that the product adds transport reaping or
that the installed SDK's own cancellation cleanup waits for pipe EOF.
