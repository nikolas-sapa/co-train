# SQL skill pilot: next-session handoff

Updated 2026-10-25. **This session is closed; the pilot is not complete.**
Use the existing local checkout, not a new worktree or the read-only reference.
Repository commits and scratch evidence have not been pushed.

## Workspace and saved changes

- Writable repo: `/Users/nikolassapalidis/Developer/co-train`
- Branch: `fix/nonfinite-dead-group-monitor`
- Last implementation: `37a519501e1c1d7f8dc0f4928135b97c75d78c1b`,
  strict terminal proof, bounded diagnostics and Docker normalization.
- Outcome documentation: `9e41dd8ec18aeea0c14f4899b23e10097a796e1d`.
- This handoff is a later documentation-only commit. Check current Git status
  and log on resumption rather than assuming an old HEAD remains current.
- No workers, test jobs or owned cleanup are pending at handoff.

Read [frozen protocol](sql-skill-pilot.md), then
[implementation plan](sql-skill-pilot-plan.md) §§8.3–8.5.
Do not revive the discarded broad repository audit from another chat.
Separate weight-training/Prime/T3 work is not this session's scope.

## What is verified

The implementation provides gated capture, executable skill qualification/reuse
and a financially closed model-pilot controller. Caller-authored offline mechanics
are not proof of model-generated skill benefit.

Current runtime source pins:

| File | SHA-256 |
|---|---|
| `ptc/sql_isolation.py` | `4f382b45d2c96ccd540329bbcbd6a82b1336982136ee6d588c3956e40187d602` |
| `ptc/test_sql_isolation.py` | `5949730ff26ce1c55bc5c6ea8326f16bb50677b609e21b34c370c233e32aa4bc` |

- Full current-source offline suite: **3,403 passed**, one unchanged optional
  Torch skip, two deliberate tokenizer deselections, ten existing
  multithreaded-fork warnings. All 132 source/configuration pins unchanged.
- Includes **428 runtime cases**, with zero FD/new-live-thread deltas.
  Forty-seven recorded offline actors were absent; 188 native process
  observations had zero errors. External-network/cache/tokenizer audits: zero.
- Terminal gate mutations produced 18 intended assertion failures across CID,
  freshness, genuine-error priority, joins and RPC-before-STOPPED.
  Seven offline guard canaries refused forbidden operations; loopback passed.
- Focused Python/security static reviews found no actionable issues.
  Static reviews are not runtime or kernel acceptance.
- Runtime protected budget/scorer files remained unchanged. Secret scans passed.

Do not add historical stage counts together or reuse their old profile pins.

## Latest real trial: failed, safely closed

One separately authorized native-pair plus record-lifecycle attempt allowed
at most 19 jobs, no retries, using the existing running Colima and pinned image.
Only **four jobs** were created:

1. Native pair: **two tests passed in 4.49s**, three ordinary CLOSED jobs.
2. Record lifecycle: **one test failed in 0.86s**, at its first PROGRAM,
   before source scoring, qualifications, promotion or fresh-process reuse.

The exact owned stats response had dictionary `memory_stats` but no `usage`.
Worker-side RPC completion was `36442.182172`; fresh STOPPED proof was
`36442.186967916`: **4.795916 ms later**. Consumption/rejection was later still.
These are monotonic timestamps, not wall-clock times.

Strict §8.3 discard correctly refused the pre-STOPPED response. The new code
therefore does **not** fix this observed cleanup race. Do not turn this into
zero/fixed-cap accounting or swallow the observation error.

The failed job retained UNRESOLVED. After separate exact-CID cleanup approval,
one non-force late DELETE removed only its proven stopped container:
`3d426327ae2b97338e5c9978cb2672490284f8bdd96b6986749ef60189e097d6`.
Original five artifacts, expired cleanup deadline and UNRESOLVED journal/block
remained byte-identical. A separate linked closure released only its reservation.

Independent final proof: **all four trial containers and all 18 recorded actors
absent; ten unrelated containers unchanged; no active reservation or unclosed
block**. Cleanup is not retrospective acceptance. No further cleanup is pending.
Do not replay claims, recovery scripts or old acceptance commands.

## Evidence to inspect, not replay

Completion root:
`/Users/nikolassapalidis/scratch/co-train-completion-2026-10-24/`

- `terminal-independent-FiZOcW0x/`: full XML/logs, source snapshot, selected
  nodes, gate mutants and `independent-validation.json`.
  Receipt SHA-256:
  `694a885b151c6f606ecf3f831b73bcb8a35273e27f22cdb4621206a5c2db9be3`.
- `terminal-real-acceptance-hmpp3s96/`: exclusive claims, current profile,
  preflight, native XML, record failure/timing and `trial-final-validation.json`.
  Final receipt SHA-256:
  `4d32f539a0e49a01eab48669cb31276de7cb8fdd7a40287c05ba6b1d5b621abc`.
- Same trial's `late-recovery/late-recovery-receipt.json` SHA-256:
  `c1ffd170dc8e93657a8ddab90df78e7f3d29111f16258309c9ed62bcd9c10aa6`.
- Current trial profile whole-file SHA-256:
  `17c1fd25226768f73339d57036c272b6d3c05f83b6d62701a7c10e2bb803425e`.
  Its claim is consumed, not a reusable approval.
- `production-real-acceptance-flx9gm02/`: earlier failed attempts, four earlier
  authorized recoveries and official public billing evidence. Historical only.

Evidence is local, outside Git. If unavailable in a new environment, report that;
do not fabricate a replacement receipt or claim fresh verification.
Historical spike reference files under `spec/spikes/reference/sql-isolation/`
are immutable: do not edit, repin, slim or replay them.

## Permissions and non-negotiable boundaries

This handoff authorizes no new consequential action. Prior one-shot trial and
exact cleanup permissions are consumed. New real trials need explicit approval;
any late recovery needs separate exact-scope approval. Do not retry unchanged
code or use an old profile after source changes.

- No push/PR/deploy, restart/resize/new VM, sudo, new image pull, dependency/model
  download, daemon switching or unrelated-container changes.
- Do not inspect/edit/switch the other sessions' worktrees. The reference at
  `/Users/nikolassapalidis/Developer/misc/co-train` is read-only.
- Do not modify budget/scorer guards: `train/sql_pilot_budget.py`,
  `train/test_sql_pilot_budget.py`, `spec/sql-pilot-budget.md`, `bench/score.py`.
- Preserve exact existing limits: both roles 256 MiB, zero additional swap,
  pids=1, nofile=64; PROGRAM 10s, SCORER 30s, complete sample ≤4s,
  original cleanup ≤12s. No fresh-budget reset or fabricated charge/headroom.
- Preserve full ownership/configuration proof and the sequence:
  positive stopped proof → token retirement/joins/actor absence → exact DELETE
  → positive absence → matching reservation release. Genuine errors win.
- No broad audit fixes or unrequested infrastructure expansion.

## Financial gate: closed

Pilot model: **`deepseek-v4-flash`**, not the agent model (`gpt-6.1-sol`).
The $50 total/max-25-request authorization is **not** a provider-enforced,
pending-inclusive spending cap. Complete authoritative rates/billable maxima,
no-overdraft/no-autocharge protection and request-specific settled USD receipts
remain missing. Official public prepaid-billing terms did not establish them.

**Zero live model calls.** No credentials, account/API probes, purchases,
provider/model requests or downloads to bypass this gate. No measured model
benefit, dollar savings, generalization or weight-training success is claimed.
Do not ask for a secret to work around missing billing guarantees.

## Start the next session here

1. Verify this checkout's status/log and read §§8.3–8.5 plus the pinned receipts.
   Preserve any newly encountered user work; do not recreate the entire history.
2. Run a **bounded offline diagnosis/design** for the proven pre-STOPPED
   missing-usage gap. Propose a conservative remedy or a concrete blocker.
   The current conditional discard cannot cover this case. A fixed OWN cap
   substitution was rejected because no conservative RAW-overshoot bound exists.
3. Freeze an explicit test plan/non-goals before changing runtime behavior.
   Keep original limits, accounting, ownership, error priority and deadlines.
   Main coordinates specialist review and independently verifies physical evidence.
4. Only after an agreed safe change, test/review/source-bind it. Offline checks
   do not authorize another real trial. Do not run heavy regressions concurrently
   with a real trial; earlier contention caused an observer timeout.
5. Fresh real record reuse and complete kernel/adversarial acceptance still need
   proof. Model-generated pilot benefit additionally needs the financial gate.
   If safety cannot be established, stop; do not expand infrastructure indefinitely.

Suggested new-chat prompt:

> Continue the SQL skill pilot in `/Users/nikolassapalidis/Developer/co-train`.
> Read `HANDOFF.md` and `spec/sql-skill-pilot-handoff.md` first. Start with bounded
> offline diagnosis/design for the proven pre-STOPPED stats gap. Preserve all
> safety and spending gates. Do not run a new real trial, recovery or model call,
> or push, without fresh explicit approval.
