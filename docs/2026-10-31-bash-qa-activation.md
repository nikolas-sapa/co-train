# Configured Bash QA activation

2026-10-31. Base `6abc2a8`, branch `feat/bash-qa-activation`.
[Test-first contract](../spec/bash-qa-activation.md).

Chosen route: flat framework plugin ID `cotrain_bash_qa` plus the explicit
project-owned `run_configured_bash_qa` runner. This is not stock `vf-eval` or
`run_eval` integration. Config loading alone must never silently run without
reporting.

Parent executed a construction-only SDK spike: flat module + explicit Harness
generic specialization resolved the intended config/class, survived AgentConfig
JSON round-trip and constructed the actual Agent, with zero policy actions.
A dotted-ID probe failed at framework `find_spec` before fallback, so the
implementation deliberately uses a flat ID. See the annotated
[reference spike](../spec/spikes/reference/bash-qa-loader/probe_loader.py).
Loading is not evidence of working QA activation.

The serialized ID expresses reporting intent. Factory and task builder remain
trusted live application callbacks, not serialized import paths or credentials.
Caller retains each factory-created channel for existing export/persistence.
No new flag, global registry, automatic Task wrapping or persistence sink.

An unbound plugin permits loader construction but refuses setup/launch.
The runner validates matching canonical configuration, claims one Agent for its
duration, builds one shared binding and explicit mixed task, installs a bound
harness, and calls the existing enforced QA entry point. It must restore the
same original harness on all exits. Existing admission and channel ownership
guards stay authoritative; no settings, budgets or rewards are normalized.

## Usage

Construct the real `Agent` through its normal SDK configuration, with this
harness section, a subprocess runtime, finite positive `max_turns` and
`retries.max_retries = 0`:

```json
{"id": "cotrain_bash_qa", "edit": false, "search": false}
```

Keep the existing application model/client configuration. Loading this section
does not authorize bare `agent.run`; activation requires live callbacks:

```python
from cotrain_bash_qa import run_configured_bash_qa
from ptc.bash_qa import BashQaTaskMixin
from ptc.sql_qa import QaChannel
from verifiers.v1.task import Task, TaskData

class ReportingTask(BashQaTaskMixin, Task):
    pass

channels = []

def make_task(binding):
    return ReportingTask(
        TaskData(prompt="Your task"), qa_binding=binding
    )

def qa_factory(data):
    channel = QaChannel()
    channels.append(channel)
    return channel

trace = await run_configured_bash_qa(
    agent, make_task, qa_factory=qa_factory
)
# Caller retains channels and may use their existing export() API.
```

Both callbacks must be synchronous. The builder receives one fresh binding
and returns its already-paired Task; the factory runs only at actual launch,
once with that Task's original `TaskData`. Channels are one-shot. Sequential
runs need fresh channels; overlapping configured calls on one Agent refuse.
Distinct Agents can overlap. The claim coordinates this runner only, not
arbitrary concurrent Agent use or callback-scheduled work.

Supported scope remains fresh subprocess runs with a string opening prompt,
finite turns, retries zero, edit/search false, no skills/compaction/MCP tools.
In particular, existing toolset-bearing Ledger tasks do not become supported
merely because this plugin exists.

## Validation

Three actual SWE-2 High tracks delivered product, unit and real configured-run
integration files separately. Parent inspected and repaired deliveries, then ran:

- **29 activation tests passed in 8.72s**, 23 unit cases and 6 real framework
  integrations. Actual JSON → SDK Agent → runner → real Bash/HTTP/gate →
  receipt before next action, with zero fixture/caller harness assignments.
  Includes sequential runs, overlapping distinct Agents, cancellation/retry,
  actual factory launch failure/retry, and unbound/direct-route refusal.
- **132 existing affected tests passed in 14.12s**, separate run: old Bash
  unit/integration, collector, PTC launch and shared channel-claim tests.
- New bound-construction suppression: **1 hit**, intended call-phase
  `configured activation` assertion RED, not a collection/setup error.
- Receipt forwarding suppression after collector consumption: **1 hit**,
  intended call-phase `receipt` assertion RED. Baseline/restored GREEN;
  **8 source/test/spec/reference hashes unchanged** across both controls.
- **12 existing product/guard/SDK hashes unchanged**. Python re-review and
  static security review APPROVE. Neither review executed tests.

Initial unit delivery had three test defects; Python review also caught
unsupported-setting cases refusing on the wrong binding. Repairs preserve
inherited config coercion and check the actual setting-specific refusals.
Async `__call__` admission and config replacement now have explicit regressions.
An actual probe also caught `partial(async_callable_object)` bypassing
inspection. Four added cases went RED before partial unwrapping was fixed;
the final suite also preserves valid synchronous partial callbacks.

Only approved temporary 127.0.0.1 ephemeral framework fixtures, automatically
closed with scripted in-process clients. No external fixture provider calls,
UV installs/downloads, corpus, training/native jobs or public listeners.
Existing SDK cancellation transport drain remains explicit fixture bookkeeping,
not a product cleanup guarantee.

Local audit artifacts are under
`~/scratch/co-train-2026-10-31/bash-qa-activation-6abc2a8/`, including
`activation-final-29-tests.log`, `affected-regressions.log`,
`controls-partial-final/receipt.json`, unchanged-source bindings and worker exports.
Earlier failed logs remain separate; no historical receipt was repinned.

No deployment, full-suite, stock CLI, current BIRD baseline or co-training claim.
Research stages remain 4 PARTIAL / 5 PARTIAL / 6 BLOCKED.
