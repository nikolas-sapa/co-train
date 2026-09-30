# HANDOFF — Step 2

**Read `HANDOFF.md` first for the project, then `step2/README.md` for the detail.**
Status 2026-09-30: **DONE. `STEP 2 PASS` — fp16 GRPO is stable on Kaggle T4.**
Result and full analysis in `step2/results/`.

---

## The answer

Five steps, Qwen3-0.6B, fp16, LoRA r=32, `beta=0.04`, `use_vllm=False`, 298 s.

| Step | `grad_norm` | `reward_std` | `kl` |
|---:|---:|---:|---:|
| 1 | 1.837 | 0.0707 | 1.34e-05 |
| 2 | 2.433 | 0.2248 | 2.16e-05 |
| 3 | 2.011 | 0.1581 | 2.61e-03 |
| 4 | 2.063 | 0.0354 | 1.33e-03 |
| 5 | 1.716 | 0.1132 | 2.49e-02 |

`grad_norm` finite and positive throughout — fp16 neither overflowed nor
underflowed. `reward_std` > 0 every step, so a real gradient existed and the
pass is not vacuous. `kl` rises across three orders of magnitude: **the curve
nobody has published**, and the reason `beta=0.04` was chosen over 0.

**Consequence: the T4 path works, so rented Ampere is not required for Step 3.**
`08` had shown prime-rl cannot train on a T4 at all, so the two paths were
disjoint; this keeps the free one open.

Re-check with no GPU: `python step2/verdict.py step2/results/step2_metrics.jsonl`

Caveats, all in `step2/results/README.md`: not a learning run, reward hacking
visible by step 4 (the reward *is* length), entropy unobservable on this stack,
single-GPU, five steps is not a trend. And the committed JSONL is
**reconstructed from notebook stdout** — Kaggle wiped `/kaggle/working` before
it could be downloaded.

---

## The one thing to do next

**Step 3 — the verifier.** It was correctly deferred until fp16 was answered;
it now is. Read `HANDOFF.md`'s Step 3 entry and `research/08-gap-closure.md` §4c
before starting: BenchJack shipped and is a *repository auditor*, not an
adversarial rollout, so the runtime half needs `trustworthy-env`.

Note the other session moved further while this ran — `ptc/` now holds a
restricted runtime and a comparison rig, and `docs/spike-verifiers.md` argues
the PTC arm should come before the verifier. Reconcile the two orderings before
committing to either.


---

## What Step 2 settled

### The TRL trainability gate: resolved, and HANDOFF was wrong three ways

HANDOFF recorded *"TRL raises at `grpo_trainer.py:1981-1982` if the chat template
is not prefix-preserving."* Against source:

1. The raise is guarded by `if self.tools` — it is inside the multi-turn tool
   loop, so a no-tools GRPO run never reaches it.
2. It does not exist in TRL ≤ 0.24.0 at all: `trl/chat_template_utils.py` is 404
   at that tag and `self.tools` appears zero times in its `grpo_trainer.py`.
3. **Unsloth pins `trl<=0.24.0`**, so on the Step 2 stack the gate is *absent*,
   not merely unfired.

Qwen3-0.6B **does** fail the check where it exists — it drops `<think></think>`
from history, so message N re-renders once N+1 appears (divergence at token 9) —
but TRL auto-repairs it via `get_training_chat_template`, verified False→True.
**The proxy escape hatch is not needed.** HANDOFF's constraint table is corrected.

Steps 5-6 are a different matter: PTC *is* tool calling, and that path does not
exist on the Unsloth stack. That fork is now the research session's `ptc/`.

### `transformers<5`, or the trainer will not import

`pip install unsloth` resolves `trl==0.24.0` — Unsloth's ceiling, confirmed by a
real resolve rather than by reading pins — **and** `transformers==5.5.0`, because
TRL 0.24 declares `transformers>=4.56.1` with no upper bound. That pair is broken:

```
>>> from trl import GRPOTrainer
ModuleNotFoundError: No module named 'mergekit'
```

transformers 5 changed `_is_package_available` to return `tuple[bool, str]`. TRL
calls it without `return_version=True` and stores the raw result, so every
optional-dependency flag becomes `(False, None)` — a non-empty tuple, therefore
**truthy** — and every `if is_X_available():` guard fires against a package that
is not installed. Measured: **11 of 12 flags inverted** on 5.5.0, **zero** on
4.57.6. `mergekit` is simply the first one the GRPO import path reaches, which is
why the error names neither transformers nor the cause.

`gate_chat_template.py` detects this and exits 1 with the fix.

---

## The mistake worth carrying forward

`verdict.py` required `entropy`, which **this stack never logs** — TRL logs it
only from a closure inside `_compute_loss`, which Unsloth replaces wholesale, and
the replacement hardcodes `compute_entropy = False`. So `verdict()` printed
`STEP 2 FAIL` on every healthy run: a fail-closed defect inside the file written
to prevent fail-closed defects.

**56 mutants missed it, and could not have caught it.** Every `verdict()` test fed
synthetic log dicts built carrying `entropy` — the assumption under test. Mutating
logic cannot falsify the premise the fixtures encode. It was found by the research
session's independent audit (`docs/step2-audit.md`), not by this session.

The generalisable lesson, which Step 1's four defects were also instances of:

> **Mutation testing validates logic against fixtures. It cannot validate the
> fixtures against reality.** For every external contract, check the real artifact
> — vendor source, a real resolve, a real API — not your model of it.

The "check against vendored source" pattern *had* been applied to `GRPOConfig`
kwargs and worked. It was simply never applied to the metric contract. Now:
`gen_metric_contract.py` derives the contract from real TRL and Unsloth source,
`test_step2.py` asserts `REQUIRED_KEYS` is a subset of it, and the fixture no
longer supplies `entropy`.

---

## Decisions made, so they are not silently revisited

| Decision | Why |
|---|---|
| `beta = 0.04`, not 0 | `08` §7 found a public Kaggle 2×T4 run at nearly this config that did 314 steps clean, so `beta=0` only reproduces a known result. It published **no KL curve** — HANDOFF's standing unknown. `beta>0` costs zero extra weights on the PEFT adapter-disable path. |
| `entropy` dropped from `REQUIRED_KEYS`, check kept | Not emitted here, but raw TRL logs it and Step 6 may drop Unsloth for rented Ampere. `observations()` declares the gap on every run rather than leaving a dormant guard. |
| Step 0 exempt for `grad_norm` only | GradScaler starts at `init_scale=65536` and halves on overflow, so step 0 legitimately overflows. One step, one key — a blanket non-finite exemption would discard the real overflow signal. |
| Flatness, never finiteness, for `kl` | Unsloth logs `kl` unconditionally; at `beta=0` it is `zeros_like(...)`. A finiteness check would pass a run that measured nothing and leave a JSONL that reads as a KL curve. |
| `verdict()` keeps its 2-tuple; notes live in `observations()` | A note must never make a run pass, and a failure must never be downgraded to a note. Asserted structurally. |

---

## What this stack cannot see, stated so nobody assumes otherwise

- **Entropy collapse.** Garg's clearest signature — entropy → 0 at lr 1e-4 — is
  unobservable. `grad_norm`, `reward_std` and KL spread are what remain.
- **Multi-GPU.** Unsloth forces `_n_gpu = 1` under `ParallelMode.NOT_DISTRIBUTED`,
  so this is single-process whatever the session shows. `NCCL_CUMEM_ENABLE` is
  inert on that path and set only so it is already right when Step 6 turns vLLM on.
- **Competence.** The reward measures output length. It cannot detect a model
  emitting 20 tokens of noise. Correct for a stability probe, useless as a task.
- **Trend.** Five steps is too few to fit a slope; `entropy > 0.01` is a floor.

---

## Reading a result

A `STEP 2 FAIL` from a non-finite `grad_norm` after step 0 is **the fp16 answer,
and it is "no"** — not a broken script. Record it. A clean negative closes Step 2
as well as a pass does: it sends Step 6 to rented Ampere, a fork `08` already made
live by finding prime-rl cannot run on a T4 at all.

Commit `step2_metrics.jsonl` either way. It opens with a `config` record naming
what produced it, and `verdict.py` can re-judge it later with no GPU.

---

## Do not

- **Start Step 3.** HANDOFF is explicit that it is the interesting one and the
  wrong next move; its shape depends on the fp16 answer (T4 vs rented Ampere).
- **Touch `src/` or `tests/`.** Step 1's gate. `tests/leaky_env.py` is a permanent
  red-team target and must stay exploitable.
- **Lift `transformers<5`** without re-running `gate_chat_template.py`.
- **Edit `metric_contract.json` by hand.** Regenerate it; the refresh commands are
  in `gen_metric_contract.py`'s docstring.
- **Trust a green check.** Mutate the target and confirm red. Four defects on this
  project were a passing check running against a stale, fake or dormant target —
  two of them inside the verification tooling itself.

---

## Concurrency

Two sessions have worked this repo. **Give each its own `git worktree`** — a shared
checkout caused a branch switch under a live session and one contaminated commit
(`git add HANDOFF.md` without diffing swept 84 lines of the other session's
uncommitted work into a Step 2 commit; split back out, trees verified identical).

Both sessions have now audited each other and both audits found something real:
`docs/step2-audit.md` (theirs, on my `step2/`) and `docs/ptc-runtime-review.md`
(mine, on their `ptc/`). Worth continuing.
