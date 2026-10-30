# Offline SQL reuse demo, 2026-10-29

Scope: portable demonstration of existing caller-authored SQL skill mechanics
and additional offline process/IPC fault tests. No production implementation
changed and no product defect was reproduced. Native acceptance remains open.

## Run from the repository root

Existing compatible Python 3, standard library only; no install or new dependency.
Use trusted local source and assets. Do not use Python optimization (`-O`).

```bash
mkdir -p "$HOME/scratch" &&
PYTHONDONTWRITEBYTECODE=1 python3 -B -m train.sql_skill_demo \
  --work-dir "$(mktemp -d "$HOME/scratch/co-train-sql-reuse.XXXXXX")/run"
```

Each invocation creates a fresh parent and supplies its nonexistent `run` child.
The demo rejects an existing work directory without overwriting; do not rerun
against the same directory. See [source](../train/sql_skill_demo.py) and
[usage](../train/README.md#portable-offline-mechanics-demo).

The hand-authored program discovers the only user table and quotes its identifier.
Existing capture, qualification and reuse APIs run with `executor=None`:

- Capture a valid EX=0 source; qualify once on each 0/1/3/7-row table.
  All four qualifications must be valid EX=1, with four actual dispatches.
- Reject a wrong whole-promotion-envelope pin with zero dispatches.
- Move source/qualification assets out of their five recorded DB paths,
  retaining the files. Decode the candidate/receipt in two distinct fresh
  Python processes and reuse on 11/13-row tables. Each requires one dispatch
  and valid EX=1, without reopening source/qualification DB paths.

The new directory retains captures, candidate, promotion, host-only fixture
inputs, moved assets and `report.json`. Python socket audit guards deny
network/DNS/loopback in the demo and both known children. These guards are
not OS confinement or arbitrary-child telemetry. Local self-approval illustrates
the API; hashes do not authenticate approval.

## Recorded verification

Independent execution validated source against unchanged baseline HEAD
`2ef5cb06cf21299fa7861050ec9a6a477f82feb9`, with no source changes during validation.
Independent Python/general/security static reviews found no actionable issues;
those reviews are separate from execution evidence.

| Check | Recorded result |
|---|---|
| Complete configured default offline suite | 3,682 passed, 1 skipped, 2 deselected, exit 0, 702.86s. No added exclusions. |
| Membership | All original 678 runtime IDs retained; 701 runtime cases, 299 skills/demo cases. Counts overlap the full suite, do not add them. |
| Two independent system-Python demo runs | Each: four EX=1 qualifications, two distinct fresh-process EX=1 reuses, five original DB paths unavailable, zero bad-pin dispatches and zero network attempts per process. |
| Four guard controls | Four baseline passes; separate pin/admission/drain/digest mutations each exited 1 at the intended assertion, not setup/import failure. |
| Full-suite Python audit | External-network/cache/tokenizer counters 0/0/0; 13 permitted loopback events. Parent and inherited-child OS external-IP denial separately verified. |
| Owned-process check | All 144 recorded PIDs absent. Not global process clearance. |
| Protected file identity | `train/sql_pilot_budget.py`, `train/test_sql_pilot_budget.py`, `spec/sql-pilot-budget.md`, `bench/score.py` matched HEAD. |

The skip was unavailable optional Torch. Both deselections are the existing
`tokenizer_integration` configuration; tokenizer integration acceptance was
not rerun. Configured testpaths are `tests ptc ledger bench train`; `step2`
is outside this default suite.

[Process fault tests](../ptc/test_sql_lifecycle_process.py) exercise controller
crashes at grant boundaries, fragmented grant framing/digests, and owned CLI/
Unix-HTTP unwind before grant. They use real local processes/IPC with synthetic
container metadata, not native/container/kernel lifecycle acceptance.

Resource evidence distinguishes transient from settled descriptors: demo
prepare/check can retain two SQLite FDs until garbage collection. Added cases
had zero settled FD delta after explicit GC and no new live threads. No claim
of zero transient descriptors or complete filesystem/FD/thread clearance.
Audit counters do not cover arbitrary native/child events; the OS profile
allows loopback/Unix IPC and is not local-proxy isolation.

Retained validator incidents include a cold observer launch exceeding its
0.2s probe deadline before warmup and an initial outer resource assertion
mistaking transient FD movement for a leak. Evidence was retained; no product
deadlines/assertions were weakened. The passing full run emitted a non-failing
60s faulthandler stack during the nested PTC baseline, which later passed.

## Evidence location and portability

Primary local receipt:
`/Users/nikolassapalidis/scratch/co-train-2026-10-29/independent-validation/validation-receipt.json`.
Its directory also contains `full-suite.log`, `demo-validation.json`,
`control-validation.json` and `final-owned-process-status.json`.
This document summarizes that receipt; documentation integration did not
rerun the full suite or demos.

These original scratch receipts are not committed or portable with a clone.
Missing evidence must be reported as unavailable, not recreated or uploaded
as housekeeping. The repository demo is portable and produces new local
fixture evidence; it does not reproduce the original full-suite environment
or confer native acceptance.

## Non-goals and skipped acceptance

No native trial or full guardian crash/recovery acceptance ran. The earlier
[real lifecycle failure](../spec/sql-skill-pilot-handoff.md#latest-real-trial-failed-safely-closed)
is not resolved by fixture success. No automatic model-generated discovery,
provider inference, training, scientific generalization/benefit, customer
traction, production sandbox acceptance or independently authenticated
approval was demonstrated.

The financial gate remains closed and earlier one-shot permissions consumed.
No new native trial, paid/model call, push or deployment is authorized.
Autonomous-team instructions do not replace these gates. Production defaults,
budget/scorer contracts and historical receipts remain unchanged.
