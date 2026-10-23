# Native TRL environment contract

Verified 2026-10-22 against the official
[TRL v1.13.0 trainer source](https://raw.githubusercontent.com/huggingface/trl/v1.13.0/trl/trainer/grpo_trainer.py).
The supplied source is never imported. The runner extracts only
`GRPOTrainer._tool_call_loop` and checks its SHA-256 before executing it.
The verified method hash is
`3a513812b6988bb1bb4cc9cceee21ebf343b63f6810c7d12eb693af856027f79`.

## Checks before implementation

The reference runner proved all of these with no model or training:

- Exactly one discovered tool; its schema equals the evaluation schema through
  the installed Transformers schema generator.
- One real SQLite execution returns 17, without exposing the gold sentinel.
- Two external observation-token positions have mask 0; four synthetic model
  positions retain mask 1. Inserted external log-probabilities are zero.
- `--break-mask` changes the verified method only in memory and fails the mask
  assertion with exit 1. The normal runner exits 0.

`--trainer-source` is required. Run the module
`spec.spikes.reference.trl_native_environment` from the repository root with a
local copy of the pinned upstream source. No source download, model loading or
training is hidden in this runner.

`--production-bridge` runs the same checked method with the implemented
`prepare_sql_training` factory instead of the throwaway fixture adapter.
It passed with final SQL execution reward `[1.0]`; its `--break-mask` control
failed too. Optimized Python is rejected so assertions cannot silently vanish.

## Implementation

1. Add a composition adapter around `sql_environment`, exposing only reserved
   `reset` and the one `run_program` tool. Rebind by explicit task ID and clear
   stale state before validating a reset.
2. Prepare conversational dataset rows and private SQL-reward metadata from
   explicitly supplied tasks. Require tool and reward database identity.
3. Preserve the existing final-SQL channel and execution reward. Treat native
   transcripts without a final assistant answer as empty predictions.
4. Forward requested positive integer steps through preflight. Keep all
   scientific gates, constants and stack rules unchanged.

The regressions require two real fixture tasks returning 17/29, eight successful
dispatches followed by a non-dispatching ninth refusal, zero gold sentinels in
model-visible input, and no stale task after a failed reset.
All 80 bridge/step cases passed. Four independent runtime guard removals
produced 1 budget, 7 stale-reset, 2 corpus-identity and 1 unfinished-answer
failures. The default offline warm-cache suite passed 1189, with one torch skip.

## Limits and non-goals

The token suffix, generation and response parser are fixtures. This does not
verify a real tokenizer, model log-probabilities, complete trainer construction,
Unsloth's patched classes, gradients, checkpoints, CUDA compatibility or learning.
The spike is a reference, not the production implementation.

The frozen project guard requires Transformers below 5; native TRL environments
require at least 5.2. The installed 5.18.0 supports the schema probe but is above
Unsloth 2026.10.3/2026.10.7's declared 5.17.0 ceiling. Package metadata suggests
a possible 5.2–5.17 intersection, not a verified or approved training stack.
No dependency, scientific rule, amendment, signature or manifest was changed.
No GPU, model, paid service or training job was used.

## Learning-lab references, 2026-10-23

`sql_replay.py` executes one real fixture task through both current arms twice
with fresh wrapper directories. Success, SQL errors and PTC partial-output
rejection produced identical same-arm observation bytes on SQLite 3.50.4.
It does not compare the arms' different renderings or implement artifact binding.

`frontier_calibration.py` preserves the exact synthetic Bernoulli stress test.
Its `--break-marginal` control replaces taskwise reduction with marginal-only
reduction and must fail. It does not generate a policy outcome or a manifest.
Both references reject optimized Python so their assertions cannot vanish.

The implementation and test-first scope are in
[`spec/learning-lab.md`](../../learning-lab.md).
