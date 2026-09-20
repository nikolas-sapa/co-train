# GRPO in Practice at Small Scale, for Multi-Turn Agentic Tasks

Research lane report. Compiled 2026-09-19.

Working copies downloaded for analysis (read-only, not modified):

- `/tmp/rl-research/trl-1.13.0/` — official `v1.13.0` release tarball
- `/tmp/rl-research/verifiers-main/` — `PrimeIntellect-ai/verifiers` @ main
- `/tmp/rl-research/prime-rl-main/` — `PrimeIntellect-ai/prime-rl` @ main

**Important caveat on provenance:** `trl` is **not installed** in this environment (`import trl` → `ModuleNotFoundError`). Every TRL line number below comes from the official v1.13.0 source tarball, not from a live interpreter. Line numbers are exact for that tag and will drift on `main`.

---

## Table of contents

1. [Sources consulted](#1-sources-consulted)
2. [Q1 — GRPOTrainer's actual multi-turn / agentic API](#2-q1--grpotrainers-actual-multi-turn--agentic-api)
3. [**The loss-masking mechanism over tool-output tokens**](#3-the-loss-masking-mechanism-over-tool-output-tokens-decisive-detail)
4. [Q2 — How `verifiers` models an environment](#4-q2--how-verifiers-models-an-environment)
5. [Q3 — trl+Harbor vs prime-rl+verifiers, with recommendation](#5-q3--trlharbor-vs-prime-rlverifiers)
6. [Q4 — Known failure modes](#6-q4--known-failure-modes)
7. [Q5 — Reward design for long-horizon agentic tasks](#7-q5--reward-design-for-long-horizon-agentic-tasks)
8. [Copy-ready snippet locations](#8-copy-ready-snippet-locations)
9. [Confidence summary](#9-confidence-summary)
10. [Known gaps](#10-known-gaps)

---

## 1. Sources consulted

### Source trees retrieved

| URL | What it contained |
|---|---|
| `https://github.com/huggingface/trl/archive/refs/tags/v1.13.0.tar.gz` | `trl/trainer/grpo_trainer.py` (3492 lines, 204 KB), `trl/trainer/grpo_config.py` (1040 lines, 70 KB), `trl/experimental/harbor/{__init__,_spec,_env}.py`, `docs/source/{grpo_trainer,async_grpo_trainer,openenv,harbor,openreward,reducing_memory_usage,speeding_up_training}.md`, 19 `examples/grpo_*` directories |
| `https://github.com/PrimeIntellect-ai/verifiers/archive/refs/heads/main.tar.gz` | `verifiers/v1/{env,task,taskset,harness,judge,trace,rollout,agent,graph,state,types,errors}.py`, `verifiers/v1/utils/decorators.py`, `docs/v1/{overview,architecture,env,agent,harnesses,harbor,tasksets,evaluation,getting_started,gepa}.md`, `skills/{create-environments,evaluate-environments,brainstorm,release}/SKILL.md`, `environments/bash_interception/`, `AGENTS.md` |
| `https://github.com/PrimeIntellect-ai/prime-rl/archive/refs/heads/main.tar.gz` | `README.md`, `docs/{algorithms,overview,scaling,inference,training,advanced,configuration,development,eval}.md`, `examples/basic/{reverse-text,wordle,hendrycks-sanity}/`, `examples/advanced/`, `configs/{ci,debug}/` |

### APIs queried

| Endpoint | Used for |
|---|---|
| `http://export.arxiv.org/api/query` (Atom) | Title/abstract search for GRPO variants and critiques; **all cited IDs re-resolved via `id_list=` for verification (16/16 resolved)** |
| `https://arxiv.org/html/2503.14476v2` (direct + via `r.jina.ai`) | DAPO paper body — the four techniques, §3.1–3.4, and the hyperparameter section |
| `https://api.github.com/search/issues?q=repo:huggingface/trl+...` | Failure-mode discovery on the TRL tracker |
| `https://api.github.com/repos/huggingface/trl/issues/{7068,6789,7269,6350,6368}` | Full bodies of the five decisive issues/PRs |
| `https://api.github.com/repos/huggingface/trl/pulls/{7068,6368}` | **Merge-status verification** (`merged`, `merged_at`) |
| `https://raw.githubusercontent.com/huggingface/trl/main/trl/trainer/grpo_config.py` | Confirming whether unmerged features later landed on `main` |
| `https://pypi.org/pypi/{trl,verifiers,prime-rl}/json` | Version and Python-requirement facts |

### Versions established

- **`trl` 1.13.0** — PyPI latest, `requires_python >= 3.10`
- **`verifiers` 0.3.1** stable; `0.3.2.dev99` on the dev channel; `requires_python >= 3.11, < 3.14`
- **`prime-rl`** — **not published on PyPI.** Install via `curl -sSL .../scripts/install.sh | bash` or git clone with submodules (`deps/verifiers`, `deps/renderers`, `deps/prime-envs`, `deps/pydantic-config`)

### arXiv IDs verified (16/16 resolved via `id_list=`)

```
2402.03300v3  2024  DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models
2503.14476v2  2025  DAPO: An Open-Source LLM Reinforcement Learning System at Scale
2503.20783v2  2025  Understanding R1-Zero-Like Training: A Critical Perspective   [Dr. GRPO]
2507.18071v2  2025  Group Sequence Policy Optimization                            [GSPO]
2506.13585v1  2025  MiniMax-M1: Scaling Test-Time Compute Efficiently with Lightning Attention  [CISPO]
2505.07291v1  2025  INTELLECT-2: A Reasoning Model Trained Through Globally Decentralized RL
2511.20718v2  2025  Stabilizing Off-Policy Training for Long-Horizon LLM Agent via Turn-Level
                    Importance Sampling and Clipping-Triggered Normalization      [SORL / SO-GRPO]
2509.26114v1  2025  Clip-Low Increases Entropy and Clip-High Decreases Entropy in RL of LLMs
2505.22257v2  2025  Revisiting Group Relative Policy Optimization: Insights into On-Policy and
                    Off-Policy Training
2503.15952v3  2025  Adaptive Group Policy Optimization: Towards Stable Training and Token-Efficient
                    Reasoning                                                     [AGPO]
2511.20347v2  2025  Soft Adaptive Policy Optimization                             [SAPO]
2510.13786v1  2025  The Art of Scaling Reinforcement Learning Compute for LLMs    [ScaleRL]
2510.06214v1  2025  Stratified GRPO: Handling Structural Heterogeneity in RL of LLM Search Agents
2510.08049v3  2025  A Survey of Process Reward Models: From Outcome Signals to Process Supervisions
2509.25598v1  2025  Hybrid Reward Normalization for Process-supervised Non-verifiable Agentic Tasks
2510.11967v1  2025  Scaling Long-Horizon LLM Agent via Context-Folding
```

Additional IDs surfaced by search but **cited by title only** (not independently resolved or read): `2601.03703` (length-invariance impossibility), `2604.16242` (gradient fingerprints), `2509.15557` (verifiable composite rewards), `2602.05261` (LUSPO), `2602.10693` (VESPO). The last two were taken from TRL's own config help text rather than the arXiv API. Treat all five as lower confidence.

### GitHub issues / PRs read in full

| # | Title | State | Created |
|---|---|---|---|
| 6368 | Stop overcounting dead groups and increase your accuracy (`loss_type="dapo_zv"`) | **closed, NOT merged** | 2026-07-13 |
| 6350 | Feature request: reward-hacking onset monitoring during GRPO/DPO training | closed | 2026-07-10 |
| 6789 | GRPO: vLLM importance-sampling ratio is biased when top_p/top_k/min_p truncate sampling | **open** | 2026-08-18 |
| 7068 | fix(grpo): add opt-in `mask_zero_advantage_groups` for zero-variance groups under `beta>0` | **closed, NOT merged** | 2026-09-05 |
| 7269 | GRPO: put vLLM's truncated-sampling log-probs on the trainer's support | **open** | 2026-09-18 |

---

## 2. Q1 — GRPOTrainer's actual multi-turn / agentic API

### 2.1 `GRPOTrainer.__init__` signature

`trl/trainer/grpo_trainer.py:300-321` (class declared at `:140`):

```python
def __init__(
    self,
    model: "str | PreTrainedModel | PeftModel",
    reward_funcs: RewardFunc | list[RewardFunc] | None = None,
    args: GRPOConfig | None = None,
    train_dataset: Dataset | IterableDataset | None = None,
    eval_dataset: Dataset
    | IterableDataset
    | DatasetDict
    | IterableDatasetDict
    | dict[str, Dataset | IterableDataset]
    | None = None,
    processing_class: PreTrainedTokenizerBase | ProcessorMixin | None = None,
    reward_processing_classes: PreTrainedTokenizerBase | list[PreTrainedTokenizerBase] | None = None,
    callbacks: list[TrainerCallback] | None = None,
    optimizers: tuple[torch.optim.Optimizer | None, torch.optim.lr_scheduler.LambdaLR | None] = (None, None),
    quantization_config: "BitsAndBytesConfig | None" = None,
    peft_config: "PeftConfig | None" = None,
    tools: list[Callable] | None = None,
    rollout_func: RolloutFunc | None = None,
    environment_factory: EnvironmentFactory | dict[str, EnvironmentFactory] | None = None,
):
```

Type alias, `grpo_trainer.py:125`:

```python
RewardFunc = str | PreTrainedModel | Callable[..., list[float | None]]
```

The trainer's declared paper provenance (`grpo_trainer.py:289-299`) is DeepSeekMath, arXiv:2402.03300.

### 2.2 `GRPOConfig` — it is a dataclass, not a signature

`trl/trainer/grpo_config.py:22-23`:

```python
@dataclass
class GRPOConfig(_BaseConfig):
```

~90 fields. There is no positional signature to quote; you set attributes. The fields that matter for multi-turn agentic work, with exact line numbers and defaults:

| Field | Line | Default | Note |
|---|---|---|---|
| `learning_rate` | 422 | — | example scripts use `1e-6` |
| `num_generations` | 479 | `None` | G in the GRPO paper; group size |
| `num_generations_eval` | 486 | `None` | falls back to `num_generations` |
| `max_completion_length` | 493 | 256 | see issue #6263 proposing 512 |
| `generation_batch_size` | 516 | `None` | |
| `steps_per_generation` | 523 | `None` | |
| `temperature` | 527 | 1.0 | |
| `top_p` | 531 | **1.0** | leave at 1.0 if using vLLM IS correction — see §6.5b |
| `top_k` | 538 | **0** | as above |
| `min_p` | 545 | `None` | as above |
| `chat_template_kwargs` | 561 | `None` | e.g. `{"enable_thinking": False}` |
| `use_vllm` | 582 | `False` | |
| `vllm_mode` | 589 | `"server"` | or `"colocate"` |
| `vllm_gpu_memory_utilization` | 651 | 0.3 in examples | colocate only |
| `beta` | 676 | **0.0** | **KL coefficient. 0.0 means no reference model is loaded at all** |
| `num_iterations` | 684 | 1 | μ |
| `epsilon` | 688 | 0.2 | clip low |
| `delta` | 692 | `None` | two-sided upper bound, INTELLECT-2 |
| `epsilon_high` | 700 | `None` | clip high; DAPO recommends 0.28 |
| `sapo_temperature_neg` | 709 | 1.05 | |
| `sapo_temperature_pos` | 717 | 1.0 | |
| `importance_sampling_level` | 755 | `"token"` | `"sequence"` = GSPO |
| `reward_weights` | 765 | `None` | applies to `reward_funcs` only |
| `multi_objective_aggregation` | 772 | `"sum_then_normalize"` | |
| `scale_rewards` | 784 | `"group"` | `"batch"` \| `"none"` |
| `loss_type` | 796 | **`"dapo"`** | 8 options, see §6.2 |
| `mask_truncated_completions` | 831 | **`False`** | **turn this on for agentic rollouts** |
| `sync_ref_model` | 839 | `False` | |
| `ref_model_mixup_alpha` | 846 | — | |
| `ref_model_sync_steps` | 854 | — | |
| `top_entropy_quantile` | 861 | 1.0 | |
| `entropy_coef` | 871 | 0.0 | |
| `use_adaptive_entropy` | 881 | `False` | |
| `entropy_coef_min` / `_max` / `_delta` / `entropy_target` | 889 / 893 / 897 / 901 | — | adaptive entropy control |
| `max_tool_calling_iterations` | 912 | **`None`** | unlimited; cap this |
| `vllm_importance_sampling_correction` | 920 | — | |
| `vllm_importance_sampling_mode` | 929 | — | `token_truncate` \| `token_mask` |
| `off_policy_mask_threshold` | 958 | `None` | |
| `use_bias_correction_kl` | 967 | `False` | multiplies KL by the IS ratio |
| `log_completions` | 980 | `False` | |

Note two defaults that shape everything downstream:

- **`loss_type` defaults to `"dapo"`, not `"grpo"`.** TRL already ships the DAPO length-bias fix as the default aggregation.
- **`beta` defaults to `0.0`.** No reference model is loaded, no KL term is computed. Config help, verbatim: *"If `0.0` (default), the reference model is not loaded, reducing memory usage and improving training speed."* This is the single largest memory saving available at small scale, and it means "KL blowup" is not a default-configuration failure mode.

### 2.3 Three agentic entry points

Documented at `grpo_trainer.py:251-283` and `docs/source/grpo_trainer.md:707-940`.

**(a) `tools=[fn, ...]`** — stateless functions. Each must be a plain Python function (sync or async) with type-hinted arguments and return type plus a Google-style docstring. TRL derives the tool schema from those. Docs:

> Each tool must be a standard Python function with **type-hinted arguments and return types**, along with a **Google-style docstring** describing its purpose, arguments, and return value.

**(b) `environment_factory`** — the general form. A callable returning a fresh environment instance, **one per rollout**, so rollouts cannot contaminate each other. Public methods become tools. Or a `dict[str, EnvironmentFactory]`, in which case each dataset row carries an `environment` column selecting one, and **only that environment's tools are exposed in its prompt** (`:277-281`). That last property matters: it prevents a game's `move` tool leaking into a coding prompt in a mixed-task run.

**(c) `rollout_func`** — you own generation entirely. Docstring, `grpo_trainer.py:258-265`, verbatim:

> Function to use for generating completions. It receives the list of prompts allocated to the current process and the trainer instance. It must return a dict with `"prompt_ids"`, `"completion_ids"`, and `"logprobs"` fields, and can optionally return `"logprob_token_ids"` (same shape as `"logprobs"`). Any other fields are forwarded to the reward functions. The function receives the raw per-process prompt slice with no duplication; it is responsible for returning the correct number of completions per prompt.

All three compose. From the docs: *"They compose — you can pass standalone `tools` alongside an `environment_factory`."*

All three carry the same warning in the docstring: *"This feature is experimental and may change or be removed at any time without prior notice."*

### 2.4 The environment contract — two reserved methods, everything else becomes a tool

Docstring at `grpo_trainer.py:266-283`, quoted in full because it is the contract:

> **environment_factory** (`EnvironmentFactory` or `dict[str, EnvironmentFactory]`, *optional*):
> A callable that creates and returns an environment instance, or a dictionary mapping environment names to such callables. The environment class should define methods that can be invoked as tools during generation. Each method should comply with the same requirements as the `tools` described above. The environment must also implement a callable `reset` method that can be used to reset state between generations. The `reset` method should return either `None` or a string: when it returns a string, that string is appended to the last user message before generation. The environment may also define a `get_reward` method taking no argument and returning a `float`: when present, the environment owns the reward, and `get_reward` is called once per completed rollout to score it from the environment's internal state. It acts as an additional reward source (with weight 1, logged under the environment's class name) alongside `reward_funcs`, which then becomes optional.
>
> With a single callable, every example uses the same environment, with one instance per rollout so their interactions stay isolated. With a dictionary, each example must carry an `environment` field selecting its environment by name, and only that environment's tools are exposed in its prompt — letting a single run mix tasks (e.g. a coding environment and a game).

Enforcement of "at least one reward source" is at `:701-706`:

```python
if not self.reward_funcs:
    raise ValueError(
        "No reward source provided. Pass `reward_funcs`, or an `environment_factory` whose environment "
        ...
    )
```

`get_reward` is appended into `self.reward_funcs` at `:694` (`self.reward_funcs.append(get_reward)`), which is why it carries weight 1 and is logged under the environment's class name.

The minimal complete environment, from `docs/source/grpo_trainer.md`:

```python
class IncrementEnv:
    # Reserved methods
    def reset(self, **kwargs) -> str | None:   # required; called at the start of each rollout
        self.counter = 0
        self.target = random.randint(1, 6)     # self-sample the task
        return f"Increment the counter by {self.target}."   # returned string becomes the prompt

    def get_reward(self) -> float:             # optional: env scores itself from its own state
        return float(self.counter == self.target)

    # Public methods (exposed as tools)
    def increment(self, step: int) -> int:
        """
        Increment the internal counter.

        Args:
            step: Value to add to the counter.

        Returns:
            The updated counter value.
        """
        self.counter += step
        return self.counter

trainer = GRPOTrainer(
    model="Qwen/Qwen3-0.6B",
    args=GRPOConfig(max_steps=1000, chat_template_kwargs={"enable_thinking": False}),
    environment_factory=IncrementEnv,
)
```

Notice: **no `train_dataset`.** Docs, verbatim: *"When you use an `environment_factory`, the environment owns the data: there is no external `train_dataset`. On each rollout, `reset()` produces the task — self-sampling from a corpus the environment holds, or generating a state procedurally — and returns the prompt. `max_steps` sets the training length."*

An external dataset is optional. When supplied, the trainer samples a row, uses its `"prompt"` column, and **passes the row's other columns to `reset()` as keyword arguments**. That is how Harbor injects `task_dir`.

A subtlety TRL flags itself and that bites group-relative methods:

> Because the environment self-samples on each `reset()`, the `G` members of a GRPO group may not share the same initial state, making the group baseline slightly noisier. For identical states within a group, have `reset()` derive the state deterministically from a shared key.

`environment_factory` requires `transformers >= 5.2.0`.

### 2.5 What a reward function actually receives

`_calculate_rewards`, `grpo_trainer.py:1636-1740`. The synchronous call site is `:1683-1686`:

```python
output_reward_func = reward_func(
    prompts=prompts, completions=completions, completion_ids=completion_ids_list, **reward_kwargs
)
```

`reward_kwargs` is assembled at `:1640-1657`. It is **every dataset column** except `prompt`, `completion`, `completion_ids` (`:1640-1641`), plus four injected keys:

| kwarg | line | what it is |
|---|---|---|
| `trainer_state` | 1646 | `self.state`. Source comment: *"This allows for dynamic reward shaping based on training progress."* |
| `log_extra` | 1649 | callable `self._log_completion_extra` — adds a column to the completions table |
| `log_metric` | 1652 | callable `self._log_metric` — logs a scalar metric |
| `environments` | 1656-1657 | **the live per-completion environment instances**, present whenever `environment_factory` is set. Source comment: *"Expose the per-completion environment instances to reward functions (both sync and async paths)."* |

Contract enforcement at `:1687-1692` — returning the wrong count raises:

```python
if len(output_reward_func) != len(prompts):
    raise ValueError(
        f"The reward function '{reward_func_name}' returned {len(output_reward_func)} rewards, but "
        f"{len(prompts)} were expected (one per prompt-completion pair). ..."
    )
```

`None` is mapped to `NaN` at `:1685`. This is the documented way to say "unscorable", and it is load-bearing — see §7.

Async reward functions are detected by `inspect.iscoroutinefunction` (`:1678`, and `:717` at construction) and executed concurrently with `asyncio.gather` (`:1698-1717`).

`nn.Module` reward models take a different branch (`:1665-1677`): conversational prompts get `apply_chat_template`d, then scored as `reward_func(**reward_inputs).logits[:, 0]`.

Final step, `:1738-1740` — rewards are gathered across processes *before* group normalization:

```python
# Gather the reward per function: this part is crucial, because the rewards are normalized per group and the
# completions may be distributed across processes
rewards_per_func = gather(rewards_per_func)
```

### 2.6 Advantage computation

`grpo_trainer.py:2780-2836`. Group mean at `:2791-2792`, group std at `:2795-2797`, batch std at `:2800-2805`, then `:2811-2814`:

```python
advantages = rewards - mean_grouped_rewards
if self.scale_rewards != "none":
    advantages = advantages / (std_rewards + 1e-4)
is_std_zero = torch.isclose(std_rewards, torch.zeros_like(std_rewards))  # for logging
```

And the unscorable defense at `:2834-2836`:

```python
# Unscorable completions (every reward func returned None) carry no learning signal: their reward is NaN here,
# so zero their advantage to keep them from moving the policy.
advantages = torch.nan_to_num(advantages, nan=0.0)
```

`frac_reward_zero_std` is logged at `:2857` — this is your advantage-collapse dashboard metric.

---

## 3. The loss-masking mechanism over tool-output tokens (decisive detail)

**This is the mechanism that decides whether a custom harness is trainable at all.** Answer: yes, TRL masks environment/tool tokens out of the loss, via a parallel `tool_mask` integer list that is built during the rollout and multiplied into the completion mask before the loss. Full chain below, every step with its line range.

### 3.1 Representation: one flat token sequence, not a list of turns

A multi-turn trajectory is **a single flat token sequence** per rollout. `completion_ids[i]` is one growing list of ints spanning every assistant turn *and* every rendered tool result. Turn boundaries are not stored structurally; they are recoverable only from the mask.

The loop that builds it: `_tool_call_loop`, **`trl/trainer/grpo_trainer.py:1985-2222`**.

### 3.2 Step 1 — mask initialized, 1 = model token

**`grpo_trainer.py:1990`**:

```python
tool_mask = [[1] * len(ids) for ids in completion_ids]  # 0 for tool result tokens, 1 elsewhere
```

That inline comment is the whole semantic: **1 = trainable model-generated token, 0 = external token.**

### 3.3 Step 2 — measuring the tool-result token span

Before it can mask, TRL must know exactly how many tokens the chat template will emit for the tool result. It does **not** guess: `_get_tool_suffix_ids`, **`grpo_trainer.py:1933-1984`**, renders a throwaway two-message conversation twice and diffs.

```python
def _get_tool_suffix_ids(self, tool_messages):
    """Get token IDs for tool result formatting by using a minimal dummy conversation."""
    # Use the real tool name instead of a dummy: some templates (e.g. GPT-OSS) derive the tool response
    # header from the assistant's tool call name.
    dummy_tool_calls = [{"type": "function", "function": {"name": tool_messages[0]["name"], "arguments": {}}}]
    dummy_messages = [
        {"role": "user", "content": "dummy"},
        {"role": "assistant", "content": "", "tool_calls": dummy_tool_calls},
    ]
    ...
    prefix_ids = self.processing_class.apply_chat_template(dummy_messages, add_generation_prompt=False, tokenize=True, ...)
    full_ids   = self.processing_class.apply_chat_template(dummy_messages + tool_messages, add_generation_prompt=True, tokenize=True, ...)
    ...
    # Some chat templates (notably Qwen3/Qwen3.5) render "...<|im_end|>\n" after an assistant/tool block.
    # When we compute `suffix_ids` by slicing `full_ids`, we must align the slicing boundary to
    # EOS (not EOS + newline).
    eos_positions = [i for i, tok_id in enumerate(prefix_ids) if tok_id == self._tokenizer.eos_token_id]
    if eos_positions:
        prefix_ids = prefix_ids[: eos_positions[-1] + 1]

    if full_ids[: len(prefix_ids)] != prefix_ids:
        raise ValueError("Unexpected tokenization: the EOS-trimmed prefix IDs are not a prefix of the full IDs.")
    return full_ids[len(prefix_ids) :]
```

**The `raise` at `:1981-1982` is the trainability gate for a custom harness.** If your model's chat template is not prefix-preserving — appending a tool message changes how earlier messages render — TRL aborts rather than mis-masking. That is the correct failure mode, but it means template compatibility is a hard prerequisite, not a tuning knob.

TRL's docs (`docs/source/grpo_trainer.md:739`) confirm and give the escape hatch:

> The GRPO tool call loop requires the chat template to be *prefix-preserving* (appending a tool message must not change how earlier messages are rendered). For known model families (e.g. Qwen3, DeepSeek-V3), TRL automatically swaps in a patched training template when tools are enabled.

### 3.4 Step 3 — the mask is extended each iteration

**`grpo_trainer.py:2185-2193`** — the core of the whole mechanism:

```python
# Update tool_mask: the tool result should be 0 and the post-tool 1
for idx in range(len(idxs_with_tool)):
    idx_with_tool = idxs_with_tool[idx]
    prompt_completion_tool_length = len(prompt_completion_tool_ids[idx])
    prompt_length = len(prompt_ids[idx_with_tool])
    completion_length = len(completion_ids[idx_with_tool])
    post_tool_length = len(post_tool_ids[idx])
    tool_length = prompt_completion_tool_length - prompt_length - completion_length
    tool_mask[idx_with_tool] += [0] * tool_length + [1] * post_tool_length
    if logprobs is not None:
        logprobs[idx_with_tool] += [0.0] * tool_length + post_tool_logprobs[idx]
```

`tool_length` is derived arithmetically from the three lengths, so the mask stays exactly aligned with the token stream by construction. Note the parallel treatment of `logprobs`: tool-result positions get `0.0` placeholders so the logprob array stays index-aligned with `completion_ids`.

Immediately before this, **`:2175-2183`** rolls back a tool result that would overflow the budget:

```python
completion_tool_length = len(prompt_completion_tool_ids[idx]) - len(prompt_ids[idx_with_tool])
excess_length = completion_tool_length + len(post_tool_ids[idx]) - self.max_completion_length
if excess_length > 0:
    new_len = len(post_tool_ids[idx]) - excess_length
    post_tool_ids[idx] = post_tool_ids[idx][:new_len]
    if logprobs is not None:
        post_tool_logprobs[idx] = post_tool_logprobs[idx][:new_len]
```

And the flat sequence is extended at **`:2196-2201`**:

```python
pct = prompt_completion_tool_ids[idx]  # = prompt-completion-tool
completion_ids[idx_with_tool] = pct[prompt_length:] + post_tool_ids[idx]
```

Loop termination: `while idxs_with_tool and iteration_num < self.max_tool_calling_iterations` (`:2002`). Return tuple at **`:2222`**:

```python
return tool_mask, completions, completion_ids, logprobs, tool_call_count, tool_failure_count, tool_images
```

### 3.5 Step 3b — the `rollout_func` path uses the same mask under a different name

If you bring your own rollout function, you supply the mask yourself as `env_mask`. **`grpo_trainer.py:2293-2295`**:

```python
else:
    # Support custom env_mask from rollout_func (e.g., for environment feedback masking)
    # Internally treated as tool_mask - marks model tokens (1) vs external tokens (0)
    tool_mask = extra_fields.pop("env_mask", None)
```

**This is the integration point for a fully custom harness.** Return `env_mask` alongside `prompt_ids` / `completion_ids` / `logprobs` and your environment's tokens are excluded from the loss with no dependency on TRL's tool-call loop or on template prefix-preservation. It is the lowest-lock-in path in either stack.

Consequence for logging, **`:2299-2300`**:

```python
if tool_mask is not None:  # count only model-generated tokens (tool_mask=1)
    completion_lengths = torch.tensor([sum(mask) for mask in tool_mask], device=device)
```

so `completions/mean_length` is not inflated by tool output.

`_generate` returns it at **`:2345`**:

```python
return prompt_ids, completion_ids, tool_mask, completions, logprobs, extra_fields, images, tool_images
```

### 3.6 Step 4 — padding, truncation interaction, and the final `loss_mask`

`_generate_and_score_completions`, **`grpo_trainer.py:2475-2524`**:

```python
completion_ids  = [torch.tensor(ids) for ids in completion_ids_list]
completion_mask = [torch.ones_like(ids, dtype=torch.long) for ids in completion_ids]
completion_ids  = pad(completion_ids,  padding_value=self._tokenizer.pad_token_id, padding_side="right", ...)
completion_mask = pad(completion_mask, padding_value=0, padding_side="right", ...)
...
if tool_mask_list is not None:
    tool_mask = [torch.tensor(mask) for mask in tool_mask_list]
    tool_mask = pad(tool_mask, padding_value=1, padding_side="right", ...)   # note: pads with 1
else:
    tool_mask = None

# If mask_truncated_completions is enabled, zero out truncated completions for attention and loss masking
if self.mask_truncated_completions:
    eos_and_pad = [self._tokenizer.eos_token_id, self._tokenizer.pad_token_id]
    is_truncated = torch.tensor([ids[-1] not in eos_and_pad for ids in completion_ids_list], device=device)
    # Mask completion_mask for attention masking
    completion_mask = completion_mask * (~is_truncated).unsqueeze(1).int()
    # Also mask tool_mask for consistency in multi-turn training
    if tool_mask is not None:
        tool_mask = tool_mask * (~is_truncated).unsqueeze(1).int()

loss_mask = completion_mask if tool_mask is None else completion_mask * tool_mask
num_items_in_batch = self.accelerator.gather(loss_mask.sum()).sum()
```

Two details worth internalizing:

- `tool_mask` pads with **1**, `completion_mask` pads with **0**. The product is what matters; padding positions are killed by `completion_mask`.
- **`loss_mask = completion_mask * tool_mask`** (`:2519`) is the single line that makes the whole thing work. It is an elementwise product of two `(B, T)` integer tensors.

### 3.7 Step 5 — attention vs loss are deliberately different

**`grpo_trainer.py:2522-2524`**:

```python
prompt_completion_ids = torch.cat([prompt_ids, completion_ids], dim=1)   # (B, P+C)
attention_mask        = torch.cat([prompt_mask, completion_mask], dim=1) # (B, P+C)
```

`attention_mask` uses **`completion_mask` only, not `loss_mask`.** Tool-output tokens are *attended to* — the model conditions on what the environment said — but are not *trained on*. That asymmetry is correct and is easy to get wrong when writing a custom trainer.

Shipped into the batch dict at **`:2927`** (`"completion_mask": completion_mask`) and **`:2959-2960`**:

```python
if tool_mask is not None:
    output["tool_mask"] = tool_mask
```

### 3.8 Step 6 — consumption in the loss

`_compute_loss`, **`grpo_trainer.py:3113-3383`**. The mask is reconstructed at **`:3116-3120`**:

```python
completion_ids, completion_mask = inputs["completion_ids"], inputs["completion_mask"]
attention_mask = torch.cat([prompt_mask, completion_mask], dim=1)
mask = completion_mask if "tool_mask" not in inputs else completion_mask * inputs["tool_mask"]
```

The Liger path, `compute_liger_loss` at **`:2963`**, does the same at **`:2985-2986`**:

```python
# Apply tool_mask (from env_mask) for loss computation in multi-turn training scenarios
loss_mask = completion_mask if "tool_mask" not in inputs else completion_mask * inputs["tool_mask"]
```

And the same product appears in the vLLM importance-sampling diagnostics at **`:2887`** and in the entropy-quantile path at **`:2683`**, so the mask is respected consistently, not just in the main loss term.

Aggregation, **`:3245-3270`**:

```python
mode = "train" if self.model.training else "eval"
if self.loss_type in ["grpo", "sapo"]:
    loss = ((per_token_loss * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)).mean()
elif self.loss_type == "bnpo":
    loss = (per_token_loss * mask).sum() / mask.sum().clamp(min=1.0)
elif self.loss_type == "dr_grpo":
    loss = (per_token_loss * mask).sum() / (per_token_loss.size(0) * self.max_completion_length)
...
```

(`dapo` normalizes by the global accumulated active-token count, which is `num_items_in_batch` from `:2520`.)

Metric helpers at **`:3347-3352`** (`masked_seq_mean`, `global_masked_mean`) use the same mask, so `kl`, `entropy`, and the clip ratios at `:3361-3381` are all computed over model tokens only.

### 3.9 Summary of the chain

```
_tool_call_loop           :1990   tool_mask = [[1]*len(ids) ...]
  _get_tool_suffix_ids    :1933-1984  measure tool-result span (raises if template not prefix-preserving)
  per iteration           :2185-2193  tool_mask += [0]*tool_length + [1]*post_tool_length
  return                  :2222   tool_mask, ...
_generate (custom path)   :2295   tool_mask = extra_fields.pop("env_mask", None)
_generate (return)        :2345   ... tool_mask ...
_gen_and_score  pad       :2501-2506  pad(tool_mask, padding_value=1)
                truncate  :2508-2517  *= (~is_truncated) when mask_truncated_completions
                COMBINE   :2519   loss_mask = completion_mask * tool_mask      <-- THE LINE
                attention :2524   attention_mask uses completion_mask ONLY
                ship      :2959   output["tool_mask"] = tool_mask
_compute_loss             :3120   mask = completion_mask * inputs["tool_mask"]
compute_liger_loss        :2986   same
aggregate                 :3245-3270  (per_token_loss * mask).sum() / <normalizer per loss_type>
```

**Confidence: strong.** Read end to end from the v1.13.0 release source.

---

## 4. Q2 — How `verifiers` models an environment

A different decomposition from TRL: four objects rather than one duck-typed class.

| Object | File | Role |
|---|---|---|
| `TaskData` | `verifiers/v1/task.py:82+` | Frozen pydantic model. One row's serializable data. **The only part stored on the trace.** |
| `Task` | `verifiers/v1/task.py` | Behavior for that row: `setup` / `finalize` / `validate` hooks, task-scoped toolsets, and `@vf.reward` / `@vf.metric` scoring methods. |
| `Taskset` | `verifiers/v1/taskset.py` | The loader. Implements `load() -> list[Task]`. |
| `Env` | `verifiers/v1/env.py:76` | `ABC, Generic[ConfigT]`. **Multi-agent control flow only.** `SingleAgentEnv` covers the plain case. |
| `Harness` | `verifiers/v1/harness.py` | The reusable agent program / tool surface, reusable across tasksets. |

### 4.1 The `Env` base class

`verifiers/v1/env.py:76-186`. Class docstring, verbatim:

> A taskset, the agents that play it, and how one task becomes one episode.
>
> Abstract: every run gets a concrete subclass — `SingleAgentEnv` for every plain taskset. A multi-agent env declares each role as an `AgentConfig` field on an `EnvConfig` subclass (bound via `Env[YourConfig]`) and writes `run(task, agents)`; optional overrides: `setup`, `finalize`, `start`/`stop` — the base owns everything else.

The overridable surface is small:

```python
async def setup(self, agents: Agents) -> None: ...            # :149  optional
@abstractmethod
async def run(self, task: Task, agents: Agents) -> None: ...  # :153-154  the only required method
async def finalize(self, task: Task, episode: Episode) -> None: ...  # :163
def complete(self, episode: Episode) -> bool:                 # :172
    return episode.ok
async def start(self) -> None: ...                            # :178  env-owned shared resources
async def stop(self) -> None: ...                             # :182
```

`finalize` is documented as the cross-trace judgement seam (`:163-171`), verbatim:

> Cross-agent judgement — THE programmable judgement surface: plain imperative Python over the finished episode (per-trace judgement already ran on each trace's own task). `episode.traces` is the flat episode in completion order, each trace's `agent.name` stamp naming its agent; attach signals via `record_reward`/`record_metric`, in program order. A raise fails the episode (the retryable unit) — validate strictly, never record a guess.

This is a real capability TRL has no equivalent for: best-of-N selection and zero-sum payoffs where a rollout's reward depends on its *siblings*.

### 4.2 Reward is declared by decorator, not returned

`@vf.reward` and `@vf.metric` are exported from `verifiers/v1/__init__.py:146-147` and `:264-265`.

Mechanism, `verifiers/v1/utils/decorators.py`:

- `mark(attr, **extra)` (`:65+`) sets a marker attribute on the function.
- `discover_decorated(obj, attr)` (`:12-27`) walks `type(obj).__mro__` collecting tagged functions, sorted by `-priority` then name. Deliberately avoids `inspect.getmembers` — docstring: *"which evaluates every descriptor — a property with side effects would run here"*. An undecorated override suppresses a decorated base method.
- `invoke(fn, available)` (`:29-38`) is **dependency injection by parameter name, falling back to type annotation**. A reward method declares only the parameters it wants (`trace`, `runtime`, ...) and receives them.
- `invoke_all` (`:41-45`) gathers them concurrently.
- `seed` / `unseed` (`:48-61`) pre-mark every expected scoring key as `None` so a trace records which signals *should* have run even if scoring fails midway.

Scoring orchestration is `Task.score`, `verifiers/v1/task.py:201-272`. Total reward is a weighted sum, `verifiers/v1/trace.py:487-488`:

```python
@property
def reward(self) -> float:
    return sum(r.value for r in self.rewards.values() if r is not None)
```

`trace.rewards: dict[str, Reward | None]` and `trace.metrics` (`trace.py:423-427`) — `None` explicitly means *"scoring didn't run"*, distinct from zero. Metrics are unweighted and do not contribute to reward.

### 4.3 The minimal complete authoring example

From `skills/create-environments/SKILL.md`, verbatim:

```python
import verifiers.v1 as vf


# One row's serializable data. Add references or other task-specific fields here.
class AdditionData(vf.TaskData):
    answer: int


# The behavior for that row. Decorated methods may request only the values they need;
# `trace` contains the full message graph and `self.data` is this task's row.
class AdditionTask(vf.Task[AdditionData]):
    @vf.reward
    async def exact_match(self, trace: vf.Trace) -> float:
        return float(trace.last_reply == str(self.data.answer))


# The taskset is the loader. Its config can be the empty base config.
class AdditionTaskset(vf.Taskset[AdditionTask, vf.TasksetConfig]):
    def load(self) -> list[AdditionTask]:
        # Construct one behavior object around each data row and the shared task config.
        return [
            AdditionTask(
                AdditionData(idx=i, prompt=f"What is {i} + {i}?", answer=2 * i),
                self.config.task,
            )
            for i in range(100)
        ]


# Export the taskset class so the v1 loader can discover it.
__all__ = ["AdditionTaskset"]
```

Scaffolding is CLI-driven:

```bash
uv run vf-init my-task-v1        # plain taskset
uv run vf-init my-task-v1 -T     # + task toolset
uv run vf-init my-agent-v1 -H    # + custom reusable harness
```

Package contract, verbatim from the skill:

> A package exports one `vf.Taskset` subclass — and optionally one `vf.Env` subclass (multi-agent control flow) and/or one `vf.Harness` subclass — through `__all__`. **Do not add `load_environment()`, `load_taskset()`, or `load_harness()` functions.** The v1 loader resolves classes and their config types from `__all__` and generic bases.

### 4.4 Ownership rules (their words, worth copying as a design discipline)

- **`TaskData`** owns immutable serializable values: prompts, system prompts, reference answers, container image, workdir, resources, timeouts. *"Do not put live clients, runtime handles etc. here."*
- **`Task`** owns behavior: `setup`/`finalize`/`validate` hooks, stop conditions, metrics, rewards, task-scoped tool declarations.
- **`Taskset`** owns loading and selection: `load()`, dataset/split/seed/sample-count knobs, shared task-agnostic tool servers.
- **`Harness`** owns the reusable agent program, its provisioning and launch, model-request wiring, and harness-generic execution metrics.
- **Runtime config chooses where code executes.** Task hooks use the `vf.Runtime` interface rather than assuming Docker/Prime/Modal/host specifics.

Lifecycle order: `Task.validate(runtime)` (model-free ground-truth check) → `setup(trace, runtime)` → harness execution → `finalize(trace, runtime)` → `@vf.reward` / `@vf.metric` *while the runtime is still live*.

### 4.5 Interception: a capability TRL lacks entirely

`@vf.stop` blocks a proposed tool call **before execution**; `@vf.intercept` rewrites the request. Real example, `environments/bash_interception/bash_interception/taskset.py`:

```python
class BashInterceptionTask(vf.Task):
    @vf.stop
    def stop_bash(self, response: vf.Response) -> bool:
        # The response is still buffered here. Stopping prevents Bash from
        # receiving the proposed call, so the command cannot execute.
        return self.data.idx == 0 and command(response.message, STOP_COMMAND) is not None

    @vf.intercept
    def rewrite_git(self, request: vf.Request) -> vf.Request | None:
        ...
        # This fills the pre-execution result. Bash returns it to the model instead
        # of running the command, and the rollout continues normally.
        replacement = result.model_copy(update={"content": "This request is blocked. ..."})
        return request.model_copy(update={"messages": [*request.messages[:-1], replacement]})

    @vf.reward
    async def rewritten(self, trace: vf.Trace, runtime: vf.Runtime) -> float:
        sentinel = STOP_SENTINEL if self.data.idx == 0 else REWRITE_SENTINEL
        executed = (await runtime.run(["test", "-e", sentinel], {})).exit_code == 0
        ...
```

Note the reward shells into the live runtime to check a filesystem sentinel — deterministic artifact verification, not transcript judging.

### 4.6 Scoring rules from the skill (verbatim, and good policy regardless of stack)

> - Prefer deterministic verification grounded in the task's actual artifact or answer.
> - Use an LLM judge only when semantic judgment is unavoidable.
> - Metrics are for observability and do not contribute to reward, but are useful.
> - Judgement that compares the sibling traces of one episode (best-of-n selection, zero-sum payoffs) lives on `Env.finalize(task, episode)`.
> - Raise ordinary Python exceptions from rollout hooks and scoring. The rollout records them as `TaskError`.

### 4.7 Stability warning

`verifiers/__init__.py:1-7`, verbatim:

> The v1 stack lives in `verifiers.v1` (`import verifiers.v1 as vf`). The classic v0 stack (`verifiers.legacy`, which also answered at its historical top-level paths — `verifiers.envs`, `verifiers.types`, ...) **has been removed.**

The skill reinforces it: *"Never mix v0 `Environment`, `Rubric`, `Parser`, `SingleTurnEnv`, `MultiTurnEnv`, or `ToolEnv` objects into a v1 taskset."*

**Practical consequence:** the majority of `verifiers` material you will find online — blog posts, Environments Hub entries, tutorials — describes v0 and will not run. The repo says so itself: *"The docs contain short, human-written guides and overviews about the architecture. The `AGENTS.md` and skills are for coding agents and go into more details."* The agent-facing skill files are the better documentation.

**Confidence: strong** for the API (read from source). **Moderate** for stability outlook.

---

## 5. Q3 — trl+Harbor vs prime-rl+verifiers

### 5.1 What Harbor actually is

`HarborSpec` (`trl/experimental/harbor/_spec.py`) is a convenience wrapper, nothing more. Module docstring, verbatim:

> Construct **one** `HarborSpec` and read three properties off it — `.train_dataset`, `.environment_factory`, `.reward_funcs` — each plugging into the matching `GRPOTrainer` kwarg.

```python
spec = HarborSpec("AdithyaSK/data_agent_rl_environment_train", agent="bash", num_tasks=64)

trainer = GRPOTrainer(
    model="Qwen/Qwen3.5-4B",
    args=GRPOConfig(num_generations=8, max_steps=50, max_tool_calling_iterations=25),
    train_dataset=spec.train_dataset,
    environment_factory=spec.environment_factory,
    reward_funcs=spec.reward_funcs,
)
```

Constructor signature (`_spec.py`):

```python
def __init__(
    self,
    dataset: str,
    *,
    agent: str | type[HarborEnv] = "bash",
    environment_type: str = "docker",   # docker | e2b | daytona | gke | modal | runloop | ...
    num_tasks: int | None = None,
    indices: list[int] | None = None,
    include_metadata: bool = True,
) -> None:
```

A Harbor *task* is a directory: `instruction.md` + `task.toml` + `environment/` + `tests/`. The dataset is a tree of them, pulled by `snapshot_download(..., allow_patterns=["tasks/**"])`.

`HarborEnv` base (`_env.py:37`) implements the TRL contract: `reset(task_dir=None, **kwargs) -> str` at `:71` (returns `instruction + self.PROMPT_SUFFIX`), `_exec(command, timeout=180)` at `:78` (truncates output to 8 KB), and a lazy `reward` property at `:87`:

```python
@property
def reward(self) -> float:
    # Submission = the agent wrote /workdir/answer.txt during the rollout; the verifier reads it.
    # Computed once, lazily, on first read (TRL reads this after the rollout via reward_funcs).
    # A fresh env that was never `reset` (e.g. the trainer probing tool methods via
    # `inspect.getmembers`, which evaluates properties) has no sandbox/task to verify — return 0.0
    if self._env is None:
        return 0.0
    if self._reward is _NO_REWARD:
        self._reward = self._run(self._verify())
    return self._reward
```

Two implementation details worth stealing regardless of stack:

- The default reward function supports **both** trainers, `_spec.py:52-62`:

```python
def _outcome_reward_func(environments=None, environment_reward=None, **_) -> list[float]:
    """Default reward: the Harbor verifier's scalar per rollout.

    `GRPOTrainer` passes the live env instances as `environments=` (read `env.reward`); `AsyncGRPOTrainer` runs envs in
    its rollout worker and passes the already-captured per-rollout rewards as `environment_reward=`. Support both so
    the same spec plugs into either trainer.
    """
    if environment_reward is not None:
        return [float(r) for r in environment_reward]
    return [float(env.reward) for env in environments]
```

- `environment_factory` returns a `functools.partial`, **not a closure**, docstring verbatim: *"so it stays picklable — `AsyncGRPOTrainer` runs its rollout worker in a separate process and pickles the factory to it (closures/lambdas would fail)."*

Agent selection accepts a built-in name, a dotted import path `"pkg.module:Class"`, a file path `"path/to/file.py:Class"`, or a `HarborEnv` subclass directly (`_resolve_agent`, `_spec.py:64-92`). Only one built-in: `AGENTS = {"bash": HarborBashEnv}` (`_env.py:231`).

Requirements: `pip install trl[harbor]`, **Python >= 3.12**, plus a sandbox backend extra.

### 5.2 Head-to-head

| Dimension | **trl + Harbor** | **prime-rl + verifiers** |
|---|---|---|
| **Install** | `pip install trl[vllm,harbor]` from PyPI. py>=3.10 for TRL; **py>=3.12 for the Harbor path** | `verifiers` on PyPI (py>=3.11,<3.14). **`prime-rl` is not on PyPI** — install script or git + 4 submodules |
| **GPU floor** | Trainer wiring is CPU-inspectable. Realistically 1 GPU colocate (`vllm_gpu_memory_utilization=0.3`) for a 0.6B; the shipped Harbor example uses a 2+2 single-node split for Qwen3-4B | README:72: *"you need at least one NVIDIA GPU to use prime-rl."* `docs/overview.md:25`: *"Single-GPU runs are supported for debugging; production RL is typically 1× inference node + 1+ trainer nodes."* `reverse-text` example: Qwen3-0.6B, *"a single consumer GPU in a few minutes"* |
| **Tested hardware** | not stated | *"We develop and test on NVIDIA RTX 3090/4090/5090, A100, H100, H200, and B200"* |
| **Docs quality** | `docs/source/grpo_trainer.md` is ~960 lines: full math derivation of every loss type, 6 worked reward-function examples, complete Agent Training section. Harbor / OpenEnv / OpenReward each get a dedicated page | `docs/algorithms.md` is the best-written artifact in either stack **for the algorithm layer** — loss components, advantage functions, curricula, multi-turn merging. Env-authoring docs are explicitly deprioritized in favour of agent-facing skill files |
| **Maturity** | GRPO is core and stable. But `environment_factory`, `rollout_func`, and all of `trl.experimental.harbor` carry *"experimental and may change or be removed at any time without prior notice"* | Targets 1T MoE on 1000+ GPUs; per-family optimized kernels, EP, CP, FP8, PD disaggregation. verifiers v1 is a rewrite that **deleted** v0 outright |
| **Custom harness effort** | **Lowest in either stack.** A duck-typed Python class with `reset()` plus public methods. `examples/grpo_2048/grpo_2048.py` is 166 lines total *including the 2048 game engine* | Higher. TaskData + Task + Taskset (+ optional Env/Harness), pydantic configs, TOML run config, generic base classes, `vf-init` scaffolding. Real structure, real ceremony |
| **Multi-turn token correctness** | `tool_mask` built by diffing a dummy render. **Hard-raises** if the template is not prefix-preserving. Patched templates auto-swapped for Qwen3 / DeepSeek-V3 | **Renderers.** `bridge_to_next_turn(prev_prompt_ids, prev_completion_ids, new_messages)` extends the previous turn's tokens verbatim, never re-rendering history. Hand-coded for qwen3, qwen3-vl, qwen3.5, glm-5, glm-4.5, minimax-m2, deepseek-v3, kimi-k2, kimi-k2.5, nemotron-3, gpt-oss. On failure, starts a **new training sample** rather than corrupting data |
| **Observation-token policy** | masked out. No option to train on them | masked out **by default**; `algo.type = "echo"` trains on them with weighted CE, per-role, default tool bodies at `alpha = 0.1` |
| **Curriculum / dynamic sampling** | none | `StandardSampler`, `DifficultyPoolSampler` (reward-threshold pools with sampling weights), `AdvRangeGate` (rejects groups whose advantages all fall in `[reject_min, reject_max]`). Checkpointed with `state_dict`/`load_state_dict` |
| **Async / off-policy** | `trl.experimental.async_grpo.AsyncGRPOTrainer`. Needs `vllm>=0.22.0` + `transformers>=5.2.0`, **FSDP2 only (no DeepSpeed ZeRO)**. Rollout worker runs with `CUDA_VISIBLE_DEVICES=""` so GPU reward models silently fall back to CPU | Async is the design centre, not a bolt-on: `max_staleness`, version-salted prefix caches, per-env algorithms |
| **Lock-in** | **Low.** Three interchangeable env integrations (OpenEnv / OpenReward / Harbor) behind one `environment_factory` contract. Your env class is plain Python with no TRL imports | Moderate but portable *upward*: a verifiers env runs on prime-rl, Prime's Hosted Training, and the Environments Hub. Env code is reusable; the TOML trainer config is not |

### 5.3 Recommendation

> **Start on `trl` with a plain `environment_factory`. Do not adopt Harbor initially. Plan a migration trigger to prime-rl + verifiers rather than a migration date.**

Reasons, in order of weight:

1. **Harbor is orthogonal to the actual problem.** What it buys is a Docker/e2b sandbox plus a task-tree format. If the harness is not a sandboxed shell, that is pure cost: an extra dependency, Python >= 3.12, and a container spun up per rollout. `HarborSpec` fans one object into three kwargs — those three kwargs *are* the API, and you can supply them yourself.

2. **The `environment_factory` contract is two reserved methods.** `reset()` and optionally `get_reward()`. Nothing to learn, nothing to port away from. The 166-line `grpo_2048` example is the entire pattern.

3. **Single-GPU colocate vLLM works today in TRL** with no orchestrator, no TOML, no git submodules. prime-rl supports single-GPU explicitly but frames it as debugging; its whole shape assumes an inference node plus trainer nodes.

4. **`rollout_func` + `env_mask` is the lowest-lock-in escape hatch in either stack** (§3.5). If TRL's tool-call loop does not fit the harness, you can own generation entirely and hand back a mask, with no dependency on template prefix-preservation.

5. **TRL's reward surface is richer for iteration.** `trainer_state`, `log_extra`, `log_metric`, and live `environments` handles are all injected into every reward function, so dynamic shaping and instrumentation need no framework changes.

Honest counterweights, stated because they are real:

- **TRL marks `environment_factory` itself experimental.** On a multi-month project that is a genuine risk. Mitigation: keep the environment class free of any TRL import so the trainer wiring is the only breakable surface. That also makes the eventual port to verifiers mostly mechanical.
- **prime-rl's renderer design is better engineering** for exact-prefix token identity, and TRL's approach will hard-fail on templates outside its patched list rather than degrade.
- **TRL is missing DAPO's Dynamic Sampling** entirely (§6.1), which prime-rl approximates with `AdvRangeGate`. On small groups with binary rewards this is the most likely thing to stall a run.

**Switch to prime-rl + verifiers when any of these becomes true:**

- throughput on long agentic rollouts is the bottleneck and async/off-policy is needed;
- the target model's chat template is not prefix-preserving and is not on TRL's patched list;
- advantage collapse is actually observed and a curriculum or dynamic-sampling gate is required;
- multi-agent rollouts or cross-sibling judgement (best-of-N, zero-sum) are needed — `Env.finalize` has no TRL analogue;
- publishing to the Environments Hub or using Prime's Hosted Training matters.

**Confidence: moderate.** The comparison facts are all sourced; the ranking is judgement, and no measured small-scale run backs it.

---

## 6. Q4 — Known failure modes

### 6.1 Advantage collapse — all group samples score identically

**Symptom.** `frac_reward_zero_std` climbs; the effective batch shrinks; loss is nonzero but learning stalls. TRL logs this metric at `grpo_trainer.py:2857`.

**Cause.** DAPO §3.2 (arXiv:2503.14476v2), verbatim:

> Existing RL algorithm suffers from the gradient-decreasing problem when some prompts have accuracy equal to 1. For example for GRPO, if all outputs {o_i} of a particular prompt are correct and receive the same reward, the resulting advantage for this group is zero. A zero advantage results in zero policy gradients, shrinking the magnitude and increasing the noise sensitivity of the batch gradient, thereby degrading sample efficiency. Empirically, the number of samples with accuracy equal to 1 continues to increase... This means that the effective number of prompts in each batch keeps decreasing, which can lead to larger variance in gradient and dampens the gradient signals for model training.

This is **the** failure mode for small-scale binary-reward agentic training. With `num_generations=8` on a task the model either always fails or always solves, most groups are dead.

**Published mitigation — Dynamic Sampling.** DAPO §3.2, verbatim:

> To this end, we propose to over-sample and filter out prompts with the accuracy equal to 1 and 0, leaving all prompts in the batch with effective gradients and keeping a consistent number of prompts. The sampling cost for each batch is dynamic. Before training, we keep sampling until the batch is fully filled with samples whose accuracy is neither 0 nor 1.

And on cost, §5, verbatim: *"When applying Dynamic Sampling, although more data needs to be sampled due to the filtering out of zero-gradient data, the overall training time is not significantly affected."*

**Implementation status — this is the important finding:**

- **Not implemented in TRL.** No dynamic sampling, no zero-variance filtering.
- Two community attempts exist and **both were closed without merging.** Verified via `api.github.com/repos/huggingface/trl/pulls/{6368,7068}` returning `merged: false, merged_at: null`, and neither identifier appears in `main`'s `grpo_config.py`:

  - **PR #6368** (2026-07-13) proposed `loss_type="dapo_zv"` — identical to `dapo` except the loss denominator excludes tokens from zero-variance groups. Rationale, verbatim: *"Dividing by a token count that includes zero-signal rows silently shrinks the effective learning rate on the rows that DO carry signal, in proportion to how many groups are tied this step."* Reported result, GSM8K / Qwen2.5-1.5B-Instruct, step 100, n=500, greedy eval:

    | Setup | Accuracy | Denominator |
    |---|---|---|
    | `loss_type="dapo"` (binary reward) | 0.536 | all tokens, including dead groups |
    | `loss_type="dapo_zv"` (binary reward) | **0.560** | dead-group tokens excluded |
    | `loss_type="dapo"` (dense reward model) | 0.590 | rarely hits zero-variance, so rarely diluted |

    *"Fixing only the denominator (no reward change) recovered 2.4 points accuracy."* Cites AGPO, arXiv:2503.15952.

  - **PR #7068** (2026-09-05) proposed `mask_zero_advantage_groups`. Verbatim: *"when `beta > 0` and every completion in a reward group gets the same reward, the group's advantage is exactly zero, so the policy loss term drops out — but the per-token KL penalty still applies regardless of the advantage, so the group still contributes a gradient."* Cites arXiv:2505.22257 §3.2. Closed as *"expected GRPO behavior rather than a bug."* The PR also notes RLOO does **not** need the fix, because it folds KL into the reward before computing `std_rewards`.

- **prime-rl ships the equivalent** as `AdvRangeGate`, docs verbatim: *"rejects a group when every trainable-token advantage falls inside `reject_min` through `reject_max`."* Plus `DifficultyPoolSampler` for reward-threshold-weighted task sampling.

**What to do today in TRL:** raise `num_generations`; curate task difficulty so the pass rate sits away from 0 and 1; keep `beta = 0.0` (the default) so zero-variance groups contribute literally nothing rather than a spurious KL gradient. If collapse is measured and persistent, that is the migration trigger to prime-rl.

**Confidence: strong**, including the negative result on merge status (verified twice, via the pulls API and a `main` grep).

---

### 6.2 Length bias — length collapse and length explosion

**Symptom.** Completion length drifts upward over training, especially on *incorrect* rollouts; or short completions are systematically favoured.

**Cause.** The `1/|o_i|` per-sequence normalization in the original GRPO loss. Dr. GRPO (arXiv:2503.20783v2), abstract verbatim:

> Additionally, we identify an optimization bias in Group Relative Policy Optimization (GRPO), which artificially increases response length (especially for incorrect outputs) during training. To address this, we introduce Dr. GRPO, an unbiased optimization method that improves token efficiency while maintaining reasoning performance.

TRL's own docs (`grpo_trainer.md:135`) state the DAPO fix is partial: *"while the DAPO formulation reduces this bias, it does not eliminate it completely."*

The three formulations, from `docs/source/grpo_trainer.md:113-145`:

```
GRPO:     L = -(1/G)  Σ_i (1/|o_i|) Σ_t l_{i,t}          # per-sequence mean  -> length bias
DAPO:     L = -(1/Σ|o_i|)  Σ_i Σ_t l_{i,t}               # global token mean  -> reduces it
Dr.GRPO:  L = -(1/(L·G))   Σ_i Σ_t l_{i,t}               # constant L = max_completion_length -> removes it
```

Config help for `loss_type` (`grpo_config.py:796-830`), verbatim on `grpo`:

> `'grpo'`: Aggregates token-level losses by normalizing over sequence length. **Not recommended due to length bias** — this approach tends to prefer shorter completions with positive advantages and longer ones with negative advantages.

**Mitigations, all shipped in v1.13.0:**

| Mitigation | Setting | Code |
|---|---|---|
| Global token-count normalization (DAPO) | `loss_type="dapo"` — **already the default** | `grpo_config.py:796`; loss at `grpo_trainer.py:3260-3266` |
| Constant normalization (Dr. GRPO) | `loss_type="dr_grpo"` | `grpo_trainer.py:3256-3258`: `loss = (per_token_loss * mask).sum() / (per_token_loss.size(0) * self.max_completion_length)` |
| Drop std scaling | `scale_rewards="none"` | `grpo_config.py:784-795`, verbatim: *"The Dr. GRPO paper recommends not scaling rewards, as scaling by the standard deviation introduces a question-level difficulty bias."* Default is `"group"` |
| Local-batch normalization | `loss_type="bnpo"` | `grpo_trainer.py:3251-3254` |
| Length-unbiased sequence loss | `loss_type="luspo"` (LUSPO) — requires `importance_sampling_level="sequence"`, TRL warns otherwise at `:908-913` | `grpo_trainer.py:3268-3276` |
| Reward-side length penalty | prime-rl `length_penalty` | `linear` subtracts a `pass_rate`-scaled penalty combining output tokens (`num_output_tokens_weight`), input/context tokens (`num_input_tokens_weight`, default 0.1) and turns (`num_turns_weight`, default 0.1), **each normalized by the group's own max**, applied *before* the GRPO baseline |

Theoretical limit surfaced by search but **not read**: arXiv:2601.03703, *"On the Impossibility of Unbiased and Length-Invariant Policy Optimization with Outcome Rewards"* (2026). Title only. **Speculative.**

**Confidence: strong** for the mechanisms and TRL implementations.

---

### 6.3 Entropy collapse

**Symptom.** Policy entropy drops rapidly; group samples become near-identical; exploration dies; the run plateaus early.

**Cause.** DAPO §3.1, verbatim:

> In our initial experiments using naive PPO or GRPO, we observed the entropy collapse phenomenon: the entropy of the policy decreases quickly as training progresses. The sampled responses of certain groups tend to be nearly identical. This indicates limited exploration and early deterministic policy, which can hinder the scaling process.

The sharper diagnosis is arXiv:2509.26114, *"Clip-Low Increases Entropy and Clip-High Decreases Entropy in Reinforcement Learning of Large Language Models"* (2025). Abstract, verbatim:

> we reveal that the clipping mechanism in PPO and GRPO induces biases on entropy. Through theoretical and empirical analyses, we show that clip-low increases entropy, while clip-high decreases it. Further, **under standard clipping parameters, the effect of clip-high dominates, resulting in an overall entropy reduction even when purely random rewards are provided to the RL algorithm.** Our findings highlight an overlooked confounding factor in RLVR: independent of the reward signal, the clipping mechanism influences entropy, which in turn affects the reasoning behavior.

That is worth reading twice: **entropy collapses even under random rewards.** It is a property of the optimizer, not of the task.

**Mitigations, all in v1.13.0:**

| Mitigation | Setting | Line |
|---|---|---|
| **Clip-Higher** (DAPO §3.1) — decouple the clip bounds | `epsilon=0.2`, `epsilon_high=0.28` | `grpo_config.py:688`, `:700`. Config help: *"Paper DAPO recommends 0.28"*; DAPO §4 confirms those exact values |
| Entropy bonus | `entropy_coef` | `grpo_config.py:871` |
| Adaptive entropy targeting | `use_adaptive_entropy`, `entropy_coef_min`, `entropy_coef_max`, `entropy_coef_delta`, `entropy_target` | `grpo_config.py:881`, `:889`, `:893`, `:897`, `:901` |
| High-entropy token selection | `top_entropy_quantile` | `grpo_config.py:861`; `get_high_entropy_mask` at `grpo_trainer.py:1413-1450` |
| Soft gating instead of hard clipping | `loss_type="sapo"` (arXiv:2511.20347) | `grpo_trainer.py:3214-3217` |

`entropy` is logged every step (`grpo_trainer.py:3363`). Watch it from step 1.

DAPO's operational guidance, §Appendix, verbatim: *"the model's entropy needs to be maintained within an appropriate range. An excessively low entropy indicates that the probability distribution is overly sharp, leading to a loss of exploration capability. Conversely, an excessively high entropy is often associated with issues of over-exploration such as gibberish and repetitive generation... we find that maintaining a slow upward trend in entropy is conducive to the improvement of model performance."*

**Confidence: strong.**

---

### 6.4 KL divergence blowup

**Symptom.** The KL term dominates the loss, or the policy drifts far from the reference and destabilizes.

**The practical fact first:** in TRL v1.13.0, `beta` defaults to **`0.0`** (`grpo_config.py:676`). Config help verbatim: *"KL coefficient. If `0.0` (default), the reference model is not loaded, reducing memory usage and improving training speed."* So by default **there is no KL term and no reference model in memory.** This is both the largest small-scale memory saving available and the reason KL blowup is not a default-configuration failure mode.

When enabled, the k3 estimator is used, `grpo_trainer.py:3191-3198`:

```python
if self.beta != 0.0:
    ref_per_token_logps = inputs["ref_per_token_logps"]
    per_token_kl = (
        torch.exp(ref_per_token_logps - per_token_logps) - (ref_per_token_logps - per_token_logps) - 1
    )
    # Importance sampling correction for the KL divergence
    if self.args.use_bias_correction_kl:
        per_token_kl = per_token_kl * coef_1
```

Added to the per-token loss at `:3242-3243`.

**Mitigations:**

- Keep `beta = 0.0`. If a KL anchor is needed, the config help cites DeepSeek-R1 (arXiv:2501.12948) using `0.001`.
- `sync_ref_model` + `ref_model_mixup_alpha` + `ref_model_sync_steps` (`grpo_config.py:839`, `:846`, `:854`) periodically move the reference toward the policy, capping the achievable divergence.
- `use_bias_correction_kl` (`:967`) multiplies KL by the IS ratio. Open PR **#7188** *"[GRPO] Multiply the KL term by the per-token importance sampling ratio"* proposes making this standard.
- Two-sided clipping via `delta` (`:692`, INTELLECT-2 arXiv:2505.07291) bounds the ratio from above, *"Recommended to be greater than 1 + ε when enabled."*
- `off_policy_mask_threshold` (`:958`) drops tokens that have drifted too far.

**Interaction bug to know:** with `beta > 0`, zero-advantage groups still emit a KL gradient (PR #7068, §6.1). Another reason to leave `beta` at 0.

**Confidence: strong.**

---

### 6.5 Truncation bias in long rollouts

Two distinct problems share this name. Both matter specifically because agentic rollouts are long.

#### (a) Truncated-completion reward noise

**Symptom.** A rollout cut off at `max_completion_length` is scored as a failure even though it was on track. The model learns to be short rather than correct.

**Cause.** DAPO §3.4, verbatim:

> In RL training, we typically set a maximum length for generation, with overlong samples truncated accordingly. We find that improper reward shaping for truncated samples can introduce reward noise and significantly disrupt the training process.

**Published mitigation.** DAPO §3.4, verbatim:

> To investigate the impact of this reward noise, we first apply an Overlong Filtering strategy which masks the loss of truncated samples. We find that this approach significantly stabilizes training and enhances performance.

DAPO's full version also adds a **soft length penalty** over a buffer zone: expected max length 16,384 tokens with an additional 4,096-token *"soft punish cache"*, so hard truncation is at 20,480.

**Implementation in TRL:** `mask_truncated_completions` (`grpo_config.py:831`, **default `False`**), implemented at `grpo_trainer.py:2508-2517`. Config help verbatim: *"When enabled, truncated completions are excluded from the loss calculation, preventing them from being incorrectly penalized and introducing noise during training. According to the DAPO paper, this is a good practice for training stability."*

Critically, it masks `tool_mask` as well as `completion_mask` — source comment at `:2515`: *"Also mask tool_mask for consistency in multi-turn training."*

TRL implements only the masking half. The soft length penalty has no TRL equivalent; prime-rl's `length_penalty` is the nearest thing.

> **Action: set `mask_truncated_completions=True` for any long agentic run.** It is off by default and it is the cheapest stability win available.

#### (b) Sampling-support truncation bias in the vLLM importance ratio

Newer, subtler, and specific to `use_vllm=True` + `vllm_importance_sampling_correction=True`.

Open issue **#6789** (2026-08-18), verbatim:

> When `top_p < 1`, `top_k > 0` or `min_p` is set, GRPO's vLLM importance-sampling correction compares two log-probabilities computed over **different distributions**, so the ratio is biased. vLLM returns log-probs renormalized over the truncated (nucleus) distribution, while the trainer recomputes them over the full vocabulary. [...] `processed_logprobs` means "after every logits processor", which includes top-p/top-k truncation followed by renormalization over the surviving tokens. Temperature is handled symmetrically [...]; truncation is not. For a sampled token that survives the nucleus, vLLM's log-prob is therefore *higher* than the trainer's by `-log(sum of surviving probability mass)`, which is a per-token, systematically negative bias in `log π_θ - log π_behaviour`.

Open PR **#7269** (2026-09-18) measured it. Qwen2.5-1.5B-Instruct, vLLM 0.28, 2,048 tokens per row, temperature 1.0, trainer side HF bf16:

| sampling | kept mass | ratio (full-vocab trainer logprobs): mean / median / % outside [0.9, 1.1] | ratio (renormalized over replayed support) |
|---|---|---|---|
| `top_p=0.8, top_k=1024` | 0.895 | 0.896 / 0.895 / **51.8%** | 1.001 / 1.000 / 4.3% |
| `top_k=20` | 0.965 | 0.965 / 0.995 / 16.2% | 1.000 / 1.000 / 6.2% |
| `top_p=1.0, top_k=1024` (control) | 0.994 | 0.995 / 1.000 / 6.9% | 1.000 / 1.000 / 5.9% |

PR verbatim: *"The full-vocabulary mean equals the kept mass; the residual after renormalisation is the ordinary engine-vs-trainer noise of the control row."*

The proposed fix, `GRPOConfig.vllm_importance_sampling_support`, relies on vLLM >= 0.28's `return_sampling_mask`. **It is not in v1.13.0 and not in `main`** — verified by grep.

> **Action:** with vLLM IS correction enabled, keep `top_p=1.0` and `top_k=-1`/`0` and control diversity with temperature alone. TRL's defaults are already `top_p=1.0` (`grpo_config.py:531`) and `top_k=0` (`:538`), so the default configuration is safe — but these are exactly the knobs people reach for first.

Related open issues: **#6688** *"Support status and numerical safety of GRPO + vLLM + bf16 LoRA for long multi-turn tool [use]"*, **#7039** *"GRPO: honor every EOS id declared in generation_config"*.

**Confidence: strong** — both sourced from the tracker with reproduced measurements.

---

### 6.6 Reward hacking

**Symptom.** Reward climbs steadily; held-out task performance does not.

**Documented state in TRL: there is no built-in detector, and the request for one was closed.** Issue **#6350** (2026-07-10) asked for callbacks tracking KL-vs-reference acceleration, entropy-collapse trend, and advantage-distribution drift (Wasserstein vs a rolling baseline). The requester's own finding, verbatim:

> the honest finding is they reliably audit hacking after the fact but don't reliably give early warning at a usable false-positive rate

**Treat KL/entropy dashboards as forensics, not as an alarm.** That is the single most useful sentence I found on this topic.

**What TRL does ship:** the unscorable-row defense. A rollout where every reward function returned `None` becomes `NaN`, then advantage `0` (`grpo_trainer.py:2834-2836`), rather than reward `0.0`, which would be a real signal that drags the group baseline. Related PRs porting the same defense elsewhere: #6426, #6429 (SDPO), #6427 (OpenReward — *"Return None for unrewarded rollouts to prevent default-0.0 advantage poisoning"*).

**Literature** (titles/abstracts only, not read in full): arXiv:2509.15557 *"Reward Hacking Mitigation using Verifiable Composite Rewards"*; arXiv:2604.16242 *"Detecting and Suppressing Reward Hacking with Gradient Fingerprints"*.

**Practical defenses that do not depend on a detector** (§7 expands these): verify artifacts rather than transcripts; instrument turn count / tool-failure count / answer-file presence as **metrics** and watch them diverge from reward; return `None` rather than `0.0` for unscorable rollouts.

**Confidence: strong** on TRL's state. **Moderate** on mitigations.

---

### 6.7 Multi-turn-specific instability (the most on-topic paper)

**arXiv:2511.20718v2 — *Stabilizing Off-Policy Training for Long-Horizon LLM Agent via Turn-Level Importance Sampling and Clipping-Triggered Normalization*** (2025). Abstract, verbatim:

> Reinforcement learning (RL) algorithms such as PPO and GRPO are widely used to train large language models (LLMs) for multi-turn agentic tasks. However, in off-policy training pipelines, these methods often exhibit unstable optimization dynamics and are prone to performance collapse. Through empirical analysis, we identify two fundamental sources of instability in this setting: (1) a granularity mismatch between token-level policy optimization and turn-structured interactions, and (2) high-variance and unreliable gradient updates induced by off-policy importance sampling and inaccurate advantage estimation. To address these challenges, we propose SORL... we instantiate two stabilized algorithms: SO-PPO and SO-GRPO. Both algorithms are designed to mitigate gradient variance and prevent optimization collapse without requiring careful early stopping or heuristic tuning... Experimental results show that both methods consistently prevent training instabilities and performance collapses observed in standard PPO and GRPO, maintain lower clipping ratios and more stable optimization trajectories.

Point (1) — **granularity mismatch between token-level optimization and turn-structured interaction** — is precisely the gap that TRL's flat-sequence + `tool_mask` representation leaves open. TRL masks tool tokens out but still optimizes at token granularity across a multi-turn trajectory; nothing aligns credit to turn boundaries.

Partial hedges available in TRL today: `importance_sampling_level="sequence"` (GSPO) moves granularity up from token to sequence, though not to *turn*. Nothing implements turn-level IS.

Related, unimplemented in either stack: arXiv:2510.06214 *"Stratified GRPO: Handling Structural Heterogeneity in Reinforcement Learning of LLM Search Agents"* (2025).

**Confidence: strong** that the paper exists and makes these claims. **Moderate** on replication.

---

### 6.8 Variant summary — what each claims to fix, and whether TRL has it

| Method | arXiv | Year | Claimed fix | In trl 1.13.0? |
|---|---|---|---|---|
| **GRPO** (DeepSeekMath) | 2402.03300 | 2024 | Origin. Critic-free; group-relative baseline replaces the value model | baseline (`loss_type="grpo"`) |
| **DAPO** | 2503.14476 | 2025 | Four fixes: **Clip-Higher** (entropy collapse), **Dynamic Sampling** (zero-advantage groups), **Token-Level Loss** (length bias), **Overlong Reward Shaping** (truncation noise). 50 pts AIME'24 on Qwen2.5-32B base | **3 of 4.** `loss_type="dapo"` (default), `epsilon_high`, `mask_truncated_completions`. **Dynamic Sampling absent** |
| **Dr. GRPO** | 2503.20783 | 2025 | Removes the length bias that *"artificially increases response length (especially for incorrect outputs)"*. 43.3% AIME'24 with a 7B base | `loss_type="dr_grpo"`, `scale_rewards="none"` |
| **GSPO** | 2507.18071 | 2025 | Sequence-level importance ratio + sequence-level clipping. *"notably stabilizes Mixture-of-Experts (MoE) RL training"*. Behind Qwen3 | `importance_sampling_level="sequence"` |
| **CISPO** (MiniMax-M1) | 2506.13585 | 2025 | *"clips importance sampling weights rather than token updates, outperforming other competitive RL variants"* | `loss_type="cispo"` |
| **INTELLECT-2** | 2505.07291 | 2025 | Two-sided clip upper bound δ; decentralized async RL at 32B | `delta` |
| **ScaleRL** | 2510.13786 | 2025 | ε_max ≈ 5.0 recommended for CISPO | cited in `epsilon_high` help text |
| **SAPO** | 2511.20347 | 2025 | Soft temperature-controlled gate replacing hard clipping; asymmetric τ_neg (1.05) > τ_pos (1.0) | `loss_type="sapo"` |
| **AGPO** | 2503.15952 | 2025 | Zero-variance-aware loss denominator + token efficiency | **no** (PR #6368 closed unmerged) |
| **Revisiting GRPO** | 2505.22257 | 2025 | Zero-variance group masking, §3.2 | **no** (PR #7068 closed unmerged) |
| **LUSPO** | 2602.05261 \* | 2026 | Length-unbiased sequence-level loss; scales each sequence's loss by its length | `loss_type="luspo"` |
| **VESPO** | 2602.10693 \* | 2026 | Smooth asymmetric Gamma weighting on sequence-level IS weights instead of hard clipping | `loss_type="vespo"` |
| **SORL / SO-GRPO** | 2511.20718 | 2025 | Turn-level importance sampling + clipping-triggered normalization for multi-turn agents | **no** |
| **Stratified GRPO** | 2510.06214 | 2025 | Structural heterogeneity in LLM search agents | **no** |
| **Clip-Low/Clip-High analysis** | 2509.26114 | 2025 | Diagnosis, not an algorithm: clipping shifts entropy independent of reward | informs `epsilon` / `epsilon_high` tuning |
| **MaxRL** | 2602.02710 \* | 2026 | Normalize by group **mean** not std; unbiased for the order-`group_size` truncation of the ML objective | no (prime-rl `algo.type="max_rl"`) |
| **RAE** (SPIRAL) | 2506.24119 \* | 2025 | Per-agent EMA baseline for multi-agent self-play | no (prime-rl `algo.type="rae"`) |

\* IDs marked with an asterisk were read from TRL's or prime-rl's own documentation and **were not independently resolved** against the arXiv API. Every unmarked ID in this table was verified (16/16).

TRL's full `loss_type` enumeration (`grpo_config.py:796`): `grpo`, `dr_grpo`, `dapo` (default), `bnpo`, `cispo`, `sapo`, `luspo`, `vespo`.

---

## 7. Q5 — Reward design for long-horizon agentic tasks

### 7.1 Start sparse and outcome-based

Both production stacks default to a single terminal scalar. Harbor's entire default reward is `_outcome_reward_func` (`trl/experimental/harbor/_spec.py:52-62`) reading one float off `env.reward`, which is itself *"the agent wrote `/workdir/answer.txt` during the rollout; the verifier reads it"* (`_env.py:87`), computed lazily exactly once.

Dense process reward is an optimization applied **after** a sparse outcome reward is demonstrably learnable, not a starting point. Adding dense shaping first means you cannot tell whether a plateau is a task problem or a reward problem.

### 7.2 Split trainer-owned from environment-owned reward — and mind the weighting asymmetry

TRL docs (`grpo_trainer.md:864-871`), verbatim:

> Environment-owned and trainer-owned rewards are not exclusive. Pass `reward_funcs` for rewards that are natural to compute from the completion (e.g. a format check on the text) *and* let the environment return its state-dependent reward through `get_reward`. All sources are summed; **`reward_weights` applies to the `reward_funcs` only (the environment owns its own scale).**

That bolded clause is a live footgun. Your environment reward is **not** weight-normalized alongside the others; it enters the sum at weight 1 with whatever scale `get_reward` returns. If `get_reward` returns a score in [0, 100] and your format reward returns [0, 1], the format signal is noise.

Also documented: *"A `reward_func` can also read environment state directly: when `environment_factory` is set, the trainer passes an `environments` kwarg (one instance per completion). This is occasionally useful, but for state-dependent rewards prefer `get_reward`."*

### 7.3 Verify the artifact, not the transcript

verifiers' authoring skill, verbatim:

> - Prefer deterministic verification grounded in the task's actual artifact or answer.
> - Use an LLM judge only when semantic judgment is unavoidable.

This is the strongest single defense against reward hacking, because it removes the hackable surface rather than trying to detect exploitation of it. A reward that shells `test -e /workdir/answer.txt` and diffs the contents (`bash_interception/taskset.py`) cannot be talked into a high score by a persuasive transcript. A reward that reads the model's own claim of success can.

Concretely: prefer **filesystem state**, **exit codes**, **test-suite results**, **parsed structured output compared to ground truth** over **LLM judges** and over **anything the model writes about its own work**.

### 7.4 Instrument with metrics before you shape with rewards

Both stacks separate observability from reward:

- verifiers: `@vf.metric` is unweighted and excluded from `trace.reward` by construction.
- TRL: `log_metric` and `log_extra` are injected into every reward function's kwargs (`grpo_trainer.py:1649-1652`).

**Instrument first, shape second.** Log as metrics: turn count, tool-call count, tool-failure count, answer-artifact presence, per-tool usage histogram, truncation rate. If reward climbs while these diverge from what task success should look like — turn count collapsing to 1, tool-failure count climbing, answer file absent — that is your hacking signal, and it is far more specific than KL or entropy drift (§6.6).

### 7.5 Shape length on the reward, not in the loss normalizer

TRL's length handling lives in the loss denominator (`loss_type`). prime-rl puts it on the reward instead: `length_penalty` with a `linear` mode subtracting a `pass_rate`-scaled term combining output tokens, input/context tokens (default weight 0.1) and turns (default weight 0.1), **each normalized by the group's own max for that quantity**, applied *before* the GRPO baseline.

The per-group normalization is what makes this work. Absolute length penalties fight the task; a penalty relative to what sibling rollouts on the *same* task spent is a clean "be more efficient than your peers" signal, and it is exactly the shape group-relative methods want. The `pass_rate` scaling means it only bites once the task is being solved — you do not penalize length while the model is still failing.

### 7.6 Two exploits to close before the first run

**(a) Truncation-as-failure.** A long, correct, on-track rollout scored 0 because it hit `max_completion_length` teaches shortness, not correctness — and on agentic tasks, truncation correlates with *harder* tasks, so you are actively training away from the tasks you care about. Fix: `mask_truncated_completions=True` (§6.5a).

**(b) Unscorable-as-zero.** A rollout your verifier could not score (sandbox died, parse failed, timeout) scored `0.0` is a **real negative signal** that drags the group baseline and makes surviving rollouts look better than they are. TRL's convention:

> **Return `None`, not `0.0`, for unscorable rollouts.**

`None` → `NaN` (`grpo_trainer.py:1685`) → advantage `0` (`:2834-2836`), source comment verbatim: *"Unscorable completions (every reward func returned None) carry no learning signal: their reward is NaN here, so zero their advantage to keep them from moving the policy."* TRL also warns at `:1728-1736` when every function returns `None` for a row, printing the offending kwargs. Encode this convention in every reward function on day one; it is invisible until it has already skewed a week of training.

### 7.7 Process reward, if you must

Entry points (titles/abstracts read, bodies not):

- **arXiv:2510.08049** — *A Survey of Process Reward Models: From Outcome Signals to Process Supervisions for Large Language Models* (2025). The survey to start from.
- **arXiv:2509.25598** — *Hybrid Reward Normalization for Process-supervised Non-verifiable Agentic Tasks* (2025). Directly on non-verifiable agentic tasks.
- **arXiv:2510.11967** — *Scaling Long-Horizon LLM Agent via Context-Folding* (2025). For horizons where the trajectory exceeds context.
- **arXiv:2504.15275** — *Stop Summation: Min-Form Credit Assignment Is All Process Reward Model Needs for Reasoning* (surfaced by search; title only).

**Confidence: moderate** on applicability — I read abstracts, not bodies.

### 7.8 A structural alternative to dense reward: train on observation tokens

prime-rl's **ECHO** algorithm (`algo.type = "echo"`) adds a weighted cross-entropy loss on environment-provided tokens already present in the rollout, selected by message role. Default: tool-response bodies at `alpha = 0.1` (the paper's λ). Configurable per role:

```toml
[orchestrator.algo]
type = "echo"

[orchestrator.algo.roles.tool]
alpha = 0.25

[orchestrator.algo.roles.user]
alpha = 0.05
```

It also accepts a token filter to narrow the selection — e.g. dropping warning lines from tool output:

```python
# sees the raw rollout (message text, sampling logprobs);
# returns one keep-mask per trainable branch, spanning that branch's token_ids.
def drop_warnings(rollout, *, patterns: list[str]) -> list[list[bool]]: ...
```

This extracts learning signal from tool output **without inventing a process reward** — no reward model to overfit, no shaping term to hack. There is no TRL equivalent; TRL always masks observation tokens out (§3).

**Confidence: strong** that it exists and works as documented. **Speculative** on whether it helps any particular task.

---

## 8. Copy-ready snippet locations

Ranked by usefulness for building a custom harness. All paths relative to `/tmp/rl-research/trl-1.13.0/` or `/tmp/rl-research/verifiers-main/`.

1. **`examples/grpo_2048/grpo_2048.py`** (166 lines) — **the one to copy.** A complete self-contained `environment_factory` with zero external dependencies: `class Game2048Env` at `:37`, `reset()` at `:38`, the `move()` tool at `:46`, private helpers `_spawn`/`_merge_line`/`_apply_move`/`_can_move`/`_render` at `:65-146`, and the full trainer wiring at `:147-159` (`reward_funcs=reward_score`, `environment_factory=Game2048Env`). This is the entire pattern including a game engine.

2. **`examples/grpo_harbor/harnesses/terminal_notes/env.py`** (221 lines) — **the multi-tool template.** A `HarborEnv` subclass exposing 10 tools: 6 shell (`shell_exec` with a `blocking` flag for background processes, `shell_write_content_to_file`, `shell_write_to_process`, `shell_view`, `shell_wait`, `shell_kill_process`) plus a 4-tool in-env note system (`create_note`, `append_note`, `read_note`, `list_note`). Shows: exactly the docstring format the schema generator accepts; per-rollout state (`self._notes`, `self._bg`) cleared in `reset()`; a `PROMPT_SUFFIX` class attribute; base64 round-tripping to write files safely through a shell. Its `README.md` is a good model for documenting a tool surface as a table.

3. **`examples/grpo_wordle/grpo_wordle.py`** (280 lines) + `grpo_wordle.ipynb` — larger stateful game environment with a notebook walkthrough.

4. **`examples/grpo_seta/grpo_seta.py`** (130 lines) — smallest Harbor-flavoured example.

5. **`examples/grpo_harbor/grpo_harbor.py`** — copy the **launch invocation only** (module docstring, lines 27-42). It has the exact two-terminal single-node 2+2 GPU split, including flags that are not obvious and not defaulted:

```sh
# Terminal 1 — vLLM
CUDA_VISIBLE_DEVICES=2,3 VLLM_SERVER_DEV_MODE=1 vllm serve Qwen/Qwen3-4B --tensor-parallel-size 2 --port 8000 \
    --weight-transfer-config '{"backend": "nccl"}' \
    --logprobs-mode processed_logprobs \
    --max-logprobs -1

# Terminal 2 — training
CUDA_VISIBLE_DEVICES=0,1 accelerate launch \
    --config_file examples/accelerate_configs/deepspeed_zero2.yaml --num_processes 2 \
    examples/grpo_harbor/grpo_harbor.py \
    --vllm-mode server --vllm-server-base-url http://localhost:8000 --env e2b
```

   Its defaults are also a reasonable starting config: `learning_rate=1e-6`, `per_device_train_batch_size=8`, `num_generations=8`, `max_completion_length=2048`, `max_steps=50`, `max_tool_calling_iterations=25`, `chat_template_kwargs={"enable_thinking": False}`, `vllm_gpu_memory_utilization=0.3` (colocate).

6. **`trl/experimental/harbor/_spec.py`** — read two things: `_outcome_reward_func` at `:52-62` (the dual-signature reward that works under both `GRPOTrainer` and `AsyncGRPOTrainer`), and the `environment_factory` property returning a `functools.partial` *"so it stays picklable"*. Async training requires the latter.

7. **`docs/source/grpo_trainer.md:416-660`** — six worked reward functions: length (token- and character-based), format checking, reference-answer comparison, multi-task routing, asynchronous, and logging extra columns/metrics.

8. **`docs/source/grpo_trainer.md:774-940`** — the `IncrementEnv` minimal environment, the external-dataset variant, the multi-environment routing example, and the env-vs-trainer reward composition example.

9. **verifiers: `environments/bash_interception/bash_interception/taskset.py`** — the tightest real example of `@vf.stop` + `@vf.intercept` + `@vf.reward` in one class, with a reward that shells into the live runtime to check a filesystem sentinel.

10. **verifiers: `skills/create-environments/SKILL.md`** — the `AdditionTaskset` minimal package (quoted in §4.3), the ownership rules, and the scoring rules. Better than the human-facing docs.

11. **prime-rl: `examples/basic/reverse-text/`** — the *"single consumer GPU in a few minutes"* Qwen3-0.6B tiny-scale SFT + RL example, with `rl.toml` / `sft.toml` / `eval.toml`. The smallest complete prime-rl run.

Other TRL examples not inspected in detail but available: `grpo_browsergym`, `grpo_carla`, `grpo_catch`, `grpo_sudoku`, `grpo_multi_env`, `grpo_echo`, `grpo_sql_agent`, `grpo_qlora`, `grpo_continuous_batching`, `grpo_visual_math`, `grpo_qwen3_vl`, `grpo_ministral3_vl`, `grpo_rnj_1_instruct`, `async_grpo_math`, `async_grpo_opencode`.

---

## 9. Confidence summary

**Strong** — everything read directly from source or verified against an API:

- Every TRL API signature, line number, config field, default value, and the complete loss-masking chain (§3), from the v1.13.0 release tarball.
- The `verifiers` v1 authoring API: base classes, decorators, DI mechanism, ownership rules, package contract.
- All 16 primary arXiv IDs, re-resolved via `id_list=`.
- The five GitHub issues/PRs quoted, **including the unmerged status of #6368 and #7068**, verified twice (pulls API `merged: false`, plus grep of `main`).
- DAPO's four techniques, quoted from the paper body (`arxiv.org/html/2503.14476v2`), not the abstract.
- Package versions and Python requirements from PyPI JSON.
- prime-rl's algorithm table, curriculum components, and multi-turn merging semantics, from `docs/algorithms.md`.

**Moderate** — sourced facts, but the synthesis is judgement:

- The stack recommendation (§5.3) and its migration triggers.
- Relative maturity and forward-stability of the two stacks.
- Whether variant papers' claimed improvements replicate at small scale on agentic tasks.
- The process-reward literature (§7.7) — abstracts read, bodies not.

**Speculative** — cited by title only, not resolved or read:

- arXiv:2601.03703 (length-invariance impossibility), 2604.16242 (gradient fingerprints), 2509.15557 (verifiable composite rewards).
- LUSPO (2602.05261) and VESPO (2602.10693) arXiv IDs, taken from TRL's config help text rather than the arXiv API.
- MaxRL (2602.02710) and RAE/SPIRAL (2506.24119) IDs, taken from prime-rl's docs.

---

## 10. Known gaps

1. **No empirical small-scale numbers.** Nothing here is a measured GRPO run at 1-2 GPUs on a stated model size. The only quantitative results found are PR #6368's GSM8K/Qwen2.5-1.5B accuracy delta (0.536 → 0.560) and PR #7269's IS-ratio bias table. **No memory footprint, no tokens/sec, no wall-clock for a multi-turn rollout, no minimum viable GPU for a given model size.** This is the largest gap and the most likely thing to invalidate a plan.

2. **`harbor` itself was never fetched.** TRL imports it lazily; I read only TRL's wrapper. The `task.toml` schema, the verifier semantics, sandbox-backend behavior and cost, and container startup latency per rollout are all unknown. Given that `environment_type` defaults to `"docker"` and one container is created per rollout, startup cost could dominate at small scale — unmeasured.

3. **The verifiers → prime-rl seam was not traced.** I read both sides but not the adapter that turns a `vf.Episode` into a `TrainingSample`, nor how advantages and loss weights ride on verifier nodes through admission.

4. **`_generate_and_score_completions` (`grpo_trainer.py:2347-2963`, ~600 lines) was not read end to end.** I read its masking, advantage-computation, and logging sections in full. Generation-batch scheduling, the vLLM colocate-vs-server split, multimodal/VLM handling, and weight-sync are unverified.

5. **The renderer claim is documented, not tested.** prime-rl's exact-prefix guarantee via `bridge_to_next_turn` is read from `docs/algorithms.md`. Their canonical reference is a blog post (`primeintellect.ai/blog/renderers`) I did not fetch, and I ran no token-identity comparison myself.

6. **`HarborEnv._verify()` (`_env.py:162`) body unread.** I saw the signature and the lazy `reward` property that calls it. How a Harbor task's pass/fail becomes a float is unconfirmed.

7. **AsyncGRPOTrainer read at doc level only.** I did not read `trl/experimental/async_grpo/`. The pickling constraints, `max_staleness` semantics, and the CPU-only rollout-worker limitation are quoted from `docs/source/async_grpo_trainer.md`, not verified in source.

8. **`WebSearch` was unavailable** (broken in this environment, per the lane brief), so there are **no practitioner blog posts, forum threads, W&B reports, or informal "what actually happened when I ran this" accounts** in this report. Everything above is source code, the arXiv API, the GitHub API, or official documentation. The practitioner layer — where small-scale reality usually diverges from papers — is entirely missing.

9. **The `num_generations` / batch-size divisibility constraints were not pinned down.** I grepped for the validation but did not locate an explicit raise; `generation_batch_size // num_generations` appears at `:1241`, `:1284`, and `:872`, implying divisibility is required, but the error path is unconfirmed.

10. **OpenEnv and OpenReward integrations were only skimmed.** `docs/source/openenv.md` establishes that all three (OpenEnv, OpenReward, Harbor) *"conform to the same `environment_factory` contract and are interchangeable at the TRL level"*, and OpenEnv has more shipped examples than Harbor. OpenEnv may be the better default of the three; I did not evaluate it properly.
