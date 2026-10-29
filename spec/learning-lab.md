# Calibrated learning diagnostics and scripted SQL evidence

2026-10-23. Baseline `f817045`. Add an offline instrument for investigating
learning signal and reproducing execution evidence. This slice does not
implement model generation, training, or a new experimental treatment.

## Test plan, before implementation

All criteria below are engineering checks, not scientific amendments.

1. Exact screening: `p=.10`, `screen_n=group_g=4`, `ceiling=.60` gives
   true dead probability `.6562`, acceptance `.3438`, and conditional plug-in
   dead estimate `.2927028795811518`, each within `1e-12`.
   Support distinct screening sample count and future group size; zero
   acceptance returns `None`, never a fabricated conditional estimate.
2. Group evidence: two balanced groups versus two saturated groups have the
   same marginal success `.5` but empirical dead fractions `0` and `1`.
   A marginal-only implementation must fail. Preserve task/arm/phase strata.
3. Group admission: require exactly G distinct sample IDs per group. Reject
   duplicates, reused samples across phases, mixed identities/configurations,
   evaluation-task overlap, booleans masquerading as numbers, and nonfinite
   rewards. A group containing invalid task evidence is visible but has no
   dead-group classification. Do not convert invalid evidence to valid zeros.
4. Real fixture integration: use `fixture.materialize` and `load_bird`, all
   committed fixture tasks and both existing arms (at least 16 episodes).
   Correct scripted final SQL scores `1.0`; two fresh re-executions preserve
   each arm's deterministic observations exactly.
5. Noninterference: prompt, action and observation strings match direct
   `build_sql_arms`/`ArmPair.run` output, with zero differing bytes. Do not
   normalize the known cross-channel divergences or require both arms'
   rendered observations to be identical.
6. Admission budget: accept eight action submissions; reject nine before
   dispatching any action. Final answer text is not an action submission.
   This is a restricted scripted recorder, not native model-round accounting.
7. Operation separation: rescoring dispatches zero backend actions. Explicit
   re-execution dispatches exactly the recorded count. Neither calls a
   generator. Loading/decoding an artifact never executes its actions.
8. Scorer fidelity: correct, wrong, empty, malformed, fenced final answers,
   and invalid golds preserve all existing `ExResult` fields. Action rejection
   text is not treated as proof of successful or failed final SQL.
9. Binding: independently corrupt task, database, prompt, caller IDs, and
   instrument/scorer settings. Reject all five before action execution.
   Recomputed self-digests must not bypass external task/ID/source checks.
10. Encoding: canonical UTF-8 JSON round trips immutable records byte-for-byte.
    Reject unknown versions/keys, duplicate JSON keys, malformed digests,
    nonfinite numbers, oversized input and invalid types. No pickle/eval.
11. Integration: combine actual episode scores into calibration samples,
    preserving invalid status. Removing task binding, reusing confirmation
    samples, or replacing taskwise reduction must each fail a negative control.
12. Run narrow tests, independent runtime negative controls and the default
    offline suite, including real isolated mutation baselines. Do not install
    dependencies to hide the existing optional torch skip or cold-cache gap.

## Reference and known seams

`spec/spikes/reference/sql_replay.py` passed on Python's SQLite 3.50.4.
For one real fixture task, same-arm observations were identical across two
fresh wrapper directories, including query errors and PTC partial-output
rejection. It does not prove arbitrary-program determinism.

The exact calibration diagnostic previously ran with all 16 G=4 Bernoulli
outcomes and a failing marginal-only control. Its archived command/results are
in `~/scratch/co-train-harness-research-2026-10-23/`.

Use the existing `ptc.sql_arms.build_sql_arms` and `ArmPair.run`, unchanged.
`ArmPair.run` does not enforce its Budget and returns only observation text.
The new recorder validates complete scripted admission before dispatch; it
does not infer backend return codes from observation text.

## Implementation A: calibration

Owner files: `bench/frontier/calibration.py`,
`bench/frontier/test_calibration.py`.

Public API:

```python
exact_screen(p, *, screen_n=4, group_g=4, ceiling=0.60) -> dict
summarize_groups(samples, *, group_g, evaluation_task_ids) -> dict
```

`exact_screen` uses binomial counts, not exponential sequence enumeration.
Validate finite non-boolean numeric p in [0,1], ceiling in (0,1), positive
integer `screen_n`, and integer `group_g >= 2`. Resource-bound both counts to
256, an operational diagnostic limit, not a change to training G.
Return an explicit hypothetical IID Bernoulli assumption, supplied parameters,
true dead probability, acceptance probability and conditional plug-in estimate.
Compare screen-boundary probabilities as exact rational values, including a
Fraction/Decimal ceiling, so complementary outcomes cannot diverge due to
floating-point subtraction. Preserve input probability/complement before
log-weight conversion; an interior Decimal must not become an endpoint.
Return JSON-safe canonical `p_exact` and `ceiling_exact` rational strings
alongside approximate numeric fields. Final float-unrepresentable acceptance
may report zero/None; conversion-rounded input endpoints must not erase a
representable acceptance tail.
Validate count limits before numeric expansion. Resource-bound Decimal
coefficient/expanded components to 8192 decimal digits and rational components
to 32768 bits, rejecting oversized inputs before Fraction conversion.
These are operational bounds, not scientific thresholds. Preserve the
5000-digit tail regression without disabling Python's global integer limit.

Provide frozen `SampleEvidence` with explicit fields:
`sample_id`, `group_id`, `task_id`, `task_fingerprint`, `arm`, `phase`,
`corpus_id`, `split_id`, `run_id`, `policy_revision`, `scorer_id`,
`score`, `status`, `valid`.

IDs/fingerprints/provenance are caller declarations, not authenticated facts.
Require nonempty identity strings, arm ptc/bash, phase screen/confirmation,
and strict boolean validity. Valid scores are binary 0/1, never bool;
invalid scores may be None or finite binary values but remain unusable.
Require every sample ID to be globally unique within the supplied collection.
Group by globally unique group_id; require all other identity/configuration
fields to agree within a group, and exactly group_g members.

Return schema version 1; complete group records (including sample IDs and
invalid statuses), plus taskwise summaries stratified by task fingerprint,
arm, phase, corpus/split/run/policy/scorer. Include all/usable/invalid group
and sample counts, status counts, valid successes, empirical dead-group
fraction and separately labelled plug-in estimate. Invalid groups contribute
to neither dead classification nor usable reward denominators; report their
counts explicitly. Empty usable strata have None estimates.

No files, CLI generation, task selection, retained list, probe calls, manifest
API, automatic filtering/resampling or confidence/independence claim.

Public output names fixed by the failure-first tests:
`true_dead_probability`, `acceptance_probability`,
`conditional_plugin_dead_estimate`; summary `schema_version`, `groups`,
`strata`; count fields `all_group_count`, `usable_group_count`,
`invalid_group_count`, `all_sample_count`, `usable_sample_count`,
`invalid_sample_count`, `valid_successes`, `status_counts`.
The invalid-sample count includes every member of an unusable group, not only
its individually invalid members. Strata expose
`empirical_dead_group_fraction` and `plugin_dead_estimate` separately.
Group records retain aligned `sample_ids`/`statuses`, `usable`, nullable `dead`.
Declared evaluation-task ID exclusion does not establish content-disjoint
splits, independence, or safe procedural-generator seed separation.

## Implementation B: scripted episode evidence

Owner files: `train/sql_episodes.py`, `train/test_sql_episodes.py`.
Keep PTC-dependent integration outside standalone bench tests. Existing train
mutation copies include whole packages, so no copy-list expansion is needed.

Public API:

```python
EpisodeIds(corpus_id, split_id, run_id, episode_id, policy_id, policy_revision)
record_scripted(task, *, arm, actions, final_answer, ids) -> SqlEpisode
encode_episode(episode) -> bytes
decode_episode(data) -> SqlEpisode
rescore_sql(episode, task, *, ids) -> ExResult
reexecute_sql(episode, task, *, ids, allow_execution=False) -> ReexecutionResult
```

Use frozen dataclasses/tuples, not mutable nested dictionaries. Explicit
`origin="scripted"`; no invented model/tokenizer/generation/logprob data.
Caller policy provenance may name the scripted fixture, never an inferred
model run. No optional token-evidence API in this first slice.

Require valid arm and IDs, a complete sequence of at most the existing
`guards.eval_max_turns()` action strings, and string final answer (empty allowed).
Validate admission before building/executing arms. Use a private managed
wrapper directory for bash; do not expose arbitrary writer destinations.

Store schema/origin; explicit IDs; task ID and fingerprint; stable DB content
digest; exact schema/backend prompt; backend identity; action cap; distinct
action/scorer row limits; comparison and scorer timeout; selected instrument
source digest; action/observation pairs; final answer and extracted SQL;
scripted terminal label; and complete frozen `ExResult`.

Task fingerprint covers all SqlTask fields except mount path. Database bytes
and current prompt bind the mount independently. Reject active/stale WAL or
rollback-journal sidecars rather than hashing only a possibly incomplete main
file. Check DB content before/after operations. This requires a stable,
caller-owned snapshot; it is not protection against malicious concurrent ABA
writes or a filesystem snapshot mechanism.

Bind the selected on-disk instrument sources: `bench/score.py`,
`ptc/sql_arms.py`, `ptc/runtime.py`, `ptc/sql_runtime.py`,
`ptc/sqlite_safety.py`, `ptc/harness.py`. Include Python/SQLite runtime
identity available without model/network calls. This is not a complete SBOM
or attestation of in-memory monkey patches.

Use existing `extract_sql` and `execution_accuracy`, set comparison, existing
default scorer limits, unchanged action cap and current backend defaults.
Never remap invalid golds, revise scorer policy or add model-visible fields.

Encoding is a strict versioned envelope with canonical payload SHA-256;
maximum encoded/decoded size 8 MiB. Self-digests detect corruption, not
authenticity. Unknown input is data, never code. No artifact writer is added.
Before rescore/re-execution, verify caller-supplied IDs, current task/DB,
instrument configuration and prompt against the artifact.

Rescore runs only protected final/gold SQL. Re-execution requires
`allow_execution is True` and replays recorded actions through a fresh arm,
then returns current observations/score plus explicit match booleans.
This opt-in is an accident-prevention boundary, not a shell sandbox. Bash
actions execute a real shell: use trusted scripts, never unsolicited artifacts.
Do not auto-retry or normalize mismatches. Preserve the original artifact.

The captured backend prompt is not the full production model request:
system instructions, tool schemas and chat-template rendering are not captured.
This API makes no token/loss/optimizer or real-policy reproduction claim.

Public record names fixed by the failure-first tests:
episode fields `schema_version`, `origin`, `ids`, `arm`, `task_id`,
`task_fingerprint`, `db_sha256`, `schema`, `prompt`, `backend`, `instrument`,
`steps`, `final_answer`, `extracted_sql`, `terminal_label`, `result`.
Each frozen step stores `action`, `observation`; terminal label is
`scripted_final`. Replay returns `observations`, `result`,
`observations_match`, `score_matches`. The canonical JSON envelope has
exactly `schema_version`, `payload`, `sha256`; the hash covers canonical
payload bytes. Selected source bindings are not a complete shell/CLI
environment snapshot.

## Parent integration and review

Parent owns `train/test_learning_lab.py`, reference/spec/research documents,
runtime negative controls, default suite and one reviewed commit boundary.
Implementation agents edit only assigned files, write tests first and stop
for the parent's red run before implementation. They never commit or push.
Python and security reviewers inspect the final implementation.

Deeper source teams inspect Harbor/OpenEnv and Agent Lightning/Reasoning Gym
core execution paths and relevant tests at pinned revisions. Reports must
distinguish source, test inspection, author claims and actual local execution.
Do not silently substitute findings for implementation requirements.

## Deferred scientific work

Real generation/token/logprob collection, optimizer and checkpoint integration
follow a separately resolved frozen stack and authorized frontier measurement.
Warm-start, mixed-interface training, harness search, and new compositional
tasks are separate treatments/instruments, not included changes.

Follow-on acceptance gates, not permission to run or change them:

| Remaining work | Required evidence before promotion |
| --- | --- |
| Frozen runtime resolution | Owner-approved dependency contract, import/preflight receipt and one real compatible native tool-loop execution; do not silently move Transformers<5 to >=5.2 |
| Sampler boundary | One actual sampled tool trajectory with tokenizer/render identity, exact aligned token IDs/mask/logprobs and zero observation-token loss; reject one planted misalignment |
| Optimizer/checkpoint | One bounded real update with finite gradients and changed weights; save/reload yields the same fixed-input evaluation before claiming training works |
| Frontier confirmation | Freeze model/revision/channel/G/IDs/corpus/sampling/evaluation membership, then separately approve generation and independent confirmation; no manifest from synthetic estimates |
| Invalid gold handling | Signed void/mask policy and an explicit defective-gold regression before excluding or training on those outcomes |
| Cold-cache operation | A clean offline startup either succeeds from declared local inputs or fails with a named missing artifact, never downloads implicitly |
| Sweep cancellation | A real timeout/cancel check proves the daemon worker stopped, not merely that its wrapper directory remained isolated |
| Harness/policy gain | Compute-matched registered cells and unchanged held-out scoring; no fixture/replay statistic presented as learning gain |

## Non-goals and protected boundaries

No dependencies/downloads, GPU/model/paid jobs, production deployment, push,
manifest writes, signed amendment/threshold/window changes, new sampling or
invalid-gold policy, model/revision/G/task-ID/corpus/channel selection, prompts
or registered tools changed, evaluation-membership changes, or dormant guard
activation. Main training remains fail-closed. No 100x or policy-gain claim.
