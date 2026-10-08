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
  --max-retries 20 --price-in 0.09 --price-out 0.18 --output-dir ~/scratch/<run>
```

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

**Twelve distinct faults: nine in the harness, three in the adjudication tools.** Written
down because three totals were in circulation and none had been derived. The vault index
says "six", which was correct as of run 2h and stopped being correct at run 3b. An OSF
abstract drafted on 2026-10-07 asserted nine with a "six harness, three tools" split, which
sums to nine and describes the wrong nine. A number in a published abstract has to be
derived, not remembered.

**Counting convention, stated so the total reproduces:** one row per fault that made a run
inadmissible, however it was numbered in the prose below. This file numbers seven of them
(1-7, of which "Defect 5" and "defect 6" appear literally, and 7 is titled "the seventh
defect"). `Deviation 02a` contributes two more that are unnumbered — knock-ons introduced by
defect 4's fix — which is why the numbered total and the true total differ by exactly two.

### Harness — nine

| fault | file's label | found by | run |
|---|---|---|---|
| turn budget of 8 never reached the PTC harness, so the cap bound 11 of 14 PTC rollouts while bash used up to 80 | 1, in `Deviation 01` | run 1's own turn counts | 1 |
| the rig reported that binding cap as `TRUNCATED (budget) 0` — the instrument asserted its own soundness falsely | 2, in `Deviation 01` | the trace contradicting the table | 1 |
| PTC's system prompt advertised bare tool names at a keyword-only bridge; 34 of 54 tool failures were this one mismatch | 3, in `Deviation 01` | tool-failure breakdown | 1 |
| PTC posted `stream: False` into a relay whose gateway timeout applies only to non-streaming requests — 504 on every attempt, so a larger retry budget changed nothing | 4, `Deviation 02` | measuring the endpoint directly | 2d |
| the SSE parser indexed `choices[0]` on the final usage chunk, which carries `choices: []` — `KeyError` on 2 PTC rollouts, surfacing as a task failure | unnumbered, `Deviation 02a` | the fix's own side effect | 2e |
| the request omitted `stream_options.include_usage`, so PTC's cost per solved task printed as unknown while bash's did not — a co-primary silently lost on one arm only | unnumbered, `Deviation 02a` | the empty column | 2e |
| the catalog was not typed and the sandbox denied every parser: same three tools both arms, but bash's action space was a strict superset | "Defect 5" | reading what each arm actually received | 2f |
| the arms name the same transport fault differently, so retryability was decided by which arm's code owned the socket | "defect 6" | a relay timeout fatal on one arm and retried on the other | 2g |
| full-scan rollouts die on a per-account request-rate limit, confounding the tier comparison it was meant to produce | "the seventh defect" | 10 of 10 void rollouts being the 40-call tasks | 3b |

### Adjudication tools — three

| fault | found by |
|---|---|
| `paired.py` intersected arm task names and only errored on an empty overlap, so a partial run reported `n=12` on a 29-task taskset | pre-flight before reading a live run |
| `paired.py` scored off `rewards` alone, so an errored rollout summed to 0.0 and was indistinguishable from a wrong answer — ten crashes would have read as ten failures | reading 3b's own output |
| the interaction interval was computed on the reverse difference; an estimate sat outside its own CI | the number looking impossible |

**Five of the nine harness faults penalised the PTC arm, one penalised bash (defect 6), two
were symmetric (the two knock-ons), and one — the rate limit — is symmetric in principle but
falls roughly three times harder on bash per unit of work, because bash makes one request per
turn.** All twelve were invisible to a green test suite.

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
zero 429s, zero truncations, billed tokens present on both arms. Every defect found
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
  the server return JSON changed what BOTH arms read: bash's billed prompt tokens rose
  553925 -> 694679 (+25%) and its score fell 10/14 -> 7/14. So 2f and 2g are not
  comparable on the bash arm either. Only 2h onward, with the fixture fixed, forms a
  comparable series.

---

## Run 2h — clean, admissible, and the premise does not survive it

2026-10-03, same config as 2f and 2g, with defect 6 fixed. Traces
`~/scratch/ptc-real-run2h/`. All 28 rollouts `agent_completed`, zero errors, zero 504s,
zero 429s, zero truncations, billed tokens on both arms. **The first run in this project's
history that is both mechanically clean and free of a known arm asymmetry.**

bash 12/14, PTC **14/14**. Paired delta **−14.3 pp** (CI [−35.7, +0.0], exact McNemar
p=0.5000, 2 discordant pairs both PTC's, 12 tied). PTC is 8.5x cheaper per solved task on
8x fewer billed prompt tokens, 4x fewer tool calls and 3.5x fewer turns.

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
| billed prompt tokens | 1,079,666 | 209,318 |
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
billed prompt tokens across 494 turns, against PTC's 209k across 167. A longer rollout with
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
| billed prompt tokens | 2,245,429 | 241,561 |
| cost / solved | $0.0099 | **$0.0013** |
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
| cost / solved | $0.0090 | **$0.0010** |
| billed prompt tokens | 2,229,481 | 208,780 |
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

The cost result is the only one that has never wavered: PTC at **$0.0010–0.0013 per solved
task** against bash's $0.0071–0.0099, on 8-10x fewer billed prompt tokens, because bash
re-sends its whole transcript once per turn. That is structural, it favours PTC under the
pre-registered co-primary, and it would hold even at an exact score tie — which run 3d is.

Score-wise the project now has: a premise that failed to reproduce, an inverted ordering on
the original 14 tasks that did not survive extension to 29, and on the extended set a tier
interaction that points consistently one way and has never cleared significance or the signed
threshold. **The defensible finding is the cost structure, not the accuracy ordering.**
