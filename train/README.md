# `train/` — the dead-group probe, and a pipeline that will not run yet

Two deliverables at deliberately different maturity levels, because
`docs/spec-cotrain.md` authorises exactly one of them.

| | status |
|---|---|
| **the dead-group probe** (§270-298) | finished and runnable. Needs no working benchmark, aborts in 5-20 steps |
| **the GRPO pipeline** (§156-240) | code, with its guards live and its gate **shut**. `preflight()` raises today |

The spec is explicit that the pipeline must not be built first (§328-342): a
mis-built pipeline announces itself as *"no training effect"*, and a benchmark
that cannot show a training effect even when the pipeline is correct produces the
same output. Broken and working become indistinguishable. So the pipeline lands
as code whose guards are tested and whose precondition check fails loudly, and
nothing here launches a training run.

## Files

| file | what |
|---|---|
| `guards.py` | the version floor, the spec's three invariants, the §344 gate. Pure stdlib |
| `dead_group_probe.py` | the derivation, the reward, the live abort, the probe's `main()` |
| `verdict.py` | no-GPU PASS/ABORT over a metrics JSONL. Both abort criteria |
| `grpo_ptc.py` | the gated pipeline: config, environment, `preflight()` |
| `test_train.py` | 111 offline tests. No GPU, no network, no model download |
| `mutate.py` | 52 mutants that break each guard, and the record that each one dies |
| `sql_capture.py` | opt-in incremental trusted SQL/PTC execution, immutable evidence, final-only scoring |
| `test_sql_capture.py` | 276 offline acceptance cases, including bounded extraction; independent guard controls verified |

## Incremental SQL/PTC capture

`start_capture(task, ids=..., allow_execution=True)` creates a trusted host
session with the unchanged canonical SQL/PTC prompt and a fresh eight-submission
budget. The opt-in must be literal `True`. Each `step` returns the actual existing
environment observation, allowing the next program to depend on it.

`finish(final_answer)` scores only final/gold SQL, without replaying actions.
`abort()` seals without a final or score. Both reject subsequent use.
Unexpected executor/scorer errors and binding/size failures invalidate the
session rather than returning partial success. Evidence separates dispatched
`steps` from budget `refusals`; a dispatched rejected program is still a step.
Final SQL is not an action. Invalid gold preserves `ExResult.valid=False`, not
a usable zero.

Example for an existing compatible interpreter, using only the committed fixture:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from bench.fixture import materialize
from bench.loader import load_bird
from train.sql_capture import (
    start_capture, encode_capture, decode_capture, rescore_capture,
)
from train.sql_episodes import EpisodeIds

with TemporaryDirectory(prefix="cotrain-capture-example-") as directory:
    task = load_bird(materialize(Path(directory) / "corpus"))[0]
    ids = EpisodeIds(
        corpus_id="committed-bird-fixture", split_id="engineering-only",
        run_id="local-example", episode_id=task.name,
        policy_id="trusted-host-example", policy_revision="fixture-v1",
    )
    session = start_capture(task, ids=ids, allow_execution=True)  # explicit consent
    prompt = session.prompt  # canonical model-visible prompt, no gold or capture metadata
    observation = session.step(
        "print(execute_sql(query='SELECT COUNT(*) AS n FROM school')[0]['n'])"
    )
    count = int(observation.strip())
    session.step(
        f"print(execute_sql(query='SELECT name FROM school LIMIT {count}'))"
    )
    # Known fixture answer supplied by the host, not a generated model answer.
    capture = session.finish("SELECT name FROM school WHERE charter = 1")
    restored = decode_capture(encode_capture(capture))  # data only
    assert rescore_capture(restored, task, ids=ids) == capture.result
```

Strict JSON evidence uses a distinct `sql_execution_capture` v1 envelope and an
8 MiB bound. Decode executes nothing; rescore executes protected final/gold SQL
only. Each later step/scoring rechecks caller IDs, task metadata, stable DB
bytes/no sidecars, canonical prompt, runtime/settings and selected source bytes,
including capture/environment/budget owners. Source edits can intentionally make
old captures unrescorable. Caller IDs/hashes are not authentication, source
bindings are not in-memory attestation, and stable snapshots do not prevent
malicious concurrent ABA writes. The restricted PTC runtime is not an OS sandbox.

Capture adds a conservative extraction-work admission limit before every call
to the unchanged shared SQL extractor: UTF-8 byte length plus the sum of raw
semicolon byte-prefix lengths must be at most 64 MiB per invocation.
Counting includes quotes/comments, discarded prose/fences and text after an
early complete statement, so some cheap-to-extract answers can reject.
Rejection is `ValueError`; failed finish invalidates its session. This limit is
separate from the 8 MiB format cap, not an overall CPU/memory deadline, and does
not alter global scoring/extraction semantics for admitted answers.

This API is not exported through native tool discovery. Existing scripted v1
recording remains unchanged. No provider traces, exact tokens, model-authorship
evidence, learning, skill promotion, training, or production-readiness claim.

Initial validation had 252 missing-API RED failures, then 252 focused passes.
The exact original combined scope independently passed 571 checks; the earlier
570 used 3 reward-query rather than 4 learning-lab cases, not a lost test.
Extraction repair had 17 behavioral RED failures, then 24 focused passes.
Current capture plus scripted/bridge/execution/learning-lab scope passed
595 checks (149.43s), no skips, with zero offline audit violations.
A real-code fresh-child attack rejected normally within a 10-second deadline;
independent bypasses of both extraction guards caused sentry assertion failures.
Original DB/budget/replay/sealed controls also failed as intended.
General/security reviews found no issues; fresh Python static re-review closed
the extraction P2. The final independent default suite completed **2,222 passed,
1 failed, 1 skipped, 2 deselected in 428.41s**, exit 1, all 2,224 selected tests
across 38 modules executed. All 276 capture and 319 exact legacy cases passed.
Optional torch was absent; two tokenizer controls were excluded by configuration.
External-network/cache/tokenizer audits were zero, with five permitted loopback
events. The unresolved existing isolated bench baseline failure copies no train
code. Startup-fixture investigation ended with all candidate edits reverted and
legacy tests/production unchanged. Capture is targeted-verified, not fully
offline accepted; skill generation/promotion remains unimplemented. See the
[test-first spec](../spec/sql-execution-capture.md) for exact scope and limits.

## Run order

```bash
# 1. adjudication, invariants and derivations — laptop, no GPU
.venv-ptc/bin/python -m pytest train -q
.venv-ptc/bin/python train/mutate.py               # 52 mutants, 0 survivors

# 2. the probe's config and expectations, without spending anything
.venv-ptc/bin/python train/dead_group_probe.py \
    --prompts PROMPTS.jsonl --taskset-id WHAT_THOSE_PROMPTS_ARE --dry-run

# 3. the probe itself — free Kaggle T4, accelerator NvidiaTeslaT4
pip install "unsloth>=2026.10.3" "trl==1.13.0" "transformers<5"
python train/dead_group_probe.py \
    --prompts PROMPTS.jsonl --taskset-id WHAT_THOSE_PROMPTS_ARE \
    --steps 5 --out probe_metrics.jsonl

# 4. re-check the saved run with no GPU
python train/verdict.py probe_metrics.jsonl           # the probe: any-step ceiling
python train/verdict.py run_metrics.jsonl --run       # a run: sustained A, plus B
```

`--steps 5` on the first launch, not 20. Five steps is the minimum that
`verdict.py` will adjudicate, it answers the probe's question, and it measures
the one number the whole feasibility argument rests on and nobody has taken —
see *Cost* below.

Download `probe_metrics.jsonl` **immediately**. Kaggle's "Restart session"
discards the pip install *and* wipes `/kaggle/working`; that is how Step 2's
first-party metrics file was lost (`step2/KAGGLE.md`).

## What the probe decides

> Does a binary reward produce usable groups against a 0.6B policy?

Under a 0/1 reward a group yields zero advantage whenever all `G` rollouts
agree, which is a Bernoulli coincidence: `p**G + (1-p)**G`. At G=4 and the only
measured solve rate available (23/29, run 3d) that is **0.397**, and TRL already
logs the realised value as `frac_reward_zero_std`. Above **0.60 on any step** the
probe stops: most of the batch yields no gradient, and no taskset fixes a reward
that cannot separate.

The expectation is a loan, not a measurement. 23/29 is `deepseek-v4-flash`'s, and
the policy that has to realise it is Qwen3-0.6B. Both tails degenerate — at G=8,
p=0.1 gives 43% dead groups against 15.7% at p=0.79 — so a *weak* policy is
worse than a strong one, and Qwen3-0.6B is the weak case. Restated as an
interval, the probe is a test of whether the realised solve rate falls outside
**(0.120, 0.880)**, which is also where the spec's exclusion of G=2 comes from:
0.793 sits outside G=2's narrower band.

**A probe result is not quotable without its taskset.** `--taskset-id` is
mandatory, it is written into the metrics header, and `verdict.py` refuses a file
that lacks it. The realised fraction is a property of (policy, taskset, G)
jointly; this repo has already shipped a real number attached to the wrong
denominator.

## Cost

**$0.** Free Kaggle T4, the same shape as the Step 2 smoke run, which fits one
card at 12.59 GB peak.

**Wall-clock: unknown, and that is itself one of the things the probe measures.**
Install is 15-20 minutes (`step2/KAGGLE.md`). Per-step time is the spec's open
question §322: the only measured generation figure is Step 2's 3.2 tokens/sec
whole-loop at `use_vllm=False`, where one GRPO step at this cap would take over
an hour and free hardware is out. With vLLM it should be minutes. Nobody has
taken the number. So run five steps, read the step time off the log, and decide
about twenty from data rather than from this paragraph.

## What is blocked, and on what

The pipeline waits on spec §344: **a taskset whose tasks sit near a 0.6B model's
frontier**. `ledger` fails this on two counts — the cheap tier's shape count is a
record-schema ceiling, and run 3d scored an exact 23/23 tie — so no value of n or
G rescues it.

`guards.frontier_taskset_status()` is that requirement as a check. It wants
`bench/frontier/manifest.json`:

```json
{
  "policy": "unsloth/Qwen3-0.6B",
  "pre_registration_amendment": "A8",
  "n_tasks": 198,
  "solve_rate_min": 0.2,
  "solve_rate_max": 0.8
}
```

and it refuses, naming each fault: a missing key, a band end at 0 or 1, a band
end whose own zero-advantage fraction exceeds the abort ceiling, a policy field
that does not say which model the rates were measured on, or an amendment id
with no `signed` heading in `docs/pre-registration.md`. **That path and schema
are this lane's declared contract and need reconciling with whoever builds the
taskset.** The gate fails closed either way.

The probe is **not** gated on any of this. It measures the reward's geometry, not
the model's competence.

## Red before green

A green test proves nothing until it has been seen red, so `mutate.py` breaks
each guard in a fresh copy of the tree and records which test dies:

```
baseline: 111 passed
52 mutants, survivors: none
```

Two mutants survived the first pass, and both were real:

- **`gate: missing manifest keys ignored`** — the gate still refused a
  key-less manifest, via its *other* checks, so nothing asserted that the
  operator is told *which* key to add. Fixed by
  `test_every_required_manifest_key_is_named_when_absent`.
- **`A: never-logged metric not reported`** — `criterion_a_any_step` carried an
  aggregate "never logged" line after a loop that already failed per step, so no
  input could reach it. Deleted. `criterion_a_sustained` keeps its equivalent,
  because there the loop alone returns clean on an absent metric, and the mutant
  aimed at that one dies.

## Conventions

Numbers are derived, never typed in: the spec's published percentages appear only
as a derivation's *expected output*, so a changed derivation fails rather than
agreeing with itself (the `tests/test_defect_ledger.py` pattern). Invariant
values that live in another file — `PTCHarnessConfig.max_turns`,
`ptc.metrics.FAILURE_PREFIXES`, `MIN_CALLS_FOR_PERFECT_RATE`, `ptc.harness.TOOLS`
— are parsed out of that file rather than copied, so the trained arm cannot
quietly diverge from the eval arm.

Guards `raise` rather than `assert`, although the spec writes them as one-line
asserts: `python -O` deletes `assert` statements, and a guard an interpreter flag
can remove is not a guard. `InvariantViolation` subclasses `AssertionError`, so
the spec's semantics survive.

Design notes, the §240-vs-§282 discrepancy and the open decisions are in
`docs/train-notes.md`.
