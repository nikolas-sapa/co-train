# Step 2 — prove the loop runs on free hardware

One question: **does GRPO run on Kaggle T4, and is fp16 stable.** Five steps.
Not a learning run.

**Run on Kaggle T4 2026-09-30: `STEP 2 PASS`.** Result, caveats and stack in
`step2/results/`; re-checkable with no GPU via `verdict.py`. This line previously
read "nothing here has touched a GPU yet" and survived the commit that added the
result (`650a303` edited this file but not this sentence), so the repo asserted
both at once. What has been verified, and how, is below.

## Run order

```bash
python step2/gate_chat_template.py    # informational, ~20 s, no GPU
python step2/smoke.py                 # Kaggle only; writes step2_metrics.jsonl
python step2/verdict.py step2_metrics.jsonl   # re-check a saved run
```

Kaggle: accelerator `NvidiaTeslaT4` (= T4 x2).
**`pip install unsloth==2026.9.12 "trl==0.24.0" "transformers<5"`** — every pin
is load-bearing, see the next section. Copy
`step2/` to `/kaggle/working`, `cd` there, run. Output lands in
`/kaggle/working`, which persists; notebook scrollback does not, and the
20-30 min idle timeout can take the kernel before you read it.

## The gate, and what checking it against source changed

HANDOFF.md records: *"TRL raises at `grpo_trainer.py:1981-1982` if the chat
template is not prefix-preserving."* Read against TRL's source rather than
its docs, three things hold that the note does not say:

1. **The raise is guarded by `if self.tools`.** It lives inside the multi-turn
   tool-calling loop. A GRPO run with no tools never reaches it, so it cannot
   block Step 2 whatever the answer.
2. **Neither the check nor the tool loop exists in TRL ≤ 0.24.0.**
   `trl/chat_template_utils.py` is 404 at that tag and `self.tools` appears
   zero times in its `grpo_trainer.py`. Both land in 0.26.0.
3. **Unsloth pinned `trl>=0.18.2,!=0.19.0,<=0.24.0`.** So on the Step 2 stack
   the gate is not merely unfired — it is absent. **That pin has since moved:**
   unsloth 2026.10.3 (2026-10-08) declares `trl!=0.19.0,<=1.13.0`. The sentence
   above describes unsloth 2026.9.12, the version the run used — verified from
   its own PyPI metadata, not inferred. The recipe now pins unsloth and trl to
   the versions the artifact records, rather than relying on a ceiling that has
   already moved once.

**Qwen3-0.6B does fail the gate** where it exists. Qwen3 drops the
`<think></think>` block from an assistant turn once a later turn is appended,
so rendering message *N* changes retroactively. Measured here:

```
prefix-preserving False   (first divergence at token 9: <think> present in the
                           2-message render, gone from the 3-message one)
after TRL patch    True   (get_training_chat_template, 3834 chars)
```

TRL's own docstring for `get_training_chat_template` uses Qwen3-0.6B as its
worked example of exactly this, and ships the repair, applied at
`grpo_trainer.py:423-428` of v0.26.0 whenever `tools` is truthy.

### The repair matches `Qwen/Qwen3-0.6B`. The run loads `unsloth/Qwen3-0.6B`.

**This section previously concluded "the escape hatch is not needed on that
path." That conclusion was measured against a model this project does not
train, and it is wrong for the one it does.**

TRL's repair is not a transformation. `chat_template_utils.py:353-362` is, in
full, three branches:

```python
if is_chat_template_prefix_preserving(tokenizer):
    return None                                   # no patch NEEDED
if tokenizer.chat_template == qwen3_chat_template:
    return qwen3_training_chat_template            # the one repair it has
else:
    raise ValueError("...patching is not supported for this template.")
```

The middle branch is an **exact string equality against a vendored copy of
Qwen3's template**. Measured 2026-10-10, no GPU, from the live tokenizer
configs and trl v0.26.0's source:

| template | chars | sha1 (12) | `== qwen3_chat_template` |
|---|---:|---|---|
| trl 0.26 vendored `qwen3_chat_template` | 4168 | `b066ba71c1b5` | — |
| `Qwen/Qwen3-0.6B` | 4168 | `b066ba71c1b5` | **True** |
| `unsloth/Qwen3-0.6B` | 4905 | `2006cdc006d3` | **False** |

And TRL's own prefix predicate, applied verbatim to both, answers **False for
both** — so neither takes the early `return None`. Therefore:

- `Qwen/Qwen3-0.6B` → equality holds → repaired → `tools=` works.
- `unsloth/Qwen3-0.6B` → equality fails → **`raise ValueError`** inside
  `GRPOTrainer.__init__`, the moment `tools=` is non-empty.

`smoke.py` loads `unsloth/Qwen3-0.6B` (`MODEL`, line 31; the artifact's
`config` block records it too). So **co-training this stack under `tools=`
raises at trainer construction**, and the escape hatch — proxying the model
call, or supplying a repaired template by hand — IS needed.

**Why no check caught it:** `gate_chat_template.py` defaulted to
`Qwen/Qwen3-0.6B` while `smoke.py` loads `unsloth/Qwen3-0.6B`, and `KAGGLE.md`
cell 3 runs the gate with no argument. The gate measured the comfortable repo
and reported `after TRL patch True`. Same class as the twelve faults in
`docs/deviations.md`: a green check against the wrong target. The default is
now `unsloth/Qwen3-0.6B` and a test asserts the two files cannot drift apart
again.

**Second defect in the same lines, found while fixing the first:** the gate
read `fixed is None` as "TRL offers no patch" and reported FAIL. TRL returns
`None` to mean the opposite — *no patch is needed* — and signals "no patch
available" by **raising**, which the gate did not catch. So on the very repo it
now checks, the old code would have died with an unhandled `ValueError`
instead of reporting a verdict. Both paths are now handled and tested.

### What this leaves for Steps 5-6

The PTC harness *is* tool calling, so it lands squarely on the path Step 2
avoids, and on the Unsloth stack that path does not exist at all. Two routes,
both already implied by HANDOFF's "migrate to TRL/prime-rl when renting
proper hardware":

- **trl ≥ 0.26 without Unsloth** — gains the tool loop and the auto-repair,
  loses Unsloth's fp16-on-Turing work. Fine on rented Ampere, not on a T4.
- **Proxy the model call** — keeps Unsloth, owns the multi-turn loop.
- **Unsloth + trl ≥ 0.26** — newly admissible, and not on anyone's list when
  the two above were written: Unsloth's ceiling moved to `trl<=1.13.0` on
  2026-10-08, so keeping Unsloth and taking the tool loop is no longer a
  contradiction. **Unverified on hardware** — nothing says Unsloth's fp16-on-
  Turing patches still apply to a trl that far forward, and that is exactly
  the kind of claim this repo does not get to assert without a run.

Which entry point exists where, read from source at each tag rather than from
the docs (counts are occurrences in `trl/trainer/grpo_trainer.py`):

| | 0.24.0 | 0.25.0 | 0.26.0 |
|---|---|---|---|
| `rollout_func` (own the generation) | **0** | 9 | 11 |
| `self.tools` (native tool loop) | **0** | **0** | 17 |
| `tool_mask` (tool tokens out of the loss) | **0** | **0** | 19 |
| `get_training_chat_template` (the repair) | **0** | **0** | 2 |
| `environment_factory` | **0** | **0** | **0** (lands later; present in 1.13.0) |

0.24's `GRPOTrainer.__init__` takes ten parameters and none of them is a seam
for externally-driven rollouts. **So the chat-template gate is not what kills a
co-training run on the Step 2 stack — there is no entry point for the harness
to attach to in the first place, and the gate sits downstream of one.** The
minimum for bring-your-own-rollouts is **0.25.0**; the minimum for a native
tool loop with loss masking and the auto-repair is **0.26.0**.

Deciding this is Step 5's, not Step 2's. Recorded so it is not discovered late.

## The dependency trap, found before spending a Kaggle slot

`pip install unsloth` on Kaggle resolved `trl==0.24.0` **on 2026-09-26, under
unsloth 2026.9.12, whose ceiling was `trl<=0.24.0`** — so `gc24.py` was
validating against the right version. That is no longer self-enforcing: unsloth
2026.10.3 raised the ceiling to `trl<=1.13.0`, and the recipe pins the version
explicitly instead. What pip resolves inside the Kaggle image is **UNKNOWN**
from here and is not checkable from a dev machine; see `KAGGLE.md` cell 2. It also resolves
**`transformers==5.5.0`**, because TRL 0.24 declares `transformers>=4.56.1`
with no upper bound. That pair does not work:

```
>>> from trl import GRPOTrainer
ModuleNotFoundError: No module named 'mergekit'
```

transformers 5 changed `_is_package_available` to return `tuple[bool, str]`.
TRL 0.24 calls it without `return_version=True` and stores the raw result, so
every optional-dependency flag becomes `(False, None)` — a non-empty tuple,
therefore truthy. Every `if is_X_available():` guard in TRL then fires against
a package that is not installed:

```python
_mergekit_available = _is_package_available("mergekit")   # (False, None)
if is_mergekit_available():                               # truthy -> passes
    from mergekit.config import MergeConfiguration        # ModuleNotFoundError
```

Measured: **11 of 12 flags inverted** on trl 0.24.0 + transformers 5.5.0, zero
on trl 0.24.0 + transformers 4.57.6. The error names neither transformers nor
the real cause, and it lands *after* the Kaggle queue and the model download.

**Install `transformers<5`.** Verified: 4.57.6 resolves with trl 0.24.0 intact,
un-poisons every flag, imports `GRPOTrainer`, and accepts every `GRPOConfig`
kwarg `smoke.py` passes. `gate_chat_template.py` now checks this and exits 1
with the fix, so the run cannot start into it.

## Why a continuous reward, not a task

GRPO's advantage is the within-group deviation from the group mean. A reward
returning the same value for all `num_generations` samples gives zero
advantage, zero gradient, and a run that completes cleanly having exercised
nothing — the false-green shape Step 1 kept finding. `word_count_reward` is
continuous in output length and cannot collapse; `verdict.py` checks that it
did not anyway (`reward_std > 0` on at least one step).

The task is a length proxy, deliberately. Step 4 brings a real reward.

## Pass criteria

`verdict.py`, applied to the logged metrics. All must hold:

| # | Criterion | Why |
|---|---|---|
| 1 | ≥ 5 logged training steps | a short or empty run must fail, not pass vacuously |
| 2 | `grad_norm` finite on every step **after step 0** | fp16 overflow surfaces as inf/nan |
| 3 | `grad_norm > 0` on ≥ 1 step | all-zero means every gradient underflowed |
| 4 | `reward_std > 0` on ≥ 1 step | otherwise no gradient existed to test |
| 5 | `loss` finite where logged | — |
| 6 | `grad_norm`, `completions/mean_length`, `reward_std` present on every step | the signals this stack can actually emit |
| 7 | `entropy > 0.01` where logged | Garg's collapse signature — **dormant here**, see below |

Criterion 1 is the load-bearing one. Without it every other check is
vacuously true on an empty log and a run that trained zero steps reports a
pass.

**Criterion 2 exempts step 0 deliberately.** torch's `GradScaler` starts at
`init_scale=65536` and halves on overflow, so the first optimizer step
legitimately overflows and transformers logs `grad_norm` as `inf`. Failing on
it would red every correct fp16 run. The exemption is one step and one key —
`observations()` reports the excused value rather than swallowing it, because
a silently-absorbed `inf` is indistinguishable from a diverging first step.

### Entropy is not measurable on this stack

`REQUIRED_KEYS` does **not** include `entropy`, and that absence is the
correction, not an oversight. TRL logs entropy — but only from a closure
inside `_compute_loss`, which Unsloth replaces wholesale, and Unsloth's
replacement hardcodes `compute_entropy = False`. Requiring it made `verdict()`
report `STEP 2 FAIL` on every healthy run: a fail-closed defect inside the
file written to prevent fail-closed defects.

Consequence, stated rather than papered over: **Garg's clearest collapse
signature — entropy going to zero at lr 1e-4 — cannot be observed here.** What
remains is `grad_norm`, `reward_std` and the KL spread. `observations()` prints
this on every run so the gap is declared rather than silent. The check itself
is kept, because raw TRL does log entropy and Step 6 may well drop Unsloth for
rented Ampere.

### Why `beta = 0.04`

`research/08-gap-closure.md` §7 found a public Kaggle 2×T4 run at almost
exactly this config — fp16, no vLLM, dense Qwen3-0.6B — that completed 314
steps with zero non-finite values. "Does it run, is fp16 stable" is therefore
already answered affirmatively by someone else's committed log, and at
`beta=0` this run would only reproduce it. That run published **no KL curve**,
which is precisely the standing unknown in `HANDOFF.md`.

`beta > 0` costs zero extra weights: for a PEFT model TRL sets
`ref_model=None` and uses the adapter-disable path, so there is no second copy
of the model, only an extra forward pass.

The trap it opens is handled. Unsloth logs `kl` **unconditionally**, and at
`beta=0` the per-token KL is `zeros_like(...)` — so a *finiteness* check would
pass a run that measured nothing at all, and the JSONL would read as a KL
curve to whoever opened it next. `observations()` checks **flatness** instead
and says so explicitly when every step reports the same value.

## Settled constraints, pinned as tests

HANDOFF settles fp16, on-policy, lr, LoRA rank, `mask_truncated_completions`,
`NCCL_CUMEM_ENABLE`, `use_vllm=False`. `smoke.py` cannot run on darwin/arm64,
so drift in any of them would not surface until a Kaggle session had been
spent — and lr or `num_iterations` drift produces a *plausible-looking*
collapse rather than an error, which is worse than a crash. The tests read
`smoke.py`'s AST and fail on change.

`NCCL_CUMEM_ENABLE=0` is checked for *ordering*, not presence: set after
`import torch` it does nothing, silently.

## Verification status — read this before trusting anything here

**Verified by execution on this machine (darwin/arm64, no GPU):**
- the prefix-preserving predicate, both directions, against real jinja and the
  real Qwen3 tokenizer — including its TypeError fallback, which is dead code
  for Qwen3 and is therefore exercised by two purpose-built templates with
  opposite answers, so a fallback returning a constant cannot pass
- Qwen3-0.6B fails the gate; TRL's patch repairs it
- the reward's spread, bounds and monotonicity
- every pass criterion, each failure mode separately
- every `GRPOConfig` kwarg exists on TRL 0.24 (`max_prompt_length` is the live
  example: present in 0.24, removed by 0.29)
- `enable_thinking=False` pre-closes the think block, and its absence changes
  the prompt — so the flag is doing work, not decorating

**Verified on Kaggle T4, 2026-09-30: `STEP 2 PASS`.** The loop runs and fp16 is
stable — `grad_norm` finite and positive across all five steps, `reward_std` > 0
throughout, `kl` rising across three orders of magnitude. Result, caveats and
stack in `step2/results/`. The GradScaler warm-up exemption went unused: there
was no step-0 `inf`, so that branch is still untested against a real overflow.

`pytest step2/ -q` → 73 passed. Root `pytest -q` → Step 1's 51, untouched.

## Mutation testing

59 mutants, zero survivors — 22 on `verdict.py`, 23 on `gate_chat_template.py`,
14 on `smoke.py`'s config, all re-run against the final code state rather than
carried over from the round that first killed them. Harness:
`step2/mutate.py` — fresh copy per mutation, `PYTHONDONTWRITEBYTECODE=1`,
both mandatory. Committed, unlike Step 1's, which sits under the ignored
`.superpowers/sdd/` and so cannot be re-run from a clone.

Six rounds, each finding something the last missed — the same pattern Step 1
reported. What survived longest, in order:

1. **A grep that matched its own docstring.** `assert "enable_thinking=False"
   in src` stayed green after the flag was deleted from the call, because the
   comment explaining the flag contains the string. Now reads the AST.
2. **A fallback tested only against its `True` answer.** `return True` in the
   `except` branch passed. Now both answers go through that path.
3. **`except TypeError` widened to `except Exception`.** Swallows a genuine
   template bug and retries it into a confident verdict. Pinned.
4. **A metric the stack never emits, required as a pass criterion.** Found by
   the research session's audit (`docs/step2-audit.md`), **not** by mutation —
   every `verdict()` test fed synthetic log dicts carrying the assumption under
   test, so mutating the logic could never falsify the premise. `GRPOConfig`
   kwargs were validated against vendored source; the metric contract was not.
   Now generated from library source by `gen_metric_contract.py` and asserted
   in `test_step2.py`, and the fixture no longer supplies `entropy`.
5. **A preflight that reported without gating.** The `transformers<5` check
   printed its diagnosis and the run continued — nothing asserted it *blocked*.
   Same shape as the dormant guards Step 1 kept finding, caught by mutating
   `if poisoned:` to `if False:`.
6. **`grad_norm` used as both the step marker and a required key** — deleting
   it shrank the step count instead of reporting a missing signal. The marker
   is now `loss`, which is not one of the required keys.

## Known holes

- **`gc24.py` is a vendored snapshot, and this hole has now FIRED.** The stated
  risk was: "if Unsloth lifts its TRL ceiling, the kwarg test validates against
  a version no longer installed and still passes." Unsloth lifted it on
  2026-10-08 (`trl<=0.24.0` → `trl<=1.13.0`), so an unpinned install is now
  free to take TRL as far as 1.13.0, where `max_prompt_length` is gone — what
  Kaggle's resolver actually picks is UNKNOWN from here — and
  `test_every_grpo_config_kwarg_exists_in_trl_024` stayed green throughout
  because it reads the snapshot. Closed two ways: the recipe pins the versions
  the artifact records, and `gate_chat_template.py` now diffs smoke.py's kwargs
  against the **installed** `GRPOConfig` via `dataclasses.fields`. Only the
  second is robust — a pin predicts the resolution, the preflight observes it.
- **The `transformers<5` pin is a ceiling, not a fix.** TRL's unbounded
  `transformers>=4.56.1` is still there; a future TRL that handles the tuple
  return will want the pin lifted, and nothing here notices that.
- **`poisoned_optional_flags()` only catches the tuple shape.** A different
  transformers change that breaks TRL some other way passes it silently.
- **The reward measures length, not competence.** It cannot detect a model
  that emits 20 tokens of noise. Correct for a stability probe, useless as a
  task signal.
- **`entropy > 0.01` is a floor, not a trend.** A run whose entropy is falling
  fast but has not yet crossed it passes. Five steps is too few to fit a slope.
- **Criteria 2-7 are all-or-any over logged steps.** A run that is healthy for
  four steps and degenerate on the fifth passes criteria 3 and 4, which ask
  only for one good step.
- **`GRPOTrainer`'s kwargs are not covered by the kwarg test**, only
  `GRPOConfig`'s — covering both would mean vendoring the 1843-line trainer for
  a six-name surface. Verified by hand against v0.24.0 `grpo_trainer.py:216-228`
  on 2026-09-25; it will not catch a later rename the way the config test would.
- **T4 x2 is asserted, not exercised.** `smoke.py` asserts `sm_<8.0` but runs
  single-process. Multi-GPU NCCL sync — the reason `NCCL_CUMEM_ENABLE` is set
  — is untested until vLLM lands in Step 6.
