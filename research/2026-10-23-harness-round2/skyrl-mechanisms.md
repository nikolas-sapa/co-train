# SkyRL token-to-update mechanisms, pinned-source research

Date: 2026-10-23. Scope: source inspection, not runtime validation. No repository edits, installs, external code execution, model/data downloads, GPU jobs or paid jobs.

## Findings and evidence boundary

- Official `NovaSky-AI/SkyRL` main resolved to **`3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d`**, commit timestamp **2026-10-23T03:58:07Z**, subject **`[SkyCap] Support OpenAI Responses API (#2510)`**. Public GitHub API observed during this research. All code links below pin that SHA. [Commit](https://github.com/NovaSky-AI/SkyRL/commit/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d).
- A concrete source chain reaches `loss.backward()`, `optimizer.step()`, sampler weight synchronization and model/optimizer/RNG checkpointing. **Source optimizer path is not execution proof**, especially not proof of native learning in co-train.
- Three distinct layers coexist: current SkyRL Gym generator, current SkyCap/Harbor capture integration, and the older `skyrl-agent` research layer. Do not splice their interfaces or infer their tests prove one another.
- Parent-supplied co-train baseline `ea6d2f6` is authoritative. Freshly read `/Users/nikolassapalidis/Developer/co-train/spec/native-training.md`: model, G, scorer, evaluation membership and GRPO are frozen; trainer construction must call train/save/resume zero times; Torch/native runtime unavailable; launch gate closed. No recommendation below authorizes changing these.

## 1. Actual Gym environment → generation → training chain

### Task and reward

[`SQLEnv.__init__/step/_get_reward`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-gym/skyrl_gym/envs/sql/env.py#L17):
each instance binds `db_id`, gold SQL, dataset identity and physical SQLite file. `step` increments turns and records the assistant action. Intermediate `<sql>...</sql>` actions execute a SQL tool and return observations as **user** messages. `<solution>...</solution>` or the turn limit terminates. Intermediate reward is 0; terminal reward is evaluated against gold SQL.

[`calculate_reward_single/execute_sql_wrapper_single`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-gym/skyrl_gym/envs/sql/utils.py#L47):
format rejection yields -1; valid predicted and reference queries are executed, fetched rows converted to `frozenset`, equality yields 1, otherwise 0. Queries run in transactions with rollback and timeout interruption. This is **SkyRL's scorer**, not permission to replace co-train's existing SQL callable or its equality semantics. Set-based results discard duplicates and order; unsuitable to transplant silently.

### Repeated prompts, exact identities

[`prepare_generator_input`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/utils.py#L564):
repeats each prompt `n_samples_per_prompt` times, deep-copies environment extras, assigns `TrajectoryID(instance_id=uid, repetition_id=k)`. A prompt UID identifies the advantage group; a repetition identifies one rollout. Replication here plus another agent layer's replication would silently multiply G.

### Agent loop and token ownership

[`SkyRLGymGenerator.agent_loop`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L332):

1. Construct environment, call `env.init`, render initial prompt.
2. Call inference with **actual `prompt_token_ids`**, session ID and cache salt. Receive sampled `response_ids`, decoded response, stop reason and optional sampler logprobs/support/routes.
3. Call `env.step(decoded_response)`, receiving observation/reward/done.
4. Build `TurnOutput` from sampled IDs and separately encoded observations.
5. In token-in/token-out multi-turn mode, append sampled IDs unchanged plus observation IDs. Repeat until terminal/context bound.
6. Trim final response to the last response endpoint, align masks/logprobs/rewards, return `GeneratorOutput`.

[`TurnOutput.get_turn_loss_mask/get_turn_rollout_logprobs`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L125):
generated action tokens receive mask 1; environment observations and next-turn scaffold receive mask 0. A manually appended stop-string EOS is **not sampled** and receives mask 0. Observation logprob zeros are padding/bookkeeping, not observed sampling probabilities.

[`get_obs_ids_from_obs`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L771):
uses a fixed base conversation to extract only new formatted observation/suffix IDs. Does not re-render prior sampled actions.
[`_update_agent_loop_state_with_multiturn_chat_template`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L1233) appends these arrays.

**Limits visible in source:** custom-template retokenization recomputes assistant masks and discards rollout logprob bookkeeping because token-in/token-out is broken; receiving sampler logprobs with the custom-template path raises. String-level `postprocessed_action` re-encodes the action and warns about token identity, rather than establishing equality with sampled IDs. Do not treat every generator mode as equally rigorous.

[`_build_per_token_rewards`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L733):
normal path puts each step reward at that assistant-turn endpoint, observations get zero reward. Out-of-range endpoint rewards are dropped after truncation. Custom-template path returns only last-step scalar reward. Environment success, context truncation and uncaptured action tokens are different events.

### Padded training batch and groups

[`RayPPOTrainer.convert_to_training_input`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L905) →
[`convert_prompts_responses_to_batch_tensors`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/dataset/preprocess.py#L207):
creates sequences, attention mask, response mask, rewards, loss mask and optional rollout logprob/support/route tensors. Responses and response-level arrays are right-aligned in the padded batch.

**Do not conflate masks:** attention mask excludes padding; response mask indicates the nonpadding response span, including interleaved external context; loss mask identifies trainable sampled actions within that span. Advantage broadcast uses response mask. Policy objective uses loss mask. Masking an external observation from loss does not remove it from causal context.

UIDs remain metadata until advantages are computed. Prompt mini-batch boundaries keep grouped rollouts together, including variable numbers of stepwise rows.

[`compute_advantages_and_returns`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1191):
ordinary mode runs estimator on each rollout and its prompt UID. Stepwise mode takes **only `is_last_step` rows** to compute one outcome advantage per rollout, then broadcasts it to every row belonging to that rollout. More context forks must not become more independent reward samples.

[`compute_grpo_outcome_advantage`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/ppo_utils.py#L1344):
sum token rewards to one score, group by UID, subtract group mean, optionally divide by `torch.std(group_scores)+1e-6`, broadcast across response span. `torch.std` uses its default sample-standard-deviation convention here. Singleton group special case is mean 0/std 1, not evidence that singleton training equals GRPO.

[`compute_rloo_outcome_advantage`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/ppo_utils.py#L1260):
`(r_i-group_mean)*G/(G-1)` for G>1, zero for singleton. This is not standard normalized GRPO.

## 2. Sampling logprobs ≠ old-policy logprobs ≠ current logprobs

There are three separate arrays:

| Quantity | Source | Role |
|---|---|---|
| `rollout_logprobs` | Actual inference sampler | Behavior distribution at sampling time |
| `action_log_probs` in training input | Separate no-grad policy forward before updates | Fixed old-policy denominator for regular PPO-family loss |
| Worker-local `action_log_probs` | Differentiable current-policy forward during each update | Numerator through which gradients flow |

[`VLLM_LOGPROBS_MODE`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/inference_servers/utils.py#L46) is **`processed_logprobs`**, explicitly validated, not raw model logprobs. Sampler transformations affect their meaning.
[`VLLM server wire`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/inference_servers/vllm_server_actor.py#L583) forwards sampling parameters and captures sampled logprobs. With support capture, top-k must exceed 1 and support/logprob rows must align. Normal response serialization can clamp nonfinite sampled logprobs, another reason to record capture configuration rather than call all numbers exact without qualification.

[`HFModelWrapper.forward`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/workers/model_wrapper.py#L409):
divides logits by algorithm temperature; default branch gathers full-vocabulary next-token logprobs. Optional support replay instead normalizes **over each recorded sampler support set**.
[`sample_support_scores/_row_normalizers`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/sample_support_replay.py#L294) computes sampled-member logit minus support log-normalizer. Requires distinct support members including sampled token and positive temperature. Recording support and actually enabling replay are separate settings. A top-k/top-p processed sampler probability is not automatically the same as a full-vocabulary teacher-forced probability, even with identical weights.

[`fwd_logprobs_values_reward/_skip_policy_forward`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1346):
normally computes old-policy scores, optional frozen reference scores and critic values. Tracks rollout-versus-forward differences **on loss-mask-positive tokens**. Skip-old-forward path requires a loss that explicitly uses rollout anchors, rollout scores present, no reward KL and no off-policy correction. Includes rollout-IS/DPPO and CISPO only with its rollout anchor; not ordinary regular/dual-clip PPO.

[`ppo_policy_loss`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/ppo_utils.py#L557):
`ratio=exp(current-old)` with bounded safe exponent; negative minimum of unclipped/clipped advantage surrogates; optional dual clip for negative advantages; optional correction; masked sum.
[`compute_tis_ratio`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/off_policy_correction_utils.py#L24):
separate detached correction `exp(old-rollout)`, tokenwise or sequence product, capped. This is not the PPO ratio. Presence of correction does not validate missing/fabricated sampler probabilities.

## 3. Normalization → loss → backward → optimizer → checkpoint

[`_normalize_advantages`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1537):
optional batch z-scoring is separate from group normalization and objective reduction. Literal implementation takes `advantages.mean()` over the full tensor, then response-mask-weighted squared deviations; do not paraphrase it as an ideal masked-mean implementation.

[`apply_loss_reduction_to_advantages_minibatch`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/ppo_utils.py#L1152):
pre-scales advantages before summing policy loss:
- `token_mean`: divide by all positive loss-mask token mass in minibatch.
- `sequence_mean`: divide by batch size × each row's trainable-token count.
- `seq_mean_token_sum_norm`: divide by batch size × configured max sequence length.
- `prompt_mean`: divide each prompt group's tokens by number of prompts × group's trainable-token count.
- `token_mean_legacy`: per-microbatch token mean averaged over microbatches, not generally the global token mean.

These are scientific choices. Do not replace frozen co-train normalization with a seemingly cleaner option.

[`_execute_training_step`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1579):
pre-stage per-data-parallel minibatch chunks; loop update epochs/minibatches; `dispatch.forward_backward_from_staged`, then **one `dispatch.optim_step` per minibatch**. Worker performs microbatch accumulation.

[`PolicyWorker._forward_backward_micro/optim_step`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/workers/worker.py#L1069):
current differentiable scores → registered loss; optional reference KL and entropy; pre-scaled policy sum multiplied by data-parallel size to cancel gradient averaging; KL/entropy separately weighted across microbatches; strategy backward. Autocast uses CUDA bf16 in this path, not co-train's frozen fp16 configuration.

[`FSDPStrategy.backward/optimizer_step`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/distributed/fsdp_strategy.py#L148):
`loss.backward()` → gradient norm clipping → if norm nonfinite, clear gradients and return without update → otherwise `optimizer.step()`, scheduler step, zero gradients. Strategy preparation creates AdamW for trainable parameters. Backend ownership is real source behavior, not an executed optimizer receipt.

[`WorkerDispatch.save_weights_for_sampler`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/workers/worker_dispatch.py#L783):
synchronizes training policy to inference engine, makes requested LoRA adapter active, handles colocation/sleep/pause branches, resumes safely, increments weight version **after sync**. Ordinary noncolocated full-weight path pauses generation around broadcast. Delta path brackets reload internally; unmerged LoRA may swap in place.
[`worker cache reset`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/workers/worker.py#L601):
synchronous prefix caching resets on updates; fully async retains cached prefixes unless configured to clear. Generator cache salt derives from weight version. Thus sync completion, cache freshness and request version are separate evidence. Fully async source permits in-flight continuations across updates; do not call that the paper's fully on-policy setup.

[`RayPPOTrainer.save_checkpoints/load_checkpoints`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1725):
`global_step_N/policy`, optional critic, `data.pt`, `trainer_state.pt`, latest-step marker; resume restores optimizer and LR scheduler. Dataloader save/load exceptions are warnings, so exact dataloader continuation is not guaranteed by method success. Latest marker is written last with a normal file write; source comment's “atomic tracking” is not proof of crash-atomic directory publication.

[`FSDPStrategy.save_checkpoint/load_checkpoint`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/distributed/fsdp_strategy.py#L361):
rank files for model, optimizer and extra state; scheduler, RNG, rank/world-size metadata, HF configs and LoRA adapters; barriers and CUDA synchronization. Trainer additionally drains pending asynchronous writes before teardown. Checkpoint config, created files, restored state and replay-equivalent next update remain four distinct claims.

## 4. HEAD SkyCap/Responses versus older SkyRL-Agent

### HEAD SkyCap: graph capture, not a new optimizer

[`skycap/README`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skycap/README.md):
standalone capture package, no dependency on `skyrl`. Text mode forwards an OpenAI-compatible endpoint but cannot establish exact model token provenance. Token mode owns rendering and token-in/token-out requests, capturing sampled IDs/logprobs/support/routes.

[`tokens.turn.plan/_bridge`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skycap/src/skycap/tokens/turn.py#L75):
message-hash match first, then renderer-assisted bridge from deepest matched **model** node using exact prior prompt/completion. If bridging declines, full-render and reuse only nodes whose token slices match exactly. Remaining context becomes a fork. Compaction, edited history or stripped thinking cannot be treated as continued sampled tokens just because visible text resembles prior output.

[`samples._fill_tokens` and default path rule](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skycap/src/skycap/samples.py#L1):
one row per root-to-leaf path; each model node targeted in **exactly one row** by default, even if shared context appears in multiple rows. Only sampled portion of targeted model node gets loss mask 1. Client-authored assistant messages are context, not sampled actions. Missing route/support payloads are not silently equivalent to complete provenance.

[`ResponsesDialect`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skycap/src/skycap/dialects/openai_responses.py#L74):
regroups Responses items into template turns; records dialect; exposes parsed reasoning/function calls. Refuses `previous_response_id`/conversation state and background mode, automatic truncation/context management in token mode, encrypted reasoning, unsupported tools/content and trailing partial assistant continuation. Requires whole replayable history. Responses support is **not** full hosted OpenAI server-state semantics or evidence that arbitrary Codex sessions are trainable.

[`HarborSkycapGenerator._attempt`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/examples/train_integrations/harbor_skycap/harbor_generator.py#L217):
per-attempt trajectory URL → Harbor trial/harness → captured graph → Harbor verifier reward → `finish` → samples.
[`compose`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/examples/train_integrations/harbor_skycap/compose.py#L110):
split at first trainable token, preserve masks/logprobs/support; paths contiguous under same trajectory; last path marked `is_last_step`; same scalar trial reward on each row; current trainer computes the advantage once, then broadcasts. Requires stepwise trajectories and disabled stepwise merge per recipe.

**Error policy differs from paper:** Harbor composition masks the **whole prompt instance across repetitions** if any outcome has a masked stop reason, producing zero-reward placeholders. Context-length trajectories retain reward when only overlong loss filtering applies. Path-rule failure is not retried; transient unknown trial failures retry on fresh graphs. Do not transplant either policy into co-train without scientific approval.

### Older research agent path still present at HEAD

[`AgentRunner.run/_post_process_results`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-agent/skyrl_agent/agents/base.py#L235) dispatches initialize → generate → evaluate stages.
[`ReActAgent.step/_prepare_llm_input`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-agent/skyrl_agent/agents/react/react_agent.py#L114):
incrementally appends previous input + previous sampled action + new observations unless history resets; generates, records transition, parses and executes tool, appends result, terminates or continues.
[`ReActTrajectory.evaluate_trajectory`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-agent/skyrl_agent/agents/react/react_runner.py#L40) invokes task evaluator.

[`transitions_to_training_data`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-agent/skyrl_agent/functional/utils.py#L135):
merge adjacent transitions only when previous full input+action is an **exact integer-token prefix** of next input; otherwise flush datum and start new. Observation mask 0, action mask 1; split at first action. Missing action logprobs become zero placeholders.
Crucially [`SkyRLBackend.async_generate_ids`](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-agent/skyrl_agent/integrations/skyrl_train/skyrl_train_backend.py#L26) returns `"logprobs": None` even though it forwards sampled token IDs. Thus old agent adapter does **not** establish sampler-probability fidelity.

Older runner outputs `episode_nums`, `is_last_episode`, `traj_idx`; current trainer stepwise interface uses `trajectory_ids` and `is_last_step`. Older trainer override states special non-repetition behavior in its own docstring and calls inherited training helpers. Source co-location is not compatibility or execution proof for the old paper recipe on HEAD. No paper-era commit was pinned by this study. Root README separately gives old SkyRL-v0 reproduction commit `a0d50c482436af7fac8caffa4533616a78431d66`; that is not an asserted SkyRL-Agent paper reproduction pin.

## 5. Verified paper identity and bounded author benchmarks

Official arXiv: **2511.16108v1**, **“SkyRL-Agent: Efficient RL Training for Multi-turn LLM Agent”**, submitted **2025-11-20 07:05:19 UTC**. Abstract page listed only v1 when fetched. [Abstract/version](https://arxiv.org/abs/2511.16108v1), [full paper](https://arxiv.org/html/2511.16108v1). README announcement date 2025-11-26 is not paper submission date. The 2026 HEAD Responses feature is later work.

Author-reported, **not independently reproduced here**:
- SA-SWE-32B, Qwen3-32B base; 4.5K R2E-Gym instances; base 24.4% → 39.4% SWE-Bench Verified Pass@1 under simple ReAct, bash+editor, 40K context, 100 evaluation steps; selected checkpoint step 125.
- Training: batch=minibatch 64 tasks, G=8, 32K context, 50 turns, LR 1e-6; leave-one-out advantages; no standard-deviation or length normalization; KL/entropy disabled; modified Qwen3 template preserves earlier thinking. External-constraint termination is loss-masked **without changing rewards/advantages**.
- Dispatcher 1.55× speedup against bounded asynchronous batching; cited setup 2×8 H100 GPUs, batch 64×8 rollouts. HEAD dispatcher code uses unbounded `asyncio.Queue()` objects with bounded worker counts; paper's “bounded queues” should not be restated as a literal HEAD `Queue(maxsize=...)` implementation.
- Table 2: **4601 H100-hours** SA-SWE versus **9180 H100-hours** DeepSWE. Ratio about **1.995×**, 49.88% reduction from those rounded entries, not independently audited “more than 2×.” DeepSWE 36.4 is simple-ReAct score, 42.2 its reported own setup. Do not mix scaffold columns.
- Table 3: Terminal-Bench 0.1.1 13.75→16.25; BrowseComp-Plus 18.1→19.4; WebArena 3.68→4.6, average turn 15.8→17.0. Not SQL/scorer/evaluation evidence for co-train.
- Paper notes tool-serving bottlenecks and timeouts: deep-research iteration 2101.6s using one H200 summarizer versus 592.1s via Qwen API, later four GH200s. Those are separate case-study serving costs, not a free optimization or expected local speedup.

## 6. Tests meaningfully inspected, none executed

All below are source-read evidence only. No test suite, external model, framework or downloaded source was executed.

1. `tests/train/generators/test_skyrl_gym_generator.py::test_turn_output_masks_uncaptured_suffix`: concrete sampled IDs `[10,11]`, manually appended EOS and two observations yield `[1,1,0,0,0]`; support rows padded with -1.
2. `tests/train/generators/test_skyrl_gym_generator_chat_templating.py::test_skyrl_gym_generator_chat_templating_exact`: real `AutoTokenizer.from_pretrained` interface but **mock generation**; compares full rendered trajectory and exact masks, Qwen3 retained-thinking vs custom-template paths. Test implementation may download tokenizer if run. Not run.
3. `tests/backends/skyrl_train/utils/test_ppo_utils.py::test_compute_rloo_outcome_advantage_basic`: grouped scores `[6,3]`, `[9,12]`, singleton `[1]` → `[3,-3,-3,3,0]`. `test_compute_grpo_outcome_advantage_norm_std_false` checks `[1.5,-1.5,-1.5,1.5]`. Default normalized-GRPO test primarily checks shapes and adv=return, weaker than a full expected-value assertion.
4. Same file reduction tests: sequence mean 2.25; fixed-length normalization .7; legacy microbatch mean 8.5; prompt mean 4.25 and missing-boundaries exception. Valuable numeric fixtures, no evidence their choices match frozen co-train.
5. `tests/backends/skyrl_train/workers/test_policy_worker_loss_scaling.py::test_policy_forward_backward_loss_scaling_with_mocked_ranks`: two mocked ranks, two microbatches; checks DP-size backward scaling and reduced metrics for cross-entropy/dual-clip. **Mock strategy.backward, mock model, patched CUDA**, not gradient or distributed execution proof.
6. `tests/train/algorithms/test_skip_fwd_logprobs.py`: rollout-IS/DPPO/CISPO-rollout return finite losses with `old_log_probs=None`; regular/GSPO excluded. Does not establish equivalence of sampled and recomputed scores.
7. `skycap/tests/test_tokens.py::test_stripped_reasoning_forks_and_trains_each_sample_once`: strips thinking during replay; verifies fork, one target per row, second call unbridged. Fake renderer and mock engine.
8. `skycap/tests/test_responses_tokens.py`: tool loop bridges after first call, reasoning+empty-content replay matches, Chat/Responses send identical prompt IDs, unsupported token-mode fields refused before sampling. Uses OpenAI SDK against local capture stack, **fake renderer/mock engine**, not a real model.
9. `tests/integrations/harbor_skycap/test_harbor_skycap.py`: linear path exact mask/support alignment; summarizing trial produces two rows with same rollout identity and one terminal row; timeout masks whole instance; crash retries fresh URLs then masks; silent successful verifier without tokens is not rewarded. Fake trials/router, not live sandbox learning.
10. `tests/backends/skyrl_train/gpu/gpu_ci/test_save_load_checkpoint.py::test_save_load_checkpoint`: train step 1, save, train step 2, record logits, reload, repeat exact step 2, compare logits with **atol=0, rtol=0**. Strong source-specified optimizer/RNG continuation test, requires actual GPU/model runtime, **not executed**.
11. `test_trainer_full_checkpointing.py` inspected resume/save section: checks files, trainer/global step/path, then assigns global_step=3 and saves again. Its “continue training” label there is not itself a post-resume optimizer-update assertion; do not elevate to stronger proof than the code provides.

Pinned test URLs and inspected symbol line numbers are indexed in `skyrl-mechanisms-sources.json`. Additional cached tests not substantively read are explicitly not claimed as executed or verified.

## 7. License, backend and cost decision

[Root LICENSE](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/LICENSE): **Apache-2.0**. Preserve applicable license/notice/attribution on code reuse. Model/data/dependency terms separate; no blanket model/data license claim.

[HEAD pyproject](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/pyproject.toml):
Python >=3.12,<3.15; Transformers >=5.6.1,<=5.16.1; Ray 2.57.0; Linux training extras include Torch 2.13.0, vLLM .31.0 and CUDA/compiled components; FSDP/Megatron/JAX/Tinker surfaces exist. Detailed source chain above follows FSDP, not a claim of all-backend parity. These are repository metadata, not a resolved ABI-compatible installation. Paper version predates these pins. SkyCap also uses a separate renderer dependency. Neither “open source” nor Tinker-shaped API makes compute free; local self-hosting still costs GPU RAM/hours, CPU sandboxes, storage and engineering. Hosted external APIs incur separate serving charges. No dollar estimate inferred from H100-hours.

**Decision: do not switch co-train backend.** HEAD stack conflicts with frozen project assumptions, current host lacks native runtime, and source improvements offer no native-learning proof. Treat this as reference design/evidence taxonomy.

## 8. Ranked transferable ideas, numeric acceptance and approval needs

These are proposed future work, not implemented. Preserve G/model/scorer/eval/GRPO and launch refusal in every case.

1. **Token provenance + prefix/mask negative controls.** Extend offline reference evidence around the actual Trainer-selected template, not a hand-edited stock tokenizer.
   - Acceptance: 2 bound SQLite tasks, >=2 turns each; 100% prior sampled integer IDs preserved where continuation is claimed; 0 external/scaffold tokens trainable; 1 corrupted prefix token and 1 flipped observation-mask bit independently fail; 0 train/save/resume calls.
   - Approval: normal narrow test/spec review only if purely offline and existing tokenizer cache. Any new template/dependency/production fallback needs explicit owner approval. This does not resolve the existing native-helper identity rejection.

2. **Group-versus-path identity conservation audit.** Borrow SkyCap's rule “many rows, one rollout advantage,” not SkyCap as a dependency.
   - Acceptance: 2 prompt IDs × existing frozen G, one rollout with 3 synthetic prefix segments; exactly 2G outcome observations before/after segmentation; no extra reward sample or sampled-token duplicate; every sampled token targeted exactly once; all-identical-reward group remains finite with expected frozen-GRPO result; swapping 1 group ID fails.
   - Approval: offline provenance assertions only. Altering exclusion, truncation, grouping, normalization or rewards requires scientific amendment/owner approval. No silent conversion to paper RLOO.

3. **Separate probability semantics in evidence.** Label sampler distribution, old policy, reference policy and current differentiable policy independently, including temperature/support and weight version.
   - Acceptance: 100% captured action tokens have truthful sampler-presence labels; missing logs stay missing, never zero-filled then certified; 0 observation probability claims; 1 fabricated sampler-presence bit fails; capture model revision + tokenizer/template hash + sampling parameters. Current real bridge observation remains “no sampler logprobs.”
   - Approval: metadata-only offline design can proceed under existing scope; obtaining real sampler/current-model scores requires approved compatible runtime, cached model, exact backend budget and launch approval. Changing PPO denominator/support replay is algorithmic approval.

4. **Future update-and-restore proof ladder, deliberately not a launch plan.**
   - Acceptance after separate approval: on fixed nondegenerate existing task batch, >=1 real trainable adapter tensor changes by >0, >=1 finite nonzero gradient observed, optimizer step counter +1, frozen base tensors unchanged where LoRA promises that; model/optimizer/scheduler/RNG checkpoint present; restored next update matches uninterrupted continuation at a preregistered backend-appropriate tolerance (target exact equality when deterministic). Removing optimizer step must fail the weight-delta check; corrupting 1 saved state element must fail restore comparison.
   - Approval: explicit runtime/stack compatibility, model cache/revision, GPU/paid budget, output destination and training launch. The current spec allows construction only; all current six verification/authorization flags stay false. Numeric deltas alone do not prove learning/generalization; held-out evaluation remains separate and frozen.

5. **Only then stage-level timing and freshness diagnostics.** Borrow init/generation/tool/scorer/update/sync separation before any concurrency redesign.
   - Acceptance: 100% of a future approved fixed batch has task/rollout IDs and nonnegative stage durations; 0 duplicate/missing rollouts; 0 version-mismatched synchronous requests; report median/p90, failed-attempt count and masked-token count separately; do not claim speedup without >=3 paired measurements with unchanged tasks/G/sampling. Predeclare >=10% median wall-time improvement and 0 reward/mask/identity mismatches for any optimization claim.
   - Approval: offline schema/spec review first; runtime measurement/parallel serving needs explicit resource approval. Any async policy staleness, dispatcher behavior or retry/exclusion change needs scientific review. Paper's 1.55× is not promised here.

## Non-goals and unresolved gaps

No backend migration, scientific amendment, changing G/model/scorer/eval/GRPO, new dependency, launch, cloud job or fabricated learning receipt. No paper-era code commit established; no benchmark rerun; no CI execution records audited; no real model sampler, gradient, optimizer, weight sync or checkpoint restore executed. Complete pinned source reachability is established, not end-to-end execution. Current co-train remains runtime-blocked.

VERIFY_REAL: fetched official pinned public source and official arXiv v1; read meaningful mechanisms/tests; wrote scratch-only research artifacts. Tests/training/GPU/restore not executed.
