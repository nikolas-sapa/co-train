# Configured PTC reporting activation

2026-10-31. Base `f5fb387`, branch `feat/ptc-qa-activation`.
[Test-first contract](../spec/ptc-qa-activation.md).

Three independent specialist investigations recommended an additive configured
PTC plugin/runner before another Env layer. Architecture and security design
approved the final bounded contract. Three file-owned SWE-2 High CLI tracks
delivered product, unit tests and real integration tests. Parent verified the
files and all three exported model identities, repaired implementation/tests,
and executed acceptance. Final Python/security static reviews approved.
File-tools-only instructions are not a capability sandbox.

## Proven before product implementation

The [promoted reference](../spec/spikes/reference/ptc-qa-loader/probe_ptc_agent.py)
proves real AgentConfig JSON generic specialization, SDK Agent.run on an ordinary
Task, actual PTC loop over an owned loopback SSE listener, one accepted
`ptc`/`catalog_callback` report and receipt before policy call 2.
Factory and trace use exact original TaskData; task hashes match and the
original harness is restored. Scratch probe passed in 1.91s; promoted probe
passed in 2.42s, separate runs. The reference deliberately binds manually and
omits product admission guards, so it is not configured-product acceptance.

## Verified product evidence

Final affected run: **375 passed in 21.37s**: 182 unit, 13 adversarial admission,
eight actual SDK integration cases and 172 existing regressions. No full-suite
claim. Unit admission/run/delegate seams are declared; they are not additional
real policy requests. SDK cases exercise the actual loop, listener, channel and
program execution with zero external attempts.

Actual activation, collector storage, receipt forwarding and original-Task
identity controls each hit once and failed at the intended call-phase assertion,
then passed after restoration. The identity case has its own passing baseline
and restored run. Thirteen source/test/spec hashes stayed unchanged. Twenty-one
existing product/fixture/SDK source hashes stayed unchanged separately.

SDK coverage includes receipt before action 2, sequential fresh channels,
barrier-overlapping Agents, original Task hook receivers and scoring, report
retention after program error, eight-report quota and cancellation after an
accepted report followed by fresh same-Agent retry.

Review fixes have actual regression evidence: the first admission eight cases
failed before fixing snapshot ordering and exact-integer live limits; five
later cases failed before fixing inspection-induced bound-wiring mutation and
equal-valued original-harness replacement. All pass in the final run. Initial
unit helper/regex errors and original-config marker leakage were repaired.
Failed logs remain in scratch, not discarded or counted as acceptance.

Scratch receipts:
`~/scratch/co-train-2026-10-31/ptc-qa-activation-f5fb387/`
(`affected-final-second.log`, `controls-final-second/verification.json`,
`delivery-verification-final.json`). Original scratch receipts are not included
in a repository clone.

## API

Flat canonical plugin ID `cotrain_ptc_qa`; config changes serialized ID only.
`ReportingPTCHarness` is loadable unbound, but setup/launch must refuse without
`run_configured_ptc_qa(agent, task, qa_factory=...)`.
The runner passes the original ordinary Task/subclass unchanged, not a mixed
Task, replacement object or synthetic scoring wrapper. Caller owns fresh
QaChannels and their export. No Env, evaluation persistence or stock CLI yet.
The owned catalog is report-only; this is not a task-local SQL catalog bridge.

For an already explicitly configured fresh Agent and original Task:

```python
from cotrain_ptc_qa import run_configured_ptc_qa
from ptc.sql_qa import QaChannel

channels = []

def fresh_qa(data):
    channel = QaChannel()
    channels.append(channel)
    return channel

trace = await run_configured_ptc_qa(agent, task, qa_factory=fresh_qa)
```

The Agent's harness ID must already be `cotrain_ptc_qa`. This example chooses
no model, client, budget or experiment authorization for the caller.

The supported subset requires fresh base Agent, explicit canonical config,
subprocess, finite positive Agent/PTC turn bounds and explicit positive finite
Agent setup/rollout/finalize/scoring timeouts. PTC program/tool timeouts remain
finite; inherited defaults are not replaced. No MCP/custom toolset declarations,
interceptors, custom catalog/transport, skills, Task timeout/image/workdir
overrides or resume. Factory must be synchronous; partial wrappers and
generator/async callables refuse in this increment.
Agent live state and declared config must agree. Ordinary task state/scoring
remain SDK-owned. No reward, metric, gold or validity reinterpretation.

## Design boundaries

Agent claim/release is serialized by a short lock; each record has an atomic
one-shot setup/launch/factory lifecycle. Scoped context, runtime/trace/data
identity and independent snapshots are rechecked before and after factory.
Finally revokes before reset, restores original harness, releases claim and
clears retained activation references. Inherited contexts retain a revoked
tombstone, not reusable authority. No channel history on activation state.

Printing the returned receipt exposes it to the model. An accepted report
followed by a program error remains collected, but its printed output may be
discarded by existing program-error behavior. Receipt and exit code alone do
not prove retained reports. Allegations remain unverified.

Guarding harness setup cannot undo earlier SDK runtime provisioning or Task
setup on a bare unbound Agent.run path. Trusted callbacks, constructors and
ordinary SDK errors/logs are not sandboxed or universally redacted. Finite
settings do not establish hard CPU/memory or synchronous-factory containment.
Model requests already include report arguments; receipt-only feedback is not
report secrecy. Caller storage/tracebacks may retain channels.

Only synthetic fixtures and approved temporary 127.0.0.1 scripted listeners.
No external product-experiment/provider/model/corpus calls, training/native campaigns,
installs/downloads, SDK edits, public listeners, gate relaxation, historical
repinning, other-worktree edits, new main merge or app deployment.
Stages remain 4 PARTIAL / 5 PARTIAL / 6 BLOCKED.
