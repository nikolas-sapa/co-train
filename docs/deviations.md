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

**Not fixed here.** The fix is a decision, not a patch: parse MCP text in `_bridge` so
a catalog function returns Python data (restoring parity, since bash's parser is the
model's own reading), or add a parse primitive to the catalog, or declare the asymmetry
and stop comparing scores. Each costs another paid run.
