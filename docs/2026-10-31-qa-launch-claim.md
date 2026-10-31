# One-shot reporting launch ownership

2026-10-31, base `0d05046`. Branch `feat/qa-launch-claim`.

The existing PTC factory reuse guard was per harness instance. Two distinct
instances could therefore accept the same retained channel. The
[test-first contract](../spec/qa-launch-claim.md) closes that gap before adding
the production Bash adapter.

[`QaChannel`](../ptc/sql_qa.py) now owns a private one-shot launch claim under
its existing lock. [`PTCHarness`](../ptc/harness.py) claims it after exact-type
admission, before runtime/action work. Claim persists after completion or setup
failure; retries require a fresh channel. The existing per-instance weak guard
remains. No global registry, extra synchronization lock or strong history.

Claiming is not a report event, consumes no quota and adds no wire field.
Collector export v1, tool count, budgets, reward/gold and disabled import/copy/
pickle paths remain unchanged. Direct SQL-arm collector reuse across actions
is not changed; this rule applies to launch factories.

Stage 4 remains PARTIAL. Installed verifiers `0.3.2.dev137` discovers
interceptors on tasks, not harness instances. A harness-only post-hoc scanner
cannot deliver acknowledgments during the rollout; no complete Bash adapter
is claimed here. Task/harness composition remains under review.
Reports remain forgeable and unverified; caller owns persistence.
Historical receipts stay dated evidence, never repinned to new source hashes.

## Validation

- **334 existing affected tests passed in 19.70s**, seven collector/harness/
  environment/reporting files, not a full-repository suite.
- **Six new tests passed in 2.70s**: one-shot admission, 12-thread contention
  with one winner, byte-identical export/quota behavior, real cross-instance
  refusal before requests, fresh-channel isolation and setup-failure lifetime.
  No new optional skip guard remains.
- Real cross-instance launch control: baseline GREEN, `_claim_launch` no-op
  RED with `DID NOT RAISE ValueError`, restored GREEN. Mutation hit twice;
  four source/test/spec hashes stayed unchanged.
- Static Python review approved concurrency, lock ordering, lifetime and
  disabled compatibility. Parent ran tests; reviewer performed file review.
- Actual SWE-2 High workers implemented source/tests in parallel. Existing
  disabled import/copy/pickle/no-tracking-lock tests passed unchanged.

Local receipt:
`~/scratch/co-train-2026-10-31/bash-reporting-0d05046/claim-control-receipt.json`.
No real corpus, product model/provider experiment, training or native job ran.
No such execution is authorized by this document.
