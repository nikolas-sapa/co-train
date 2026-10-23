# Native SQL trainer assembly, without opening launch gates

2026-10-23. Baseline `d6d04f0`. Implement the missing explicit-task constructor
path, not a training launch or an approved dependency upgrade.

## Failure-first acceptance tests

1. `test_real_gate_blocks_before_runtime_side_effects`: current real preflight
   refuses before 1 framework import, Dataset/model/trainer construction or
   output creation. The same refusal survives `python -O`. Removing preflight
   must fail an independent negative control.
2. `test_runtime_report_never_certifies_execution`: installed metadata and
   supplied fixture metadata are labelled separately. Neither can produce
   `runtime_verified=True`, `training_verified=True` or launch authorization.
   Report all missing selected packages, not just the first.
3. `test_frozen_native_conflict_is_explicit`: TF4.57.6 fails native >=5.2;
   TF5.17.0 fails the unchanged frozen <5 constraint; installed TF5.18.0 and
   datasets5.0.1 additionally exceed selected Unsloth metadata bounds.
   All refuse before model loading. A supplied version dictionary cannot
   override the production runtime check.
4. `test_two_task_assembly_preserves_native_inputs`: two real SQLite fixture
   tasks (17/29), exactly two Dataset rows with all four bridge columns;
   reset and SQL rewards remain task-bound, exactly one discovered run_program,
   no additional `tools` registration. Construction calls train zero times.
5. `test_constructor_arguments_are_separate`: loader receives no reward_funcs
   or lora_rank; PEFT receives existing r/alpha; trainer receives the bridge SQL
   callable/factory, not exact-match reward. Preserve G/beta/lr/fp16/cap/thinking
   and requested steps 1/17/200. Keep native optimizer ownership.
6. `test_local_revision_and_output_admission`: require a full 40-hex model
   revision and explicit positive integer context bound. Set local_files_only.
   Reject invalid steps/context/revision and existing nonempty or symlinked
   output destinations before runtime imports. Never clean/overwrite output.
7. `test_actual_native_template_context`: use trainer.chat_template override,
   not an assumed mutation of tokenizer.chat_template. Render the exact bridge
   prompt with the one actual discovered tool schema and existing thinking
   kwargs; prompt tokens plus completion cap must fit the caller's context.
   One-token undersizing fails; no bare 2612 assumption.
8. `test_native_prefix_contract`: cached stock tokenizer's failing native
   tool-suffix prefix must not be reported as a pass. Inspect/pin official
   TRL's training-template helper and prove its positive behavior in a
   reference before claiming a full tokenizer boundary. Corrupting one prefix
   token must fail. Never hand-edit the production template.
9. `test_checkpoint_configuration_is_not_restore_proof`: native saves at
   requested steps, save_only_model=False, push_to_hub=False; no save/train/
   resume invocation during construction. Configuration is not checkpoint
   existence or restoration evidence.
10. Execute one real available Dataset conversion and real SQL bridge calls.
    Constructor spies are explicitly wiring tests, never runtime/gradient
    verification. Source-bound native template execution is a separate
    reference, not a complete patched Trainer.
11. Run narrow existing bridge/config checks, independent runtime/gate and
    context negative controls, Python/security review, and the offline
    default suite. Keep absent torch and unavailable cold caches visible.

## Established evidence and remaining spike

`research/2026-10-23-native-runtime-metadata.json` records fresh official
versioned PyPI metadata for the proposed core and critical compiled packages.
It is not a lockfile. In addition to the known Transformers conflict, local
datasets5.0.1 is outside Unsloth's <5 bound. Linux Torch/vLLM/CUDA identity
cannot be inferred from one historical mixed-cu128/cu129 run.

The real local environment is Darwin arm64, Python3.12.13, Transformers5.18.0
and datasets5.0.1, without torch/TRL/Unsloth/vLLM/Accelerate/PEFT.
It can convert real Arrow rows and tokenize cached unsloth/Qwen3-0.6B;
it cannot execute the specified CUDA training runtime.

A fresh cached-tokenizer test found stock native tool-suffix prefix mismatch
at token 9. Native TRL selects a training-safe template into its own
`trainer.chat_template`, which need not replace tokenizer.chat_template.
The official helper reference was checked: its Qwen3 training string preserves
the prefix (29/48 tokens) while cached stock is 29/44 with mismatch at 9.
However, automatic helper selection REJECTS the cached template's exact
identity. The rendering-positive spike uses an explicitly hypothetical
canonical identity view; it is not a production fix or supported constructor.
No production identity shim, hand-edited template or fallback is allowed.
Selected template SHA256:
`1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9`.
The real bridge observation was 17 with 19 external masked tokens and no
sampler logprobs. Prefix and mask mutations failed independently.
The existing SHA-pinned `_tool_call_loop` reference remains valid only for its
synthetic token/parser inputs and real SQLite action, not full generation.

## Track A: non-executing runtime compatibility report

Owner: `train/native_runtime.py`, `train/test_native_runtime.py`.

Public API:

```python
native_runtime_report(versions=None) -> dict
require_native_runtime() -> dict
```

Only the report accepts caller-supplied version fixtures. Production requirement
collects fresh installed distribution metadata itself, with no caller bypass.
No framework imports, installer, network request or environment mutation.
Use existing `guards.check_stack` for the frozen rules, never rewrite them.

Inspect selected packages: unsloth, unsloth_zoo, trl, transformers, torch,
vllm, datasets, accelerate, peft. Explicit core proposal is Unsloth/Zoo
2026.10.3, TRL1.13.0, Transformers5.17.0. It is not owner-approved.
Report native Transformers >=5.2 separately from the general TRL package
floor; selected Unsloth ceiling <=5.17 and datasets4.7<=version<5 separately.
Other selected direct bounds: torch2.4<=version<2.15, vLLM .19.1 through .28,
Accelerate>=1.4, PEFT>=.18, Zoo>=2026.10.3. These are selected critical checks,
not complete transitive/marker/ABI resolution; say so in the output.
Known vLLM0.23 constraints must not be contradicted by the report (Torch2.11,
excluded early Transformers5 releases). Unknown builds remain unverified.

Use bounded strict release-version parsing, not permissive numeric coercion.
Unknown/prerelease formats fail closed as unevaluable metadata, never pass.
Report schema1, metadata source, actual platform/Python, exact supplied/
resolved versions, frozen/native blockers, proposed core, and permanently
false runtime/training verification and launch-authorization fields.
Zero selected errors can be called metadata-only, never ready/compatible.
Require raises a named exception on blockers. Current frozen/native conflict
must keep it closed. The report itself grants no authority to execute.

Public report fields are `schema_version`, `metadata_source` (`installed` or
`fixture`), `platform` (system/machine/python), `versions`, `candidate_core`,
`metadata_scope="selected_direct_constraints_only"`, `limitations` and `issues`.
Issues retain `missing`/`invalid` package-to-string maps, the unchanged frozen
guard's list, and `native`/`selected` package-to-list maps. The six permanently
false fields are `candidate_approved`, `dependency_graph_verified`,
`abi_verified`, `runtime_verified`, `training_verified`, `launch_authorized`.
`NativeRuntimeError(RuntimeError)` retains the complete report in `.report`.

## Track B: explicit native trainer construction

Owner: `train/native_training.py`, `train/test_native_training.py`.

Public API:

```python
build_sql_trainer(
    tasks, db_root, *, output_dir, model_revision, max_seq_length,
    steps=200, root=REPO_ROOT,
)
```

Return the constructed Trainer only. Do not call train, save, resume or
publish. Keep `grpo_ptc.main()` and its post-preflight refusal unchanged.

Validate explicit inputs, but create no files and import no frameworks until
the existing real `grpo_ptc.preflight(root=root, steps=steps)` and new production
`require_native_runtime()` pass. No public dependency/preflight injection,
approval boolean, alternate model, arm, G, reward, or task selector.
Private constructor seams may be replaced in labelled unit tests only.

Use `prepare_sql_training` on caller-supplied tasks and the same physical
tool/scorer databases. Convert its conversational rows to a Dataset without
pre-rendering, repeating rows or deleting answer/task_id/db_id metadata.
Set remove_unused_columns=False explicitly.

Load Unsloth before torch, Transformers/TRL/PEFT. Reject a contaminated fresh
process rather than claim import order was correct after those imports.
Keep existing model ID and LoRA/precision settings; use constructor-specific
kwargs, never pass `**model_spec()` wholesale. Loader uses explicit fp16,
local_files_only=True, required pinned revision and caller context bound.
No implicit model/dependency download, fallback precision or alternate backend.

Derive batch sizes with existing `batch_for(NUM_GENERATIONS)`. Reuse unchanged
PTC `training_config(steps=steps)`, then add output, metadata retention,
prepared.max_tool_calling_iterations, and native checkpoint scheduling:
save_strategy="steps", save_steps=steps, save_only_model=False,
push_to_hub=False. No injected optimizer, probe abort callback or new policy.
Register environment_factory and actual prepared SQL reward exactly once;
do not pass a duplicate tools list.

The caller must supply the context bound before model load. After native
construction, validate every actual prompt using the Trainer-selected template,
the actual `trainer._env_tools[None]` discovery and unchanged chat kwargs, before returning
and before any generation. Require prefix-preserving suffix behavior. This
resolves sequence-sizing order without pretending a stock pre-load template
is necessarily the native template.
Use the actual native `_get_tool_suffix_ids` on a synthetic conversational
boundary as a fail-closed check, not a model generation or backend execution.
Require exactly the one named discovered program tool; reject missing runtime
attributes rather than measuring another prompt/template/tool view.

Partial construction can allocate approved runtime resources. Do not claim
cleanup, checkpoint existence, AMP update or arbitrary-program determinism
from constructor success. Runtime activation remains blocked today.

## Parent ownership and implementation order

Parent owns this spec, promoted references, cross-slice checks, metadata/
validation research, README/train-notes/HANDOFF updates and one local commit.
Teams write assigned tests first and stop for parent RED before source code.
After the native-template spike, promote/comment the reference, finalize any
contract clarification here, then implement. No agent commits or pushes.

## Non-goals / protected boundaries

No frozen version-rule, scientific amendment/signature/manifest, threshold,
model/revision selection, G/channel/prompt/tool/scorer/evaluation-membership
change. No dependency/model install/download, GPU/model/paid run, training launch,
production deployment or push. Do not replace TRL/Unsloth with another trainer.
Do not add a receipt checker that emits invented gradients/weights or calls
fixture consistency real learning. Actual sampler/logprob, optimizer and
checkpoint restore evidence remains a separately approved runtime task.
