# co-train: ranked local improvement gaps

Baseline supplied by parent: `ea6d2f6`. Read-only source/spec/test inspection, 2026-10-23. No nested agents, web, installs, tests, model runs, git operations, or project/reference writes. Only this requested scratch artifact was written.

## Bottom line

The next meaningful training milestone is **actual native sampling → aligned token/logprob/loss-mask evidence → a finite, non-skipped optimizer update → changed trainable weights → fresh-process checkpoint restoration**. Another synthetic receipt, constructor abstraction, replay format, or harness-search framework cannot establish this.

Best immediate offline slice: close sweep cancellation, then make tokenizer/bootstrap requirements explicit. Highest-leverage owner decision: whether to authorize a revised native runtime contract and a genuinely supported tokenizer/template identity. Neither decision has been made. Main training must remain closed.

## What is already covered

| Local path and symbols | Established implementation, not a new proposal | Boundary still open |
| --- | --- | --- |
| `/Users/nikolassapalidis/Developer/co-train/train/native_runtime.py`: `native_runtime_report`, `require_native_runtime`, `_parse_release` | Framework-free metadata diagnostics; nine selected packages; fresh installed enforcement separate from fixture reports; six approval/verification fields permanently false. | Selected direct bounds are not full dependency resolution, CUDA ABI, patched-runtime execution, or authorization. |
| `/Users/nikolassapalidis/Developer/co-train/train/native_training.py`: `build_sql_trainer`, `_load_runtime`, `_validate_native_view`, `_admit_output` | Explicit-task constructor; real preflight then fresh runtime gate; Unsloth-first process discipline; local-only 40-hex revision; separated loader/PEFT/trainer kwargs; all four Dataset columns; native optimizer ownership; actual discovered tool and selected-template/context checks; checkpoint configuration. | No actual patched Trainer/model-loader path exercised. Construction does not call train/save/resume. Post-admission failure can leave resources allocated. |
| `/Users/nikolassapalidis/Developer/co-train/train/sql_bridge.py`: `prepare_sql_training`, `_SQLEnvironment.reset`, `_native_reward`, `_final_text` | Explicit ordered tasks, private frozen task bindings, tool/scorer same-file checks, fresh reset state, exactly one public program tool, eight submissions, final-assistant-only SQL extraction. | Real framework batching/repetition/reset/reward metadata alignment, sampling and optimization unproved. |
| `/Users/nikolassapalidis/Developer/co-train/train/sql_episodes.py`: `record_scripted`, `encode_episode`, `decode_episode`, `_bind`, `rescore_sql`, `reexecute_sql` | Immutable scripted episodes; strict canonical JSON, 8 MiB cap, external task/ID/DB/prompt/settings/selected-source binding; rescoring separate from literal-True action replay. | Explicit `origin="scripted"`. No complete production request, real tokenizer/model generation, gradients, or policy replay. Digests are not authentication. |
| `/Users/nikolassapalidis/Developer/co-train/bench/frontier/calibration.py`: `exact_screen`, `SampleEvidence`, `summarize_groups` | Exact hypothetical screening diagnostic; task/arm/phase/config strata; distinct sample IDs; evaluation-ID exclusion; invalid groups remain visible; empirical dead fraction separate from plug-in estimate. | Caller-declared identities do not establish independent sampling, content-disjoint splits, or frontier validity. No automatic selector or manifest authorization. |
| `/Users/nikolassapalidis/Developer/co-train/process_watchdog.py`: `run_bounded`, `_cleanup`, `_signal_group` | Mutation subprocess-group lifetime bounded on normal return, timeout and interruption; signal original group after leader exit; bounded drain/reap and loud cleanup failures. | Not sweep-thread cancellation, output-volume bounding, or containment of descendants escaping with a new session. |

Already-covered tests worth preserving, not rebuilding:

- `/Users/nikolassapalidis/Developer/co-train/train/test_native_runtime.py`: `test_runtime_report_never_certifies_execution`, `test_frozen_native_conflict_is_explicit_and_uses_existing_guard`, `test_require_collects_actual_metadata_not_previous_fixture_or_report_cache`.
- `/Users/nikolassapalidis/Developer/co-train/train/test_native_training.py`: `test_real_gate_blocks_before_runtime_side_effects`, `test_real_gate_survives_optimized_python`, `test_two_task_assembly_preserves_native_inputs`, `test_actual_native_template_context_uses_all_rows_and_kwargs`, `test_one_token_context_undersize_rejects`, `test_checkpoint_configuration_is_not_restore_proof`, `test_real_dataset_arrow_interop_only_not_selected_runtime_compatibility`. The `wiring` fixture explicitly replaces preflight/runtime/loader/trainer and forbids training/save calls.
- `/Users/nikolassapalidis/Developer/co-train/train/test_sql_bridge.py`: eight real dispatches/ninth refusal, failed-reset invalidation, immutable private bindings versus mutable public rows, strict reward cardinality, invalid-gold policy preservation.
- `/Users/nikolassapalidis/Developer/co-train/train/test_sql_episodes.py`: unchanged backend output, two fresh replays, no action dispatch on decode/rescore, external-binding corruption, database changes and sidecars.
- `/Users/nikolassapalidis/Developer/co-train/train/test_learning_lab.py`: 64 actual scripted samples across eight fixture tasks and both arms; 16 task/arm groups; invalid-gold visibility, phase sample reuse, pooled-marginal rejection.
- `/Users/nikolassapalidis/Developer/co-train/tests/test_process_watchdog.py`: real-process lifetime checks, independent 2.5 s supervisor timeout and <3 s outer bound, escaped-pipe diagnosis, cleanup error propagation.

Current HANDOFF/roadmap report 139 native-targeted passes and 1861 default-suite passes with one optional Torch skip, warm cache only. These are historical recorded results, **not rerun or independently certified here**. More test-count growth is not evidence of learning.

## Ranked proposals

Rank is leverage toward an honest training claim, not permission or immediate execution order.

### 1. Resolve native stack/template contract, or explicitly remain blocked

**Lane:** owner-approved runtime/scientific decision. Offline evidence inventory is safe; changing guards, dependencies, tokenizer identity or prompts is not.

Locations: `/Users/nikolassapalidis/Developer/co-train/train/guards.py:check_stack`; `/Users/nikolassapalidis/Developer/co-train/train/native_runtime.py:require_native_runtime`; `/Users/nikolassapalidis/Developer/co-train/spec/native-training.md`; `/Users/nikolassapalidis/Developer/co-train/spec/spikes/reference/native_template.py:main`.

- Frozen Transformers `<5` and native environment `>=5.2` have an empty intersection. No resolver sophistication fixes this. Local 5.18/datasets 5 also violate selected Unsloth ceilings. Candidate Unsloth/Zoo 2026.10.3, TRL 1.13.0, Transformers 5.17.0 is **unapproved**, not a working stack.
- Cached automatic template selection rejects exact identity. The canonical identity view in the reference is hypothetical. Positive rendering of that view cannot promote the cached template. No identity shim, template hand edit, or fallback.
- `_parse_release` deliberately rejects local/build suffixes. A future CUDA distribution reporting `+cu...` can still fail admission; record its exact installed metadata/build rather than stripping the suffix to manufacture compatibility.

**Proposed acceptance:** one explicit owner decision covering the runtime contract; exact resolved distributions/builds, hardware/driver/Python and patched class/method identities; zero unacknowledged dependency/ABI blockers; actual upstream helper accepts the exact approved tokenizer/template bytes without substitution; all prompts fit context; one-token prefix corruption and one-token context undersize each fail. These checks do not authorize generation themselves.

**Dependency:** none can currently open production. Recommend parent-level architecture advice before committing to runtime activation; no advisor/nested agent was invoked here.

### 2. Capture the real sampler-to-loss boundary, not another episode receipt

**Lane:** offline interface/negative-control design first; actual model/GPU work only after explicit approval and rank 1.

Locations: `/Users/nikolassapalidis/Developer/co-train/train/native_training.py:_validate_native_view`; `/Users/nikolassapalidis/Developer/co-train/train/sql_bridge.py:_SQLEnvironment.reset,_native_reward`; `/Users/nikolassapalidis/Developer/co-train/spec/spikes/reference/trl_native_environment.py:main`; `/Users/nikolassapalidis/Developer/co-train/spec/spikes/reference/native_template.py:main`.

The pinned-method references already prove real SQLite dispatch against synthetic/generated-token inputs. `native_template.py` scripts the final answer, substitutes a fixture parser and explicitly requires sampler logprobs to be absent. The older reference supplies synthetic logprobs. Neither proves actual native generation.

**Minimal proposed milestone M1:** one genuinely sampled native tool trajectory, including a real tool observation and a subsequent sampled assistant continuation, with exact request/template/tokenizer/model identities. No forced/scripted tool call or fabricated successful final answer. An inability to elicit a tool call within the preapproved budget is a reported failed milestone, not permission to inject one.

**Numeric checks:** zero token/mask/logprob alignment discrepancies; identical declared completion-axis lengths; zero externally supplied observation-token loss weight; finite sampler logprobs at every sampled-token position used by the loss; external placeholders explicitly not called sampled logprobs. A planted one-position token/logprob shift and a single observation mask bit changed to 1 must each fail independently.

Also verify actual patched batching on two distinguishable tasks (existing SQLite 17/29 pattern), G-fold row repetition, task-bound resets/rewards, and absence of private gold in the full rendered model request. Constructor spies cover call shape only. Capture both sampler and training-policy logprobs, without requiring equality or changing the signed mismatch monitor.

**Non-goal:** expand scripted `SqlEpisode` into a generic rollout platform. Keep scripted and sampled evidence explicitly different; add only the boundary data the real native path emits.

### 3. Prove one real update and restoration, then separately prove monitoring/probe adequacy

**Lane:** actual model/GPU work; owner-approved budget/hardware/runtime/data and M1 required.

Locations: `/Users/nikolassapalidis/Developer/co-train/train/native_training.py:build_sql_trainer`; `/Users/nikolassapalidis/Developer/co-train/train/dead_group_probe.py:batch_for`; `/Users/nikolassapalidis/Developer/co-train/train/verdict.py:probe_verdict,run_verdict`; `/Users/nikolassapalidis/Developer/co-train/train/grpo_ptc.py:main`.

**Minimal proposed milestone M2:** exactly one native optimizer update from actual sampled, SQL-scored groups, not a toy Torch optimizer or supplied gradient array.

- Preserve G=4, four groups per optimizer step, current `batch_for(4)=(8,2)`, beta .04, LR 3e-5, fp16, thinking disabled and existing completion/action caps. Verify their effective meaning in the patched trainer rather than assuming the formula matches runtime scheduling.
- At least one usable group must have nonconstant actual rewards; do not force outcomes, resample until green, or alter rewards to get there.
- Finite loss; all present trainable gradients finite; at least one nonzero trainable gradient; exactly one optimizer step, zero AMP-skipped updates; at least one trainable LoRA parameter changes by strictly more than zero; frozen base tensors unchanged.
- Save an actual native checkpoint. A fresh process loads the same base revision plus saved adapter/model state; restored trained tensors equal saved post-update tensors exactly. On a predeclared fixed-input evaluation require zero token-ID/reward mismatches and max absolute logit difference <=1e-3, a proposed engineering tolerance to approve before execution, not a new scientific threshold.
- Record actual native optimizer/scheduler/scaler/RNG/global-step state. Do not claim resumable training merely from restored weights: that stronger claim additionally needs native resume reaching step 2 without resetting recorded optimizer state.
- Negative controls: skip the optimizer step, reload the original adapter, or remove/corrupt a required checkpoint component. Each must prevent the corresponding proof from passing.

One update is an **engineering smoke**, not a five-step probe, policy improvement, or RUN PASS. Existing minimum probe length 5, sustained window 10, ceiling .60 and multiplier 3.0 remain untouched. Complete run telemetry must actually feed existing verdict functions; finite metrics do not themselves prove changed weights.

**Important dependency:** production `build_sql_trainer` calls frontier preflight before runtime loading, and `grpo_ptc.main` still refuses after preflight. No manifest means no use of this constructor for even the one-step smoke. Ordinary route is approved runtime/measurement contract → authorized frontier evidence → reviewed manifest admission → approved native update. Any narrower engineering-only launch authorization would be a separate owner-approved contract, never a hidden fixture/preflight bypass.

### 4. Stop timed-out sweep computation, not only wrapper collisions

**Lane:** highest-value immediately implementable offline engineering candidate, with process/safety review.

Locations: `/Users/nikolassapalidis/Developer/co-train/bench/sql_parity_sweep.py:_with_deadline,_one`; `/Users/nikolassapalidis/Developer/co-train/bench/test_sql_parity_sweep.py:test_late_timed_out_wrapper_cannot_replace_the_next_task`; `/Users/nikolassapalidis/Developer/co-train/process_watchdog.py:run_bounded`.

`_with_deadline` returns while its daemon remains alive. Private wrapper ownership already fixes the wrong-database race; do not redo that repair. `_one` currently uses the existing 30+15 s outer bound. Cancellation needs an actual interruptible execution owner, not a timed-out Future.

Prefer evaluating a small owned subprocess around one differential call, reusing watchdog behavior where suitable, versus exposing/coordinating SQLite connection interruption across both drivers. Choose after a narrow lifecycle test; do not grow a distributed worker system.

**Proposed numeric checks:** test deadline .10 s; no executing owned worker/descendant and no post-timeout side-effect marker within 1 s; independent supervisor <3 s; two successive 17/29 tasks never cross-bind; zero valid-query output/score differences; errors remain `sweep_error`, deadlines `sweep_timeout`; preserve production timeout/row/comparison policy. Mutation removing termination must fail on actual liveness, not directory disappearance. Process-group cleanup is not a hostile-shell sandbox.

### 5. Make offline bootstrap honest and reproducible

**Lane:** safe offline test/startup engineering; dependency/artifact acquisition separately approved.

Locations: `/Users/nikolassapalidis/Developer/co-train/bench/test_contamination.py:test_long_positive_control_is_longer_and_still_canonical,test_v2_control_is_length_matched_to_bird`; `/Users/nikolassapalidis/Developer/co-train/pytest.ini`; `/Users/nikolassapalidis/Developer/co-train/train/native_training.py:_load_runtime`.

Both contamination controls call `AutoTokenizer.from_pretrained("unsloth/Qwen3-0.6B")` without a pinned local artifact or explicit local-only flag. Current warm-cache green is not cold-cache/offline startup. The optional Torch skip remains visible; installing Torch is not this task's fix.

**Proposed numeric checks:** with empty isolated HF caches and all network attempts rejected, pure offline suite completes without tokenizer access; separately identified tokenizer integration either succeeds from declared exact local bytes or exits nonzero with a named missing artifact, zero network attempts. Removing one required tokenizer file must fail. Preserve both real tokenization assertions and their negative controls; merely skipping/reclassifying them is not an integration pass. Do not claim the full existing suite cold-cache green without its explicit integration evidence.

### 6. Freeze frontier provenance and invalid-gold semantics before collecting evidence

**Lane:** offline diagnostic schema/source inventory safe; instrument, split, sampling, reward policy and admission changes owner-approved; measurement itself model/GPU/possibly paid.

Locations: `/Users/nikolassapalidis/Developer/co-train/bench/frontier/probe.py:ProbeResult.report,ProbeResult.manifest,probe`; `/Users/nikolassapalidis/Developer/co-train/train/guards.py:frontier_taskset_status,_check_measurement,retention_floor`; `/Users/nikolassapalidis/Developer/co-train/train/ex_reward.py:make_execution_reward`.

- Active admission requires a nonempty policy string, not an exact match to the training model/revision. It does not call `_check_measurement`; do not activate that entire helper because its retention floor is unsigned.
- `ProbeResult` preserves rates/retained/void records but lacks full revision, corpus digest, channel, sampling and evaluation-membership binding. `probe(generate(task)->str)` only scores returned text; it does not establish that generation used the intended channel or independently sampled confirmation groups.
- Reward still maps invalid gold to 0; calibration correctly keeps invalid groups unusable. That mismatch is known, not an invitation to silently mask training examples. Existing protected execution of 800 shipped golds is already recorded; repeat a census only if relevant DB/scorer bytes change.

**Proposed acceptance:** owner-frozen model/revision, template/channel, corpus and ordered candidate IDs, G, sampling config, scorer, train/eval membership and invalid-gold disposition; 100% candidate outcomes retained including voids; zero reused screen/confirmation samples; zero declared train/eval overlap plus an explicit content/seed leakage audit. Same-marginal balanced versus saturated controls must remain different (dead fractions 0 versus 1). Exact-screen reference p=.10, n=G=4 already yields .6562 true dead probability versus .2927028795811518 conditional plug-in estimate: screening does not certify independent trainability.

Current derived task-count floor is documented as 59; preserve the actual signed/power-derived gate, not an invented retention threshold. A manifest may only follow authorized real measurements and the separately approved admission contract. No synthetic manifest, no picking a more favorable G, no reporting historical G=8 v10 as current G=4 evidence.

### 7. Only then ask whether a more elaborate harness helps

**Lane:** owner-approved scientific treatment plus real compute.

Location: `/Users/nikolassapalidis/Developer/co-train/docs/completion-roadmap.md`, completion steps 3–5. Current constructor is PTC-only; config vocabulary for two arms is not a bash-trained comparator.

First complete a registered base/PTC-trained/bash-trained × PTC/bash-evaluation matrix: exactly six cells, paired held-out IDs, uncertainty, token/dollar costs and channel divergence reporting. Preserve shared cross-arm cap 4258 when comparing trained arms, rather than reusing PTC-only 3072. Developing/authorizing the missing comparator is later work, not a reason to expand the current constructor now.

Harness search, adaptive task sampling, warm-start/SFT, mixed-interface training, new tools/prompts, curriculum and new procedural tasks are distinct treatments or instruments. Require compute-matched controls and unchanged held-out scoring. Null or inconclusive results are valid completion outcomes. BIRD remains H3/H4/H5, not N1; do not revive H2.

More harness complexity cannot reconcile contradictory version gates, support a rejected template, turn all-equal rewards into informative groups, or establish an optimizer step. It increases action-distribution drift, provenance burden, contamination routes and debugging surface before the simplest learner is proven. Do not adopt another training platform merely because it has richer receipts or orchestration.

## Approval gates and non-goals

Safe next work is bounded engineering/tests around process lifetime, offline startup and source-bound evidence contracts. Implementation remains a separate assignment. Any future guard/permission/process changes need reviewer/security scrutiny; runtime architecture merits parent-level advice.

Owner approval is required before runtime contract/dependency changes, tokenizer/template identity changes, manifest/admission/signature changes, model/revision/channel/G/task/corpus/split selection, invalid-gold policy, new prompts/tools, optimizer/scientific thresholds, or experimental treatments. Approval for a design is not approval for install/download, model execution, GPU allocation, paid API usage or spending.

No launch, manifest write, threshold relaxation, template shim, dependency install, alternate trainer, scorer rewrite, divergence normalization, harness-search machinery, learning-gain claim, synthetic gradient/checkpoint receipt, push, deploy, or project/vault edit belongs to this synthesis.

## Evidence and validation limits

- Sources inspected directly: modules/tests named above, `/Users/nikolassapalidis/Developer/co-train/spec/native-training.md`, `/Users/nikolassapalidis/Developer/co-train/spec/learning-lab.md`, `/Users/nikolassapalidis/Developer/co-train/docs/completion-roadmap.md`, and current state in `/Users/nikolassapalidis/Developer/co-train/HANDOFF.md` (lines 9–61).
- File tools were available; no shell/Execute/git tool was exposed. Parent-supplied `ea6d2f6` is authoritative context, not independently verified HEAD. Working-file inspection cannot certify a commit snapshot or absence of concurrent edits.
- No live package/hardware discovery, tests, mutation runs, template execution, SQLite actions, models, GPUs, network or paid calls performed. No external-framework conclusions imported from other workers; their unfinished files were not read.
- Proposed numeric checks above are future acceptance criteria, not observed passes or scientific amendments. Local absence of Torch and other training packages is retained from current authoritative project context; it was not repaired or hidden.
- `wrap-up` skill was activated as instructed; all vault/project/proposal-write steps were skipped because this assignment permits only this one scratch artifact. Suggested skill fix, not applied: `/Users/nikolassapalidis/.agents/skills/wrap-up/SKILL.md`, add “For read-only/parent-bounded subagents, return wrap-up facts without vault or proposal writes.”

VERIFY_REAL: source/spec/test inspection only; requested artifact written and freshly read back. No runtime/training claim.
