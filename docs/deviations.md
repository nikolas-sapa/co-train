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

## How to launch a real-mode run (recorded 2026-10-07, because it was not written down)

Every run below names the relay as "VyceAI" and none of them records the endpoint, so
reproducing one meant reverse-engineering it out of `~/.zshrc`. The invocation is:

```
./.venv-ptc/bin/python ptc/compare.py real \
  --taskset ledger --model deepseek-v4-flash \
  --base-url https://vyceai.com/v1 --key-var VYCEAI_API_KEY \
  --num-tasks 29 --arms bash,ptc --max-turns 150 --max-concurrent 1 \
  --max-retries 20 --price-in 0.2186 --price-out 0.670 --output-dir ~/scratch/<run>
```

**⚠ The price flags changed 2026-10-10 and this is the only place to get them right.**
Every run to date passed `--price-in 0.09 --price-out 0.18`, which nobody had ever checked
against the endpoint. Measured from `x-balance-remaining` deltas: **$0.2186/M input**
(three large-prompt calls with 2-3 token completions gave 0.2207, 0.2174, 0.2177) and
**$0.670/M output** (OLS over six calls with completions of 340-2,284 tokens at a fixed
15-17 token prompt). Any per-call component is below **$1.7e-5** and the same fit puts it at
$2e-6, so there is none worth modelling. Corroborated independently by run 1's recorded
**$0.16 billed** below, which is 1.07x the measured-rate re-derivation of that run ($0.1502)
and 2.65x what the rig computed at the assumed rates ($0.0603). `ptc/metrics.py` now carries
these as `MEASURED_PRICE_IN`/`_OUT` and prints a loud note when a run is priced under them.

**Dollar figures in the void-run records below (2a-2g) are NOT corrected.** They were
computed at the assumed rates and are left as they were recorded, because those runs are
inadmissible and rewriting their numbers would destroy the audit trail without informing
anything. Multiply input by 2.43x and output by 3.72x to compare them with a corrected run.
Only the three admissible runs — 2h, 3c, 3d — carry corrected dollars.

**These are the values that produced a clean run, and they are not the ones this recipe
first carried.** `--max-turns 80 --max-retries 7` was the 2d-2h configuration and is
insufficient on the 29-task set: at 7 retries run 3b lost 10 of 29 bash rollouts to a
per-account rate limit, and at 80 turns run 3c still truncated `longest-chain-start`. Run 3d
at 150/20 is the first with zero voids and zero truncations on both arms. Both numbers scale
with how many sequential model calls the heaviest task needs on the one-call-per-turn arm, so
a taskset with more records needs more of each.

**`--max-retries` is not optional, and its default is 0.** Runs 2d through 2h all
passed 7; the flag exists because the relay throws transient 429s and 504s, and a budget
of 0 lets a single one void the rollout it hits. The first version of this recipe omitted
it, and run 3a -- the first run launched FROM this recipe -- died with 27 of 58 rollouts
errored, PTC 20 and bash 7. That reads exactly like an arm asymmetry and was not one.
`--max-concurrent 1` is load-bearing for the same reason: 2c at concurrency 2 took 429s
that a retry budget of 3 could not outlast.

A retry budget hides a *fatal* fault as well as a transient one, which is the argument for
leaving the default at 0 rather than raising it. A run that needs eight attempts per
rollout is telling you something, so read the retry count in the output rather than passing
the flag and looking away.

**Do not run the test suite while a real-mode run is in flight.** `pytest tests ptc
ledger` serves MCP servers from two different test files in one session, and a live run is
spawning its own; under that contention a server loses the port-startup race and the test
waiting on it burns the ~3 minute port-file timeout. It fails as an *assertion* in whichever
server-dependent test drew the short straw, which reads like a logic regression and is not
one. Two runs on 2026-10-07 failed that way, each on a DIFFERENT test, with suite times of
162s and 696s against a normal 14-17s.

Measured both ways before trusting it: three sequential full-suite runs at the commit before
the A5 taskset extension and three after, nothing else running — 207 passed in 14.3/17.8/14.2s
and 215 passed in 16.4/14.4/14.2s, zero failures. `ptc/test_harness.py` alone is 42 passed in
~11s, 3/3, and does not flake even with a second pytest running concurrently. **A suite time
over ~30s is the tell: read it as contention and re-run clean, do not debug the assertion.**

`GET https://vyceai.com/v1/models` lists the available ids and is free, so it is the
cheap way to confirm `deepseek-v4-flash` still resolves before spending a run on it.
`https://api.vyceai.com/v1` is NOT the endpoint — it answers, but not with JSON.

This does not retire the standing validity threat: the relay is third-party and
unaudited, and what `deepseek-v4-flash` means on the far side is still not verifiable
from here. Writing the URL down makes the run reproducible, not the model identity
trustworthy.

---

## The defect ledger (added 2026-10-08, because the count kept being asserted)

**Twenty-two distinct faults: nine in the harness, six in the adjudication tools, seven in
the instruments built after run 3d.** Written down because three totals were in
circulation and none had been derived. The vault index says "six", which was correct as of
run 2h and stopped being correct at run 3b. An OSF abstract drafted on 2026-10-07 asserted
nine with a "six harness, three tools" split, which sums to nine and describes the wrong
nine. A number in a published abstract has to be derived, not remembered.

**The total moved 12 → 13 on 2026-10-10**, on the one-armed tool-success rate below. Any
text asserting twelve — including the OSF abstract — is now stale.

**It moved 13 → 22 on 2026-10-12/13, and not one of the nine was exposed by a run.** They
were exposed by building the next instrument: the BIRD-SQL taskset, the paired SQL arms, the
frontier gate and the probe's prompt draw. Two of the nine are in `ptc/paired.py` and join
the adjudication tools; the other seven are in `bench/`, `train/` and the new `ptc/sql_arms.py`,
which is neither of the two locations this ledger was built with, so they get a third group
rather than a home that flatters the split. **No run id is invented for them.** The honest
entry in a "run that exposed it" column is that there was no run: the instrument had not
run anything yet, and eight of the nine were found by writing the tests the instrument
needed in order to be trusted. The ninth was found differently and worse: the brief
commissioning this section asserted a count of eight, and the commit it cited for one of
them recorded a third fix nobody had filed. An asserted total hid a defect from the ledger
whose subject is asserted totals.

**Seven of the nine are this project's own, introduced while building that instrument
rather than inherited** (every row in the third table, including a timeout that could not
fire inside the tool written to avoid one, and a guard that could not fail inside the gate
written to make the band mean something). The two `ptc/paired.py` rows are inherited: that
expression dates to 2026-10-03, and every delta asked for between then and now sat outside
the band. The near-miss inside the second row's *fix* is this session's own too — the AST
test written to keep `_attained` independent matched the helper's name as a substring and
failed on `_attained`'s comment about it, which is the same fault class as the row it was
guarding.

**Three summary documents still state the submitted thirteen**, and they are the owner's to
amend, not this file's: `HANDOFF.md`, `docs/outreach.md` (the OSF title, note and abstract)
and `docs/results-untrained.md`.

The `submitted` column exists so that both numbers stay derivable from one table: the
thirteen those documents describe, frozen on 2026-10-11, and the twenty-two the ledger holds
now. `tests/test_defect_ledger.py` reads each of their sentences against the submitted
subset, so none of them can drift to a third number while waiting for the amendment, and
whichever of them is still on the submitted value has to be named in the list above — the
paragraph is parsed, not read. **A fifth document was unpoliced entirely until 2026-10-13:**
`docs/harness-parity.md` said "every one of the thirteen was invisible to a green test suite"
in a sentence no pattern parsed, so the 12 → 13 move had already passed it by and it was
still three days stale when the count moved again. It is tracked as of `04575d4`, corrected
to the live total, and read by the guard now. A guard over ten sites and a guard over eleven
look identical from the ten, which is the whole reason the sites are enumerated in code
rather than remembered.

**The `state` column was added 2026-10-11, and it is not a boolean.** The abstract said
"twelve of them fixed", which was the only count in any of these documents that nothing could
derive: the tables recorded what each fault was and what caught it, never whether it had been
repaired. Forcing it to a boolean would have lied in two places, so there are three states and
the honest total is **20 fixed, 1 not fixable, 1 withdrawn**:

- **fixed** (20) — a code change exists and a test covers it. Verified per row against the
  implementation, not from memory: the turn budget reaching `PTCHarness`, `n_budget_exhausted`
  in the metrics, `render_catalog` in the system prompt, `"stream": True`, the
  empty-`choices` guard, `stream_options.include_usage`, the typed MCP catalog,
  `"HarnessError"` in the retry include-list, `_binom_cdf`'s log space with a max-shift,
  `Fraction` in `_attained`, `compare: str = "set"`, `MAX_ROWS = 500_000`, a defined
  `SECOND_HARNESS_REQUIREMENTS`, `MIN_FRONTIER_TASKS`, a progress handler that reads a
  deadline rather than a flag nothing sets, and `root = pathlib.Path(root)` at the gate.
- **not fixable** (1) — the per-account rate limit. Its own section below is titled *"the
  seventh defect, and it is structural rather than fixable"*: bash issues 475 tool calls
  across 494 turns against PTC's 138, so it meets a request-rate limit roughly three times as
  hard, `--max-concurrent 1` cannot help because the limit is rate over time rather than
  parallelism, and raising the retry budget further would be measuring the relay. It is
  survived per-run, not repaired.
- **withdrawn** (1) — the one-armed `tool_success_rate`. The outcome it produced is retracted
  rather than the instrument corrected, because correcting it means giving the bash arm an
  error channel the predicate can see *and* widening the predicate to catch wrapped
  exceptions on both arms. Secondary 3 stays withdrawn until both exist.

So "twelve fixed" was wrong on its own terms even before the thirteenth was filed: the rate
limit has never been fixed and the ledger has said so since 2026-10-08.

**Counting convention, stated so the total reproduces:** one row per fault that made a run
inadmissible, however it was numbered in the prose below. This file numbers seven of them
(1-7, of which "Defect 5" and "defect 6" appear literally, and 7 is titled "the seventh
defect"). `Deviation 02a` contributes two more that are unnumbered — knock-ons introduced by
defect 4's fix — which is why the numbered total and the true total differ by exactly two.
**Extended 2026-10-12:** one row per fault that would have made a run inadmissible had the
instrument it lives in ever been run, which is the only form the convention can take for a
fault found before the first rollout. Admissibility is the test, not whether a rollout
happened to be burned proving it.

### Harness — nine

| fault | file's label | found by | run | submitted | state |
|---|---|---|---|---|---|
| turn budget of 8 never reached the PTC harness, so the cap bound 11 of 14 PTC rollouts while bash used up to 80 | 1, in `Deviation 01` | run 1's own turn counts | 1 | yes | fixed |
| the rig reported that binding cap as `TRUNCATED (budget) 0` — the instrument asserted its own soundness falsely | 2, in `Deviation 01` | the trace contradicting the table | 1 | yes | fixed |
| PTC's system prompt advertised bare tool names at a keyword-only bridge; 34 of 54 tool failures were this one mismatch | 3, in `Deviation 01` | tool-failure breakdown | 1 | yes | fixed |
| PTC posted `stream: False` into a relay whose gateway timeout applies only to non-streaming requests — 504 on every attempt, so a larger retry budget changed nothing | 4, `Deviation 02` | measuring the endpoint directly | 2d | yes | fixed |
| the SSE parser indexed `choices[0]` on the final usage chunk, which carries `choices: []` — `KeyError` on 2 PTC rollouts, surfacing as a task failure | unnumbered, `Deviation 02a` | the fix's own side effect | 2e | yes | fixed |
| the request omitted `stream_options.include_usage`, so PTC's cost per solved task printed as unknown while bash's did not — a co-primary silently lost on one arm only | unnumbered, `Deviation 02a` | the empty column | 2e | yes | fixed |
| the catalog was not typed and the sandbox denied every parser: same three tools both arms, but bash's action space was a strict superset | "Defect 5" | reading what each arm actually received | 2f | yes | fixed |
| the arms name the same transport fault differently, so retryability was decided by which arm's code owned the socket | "defect 6" | a relay timeout fatal on one arm and retried on the other | 2g | yes | fixed |
| full-scan rollouts die on a per-account request-rate limit, confounding the tier comparison it was meant to produce | "the seventh defect" | 10 of 10 void rollouts being the 40-call tasks | 3b | yes | **not fixable** |

### Adjudication tools — six

| fault | found by | submitted | state |
|---|---|---|---|
| `paired.py` intersected arm task names and only errored on an empty overlap, so a partial run reported `n=12` on a 29-task taskset | pre-flight before reading a live run | yes | fixed |
| `paired.py` scored off `rewards` alone, so an errored rollout summed to 0.0 and was indistinguishable from a wrong answer — ten crashes would have read as ten failures | reading 3b's own output | yes | fixed |
| the interaction interval was computed on the reverse difference; an estimate sat outside its own CI | the number looking impossible | yes | fixed |
| `tool_success_rate` was only ever instrumented on one arm: a failure is a result whose text starts with `rejected:`/`error:`, which only the PTC harness emits, so bash printed 1.000 on 822 calls by construction and secondary 3 compared a measured rate against an unmeasurable one | the training lane testing a guard, 2026-10-10 | yes | **withdrawn** |
| `power_pairs` built each binomial term as `comb(d, i) * p ** (d - i)`, which converts the exact big integer to float first and raises `OverflowError` past d of ~1030, so every delta between 0.02 and 0.04 crashed instead of answering. Bounded on *both* sides, which is why no run ever touched it: delta >= 0.05 answers at a d below the ceiling and delta < 0.02 takes the lower `hi` bound and stops at d of 1000. All four published figures (59, 398, 859, 1571) sit outside the band | the bench lane siting the new taskset's power at a delta nobody had asked for before, 2026-10-12 | no | fixed |
| `_attained` carried the same overflowing expression, and it is `demo()`'s *independent* check on the search, so the obvious repair (route it through the fixed helper) would have made the check agree by construction. Given exact `Fraction` arithmetic instead, a third method, and pinned by an AST test on call nodes | repairing the row above; the AST test's own first version matched the helper's name as a substring and failed on `_attained`'s comment about it | no | fixed |

### Instruments built after run 3d — seven

Same columns as the table above, and the same counting rule, but no `run` column: none of
these seven was exposed by a run. They were exposed by building the instrument the next runs
will use, before it had run anything. Each fault names its own file, because "the harness"
and "the adjudication tools" are the two locations the project had when the ledger was
written and these are in neither.

| fault | found by | submitted | state |
|---|---|---|---|
| nothing pinned `bench/score.py`'s comparison default: every comparison test passed `compare=` explicitly, so the one value a caller gets by saying nothing was the one value nothing checked, and it was `multiset` — which makes an EX number incomparable to the published sub-1B figures that site this project's frontier band | reading BIRD's published `evaluation.py` against a lane brief that called multiset its convention, 2026-10-12 | no | fixed |
| `MAX_ROWS` at 100,000 rejected two valid BIRD dev golds that legitimately return 228,765 and 278,230 rows in about a second, classifying them as defective tasks. The instrument penalising valid work is defect 5's shape | measuring the cap against all 1534 dev golds instead of assuming it, 2026-10-12 | no | fixed |
| `SECOND_HARNESS_REQUIREMENTS` was listed in `ptc/sql_arms.py`'s `__all__` and never defined, so `from ptc.sql_arms import *` raised `AttributeError` and three docstrings pointed at nothing | exercising the module's own export list, 2026-10-12 | no | fixed |
| three gate tests in `train/test_train.py` were left failing when `measurement` became a required manifest key without the fixture being updated in the same change. They are the tests asserting the gate *opens*, which is the direction a half-finished guard breaks silently in: a gate stuck shut looks exactly like a gate doing its job | running the whole train suite rather than the file under edit, 2026-10-12 | no | fixed |
| `train/guards.py`'s `n_tasks > 0` was conformant by construction: the solve-rate band is a band over the *retained* subset, so it cannot fail once out-of-band tasks are discarded, and a suite that drew 198 tasks and kept 3 passed every band check. The floor that replaced it is `power_pairs(0.25, 0.5)`, derived at import rather than stored, so it moves when the power function is corrected | the bench lane asking what the band could still reject, 2026-10-12 | no | fixed |
| `bench/make_probe_prompts.py`'s gold-query timeout could never fire: its `sqlite3` progress handler closed over a flag nothing ever set, so it returned 0 forever and the two non-terminating BIRD golds hung the entire draw with no output. A timeout that cannot fire, written into the very tool built to avoid one | the draw producing no output at all, then a test driving an unbounded recursive CTE through the handler, 2026-10-13 | no | fixed |
| `train/guards.py`'s gate accepted only a `Path`: `root / FRONTIER_MANIFEST` raised `TypeError` on a `str`, so the one function whose entire purpose is explaining why the pipeline is shut failed with an operator error on an ordinary argument instead of a reason | not by the code and not by a run: this row exists because the brief commissioning the eight rows above was wrong about the count, and the commit it cited recorded a third fix, 2026-10-13 | no | fixed |

**Five of the nine harness faults penalised the PTC arm, one penalised bash (defect 6), two
were symmetric (the two knock-ons), and one — the rate limit — is symmetric in principle but
falls roughly three times harder on bash per unit of work, because bash makes one request per
turn.** The ledger holds twenty-two rows, and the suite was green over all of them but the
gate tests. The one-armed `tool_success_rate` is worse than invisible: `test_metrics.py`
pinned the two failure prefixes against drift *in the strings*, so the suite actively locked
in the blindness it was meant to guard.

**"Invisible to a green suite" needs splitting after 2026-10-12, because the nine new rows
got past it two different ways.** Three of them are the harder case — a guard that could not
fail, a timeout that could not fire, and a default nothing pinned — where the suite was green
*because* the check could never try, and a check that cannot fail is indistinguishable from
one that passes. The gate tests are the opposite route, and the only row here the suite did
report: they were left *failing*, so it was red and nobody had run it. A red suite nobody
reads and a green suite that cannot fail produce the same silence, and only one of them looks
like a problem.

---

## Deviation 01 — untrained measurement, run 1 void on instrument defect

**Run 1.** 2026-10-01, `ptc/compare.py real`, taskset `ledger`, n=14, `num_rollouts=1`,
`deepseek-v4-flash` via VyceAI `/v1/chat/completions`, prices 0.09/0.18 $/M, $0.16 billed.
Traces `~/scratch/ptc-real/traces/`, log `~/scratch/ptc-real/stdout.log`.

**That `$0.16` is the most load-bearing number in this file, and nobody noticed for nine
days.** It is the only *observed* charge recorded anywhere in the project; every other dollar
figure here is arithmetic the rig performed at prices nobody had checked. Run 1's traces carry
638,627 prompt and 15,773 completion tokens, so at the assumed 0.09/0.18 the rig computes
**$0.0603** — 2.65x below what was actually charged. At the rates measured on 2026-10-10
($0.2186/M in, $0.670/M out) the same traces give **$0.1502**, within 7% of the $0.16. It is
an independent corroboration of the corrected rates, from a route that had nothing to do with
the measurement, and it was sitting in this file the whole time. **Do not edit this line.**

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

## Run inventory (added 2026-10-11, because the count was asserted in two places and disagreed)

**Fourteen arm-pairs carry dated rollouts on disk. The run *labels* run to twelve. Both
numbers are right, and the gap is the point.**

The OSF abstract said *"across ten runs"* until 2026-10-11 — written on 2026-10-08 at commit
`9ae53f8`, which was itself a correction of an earlier "seven", and made stale within hours by
3c and 3d landing the same day. `HANDOFF.md` said the premise *"met a real model twelve
times"*. Neither was derived. Dated from each rollout's own `timing.start`:

| # | first rollout (UTC) | rollouts | `max_turns` | artifact | label |
|---|---|---|---|---|---|
| 1 | 2026-10-01 12:46 | 28 | 80 | `ptc-real/traces-run3-conc1/` | **unlabelled** |
| 2 | 2026-10-01 13:05 | 28 | 80 | `ptc-real/traces/` | run 1 |
| 3 | 2026-10-01 14:30 | 28 | 80 | `ptc-real-run2/traces-attempt-conc4/` | 2a |
| 4 | 2026-10-01 14:34 | 24 | 80 | `ptc-real-run2/traces/` | 2b |
| 5 | 2026-10-02 03:38 | 28 | 80 | `ptc-real-run2c/` | 2c |
| 6 | 2026-10-02 11:05 | 28 | 80 | `ptc-real-run2d/` | 2d |
| 7 | 2026-10-02 11:59 | 28 | 80 | `ptc-real-run2e/` | 2e |
| 8 | 2026-10-02 12:40 | 28 | 80 | `ptc-real-run2f/` | 2f |
| 9 | 2026-10-03 04:57 | 28 | 80 | `ptc-real-run2g/` | 2g |
| 10 | 2026-10-03 05:16 | 28 | 80 | `ptc-real-run2h/` | 2h — **admissible** |
| 11 | 2026-10-07 12:06 | 58 | 80 | `co-train-run3a/` | 3a |
| 12 | 2026-10-07 12:46 | 58 | 80 | `co-train-run3b/` | 3b |
| 13 | 2026-10-08 04:24 | 58 | 80 | `co-train-run3c/` | 3c — **admissible** |
| 14 | 2026-10-08 05:19 | 58 | 150 | `co-train-run3d/` | 3d — **admissible** |

**Three things this resolves.**

**There is no missing 2b.** `~/scratch/` has no `ptc-real-run2b` directory, so the label
sequence "1, 2a-2h, 3a-3d" reads as thirteen directories where only twelve exist. Both 2a and
2b live inside `ptc-real-run2/` as sibling subdirectories — 2a at `traces-attempt-conc4/`, 2b
at `traces/` — exactly as the attempt log below records. Counting directories undercounts;
counting labels is right at twelve.

**Row 1 is an arm-pair that no document had ever counted.** `ptc-real/` also holds two
subdirectories, and `traces-run3-conc1/` precedes the run-1 traces by nineteen minutes. Its
name belongs to a numbering scheme abandoned before run 1 was written up. It is 28 rollouts of
real spend against the relay, and it is why the artifact count is fourteen and not thirteen.
It is not admissible and changes no result; it is counted here because a run that happened is
a run that happened.

**Only three runs are admissible, and that has not changed:** 2h on the original 14 tasks, 3c
and 3d on the extended 29. Runs 1 through 2g carry instrument defects, 2g is unreadable
(defect 6), and 3a and 3b are void — 3a on a `--max-retries 0` launch error, 3b on the rate
limit that flag exists to survive.

**Which number to publish:** *fourteen measured runs, of which three are admissible.* Quoting
a bare count invites exactly the staleness corrected here, because the admissible count and
the attempt count have never been equal and the attempt count only ever grows.

---

### Run 2 attempt log

Run 2 took three attempts. All are preserved; none is discarded.

- **2a**, `--max-concurrent 4`: 429 storm, 21 of 28 rollouts errored. The rig refused
  to print a result and exited non-zero. Void, nothing measured.
  `~/scratch/ptc-real-run2/stdout-attempt-conc4-429.log`, `traces-attempt-conc4/`.
- **2b**, `--max-concurrent 1`: ran 3h18m and completed bash 14/14, PTC 10/14, then
  stopped because the agent driving it died (`402` on its *own* model backend, not on
  VyceAI — zero 402s in any trace, all 10 PTC traces `is_completed=true`, VyceAI health
  `solid` across the whole window). No summary table was printed, so there is nothing
  to mistake for a result. Partial traces retained at `~/scratch/ptc-real-run2/traces/`.
- **2c**, `--max-concurrent 2 --max-retries 3 --max-turns 80`, detached from any agent
  so a driver death cannot end it. `~/scratch/ptc-real-run2c/`. This is the attempt
  intended to be read against P1-P5.

**Both instrument fixes are confirmed to have taken**, on 2b's partial traces:

- Turn budget: PTC turns `[1,2,2,3,11,5,4,12,2,28]`. Nothing pinned at 8, three
  rollouts exceed it, `max_turns: 80` present in all traces. Run 1's wall is gone.
- Signatures: keyword-convention failures went **34 of 54 (run 1) to 0 of 60 (run 2b)**.
  The 26 remaining PTC tool failures are legitimate: 23 AST-allowlist rejections
  (attribute 9, Import 4, ImportFrom 4, Try 2, unknown name 3, program budget 1) and 3
  genuine bugs in the model's own programs.

2b's partial scores are recorded but are **not** a result: PTC 6 solved of 10, bash 11
of 14, and three of those zeros are endpoint noise (two PTC rollouts hit VyceAI 504s,
one bash rollout timed out), so both arms are understated. The four unrun PTC rollouts
were precisely the heavy enumeration tasks, which biases any partial read.

### Why run 2 took four attempts — root cause, not tuning

2a and 2c both died on VyceAI 429s, and the obvious reading (we went too fast) is
wrong. Evidence: 2b (clean) and 2c (11 of 28 errored) peaked at an **identical 49
req/60s** against a documented 60, and 2c's first 429 followed only 21 requests in the
prior 60s, 6 in the prior 30s, 1 in the prior 10s, after a 21-second idle gap. The
arms never even ran concurrently (bash t+0-120s, PTC t+122-506s). All 429s formed one
contiguous **98-second band** (t+64.9 to t+163.1), with zero successful calls inside
it and none after.

So the throttle was **external to this run** and not caused by its request rate. The
rig's failure was that its retry budget could not outlast it: `max_retries=3` gives 4
attempts on a `min(0.5 * 2**attempt, 30.0) * (0.5 + jitter)` curve, a few seconds of
wall clock. All six failed bash rollouts spent every attempt on request #1 and
recorded `nodes=0` — no assistant turn ever produced. Nine of 14 PTC rollouts *did*
retry away 1-3 429s and finished.

**2d** therefore runs `--max-concurrent 1 --max-retries 7` (8 attempts, backoff
capped at 30s each, spanning past a 98s band). No code changed; these are flags.

The five 504s are a separate, relay-side failure: Cloudflare in front of VyceAI,
hitting only PTC's slowest calls (10.8-13.4s against a 1.6s median). Not a client
timeout — `verifiers/v1/harnesses/utils/core.py:453` passes
`httpx.Timeout(600.0 if args.bash else None, connect=5.0)`, so the PTC arm has no read
timeout at all. Note that line as a standing arm asymmetry in the instrument (600s
bash vs unbounded PTC), on the permissive side for PTC.

### Deviation 02 — the PTC arm was not streaming, and only the PTC arm

Run 2d, with `--max-retries 7`, took **zero 429s**: the retry fix worked. It still
failed, on a different and fully deterministic cause. All 45 of its errors were
Cloudflare `504: Gateway time-out`, all on the PTC arm; bash made 261 calls with none.
The same four heavy enumeration tasks failed in 2b, 2c and 2d.

Measured directly against the endpoint:

| request | result |
|---|---|
| non-streamed, long generation | **504 at 11s** |
| identical request, streamed | **200 at 23s** |
| non-streamed, short | 200, immediate |
| large prompt, streamed (TTFB) | 200, first byte 2.0s |

So the relay's gateway timeout applies only to non-streaming requests, and neither
prompt size nor time-to-first-byte is involved. `ptc/harness.py` posted
`"stream": False` while the bash arm streams through `verifiers`
(`harnesses/utils/core.py:266`). PTC's longer programs exceeded 11s and 504'd on every
attempt, which is why a larger retry budget changed nothing.

This is the **third arm asymmetry** found in this instrument, after the turn budget and
the prompt signatures. The PTC arm now streams and accumulates SSE deltas into one
message; the mock transport in `ptc/test_harness.py` streams too, so the suite
exercises the transport production uses rather than the one it abandoned. A check goes
red if the arm ever stops streaming. 123 -> 124 tests.

Bearing on the earlier runs: every PTC number in runs 1, 2b, 2c and 2d was produced
over a transport the bash arm was not using, and on tasks whose programs run longest.
Run 1's +64.3pp is therefore confounded by three defects, not two.

### Deviation 02a — the streaming fix introduced two defects of its own

Run 2e took **zero 504s and zero 429s**: the streaming fix worked, and the PTC arm
went from 55 tool calls and 65 assistant turns (2d) to 251 and 265. It still exited
non-zero, for two causes both created by that fix:

1. The SSE parser indexed `payload["choices"][0]` directly, but the final usage chunk
   carries `choices: []` (and a missing `choices` key on some relays). It raised
   `KeyError: 'choices'`, which surfaced as a `HarnessError` — i.e. it read as a task
   failure — on 2 PTC rollouts.
2. The request omitted `stream_options: {"include_usage": True}`, so the stream carried
   no usage chunk, the interception server recorded no billed tokens, and PTC's **cost
   per solved task printed as unknown while bash's did not**. That is a pre-registered
   co-primary silently lost on one arm only — the same shape of defect as the three
   already found, introduced while fixing the third.

Both fixed, each with a check proven red. 124 -> 126 tests.

Recorded because it is the pattern worth noticing: every fix to this instrument so far
has had to be verified against a real run, and two of four introduced a fresh asymmetry
that the test suite would not have caught on its own.

### Validity threat: the endpoint is an unaudited relay

VyceAI is a third-party relay, not a first-party provider. What `deepseek-v4-flash`
means on the other side of it is not verifiable from here: a relay can route to a
different provider, serve a quantized or substituted model, or cache. The model
identity is load-bearing for this measurement, so this is recorded as a known
limitation of every real-mode number in this project, not as a solved problem.

Related and worth recording because it cost three attempts: this machine routes Claude
Code itself through another such relay (`ANTHROPIC_BASE_URL=https://agentrouter.org`).
Two agents driving these runs died mid-flight on that pool's `402` quota errors, which
is what ended 2b with 24 of 28 rollouts complete. A measurement must not depend on an
agent staying alive; 2c onward run detached via `nohup`.

### Endpoint note

VyceAI ignores `max_tokens` (a request capped at 1 returned 48 completion tokens), so
it provides no per-call cost ceiling. Cost control here is the turn budget and the
price flags, not the sampling cap.

### Known residual threats to run 2

- Provider treats the arms unequally: every 504 in run 1 landed on PTC, none on bash,
  its longer catalog prompts drawing gateway timeouts. Retries mask the fatal ones;
  the asymmetry remains.
- `--max-concurrent` and `--max-retries` were added to survive 429/504 and are
  default-off. Run 2 must record the values used.
- No prompt caching (`cached_tokens` absent on all 379 calls), so re-sent transcript
  tokens bill at full input rate and cost is an upper bound.
- n=14, one rollout each, one model, one provider, no repeat for variance.

---

## Run 2f — the first clean run, and the fifth defect it exposed

2026-10-02, `ptc/compare.py real`, taskset `ledger`, n=14, one rollout each,
`--max-concurrent 1`, `max_turns 80`, `max_retries 7`, streaming with
`stream_options.include_usage`. Traces `~/scratch/ptc-real-run2f/traces/`,
log `~/scratch/ptc-real-run2f/stdout.log`.

**Mechanically clean.** All 28 rollouts `agent_completed`, zero errors, zero 504s,
zero 429s, zero truncations, relay-reported usage on both arms. Every defect found
in runs 1 and 2a–2e is gone from the trace.

| | bash | ptc |
|---|---|---|
| score (primary) | 0.7143 (10/14) | 0.4286 (6/14) |
| cost / solved | 0.0051 | 0.0148 |
| tool calls | 259 | 234 |
| tool success rate | 1.000 | 0.6239 |
| assistant turns | 273 | 248 |

**Paired, because the arms share the taskset.** `compare.py` prints each arm's own
unpaired CI, which throws the pairing away. `ptc/paired.py` on the same traces:

```
paired delta (bash - ptc)   +28.6 pp
95% CI on the difference    [+0.0, +57.1] pp   (lower bound 0.0 at every seed)
discordant pairs            bash-only 5, ptc-only 1, tied 8
exact McNemar p             0.2188
```

Six discordant pairs cannot separate the arms. **The gap is not significant** and the
interval includes zero, so run 2f does not license a verdict on H1 either way — it is
underpowered, not null. The point estimate (+28.6 pp) sits nearer the TAC end (+22)
than the APEX end (+6.8) that H1 predicted, which is evidence *against* H1's direction,
at a confidence the n does not support.

### Defect 5 — the catalog is not typed, and the sandbox denies every parser

The decisive finding, and the reason the +28.6 pp is still not a model comparison.

The two arms do not have comparable action spaces, in a way no previous run surfaced:

- **bash arm** gets four tools: `bash`, plus `ledger_get`, `ledger_ids`,
  `ledger_links_to` as native tool calls. Its `shell-call share` is **0.0000** — it
  never used the shell. It called the typed functions directly and read their JSON
  output with its own attention.
- **PTC arm** gets one tool, `run_program`, over the same three functions inside
  `ptc/runtime.py`'s sandbox — no imports, no attribute access, and a `SAFE_BUILTINS`
  without `ord` or `chr`.

`ledger_get` returns MCP text: the **string** `{"id": "r00", "amount": 8971, ...}`,
because `_bridge` hands `call_mcp`'s result back unparsed. So the PTC arm receives
data it has no primitive to parse — no `json`, no `.split`, no `.keys`, no subscript
by key on a `str`, no `ord` to classify a digit. 46 of its 88 tool failures are the
sandbox rejecting ordinary Python (34 attribute access, 12 import) and 11 more are
`TypeError: string indices must be integers` — the model subscripting a JSON string
as if it were the dict the catalog's own description implies.

On `total-invoice` the model spent 25 calls hand-rolling a character-level JSON parser
out of `<` and `>` string comparisons, discovered `.isdigit` and `ord` were both
unavailable, and got there anyway. It is the one task PTC won and bash lost. The
failures cluster exactly where machine parsing is unavoidable: `total-invoice`,
`total-memo`, `total-receipt`, `largest-record`, `richest-owner`.

This is the asymmetry pre-registration §5 names in advance — *"a deliberately minimal
PTC vocabulary against a composed shell makes a PTC loss unattributable"* — except it
is worse than minimal vocabulary. The bash arm's action space is a strict **superset**
of the PTC arm's: same three functions, plus a shell it did not need, minus the
requirement to write a parser to use them. A "typed catalog" that returns unparsed
text is not typed, and the 17 `unknown name` rejections show the model reaching for
the primitives a typed one would have made unnecessary.

**Fixed, in two places and one prompt.** The catalog is now typed in fact as well as in
name:

1. `ledger/servers/store.py` returns JSON from all three tools -- `ids` a JSON array,
   `links_to` a JSON array (empty rather than `"none"`), `get` a JSON object or `null`
   rather than the prose `"no such record"`. One shape, so one decode rule, and both
   arms receive the same bytes.
2. `ptc/harness.py::_decode` parses that text once in `_bridge`, so a program receives a
   dict or a list. Non-JSON text passes through unchanged; a server returning prose
   still needs a per-server decoder, which is the declared ceiling.
3. The PTC system prompt now says a catalog function returns DATA, not text. Without
   this the decoder opens a new gap: the tool's own description says "returns a JSON
   object", and a model that believes it reaches for the parser that is still absent.

Three checks, each proven red against an isolated mutant (bridge stops decoding; `ids`
reverts to space-separated; the prompt line removed). 126 -> 207 tests across
`tests ptc ledger` -- note that bare `pytest` runs only `tests/` per `pytest.ini`
`testpaths`, so it reports 51 and silently skips both suites that matter here.

> **Tooling note, 2026-10-10.** That last caveat no longer applies: `pytest.ini`'s
> `testpaths` now reads `tests ptc ledger`, so a bare `pytest` collects all three. The
> counts above are left as recorded. `step2` is still a separate invocation, and the
> interpreter must be `.venv-ptc/bin/python` -- the system one has no `verifiers` and
> fails during collection.

This does not advantage the PTC arm. It hands the program the information bash reads
with its own attention, and leaves PTC the work of computing over it rather than
reading it.

### Power, as a number rather than a word

`ptc/paired.py` now reports the paired tasks needed for 80% power at exact McNemar,
given the observed discordance rate. At run 2f's 0.429:

| target effect | paired tasks for 80% power |
|---|---|
| +28.6 pp (2f's own point estimate) | 39 |
| +6.8 pp (pre-reg §3's APEX target) | 732 |

**The APEX-end target is out of reach for this design.** 732 paired tasks at 2f's rate
(28 rollouts in 3h26m at `--max-concurrent 1`) is roughly 180 hours of wall clock. H1 as
written cannot be adjudicated here; it is testable only as a large-effect claim, and the
pre-registration's +6.8 to +8.4 pp target band is not something this instrument can
see. Recorded rather than quietly dropped.

**Sizing the next run deliberately does not mean raising n now.** Both numbers above are
computed from the *broken* instrument: 2f's discordance came almost entirely from the
aggregation tasks, which are exactly the ones defect 5 made unwinnable for PTC. A
required-n derived from that discordance is a measurement of the defect. Raising n by
expanding the per-record families would also push discordance *down* -- both arms solve
every one-call lookup, so 40 more lookups buy tasks and no power.

Order of operations, therefore: **run 2g at n=14 as a calibration run**, claim nothing
from it, read the unconfounded effect size and discordance off it, and size the
adjudicating run from those. One cheap run (2f cost $0.14 in total across both arms)
before committing wall clock to a large one.

---

## Run 2g — the ordering reversed, and defect 6 made it unreadable

2026-10-03, same config as 2f (`--max-concurrent 1`, `max_turns 80`, `max_retries 7`,
streaming with usage), first run after defect 5's fix. Traces
`~/scratch/ptc-real-run2g/`.

| | bash | ptc |
|---|---|---|
| score (primary) | 0.5000 (7/14) | **0.8571 (12/14)** |
| cost total | 0.0643 | **0.0072** |
| cost / solved | 0.0092 | **0.0006** |
| tool calls | 263 | 57 |
| tool success rate | 1.000 | 0.5789 |
| assistant turns | 277 | 71 |
| wall clock | ~25 min for both arms (2f took 3h26m) | |

**The ordering reversed.** PTC above bash, at 15x lower cost per solved task and a
quarter of the turns. Defect 5 was worth more than the entire effect the project set out
to measure.

**And the run is not readable.** `richest-owner` ended `stop_condition="error"` on the
bash arm, so its 0.0 is a transport artefact rather than a result, and `compare.py`
exited non-zero refusing to print a verdict. Correct behaviour; the number above is
reported only because the direction is too large to leave unrecorded, and it is not an
admissible measurement.

### Defect 6 — the arms name the same transport fault differently

`richest-owner` died on `openai.APIError: The request timed out`, raised inside the
bundled runtime script and re-wrapped by the rig as `HarnessError`. The retry policy
included `ProviderError` only -- deliberately, so that a genuine harness or sandbox fault
stays red -- so this was never retried. On the same run a 429 on `total-receipt` *was*
retried and scored 1.0.

The asymmetry is in who owns the socket, not in the fault:

- **PTC** owns its HTTP client (`_stream_message`), so a relay timeout surfaces as
  `ProviderError` → retryable.
- **bash** delegates to the bundled runtime, which raises inside its own subprocess →
  `HarnessError` → fatal.

`richest-owner` is bash's heaviest task (40 catalog calls) and the bash arm is the only
one with a read timeout at all: `harnesses/utils/core.py:453` passes
`httpx.Timeout(600.0 if args.bash else None, connect=5.0)`. So the arm with the deadline
was also the arm whose timeout could not be retried. This is the sixth defect in a row
whose effect lands on one arm, and the first that lands on **bash**.

**Fixed** by adding `HarnessError` to the retry include list, with the reason recorded in
`ptc/compare.py` and in the tripwire test that had to be changed to allow it
(`test_the_retry_policy_is_restricted_to_provider_errors_exactly`, widened once, pinned
again). The original intent survives: a deterministic harness fault exhausts all seven
retries and still ends red.

### Two things run 2g does establish, pending 2h

- **PTC's tool failures are no longer structural.** 24 of 57 calls failed, but the shape
  changed completely: 18 are attribute access the sandbox has always banned and the
  prompt always declared (`.get` x10, `.append` x3, `.keys` x3, `.zfill`), reachable
  another way (`d['amount']` works, `for k in d` works), and 1 is the lone surviving
  `TypeError`. In 2f, 46 failures had no alternative path at all. The arm now fails where
  the model reaches past a declared constraint, which is a model result, not a rig one.
- **The fix was not neutral to the bash arm, and that is a confound to declare.** Making
  the server return JSON changed what BOTH arms read: bash's relay-reported prompt tokens rose
  553925 -> 694679 (+25%) and its score fell 10/14 -> 7/14. So 2f and 2g are not
  comparable on the bash arm either. Only 2h onward, with the fixture fixed, forms a
  comparable series.

---

## Run 2h — clean, admissible, and the premise does not survive it

2026-10-03, same config as 2f and 2g, with defect 6 fixed. Traces
`~/scratch/ptc-real-run2h/`. All 28 rollouts `agent_completed`, zero errors, zero 504s,
zero 429s, zero truncations, relay-reported usage on both arms. **The first run in this
project's history that is both mechanically clean and free of a known arm asymmetry.**

bash 12/14, PTC **14/14**. Paired delta **−14.3 pp** (CI [−35.7, +0.0], exact McNemar
p=0.5000, 2 discordant pairs both PTC's, 12 tied). PTC is **7.53x** cheaper per solved task
on **7.99x** fewer relay-reported prompt tokens, 4x fewer tool calls and 3.5x fewer turns.

**⚠ CORRECTED 2026-10-10 — published as "8.5x cheaper per solved task on 8x fewer billed
prompt tokens".** The `8.5x` was $0.0051/$0.0006, two 4-dp cells divided; unrounded at the
rates then in use it is **8.05x**, and at the relay's measured rates ($0.2186/M in, $0.670/M
out) it is **7.53x**. "Billed" was false: the counts are relay-synthesised, not
provider-billed. Full account in `docs/results-untrained.md`.

Adjudicated against the pre-registration in **`docs/results-untrained.md`**, which is the
§6 negative report. Headline: H1 is wrong on **sign**, not magnitude.

bash's two failures are both arithmetic — `total-invoice` and `total-receipt`, where it
fetched all 40 records across 42 turns, listed them, and then mis-summed fifteen numbers in
context. It had a shell throughout and its shell-call share was 0.023; it chose not to
compute. PTC wrote `sum(...)`.

### A bug in the power function, found by this run's own numbers

`power_pairs` guarded `p >= 1` and returned "not detectable at this discordance". But
`|delta|` can never exceed the discordance rate (both are computed from the same discordant
pairs), so `p` lives in `[0.5, 1.0]` and **`p == 1.0` is the unanimous case -- the easiest
effect to detect, not an impossible one.** Six unanimous discordant pairs already give an
exact two-sided p of 0.031. Run 2h is exactly that case (2 of 2 one way), so the tool
reported its own best-case input as undetectable, when the answer is 39 paired tasks.

Fixed to guard `p > 1`, which is the genuinely impossible case. Pinned by a check proven red
against the old `>=`. Worth recording as the seventh thing in this project that was wrong in
the direction of under-reporting an effect, and the first that was wrong in *our analysis*
rather than in the instrument.

### Required n, recomputed on the fixed instrument

Both figures in §8/A1 were computed from run 2f's broken-instrument discordance (0.429) and
are superseded here. On 2h's discordance (0.143):

| target | paired tasks for 80% power |
|---|---|
| the observed 14.3 pp | 39 |
| pre-reg §3's +6.8 pp | 242 |

242 is roughly 7 hours of wall clock at 2h's rate (28 rollouts in ~25 min), not the ~180
hours A1 estimated from 2f. **The APEX-end band is reachable after all** — A1's conclusion
was an artefact of the defect, which is itself worth recording as the cost of amending from
broken data.

### Ceiling

PTC at 14/14 is saturated. The taskset can establish that PTC is not worse; it cannot
measure how much better. An effect-size run needs harder tasks, not just more of these.

---

## Runs 3a and 3b — the hard tier has headroom, and the bash arm cannot finish it

**First runs on the 29-task taskset** (`pre-registration.md` §8/A5). Both are **void as
comparisons**. One of them answers the question it was launched for anyway, and the other
is a self-inflicted repeat of a lesson this file already contained.

### 3a — void, and the cause was the launch, not the arms

2026-10-07, 29 tasks, both arms, `--max-retries 0` — **the default, and my error.** 27 of 58
rollouts errored: PTC 20, bash 7. Scores printed as bash 0.586 / PTC 0.241, and **none of
that is admissible**: the rig said so and exited non-zero.

The shape of it is the trap. PTC losing 20 rollouts to bash's 7 reads exactly like the
arm asymmetry this project has found six times, and it was nothing of the kind — every
admissible run from 2d on passed `--max-retries 7`, because the relay throws transient
429s and 504s. The recipe at the top of this file was written the same day and **omitted
the flag**, so the first run launched from it reproduced the defect the flag exists to
prevent. Recipe fixed, and `compare.py` now warns at launch when real mode gets a budget
of 0.

### 3b — the headroom question is answered on the arm that ran clean

2026-10-07, same taskset and model, `--max-retries 7`, `--max-concurrent 1`, `max_turns 80`.

| | bash | ptc |
|---|---|---|
| completed | 19/29, **10 void** | **29/29, zero errors** |
| solved | 14 (0.4828) | 20 (0.6897) |
| errors | HarnessError 4, ProviderError 124 | ProviderError 37, all survived |
| relay-reported prompt tokens | 1,079,666 | 209,318 |
| tool calls / turns | 475 / 494 | 138 / 167 |

**The comparison is void.** bash lost 10 rollouts, so no paired delta exists and
`ptc/paired.py` now refuses to compute one (that guard was added the same day, after
finding it would have silently compared the 19 survivors and called it `n=19`).

**What is readable: A5's extension worked.** The PTC arm completed every rollout with zero
errors and scored **20/29 (69%)**, against **14/14 (100%)** on the old taskset. The hard
tier is not saturated, and a training run against it would have somewhere to climb. That
was the whole purpose of the extension and it is the one claim these runs support.

### The seventh defect, and it is structural rather than fixable

**All 10 of bash's void rollouts are full-scan tasks** — `total-*`, `richest-owner`,
`isolated-total`, `owners-all-kinds`, `invoice-total-all-kind-owners`, `kind-max-*`,
`count-nakamura-invoice`. Every one carries `min_calls = 40`. Not one of the cheap tasks
failed on either arm.

That is not luck. bash makes one tool call per turn and re-sends the transcript each time,
so a 40-call task is a 40+ turn rollout with a transcript that grows every turn: 1.08M
relay-reported prompt tokens across 494 turns, against PTC's 209k across 167. A longer rollout with
slower per-turn responses is simply exposed to more transport faults, and 124 ProviderErrors
were retried away while 4 HarnessErrors were fatal — defect 6's class again, where the bash
arm delegates to the bundled runtime and a relay timeout arrives as a non-retryable error.

**This confounds the measurement it was supposed to produce.** On the tasks where a
program-over-catalog arm should win, the shell arm cannot reliably finish a rollout through
this relay — so "bash scores lower on full-scan tasks" and "bash cannot complete full-scan
rollouts here" are not separable with this endpoint, and more retries only hides the
difference further. Raising the budget again would be measuring the relay.

**Corrected 2026-10-08 — it is a rate limit, not tail latency.** The paragraph above
originally read this as the relay's tail latency failing a 40-turn rollout, and framed the
fix as buying a better provider. Reading the per-rollout `errors` arrays says otherwise:
across the 10 void bash rollouts the tally is **67 `ProviderError` 429s and 3
`HarnessError`s**, and the first void rollout carries exactly 7 errors — the whole
`--max-retries 7` budget — every one of them `upstream 429: rate_limit_exceeded`.

So the mechanism is throttling, and the exposure is still structural: bash issues 475 tool
calls across 494 turns against PTC's 138 and 167, so it meets a per-account request-rate
limit roughly three times as hard. `--max-concurrent 1` does not help, because this is
request rate over time rather than parallelism. 2d took zero 429s on the same budget at
n=14; n=29 simply outlasts it.

This is tunable with a flag that already exists, which the earlier framing wrongly
presented as a spend decision. **Run 3c re-runs at `--max-retries 20`.** Raising the budget
does not weaken the instrument: `compare.py:188` keeps a deterministic harness or sandbox
fault exhausting every retry and ending red, so only transient faults become survivable.

If 3c still voids, THEN the endpoint is the constraint and the original two options apply.

---

## Run 3c — clean on the 29-task set, and it contradicts A6's headline prediction

2026-10-08, 29 tasks, `--max-retries 20 --max-concurrent 1 --max-turns 80`. **Zero void
rollouts on either arm** — 28 `agent_completed` plus one `max_turns` on bash, 29
`agent_completed` on PTC. First admissible comparison on the extended taskset.

| | bash | ptc |
|---|---|---|
| score | **21/29 (0.7241)** | 20/29 (0.6897) |
| 95% CI | [0.552, 0.862] | [0.517, 0.862] |
| relay-reported prompt tokens | 2,245,429 | 241,561 |
| cost / solved (measured rates) | $0.0243 | **$0.0035** |
| tool calls / turns | 836 / 864 | 150 / 179 |
| shell-call share | 0.0132 | 0.0000 |

**The marginal is +3.4 pp to bash**, paired CI [−20.7, +27.6], 6 discordant pairs to bash and
5 to PTC, exact McNemar p=1.0000. Not separable, and A6 declined this number as the headline
in advance, which is just as well.

### Against the signed predictions

- **N1 — NOT met, and not separable.** Predicted the interaction at ≤ −25 pp; measured
  **−23.7 pp**, 95% CI **[−64.1, +15.2]** — direction correct, magnitude short by 1.3 pp,
  and the interval includes zero, so the tier asymmetry is a point estimate on this n and
  not a demonstrated effect either. The first interval this tool printed for it was
  `[−13.1, +64.1]`, which put the estimate OUTSIDE its own CI; the call site was passing
  `(full-scan, cheap)` positionally into a signature named `(low, high)` and reporting the
  interval on the reverse difference. Fixed and pinned by tests (see below). Either way the
  conclusion is the same — includes zero — but the printed number was wrong, which is worse
  than useless in a file like this one. Cheap tier: bash +18.2 pp (0.909 vs 0.727), CI
  [+0.0, +45.5], p=0.5000. Full-scan tier: bash **−5.6 pp** (0.611 vs 0.667), CI
  [−38.9, +27.8], p=1.0000. The interaction is real and points the way A6 said, but on this
  n it does not clear the bar I signed — and 18 full-scan tasks cannot separate a 5.6 pp gap.
- **N2 — MET.** bash wins the cheap tier at +18.2 pp. A typed-tool call read with the model's
  own attention beats paying program-authoring overhead when one call suffices.
- **N3 — HOLDS.** bash's full-scan shell share is **0.0140**, and 4 of 18 rollouts do any
  arithmetic at all. The prediction most worth being wrong about was right: bash retrieves
  and then guesses even where a shell is exactly what the task needs.
- **N4 — MET, better than predicted.** 0 void rollouts against a predicted ≤ 4. The retry
  budget was the whole constraint; the endpoint was never the problem.

### Two further tool defects found while adjudicating this run

Both in `ptc/paired.py`, both found by the numbers looking wrong rather than by a test:

1. **`power_pairs` took 115 seconds and left a redirected stdout at 0 bytes**, which read as
   a silent failure and sent me chasing a nonexistent bug through the shell. `crit` was
   recomputed inside the candidate-`n` loop as an `O(d^2)` scan. It depends only on `d`, and
   it is monotone in `k`, so it is now cached and binary-searched: 115s → 16s, identical
   answers on all seven reference cases.
2. **The interaction interval was computed on the reverse difference** — see N1 above. The
   tell was an estimate sitting outside its own CI, which a correct percentile bootstrap
   cannot do.

Neither was caught by the suite, because the suite tested the harness and not the reading of
its output — the same gap that produced the `paired.py` void-rollout defect a day earlier.
That is now three defects in the tools that adjudicate results, against six in the harness
itself. **The instrument has been the problem at least as often as the thing it measures.**

### The one budget caveat

One bash rollout stopped on `max_turns` rather than completing, and `compare.py` flags the
score comparison as invalid until the budget rises. It is the same class of issue as the
retries: bash spends turns re-retrieving because it has one call per turn, and it cost
**864 turns to PTC's 179** for the same 29 tasks. That is the mechanism N1 was about,
showing up as a resource limit rather than a score. Whether it changes the full-scan tier
needs a `--max-turns` above 80, which is a cost decision, not a flag default.

### What this changes

`docs/results-untrained.md` stands untouched — it reports run 2h on the 14-task set, which is
what it says. But on the extended taskset the untrained ordering is now **bash ahead on the
cheap tier and PTC ahead on the full-scan tier, with the marginal in bash's favour by 3.4 pp
and p=1.0000.** Anyone reading the 2h inversion as "PTC wins" should read this alongside it:
the effect is tier-dependent, and the aggregate is a wash.

---

## Run 3d — clean, and the tier pattern holds while the magnitude shrinks

2026-10-08, 29 tasks, `--max-turns 150 --max-retries 20 --max-concurrent 1`. **The cleanest
run in the project: zero voids, zero truncations, 29 `agent_completed` on both arms.**

| | bash | ptc |
|---|---|---|
| score | 23/29 (0.7931) | 23/29 (0.7931) |
| cost / solved (measured rates) | $0.0222 | **$0.0027** |
| relay-reported prompt tokens | 2,229,481 | 208,780 |
| tool calls / turns | 822 / 851 | 156 / 185 |
| shell-call share | 0.0304 | 0.0000 |

**Exact tie on score**, and 5 `HarnessError`s on bash were retried away to completion rather
than voiding anything — the 150-turn budget was sufficient for `longest-chain-start`, which
is what 3c's single truncation was about.

### Across three consecutive clean runs

| | 3b (void) | 3c | 3d |
|---|---|---|---|
| bash / ptc | incomplete | 21 / 20 | **23 / 23** |
| cheap tier delta | — | +18.2 pp | **+9.1 pp** |
| full-scan delta | — | −5.6 pp | **−5.6 pp** |
| interaction | — | −23.7 pp | **−14.6 pp**, CI [−49.5, +16.7] |
| bash full-scan shell share | — | 0.0140 | **0.0300** |
| voids | 10 | 0 | **0** |

**The full-scan delta is −5.6 pp in both clean runs — identical to the decimal.** With n=18
that is 12 against 13, one task apart, so the agreement is as likely to be the small integer
grid as a stable effect. It should not be read as replication at this n.

**N1 not met, on either clean run.** Predicted ≤ −25 pp; measured −23.7 then −14.6. The
direction has held three times and the magnitude has never approached the bar I signed. The
cheap tier's bash advantage halved between the two runs (+18.2 → +9.1) while full-scan's
barely moved, so even the consistency of the *gap* is driven by the tier that is noisier at
n=11.

### N3 holds, and its falsification test failed to fire

bash's full-scan shell share **rose** from 0.0140 to 0.0300, and 6 of 18 rollouts now do some
arithmetic against 4 of 18 in 3c. **Its full-scan score did not rise with it — 0.667, exactly
as in 3c.** A6 named this the prediction most worth being wrong about, on the ground that a
share rising *together with* the score would mean the mechanism is tool availability rather
than channel, and the framing should be retired. Availability increased, solve rate did not:
the mechanism is not availability. Retained.

### The honest summary after three runs

The cost result is the only one that has never wavered, but it is **two ratios, not one**, and
they are reported separately from here on because merging them is what produced the error
corrected below:

- **Token ratio**, relay-reported prompt tokens bash/ptc: **7.99x** (2h), **9.30x** (3c),
  **10.68x** (3d) — the published 8.0-10.7x, which reproduces exactly. Floor after correcting
  for the relay's token counter: **6.9-8.9x**.
- **Cost ratio**, dollars per *solved* task bash/ptc: **7.53x**, **7.01x**, **8.21x** at the
  relay's measured rates — **$0.0126-0.0243 against PTC's $0.0017-0.0035**. Honest floor
  **6.1x** (3c, worst assumption about the counter).

That is structural, it favours PTC under the pre-registered co-primary, and it would hold even
at an exact score tie — which run 3d is. **The defensible claim is the range with its floor,
6.1x-8.2x on cost per solved task, not a single multiple.**

**⚠ CORRECTED 2026-10-10 — this section published "PTC at $0.0010–0.0013 per solved task
against bash's $0.0071–0.0099, on 8.0-10.7x fewer billed prompt tokens".** Introduced in the
run-3d commit. Four faults, no instrument defect among them — these are reporting faults in
this file:

1. **`$0.0071` is not a per-solved figure.** It is run 3d's bash cost total divided by the
   **29 tasks attempted** (0.2067/29 = $0.00713). Per the 23 solved it is $0.00899. The
   co-primary is defined on *successful* tasks and PTC's companion range was purely
   per-solved, so the published interval spanned two different denominators.
2. **It omitted run 2h.** 2h's bash cost per solved task is **$0.0051**, below the floor the
   range published, on the run `docs/results-untrained.md` is built from. The correct
   per-solved range at the rates then in use is **$0.0051-$0.0099**.
3. **The rates were never measured.** All runs used `--price-in 0.09 --price-out 0.18`. The
   relay charges **$0.2186/M in** (three large-prompt calls with 2-3 token completions:
   0.2207, 0.2174, 0.2177) and **$0.670/M out** (OLS over six calls, completions 340-2,284).
   Any per-call component is under **$1.7e-5** and the same OLS puts it at $2e-6, so there is
   no material one — which matters in the counter-intuitive direction: bash bills 10.7x the
   prompt tokens on only 4.6x the calls, so a per-call fee would land relatively harder on
   **PTC** and shrink the gap, not widen it. The single recorded real charge in this file,
   run 1's **$0.16**, is 1.07x the measured-rate re-derivation ($0.1502) and 2.65x the
   assumed-rate one ($0.0603) — independent corroboration from nine days earlier.
4. **"Billed prompt tokens" was false.** `usage.prompt_tokens` from this relay equals
   `cl100k_base` over the raw message content *exactly* on short prompts, carries no
   chat-template overhead, returns the identical count for one prompt under two different
   model ids, and exceeds every standard tokenizer by 43-56% above ~3.8k tokens. It is
   computed relay-side. Call it relay-reported.

Fault 4 is why the cost ratio now carries a floor rather than a point value: the divergence
lands where bash's prompts live (38.7% of its tokens in calls above 3,800 against PTC's 1.9%),
so a size-dependent distortion does **not** cancel in a ratio of two arms at different prompt
sizes. At a divergence onset of 200 tokens it cancels exactly and the ratio returns to
as-reported, which is the proof that the threat is the asymmetry rather than the inflation.
The instrument now refuses to print a cost without naming its rate (`ptc/metrics.py`), and
`ptc/relay_audit.py` pins the endpoint's signature so a silent change becomes detectable.

Score-wise the project now has: a premise that failed to reproduce, an inverted ordering on
the original 14 tasks that did not survive extension to 29, and on the extended set a tier
interaction that points consistently one way and has never cleared significance or the signed
threshold. **The defensible finding is the cost structure, not the accuracy ordering.**


---

## The thirteenth defect — tool-call success was only ever measured on one arm

Found 2026-10-10 by the training lane while testing an unrelated guard, and derived here
from the traces rather than from the report that surfaced it.

`tool_success_rate` is `1.0 - tool_failures / tool_calls`, and `tool_failures` counts tool
results whose text starts with one of `FAILURE_PREFIXES` — `"rejected:"` or `"error:"`.
**Those are the strings `ptc/harness.py` emits.** The bash arm's tools are `bash`,
`ledger_get`, `ledger_ids` and `ledger_links_to`; they return JSON or shell output, so no
bash tool result can match the predicate. Read straight out of the trace nodes, across all
three admissible runs:

| run | arm | tool calls | results matching the predicate | rate as published |
|---|---|---|---|---|
| 2h | bash | 266 | **0** | **1.0000** |
| 2h | ptc | 66 | 29 | 0.5606 |
| 3c | bash | 836 | **0** | **1.0000** |
| 3c | ptc | 150 | 78 | 0.4800 |
| 3d | bash | 822 | **0** | **1.0000** |
| 3d | ptc | 156 | 74 | 0.5256 |

Zero in 1,924 bash tool calls, across three runs, on a predicate bash cannot satisfy.
**Secondary 3 as published therefore compares a measured rate against an unmeasurable one.**
bash's 1.000 is a floor artefact of the predicate, not a performance figure, and the
direction of the published comparison — bash ahead — is an artefact of the same shape as
defect 2: the instrument asserting its own soundness falsely.

**And bash's failures are not absent, only unmatched — which is the part that makes this a
measurement fault rather than a definitional one.** Grepping the same results for
failure-shaped text that the predicate misses:

- 2h: `bash: ledger_get: command not found` (1)
- 3c: `bash: ledger_ids: command not found`, plus bulk outputs carrying `Error or no result`
  for individual records (3)
- 3d: two Python `Traceback (most recent call last):` blocks, a JSON-wrapped
  `{"error": "No module named 'ledgers'"}`, plus two partial bulk outputs (5)

The JSON one is the sharpest illustration: `{"error": ...` misses `error:` by the two
characters `{"`. Counting only those, bash's rate is at most **0.9962 / 0.9964 / 0.9939** —
and that is still a floor, because it was found by searching for failure words in English
rather than by an error channel the rig can see.

**The defect is wider than one uninstrumented arm: the predicate is blind to an entire error
channel.** The training lane established that TRL wraps a tool exception as
`{"error": str(e)}` and then `str()`s it, so the text arriving at the predicate is
brace-first and cannot match `error:` — the same two characters as the `{"error": "No module
named 'ledgers'"}` above, from a different source. The consequence is not historical: a
**correct** PTC arm under the planned Path C would also print 1.000 if `run_program` ever
raised instead of returning a formatted string, because the raise would arrive wrapped. So
`FAILURE_PREFIXES` is not merely missing the bash arm's dialect, it is missing the dialect
that any exception-based tool failure speaks. A test pins this and goes red if TRL changes
the wrapping.

**What this does and does not reach.**

- **Secondary 3 is withdrawn as an arm comparison** on all three runs. PTC's own rate
  (0.4800-0.5606) is measured and stands; bash's is not measured at all.
- **H4 needs qualifying, and it was the project's best-powered hypothesis.** The benchmark
  lane had just assessed it as the strongest available test — per call, 7.8 pp half-width at
  n=29 against a 26.9 pp pre-registered target. That assessment assumed both arms were
  instrumented. The source paper's 65.2% vs 92.1% gap is untouched; **this project cannot
  measure its own version of it** until bash's failures are visible to the predicate.
- **The cost co-primary is NOT affected, by derivation rather than by assumption.** Cost is
  computed only from `Trace.usage` — `prompt_tokens`, `cached_input_tokens`,
  `completion_tokens` — in `summarize`'s pricing block. `tool_failures` has exactly two
  readers in the whole repo: `tool_success_rate` and the table row that prints it. Neither
  `ptc/paired.py` nor `ptc/audit.py` reads either field, so nothing in the primary, the
  cost co-primary, the stability co-primary or the tier split depends on it. Secondary 4,
  shell-call share, is computed from `SHELL_TOOLS` name matching on the *call* side and is
  also unaffected.
- **Score is unaffected.** A tool failure is data the model reads, not a scored event; the
  grader reads the final answer.

`ptc/metrics.py` now refuses to print a perfect rate quietly: any arm with at least
`MIN_CALLS_FOR_PERFECT_RATE` calls and zero detected failures raises a `*** NO TOOL FAILURE
WAS DETECTABLE` note naming the predicate, and `ptc/test_metrics.py` covers the channel
being absent rather than only the strings being intact. The fix for the measurement itself —
giving the bash arm a failure channel the predicate can see — is not done, and secondary 3
stays withdrawn until it is.
