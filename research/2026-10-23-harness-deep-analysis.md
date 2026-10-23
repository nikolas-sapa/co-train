# Deeper harness source analysis

2026-10-23. Selected pinned core paths and relevant test bodies were inspected.
This is not an exhaustive audit or an upstream runtime/benchmark reproduction.
Earlier research covered selected Prime/Pi/T3/ART/OpenHands/mini-SWE paths;
some broader findings were indexed-source or documentation evidence only.
This continuation used source-capable workers to remove that retrieval limit.

## Additional repositories

| Component | Pinned revision | License | Scope |
| --- | --- | --- | --- |
| Harbor | `bfc6c005e9a572ba22fd7e2d3b414bf014ae1ab0` | Apache-2.0 | Trial → agent/runtime → verifier → result/regrade, plus cleanup/scoring/regrade tests |
| OpenEnv | `6e5c73c0231dae82878c1a94c43e155527e26105` | BSD-3-Clause | Session/rollout and external-process paths, capture/export, rewards and cancellation tests |
| Agent Lightning | `05c7fe133175653e48c990546a3509e52dc56512` | MIT | Rollout IDs → proxy capture → train view → verl adapter → actor-update path and tests |
| Reasoning Gym | `49b07130b3fcd12f2d064bba7c43869543a0e7e7` | Apache-2.0 | Composite/generated item → version registry → bundled TRL reward, plus determinism/version/scoring tests |
| Terminal-Bench | `e67a2cb7db4d9795c212909b3395d8c22ad60aec` | Apache-2.0 | Dataset identity/README/license only, not a task-level audit |

GitHub identity redirects were checked: `laude-institute/harbor` now resolves
to `harbor-framework/harbor`; `meta-pytorch/OpenEnv` to `openenv/OpenEnv`.
A repository HEAD is not a frozen benchmark release; avoid `@latest`.
Repository licenses do not clear every separately sourced dataset/image.

## Where the benefits come from, and where assurance stops

### Harbor

The trial separates agent execution, verification, artifact collection and
phase timing. Partial agent output can still be graded after an agent timeout.
Regrade can reuse artifacts without starting the agent.

However, reward validity is a derived, unpersisted policy property: rereading an
old result under changed exception-classification code can change validity.
A saved result or cleanup flag is not proof that resources were reclaimed.
Regrade checks artifact structure/coverage, not universal content authenticity.

Sources: [single-step lifecycle](https://github.com/harbor-framework/harbor/blob/bfc6c005e9a572ba22fd7e2d3b414bf014ae1ab0/src/harbor/trial/single_step.py),
[error policy](https://github.com/harbor-framework/harbor/blob/bfc6c005e9a572ba22fd7e2d3b414bf014ae1ab0/src/harbor/models/trial/error_policy.py),
[regrade](https://github.com/harbor-framework/harbor/blob/bfc6c005e9a572ba22fd7e2d3b414bf014ae1ab0/src/harbor/trial/regrade.py).
Tests inspected included verifier nonfinite rewards, cleanup cancellation,
result-policy round trips and missing/unsafe regrade artifacts.

### OpenEnv

Resource sessions separate task binding, policy control, sampling and closure.
Capture distinguishes evaluation traces from training-token evidence.
The external harness process has its own cancellation/teardown mechanism.

These APIs do not establish one universal credit or timeout contract.
One external-path action can contain several internal model/tool calls.
Timeout/crash can become reward zero plus error metadata; a consumer that
ignores metadata would train on infrastructure failure. Flat token arrays
do not establish per-turn loss alignment. Seed acceptance is not seed use.

Sources: [rollout](https://github.com/openenv/OpenEnv/blob/6e5c73c0231dae82878c1a94c43e155527e26105/src/openenv/core/harness/rollout.py),
[external environment](https://github.com/openenv/OpenEnv/blob/6e5c73c0231dae82878c1a94c43e155527e26105/src/openenv/core/harness/environment.py),
[export](https://github.com/openenv/OpenEnv/blob/6e5c73c0231dae82878c1a94c43e155527e26105/src/openenv/core/harness/capture/export.py).
Tests inspected include fake-adapter lifecycle tests, real subprocess test
definitions, and evaluation-capture rejection from training contracts.
Those tests were not executed here.

### Agent Lightning

The inspected source is rewritten v1.0, not the original paper's v0.x code.
It decouples agent execution from training through proxy evidence, explicit
rollout/attempt IDs and a verl adapter. It reaches a real actor-update path.

The training view is not an immutable full transcript: identical prompt-token
requests can be deduplicated, missing/error responses filtered, and the last
reward event selected. Proxy retries and prepared request bodies differ from
the client's original requests. Mutable storage and optional telemetry uploads
are additional provenance/side-effect boundaries.

The adapter masks inserted observations and supports prefix breaks. Per-rollout
advantage/loss normalization explicitly handles one rollout becoming several
rows. Those algorithmic choices cannot be copied as unchanged GRPO.
An inspected advantage test uses a fake advantage function; it does not prove
the real optimizer mathematics or backward equivalence.

Sources: [rollout manager](https://github.com/microsoft/agent-lightning/blob/05c7fe133175653e48c990546a3509e52dc56512/agentlightning/verl/agl_rollout_manager.py),
[adapter](https://github.com/microsoft/agent-lightning/blob/05c7fe133175653e48c990546a3509e52dc56512/agentlightning/verl/rollout_adapter.py),
[trainer](https://github.com/microsoft/agent-lightning/blob/05c7fe133175653e48c990546a3509e52dc56512/agentlightning/verl/trainer.py).
Author-reported learning gains belong to their report/model/data configuration,
not this static inspection or co-train.

### Reasoning Gym

Procedural generation provides reproducible instances and oracle-backed
difficulty variation. Version IDs let scoring reach an older dataset instance.
The registry retains mutable object references, not immutable dataset snapshots.

The bundled chain-sum TRL example uses seed-plus-index generation. Its shifted
train/evaluation seeds can generate overlapping entries at shifted indices.
That is a static deduction about the tutorial, not a finding about paper runs.
Different IDs or seeds alone cannot prove content-disjoint splits.

Some scorers include partial-credit/tolerance fallbacks or suppress verifier
exceptions. These are reward semantics, not neutral compatibility utilities.

Sources: [composite](https://github.com/open-thought/reasoning-gym/blob/49b07130b3fcd12f2d064bba7c43869543a0e7e7/reasoning_gym/composite.py),
[chain sum](https://github.com/open-thought/reasoning-gym/blob/49b07130b3fcd12f2d064bba7c43869543a0e7e7/reasoning_gym/arithmetic/chain_sum.py),
[TRL example](https://github.com/open-thought/reasoning-gym/blob/49b07130b3fcd12f2d064bba7c43869543a0e7e7/examples/trl/grpo.py).

## Concrete co-train changes selected

[`spec/learning-lab.md`](../spec/learning-lab.md) specifies two additive modules:

1. Explicit task/arm/phase/group/sample evidence with taskwise calibration.
   Count invalid groups separately; never let storage-row multiplicity or a
   corpus marginal substitute for per-task reward-group statistics.
2. Scripted SQL evidence with immutable bytes/bindings and separate rescore
   and opt-in re-execution. Record the existing complete scoring result and
   selected instrument-source identity.

These are preparation for an evidence-producing learning experiment.
They do not implement sampler tokens, gradients, checkpoints, independent
sampling proof or full split-content auditing. Declared sample IDs and
fingerprints are not authenticated evidence. No upstream implementation or
reward/drop/retry policy is imported.

Full source-path notes and test-inspection limits are preserved in the local
scratch research reports `deep-environments.md`, its JSON source manifest,
and `deep-learning-systems.md` under
`~/scratch/co-train-harness-research-2026-10-23/`.
