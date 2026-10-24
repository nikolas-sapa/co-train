# rLLM policy-update mechanisms, pinned source inspection

Date: 2026-10-23. Scope: static official-source research only.
rLLM pin: `4e828c81680e5a85b638ceedeaf09d1e90109ca8`.
co-train baseline supplied by parent: `ea6d2f6`; no git commands used to reverify it.

## Verdict

rLLM contains a real, statically connected agent → captured generation → grouped advantages → backend loss/backward/optimizer → sampler refresh/checkpoint path. This is not merely reward logging. **No training, gradients, weight changes, checkpoint creation or restoration were executed or verified here.**

The reusable contribution for co-train is explicit token/mask/provenance accounting, not a backend replacement. "Same agent code for eval/train" is supported by shared execution code, not a guarantee of identical model, sampling distribution, context construction, reward population or numerical objective. Backend selection is not scientifically neutral.

## Pin, era and citation

- [Official main ref](https://api.github.com/repos/rllm-org/rllm/git/ref/heads/main) returned this exact pin during inspection. [Commit metadata](https://api.github.com/repos/rllm-org/rllm/commits/4e828c81680e5a85b638ceedeaf09d1e90109ca8) dates it **2026-10-09T01:22:20Z**, message `feat(fireworks): default to R3 router replay (#934)`. "HEAD on 2026-10-23" is an observation date, not commit date.
- [Pinned README](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/README.md) explicitly cites `rllm2025`, *rLLM: A Framework for Post-Training Language Agents*, with `note={Notion Blog}` and original URL https://pretty-radio-b75.notion.site/rLLM-A-Framework-for-Post-Training-Language-Agents-21b81902c146819db63cd98a54ba5f31 . This is not an arXiv identifier or evidence that the 2025 blog describes the 2026 HEAD implementation. The original Notion body was not fetched.
- [Pinned pyproject](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/pyproject.toml#L77-L97) declares `verl==0.8.0`, `vllm==0.22.1`, `torch>=2.10.0`, `transformers>=5.5.3`, `flash-attn==2.8.3`; default dependencies include `tinker>=0.22.2`, `tinker-cookbook>=0.4.1`; Fireworks uses `fireworks-ai[training]==1.2.20` plus cookbook commit `bba676c6d00bd595f9453e0b2165b7457a01e0d5`. These are declarations, not an installed compatible lock.
- [Public trainer export](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/__init__.py) is `unified_trainer.AgentTrainer`. Do not accidentally inspect/import the similarly named legacy [agent_trainer.AgentTrainer](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/agent_trainer.py#L6-L54), which accepts only verl workflows and says older agent/env/SDK interfaces were removed.
- Current source also contains `trainer/deprecated/` modules. Older reports about SDK collectors, old `TinkerAgentTrainer`, `DataParallelPPOActor.update_policy`, FSDP worker topology or different dependency versions cannot be pasted onto HEAD. No particular older report/pin was supplied for a line-by-line historical comparison.
- Concrete era mismatch within the current tree: `tests/test_verl_policy_loss.py::TestVerlActorPatch` imports `patch_verl_actor_for_loss_override`, but that symbol is absent from pinned `rllm/trainer/verl/patch.py`. Current path instead installs `CustomPPOLoss` into EngineWorkers. Static finding, not an executed ImportError.

## Actual end-to-end chain

### 1. One agent function, explicit session routing

[unified_trainer.AgentTrainer.__init__/train](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/unified_trainer.py#L1002-L1111) accepts an `agent_flow` plus evaluator/hooks and dispatches a backend launcher. The [math-tool cookbook](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/cookbooks/math_tool_agent/train.py#L19-L37) passes the ordinary `math_tool_agent` and `math_tool_evaluator` into this API.

[AgentFlowEngine._run_flow_only](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/agentflow_engine.py#L575-L637) creates a gateway session, picks train versus validation sampling parameters, and calls `run_agent_flow` with:
`AgentConfig(base_url=session_url, model=self.model, session_uid=uid, is_validation=..., sampling_params=...)`.
The agent uses an OpenAI-compatible client against this URL, not direct access to optimizer state.

[interleave_tasks](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/data/utils.py#L28-L39) repeats each task G times with one shared task ID. The engine produces episode IDs with a final rollout-index suffix. G is a sampling group size, not the number of tool calls.

### 2. Gateway obtains sampled tokens/logprobs, does not reconstruct them from text

[SessionRoutingMiddleware._mutate](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/middleware.py#L124-L140):
- Adds `logprobs=True` and `return_token_ids=True` only when those keys are absent, not unconditionally over an explicit false.
- Overrides the request model when gateway model pin is configured.
- Applies session sampling parameters with `payload.update(sp)`; configured session keys override agent-provided keys, absent keys pass through.

[data_process.extract_prompt_token_ids/extract_completion_token_ids/extract_logprobs/build_trace_record](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/data_process.py#L23-L217) extracts `prompt_token_ids`, `choices[0].token_ids`, chat `.logprobs.content[].logprob` or completions `.token_logprobs`, then constructs `TraceRecord`. Streaming accumulates token/logprob deltas. These are upstream sampling records. Logprob extractors omit null entries; token/logprob alignment still needs validation.

For Tinker, [create_tinker_handler](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/gateway/tinker_adapter.py#L44-L112) translates its native `ModelOutput` into the same vLLM-like response fields.
[TinkerEngine.generate/assemble_model_output](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/rollout/tinker_engine.py#L318-L375) calls `sampling_client.sample_async`, uses `sequences[0].tokens` and `.logprobs`, and parses text/tool calls afterward. Do not substitute text re-tokenization for those sampled IDs.

### 3. Trace → Step → Trajectory → Episode, then evaluator reward

[trace_record_to_step](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/trace_converter.py#L31-L73) constructs `ModelOutput(prompt_ids, completion_ids, logprobs, finish_reason, weight_version)` and a `Step` containing original messages plus response.

[Step.model_post_init](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/types.py#L149-L167) backfills convenience training fields and asserts response/logprob equal length **when logprobs are nonempty**. Empty logprobs are not rejected there.

[enrich_episode_with_traces](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/agentflow_engine.py#L102-L248) matches traces chronologically/positionally to agent steps, preserving action/reward/done. A trajectory with no agent steps absorbs remaining traces. This is positional bookkeeping, not semantic proof that concurrent multi-agent calls belong to the right role.
Training strictness rejects empty token IDs and short trace counts, with an explicit trailing-malformed-trace exception. **No traces at all returns the original episode with a warning**, even in strict mode; this is not universal fail-closed capture.

[_finish_episode](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/agentflow_engine.py#L646-L698) enriches with `strict=not is_validation`, invokes the evaluator, fills missing trajectory reward with `eval_output.reward`, and preserves any already-set per-trajectory rewards.
Canonical [Episode/TrajectoryGroup identity](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/types.py#L317-L409) splits IDs at the final colon, preserving hierarchical task IDs.

### 4. Transform/filter/group → GRPO advantages

[UnifiedTrainer._train_batch_async](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/unified_trainer.py#L521-L570) orders:
generation → episode-to-group transform → rejection/filtering → backend transform → backend processing → advantage stage → policy update. Empty episode/group paths return without an update.

[transform._build_trajectory_groups/_default_traj_grouping_hook](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/algorithms/transform.py#L63-L152):
- Groups by `f"{episode.task_id}:{trajectory.name}"`, not one batch-wide comparison.
- Rejects colons in trajectory names; skips zero-step trajectories and compact-filtered terminations.
- Missing trajectory rewards must be missing for the whole group or present for the whole group. In broadcast mode all-missing rewards propagate from each trajectory's final step.
- Name imputation may rename unnamed/default trajectories. Filtering can shrink G. Retained G must therefore be measured, not inferred from requested rollout count.

[collect_reward_and_advantage_from_trajectory_groups](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/algorithms/advantage.py#L165-L250) requires broadcast mode, selects estimator per role or default, computes one scalar per trajectory, and writes it to every Step.

Exact [GRPO helper](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/algorithms/rl_algo.py#L6-L18):
- G > 1: `A_i=(r_i-mean(r))/(np.std(r)+1e-6)`, population std (`ddof=0`), or centered only if normalization disabled.
- G <= 1: mean=0, std=1, so a singleton reward becomes approximately its reward, **not zero**.
- Equal-reward groups with G>1 produce zero advantages. Metrics distinguish informative, all-success and all-failure groups.
- Precomputed advantages are a separate mode. Tinker transform uses `any(step.advantage is not None)` to skip all recomputation; incomplete mixed precomputed inputs can fail/drop later. Do not treat that shortcut as a completeness certificate.

### 5. Prefix merging, next-token shift and masks

[Tinker trajectory_to_datums](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/transform.py#L45-L151):
- Maintains actual prompt+sampled-response token sequence.
- If next prompt starts with that full exact sequence, appends only new observation tokens, then next sampled action.
- Prefix break emits current Datum and starts another. It does **not** repair/re-tokenize the old actions to force a match.
- Prompt/new observation positions: sampled logprobs=0, advantage=0, mask=0. Response action positions: sampled logprobs preserved, scalar advantage broadcast (or per-token list), mask=1.
- Model input is full sequence excluding last token; targets/old logprobs/advantages/mask all shifted by one (`[1:]`). Equal aligned lengths asserted.
- Missing logprobs/advantage are assertion errors; group transform catches assertion errors, drops malformed trajectories, and reports `batch/dropped_malformed_sequences`.

[verl _process_trajectory](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/verl/transform.py#L248-L402) similarly merges exact cumulative token prefixes into rows with response `[A0, obs1, A1, ...]`, `response_mask=[1...,0...,1...]`. Prefix breaks create multiple rows sharing trajectory UID/scalar advantage. Prompt left-padding and response right-padding/truncation occur in `_batch_tensors_and_build_data_proto`; attention mask and response/loss mask are distinct.
Verl is more permissive about absent logprobs, can omit `rollout_log_probs`, and contains short-logprob zero-padding logic. That is not equivalent to a strict sampler likelihood receipt.

[TokenAccumulator.build_next_prompt](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/token_accumulator.py#L85-L153) delegates to renderer `bridge_to_next_turn(previous_prompt_ids, previous_completion_ids,new_messages)`. Divergent message prefix resets accumulation; unprovable bridge returns None and falls back to normal chat. [Proxy](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/proxy.py#L137-L179) rewrites subsequent cumulative calls to tokenized completions when enabled. [Base config](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/config/rllm/base.yaml#L149-L163) defaults `cumulative_token_mode:false`. This is optional infrastructure, not proof co-train's real tokenizer prefix boundary is fixed.

## Sampler likelihood versus old/current/reference policy

### Tinker: sampled logprobs are denominator, server owns gradients

[TinkerPolicyTrainer._get_forward_backward_futures](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/tinker_policy_trainer.py#L161-L201) sends shifted `target_tokens`, sampled `logprobs`, and advantages to `training_client.forward_backward_async`. `_remove_mask` drops the explicit mask; **zero advantages perform RL masking**. GRPO maps to `"ppo"`; REINFORCE/RLOO map to `"importance_sampling"`. No separate proximal old-policy forward appears in this path. Returned `"logprobs"` are learner forward-pass logprobs, not newly sampled values.

[Official PPO docs](https://tinker-docs.thinkingmachines.ai/tinker/losses/ppo/) define `ratio=exp(target_logprobs-sampling_logprobs)`, clipped/unclipped minimum objective, `loss=-objective.sum()`. [Loss docs](https://tinker-docs.thinkingmachines.ai/tinker/losses/) explicitly sum token losses. Pinned rLLM transform broadcasts scalar advantages without dividing by response length. **Do not claim this path implements seq-mean-token-mean or equal per-trajectory weighting.** A comment in verl transform about matching Tinker's per-Datum aggregation is not stronger evidence than actual transform plus documented API objective. Exact service-side cross-request/distributed scaling is not inspectable from this repo.

Pinned Tinker code also does not pass `loss_fn_config`, `algorithm_config.eps_clip`, `kl_beta`, `loss_agg_mode` or TIS weights into this call. Thus sharing `AlgorithmConfig` does not prove those knobs have equal backend semantics or preserve co-train beta=.04. Current provider docs mention custom clipping while also retaining older fixed-.2 prose; rLLM here relies on provider defaults, not an explicit clip receipt.

`optim_step_future` creates `AdamParams(learning_rate*schedule,beta1=.9,beta2=.95,eps=1e-8)` and calls `optim_step_async`, awaited by `TinkerBackend.update_policy`; fused mode queues fwd/bwd then optimizer futures. Actual tensor `.backward()` and optimizer implementation are remote service internals, not local source verified here.

### verl: separately recomputed proximal policy by default

[VerlBackend.process_backend_batch](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/verl/verl_backend.py#L627-L704):
- Normal/default backend config `bypass_mode:false`: `compute_log_prob` on current actor before updates yields fixed batch `old_log_probs`; captured sampler values remain `rollout_log_probs`.
- Bypass mode: assigns `old_log_probs=rollout_log_probs` and asserts their presence.
- Optional TIS computes weights from `old_log_probs-rollout_log_probs`, mask and cap (default cap2).
- Separate reference logprobs come from ref policy or actor with LoRA disabled. This is a third policy view, not the sampler or proximal denominator.
- Off-policy metrics compare sampled and proximal logprobs on the action mask. Equality cannot be inferred just from same model name.

`update_policy` → [_update_actor_with_loss_routing](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/verl/verl_backend.py#L745-L825) → actor EngineWorkers `.update_actor`, with mini-batch row count, global rollout denominator, PPO epochs, shuffling and optional per-role loss override.
[CustomPPOLoss](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/verl/verl_backend.py#L64-L91) delegates to verl `ppo_loss`.

### External verl optimizer chain, version matched

Declared verl0.8.0 tag resolved to immutable commit **`7aed6b230776f963fa09509c10d9c3a767d1102c`** via [tag ref](https://api.github.com/repos/verl-project/verl/git/ref/tags/v0.8.0). Inspected upstream source, not installed/executed:

1. [EngineWorkers.update_actor/train_mini_batch/train_batch](https://github.com/verl-project/verl/blob/7aed6b230776f963fa09509c10d9c3a767d1102c/verl/workers/engine_workers.py#L234-L350) iterates PPO mini-batches/epochs and calls engine training.
2. [BaseEngine.train_batch](https://github.com/verl-project/verl/blob/7aed6b230776f963fa09509c10d9c3a767d1102c/verl/workers/engine/base.py#L112-L127): `optimizer_zero_grad()` → `forward_backward_batch(...forward_only=False)` → `optimizer_step()`.
3. [ppo_loss](https://github.com/verl-project/verl/blob/7aed6b230776f963fa09509c10d9c3a767d1102c/verl/workers/utils/losses.py#L57-L144) uses current model logprobs, fixed old logprobs, advantages and response mask. Optional entropy and reference-KL terms are separate.
4. [compute_policy_loss_vanilla](https://github.com/verl-project/verl/blob/7aed6b230776f963fa09509c10d9c3a767d1102c/verl/trainer/ppo/core_algos.py#L1279-L1362): ratio=`exp(clamp(logp_current-logp_old,-20,20))`, asymmetric PPO clipping, negative-advantage dual-clip branch, optional rollout IS weights, then masked aggregation.
5. [FSDPEngine.forward_backward_batch/optimizer_step](https://github.com/verl-project/verl/blob/7aed6b230776f963fa09509c10d9c3a767d1102c/verl/workers/engine/fsdp/transformer_impl.py#L617-L704): micro-batch forward → scaled/unscaled `loss.backward()` → gradient clipping → scaler step/update or finite-grad `optimizer.step()`. Nonfinite gradients can skip updates. This establishes a concrete FSDP route, not every supported engine route.

[agg_loss](https://github.com/verl-project/verl/blob/7aed6b230776f963fa09509c10d9c3a767d1102c/verl/trainer/ppo/core_algos.py#L1138-L1197) distinguishes:
- token-mean: sum masked token losses / global active-token count;
- seq-mean-token-sum: token sums, then global sequence denominator;
- seq-mean-token-mean: per-row active-token mean, then global sequence denominator.
rLLM decouples emitted row count from original rollout count in batch padding/update metadata, so merging/context splits/padding affect interpretation. A split trajectory has multiple rows; do not assert exact per-trajectory equal weighting without measuring denominator and segments. Multi-loss routing has an explicit TODO retaining older flat mini-batch semantics.

### Fireworks: third, nonidentical implementation

[FireworksPolicyTrainer.forward_backward_from_trajectory_groups/optim_step](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/fireworks/fireworks_policy_trainer.py#L419-L545) reuses Tinker Datum transform, rebuilds `loss_mask`, normally recomputes proximal logprobs with `.forward()`, passes both proximal and inference logprobs to a pinned external cookbook builtin-loss builder, and invokes remote `.forward_backward`.
For seq-mean-token-mean it divides advantages by active action-token count per sequence and requests `NUM_SEQUENCES` grad normalization in `.optim_step`; token-mean uses `NUM_LOSS_TOKENS`. Remote builtin kernel, not rLLM-local autograd.
Its checkpoint functions save/hot-load sampler weights and separate DCP state; `_try_resume` calls `load_state_with_optimizer`. Full Fireworks cookbook/kernel implementation was not inspected. Default R3 replay and default bypass=false differ from Tinker.

## Policy weight identity and checkpoints

- Tinker startup creates one LoRA training client, saves initial sampler weights, and creates the sampling client from their returned path. [on_train_start/on_policy_updated](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/tinker_backend.py#L368-L424) propagates that exact client to rollout engine and refreshes it after updates.
- [save_checkpoint_and_get_sampling_client](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/tinker_policy_trainer.py#L337-L376): nonpersistent sync calls `save_weights_and_get_sampling_client_async`; persistent saves both `save_state_async(name)` and `save_weights_for_sampler_async(name)`, awaits both, and writes `checkpoint.json` containing state path, sampler path and dataloader state plus latest-step tracker. Resume uses `create_training_client_from_state_async(state_path)` and corresponding sampler path. These are distinct full-state and inference artifacts.
- [verl on_batch_end/on_policy_updated](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/verl/verl_backend.py#L844-L895) saves at configured frequency; colocated mode updates rollout weights at batch end, separated mode through policy-update hook. [save_checkpoint/load_checkpoint](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/verl/utils.py#L222-L307) delegates actor checkpoint RPC, separately saves `data.pt` dataloader state, and resumes actor+loader. HDFS restore explicitly unsupported.
- Async [_perform_weight_sync](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/unified_trainer.py#L812-L827) pauses/drains generation when partial rollouts disabled, increments version, runs backend sync, updates rollout-engine/gateway version, then resumes. Response-supplied weight_version takes precedence over gateway fallback stamps. A version counter is not a content hash or atomic proof across all in-flight calls.
- Model string, version stamp and checkpoint configuration alone do not prove sampler/learner weights match. Required runtime evidence would include immutable model+adapter identities, actual sampler artifact, learner/checkpoint state, per-step version provenance and measured likelihood discrepancy.

## "Same agent for evaluation and training": qualified yes

[eval.runner.run_dataset](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/eval/runner.py#L29-L110) accepts the same `AgentFlow` interface and constructs `AgentFlowEngine`; training supplies the agent to that engine too. Both route calls through gateway and use the same evaluator protocol. This verifies code reuse statically.

Not verified: same checkpoint, template, sampling params, tool schema, sandbox, evaluator identity, budget or held-out membership. `is_validation` is exposed to agent code; train/val sampling params are separately enforced; validation tolerates missing token IDs; G and n_val differ. The claim does not turn an ordinary hosted text-only eval into trainable token/logprob data, and it does not establish scientific parity for co-train.

## Tests inspected, none executed

All listed test files were fetched and inspected as source. No pytest, imports, remote sampler, GPU or paid API jobs ran.

| Test source | Meaningful assertions | Limit |
|---|---|---|
| [test_tinker_transform.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_tinker_transform.py) | Single-step shifted targets/logprobs/advantages, exact masks, cumulative merge, independent/mixed prefix splits, image chunks, missing logprobs/advantage and mismatch negatives | Synthetic token sequences; no real tokenizer/generation/gradient |
| [test_verl_transform.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_verl_transform.py) | rollout logprobs preserved, absent/mixed availability, multi-step response mask `[1,1,0,1,1,1]` | Mock tokenizer/engine; no proximal likelihood/optimizer check |
| [test_trajectory_grouping.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_trajectory_grouping.py) | Hierarchical task-ID parsing, colon rejection, per-task centered advantages approx `[-1,1,-1,1]`, role override | Group arithmetic, not learning |
| [test_trace_converter.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/engine/test_trace_converter.py) | Captured fields/tool calls into Step and metric calculations | Constructed records |
| [test_token_accumulator.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/tests/unit/test_token_accumulator.py) | Prefix divergence/shrink/reset, no re-tokenized assistant append, cumulative state | Renderer fixtures, not co-train cached tokenizer |
| [test_tinker_checkpoint.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_tinker_checkpoint.py) | Auto/disable/explicit resume-directory resolution, missing checkpoint negatives | No optimizer-state restore or restored generation |
| [test_tinker_gateway_integration.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/integration/test_tinker_gateway_integration.py) | Real completion, token-data trace, Step roundtrip, streaming, multi-turn tools | Needs `TINKER_API_KEY`, auto-skips without it; sampling not training |
| [gateway test_training_workflow_e2e.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/tests/integration/test_training_workflow_e2e.py) | Session lifecycle, multiturm/streaming trace capture | Needs real vLLM, auto-skips; "training workflow" title does not mean optimizer ran |
| [test_verl_policy_loss.py](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/test_verl_policy_loss.py) | Config/loss routing/grouping assertions | Patch tests reference absent old patch; some tests only check symbols/no-crash, not claimed override behavior |

No inspected test establishes nonzero parameter delta, finite nonzero gradient, changed next-step likelihood, successful checkpoint restoration, or evaluation improvement. No conclusion about uninspected tests.

## License, API and cost boundaries

- [Pinned LICENSE](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/LICENSE): Apache License 2.0. Permissive source reuse requires applicable license/notice/attribution obligations. It grants neither hosted compute credits nor model-weight/data rights. Dependency and model licenses require independent review before adoption.
- Tinker "single-machine" in README describes controller ergonomics, **not free local training**. `ServiceClient`, remote sampling/training/optimizer/state APIs require an account/API access and paid metering when used against service. No credentials read here.
- [Official Tinker machine-readable pricing](https://tinker-docs.thinkingmachines.ai/tinker/models.json), fetched 2026-10-23: Qwen/Qwen3-8B is $0.195/M prefill, $0.039/M cached prefill, $0.60/M sampled, $0.44/M trained tokens; [pricing page](https://tinker-docs.thinkingmachines.ai/tinker/models/) says checkpoint storage $0.10/GB/month and training-client forward-only passes billed at training rate. Illustrative 1M uncached prefill +1M sample +1M train = $1.235 before storage/extra passes, not a job quote. This is **not** a price or support promise for co-train's unsloth/Qwen3-0.6B, which was absent from fetched training roster.
- Fireworks requires hosted trainer/deployment provisioning or attaching existing jobs; code defaults can create them. [Official pricing search result](https://fireworks.ai/pricing) says dedicated Training API jobs per GPU-hour; [official estimator](https://docs.fireworks.ai/fine-tuning/rft-cost-estimator) says GPU-seconds consumed and warns estimates are not budgeting forecasts. No shape/rate quote or account was inspected. Approval must cover trainer, rollout deployment, reference trainer if used, storage, sandbox and external evaluator costs.
- verl is self-hosted distributed training, not a per-token rLLM API bill; hardware, storage and optional sandbox/vendor costs remain. Installing the declared stack would not solve co-train's frozen environment rules.
- Actual model/API/GPU spend in this inspection: none. Research FetchUrl/WebSearch calls only; platform research-tool billing was not inspected.

## co-train comparison and bounded ideas

Read `/Users/nikolassapalidis/Developer/co-train/spec/native-training.md`, relevant `train/grpo_ptc.py`, and constants in `train/dead_group_probe.py`. Frozen values observed: `unsloth/Qwen3-0.6B`, G=4, LoRA rank32, beta=.04, LR=3e-5. Native spec preserves task-bound SQLite SQL scorer, one actual discovered `run_program`, exact model revision/context admission, fp16, completion/turn budget, eval membership and native optimizer ownership. Current Darwin runtime lacks torch/TRL/Unsloth/vLLM/Accelerate/PEFT and has known frozen/native Transformers conflict. Spec records real prefix mismatch, no sampler logprobs and no actual learning. Those remain blockers.

**Non-goals:** no rLLM/backend replacement; no dependency upgrade, model/G/beta/LR/scorer/prompt/tool/evaluation-membership change; no production-template identity shim; no installation/download/launch/GPU/paid call. Nothing in this report opens a gate.

Proposed ideas only, no implementation:

1. **Offline token receipt contract, separate from learning proof.** Reuse already approved source-bound references and fixtures, without importing rLLM. Require on every admitted training Step `len(response_ids)==len(sampler_logprobs)>0`, finite logprobs, zero prompt/tool loss mask, action-only mask, exact model/template/tool/scorer hashes and sampler-versus-recomputed labels. Numeric acceptance: 10 positive fixtures and 10 independently corrupted fixtures; 0 corruptions admitted; 100% IDs/logprobs/masks aligned. Approval: parent before new project files; real receipts separately require approved runtime. Fixtures remain labelled synthetic.

2. **Prefix/segmentation diagnostics, not template repair.** Preserve real sampled IDs, measure exact prefix breaks and segment count. Numeric acceptance: 3-turn cumulative fixture yields exactly1 segment; mutate exactly1 prior token yields exactly2 segments; tool observation changes contribute exactly0 loss-bearing tokens. Cached stock tokenizer's known mismatch remains a failure, not a green fallback. Approval: offline reference/test scope only; any production template change needs explicit owner decision and a new spec.

3. **Fixed-G learning-signal audit.** For 2 existing fixture tasks ×G4, report requested/retained G, per-task reward mean/std, all-success/all-failure/informative counts and GRPO advantages. Numeric acceptance: 8 trajectories retained, exactly2 groups, mixed rewards `[0,0,1,1]` produce approximately `[-1,-1,1,1]` within1e-5 under the specified formula, uniform groups produce0 within1e-8. Zero automatic filtering/resampling/task-selection changes. Approval: parent for test additions; scientific approval before changing normalization, filtering or frozen G.

4. **Approved one-update/checkpoint receipt spec for existing native backend.** Plan only until runtime/dependency gates are owner-approved. Numeric acceptance proposal: exactly1 optimizer update on existing 2 tasks ×G4; finite nonzero grad norm; ≥1 trainable adapter tensor changes with max_abs_delta>0; immutable before/after model+adapter IDs and real sampler logprob receipt; checkpoint full-state reload reproduces adapter tensors exactly and deterministic fixed-token forward logits within1e-5 absolute on declared dtype/device. Independent negative controls: zero/skip optimizer must fail delta check, corrupt checkpoint identity must fail restore check, mask1 tool token must fail mask check. Numeric tolerances need owner ratification before execution, especially fp16 forward tolerance. No fixture can satisfy real-learning fields. Approval: explicit runtime stack/model-cache/context/GPU/cost/checkpoint-output admission; no held-out membership/scorer changes and no new training backend.

## Verification and limitations

Source fetches succeeded for cached files. GitHub API JSON was parsed from Markdown fences without executing downloaded code. Symbol/line references are to immutable pins except explicitly labelled live provider docs. Cached `.py` files are inert fetched source text, never imported or executed; fetched Markdown may not be byte-identical to raw Git blobs. Source manifest records Git blob identities where available.

No git/clone/install, model/data download, third-party execution, GPU/paid job, nested agent, project edit, reference edit, commit or push. Only requested scratch report, source manifest and optional cache were written. Static optimizer reachability is not executed training.

VERIFY_REAL: official rLLM main ref and commit metadata matched supplied pin; complete FSDP source route reaches backward/optimizer and checkpoint RPCs; no runtime learning/restore claims. Deliverable existence/manifest checks are separate local file checks, not framework tests.
