# SkyRL rollout failures and restore invariants

Date: 2026-10-23. Source-only independent review. Repository: NovaSky-AI/SkyRL.
Exact pin: `3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d`.
[Commit](https://github.com/NovaSky-AI/SkyRL/commit/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d):
2026-10-23T03:58:07Z, “[SkyCap] Support OpenAI Responses API (#2510)”.
Parent supplied this as HEAD; I verified the commit, not the moving default-branch HEAD.

Local scope: `/Users/nikolassapalidis/Developer/co-train` at parent-supplied
`ea6d2f6`; fresh-read `spec/native-training.md`. No git commands used to reverify
that baseline. Frozen GRPO, model, G, scorer, evaluation membership and science
remain unchanged. No Torch, upstream imports/execution, backend installation,
model/data download, GPU use, training, benchmark or project edits.

## Evidence rubric and limits

- **S**: actual pinned implementation body inspected, with a concrete control-flow/data witness.
- **T**: actual pinned test body inspected. Coverage description only; tests were not run.
- **D**: pinned documentation or explicit implementation contract.
- **L**: local static parsing/hashing of cached source text, no imported/executed upstream code.
- No runtime reproduction or empirical severity claim. Missing tests alone are not findings.
- Cached source is FetchUrl Markdown text, not a git checkout. SHA256 values in
  `skyrl-failures-sources.json` identify cached text, not upstream git blob hashes.

## Findings: concrete counterexamples

### F1. Gym environment cleanup is bypassed on exceptions/cancellation (S, T)

[SkyRLGymGenerator.agent_loop](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L379-L397)
creates `env` and awaits `env.init`; generation and `env.step` are awaited at
480 and 537. `env.close` occurs only on the normal path at
[627–630](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L627-L630).
The only [finally clause](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L730-L731)
awaits `finish_session(session_id)`.

**Witness:** environment created successfully, engine `generate` raises once.
Execution jumps directly to `finish_session`; `env.close` runs zero times.
Same with cancellation during `env.step`. This proves the cleanup omission,
not a leak for every environment. Separately, if `finish_session` raises while
another exception propagates, its exception replaces the primary exception.

Existing cancellation utilities preserve primary errors and bound cleanup,
but are not used in this finally clause. `test_cancel_background_tasks_bounds_an_unresponsive_task`
explicitly asserts the task is still alive after its 0.01-second grace period;
bounded wait is not proof of cancellation completion.
[Utility test](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/tests/train/test_async_utils.py#L73-L89).
No executed proof of backend request abortion.

**co-train safeguard:** local lifecycle-spy negative controls only. Do not
interpret timeout/constructor refusal as evidence resources were reclaimed.

### F2. Postprocessed actions can inherit logprobs of different tokens (S, T)

[agent_loop 543–568](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L543-L568)
replaces `output_ids` with tokenizer encoding of `postprocessed_action`, but
passes unchanged `response_logprobs` into `TurnOutput`. Routed-expert and
sample-support traces explicitly reject this path; ordinary logprobs do not.
[TurnOutput 125–151](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/skyrl_gym_generator.py#L125-L151)
assigns loss-mask 1 to output tokens and returns these original logprobs.

**Witness:** sampler returns IDs `[10,20]`, logprobs `[-0.1,-0.2]`;
environment supplies action encoding `[30,40]`, same length, no synthetic EOS,
no expert/support capture, ordinary multi-turn token path.
Result contains trained IDs `[30,40]` paired with logprobs of `[10,20]`.
Equal lengths defeat shape checks. No claim this path is used by co-train.

`test_postprocessed_action_used` deliberately verifies rewritten IDs are present,
raw IDs absent, and mask lengths agree. It does not assert sampler-token
identity.
[Test body](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/tests/train/generators/test_skyrl_gym_generator.py#L1167-L1246).
Custom-history retokenization is a separate, acknowledged non-token-in/token-out
path; logprob capture there raises. Do not conflate it with this witness.

**co-train safeguard:** preserve generated IDs and token provenance. Reject
equal-length substitution in the local reference checker; do not add template
rewriting or an alternate backend.

### F3. SQL scorer collapses infrastructure/reference failures into model failure (S)

[execute_sql_wrapper_single](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-gym/skyrl_gym/envs/sql/utils.py#L46-L100)
returns `(db_file, sql, None, 0, output_str)` for every execution exception.
[calculate_reward_single / compute_score_single](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-gym/skyrl_gym/envs/sql/utils.py#L103-L133)
ignore both execution-success flags, award 1 only for two non-None equal results,
otherwise 0, and turn outer exceptions into 0.

**Witness:** correctly formatted predicted SQL is identical to gold SQL;
database exists at `SQLEnv` construction but becomes unreadable before scoring,
or gold execution raises due to corrupt/missing schema. Score is ordinary 0,
indistinguishable from a valid wrong answer. `SQLEnv.step` returns that reward
normally with `done=True`, without a scorer-validity status.
[Environment path](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl-gym/skyrl_gym/envs/sql/env.py#L84-L107).

The SQL “timeout” is not a hard wall-clock bound: after timeout it calls
`conn.interrupt()` then unbounded `done.wait()` at line 91. If SQLite connection
open / native I/O is stuck before `conn_holder` is populated, there is nothing
to interrupt and the wrapper can still wait. This is a conditional blocking
witness, not an observed SQLite hang.

**co-train safeguard:** preserve the frozen scorer. Separate pre/post database
identity and infrastructure-health checks from reward. Invalid infrastructure
must invalidate the diagnostic/run, not be recoded into a scientific label.
Any actual scorer/error-policy amendment requires owner approval.

### F4. “Latest checkpoint” can point to incomplete restore state (S, T)

Three source-supported publication windows:

1. [RayPPOTrainer.save_checkpoints 1746–1769](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1746-L1769)
   catches dataloader-save exceptions, then still writes trainer state and latest
   pointer and invokes old-checkpoint cleanup. **Witness:** `state_dict()` raises;
   latest advances without `data.pt`.
2. [FullyAsyncRayPPOTrainer.save_checkpoints 1202–1218](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/fully_async_trainer.py#L1202-L1218)
   calls the base save (including latest-pointer publication/cleanup) before
   writing `fully_async_state.pt`. **Witness:** process interruption or write
   error between those operations. Latest refers to a checkpoint whose async
   loader requires the missing file at 1234.
3. [MegatronStrategy.save_checkpoint 371–414](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/distributed/megatron/megatron_strategy.py#L371-L414)
   optionally schedules disk writes and returns while they remain pending.
   [WorkerDispatch.save_checkpoint](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/workers/worker_dispatch.py#L580-L597)
   waits for that method, not `finalize_pending_saves`. Base trainer can publish
   latest before pending shards finish. Graceful teardown/load does finalize;
   that does not cover process loss during the earlier publication window.
   Do not claim every save is async.

Also the pointer is an ordinary `open(...,"w")` write, not replace/rename-based
atomic publication. A comment calling it “Atomic tracking” is not crash proof.

**Coverage:** `test_trainer_full_checkpointing` builds real models but manually
sets global_step=2, saves/loads, sets 3, saves again. It checks file/config/step
presence; despite its docstring, that body performs no actual update or
continuation-equivalence comparison.
[Test body](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/tests/backends/skyrl_train/gpu/gpu_ci/test_trainer_full_checkpointing.py#L231-L321).
This is not evidence no stronger test exists, see F5.

**co-train safeguard:** native checkpoint configuration remains configuration
only. A non-executing completeness manifest should refuse partial state; it
cannot certify restoration or authorize launch.

### F5. FSDP requested restore can silently omit optimizer/RNG state (S, T)

[FSDPStrategy.load_checkpoint 491–537](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/distributed/fsdp_strategy.py#L491-L537)
requires model and extra files, but treats optimizer presence as optional.
It loads optimizer only if the loaded dictionary is truthy, even when
`load_optimizer_states=True`; RNG restoration runs only if `"rng"` exists.

**Witness:** saved model and valid scheduler/extra state remain; optimizer file
contains `{}`. Fresh optimizer supplied, `load_optimizer_states=True`.
Model/scheduler restore completes; optimizer retains fresh moments.
Removing RNG key similarly skips RNG restoration. Empty optimizer is legitimate
for some weight-only/initial cases, so this is a strict-resume admission gap,
not a claim every such checkpoint is corrupt. Missing-file behavior can also
depend on `io.local_read_files`; the `{}` witness avoids that uncertainty.

Base trainer [load_checkpoints 1868–1904](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/trainer.py#L1868-L1904)
also tolerates absent/broken dataloader state, starts it from beginning, and
reports complete load after policy restore. This explicitly degrades replay
identity, rather than proving exact continuation.

**Positive evidence:** FSDP saves optimizer/scheduler and per-rank RNG.
Base `Strategy` saves/restores Python, NumPy, Torch CPU and current CUDA device
RNG. Megatron has optimizer/scheduler/RNG save and restore paths too. No general
“SkyRL never restores RNG/optimizer” claim is warranted.

A stronger test actually exists:
[test_save_load_checkpoint](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/tests/backends/skyrl_train/gpu/gpu_ci/test_save_load_checkpoint.py#L156-L234)
updates, saves, updates, reloads, repeats the second update and asserts logits
with `atol=0, rtol=0`, across configured FSDP/Megatron variants. That is real
positive continuation-test code, not a run result here. It does not establish
strict refusal of deliberately empty optimizer or missing RNG state.

**co-train safeguard:** receipt/schema-only checks can demand separate model,
optimizer, scheduler, RNG and data identities. Actual native restore comparison
is separately approved GPU/runtime work. Never fabricate weights or gradients.

### F6. Non-finite verifier rewards have no rejection at the inspected bridge (S)

[HarborSkycapGenerator._attempt 244–255](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/examples/train_integrations/harbor_skycap/harbor_generator.py#L244-L255)
uses `float(results.verifier_result.rewards["reward"])` without a finite check;
[compose 157–176](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/examples/train_integrations/harbor_skycap/compose.py#L157-L176)
forwards it for unmasked outcomes. Trainer postprocessing casts it again,
without rejecting it. [GRPO outcome advantages](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/backends/skyrl_train/utils/ppo_utils.py#L1366-L1393)
take group mean/std.

**Conditional input witness:** a verifier result object exposes numeric
`float("nan")` for one live member and 1.0 for another in the same UID group,
zero-variance filtering disabled. Cast accepts NaN; GRPO mean/std are NaN, hence
both members' advantages become NaN. This proves the inspected bridge is not a
finite-value boundary. Whether a particular external Harbor verifier/model
validation admits such an object was not traced or executed; no unconditional
production exploit/incident claim.

**co-train safeguard:** local diagnostic fixtures reject NaN/+Inf/-Inf before
group arithmetic. Reject, do not replace with 0 or change the scorer.

## Important non-bugs and current-version boundaries

### Async: capacity ceiling is not per-trajectory policy identity (S, T, D)

[_AsyncStalenessManager](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/fully_async_trainer.py#L115-L187)
explicitly documents aggregate admission rather than a hard per-group bound.
[convert_generation_group_mini_batch_to_training_input](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/fully_async_trainer.py#L1037-L1070)
logs and accepts groups whose scheduling-step age exceeds max staleness.
Example: group scheduled at step 1 completes at step 4 with limit 1; age 3 is
logged, not rejected. This violates a hypothetical strict-on-policy consumer
contract, not SkyRL's documented contract. Scheduling step/cache salt also
does not prove every token of an in-flight trajectory came from one weight set.

Worker creates all repetitions for one prompt, asserts equal UIDs, and enqueues
a whole `GeneratedOutputGroup`; finish-time FIFO does not by itself mix prompt
membership. Variable stepwise rows retain one group UID per response row.
No supported group-mixing bug found in these paths.
Inspected tests exercise filtered-capacity recovery, trained-vs-filtered UID
restore and consumer failure wakeup. They are not hard per-token policy-version
evidence.

### Masks/prefix breaks: inspected merge logic does the conservative thing (S, T)

[_merge_single_trajectory](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skyrl/train/generators/utils.py#L924-L965)
requires previous prompt+response to prefix the next **prompt**, not the next
prompt+response. Prefix break flushes into a separate row; observation deltas
receive mask/logprob/reward zeros. Test bodies verify mismatched prefixes stay
two rows and overlapping response tokens do not merge.
[Tests](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/tests/train/generators/test_generator_output_utils.py#L701-L759).
No evidence for a generic tool-mask/prefix-merge bug. F2 is narrower.

### Current SkyCap + Responses API is not paper-era SkyRL-SQL (S, T, D)

This pin introduces Responses API support in `skycap/`. README distinguishes
current unified SkyRL, agent and gym layers, with an explicit different v0
reproduction commit `a0d50c482436af7fac8caffa4533616a78431d66`.
Do not backdate current SkyCap behavior to 2025 SQL/v0 results.

- `RetryCache`: explicit idempotency key or `x-stainless-retry-count>0` coalesces/
  replays committed calls. Repeated unmarked body deliberately resamples;
  text-mode relayed streams are not cached. TTL=600 seconds, max settled
  entries=64; running entries are retained. These are bounded cache semantics,
  not exactly-once guarantees across restart/eviction.
  [Source](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skycap/src/skycap/retry.py#L92-L160).
  Tests actually assert one upstream request for SDK retry, two for unmarked
  repeat, two for text-stream retry, mismatched keyed body HTTP400.
- Harbor integration retries unknown failures on **fresh** trajectory graphs;
  `PathRuleError` is not retried. Agent timeout and exhausted error mask the
  **whole prompt instance**, including successful sibling repetitions.
  Context-length failures may remain zero-reward trained rows unless overlong
  filtering clears them. No silent shrinking to G-1: masked placeholders retain
  identity, though effective trainable group size can change.
  [compose](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/examples/train_integrations/harbor_skycap/compose.py#L124-L168).
  Tests assert whole-instance masking, no retry for agent timeout, fresh graphs
  on crashes and separate retry-attempt infrastructure metrics.
- Responses parser refuses stateful continuation fields/background;
  token mode refuses `truncation="auto"` and context-management compaction.
  Streamed context overflow intentionally returns HTTP200 with
  `response.failed`; non-streamed overflow HTTP400. Completion cap returns
  `response.incomplete`. HTTP200 alone is not usable-result evidence.
- Tests explicitly document ignored controls: `tool_choice="required"`,
  `parallel_tool_calls`, structured-text schema and reasoning effort can be
  ignored/echoed. Echoed request fields are not enforcement receipts.
  [Actual tests](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/skycap/tests/test_responses_tokens.py#L149-L214).
  This compatibility subset is explicit, not proof of a full OpenAI Responses
  implementation. Token-mode marked-stream retry does have a one-engine-call
  test at 241–248.

## Cheap local negative controls, numeric pass criteria

**Proposals, not implemented or run.** No scientific/backend changes. Keep
fixtures explicitly metadata/reference-only; no fixture earns runtime_verified,
training_verified or launch_authorized.

1. **lifecycle_primary_error**: 3 fixture exits (success, one engine error,
   one cancellation), exactly 1 env close + 1 session finish per created
   environment. Inject cleanup error once; original error identity remains,
   cleanup recorded separately. Local fixture cleanup budget 100 ms, total
   <1 s; an unfinished task produces explicit failure, not “cleaned”.
2. **token_identity_not_length**: 2 equal-length sequences `[10,20]` and
   `[30,40]`; unmodified sampler identity accepted once, one-token mutation
   rejected once even with matching mask/logprob lengths. External tool-token
   count=19 stays mask 0 in existing bridge reference; flip exactly one and
   require rejection. No production template edits.
3. **group_membership_and_policy**: two fixture prompts, exactly frozen G
   unique repetition IDs per prompt, one shared task/scorer identity per group.
   Delete one repetition, duplicate one, swap one UID, mark one infra-invalid,
   mutate one policy revision: 5/5 refused for scientific admission, 0 implicit
   redraws/resamples. This validates an unchanged fixed-group contract, not a
   new failure/drop policy. Async source labels remain diagnostic only.
4. **reward_validity_not_zero**: valid wrong answer=finite 0 accepted once.
   4 distinct invalid cases (gold-query error, infrastructure timeout, NaN,
   +Inf) rejected 4/4 as invalid evidence, never remapped to 0. Add -Inf if the
   proposed checker is implemented: total then 5/5. Use approved SQLite fixture,
   not an alternate scientific scorer.
5. **checkpoint_completeness_is_not_restore**: one complete synthetic manifest
   plus 6 mutations (model missing, optimizer empty/missing, scheduler missing,
   RNG missing, data/consumed-UID state missing, step mismatch). Complete
   manifest is “metadata_complete” only; 6/6 mutations refuse. All 7 outputs
   retain runtime_verified=false and training_verified=false. Merely listing
   filenames does not prove tensor content, RNG equivalence or publication
   durability.
6. **http_success_is_not_rollout_success**: four synthetic Responses bodies:
   completed + valid tokens, HTTP200/failed, HTTP200/incomplete, completed with
   no sampled tokens. Exactly 1 usable, 3 non-usable, 0 invented rewards.
   Strict validation is a local receipt rule, not API backend migration.
7. **guard_must_fail**: existing real preflight and production runtime gate
   refuse before 1 framework import/model/trainer construction/output creation,
   including `python -O`. For a private labelled fixture seam only, removing
   the preflight or flipping the metadata-source field must make its independent
   check red. Retain current real native-template prefix mismatch as failure,
   not a hypothetical canonical-template pass.

Budget target for these stdlib/local-fixture checks: 0 network requests, 0 Torch
imports, 0 installs, 0 model loads, <5 s total and <100 MB incremental RSS.
Targets are proposed acceptance thresholds, not measured results.

## Approval and costs

- **Allowed now:** source review, scratch artifacts, proposed offline fixtures;
  no install, no launch, no backend switch. No monetary/GPU jobs initiated.
- **Owner approval required:** implementing project safeguards outside assigned
  scope; deciding whether invalid data aborts/masks/retries/redraws a scientific
  run; any GRPO/model/G/scorer/eval/science/version amendment; external sandbox,
  API, paid/GPU run, dependency/model download, training or actual restore.
- **License:** root Apache-2.0, no royalty fee; retain license/notices and mark
  modifications if copying/distributing. Does not license arbitrary model
  weights/datasets or establish their permitted use.
  [Pinned LICENSE](https://github.com/NovaSky-AI/SkyRL/blob/3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d/LICENSE).
- Source browsing has no upstream training charge; connector billing not
  inspected. GPU/sandbox/API reproduction costs unmeasured, not “free”.
  Runtime tests above require hardware/frameworks absent from local co-train;
  no dollar estimate or benchmark result invented.

## Artifacts and verification

- `/Users/nikolassapalidis/scratch/co-train-research-round2-2026-10-23/skyrl-failures.md`
- `/Users/nikolassapalidis/scratch/co-train-research-round2-2026-10-23/skyrl-failures-sources.json`
- Source text + tree + local static audit under
  `/Users/nikolassapalidis/scratch/co-train-research-round2-2026-10-23/skyrl-failures-cache/`

VERIFY_REAL: actual pinned source/test bodies read; source text parsed and
hashed locally without executing upstream code. No runtime/benchmark/training
or project test results claimed. Proposed negative controls remain unexecuted.
