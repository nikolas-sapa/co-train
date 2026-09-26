# Step 2 audit — findings for the step2/ owner
2026-09-26. Written by the research session. **`step2/` is not mine and I have not
edited it** — one patch was made before ownership was declared and was reverted
(`git checkout -- step2/verdict.py`; tree clean, nothing committed).

Everything below was verified in library source, not docs. Unsloth is unpinned, so
line numbers are `@ main` as of this date and should be re-checked if it moves.

---

## The root cause behind most of this: the metrics contract is not TRL's

`step2/smoke.py:20` runs `import unsloth` **before** `step2/smoke.py:25` does
`from trl import GRPOConfig, GRPOTrainer`. Unsloth rebinds both names at import
time — `unsloth/models/llama.py:4037` calls `PatchFastRL(...)` at module level →
`unsloth/models/rl.py` → `patch_trl_rl_trainers()`, which reassigns
`trl.GRPOTrainer`, `trl.trainer.GRPOTrainer` and `trl.trainer.grpo_trainer.GRPOTrainer`
to `UnslothGRPOTrainer`, and the same for `GRPOConfig`.

So `step2/verdict.py:44-45`'s comment — *"verified against trl v0.24.0
grpo_trainer.py"* — cites a file the run does not execute. The operative source is
`unsloth/models/rl_replacements.py`. TRL v0.24.0 is still the right reference for
config **fields** (Unsloth's config mirrors it) but not for **logged metrics**.

## 1. FATAL — `verdict.py` fails every healthy run

`REQUIRED_KEYS` includes `"entropy"`. It is never logged on this stack.

`rl_replacements.py` contains the word exactly three times: `compute_entropy = False`
hardcoded at **:1888** and **:2908**, passed through at **:2920**. TRL does log
entropy, at `grpo_trainer.py:1761` — but inside `_compute_loss`, whose sole caller
`compute_loss` Unsloth replaces wholesale, making that line dead code here.

Result: `verdict()` appends `"step N: missing entropy"` for all five steps and prints
`STEP 2 FAIL` on a perfectly good run. The fail-closed bug the file exists to prevent
is in the file.

**Fix:** drop `"entropy"` from `REQUIRED_KEYS`.

**Do not paper over the loss.** Garg's clearest collapse signature was entropy going
to zero at lr 1e-4 (3e-5 stable), and this stack cannot see it. What remains is
`grad_norm`, `reward_std`, and KL spread. If collapse detection ever matters more than
"does fp16 run", the upgrade path is patching `compute_entropy = True` in the
replacement or reading logits in a callback — not worth it for Step 2's one question.

## 2. HIGH — `grad_norm` is `inf` on step 1 under fp16 *by design*

`GradScaler` starts at `init_scale = 65536` and calibrates down; the first step
legitimately overflows and transformers logs `inf`. `verdict.py:82` treats any
non-finite value as failure, so a correct fp16 run fails on step 1.

**Fix:** exempt the first step for `grad_norm` **specifically** — not a blanket
exemption, or the real overflow signal is lost with it.

## 3. MEDIUM — `beta` unset skips the only unpublished measurement

This is an opportunity, not a bug, but it has a trap attached.

Unsloth logs `kl` **unconditionally** at `rl_replacements.py:3141`/`:3144`, with no
`beta != 0.0` guard (TRL guards it at `grpo_trainer.py:1758`). At `beta=0.0` the
per-token KL is `torch.zeros_like(...)` (`unsloth_zoo/rl_replacements.py:577-579`),
so **every step logs a literal constant `0.0`**.

Two consequences:

- Adding `kl` to `REQUIRED_KEYS` with a *finiteness* check would **pass** a run that
  measured no KL at all, and the JSONL would read as a KL curve to whoever opens it
  next. Assert on **spread** (`len(set(kls)) == 1` → fail), not finiteness.
- Setting `beta = 0.04` costs **zero extra weights**: `grpo_trainer.py:430-433` sets
  `self.ref_model = None` for a PEFT model and uses the adapter-disable path.

Why it is worth doing: `research/08-gap-closure.md` §7 found a public Kaggle 2×T4 run
(`rkkzone/qwen3-0.6b-math-l45-grpo-adapter`) at almost exactly this config —
`fp16=True`, `bf16=False`, `use_vllm=False`, dense Qwen3-0.6B — that completed **314
steps in 5.9 h with zero non-finite values**. "Does it run, is fp16 stable" is
therefore already answered in the affirmative by someone else's committed log. That
run had `beta=0` and published **no KL curve**, which is precisely the standing
unknown in HANDOFF. At `beta=0`, Step 2 reproduces a known result and leaves the
unknown standing. At `beta>0`, it contributes the one curve nobody has.

If you decide against it, say so explicitly in `step2/README.md` so a future session
does not think KL was measured.

## 4. LOW — dataset comment is wrong, conclusion is safe

`smoke.py:70` says `max_steps * per_device_batch`. `RepeatSampler` actually consumes
`max_steps × (generation_batch_size // num_generations)` = **5 unique prompts**
(`grpo_trainer.py:685-692`). You supply 128. 25× slack; never wraps short. Comment
only.

## 5. LOW — it is single-GPU, and the banner says otherwise

`smoke.py:94` prints `T4 x2`, but `rl.py:531-534` forces `args._n_gpu = 1` under
`ParallelMode.NOT_DISTRIBUTED`, so it is single-GPU unless launched with
`accelerate launch --num_processes 2`. `NCCL_CUMEM_ENABLE` is inert on that path.
Truthfulness-of-output issue, not a crash.

---

## Checked and CORRECT — no action

| Item | Verdict | Source |
|---|---|---|
| `load_in_16bit` | Real Unsloth arg, unquantized 16-bit LoRA; conflict guard does not fire | `loader.py:458`, `:150-153` |
| All 17 `GRPOConfig` kwargs | Exist in v0.24.0 | `grpo_config.py` |
| `mask_truncated_completions` | Exists **and** smoke.py sets it | `grpo_config.py:557`, `smoke.py:126` |
| `completions/mean_length` | Survives — emitted by TRL's `_generate`, which Unsloth wraps rather than replaces | `grpo_trainer.py:1332` |
| `reward_std`, `grad_norm` | Emitted | `grpo_trainer.py:1526`; `transformers/trainer.py:3206` |
| Reward fn receives `list[str]` | `is_conversational` False for `{"prompt": "<str>"}`; verdict.py's `isinstance(str)` arm is the live one | `grpo_trainer.py:1472,1478` |
| `on_log` signature | Correct, fires on the GRPO path | `transformers/trainer_callback.py:547` |
| `num_generations` divisibility | Passes at world_size 1 **and** 2 (8 or 16, both `% 8 == 0`) | `grpo_config.py:648-687` |
| T4 assert | `sm_75` passes `cap[0] < 8` correctly | `smoke.py:97` |

## Suggested order

1 and 2 are blocking — the run cannot report a pass without them. 3 is the one worth
a decision rather than a patch. 4 and 5 are cosmetic and can ride along.
