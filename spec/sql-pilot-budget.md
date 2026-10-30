# Offline SQL pilot budget primitive

## Test plan (before implementation)

1. Admit exactly 50,000,000 USD micros, reject 50,000,001 with byte-identical
   state. Admit 25 sequential settled requests, reject number 26 without consuming
   an ID. Failed admissions change zero bytes.
2. Decode a valid whitespace-padded 65,536-byte envelope; reject 65,537 bytes.
   Reject duplicate/unknown fields, floats/nonfinite numbers, bool-as-int,
   unsupported versions, depth over 12, malformed hashes, configuration drift,
   out-of-range integers, and unreachable historical state graphs.
3. Preserve the full unresolved maximum across fresh opens, both before and
   after dispatch claim. Reject release, duplicate IDs/claims/settlements and
   incomplete settlement. No cancellation operation exists.
4. Run eight real simultaneous processes: exactly one reservation succeeds and
   exactly one dispatch claim succeeds. Kill one owned process after its durable
   claim ACK while it holds the real guard again; kernel lock release must let a
   fresh process observe identical bytes and reject replay. Also race eight
   exclusive initializations, with exactly one winner.
5. Persist under/equal/over-maximum actual charges exactly. Overrun always
   permanently halts admission, even below the total limit. Authorized zero
   requires explicit configuration and settlement SHA.
6. Reject symlinked files/directories, wrong ownership/modes, hard links and
   missing guard beside state. Observe real file fsync, atomic replacement and
   directory fsync; inject commit uncertainty and read real committed state in a
   fresh process. Never claim unsupported filesystem durability.
7. In independent fresh processes, five baseline API sentinels pass. Five
   in-memory mutants (money limit, request limit, unknown retention, single
   claim, configuration binding) each fail one intended assertion, not parsing
   or import. Mutation results remain separate from baseline results.

## Contract and choices

Only stdlib, POSIX, local trusted storage. No dependencies or source integration.
`BudgetConfig` is frozen: `run_id` (1..128 printable ASCII bytes),
`approved_model` (1..256), `profile_sha256` (64 lowercase hex),
`authority_ref` (1..256 printable ASCII, reference only),
`limit_usd_micros=50000000`, `request_limit=25`,
`zero_charge_authorized=False` (exact bool). All identities permit ASCII space
through tilde, not controls. All money is exact int, not bool, in 0..2**63-1.
Explicit zero authorization is required for both maximum and actual zero.
No default rates or inferred prices.

Public API:

* `BudgetLedger.create(directory, config) -> BudgetSnapshot`: exclusively creates
  a **new** directory. An existing directory is never initialized or modified.
  Interrupted creation can require operator investigation; no auto-repair.
* `BudgetLedger.open(directory, expected_config) -> BudgetLedger`
* `ledger.snapshot() -> BudgetSnapshot`
* `ledger.reserve(request_id, max_charge_micros) -> Reservation`
* `ledger.claim_dispatch(request_id) -> DispatchClaim`
* `ledger.settle(request_id, actual_charge_micros,
  settlement_evidence_sha256) -> Settlement`

All returned records are frozen; snapshot requests are a tuple of frozen
`RequestRecord`s. Snapshot exposes settled/reserved/exposure micros as derived
properties. Reservation/claim contain ID and maximum; Settlement additionally
contains actual, evidence and explicit `halted` outcome. `BudgetError` carries
finite fixed messages, not input values. There are no callbacks.

Reserve requires active state, no unresolved request, unused ID forever, fewer
than 25 entries, and settled actual plus unresolved maxima plus new maximum at
most 50,000,000. Failures do not write state. A reserved or dispatch-claimed
request holds its full maximum indefinitely, including timeout/crash/restart.
Only reserved -> dispatch_claimed -> settled transitions exist. A claim is
durably issued permission, not proof of HTTP delivery or upstream exactly-once.
The later trusted runner must use at most one attempt per claim, zero retries.
Settlement requires an exact actual and evidence digest. Missing/invalid data
leaves the request unresolved. Actual above its maximum is persisted unchanged,
with `halted_overrun`, before returning `halted=True`. No more admissions.
Python integer arithmetic never clamps historical totals.

## Storage and implementation plan

Absolute paths only, no expansion, `.`/`..`, or symlink traversal. Ancestors must
be trusted. New dedicated directory is owned by effective UID, mode 0700.
`state.json` and separate permanent `guard` are owned regular mode-0600 files
with exactly one link. Guard has zero content, is never replaced or unlinked,
and exists before state. Open never creates it. Handles bind directory and guard
device/inode identities; each operation reopens and revalidates them.

Every operation opens descriptor-relative with `O_NOFOLLOW`, checks ownership,
permissions, link count and inode identity, then holds real exclusive `flock`
on the guard. State is read at most 65,536+1 bytes before decoding. JSON rejects
duplicate keys, float/nonfinite tokens, excessive depth and unknown fields.
Envelope fields are exactly `format="sql_pilot_budget"`, `schema_version=1`,
`payload`, `sha256`. Payload fields are exactly `config`, `status`, `requests`.
SHA-256 covers canonical payload UTF-8 JSON (sorted keys, compact separators,
ASCII escaping, no NaN). Input envelope whitespace is allowed within byte limit.
Request fields exactly: `request_id`, `maximum_charge_micros`, `state`,
`actual_charge_micros`, `settlement_evidence_sha256`. Unsettled actual/evidence
are null; settled requires both. Validation replays admission history: unique
IDs, at most one unresolved last entry, limits, exact configuration binding,
and overrun only as the final settled entry with matching permanent halt.

Implementation order: immutable types/strict codec/history gates, trusted
descriptor-relative storage, then serialized public transitions. Small shared
money/count/unresolved/claim/config gates must be reached through the real API
and independent sentinels, not test-only stub methods.

Under lock: validate current bytes -> exclusively create random own temporary
file -> write all -> fsync file -> atomic replace -> fsync directory -> ACK.
Initial creation also fsyncs guard, directory and parent. A commit I/O failure
raises explicit uncertainty: caller must not dispatch or retry. Temporary
cleanup only touches the exact own-created regular inode, never broad patterns.
All owned descriptors get a close attempt even if one close fails; a close
failure also reports uncertainty, never a successful ACK. No stale-PID cleanup.
Crash-created orphan temps are not auto-deleted. Foreign file ownership is
fault-injected at the actual fstat boundary in unprivileged tests; symlinks,
permissions, hard links, FIFOs and file locking use real filesystem fixtures.

## Non-goals and admission blockers

This is arithmetic/durability, **not enforcement of real Vyce or image costs**.
No network runner, inference, credentials, rate lookup, billing authentication,
currency conversion, refunds/cancellation, SQLite migration, or integrations.
The approved $50 total and 200 MB image scope do not prove any billable bound.
Provider-enforced $50 ceiling was declined; pricing and maximum billable output
remain unverified. The later admission adapter must establish verified pricing
and billable maxima or a provider ceiling before any inference. This primitive
does not implement the 200 MB image bound.

Authority references, profiles, evidence digests and self-hashes are not
certification or authentication. Trusted callers/profiles can lie. Local fsync
semantics are filesystem-dependent; network filesystems, hostile same-UID
writers, administrative rollback and hardware lying about persistence are not
secured. A persisted overrun cannot undo an upstream charge.
