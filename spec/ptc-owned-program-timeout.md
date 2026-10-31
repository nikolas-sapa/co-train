# Owned program timeout preflight

2026-10-31. Base `6c0ab18990ee5df7e8cfbf19d3f2ae0d6a500906`.
Prerequisite selected by `sql-owned-invocations.md:253–263`, not a SQL adapter.

## Test plan, before implementation

| Gate | Numeric acceptance |
| --- | --- |
| Optional compatibility | Existing runners with no validator retain their dispatch, observations and exactly-one close. Disabled ownership never inspects this hook. |
| Captured timeout | One synchronous `validate_program_timeout(timeout)` call per valid runner, before model request 1. It receives the exact launch-captured timeout subsequently passed to every program, even if factory or validator mutates config. |
| Accepted validation | Returning exactly `None` permits the normal loop; two program calls still produce one validation and one close. Generic core imposes no SQL-only 5s restriction. |
| Refused validation | Each validator exception propagates before any policy/program call, with one retained runner close. `ProgramRejected` at preflight is not tool feedback. |
| Invalid hook | Explicit non-callable values, coroutine functions and async-generator functions fail before any policy/program call. Valid runner closes once. Missing attribute alone means no validation. |
| Invalid result | Non-None results, including false/zero, coroutine, async generator and custom awaitable fail before any policy/program call. Returned bare coroutine is closed without executing it; arbitrary awaitables are not driven or cancelled. Runner retains responsibility for anything it created. |
| Lookup failure | A non-AttributeError raised while obtaining the hook still produces zero policy/program calls and exactly one close. |
| Cleanup priority | Validation failure cannot skip retained cleanup. Failed/non-None cleanup remains infrastructure-fatal. Three caller cancellations during held cleanup cannot detach it. No original-exception-identity enhancement to existing close semantics is claimed. |
| Actual SDK | At least one actual configured SDK episode reaches an inert owner that refuses timeout before policy. Zero model requests, zero owner program calls, one close, no successful episode or scorer call. Use original Task and normal Agent/evaluation lifecycle, not harness assignment. |
| Sensitivity | Removing only the validation call causes a named intended pre-model-refusal assertion to fail. Restored positive passes; no production bypass hook. |

Use existing finite/non-bool timeout admission unchanged. Invalid launch values
that already fail before factory construction must still construct zero owners.
Only a runner constructed with valid async `run_program` and `aclose` methods
is covered by the exactly-one-close obligation.

## Contract and implementation

Add optional duck-typed `validate_program_timeout(timeout)` to trusted inert
owners, without making it mandatory in `OwnedProgramRunner`. A unique sentinel
distinguishes absence from an explicitly invalid hook. Resolve and call it inside
the existing runner `try/finally`, immediately before `_loop`. Enforce a callable
synchronous hook and an exact None result. Do not await validation or introduce
another timeout, thread, task, cancellation mechanism or configuration field.
Validation exceptions remain fatal launch errors, not model-visible feedback.
Continue using existing retained `_close_program_runner`.

Tests precede production edits. Python/security review precedes new actual SDK
execution. Existing SDK fixture ownership remains reference evidence, not proof
of native SQL cleanup. New SDK preflight tests must prevent program/process
dispatch even when validation is missing, using an inert fixture owner.

## Non-goals

No native SQL program/scorer adapter, TaskData-to-SqlTask provenance guarantee,
configured BIRD binding, real draw/baseline/training, SDK modification, source
repinning, native/profile/model/corpus/spend activation or process-group signals.
Native PROGRAM's existing 5s worker default and 10s containment ceiling do not
change. A later adapter must validate its supported timeout and fresh source
binding before model dispatch, retaining execution-time admission checks.

## Verification

Independent tests initially produced 20 intended failures and 6 passes, with
the actual SDK case deselected. After implementation, all 26 unit cases passed.
The final affected run passed 322 cases in 17.46s, including the guarded actual
SDK refusal and 295 existing harness/owner/configured-QA regressions. Not the
full suite. The SDK case uses an inert owner and denies unexpected SQL scoring;
it proves preflight routing, not native SQL execution or cleanup.

The portable `spec/spikes/reference/ptc-owned-program-runner/timeout_control.py`
control bypasses validation exactly once and reaches the named intended
pre-model assertion, with source bytes unchanged. A separate fresh interpreter
passes its restored positive. No production bypass selector exists.
