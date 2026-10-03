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
