"""Step 2: five GRPO steps on Kaggle T4 x2. Does it run, and is fp16 stable.

That is the whole question. This is not a learning run — 5 steps at 0.6B
teaches nothing — it is a stability probe. Whether it passed is decided by
`verdict.py`, not by the run exiting 0, because a GRPO run with a degenerate
reward completes cleanly while producing no gradient at all.

    python step2/gate_chat_template.py      # first, informational
    python step2/smoke.py                   # writes step2_metrics.jsonl
"""

from __future__ import annotations

import os

# Before torch. 180 s -> 4 s on vLLM weight sync; harmless without vLLM, and
# setting it here means it cannot be forgotten when Step 6 turns vLLM on.
os.environ.setdefault("NCCL_CUMEM_ENABLE", "0")

import unsloth  # noqa: F401  # must precede transformers/trl for its patches

import torch
from datasets import Dataset
from transformers import TrainerCallback
from trl import GRPOConfig, GRPOTrainer
from unsloth import FastLanguageModel

from verdict import TARGET_WORDS, load, verdict, word_count_reward

MODEL = "unsloth/Qwen3-0.6B"
OUT = os.environ.get("STEP2_OUT", "step2_metrics.jsonl")
MAX_SEQ = 1024
LORA_RANK = 32            # HANDOFF: 16-32
NUM_GENERATIONS = 8
MAX_STEPS = 5

SUBJECTS = [
    "a harbour at dawn", "a worn leather satchel", "an empty tram", "a copper kettle",
    "a mountain path", "a second-hand bookshop", "a thunderstorm", "a quiet library",
    "a fishing boat", "an old piano", "a greenhouse", "a train station at night",
    "a lighthouse", "a bakery in winter", "a river in flood", "a desert road",
]


def build_dataset(tok) -> Dataset:
    """Plain-string prompts, pre-rendered.

    Rendered here rather than handed to TRL as messages for two reasons.

    `enable_thinking=False` does not remove Qwen3's <think> block — it emits
    an already-closed empty one at the end of the prompt, so the completion
    starts on the answer. Left at the default, the prompt ends at
    "assistant\n" and the model opens its own <think>, which on a 128-token
    completion budget means mean_response_length measures reasoning rather
    than output, and truncation rates reflect the wrong thing.

    And TRL 0.24 — Unsloth's ceiling — has no `chat_template_kwargs`, so
    there is no way to pass that flag through the trainer. Plain strings are
    the only route.
    """
    prompts = [
        tok.apply_chat_template(
            [{"role": "user", "content": f"Describe {s} in about {TARGET_WORDS} words."}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        for s in SUBJECTS
    ]
    # RepeatSampler takes `generation_batch_size // num_generations` UNIQUE
    # prompts per optimizer step and repeats each one num_generations times
    # (trl grpo_trainer.py:685-692) — that is 1 prompt per step here, not
    # per_device_batch. So max_steps needs 5 prompts; 128 is 25x slack.
    return Dataset.from_dict({"prompt": prompts * 8})


class JsonlLogger(TrainerCallback):
    """Persist every log line. /kaggle/working survives the session; the
    notebook's scrollback does not, and the 20-30 min idle timeout can take
    the kernel before the output is read."""

    def __init__(self, path):
        self.path = path
        open(path, "w").close()

    def on_log(self, args, state, control, logs=None, **kw):
        if logs:
            import json

            with open(self.path, "a") as f:
                f.write(json.dumps({**logs, "step": state.global_step}) + "\n")


def main() -> int:
    assert torch.cuda.is_available(), "no CUDA — this runs on Kaggle, not the dev machine"
    cap = torch.cuda.get_device_capability()
    # device_count() is what the session exposes, not what trains. Unsloth's
    # generated trainer forces args._n_gpu = 1 whenever parallel_mode is
    # NOT_DISTRIBUTED (unsloth/models/rl.py:531-534), which a plain
    # `python smoke.py` always is — so this trains on ONE T4 and the
    # NCCL_CUMEM_ENABLE above is inert until Step 6 launches distributed.
    print(f"gpu   {torch.cuda.get_device_name(0)}  sm_{cap[0]}{cap[1]}  "
          f"x{torch.cuda.device_count()} visible, 1 training (Unsloth pins _n_gpu=1)")
    # T4 is sm_75; bf16 needs 8.0. Asserted rather than branched on: a silent
    # fall-through to bf16 on better hardware would not be the Step 2 run.
    assert cap[0] < 8, f"expected a pre-Ampere GPU for the fp16 question, got sm_{cap[0]}{cap[1]}"

    model, tok = FastLanguageModel.from_pretrained(
        model_name=MODEL,
        max_seq_length=MAX_SEQ,
        dtype=torch.float16,   # explicit: T4 cannot do bf16
        load_in_4bit=False,    # 0.6B fits in 16-bit on a 16 GB T4; keeps the
        load_in_16bit=True,    # fp16 question clean of quantisation effects
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        lora_alpha=LORA_RANK,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    cfg = GRPOConfig(
        output_dir="step2_out",
        max_steps=MAX_STEPS,
        learning_rate=3e-5,        # Garg: 1e-4 collapses the policy, 3e-5 does not
        num_generations=NUM_GENERATIONS,
        per_device_train_batch_size=NUM_GENERATIONS,
        gradient_accumulation_steps=1,
        num_iterations=1,          # on-policy. Garg: 16-step reuse collapses mid-run
        # The only measurement this run can contribute that nobody has
        # published. gap-closure section 7: a public Kaggle 2xT4 Qwen3-0.6B fp16
        # GRPO run already shows 314 clean steps at this exact config, so
        # "does fp16 run" is settled — but it ran beta=0, so `loss` was
        # identically 0 and no KL curve exists. Costs no extra weights: the
        # model is PEFT, so TRL sets ref_model = None and reverts via
        # disable_adapter() (grpo_trainer.py:430-433, :1456-1466) rather than
        # loading a second 0.6B. One extra forward pass per step.
        beta=0.04,
        max_prompt_length=256,
        max_completion_length=128,
        mask_truncated_completions=True,
        use_vllm=False,
        fp16=True,
        bf16=False,
        logging_steps=1,           # 5 steps total; every one is a data point
        log_completions=True,
        save_strategy="no",
        report_to="none",
    )

    # GRPOTrainer's own kwargs are not covered by the GRPOConfig kwarg test —
    # that would mean vendoring 1843 more lines for a six-name surface. Checked
    # by hand against trl v0.24.0 grpo_trainer.py:216-228 on 2026-09-25: model,
    # reward_funcs, args, train_dataset, processing_class, callbacks all present.
    GRPOTrainer(
        model=model,
        processing_class=tok,
        reward_funcs=[word_count_reward],
        args=cfg,
        train_dataset=build_dataset(tok),
        callbacks=[JsonlLogger(OUT)],
    ).train()

    ok, why = verdict(load(OUT))
    print("\n" + "=" * 60)
    print("STEP 2 PASS — loop runs, fp16 stable" if ok else "STEP 2 FAIL")
    for r in why:
        print("  -", r)
    print(f"metrics: {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
