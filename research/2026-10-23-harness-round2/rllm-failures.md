# rLLM trace admission, pinned source review

Review date: 2026-10-23. Repository: `rllm-org/rllm`. Exact pin: `4e828c81680e5a85b638ceedeaf09d1e90109ca8`. GitHub commit metadata dates this commit **2026-10-09**, not October 23. “HEAD 2026-10-23” is the supplied snapshot label; this review did not independently compare the default branch HEAD.

## Verdict and boundaries

**Useful admission-contract ideas, not a backend recommendation.** Trace capture, successful agent completion, and trainer-admissible evidence are separate states. This pin has real protections (strict nonempty token checks, retry cleanup, pending-write flush, prefix splitting, shifted masks), but not an end-to-end exactly-once, attempt-bound, terminal-state, sampler-version admission contract.

Most actionable source-derived counterexamples:
1. Concurrent calls in one session can receive another call's reward/action/done through positional enrichment.
2. Retry cleanup failures are logged and ignored while reusing the same session.
3. Partial streams can be persisted and pass nonempty-ID enrichment without a finish reason.
4. Cumulative streaming sends correct client text but builds the captured trace from unconverted completions chunks, losing that text.
5. Streaming tool-call fragments become separate malformed tool calls.
6. Malformed trajectories can be dropped **after** group advantages were calculated, changing the trained group without recalculation.

These are static control-flow counterexamples, **not executed upstream reproductions**. No rLLM import, upstream tests, torch, model, generation, optimizer, checkpoint restore, GPU or paid job was run. Only public source retrieval and local scratch-file writes occurred.

Co-train context: parent supplied `ea6d2f6`; read `/Users/nikolassapalidis/Developer/co-train/spec/native-training.md` fresh. Its header cites baseline `d6d04f0`, so the local file read is not independently verified as the historical `ea6d2f6` blob. Its protected boundaries remain authoritative: unchanged GRPO/model/G/scorer/evaluation/science and frozen dependency guards, no replacement of TRL/Unsloth, no launch authorization. Local no-torch/no-CUDA state cannot prove learning. No project/reference edits, git commands, clones, installs, model/data downloads, nested agents or third-party code execution.

## Findings

### F1. Positional trace matching is unsafe for within-session concurrency

**High-confidence conditional misattribution.** `enrich_episode_with_traces` explicitly matches traces by position, not request/step identity. Memory storage orders by persistence insertion; SQLite orders by persistence-time `created_at`. `build_trace_record` stamps time only after response capture. Thus chronological here means completion/storage order, not logical agent-step order. [S1, S2, S3, S4]

Concrete schedule: agent step list is `[A, B]`; both calls use session `task:0`; A takes 100 ms, B takes 10 ms. Store returns `[trace_B, trace_A]`. Both traces have valid prompt/completion IDs and equal counts. Enrichment copies A's action/reward/done onto B's token sequence, then B's onto A's. Two steps and two traces satisfy the checked count relation. No trace/agent ID equality is checked.

Related count hole: one agent step and two **valid** traces are not rejected as “too many.” Only extra malformed suffixes are trimmed. The first trace is consumed and the valid surplus has no final consumption check. An SDK retry/background auxiliary call can therefore shift which call receives the reward. Do not confuse UUID uniqueness with semantic deduplication.

**Negative control:** two concurrent same-session calls, reversed completion order, distinct actions/rewards `0/1`, must yield **0 cross-bindings**; one valid surplus trace must yield **1 explicit rejection**, not silent omission. Existing concurrency tests cover 10 separate sessions, 5 sessions with sequential 3-turn loops, and 50 separate sessions, not two overlapping cumulative calls in one session. [T1]

### F2. Retry attempts reuse identity; cleanup failure does not fail closed

`AgentFlowEngine.process_task_with_retry` uses `uid = f"{task_id}:{rollout_idx}"` on every attempt. Retry calls `adelete_session(uid)`, but catches cleanup errors, logs, and continues. No attempt generation/nonce participates in the session key. [S1]

Concrete schedule: attempt 1 stores valid trace A then evaluator throws; deletion before attempt 2 fails; attempt 2 stores valid trace B and returns one agent step. Fetch returns `[A,B]`. F1's surplus-count hole lets the attempt-2 reward attach to A, with B ignored. An earlier in-flight request completing after cleanup is another contamination route: deleting the session does not cancel requests or tombstone the old generation.

**Important mitigation actually present:** `GatewayManager.aget_traces` and `adelete_session` flush pending writes first. Do not report a blanket “reads never flush” bug. This drains a snapshot of queued persistence tasks, not all still-running generations or a failed previous attempt's future writes. [S5, S6]

**Negative control:** three forced attempts, 1 unique attempt identity each, late completions from attempts 1/2 plus a failed delete. Accepted attempt must contain **exactly 1 expected attempt's traces and 0 others**; cleanup failure must produce a bounded explicit failure or isolation. Retry selection of eventually valid rollouts also changes the observation distribution; co-train must not adopt success-only retry/filter semantics without scientific approval.

### F3. Streaming capture is not terminal-success admission

`Proxy._handle_streaming` captures chunks and in its `finally` persists whenever `session_id and chunks`. Cumulative streaming similarly ingests and persists partial chunks in `finally`. Neither branch requires `[DONE]`, a finish reason, a successful HTTP status, or a cancellation disposition. `build_trace_record_from_chunks` allows `finish_reason=None`; strict enrichment checks nonempty IDs, not terminal status. [S4, S7, S1]

Concrete input: first chunk contains prompt `[1,2]`; next has completion `[3]`, logprob `[-0.2]`, content `"partial"`; connection ends before a finish chunk. A captured record can have nonempty aligned IDs and `finish_reason=None`, and it passes the inspected strict enrichment predicate. Whether a particular ASGI cancellation permits final persistence depends on cleanup-await behavior; an early EOF with those chunks suffices for the static counterexample. Do not claim every cancellation is durably captured.

Remote path is more explicit: an unfinished `RemoteTaskResult` has reward overwritten to `0.0`, but existing traces still become training steps. Its termination reason is preserved or becomes UNKNOWN. Default compact-filter dataclass flags are all false. A configured timeout/error filter can change this; the gateway alone does not quarantine it. [S8, S9]

**Negative control:** cut a 3-chunk stream after chunk 2 and separately force timeout, cancellation and HTTP error. Each incomplete trace gets **0 training admissions**, a distinct terminal disposition and **1 ledger record**. If zero-reward partial learning is intentionally chosen instead, that is a scientific/scorer policy requiring owner approval, not an infrastructure fix.

### F4. Cumulative streaming loses captured answer text while client text is correct

`_handle_cumulative_streaming` appends the upstream `/v1/completions` chunk to `chunks`, then separately translates `choices[0].text` to outbound `delta.content`. At the end it passes the **original** chunks to `build_trace_record_from_chunks`, which reads only `choices[0].delta.content`, not `text`. `trace_record_to_step` reads content from that captured response message. [S7, S4, S10]

Concrete input: one upstream chunk with `text="42"`, token IDs `[42]`, one logprob, and later `"stop"`. Client sees `"42"`; captured `response_message` has only assistant role, so `Step.model_response/output/content` is `""`. Token-based training may remain structurally valid while text-based evaluator sees a different answer. Actual reward impact depends on evaluator/agent fields, not guaranteed for every task.

Inspected cumulative streaming test asserts client content `"Hello from mock!"`, token-ID upstream rewriting and `stream=True`; it does **not** read the stored trace's content. Usage test checks outbound usage, also not stored text. [T2]

**Negative control:** 2 turns, turn 2 streamed, assert client text, captured response content and converted Step output are **3 identical strings**, including `"42"` and a Unicode/tool-containing variant; mutate captured text once and require rejection.

### F5. Streaming tool calls are concatenated as fragments, not reconstructed by index

`build_trace_record_from_chunks` does `tool_calls_parts.extend(delta["tool_calls"])`. `_parse_openai_tool_calls` then treats every fragment as a complete call. Reasoning deltas also are not accumulated, unlike nonstreamed reasoning extraction. [S4, S10]

Concrete OpenAI-style call in two fragments:
- index 0, id `call_1`, function name `sql`, arguments `{"x":`
- index 0, function arguments `1}`

Expected: **one** `sql({"x":1})` call. Actual inspected path stores **two** tool-call entries. Conversion produces `sql({"raw": "{\"x\":"})` and an unnamed call with `{"raw":"1}"}`, not one parsed call. IDs/index are not used to reassemble arguments. This is a trace semantics issue even if completion IDs/logprobs are perfect.

**Negative control:** split one call at each of 5 argument boundaries, expect **1 call, 1 stable ID, exact decoded arguments** in all cases; two interleaved indices must produce exactly **2 calls**, no fragments. Inspected data-process streaming test contains plain content only. Trace-converter tool tests use complete tool objects, not streamed fragments. [T3, T4]

### F6. Storage failures are swallowed, including “synchronous” capture

`Proxy._persist` catches/logs exceptions even when `sync_traces=True`; `_safe_store` also catches/logs exceptions. `/admin/flush` gathers pending tasks with `return_exceptions=True` and returns `{"status":"flushed"}` without a durable-write acknowledgement/failure count. Thus flush means draining, not admission-integrity certification. [S7, S6]

Concrete input: store raises once on a successful response. Client still receives success; later flush can return flushed; trace count is lower. If **all** traces are missing, enrichment's `if not traces` branch returns the raw episode even in strict mode, before token checks. If raw agent steps already contain IDs the raw payload can survive; if they are lightweight, later transforms can fail/drop them. Neither outcome is an exactly-once receipt.

**Negative control:** fail exactly 1 of 3 stores, both sync and async. Producer/admission ledger must expose **expected=3, persisted=2, rejected=1**, and train **0 groups** requiring that missing member. A no-trace strict training result must not be called enriched. Existing resilience tests tolerate an error trace and assert surviving successful counts, not a durable admission receipt. [T5]

### F7. Drops after advantage calculation alter trained groups

The buffer transforms groups, enforces `min_trajs_per_group` (default 2), computes advantages, optionally removes zero-advantage groups, then queues them. Tinker's `transform_trajectory_groups_to_datums` treats any precomputed advantage as enough to skip recomputation and drops each trajectory whose datum conversion raises `AssertionError`. No post-drop cardinality or full-group re-admission is visible there. [S11, S12, S9]

Concrete two-member illustrative group (not co-train's prescribed G): rewards `[0,1]`, first member has nonempty IDs but missing logprobs, second is valid. GRPO assigns approximately `[-0.999998,+0.999998]` using population std `.5` and epsilon `1e-6`. Then Tinker rejects the first member and emits only the positive member's datum. The original group passed min=2, but actual trained membership is 1 and no longer centered. Counter metric `batch/dropped_malformed_sequences=1` exists; it is observability, not a group admission gate. [S13]

Compact filtering is a **termination filter**, not context compaction repair. It can remove ERROR/TIMEOUT/MAX_TURNS members before grouping, changing group membership by configuration. A singleton is rejected by default async min=2; do not claim default singleton admission there. The standalone GRPO helper nevertheless returns `r/(1+1e-6)` for one member (mean=0,std=1), not a centered zero advantage, so overrides/direct paths need explicit policy. [S9, S13]

**Negative control:** configured G expected members, one member missing all sampler logprobs: **0 partial-group training admissions**, and exact expected/retained/reason counts. Recomputing, refilling, dropping the group, or training the survivors are different scientific choices, all approval-required for co-train.

### F8. Alignment checks exist, but rely on assertions and are late/incomplete

Do not allege all shape checking is absent. `Step.model_post_init` checks nonempty logprob length when a `model_output` exists. Tinker rejects empty logprobs and missing/per-token mismatched advantages, and asserts equal shifted input/target/logprob/advantage/mask lengths. Synthetic tests check exact mask arrays. [S14, S12, T6]

However, these integrity checks use `assert`, which Python `-O` removes. `TraceRecord` itself has plain lists and no cross-field/finite-value validator. Extractors filter out null logprobs; e.g. 3 completion IDs and logprobs `[-.1,None,-.3]` become length 2. Normal conversion can catch this, but it is not fail-closed at capture, and optimized assertion-only paths lose the gate. Nonempty matching-length nonfinite floats have no finite-value check in these inspected admission functions. This is not a claim about an uninspected service accepting NaNs.

**Negative control:** lengths `3/2`, empty sampler logprobs, NaN and infinity each rejected under ordinary Python and `-O`, **0 backend calls**. Normal positive shifted example: prompt `[1,2,3]`, completion `[4,5]` must yield 4 targets and mask `[0,0,1,1]`. A one-token shift or one observation-mask bit flipped to 1 must fail. No such controls were executed here.

### F9. Prefix reset is useful, but not compaction equivalence or same-session serialization

`TokenAccumulator` tracks raw sampled IDs, fingerprints the **request** message prefix and resets on shorter/changed histories. A declined bridge also resets/re-ingests. This is a real fix already present at this pin; do not repeat the previously fixed “declined bridge keeps stale prefix” as a current bug. [S15, S7, T2]

Two remaining contracts:
- The newly appended assistant message is outside the prior request fingerprint. `extract_new_messages` drops **every** appended assistant. Changing the latest returned assistant `"A"` to `"B"` while leaving the old request prefix unchanged is not detected; bridge uses sampled A's IDs, not the B text presented in the new request. This can be intentional raw-token authority, but then text/token divergence needs explicit rejection/receipt, not a claim that all supplied history was honored.
- Accumulators are shared mutable per-session state without a per-session lock across upstream awaits. Two post-first-turn requests can both build from state N; completion order decides which becomes state N+1. Sticky worker routing is not a session transaction.

Tinker prefix merger splits on token-prefix mismatch, rather than proving a summarized/compacted prompt equivalent or rejecting it. Splitting protects exact token histories locally but changes number of loss rows and repeats broadcast trajectory advantage across segments. Metrics expose splits; they do not establish co-train's context/science equivalence. [S12]

**Negative controls:** change 1 prior prefix token, expect **2 segments** instead of a false merge; inject renderer-decline once and require next turn starts from re-ingested tokens; modify latest assistant only, require **1 explicit divergence disposition**; overlap two same-session requests and require either serialization or **0 accepted state-overwrites**.

### F10. Version labels are not full sampler-policy identity

Nonstreamed builder prefers upstream response `weight_version` over the proxy fallback. Streaming builder never extracts version from chunks and always uses the supplied proxy version, snapped at request entry. A streaming engine response containing version 7 with proxy 6 is stamped 6. [S4, S7]

The buffer uses the minimum **known** step version, ignores `None`, and defaults to 0 only if none are known. A `[7,None]` trajectory group becomes 7, not “unknown.” Unified async training records version difference **after** policy update, not a fail-closed per-group stale-version admission test in the inspected consumer. Coordinator quota/drain logic is a real throttle and `partial_rollout=False` drains before sync; these mitigations should not be confused with response-bound identity validation. [S11, S16, S17]

Sticky routing can fall back to another healthy worker and cache is cleared on pool changes. Worker metadata has model name but no weight version. For external vLLM, proxy stamping is therefore an assertion about coordination, not measured proof every routed worker served the same policy. No global mixed-worker exploit was executed.

**Negative controls:** proxy 6/upstream stream 7 must either record **7** or reject; one `None` among G policy labels means **0 fully-verified group admissions**; compare hashes/versions before training rather than only logging negative/positive staleness after an update. No stale-policy mechanism should be introduced into frozen co-train as an unapproved sampling/backend change.

### F11. Checkpoint metadata/resume helper tests are not restore or replay proof

Tinker save awaits remote state/sampler saves, then writes local `checkpoint.json` and latest-step tracker directly with `open(...,"w")`, not atomic replacement. Metadata contains paths and dataloader state, not a trace-admission ledger, per-attempt IDs, pending async buffer/in-flight episodes, scorer/model/template hashes or coordinator state. Resume uses remote state path and sampler path and optionally loader state. Backend restores global step and loader position, but not sampler-policy identity from a manifest. [S18, S19]

Concrete fail-closed gap: auto tracker names an existing `global_step_N` directory whose `checkpoint.json` is missing. `_resume_step_dir` returns the directory based on existence; `initialize_async` sees no resume info and starts a fresh LoRA client, rather than rejecting this damaged selected checkpoint. Invalid JSON errors are different: they propagate, not silently fall back. Crash during direct checkpoint/tracker writes can also leave partial metadata; no transactional guarantee claimed.

Async generation advances the dataloader while groups are buffered/in flight. Saving its current state without those buffered episodes is not proof resume will replay the exact next admitted task group. This is a source-level continuity gap, not proof model optimizer restoration is broken.

Inspected checkpoint tests explicitly bypass trainer initialization and write fictional `tinker://...` paths. They exercise `_resume_step_dir` only: auto/disable/explicit path/missing-dir cases, no remote state reload or one-step equivalence. [T7]

**Negative controls:** selected checkpoint directory missing metadata => **1 hard refusal, 0 scratch client creations**. Truncate JSON and tracker separately => **0 ambiguous resumes**. Future approved runtime restore: match next **2 task/group identities**, optimizer/scaler/scheduler and RNG state as applicable, policy/logprob identity, and one resumed update against uninterrupted reference under predeclared numeric tolerances. Not executable/authorized here.

## Inspected tests versus executed evidence

Read actual bodies, not just names:
- **T1:** concurrent session isolation, 10/50 distinct sessions; 5×3 sequential turns; streaming polls up to 10 seconds. Mock upstream, sync capture for nonstream path. No same-session overlapping cumulative race.
- **T2:** mock-renderer cumulative bridge, reset-on-divergence and declined-bridge regression, streamed client content and usage. No real model tokenizer/renderer boundary; no streamed stored-answer equivalence assertion.
- **T3:** data-process nonstream and normal `delta.content` streaming builders. No early-EOF, fragmented tools, upstream stream-version precedence, or `text`-chunk captured-content test in the inspected body.
- **T4:** trace conversion for full tool objects, malformed full JSON fallback, reasoning, IDs, weight propagation. No streaming-fragment assembly.
- **T5:** injected worker 500, invalid JSON, 2 successful calls then 500, normal session deletion. Does not prove durable receipts, retry-generation isolation, or interrupted streaming admission.
- **T6:** synthetic Tinker datums: exact single/merged masks; split prefix/nonprefix cases; missing logprobs, advantage mismatches, empty trajectory and one-token boundary. No real sampler/optimizer check.
- **T7:** seven local checkpoint path-resolution tests with fabricated remote paths; no checkpoint restoration.
- **T8:** AgentFlow `_Gateway` test double, validation flag and strict empty-token behavior. No failed-cleanup/later-attempt race. Its empty-trace validation fixture is not a training no-trace admission test.
- **T9:** hierarchical task IDs/group roles and per-task GRPO centering. Protects colon-delimited ID parsing, not attempt/call dedup.

**Executed:** zero upstream tests, zero negative-control executions, zero library imports/training calls. Proposed controls above are acceptance criteria, not reported passing results. Not a full-repository test-coverage census.

## Adoption choices, tradeoffs, costs and approvals

1. **Recommended now: copy ideas into a proposed admission specification only.** Separate `captured`, `attempt_closed`, `scored`, `group_complete`, `admitted`, `consumed`, `checkpointed` states; immutable task/rollout/attempt/call/segment IDs; expected G and exact member set; sampler provenance and terminal disposition. Reuse invariant concepts, not source code/runtime. Benefit: bounded review surface and no stack change. Cost: stricter refusal and more explicit accounting; not proof of learning.

2. **Do not silently add retry/refill/filter/partial-reward policy.** A retry budget of 3, survivor-only updates, failure-as-zero, prefix splitting or replacement sampling each affects distribution/group semantics. Numeric gates proposed here require owner approval for any changed scientific handling; frozen G/scorer/eval membership remains unchanged. Logging rejection is safer than inventing permission to repair groups.

3. **Do not adopt rLLM backend/gateway as this research's implementation.** Root package is a training stack with Tinker dependencies and optional Fireworks/verl. Standalone gateway README says “6 dependencies, no ... transformers,” but pinned pyproject actually lists **8 direct dependencies**, including `renderers>=0.1.7` and `transformers>=4.50.0`. That prose is not a dependency-compatibility certificate. Installing even “just gateway” would need owner dependency/security/privacy review and approved isolation. [S20, S21]

**License:** Apache-2.0 at exact pin, royalty-free copyright/patent grants subject to license conditions, including retention of license/notices and marking modified redistributed files. Commercial service/model/dataset licenses are separate. No source was promoted into co-train. [S22]

**API/cost:** public GitHub source GETs only; **0 provider inference/training API requests, 0 GPUs/paid jobs**. Public source access is not a training-cost estimate; tool-platform retrieval billing was not measured. Tinker state/sampler/training calls and Fireworks/provider/GPU execution are cost-bearing possibilities, not free because repository is Apache. Current dollar/token/GPU prices were not fetched or verified; approval must specify provider/model, rate card, region, token/step ceiling, retry budget and hard spend cap before any such call.

**Approval needs:** backend/dependency/vendor changes; any change to model/revision/G/GRPO/scorer/eval/science; remote trace retention or external service use; checkpoint/resume experiment; installations, downloads, actual sampler/optimizer/GPU/paid execution. This report grants none.

## Non-goals

No backend replacement, code patch, project-file edit, dependency resolution, auth audit, whole-repository bug verdict, deployment, training launch, runtime compatibility certification or learning proof. No claim that all rLLM configurations hit every conditional finding.

VERIFY_REAL: pinned source and named test bodies inspected; report/source inventory written to scratch and checked. All counterexamples are source deductions, all numeric controls proposed and unexecuted; no upstream runtime/learning/restore success claimed.

## Exact pinned symbol and test URLs
- **S1**: [`rllm/engine/agentflow_engine.py`, enrich_episode_with_traces; process_task_with_retry (458-524); _finish_episode (646-706)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/agentflow_engine.py#L110-L230)
- **S2**: [`rllm-model-gateway/src/rllm_model_gateway/store/memory_store.py`, MemoryTraceStore.store_trace/get_session_traces](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/store/memory_store.py#L64-L94)
- **S3**: [`rllm-model-gateway/src/rllm_model_gateway/store/sqlite_store.py`, SQLiteTraceStore.store_trace/get_session_traces](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/store/sqlite_store.py#L116-L170)
- **S4**: [`rllm-model-gateway/src/rllm_model_gateway/data_process.py`, build_trace_record; build_trace_record_from_chunks; extract_logprobs (50-76)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/data_process.py#L188-L310)
- **S5**: [`rllm/gateway/manager.py`, GatewayManager.aget_traces/adelete_session/adelete_sessions](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/gateway/manager.py#L301-L325)
- **S6**: [`rllm-model-gateway/src/rllm_model_gateway/server.py`, session delete APIs; admin flush (380-392)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/server.py#L278-L311)
- **S7**: [`rllm-model-gateway/src/rllm_model_gateway/proxy.py`, Proxy.handle; cumulative streaming (368-503); streaming (509-639); retry/persist (747-787)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/proxy.py#L135-L184)
- **S8**: [`rllm/engine/remote_agent_flow_engine.py`, RemoteAgentFlowEngine.process_task_with_retry; _build_episode](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/remote_agent_flow_engine.py#L97-L212)
- **S9**: [`rllm/trainer/algorithms/config.py`, CompactFilteringConfig; RejectionSamplingConfig (180-218)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/algorithms/config.py#L110-L161)
- **S10**: [`rllm/engine/trace_converter.py`, _parse_openai_tool_calls; trace_record_to_step](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/engine/trace_converter.py#L13-L81)
- **S11**: [`rllm/trainer/buffer.py`, TrajectoryGroupBuffer.add_episode; _min_weight_version (414-421)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/buffer.py#L166-L265)
- **S12**: [`rllm/trainer/tinker/transform.py`, trajectory_to_datums; transform_trajectory_groups_to_datums](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/transform.py#L42-L239)
- **S13**: [`rllm/trainer/algorithms/rl_algo.py`, calculate_grpo_advantages_per_group](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/algorithms/rl_algo.py#L6-L18)
- **S14**: [`rllm/types.py`, Step.model_post_init](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/types.py#L149-L167)
- **S15**: [`rllm-model-gateway/src/rllm_model_gateway/token_accumulator.py`, extract_new_messages; TokenAccumulator.is_cumulative/update_prefix/build_next_prompt](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/src/rllm_model_gateway/token_accumulator.py#L33-L162)
- **S16**: [`rllm/trainer/sync_coordinator.py`, SyncCoordinatorConfig; SyncCoordinator quota/sync](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/sync_coordinator.py#L9-L110)
- **S17**: [`rllm/trainer/unified_trainer.py`, _generation_loop; _training_loop; _perform_weight_sync (812-827)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/unified_trainer.py#L629-L763)
- **S18**: [`rllm/trainer/tinker/tinker_policy_trainer.py`, initialize_async; save_checkpoint_and_get_sampling_client/_resume_step_dir (335-400)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/tinker_policy_trainer.py#L120-L159)
- **S19**: [`rllm/trainer/tinker/tinker_backend.py`, on_train_start; on_policy_updated](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/tinker/tinker_backend.py#L368-L410)
- **S20**: [`rllm-model-gateway/pyproject.toml`, standalone gateway metadata/dependencies](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/pyproject.toml#L5-L22)
- **S21**: [`rllm-model-gateway/README.md`, dependency prose; root pyproject.toml dependencies also inspected](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/README.md#L66-L72)
- **S22**: [`LICENSE`, Apache-2.0 license](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/LICENSE#L1-L202)
- **S23**: [`rllm/trainer/algorithms/transform.py`, _build_trajectory_groups](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm/trainer/algorithms/transform.py#L105-L152)
- **T1**: [`rllm-model-gateway/tests/unit/test_concurrent_sessions.py`, all four concurrency test bodies/fixtures](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/tests/unit/test_concurrent_sessions.py#L16-L127)
- **T2**: [`rllm-model-gateway/tests/unit/test_cumulative_token_mode.py`, mock renderer/fixture; reset/declined bridge (221-324); stream text/usage (371-451)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/tests/unit/test_cumulative_token_mode.py#L18-L76)
- **T3**: [`rllm-model-gateway/tests/unit/test_data_process.py`, TestBuildTraceRecord nonstream/stream bodies](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/tests/unit/test_data_process.py#L142-L234)
- **T4**: [`tests/engine/test_trace_converter.py`, complete tool call conversion; basic Step/reasoning/version tests](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/engine/test_trace_converter.py#L16-L213)
- **T5**: [`rllm-model-gateway/tests/unit/test_error_resilience.py`, resilience/cleanup fixtures and tests](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/rllm-model-gateway/tests/unit/test_error_resilience.py#L22-L187)
- **T6**: [`tests/unified_trainer/test_tinker_transform.py`, single and merged masks; nonprefix test bodies (331-367); edge cases (470-534)](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_tinker_transform.py#L207-L308)
- **T7**: [`tests/unified_trainer/test_tinker_checkpoint.py`, all seven local _resume_step_dir tests and fixture](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_tinker_checkpoint.py#L12-L71)
- **T8**: [`tests/engine/test_agentflow_engine.py`, gateway double; validation/strict test bodies](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/engine/test_agentflow_engine.py#L12-L127)
- **T9**: [`tests/unified_trainer/test_trajectory_grouping.py`, hierarchical identity/grouping/GRPO test bodies](https://github.com/rllm-org/rllm/blob/4e828c81680e5a85b638ceedeaf09d1e90109ca8/tests/unified_trainer/test_trajectory_grouping.py#L24-L125)
