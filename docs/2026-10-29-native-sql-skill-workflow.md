# Bounded native file-SDK and Timer acceptance, 2026-10-29

Completed caller-authored fixture campaign through the actual
[file SDK](../train/sql_skill_workflow.py) and
[outer Timer](../bench/sql_reuse_timing.py).
This adds bounded native SDK happy-path coverage, beyond the earlier
[direct-evaluator trial](2026-10-29-bounded-native-acceptance.md).
It does not establish full adversarial/kernel acceptance or measured benefit.

## Actual workflow and approval boundary

Phase A used 11 native jobs: source PROGRAM/SCORER pair with valid EX=0,
one SDK source-rescore SCORER with EX=0, then four qualification
PROGRAM/SCORER pairs, all valid EX=1. Canonical candidate, captures and promotion
were saved through the existing SDK. Qualification alone remained UNAPPROVED.

After reading the candidate program, all four captures and promotion against
whole-file pins, the supervising caller created a separate approval record
outside the campaign directory. Its pin and approval IDs were forwarded unchanged
to both reuse children. This is external caller review of a fixture, not
independent authentication, customer permission or a production approval feature.

Before reuse, five historical source/qualification DBs were moved and preserved
with matching bytes, inodes, modes and mtimes; their old paths were absent.
Phase B used four native jobs: two PROGRAM/SCORER pairs in two distinct fresh
child processes through `reuse_approved_files`. Both saved captures were
`final_submitted`, valid EX=1, with distinct fresh task/DB IDs and DB digests.
A wrong promotion pin on the actual SDK path, with literal
`allow_execution=True`, dispatched zero jobs.

All four observed phase-native/postproof process exits were zero.
Total campaign: **15/15 CLOSED jobs, 7 PROGRAM and 8 SCORER**, matching canonical
pending/committed finalization pairs, zero retries, model calls or incidents.
This is a separate campaign; do not add its job count to older trials as a
quality, model or scientific metric.

## Timer observations, not a speed comparison

| Synchronous SDK callback | Observed elapsed ns |
|---|---:|
| Candidate preparation | 8,077,375 |
| Qualification | 12,050,838,458 |
| Fresh reuse 0 | 2,840,889,708 |
| Fresh reuse 1 | 2,864,164,541 |

These instrumented spans include actual SDK reads, writes, rename and final
fsync inside each callback. Source generation's two jobs, fixture construction,
process bootstrap, parent approval and observation finalization are excluded.
There was no baseline measurement or causal comparison. Qualification versus
reuse durations do not establish speedup, net savings or amortized benefit.
Billing, tokens, human review cost, provider latency and quality comparison
remain unavailable.

## Cleanup, resources and unchanged production

All 15 owned container IDs and 75 recorded owned actor PIDs were physically
absent; active reservations and unclosed blocks were zero. Normal owned-container
DELETE cleanup occurred. Historical DB files were preserved, not deleted.
Ten unrelated containers retained the same IDs/state; the VM remained up with
nine unrelated containers running. Three VM configurations stayed unchanged.

Maximum cleanup was 0.183541875s against the original 12-second bound.
There were 45 memory samples with maximum interval 0.177080792s (bound 4s);
minimum headroom 682,225,664 bytes exceeded the 469,762,048-byte bound;
post-run headroom was 742,072,320 bytes. Caller and both reuse children had zero
raw and GC-settled FD/thread deltas. These are scoped observations, not global
host clearance or adversarial memory-pressure testing.

All 142 Python sources and 16 native-role files remained unchanged against
HEAD `ced74223aa63e0ccdf7ac77501edc2394feff46f`.
The earlier [3,793-pass offline suite, 28 independent probes and three sensitivity
controls](2026-10-29-sql-qualification-evidence.md) remain their recorded scopes.
No full suite or native campaign was rerun for this docs-only integration.
Fixture guest versions were Python 3.12.15 and SQLite 3.40.1.

## Local receipts and reproducibility limits

Campaign root:
`~/scratch/co-train-2026-10-29/native-readiness/authorized-sdk-native-cb8a1f43/`.
It retains actual `reuse-0/reuse.json` and `reuse-1/reuse.json` captures.

| Local artifact | SHA256 |
|---|---|
| `campaign-final-receipt.json` | `e9a0d9a9dbd5de5957e16d84f20460ab8fab70f5b9f3bfcece23acf92a38f071` |
| `campaign-terminal-receipt.json` | `c21974a979bc39315f658f26d060122ab89955c3b7e7b787b56470f670cbbe91` |
| `campaign-external-completion.json` | `1c7a688018f5727d894d173b18d4c4fa5f28aec09aa405829804738f52ef71ed` |
| `artifact-manifest.json` | `b24e2cb9b5cd3d58ca6c1489d78712a0e7e631e0fde4138abca812a54dd976af` |

The manifest covers 901 campaign and 17 external artifacts; inventory size is
not a quality metric. Separate caller approval:
`~/scratch/co-train-2026-10-29/native-readiness/sdk-native-promotion-approval-cb8a1f43.json`,
SHA256 `24c2cae4e135c60248e0393957cffec9b6954649752f3feec80d36849537a3f6`.

Scratch helper:
`~/scratch/co-train-2026-10-29/native-readiness/sdk-timer-preparation-v3-d7pdzufs/sdk_timer_native_acceptance.py`,
SHA256 `24b26a4a577e19a56ab9ac0a8a514ef19861b8721b3400fd73a48c3464bcb60b`.
Python/security review approved that hardened helper; 21 offline guard
regressions and intended fault controls passed. The helper, approval assets and
native evidence are local, not bundled into Git or a clone-only run command.
Older helper versions and earlier dated receipts remain preserved.

## Remaining limits and authorization

Bounded native file-SDK happy-path acceptance is now covered. Full adversarial
OOM, timeout, guardian/kernel faults, independently authenticated approval,
model learning/benefit, customer savings and team-hour benefit remain unproved.
Generic capture comparison still cannot authenticate provenance or attribute
approved reuse. Native Timer spans are observations, not a benchmark.

The fresh 15-job authorization is exhausted; no additional native execution
is authorized by this receipt. Financial gates remain closed. No new paid,
provider/model, workload-shutdown or deployment permission follows; separate
standing Git instructions remain unchanged.
