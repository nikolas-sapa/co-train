# One-shot reporting-channel launch ownership

2026-10-31, base `0d05046`. Architect-approved prerequisite for production Bash
reporting. Existing PTC reuse guard is per harness instance, not cross-instance.

## Test plan first

- First `_claim_launch()` returns `None`; second refuses with `ValueError`.
- **12 simultaneous threads** claim one channel: exactly **1 success / 11
  refusals**, all join within **5 seconds**, no unhandled worker errors.
- Collector export bytes before/after claim/refusal: **0 differences**.
  Shortcut IDs, event/report counts and quota behavior unchanged.
- Real existing PTC launch fixture: two distinct harness instances use one
  retained channel; first completes, second refuses before **0 additional
  model/action requests**, even after completion.
- Same-instance existing reuse cases stay GREEN. Fresh channels on two
  instances still run successfully with **0 cross-channel events**.
- Inject a post-claim setup failure: retry on a different instance with the
  same channel refuses before **0 actions**; fresh channel succeeds.
- Existing disabled child import/copy/pickle/no-tracking-lock tests pass
  unchanged; use `-I -B` for isolated child code.
- Actual control: replace `_claim_launch` with a no-op; the cross-instance
  real-launch case must become intended call-phase RED. Restore: GREEN.

## Implementation

`QaChannel` initializes a private one-shot flag. Private `_claim_launch()`
holds the channel's EXISTING synchronization lock, atomically tests/sets the
flag, returns None first time, raises neutral ValueError on later calls.
No global registry/new lock/strong-reference history. State lasts with channel.

PTCHarness invokes it after exact-concrete-channel admission and before
runtime/actions. Keep existing per-instance weakref/lock guard initially,
avoiding unrelated refactoring. Claim persists after setup failure/completion.
No new QA imports, tracking state or lock allocation on disabled paths.

Source ownership: implementation worker only `ptc/sql_qa.py`, `ptc/harness.py`;
test worker only new `ptc/test_qa_launch_claim.py`. Parent owns docs/commits.
Future Bash adapter calls the same channel method after its own admission.

## Non-goals and limits

No Bash adapter/hook guessing yet, public tool/schema/CLI changes, SQL task
addition, direct SQL-arm channel ownership change, collector export-version
change, budgets/rewards/gold/gates, persisted sink or native/model/training run.
This enforces factory fresh-per-launch ownership, not authenticated telemetry
or prevention of arbitrary trusted host writes. Markers remain forgeable.
Source hashes change; historical receipts remain historical, never repinned.
