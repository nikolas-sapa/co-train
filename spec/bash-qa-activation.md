# Configured Bash QA activation, test-first contract

2026-10-31. Base `6abc2a8`, branch `feat/bash-qa-activation`.

## Required tests before implementation

| Named test | Numeric pass criterion |
|---|---|
| Flat plugin round-trip | Actual SDK resolves exactly 1 intended Harness/config class. AgentConfig JSON round-trip preserves canonical ID and every public field. Zero serialized factory/binding/private-marker fields. |
| Canonical identity refusal | Wrong ID/type, mismatched public config, bound input and forged copied config refuse with zero builder/factory/policy/tool calls. Original harness unchanged. |
| Unbound/partial refusal | Unbound setup/direct launch/bare Agent run and both partial constructor pairings refuse with zero policy/tool actions and zero factory calls. No disabled-Bash fallback. |
| Clone refusal | Shallow/deep marked copies reconstructed without dependencies refuse before zero actions. JSON reconstruction creates unbound reporting harness, never an executable disabled fallback. |
| Builder admission | Noncallable, async callable, native-coroutine return, async-generator return, non-Task/non-mixin and wrong binding refuse before harness assignment. Zero factory/policy/tool calls; zero unawaited-coroutine warnings for owned native coroutine returns. |
| Unsupported settings | Existing runtime/prompt/replay/skills/compaction/edit/search/MCP/turns/retries refusals persist, zero policy/tool actions and zero silent setting changes. |
| Runner lifetime | Success, builder exception, admission failure, run exception and cancellation restore exact original harness. Zero owned agent claims/routing entries/wrappers afterward. |
| Agent exclusivity | Barrier-controlled 2 overlapping runner calls on one Agent yield exactly 1 refusal. Two distinct Agents can overlap with zero cross-channel events. |
| Configured real receipt | Actual Agent constructed from canonical JSON, zero fixture/caller harness assignments. Runner activation yields exactly 1 factory call and 1 report; receipt observed before next action. Real Bash/child HTTP/framework gate, zero external fixture provider calls, loopback only, <=20s outer bound. |
| Configured cleanup | Real completion, failure and cancellation leave original unbound harness restored; repeated fresh runs succeed with separate exact channels. |
| Ordinary Bash unchanged | Isolated child loads ordinary Bash config with zero imports of new plugin/QA modules, factory calls, wrapper writes or new tracking allocations. |

Two actual controls, not a mock green:

1. Suppress the **new bound-construction boundary**: wrap
   `ReportingBashHarness.__init__`, count a hit only when both live dependencies
   arrive from the runner, and construct unbound instead. Actual configured
   integration must fail an intended call-phase activation assertion. Baseline
   and restored runs GREEN; no policy action can slip past unbound refusal.
2. Suppress existing Request receipt forwarding in the configured real test.
   Collector consumption still occurs; the next-request receipt assertion must
   go intended call-phase RED, restored GREEN.

Record actual mutation hits, pytest phase/error, source/test/spec hashes before
and after. No setup/collection error, skipped test or unrelated exception counts.
The configured integration may convert only expected admission ValueError/
TypeError into a clearly labelled activation assertion, never hide arbitrary
network/runtime failures.

## Reference spike and confirmed constraints

Actual installed verifiers `0.3.2.dev137`:

- Dotted IDs fail in `_import_plugin` at namespaced `find_spec`, before fallback.
  Parent observed `import_harness("ptc.bash_qa")` fail while flat `ptc` succeeds.
- Flat-module `__all__` must export exactly one Harness subclass.
- Config discovery reads generic ancestry, not constructor annotations.
- AgentConfig dumps/revalidates harness configs through their ID; the old
  private marker alone cannot preserve serialized reporting intent.
- Loader constructs `cls(config)` without live factory/binding.
- Stock SingleAgentEnv calls bare `agent.run`, not the enforced QA entry point.

Construction-only reference:
[`spikes/reference/bash-qa-loader/probe_loader.py`](spikes/reference/bash-qa-loader/probe_loader.py)
and adjacent `qa_activation_probe.py`. Parent executed both scratch and promoted
versions: actual loader/config/JSON/Agent construction GREEN, zero policy
actions. They prove the flat ID + explicit generic specialization, **not**
working reporting activation. Their disabled prototype must not be copied as
the product's unbound behavior.

Repo is source-root importable, with no packaging entry points introduced here.
Existing `ptc.__all__ = ["PTCHarness"]` stays unchanged.

## Exact implementation contract

Only new product file `cotrain_bash_qa.py`, canonical flat ID
`cotrain_bash_qa`. Tests: `ptc/test_bash_qa_activation.py` and
`ptc/test_bash_qa_activation_integration.py`. Existing QA/collector/framework
modules remain unchanged.

```python
class ReportingBashConfig(QaBashHarnessConfig):
    id: Literal["cotrain_bash_qa"] = "cotrain_bash_qa"

class ReportingBashHarness(QaBashHarness, Harness[ReportingBashConfig]):
    def __init__(self, config: ReportingBashConfig, *,
                 qa_factory=None, qa_binding=None): ...

async def run_configured_bash_qa(
    agent: Agent, make_task: Callable[[BashQaBinding], Task], *,
    qa_factory: Callable[[TaskData], QaChannel],
) -> Trace: ...

__all__ = ["ReportingBashHarness"]
```

Config/runner are accessible through explicit named imports. Canonical ID
itself requires reporting, no new activation boolean or serialized callbacks.
Config changes only ID. Preserve inherited defaults; caller must explicitly
select supported values, including `edit=False`, not silently normalize them.

### Harness states

- Exact ReportingBashConfig type and canonical ID required, including checks
  against unvalidated `model_copy(update=...)` changes.
- Unmarked config + both live dependencies absent: construction allowed only
  for loader use. Both setup and launch refuse neutrally, naming
  `run_configured_bash_qa`. Never delegate disabled Bash behavior.
- Exactly one dependency supplied: immediate refusal.
- Both supplied: delegate existing QA constructor and execution checks.
- Marked config without dependencies: existing clone refusal still applies.
  Do not reset the marker or turn missing dependencies into disabled mode.

### Runner lifecycle

1. Require actual Agent, exact unbound/unmarked ReportingBashHarness and
   exact canonical config type/ID. Require matching exact canonical config
   on `agent.config.harness`, every public field equal via
   `model_dump(mode="json")`, no excluded fields.
2. Require callable synchronous builder/factory. Reject identifiable async
   callables/async-generator functions before invocation.
3. Claim Agent with private attribute + unique owner identity. Existing claim
   refuses; no global registry. Create one fresh binding; call builder once.
4. Returned object must be both Task and BashQaTaskMixin, paired to that exact
   binding. No automatic wrapping/reconstruction of arbitrary Task instances.
   Reject awaitable/async-generator returns. Close an owned native coroutine
   before raising, never await unsupported builders.
5. Before assignment, recheck original harness identity and public config
   against its **pre-callback snapshot**, not merely mutual equality of two
   possibly aliased objects. Refuse callback-induced reconfiguration.
6. Construct bound ReportingBashHarness from the same canonical config,
   supplied factory and new binding. Assign only `agent.harness`.
7. Await existing `run_bash_qa(agent, task)`. Do not import/expose/set its
   private permit. Keep original Task behavior and every existing admission,
   channel-claim, occurrence, PATH/runtime and cleanup guard.
8. Finally restore the exact original harness object and release only this
   invocation's owner identity. Includes callback failure before assignment,
   admission refusal, exception and cancellation. No agent config, limits,
   runtime settings or process-global environment changes.

Factory is called only through existing launch, on exact original TaskData,
once per admitted launch; must return exact fresh QaChannel. Caller owns channel
retention/export, no persistence service or serialized export path.

Agent claim coordinates this runner only. Trusted callbacks must not schedule
work or mutate Agent state; arbitrary external Agent mutation/concurrent use is
unsupported and not made safe by this claim.

### Real fixture boundary

Reuse source-confirmed existing Bash fixture seams where suitable, but do not
use its manual `agent.harness` assignment helper for configured integration.
Construct actual Agent from canonical JSON and let runner do activation.

Temporary framework listener only127.0.0.1:0, no tunnel/external provider.
Actual bundled child, Bash, normal HTTP and tool gate. Existing-interpreter
script-cache seed refuses UV bootstrap; no install/download/global cache write.
Ownership-filtered real-process creation bookkeeping/drain <=5s compensates
SDK cancellation kill-without-wait, explicitly fixture-only. No fake process,
mocked forwarding or warning suppression. Unraisable warnings are test errors.

## Non-goals

No stock `vf-eval`/`run_eval` support claim, custom Env/Taskset integration,
packaging changes, SDK/reference edits, training, campaigns, corpus, external
product model calls, downloads/installs, public listeners, credentials or
callback paths added to config, automatic Task wrapping, persistence,
rewards/gold/gate/frontier changes, replay, skills, compaction or MCP support.
Do not alter the unfinished training CLI or claim deployment.
