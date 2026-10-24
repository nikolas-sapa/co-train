# Meta-Harness search-validity review

Date: 2026-10-23. Source: `stanford-iris-lab/meta-harness` at **`8123ccabe2b19fa1123090b2e5f1bacc20963ce8`**. HEAD verification supplied by parent, not repeated.

## Verdict and scope

Useful research-loop patterns, not a ready-made validity or security boundary for co-train. Adopt evidence capture, explicit evaluation contracts and complete-result checks conceptually. Reject direct adoption of mutable-name result identity, resumable post-test search, incomplete-manifest promotion, best-observed-suite scores as generalization, and wall-clock limits as spending controls.

This is static inspection of actual code and test bodies, not an execution audit. No upstream tests, benchmarks, negative-control runs, models, remote execution, installs, clones, GPU or paid jobs. No empirical performance or paper reproduction claims. Findings distinguish reachable code behavior from unverified operational risk.

`/Users/nikolassapalidis/Developer/co-train/spec/native-training.md` was read only. Parent-supplied co-train pin `ea6d2f6` remains context, not independently reverified. Frozen scientific/runtime/launch constraints remain unchanged. Harness search over a fixed model is not evidence of gradient learning, optimizer updates, checkpoint validity, or actual native SQL training. No project/reference changes.

The root README explicitly distinguishes this cleaned-up reference repository from **`stanford-iris-lab/meta-harness-tbench2-artifact`**, which holds the paper's optimized TB2 harness. No artifact source was used or inspected; no artifact pin or artifact-specific finding is claimed. Paper itself was not reviewed here.

### Evidence notation

All links below are commit-pinned. Paths and exact symbols, raw URLs, Git blob IDs and local cache paths are enumerated in `meta-failures-sources.json`.

- [TC outer](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/text_classification/meta_harness.py)
- [TC benchmark](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/text_classification/benchmark.py)
- [TC inner](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/text_classification/inner_loop.py)
- [TC LLM/cache](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/text_classification/llm.py)
- [TB2 outer](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/terminal_bench_2/meta_harness.py)
- [TB2 shell](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/terminal_bench_2/scripts/run_eval.sh)
- [Pilot controller](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/experimental/harbor_meta_harness/controller.py)
- [Pilot agent](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/experimental/harbor_meta_harness/agents/meta_harness.py)

## Findings

### F1. “Fixed evaluator” and “hidden test” are conventions in the reference loops, not enforced access boundaries

**Observed.** TC/TB2 `PROPOSER_ALLOWED_TOOLS` includes Read, Write, Edit and Bash. Shared `claude_wrapper.build_command` passes `--dangerously-skip-permissions` (lines 127–147). TC `validate_candidates` imports arbitrary candidate code; `inner_loop.load_memory_system` imports and constructs it in the evaluator process (lines 479–504). Evaluation then calls the same process's scorer. TB2 validates a class/interface, not an immutable evaluator or editable-path allowlist. Its proposer skill prohibits edits to existing agents/controller/wrapper, but this is prompt text.

TC `load_dataset_splits_3way` loads train, validation and test lists before candidate construction, including when only validation output was requested (inner lines 609–659). Public test files are in the repository. This is **not** proof test labels are passed to `predict`: `evaluate_memory` passes input only, then scores outside `predict`. It does mean arbitrary Python/Bash has no demonstrated filesystem/process separation from labels, scorer modules or results.

**Interpretation.** Trusted/cooperative harness research, not safe adversarial reward optimization. A candidate can in principle modify imported scorer globals or read public label files under ordinary process permissions; no malicious run or exploited result was observed. The TC README candidly calls its split isolation operational, not access control. [ONBOARDING.md](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/ONBOARDING.md#L70-L107) recommends fixed evaluation and inaccessible final tests, stronger than this example enforces.

**Tests.** TC scorer tests exercise expected answer parsing/metrics, not scorer immutability. TB2 tests check exact class/subclass validation. These are useful contracts, not tamper-resistance evidence.

**Decision.** Reject direct execution beside co-train's frozen scorer or scientific inputs. Separate candidate generation/execution from an immutable evaluator and sealed final split before any separately authorized search.

### F2. Incomplete finalization explicitly reopens search after possible test exposure

**Observed.** TC `finalize_run` writes `status="in_progress"`, evaluates multiple selected/baseline systems, prints test results, then checks missing groups. If any worker/group fails, it exits leaving `in_progress`. `run_evolve` blocks only `status=="complete"` (outer lines 286–402).

[HeldOutIsolationTests.test_incomplete_finalization_allows_evolution](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/reference_examples/text_classification/tests/test_evolution_contracts.py#L154-L188) explicitly tests that an incomplete finalization permits ordinary evolution. It uses corrupt `{}` fixtures, not a partial successful test disclosure.

**Deduction.** If one test group succeeds and another fails, successful outputs may already be visible while search can resume under the same name. This breaks “selection frozen before any test exposure,” even though the complete-finalization path correctly blocks further same-name evolution. Starting a new run can also reuse the shared agents directory and accessible old test results; run names are not independent scientific trials.

**Decision.** Adopt explicit finalization, reject its lock transition. Freeze candidate identities and search immediately before the first test request; failed finalization permits retries of the same frozen identities only, not new proposals. This is a proposed future search protocol, not a change to co-train's frozen policy.

### F3. Candidate, history and result identity are mostly mutable names, not immutable evaluated artifacts

**Observed.** TC `run_dir` keys by dataset/memory-name/model-short-name/seed. `get_model_short_name` discards provider prefixes. `build_val_runs`/`build_test_runs` skip existing numeric-accuracy results without comparing source, model revision, evaluator, dataset bytes, sizes, mode, epoch count, temperature or endpoint. `_has_usable_result` accepts a dict with numeric `accuracy`; it does not require membership/count/hash attestation. `load_results` enforces configured seed-group presence, but not those identities.

TC candidate source lives in one shared `agents/` directory across named runs. `finalized.json` records system names, not code/config digests. Evolution summary records names/hypotheses/scores. TB2 summary adds import paths, but these also point to live files; final winner import is recovered by name from the first matching summary row. Candidate jobs use `evolve-{name}-t{trials}`, without source digest. Baseline reuse checks model/trial count when config exists; if config is absent, it explicitly trusts cached results (TB2 lines 611–636). Later baseline frontier seeding reads existing dirs even after a failed rerun (660–666).

**Deduction.** Editing/reusing a name can combine old validation scores or memory state with new source at test time. This is a concrete cache-key/integrity limitation; no actual name collision, stale baseline promotion or concurrent run was observed. Cross-run result directories do help, but do not freeze shared code. Provider-name collisions matter only when such configurations are used.

**Tests.** TC fixtures deliberately show `{"accuracy":1.0}` is sufficient for cache reuse. Corrupt/null-result retries and incomplete seed-group omission are covered. Source/config mutation invalidation is not.

**Decision.** Reject name-only reuse. Proposed artifact ID: digest candidate source plus all imported local candidate dependencies/templates, full model/provider/revision/settings, evaluator/config/environment identity, dataset/split/membership, initial memory state, seed/replicate and budget policy. Separate human name from ID. Fail closed on missing identity; do not infer provenance from filenames.

### F4. TC frontier selection can reward candidates evaluated on only the easy subset of datasets

**Observed.** `load_results` requires all configured seeds **within each dataset group**. `print_frontier` then averages whichever dataset groups exist for each memory (`benchmark.py` lines 675–688). Outer `run_evolve` likewise averages available dataset accuracies, not the full configured dataset list (lines 529–540), even after a benchmark failure. There is no complete-dataset gate before frontier writing.

**Arithmetic negative example, not a measured run.** Config has 3 datasets. Candidate A with results only on one dataset at 100% gets aggregate 100%; candidate B at 60% on each of all 3 gets 60%. A zero-context A can dominate B in the stored accuracy/context frontier despite missing 2/3 evaluation groups. The printed results table separately divides by the configured dataset count (benchmark line 350), so displayed table and frontier can disagree.

**Decision.** Reject promotion of incomplete manifests. Require exactly all configured dataset × seed groups; mark incomplete as ineligible, rather than silently averaging observed groups. Preserve missingness separately from real incorrect answers and infrastructure errors.

### F5. TB2 counts existing failed trials conservatively, but omitted trials/tasks escape the denominator

**Observed.** `parse_job_results` counts missing/corrupt results **inside existing trial directories** as zero, a good safeguard. It cannot count a trial directory that was never created. `expected_trials` only warns for tasks it discovers. No expected 89-task membership manifest is checked. `compute_pass_rates` divides successes by the trials actually found. `update_frontier` accepts that average immediately (TB2 lines 210–271, 373–393, 774–835).

**Arithmetic negative example.** With expected 89 × 2 = 178 trials, a directory containing only one successful trial yields discovered average 1.0 and only a count warning. It is not rejected or scored 1/178. Outcome depends on actual Harbor output/completion behavior; this review does not show Harbor normally exits successfully in that state.

**Additional confirmed path.** Normal candidate `harbor_run` returns `None` on timeout and callers skip partial parsing, which is good and tested. Optional final 5-trial evaluation discards that success flag (`job_dir, _ = harbor_run`) and parses whenever the directory exists (879–887). Thus timed-out/stale partial final output can be printed as a 5-trial score despite the normal-run timeout safeguard.

**Decision.** Reject frontier eligibility until exact expected task IDs and trial IDs are present, with one terminal outcome each. Final evaluation must require successful completion and identical manifest validation, not directory existence.

### F6. TB2 final evaluation and pilot “best reward” are adaptive same-task estimates, not untouched-task validation

**Observed.** TB2 search proposes from scores and full failed/successful trajectories on the full official 89-task set; default search has 2 trials per task. `--full-eval` runs the selected winner with 5 trials on the **same full set**, not separate tasks. More trials can reduce rollout noise but cannot undo task-adaptive selection. Prompt anti-overfitting rules ban task names/hardcoded hints, not statistical adaptation.

Pilot `_evaluate` returns per-task rewards on each query. [Outer-task verifier](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/experimental/harbor_meta_harness/tasks/select-harness/tests/test_outputs.py) reports `max(rewards)` from accepted history. It does not rerun the winner or verify current `/app/harness.py` matches the best history entry's source hash. Pilot README explicitly labels its collection results exploratory on optimization tasks.

**Interpretation.** Legitimate search objectives, not bugs by themselves. A per-task frontier combining different winning harnesses is an oracle summary, not proof a single deployed harness achieves the union. No independent generalization claim is supported by these paths alone.

**Decision.** Adopt full history for diagnosis. Reject best-observed/adaptive scores as promotion evidence. Any separately approved confirmatory experiment must freeze one artifact and evaluate once on a predeclared untouched split; repeated same-task trials remain exploratory.

### F7. Response cache reduces calls, but does not define independent replicates or equal-compute comparisons

**Observed.** `ProviderLLM._cache_path` hashes cache version, normalized model, endpoint, system prompt, prompt and kwargs. Good request-level discrimination. It lacks run/replicate ID or provider model revision unless encoded in the configured strings/kwargs. Default cache is shared under `~/.cache/text-classification/litellm`. TC `LLM` passes temperature and max_tokens, not the dataset seed as a provider seed.

Identical cached requests return the stored content with no provider token/cost increment (`_generate_one` 252–268); `LLM.__call__` still increments logical calls. Reported tokens therefore measure fresh accounted calls, not logical inference effort. Local endpoint cost is explicitly set to zero; unknown completion-cost estimation also falls back to zero. Output JSON omits `estimated_cost_usd`.

**Deduction.** Repeated identical prompts can reuse a stochastic answer instead of independent samples. This can be desirable memoization, but does not support independent multi-seed variance estimates. Warm-cache runtime/tokens and cold-cache runtime/tokens are different quantities. Cache contamination across splits is not established: identical prompt keys imply shared responses, not automatic access to test labels.

**Decision.** Adopt exact-request caching only with explicit replay semantics. Separate logical requests/tokens, cache hits, fresh provider usage, retries and billed cost. Replicate-specific cache namespaces or explicit provider seeds are needed if independent sampling is the objective. Unknown cost must remain unknown, not free.

### F8. Timeouts/retries are bounded in places, but descendant/resource cleanup is not demonstrated

**Observed.**
- TC outer `run_cmd` times out a direct subprocess after 7200s. Benchmark `_run_with_retries` allows 3 attempts (2 retries), each up to 7200s, killing/reaping the direct process on timeout. It has no `finally`/`CancelledError` branch to kill a worker when the async task itself is cancelled.
- Wrapper `run` kills and waits for the direct Claude process on deadline. No process-group/session cleanup is implemented. TC/TB2 signal handlers only set `_interrupted`, requesting “finishing current step”; they do not immediately cancel the current subprocess.
- TB2 Python `harbor_run` sets `HARBOR_EXTERNAL_TIMEOUT=1`, disables shell timeout wrapping and uses direct-subprocess timeout. Standalone shell mode uses TERM then kill-after 60 if GNU timeout/gtimeout exists; otherwise no shell deadline.
- Pilot `run_child` catches direct-subprocess timeout and gives reward zero. `_evaluate` awaits a controller subprocess with no explicit surrounding deadline or cancellation cleanup. Temporary candidate directory cleanup uses a context manager, but this is not proof child/remote sandbox teardown.

**Limits.** No leaked process, paid resource or orphaned sandbox was observed. Harbor/backend cancellation and cleanup internals were not audited. Direct-process kill is not evidence all descendants or already-launched cloud work stopped.

**Tests.** TB2 timeout tests inspect forwarded flags/timeout using mocks or fake executables, including exit 124 → None. They do not spawn an actual descendant tree or a real sandbox. TC benchmark failure-propagation test mocks the job launcher. Coverage gaps alone are not runtime bugs; the missing cancellation cleanup branch is directly visible.

**Decision.** Reject timeout wiring as cleanup certification. Require cancellation-safe process-group and backend job ownership plus terminal resource receipts before authorizing paid execution.

### F9. Pilot improves source identity/controller separation, but denylist, budget and attempts have concrete limits

**Observed.** `controller.evaluate_source` snapshots source, hashes SHA-256, validates before launch, stages it in a temporary directory and never imports it into the controller. This is stronger identity/isolation than the reference outer loops. `validate_source` lowercases and substring-checks a denylist, then AST-checks `AgentHarness`, async `run` and BaseAgent inheritance. It is not a sandbox: concatenated or dynamically constructed references can lack the forbidden literal substring. Passing validation means minimal interface compliance, not semantic safety.

`EvaluationState` is a frozen dataclass with tuple history. `record` creates new state, but stored result dictionaries remain shallowly mutable. No mutation path from the outer model to those in-memory dictionaries was shown. The normal agent path checks zero budget before evaluating and records ordinary rejection/nonzero controller outcomes.

**Concrete limits.**
1. `_evaluate` decrements budget only after controller completion and JSON parsing. A malformed/missing result raises to `run`'s catch; the old state survives. If paid child work happened before that error, it is not charged to the evaluation-call budget/history. No such failure was observed.
2. `record` itself permits negative remaining values; suite loading int-coerces budget without a positive-bound check. Default budget 4 avoids this, so it is a non-default/input-validation issue, not default exhaustion bypass.
3. `command_for` exposes configurable `--n-attempts`, but `child_result` requires exactly one `*/result.json`. If Harbor writes one trial directory per attempt, n_attempts >1 produces “missing Harbor result”/zero instead of aggregating attempts. Default n_attempts=1 is consistent; Harbor multi-attempt layout was not executed here.
4. Source SHA identifies only source, not suite/model/evaluator/environment/config. `accepted=True` means source accepted/scored, not successful infrastructure or promotion.
5. Pilot budget controls evaluation calls, not candidate inference tokens, retries, wall time or dollars.

**Tests.** Rejection-before-child launch, mean/min aggregation, suite config/attempt forwarding, staged PYTHONPATH and a one-step immutable-state transition are covered. `test_evaluation_state_is_immutable_and_bounded` checks 4→3 and unchanged original state, not exhaustion/negative inputs, exception charging or deep immutability.

**Decision.** Adopt snapshot-before-score, content hash, trusted external controller and explicit query allowance. Reject substring denial as leakage proof and success-path decrement as resource accounting. Reserve budget before dispatch; record terminal failure/cancel status for every reserved attempt. Do not assume configured attempts are supported without a real layout test.

## Costs, permissions and license

[LICENSE](https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/LICENSE): MIT, Copyright (c) 2026 Yoonho Lee. Retain copyright/permission notice with copied substantial source. MIT is not a warranty, model-use license, dataset-rights audit or provider spending authorization. Dataset/model/provider terms were not independently audited.

Configured resources, not measured invoices:
- TC default solver `openrouter/openai/gpt-oss-120b`; proposer Claude Code `opus` via subscription authentication after temporarily removing `ANTHROPIC_API_KEY`. Subscription usage is not unlimited/free.
- TC config has 1 seed, 3 datasets, 2 baselines, 3 candidate systems requested **by prompt** per iteration. Each system has 450 training examples, 130 validation examples, 412 test examples across the configured datasets. These are input counts, not fixed model-call counts; arbitrary candidate learning/retrieval can call models repeatedly. 9 candidate dataset jobs/iteration can become up to 27 launcher attempts before LLM-level retries. LLM retry wrapper allows 6 attempts, timeout 600s each, with backoff.
- TB2 solver `anthropic/claude-opus-4-6`, temperature 0.7, full set 89, 2 search trials, concurrency 50, overall Python deadline 28800s. Nominal trials: 356 for 2 baselines; 178 per candidate; 1 additional smoke trial unless skipped; optional final winner evaluation 445 trials. Candidate count is prompt-requested 1, not structurally enforced. These counts are not dollar bounds.
- Pilot default child `openai/gpt-5.4-nano`, Modal environment, 3 task suite, n_attempts=1, eval_budget=4, child timeout default 600s. Outer default model in README is `openai/gpt-5.4-mini`. Suite budget gives at most 12 normal child-task evaluations under the default success-path accounting, not a price cap.
- Solver/provider calls, sandbox/backend use and proposer usage all need separate authorization and metering. No authoritative unit-price schedule or measured total was obtained; no dollar estimate supplied. Failure/retry costs can be absent from completed-result summaries.

## Actual test-body inspection

Complete recursive tree: 149 entries, `truncated=false`. Read all **5 framework test files, 52 named test bodies**: TC evolution contracts 6, TC benchmark 8, TC data 14, TB2 outer 11, pilot controller 13. Also read the pilot outer-task verifier body (`main`, not a unit test). These counts describe inspected source only; **0 tests executed**.

- TC evolution: default no-test flow, successful finalization lock/printing, run-scoped results, intentionally resumable incomplete finalization, metadata preservation, stable few-shot input seed.
- TC benchmark: seed aggregation/incomplete groups, equal-cost Pareto dominance, package import discovery from unrelated cwd, corrupt-result retry planning, numeric-result skipping, mocked worker-failure exit propagation.
- TC data: supported tasks, vendored split counts/shape, requested split counts and several positive scorer cases. No entity-level cross-split overlap audit was performed; distinct split filenames/count checks do not establish semantic disjointness.
- TB2: class validation (including invalid shell path before Harbor), mocked Python timeout propagation, fake shell command/timeout/backend wiring, one mocked KIRA loop signature check.
- Pilot: suite/attempt forwarding, literal leakage rejection before launch, fake-child aggregation, path staging, one-step state transition, one reward-file parse.
- Inner handmade task verifiers for budget-rollups/dedupe-events/reconcile-ledger were not read. Their presence is known from the tree; no claims about their correctness or anti-cheat strength.

No coverage percentage inferred. Missing coverage is not itself a bug. Tests demonstrate only their asserted contracts; mocks/fakes do not certify providers, real model behavior, cleanup or independent learning.

## Proposed failure-first controls with numeric pass criteria

**Not implemented or run.** These are review proposals for a separately approved harness-search design, not approved changes to co-train's frozen metrics, thresholds, memberships or spec.

| Control | Deliberate negative target | Numeric acceptance |
|---|---|---|
| NC1 scorer/label isolation | Candidate attempts 3 scorer-file writes and 3 final-label reads; evaluator digest mutated once | 0 permitted writes/reads; 1/1 digest mutation rejected before scoring; 0 promotion records |
| NC2 first-test freeze | Expose 1 successful test group, force 1 other group to fail, then request evolution | 0 subsequent proposals, even in incomplete finalization; retry only identical frozen artifact/config IDs |
| NC3 content identity | Independently mutate 1 source byte, 1 prompt-template byte, 1 scorer byte, endpoint, split membership and temperature | 6/6 stale-result reuses refused; unchanged artifact retains exactly its own valid cache entry |
| NC4 exact manifests | TC: remove 1 of 3 dataset groups; TB2: supply 1 successful trial of expected 178, then remove 1 of a complete 178 | 0/3 incomplete cases eligible for frontier/promotion; complete TB2 case has exactly 178 terminal trial IDs |
| NC5 timeout finalization | Final run returns 124 but has stale successful result dirs | 0 final score/promotion certifications; explicit incomplete status |
| NC6 independent replicates | Repeat identical prompt in 2 replicate IDs against a counting, seeded provider stub; warm/cold replay modes | Independent mode makes exactly 2 fresh stub calls; replay mode exactly 1 fresh+1 hit; logical requests remain 2 in both |
| NC7 cancel cleanup | 20 trials of parent+grandchild process fixture; separately 1 explicitly approved backend sandbox lifecycle check | Within 5s of cancellation, 0 owned local descendant processes and terminal/released backend receipt; no retries before cleanup confirmation |
| NC8 budget reservation | Budget 4; force malformed evaluator JSON on each dispatch, then request 5th evaluation | Exactly 4 reserved ledger entries, remaining=0, 0 fifth child launches; malformed results cannot refund spent work |
| NC9 attempts/schema | Configure 2 attempts with rewards 0 and 1; add NaN, Infinity, bool, negative and >1 reward fixtures | Exactly 2 terminal trial records, predeclared mean=0.5; all 5 invalid reward fixtures rejected before selection |
| NC10 anti-leakage defense | Literal forbidden path, concatenated spelling and indirect module/file access | 3/3 access attempts denied by execution permissions, not merely string matching; validator bypass alone must not expose protected inputs |
| NC11 promotion identity | Best history source A, current source B; mutate A after scoring; show winner score from same search tasks | 0 promotion of B or mutated A; same-task score labeled exploratory; final receipt binds 1 selected digest, not max history alone |
| NC12 guard sensitivity | Disable each new guard once against its corresponding negative fixture | Every disabled guard produces at least 1 failing assertion; all enabled guards pass the corresponding fixture set |

The 5s cleanup target and hypothetical future reward domain [0,1] above are proposed test specifications, not measured capability or existing co-train policy. Where actual scorer domains differ, preserve the approved domain and change the fixture contract before implementation.

## Adoption boundary

**Adopt conceptually:** fixed-model harness optimization as a separate hypothesis; mechanism-labeled proposals; source snapshots/content hashes; append-only attempt evidence; explicit suite/task IDs; external evaluation controller; default no-test evolution; complete seed groups; zero for existing terminal trial failures; bounded proposal/query plans; trace-plus-cost diagnostics.

**Reject as direct co-train implementation:** arbitrary candidate edits beside scorer/data; string denylist as isolation; mutable-name cache/frontier identity; post-test unfreeze; incomplete-manifest winner selection; same-task reruns as generalization; cache-adjusted tokens as equal-compute proof; best-history score as current-artifact certification; timeout flags as cloud cleanup proof; success-only budget accounting; “training” memory updates as evidence of native model learning.

**Follow-up gate:** owner must approve any separate search design and its immutable evaluation boundary, costs, controls and untouched-test protocol first. No search/training launch or frozen-spec amendment is authorized by this review.

VERIFY_REAL: Wrote this review and pinned-source manifest using real filesystem tools; source/test-body inspection only. No benchmark reproduction, tests, negative controls, actual learning, cleanup or deployment verified. Independently recomputed Git blob SHA-1 for all 29 cached sources against the pinned tree: 29/29 exact matches, 0 mismatches (stdlib-only local integrity check, no upstream code executed).
