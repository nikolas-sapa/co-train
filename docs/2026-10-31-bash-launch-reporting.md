# Production Bash launch reporting

2026-10-31, base `28570dc`, branch `feat/bash-launch-reporting`.
**Fresh subprocess reporting implemented and fixture-verified.**
[Test-first contract](../spec/bash-launch-reporting.md).

This route pairs a reporting task mixin with the actual framework Bash harness.
The shared binding keys state by Trace identity, never a shared current channel.
The task request interceptor processes new Bash observations and forwards the
collector's feedback before the next model action. A harness-only post-run scan
or the existing in-process SQL runner does not establish that behavior.

Initial scope is fresh subprocess rollouts only. Skills, replay/resumption,
compaction, search/edit and additional MCP tools are unsupported and must
refuse, not silently disable reporting. Config cloning preserves private
reporting intent and refuses loss of factory/binding.

Caller supplies a fresh exact channel through the factory and owns export/
persistence. The existing atomic one-shot claim prevents reuse across launches.
Wrapper directories and PATH changes are launch-local and cleaned on all exits.
No process-wide environment mutation, added tool, model turn, budget, reward,
gold, validity or frontier change.

Installed verifiers `0.3.2.dev137` supplies Request and Trace to task interceptors,
including empty pre-execution probes. Probes are ignored; occurrence tracking
avoids duplicate submission across repeated history. Pending rewritten results
are capped at 64 and cleared after commitment/cleanup.

Framework tool observations retain 20,000 head/tail payload bytes plus
truncation headers, not a 20,000-byte wire ceiling. Reports can only cover
complete marker lines delivered to the host.
Do not claim original-output preservation above that bound, collection of
truncated markers, or receipt visibility without the actual bounded test.

Reports and shell markers remain forgeable, unverified allegations.
This is not authentication, a new sandbox or a persistence service.
Stage 4 remains PARTIAL: framework/CLI registration, isolated reporting
transport and actual TRL integration remain. Stages 5/6 remain PARTIAL/BLOCKED;
no current BIRD paired baseline is created here. Existing separate PTC
skills-cloning behavior is outside this change.

## Opt-in API

1. Create one `BashQaBinding`, shared by the task and harness.
2. Mix `BashQaTaskMixin` before the existing Task class. Pass
   `qa_binding=binding` when constructing the task.
3. Construct `QaBashHarness(QaBashHarnessConfig(...), qa_factory=...,
   qa_binding=binding)` and assign it to the configured `agent.harness`.
   The current framework loader does not register this subclass.
4. Call `await run_bash_qa(agent, task)`, not bare `agent.run`. Retain each
   factory-created channel and export it through the existing caller API.

Factory receives the exact original `task.data`, once per admitted launch,
and must return a fresh exact `QaChannel`. Use SubprocessConfig, a string
opening prompt, finite positive `max_turns`, retries zero, empty skills,
`edit=False`, `search=False`, `compaction=None`, no task MCP toolsets.
Unsupported composition refuses, never silently changes settings. The
config's private intent marker survives cloning but is absent from dump/schema.

## Approved fixture boundary

User approved temporary **127.0.0.1-only**, ephemeral framework test listeners,
automatically stopped afterward, with an in-process scripted model client.
Real Bash child/SubprocessRuntime and the normal HTTP/tool gate remain real.
No external model/provider call, separate fake-provider listener, public bind,
Docker, tokenizer/model download, training or native SQL job is authorized.

## Validation

Parent executed the real baseline fixture: ProgramResult exit0, trace.ok true,
2 scripted requests and 1 committed Bash marker observation. The fixture uses
the already-installed interpreter through an explicit local script-cache seed,
refuses dependency bootstrap and leaves process/HTTP/Bash execution real.
That baseline alone does not establish QA receipt forwarding.

Final executed checks, separate runs:

- **38 new passes in 9.50s**: 30 unit/lifecycle cases and 8 actual Bash
  subprocess integrations. Unraisable exceptions are errors, not filtered.
- **94 existing passes in 3.08s**: collector, PTC reporting and one-shot claim.
- Actual forwarding control: baseline GREEN, suppress returned Request while
  retaining collector consumption gives intended call-phase RED
  (`receipt_at == []`, expected `[2]`), restored GREEN. One actual rewrite
  suppression hit; five source/test/spec hashes unchanged.
- Static Python and security implementation reviews **APPROVE** after repairs.
  Neither review claims test execution.

Real integration covers receipt before next action, invalid-report refusal,
9 attempts/8 accepted plus visible ninth refusal, forgeable-marker provenance,
exact small-output prefix, actual oversized rebound with retained receipt,
2 barrier-proven overlapping launches, pinned history and cancellation.
Unit cases cover cloned-config refusal, direct-entry rejection, exact factory
data, distinct identical occurrences, 64 pending rewrites/65th pre-mutation
refusal, committed-prefix pruning, cross-binding runtime exclusion, empty PATH
precedence and cleanup-error release. Collector quotas are unchanged.

Installed SDK cancellation kills foreground processes without awaiting their
transports. The fixture now records only its real foreground child processes
through a delegating creation wrapper and drains them within 5s at teardown.
This is explicit fixture bookkeeping, not a new product cleanup guarantee.

Initial/intermediate failures are retained in scratch, not counted as final
GREEN: unit probes ran after launch closure, two cache tests incorrectly
expected 64/65 accepted reports despite the unchanged eight-report quota,
and the output oracle initially mistook the payload budget for a wire ceiling.
One intermediate run overlapped product edits and is not validation evidence.
Product fixes enforce runtime-resident ownership across bindings, preserve
explicit empty PATH values and release ownership even when cleanup raises.

Scratch evidence: `~/scratch/co-train-2026-10-31/bash-reporting-28570dc/`,
including `final-validation-receipt.json`, `bash-final-tests.log`,
`affected-regressions.log`, `forwarding-final/receipt.json` and actual
SWE-2 High session exports. No historical receipt was repinned.

No full-suite, deployed-app, external product-model, corpus, training or native
experiment claim. These fixture results do not measure a BIRD baseline or
co-training benefit. Main is not merged by this feature branch.
