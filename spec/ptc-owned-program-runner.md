# Optional owned program runner for PTCHarness

## Status and reference

Framework extension only. No native adapter or execution-profile activation.
Reference: `spikes/reference/ptc-sql-ownership/`. Its six fixture gates and
directed trace-at-close diagnostic show why the generic thread prototype is
not the production SQL ownership architecture.

Use existing PROGRAM/scorer isolation for the eventual SQL adapter. That
controller still needs explicit cancellation/cleanup acknowledgment and timeout
fidelity. An unresolved guardian is not cleanup completion. This increment
provides only the ordinary harness injection seam and lifecycle tests.

## Test plan, before implementation

1. **Default compatibility:** existing harness and configured PTC QA tests stay
   green. With no factory, keep the existing catalog execution and HTTP/SSE
   path; no isolation imports, selection, or execution.
2. **Exact dispatch and observations:** two submitted programs cause exactly
   two calls to one launch-local runner, with exact source and configured
   timeout. Runner observations appear verbatim in the next real tool messages.
   Exactly one model-facing tool remains `run_program`.
3. **Original data/catalog:** factory receives the identical launch TaskData
   and the actual compiled launch catalog, including the print callback.
   It runs once before the first model request. Unsupported catalog entries
   can therefore be rejected before dispatch, not silently discarded.
4. **Closed unsupported combinations:** injected runner with QA or MCP is
   refused before harness MCP discovery, factory invocation or model request.
   Non-callable/async factories, invalid runner methods and non-finite or
   nonpositive injected program timeout are refused before model dispatch.
5. **Fatal infrastructure:** explicit infrastructure errors, unexpected runner
   exceptions and non-string results produce zero subsequent model requests.
   They are not converted to retryable `error:` tool feedback. ProgramRejected
   remains ordinary model-visible rejection data.
6. **Owned close:** normal completion, program rejection and failure each close
   the runner once. Cancel twice while close is held at a bounded fixture gate.
   Caller cannot exit before close completes. New cancellation during otherwise
   normal close also propagates, after close completion.
7. **SDK composition:** canonical JSON resolution, original Task, configured
   test-only binding and ordinary PTCHarness delegate to the seam. A fixture
   process executes actual Python SQL/catalog code, not scripted observations.
   Cancel only after at least one actual SQLite VM progress signal. At caller
   exit: zero live captured worker-group members, child reaped, no extra policy
   dispatch, hooks setup only, score not called. A fresh rollout gives typed
   integer 42, EX1 and exactly one completed persisted JSONL record.
8. **Sensitivity:** an isolated bypass of retained close joining makes the
   ownership assertion RED with one selected test and a recorded bypass hit.
   An infrastructure-error-to-feedback bypass makes the no-next-request gate
   RED. Restore source bytes and rerun affected positives.

Fixtures use tiny synthetic databases, scripted interception clients and
bounded 127.0.0.1-only SDK listeners. Fixture process cleanup is not evidence
that the existing Docker controller's unresolved-guardian paths are fixed.
Use finite scheduling gates, outer test caps and owned child kill/drain on
every test exit. No provider, corpus, Docker or native image execution.

## Contract

Add optional constructor argument `program_runner_factory` to `PTCHarness`.
It is a synchronous, inert, trusted host callback:

```python
factory(data: TaskData, catalog: Catalog) -> OwnedProgramRunner

class OwnedProgramRunner(Protocol):
    async def run_program(self, code: str, *, timeout: float) -> str: ...
    async def aclose(self) -> None: ...
```

The factory creates a fresh runner for each launch. Like existing caller
catalog functions, it is trusted configuration, not model-controlled code.
It must not start work before returning its owner object. It must validate
the actual catalog against its supported action space and fail closed on
unsupported entries. No constructor or JSON config silently selects a profile.
Async factory functions and awaitable factory results are unsupported.
The factory must not mutate supplied data, catalog or harness configuration.
The admitted program timeout is captured once for the injected launch.

Create the runner after assembling the launch catalog but before `_loop` and
its first policy request. When the reference protocol is absent, keep the same
system prompt and schemas. A complete opt-in reference protocol consists of
synchronous `reference_descriptor` and `validate_launch` plus asynchronous
`run_reference`; partial or incorrectly typed protocols fail closed.
It adds only a bounded canonical public descriptor with exactly `skill_id`,
`promotion_sha256`, `scope` and the fixed instruction
`Select this approved skill by ID and promotion digest.` All values are strings:
nonempty skill ID at most 256 UTF-8 bytes, scope at most 1024 bytes, a 64-character
lowercase hexadecimal promotion digest, instruction at most 256 bytes, and
canonical serialized descriptor at most 2048 bytes. No private task/gold,
candidate program, host paths or approval material is advertised.

Opt-in keeps the single original `run_program` tool and SDK loop, with a closed
union of exactly `{"code": str}` or
`{"skill_id": str, "promotion_sha256": str}`. Reject duplicate/extra keys,
incomplete or mixed forms and unknown tool names. Validate launch authority
before the first policy request and after every response, before tool-argument
parsing, direct-code/reference dispatch or final/no-tool handling. The SQL
reference path freshly validates approval and admits current promotion/task/
instrument/DB/source binding before dispatching the admitted candidate program
through the original `run_program` path.

Keep interception, tool-message forwarding, original Task/scorer and SDK
lifecycle/writer unchanged, including existing ACK and retained cleanup handling.
Preserve the existing `_loop` call shape when injection is absent. Host
association with the actual SDK Task/scorer is not inferred from typed-equal
settings, and the generic protocol does not prove custody.

Injected execution returns final observation text, including any native
rejection formatting, without a second renderer or serialization scheme.
ProgramRejected raised by a runner keeps existing rejection handling.
Introduce `ProgramInfrastructureError`; re-raise it before the legacy broad
exception-to-feedback handler. Wrap other injected-runner execution exceptions
and invalid result types as infrastructure errors. Cancellation propagates.

Always retain and shield one `aclose()` task after runner creation. Join it
through repeated caller cancellation, consume its outcome, then propagate
cancellation. Never suppress a new cancellation during otherwise-normal close.
Cleanup failure or self-cancellation is infrastructure failure, not successful
cleanup. A close result other than `None` is not an acknowledgment. The runner
must retain all in-flight handles across cancellation and
may acknowledge close only after its resources are released.

This protocol does not independently prove an arbitrary callback's cleanup
claim. The SQL adapter must provide source-backed, independently tested worker,
observer, guardian and connection release evidence. Caller-supplied callbacks
remain responsible for bounded behavior.

## Implementation plan

1. Add the protocol, infrastructure error and private retained-close helper in
   `ptc/harness.py`. Constructor validation and launch-local factory binding
   must leave the disabled path unchanged.
2. Route injected program actions through the runner in the existing `_loop`.
   Do not fork the loop, modify installed SDK files or assign `agent.harness`.
3. Add independent unit and actual SDK lifecycle tests, using owned fixture
   processes only. Run intended-failure controls, affected existing tests and
   Python/security review before publication.

## Non-goals

- No canonical SQL tracer/kernel redesign or claim its legacy cleanup is fixed.
- No PROGRAM/scorer controller cancellation API, guardian changes or repinning.
- No real native/profile activation, policy/checkpoint/tokenizer/backend choice,
  model/corpus/draw/baseline/training run, spend authorization or repeat count.
- No reuse of report-only configured PTC QA for a BIRD SQL catalog.
- No OS sandbox, universal I/O deadline or arbitrary callback containment.
- No claim that a seam or fixture establishes complete paired-runner coverage.

The eventual BIRD adapter still requires explicit fail-closed profile admission,
timeout preservation, complete cleanup evidence, private gold/scorer ownership
and exact persisted paired coverage before statistics.
