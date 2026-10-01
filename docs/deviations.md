# Deviations from the pre-registration

Append-only. Each entry is written **before** the run it governs, for the reason
`pre-registration.md` gives in its own preamble: choosing the metric afterwards is
choosing the result. The same holds for choosing the instrument afterwards.

The pre-registration is silent on amending the instrument, re-running, and reporting
a discarded run. No procedure was followed because none was written. This file is the
procedure from here on.

**Status: UNSIGNED.** Authored by Claude under Nikolas' direction, 2026-10-01. It
records what was done and what is predicted; it is not an owner's signature on the
amendment.

---

## Deviation 01 — untrained measurement, run 1 void on instrument defect

**Run 1.** 2026-10-01, `ptc/compare.py real`, taskset `ledger`, n=14, `num_rollouts=1`,
`deepseek-v4-flash` via VyceAI `/v1/chat/completions`, prices 0.09/0.18 $/M, $0.16 billed.
Traces `~/scratch/ptc-real/traces/`, log `~/scratch/ptc-real/stdout.log`.

**Result as measured.** bash 0.8571 (12/14), PTC 0.2143 (3/14), gap **+64.3 pp**. CIs
disjoint. All 28 rollouts real (non-zero `num_total_tokens`), zero error stops, zero
truncations *reported*.

**Why it is void.** +64.3 pp sits far outside both published figures (+6.8, +22.0) and
outside this project's own H1 prediction (~+7 pp), in the direction two instrument
defects push it:

1. **The turn budget never reached the PTC arm.** `ptc/harness.py:135` defaulted
   `PTCHarnessConfig.max_turns` to 8; `compare.py:138` set `agent["max_turns"] = 80`
   but never `agent["harness"]["max_turns"]`. The cap bound on **11 of 14** PTC
   rollouts (turn counts `[3,5,7,7,8,8,8,8,8,8,8,8,8,8]`). Bash peaked at 44 of 80 and
   never bound. This is the defect the 2026-09-29 4→80 decision targeted, inverted:
   it handed bash the aggregation tier.
2. **The rig reported the binding cap as zero truncations.** `metrics.py:186` counted
   only episode-level `trace.is_truncated`, which a harness-internal give-up never
   sets. The table printed `TRUNCATED (budget) 0` while the cap bound 11 of 14. The
   instrument asserted its own soundness falsely.

A third, smaller defect: the PTC system prompt advertised bare tool names
(`harness.py:208-209`) while `_bridge` is keyword-only by design, so the model wrote
`ledger_get("r1")` and was refused. 34 of PTC's 54 tool failures were this one
mismatch. The remaining ~20 were the AST allowlist working as designed.

**Not confounds, checked.** `sampling.max_tokens` 512 never bound on either arm (zero
`length` finish reasons; longest completions 603 bash / 343 PTC). Note separately that
VyceAI ignores `max_tokens`, so it provides no cost ceiling.

**Fixes.** Instrument only. Turn budget propagated to the PTC harness; budget
exhaustion surfaced in the truncation metric; real parameter signatures formatted into
the PTC system prompt. `_bridge` stays keyword-only and the AST allowlist is unchanged
— PTC's permitted action space is **not** widened, only its description. Each fix
carries a check proven red against the unfixed code. Suite 110 → 118.

**Run 1 is retained and reported, not discarded.**

### Predictions for run 2, recorded before it executes

Same endpoint, model, taskset, n, and prices; only the three instrument fixes differ.

- **P1.** PTC tool-call success rate rises from 0.443 toward the source paper's
  untrained 65.2% (Table 2). Predicted band **0.60–0.80**.
- **P2.** PTC solve rate rises from 0.2143. Predicted band **0.40–0.70**.
- **P3.** The gap narrows sharply from +64.3 pp but bash still leads. Predicted band
  **+10 to +35 pp**.
- **P4.** The gap likely still exceeds +22 pp, i.e. **above both published figures and
  above H1's ~+7 pp**. If so, that is evidence against H1's *magnitude* even on a
  repaired instrument, and must be reported as such rather than absorbed.
- **P5.** PTC's cost-per-solved-task advantage ($0.0024 vs bash $0.0044) **shrinks or
  reverses** once PTC is allowed its full 80 turns. Its run-1 win on the cost
  co-primary was partly purchased by being cut off at 8 turns, and that must not be
  banked as a finding.

Falsification of a prediction is a result, not a reason to amend again.

### Asymmetry declared, per §5

§5 requires action-space altitude held comparable across arms **or the asymmetry
declared**. It is not comparable and is hereby declared: a deliberately minimal PTC
vocabulary under an AST allowlist runs against a composed shell with unconditional
`bash`. Per `08` §8 this makes a PTC *loss* unattributable between the harness
paradigm and the vocabulary. Real mode also carries no control arm (2026-10-01
decision); canned mode carries the tool-dependence proof instead.

### Instrument change that moves a co-primary input

Fix 3 lengthens the PTC system prompt (the keyword convention sentence plus rendered
signatures). PTC's prompt-token column therefore moves between run 1 and run 2 for a
reason unrelated to model behaviour, and billed cost per successful task is a
co-primary. Run 2 must report PTC's prompt tokens as not comparable to run 1's on
this axis; the comparison that stays valid is bash-vs-PTC *within* run 2.

### Known residual threats to run 2

- Provider treats the arms unequally: every 504 in run 1 landed on PTC, none on bash,
  its longer catalog prompts drawing gateway timeouts. Retries mask the fatal ones;
  the asymmetry remains.
- `--max-concurrent` and `--max-retries` were added to survive 429/504 and are
  default-off. Run 2 must record the values used.
- No prompt caching (`cached_tokens` absent on all 379 calls), so re-sent transcript
  tokens bill at full input rate and cost is an upper bound.
- n=14, one rollout each, one model, one provider, no repeat for variance.
