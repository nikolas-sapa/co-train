# The untrained bash-over-PTC gap does not reproduce. It inverts.

`docs/pre-registration.md` §6, written 2026-09-25 before any run:

> **If the untrained bash-over-PTC gap does not reproduce, the project is over** and the
> correct output is a short negative report on a first-party unreplicated result.

This is that report. It is the pre-committed deliverable, not a fallback.

## What was predicted

**H1** (§4, signed in advance): bash − PTC reproduces at the small end, *"closer to +7 pp
than +22 pp"*. The source paper (arXiv 2609.11999, first-party, **zero citations** by five
independent routes, unreplicated) reports +6.8 to +22.0 pp across four arms.

## What was measured

Run 2h, 2026-10-03. `ledger`, n=14 paired tasks, one rollout each, `deepseek-v4-flash`
via VyceAI, `--max-concurrent 1`, `max_turns 80`. All 28 rollouts `agent_completed`, zero
errors, zero 504s, zero 429s, zero truncations, billed tokens present on both arms.

| outcome (pre-registered) | bash | ptc | |
|---|---|---|---|
| **score** (primary) | 0.857 (12/14) | **1.000 (14/14)** | PTC ahead |
| **cost / solved** (co-primary 1) | $0.0051 | **$0.0006** | PTC **8.5x** cheaper |
| **stability** (co-primary 2) | 12/14, 0 errors | **14/14, 0 errors** | PTC ahead |
| tool-call success rate (secondary 3) | 1.000 | 0.561 | bash ahead |
| shell-call share (secondary 4) | 0.023 | 0.000 | — |
| billed prompt tokens | 660,842 | **82,664** | PTC **8x** fewer |
| tool calls | 266 | **66** | PTC 4x fewer |
| assistant turns | 280 | **80** | PTC 3.5x fewer |

Paired, because the arms share the taskset:

```
paired delta (bash - ptc)   -14.3 pp        <- sign is inverted vs H1
95% CI on the difference    [-35.7, +0.0] pp
discordant pairs            bash-only 0, ptc-only 2, tied 12
exact McNemar p             0.5000
```

## The finding

**H1 is wrong on sign, not on magnitude.** Predicted +7 pp for bash; measured −14.3 pp for
bash. PTC solved every task; bash solved 12 of 14. No task went the other way: bash won
zero discordant pairs.

**bash's only two failures are arithmetic.** On `total-invoice` and `total-receipt` it
fetched all 40 records correctly across 42 turns, listed the relevant ones, and then had to
sum fifteen numbers in context. It got them wrong. The PTC arm wrote `sum(...)` in a program
and got them right. **bash had a shell the whole time and chose not to compute with it** —
its shell-call share was 0.023. That is a model-behaviour result, not a missing tool: forcing
the action to be expressed as a program makes the model compute where a free-text channel
lets it guess.

**The cost result is structural, not noise.** bash re-sends the whole transcript on every
tool call and takes one call per turn, so it billed 8x the prompt tokens for 4x the tool
calls. Per pre-registration §2, cost per successful task was declared a co-primary
*precisely* so this axis could not be chosen after the fact. It favours PTC by 8.5x, and it
would have favoured PTC even had the scores tied.

## What this does not show

- **Not statistically separable at n=14.** The CI on the difference touches zero and exact
  McNemar gives p=0.5000 on two discordant pairs. The sign is clear; the significance is not.
  80% power on this effect needs **39 paired tasks** (242 for the +6.8 pp band H1 named).
  This report claims a failure to reproduce, not a demonstration of the reverse.
- **PTC saturated.** 14/14 is a ceiling: the taskset cannot measure how much better PTC is,
  only that it is not worse. Any future run that wants an effect size needs harder tasks.
- **One model, one provider, one taskset, no repeats.** `deepseek-v4-flash` through VyceAI,
  an unaudited third-party relay — what that model identity means on the far side is not
  verifiable from here, and it is load-bearing.
- **`ledger` is self-authored.** Construct validity is the known weak point
  (`docs/licence-requests.md` tracks the Harness-Bench request that would replace it).

## Why this took seven runs

Six instrument defects, each large enough to produce the published result on its own, every
one of them invisible to a green test suite and visible only against a live endpoint. Five
penalised the PTC arm; the sixth penalised bash. Full evidence in `docs/deviations.md`.

1. The turn budget never reached the PTC harness: PTC got 8 turns, bash 80.
2. PTC's prompt advertised bare tool names at a keyword-only bridge.
3. PTC posted `stream: False` into a relay with an 11s gateway timeout; bash streamed.
4. The fix for 3 dropped the usage chunk, losing a pre-registered co-primary on PTC only.
5. **The catalog returned text no program could parse.** Same three MCP tools for both arms,
   but bash held them as native calls and read their JSON with its own attention, while PTC
   reached them through a sandbox with no `import json`, no attribute access and no `ord`.
   bash's action space was a strict *superset*. On `total-invoice` the PTC model spent 25
   calls building a character-level JSON parser out of `<` comparisons.
6. The arms reported the same transport fault under different type names, so an identical
   relay timeout was retryable on PTC and fatal on bash.

Run 1 reported **+64.3 pp** in bash's favour. That number was entirely instrument. The
honest summary of this project's measurement history is that a +6.8 to +22 pp published gap
survived six of our own defects and did not survive their removal.

## Conclusion

§6's condition is met: the gap does not reproduce, and the deliverable is this report rather
than a training run. The stronger claim this licenses is narrow and worth stating plainly:
**on this taskset, at this scale, the published bash-over-PTC ordering is not reproducible,
and the burden of the six defects it took to stop reproducing it falls on the instrument, not
on the hypothesis.** A first-party, uncited, unreplicated +6.8 to +22 pp result failed to
replicate on its own stated direction.

**Not concluded:** that PTC beats bash. n=14 with a saturated arm cannot carry that, and
nothing here is a verdict on co-training, which was never run.

---

# Addendum, 2026-10-08 — the extended taskset, and what it withdraws

**Everything above this line is left byte-identical.** It reports run 2h on the 14-task
taskset, which is what it says it does, and the conclusion it draws about reproducibility
stands. This addendum exists because two later runs on a *larger* taskset partly withdraw the
inversion, and publishing the report above without them would be accurate by sentence and
misleading by omission.

## Why the taskset was extended, and the handicap that carries

Run 2h scored PTC **14/14**. A taskset the untrained model already solves completely has no
headroom: a co-training run against it could not produce a readable result in either
direction, since 2607.12640 — cited in this project's own pre-registration — finds GRPO helps
*"only when there is headroom to climb"*.

15 tasks were added, 14 → 29. Each is a second-order read of the same five record fields — a
rank, a mean, a link-walk, a set — where the original many-call tier is a single
filter-and-sum pass. No new field, record, or tool.

**This is a post-hoc instrument change** (`pre-registration.md` §8/A5), and it makes the
construct-validity problem worse rather than better: the harder tasks were authored *after*
observing that bash's only two failures on 2h were arithmetic, and the new tier contains more
arithmetic. A reader is entitled to discount this section accordingly, and the Harness-Bench
licence request (`docs/licence-requests.md`) remains the only fix that does not have this
problem. The prediction for the new question was signed before the data existed (§8/A6).

## What the two clean runs measured

Runs 3c and 3d. Both 29 tasks, both arms, `deepseek-v4-flash`, `--max-concurrent 1`. 3c at
`--max-turns 80 --max-retries 20`; 3d at `--max-turns 150 --max-retries 20`. **Run 3d is the
cleanest run in the project: zero voids, zero truncations, 29/29 `agent_completed` on both
arms.**

| | run 3c | run 3d |
|---|---|---|
| score | bash 21/29, ptc 20/29 | **bash 23/29, ptc 23/29** |
| cheap tier (n=11) | bash **+18.2** pp, CI [+0.0, +45.5] | bash **+9.1** pp, CI [+0.0, +27.3] |
| full-scan tier (n=18) | bash **−5.6** pp, CI [−38.9, +27.8] | bash **−5.6** pp, CI [−33.3, +22.2] |
| interaction | **−23.7** pp, CI [−64.1, +15.2] | **−14.6** pp, CI [−49.5, +16.7] |
| exact McNemar, marginal | p=1.0000 | p=1.0000 |
| cost / solved | $0.0099 vs **$0.0013** | $0.0090 vs **$0.0010** |
| billed prompt tokens | 2,245,429 vs **241,561** | 2,229,481 vs **208,780** |
| tool calls / turns | 836 / 864 vs **150 / 179** | 822 / 851 vs **156 / 185** |

## The finding on the extended taskset

**The effect is a tier interaction, and it is not significant.** bash leads where one tool
call suffices; PTC leads where a program must be written to compute. The direction held in
both clean runs. The magnitude did not: the interaction fell from −23.7 to −14.6 pp, both
intervals include zero, and the pre-registered threshold of −25 pp was missed on both
occasions.

The full-scan delta is −5.6 pp in both runs, identical to the decimal. That is 12 against 13
on n=18 — one task apart — so at this n the agreement is as likely to be the small integer
grid as a stable effect, and should not be read as replication.

**Run 3d is an exact tie: 23 of 29 each, p=1.0000.** Any reading of this project that has PTC
winning on accuracy does not survive the extended taskset.

## What has never wavered, in any run

Cost. bash re-sends its entire transcript on every turn and takes one tool call per turn, so
it billed **8 to 10 times** the prompt tokens for the same work across every run: **$0.0071
to $0.0099 per solved task against PTC's $0.0010 to $0.0013.** Pre-registration §2 declared
cost per successful task a co-primary *precisely* so this axis could not be chosen after the
fact. It is structural rather than incidental, and it holds at an exact score tie — which run
3d is.

**The defensible finding of this study is the cost structure, not the accuracy ordering.**

## Two task shapes break the measurement, and the fix is a flag

Full-scan tasks need 40+ turns on bash at one call per turn, which trips a per-account
request-rate limit on the relay. Run 3b lost **10 of 29** bash rollouts that way, every one a
40-call task and not one a cheap task. `--max-retries 20` takes that to zero; `--max-turns
150` clears the single truncation 3c still carried. Run 3a, separately, was void because it
was launched at the *default* `--max-retries 0` — my own error, and the first run launched
from a recipe I had written hours earlier that omitted the flag.

## bash does not compute, even where a shell is the answer

Measured from the traces rather than inferred (`ptc/audit.py`). bash's shell-call share on the
full-scan tier: **0.023** (2h) → **0.0140** (3c) → **0.0300** (3d), with 4 then 6 of 18
rollouts doing any arithmetic at all. **Its full-scan score did not move: 0.667 in both clean
runs.**

A6 named this the prediction most worth being wrong about, because a share rising *together
with* the score would mean the mechanism is tool availability rather than channel, and the
framing should be retired. Availability rose. The solve rate did not. The mechanism is not
availability.

## Nine more defects, three of them in the tools that read the result

The report above counts six. The ledger at the top of `docs/deviations.md` now counts twelve:
nine in the harness and three in `ptc/paired.py` and its callers — a partial-run guard that
only fired on an empty overlap, a reader that scored an errored rollout 0.0 and so could not
distinguish a crash from a wrong answer, and an interaction interval computed on the reverse
difference. The last was caught because the point estimate sat outside its own confidence
interval, which a correct percentile bootstrap cannot do.

**The instrument has been the problem at least as often as the thing it measures**, and three
of the twelve faults were in the code that decides what the numbers mean rather than in the
code that produces them. That is the part of this project most worth generalising.
