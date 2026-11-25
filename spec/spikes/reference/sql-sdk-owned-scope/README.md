# Registered SDK retained-scope feasibility

Source-only reference, 2026-10-31, base `a718cf5`. Not configured BIRD binding.

Run both probes explicitly with the qualified SDK interpreter:

```sh
cd /absolute/co-train
PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1 HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY=127.0.0.1,localhost \
  /absolute/qualified/python -I -B -m pytest -p no:cacheprovider -q \
  /absolute/co-train/spec/spikes/reference/sql-sdk-owned-scope/program_probe.py \
  /absolute/co-train/spec/spikes/reference/sql-sdk-owned-scope/scope_probe.py
```

Parent must impose an independent process-level timeout. The source's 25-second
asyncio watchdog cooperatively cancels; it cannot guarantee a wall-clock bound.
Source qualification used a separate 45-second command timeout.

## Measured scratch evidence

- PROGRAM protocol: 3 passed in 2.17s. Real ordinary builder/public factory,
  exact timeout validation, two actual inert runners and one actual close task
  per runner. Outer scope reuses already completed closes. **Not overlapping
  outer-close initiation or active-owner cleanup proof.** Two scripted unit text
  requests; zero PROGRAM/native/SQL operations, enforced by existing guards.
- SDK lifecycle: 5 passed in 2.53s. Original registered Task/Harness/Taskset/Env,
  Agent, scoring gather/wait_for and JSONL writer. Cancels two and three each
  wait for a new caught-CancelledError acknowledgment while close remains held.
  Stock scoring timeout and failed gather sibling retain/join actual scoring
  tasks. Scope revocation follows close and task drain.
- Fresh negative/restored interpreters: one selected test each passed in
  2.51s / 1.76s. Negative skips exactly one actual score-close-before-reward
  await, hits once, and fails the named `PUBLICATION_BARRIER: reward` assertion
  inside its expected-failure check. Restored plugin has zero fault hits.
  **This does not bypass or qualify sensitivity of Env's writer barrier.**

Python and security source reviews approved this bounded synthetic scope.
The SDK reference reuses the existing first-party guarded scripted loopback
fixture and its runtime/transport drains. No SDK patch, stock timeout removal,
process-group fixture, SQL scoring, provider requests or native execution.

## What remains unproved

Actual owned PROGRAM/SCORER controllers and ACK authority; shared Task concurrent
samples; retained-draw 8/7/1 admission; decoder-produced native results; original
12-second unknown-proof retention and independent 19.5-second SAFE teardown;
association/invalid-to-zero/Env-writer-barrier mutation controls.

Keep these limits when using the pattern. Implement production fresh from its
specification, not by promoting this cooperative resource or empty catalog.

## Pending-before-result sibling scheduling

`sibling_probe.py` re-exports the original guarded composition probe and its
framework fixture, avoiding a second copy of the scheduling/AST checks.
The original probe passed once in 3.95s on 2026-11-01 under an independent
30-second command watchdog. Run this reference explicitly with the same
qualified interpreter and pytest flags, not the older probes' asyncio timer.
After focused Python/security review, the explicit reference run collected
exactly one test and passed in 3.43s under the same 30-second watchdog.

PROVES: Actual stock SDK Harness.score reaches its post-base check while the
original Task.score callback is pending before any result. One declared
fixture error causes unchanged Env cleanup to cancel/join that child through
a held original public close. Seven rows contain six MOCK successes and one
failed unrewarded target; guarded native/process/signal attempts remain zero.

SHORTCUT: Six results are explicit ExResult mocks; scorer admission/close uses
the existing empty-job composition fixture. The unused target mock is never
returned. MISSING: Actual-owned sibling cleanup, native ACK/current SAFE,
active-query cancellation, fast-close/late-sibling race and independent
writer-bypass sensitivity. This does not relax the remaining contract gates.
