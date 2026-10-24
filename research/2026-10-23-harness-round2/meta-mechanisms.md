# Meta-Harness mechanisms, pinned-source research

Date: 2026-10-23. Research only. No implementation or execution of repository code.

## Verdict and evidence boundary

Meta-Harness is **harness-code search around frozen models**, not native gradient training. Useful pattern: proposer selectively reads prior source, traces and scores; trusted outer code validates and evaluates; history supports subsequent proposals. No source evidence here establishes co-train sampler logprobs, optimizer updates, changed weights, checkpoint restoration, or real learning.

Authoritative co-train context: revision `ea6d2f6`, fail-closed native constructor, calibration/frozen scripted traces. Read `/Users/nikolassapalidis/Developer/co-train/spec/native-training.md` in full. Frozen dependency conflict and actual native-template identity/prefix failure remain blockers. Neither this research nor an offline harness-search fixture opens launch gates. No local revision recheck, per no-git instruction.

Primary source pin: `stanford-iris-lab/meta-harness@8123ccabe2b19fa1123090b2e5f1bacc20963ce8`. Parent supplied official-HEAD check; this worker fetched its recursive tree (`truncated=false`) and full relevant source/tests. References below use this pin, abbreviated `P`:

`https://github.com/stanford-iris-lab/meta-harness/blob/8123ccabe2b19fa1123090b2e5f1bacc20963ce8/`

Machine-readable full URLs, symbols, read scope and limitations: adjacent `meta-mechanisms-sources.json`.

## 1. Classification: actual proposal → validation → evaluation → history → selection

Paths relative to P, under `reference_examples/text_classification/`:

1. **Proposal.** `meta_harness.py::run_evolve` loads `config.yaml`, establishes `logs/<run>/`, optionally evaluates baselines, resumes at max summary iteration + 1, removes stale `pending_eval.json`, then calls `propose_claude`. `render_task_prompt` supplies summary/frontier/reports paths. `propose_claude` calls `claude_wrapper.run(model="opus", effort="max")`, default 2,400-second deadline. A successful CLI exit plus pending file existence counts as proposal success.
2. **Search guidance, not enforcement.** `.claude/skills/meta-harness/SKILL.md` asks for exactly **3** candidates, distinct falsifiable mechanisms, prototypes, no dataset-specific hints, and pending fields `name/file/hypothesis/axis/base_system/components`. Python only reads `.get("candidates", [])`; it does not enforce cardinality, structural novelty, immutable parents, required metadata, candidate-name grammar, or an edit allowlist. Candidate names are interpolated into a Python `-c` import string. Treat proposals as untrusted code/data.
3. **Validation.** `validate_candidates` runs a 30-second child import, `from text_classification.agents.<name> import *; print('OK')`; accepts exit 0 plus stdout containing `OK`. This executes candidate module top-level code. It does not instantiate, exercise cold-start prediction/learning, verify a `MemorySystem`, check reward integrity, or sandbox filesystem/network access.
4. **Evaluation.** `run_benchmark` invokes `benchmark.py` with run-scoped logs/results paths. `benchmark.build_val_runs` expands configured models × datasets × candidates × seeds, launches `text_classification.inner_loop`, saves `val.json`, `memory.json`, and training `log.jsonl`. Checked config: GPT-OSS-120B, offline mode, 1 epoch, temperature 0, batch 1, seed `[42]`, launcher concurrency 16; baseline systems `no_memory`, `fewshot_all`. These are release defaults, not paper reproduction parameters.
5. **Inner learning semantics.** `inner_loop.run_inner_loop` online mode predicts an entire batch before supplying evaluator feedback and ground truth to `learn_from_batch`. `_run_offline_loop` instead directly supplies labels as both prediction and ground truth, can evaluate validation after each epoch, and restores best serialized memory state. These are application-memory updates, not weight training. `evaluate_memory` calls prediction and evaluator without explicitly calling learning. It does not prevent a candidate's `predict` from mutating memory or reaching files.
6. **History.** `JSONLLogger` records train feedback, predictions, targets, prompt lengths/hashes and configured serialized-state checkpoints. `MemorySystem.call_llm` stores last prompt text/length/hash in thread-local state. `claude_wrapper.log_session` writes proposer metadata, raw stream events, response, extracted JSON artifacts and per-tool inputs/outputs. `update_evolution_summary` appends candidate hypothesis/axis/components, aggregate validation and timings. Candidate source files remain in a **shared agents directory**, not a content-addressed immutable per-run archive. Run-name scopes logs, not source ownership.
7. **Selection.** `benchmark.load_results` admits only complete configured seed groups, pools correct/total when available, sums usage/runtime, averages context characters. `print_frontier` selects per-dataset max accuracy with smaller-context tie-break; aggregate `compute_pareto_frontier` retains nondominated accuracy/context pairs. Exact accuracy/cost ties both survive. There is **no deterministic parent tournament**: proposer chooses which prior source to reuse. Final test selection is baselines ∪ validation Pareto systems ∪ per-dataset validation winners.
8. **Finalization.** `finalize_run` writes `finalized.json(status="in_progress")` before test calls, loads saved memory rather than retraining, verifies expected system/dataset complete result groups, then marks complete. A complete marker blocks subsequent `run_evolve`; repeat finalization only prints cached test results.

### Isolation and correctness caveats visible in source

- **Important explicit gap:** `run_evolve` blocks only `status=="complete"`. An incomplete finalization leaves `in_progress` and permits search, even after some test results may exist. `test_incomplete_finalization_allows_evolution` explicitly codifies this. Thus the docstring's "freezing" is weaker than irrevocable freeze-before-first-test.
- Held-out data are ordinary local files; proposer has Read/Write/Bash and candidate imports run on host. Splits are not a security boundary. `inner_loop` loads all three splits even in validation-only mode, although only requested predictions are scored.
- `data.api.load_dataset_splits_3way` uses separate MCE files, seeded shuffling, requested-count checks; transfer loaders use official validation splits or deterministic 80/20 train slicing. No content-deduplication or split-overlap assertion in inspected tests. This worker did **not** fetch dataset payloads or verify actual disjointness.
- `data.evaluators.get_evaluator` is trusted plumbing, but not filesystem-protected. USPTO lowercases dot-delimited reactant strings and compares sets, not chemically canonicalized equivalence. LawBench compares charge sets and returns extra F1 metrics; saved score selection is accuracy. Do not transplant these task-specific evaluators into SQL.
- **Aggregation discrepancy:** `print_frontier` averages over available dataset results, not an enforced complete dataset grid. Outer `run_evolve` similarly averages available scores. Complete seeds per dataset do not imply complete datasets per candidate; partial coverage can distort selection. `print_results` uses configured dataset count as divisor, so display and frontier can disagree.
- **History delta discrepancy:** frontier is updated before `update_evolution_summary`, which re-reads the newly updated frontier. Summary delta is therefore not reliably change against previous best. In classification the outer print normalizes fractional/percent values, while summary assumes percentage values. Failed imports get rows when all candidates fail; if some validate, invalid candidates disappear from that iteration's summary. A proposer failure writes no summary row, so resume does not count it.
- `run_evolve --model` checks/labels one model, but its benchmark invocations do not pass a model restriction; benchmark jobs expand configured `MODELS`. Current config has one model, limiting practical impact here.

## 2. TB2 reference search: different scientific protocol

Under `reference_examples/terminal_bench_2/`:

- `meta_harness.py::run_evolve` follows proposal/pending/import/smoke/full-eval/frontier/summary. Skill asks for **1** mechanism per iteration; code normalizes import classes to `AgentHarness`. `validate_agent_class` verifies the exact imported object is a class and a Harbor `Terminus2` subclass. Child imports still execute code, not static validation.
- `smoke_test`: one `extract-elf` trial, 1,800-second default; requires top-level result and zero reported errors, **not positive reward**. Can be skipped.
- `harbor_run` → `scripts/run_eval.sh`: `terminal-bench@2.0`, full 89 tasks, default 2 attempts/task, concurrency 50, Claude Opus 4.6. Hard 30-task subset exists in shell for manual development, not a held-out final split.
- `parse_job_results` ignores potentially stale top-level totals, reads individual trial directories. Existing trial directories with missing/corrupt results or absent reward count as zero. `compute_pass_rates` uses positive reward as pass and flat total passes / observed trials, not average of task averages.
- **Completeness gap:** expected trial counts only warn for observed tasks; entirely absent task/trial directories are not synthesized or rejected. Declared 89×2 does not guarantee denominator 178.
- `update_frontier` keeps strict per-task and global improvements. `update_evolution_summary` appends scores, hypothesis/changes/import path, rollout token/cost/turn metrics. Again delta uses post-update frontier, not necessarily the old best.
- Optional `--full-eval` evaluates the global winner for 5 attempts on the **same 89 tasks**. It is increased sampling, not out-of-sample generalization. Unlike search handling, final branch ignores `harbor_run` success flag and parses any existing job directory, so partial timed-out final data can be displayed.
- Skill bans task names and existing-file edits, but search loop has no corresponding static edit/leakage enforcement. Wrapper permissions are not isolation.

## 3. Experimental bounded Harbor controller, not the paper reference core

Read full `experimental/harbor_meta_harness/controller.py`, `agents/meta_harness.py`, `tests/test_controller.py`, collection preparer, suite and select-harness verifier.

- `AgentHarness._evaluate` downloads current `/app/harness.py` to host logs and launches short-lived `controller.py`; controller reads source, hashes SHA256, applies string denylist plus AST interface checks, stages `candidate.py` in a temporary directory and imports it only inside Harbor child processes. Parent controller does not import candidate.
- `validate_source` requires top-level `AgentHarness`, direct `BaseAgent`-named base and async `run`; rejects universal `/tests`, `test_outputs`, `verifier`, `/solution`, `task.toml`, plus per-suite task references. This is a lexical heuristic, **not semantic noninterference or sandboxing**. Encoding/constructing paths dynamically can evade string bans; comments can trigger false positives. Child host process inherits credentials/environment.
- Default suite: 3 synthetic tasks, mean aggregator, 4 evaluator calls, 1 attempt/task, default 600-second child timeout. Alternatives mean/min/fraction_solved. `prepare_collections.py` defines selected TB2-easy/HumanEvalFix/CodePDE suites and probe-result comments. Those comments are not independently verified gains.
- Frozen dataclass `EvaluationState` appends result history and decrements budget. `_evaluate` prevents calls at exactly zero. It records completed controller outcomes including rejection/failure, but exceptions before `record` (download, parse, launch) are caught in outer loop and can avoid debit. `record` itself does not enforce nonnegative remaining; dicts inside frozen tuple are mutable.
- Controller `child_result` expects exactly **one** `*/result.json`; configurable `n_attempts>1` conflicts with this reader. Missing/malformed results, nonzero child exit or timeout become reward 0; `evaluate_source.accepted=True` means source passed validation, not successful child execution.
- Outer loop caps turns at `max(24, eval_budget*3)`, terminal commands at 120 seconds, output at last 12,000 characters per stream. `_evaluate` waits for controller without its own aggregate deadline. No content-deduplicating cache or best-candidate restoration.
- `tasks/select-harness/tests/test_outputs.py` grades **maximum accepted reward in uploaded evaluation_history.json**, with only budget arithmetic sanity checking. It does not prove final `/app/harness.py` matches winning SHA or authenticate history. Best history score ≠ selected final executable.

## 4. Cache and timeout policies

| Layer | Actual source policy | Adoption risk |
|---|---|---|
| Classification result cache | Dataset/system/model-short-name/seed path; skip if JSON dict contains numeric accuracy. Inner CLI skip is weaker, existence-only unless force. | No binding to source SHA, dataset/scorer hashes, mode, epochs, temperature or full model identity. Numeric bool/nonfinite/out-of-range not strictly rejected. |
| Classification LLM cache | `llm.ProviderLLM._cache_path`: SHA256 of cache-version 1, normalized model, endpoint, system prompt, prompt, kwargs. Persistent shared cache; temp-write/replace with instance-local lock. | No TTL/provider revision/dataset isolation; cache replay not fresh stochastic sampling. Cached content schema is weakly checked. Identical stochastic requests can reuse one draw. |
| Usage accounting | Cache hit bypasses provider usage/cost increments; logical LLM calls still increment. Unknown token/cost estimation errors fall back to 0. | Distinguish physical spend, logical work and unknown usage. Zero is not proof of free/no work. |
| Classification deadlines | Import 30s; proposer 2,400s; outer benchmark command 7,200s. Launcher workers 7,200s/attempt × 3 attempts. LLM call 600s × up to 6 attempts, retry rate limits/timeouts with exponential+jitter waits. | Outer benchmark can expire before launcher retry budget; kills do not explicitly clean descendant process groups or remote jobs. |
| TB2 baseline cache | Model substring and attempt count checked if config exists; missing config is explicitly trusted. `--skip-baseline` can seed frontier from whatever results exist. | No strict expected-task/content/environment binding. Reused names can refer to changed source. |
| TB2 timeout | 28,800s default via env. Python subprocess enforces deadline; shell timeout TERM then kill-after 60s when available, unless external timeout flag. | Shell silently runs unbounded if neither timeout nor gtimeout exists; Python sets external flag. Remote cleanup not proven. |
| TB2 model calls | `baseline_kira.AgentHarness`: 900s API timeout × up to 5 attempts; nonretryable auth/bad-request/context/output/cancellation excluded. Selected infrastructure coroutines capped 600s; command duration capped 60s; output cap 30,000 bytes. | Limits cover different layers; not one global monetary or process-tree budget. |
| Anthropic prompt cache | `anthropic_caching.add_anthropic_caching` deep-copies messages and marks latest 3 messages' text/content blocks ephemeral for Claude/Anthropic model names. | Provider prompt caching, not evaluation-result validity. No local TTL set in this helper. |

No inspected test suite proves nested process/remote-resource cleanup, isolation under hostile code, cache-content invalidation, or correct stochastic independence.

## 5. Tests actually inspected, zero tests executed

Full files inspected:

- `reference_examples/text_classification/tests/test_evolution_contracts.py`: metadata preservation, stable SHA-based few-shot seed, default evolution without `--test` (zero iterations), mocked successful finalization + later search refusal, run-scoped test outputs, and explicit allowance of evolution after incomplete finalization.
- `.../tests/test_benchmark.py`: configured-seed pooling (15/20 = 0.75), omit incomplete seed group, equal-cost Pareto domination, cwd-independent worker construction plus a subprocess import-spec probe, corrupt val/test retry, usable-cache skip, mocked worker failure propagation.
- `.../tests/test_data.py`: supported task lists, expected vendored split counts, requested sizes, prompt formats, extraction and evaluator examples. **No split-disjointness test.**
- `reference_examples/terminal_bench_2/tests/test_meta_harness.py`: exact subclass acceptance/rejection, invalid class before Harbor launch, Python timeout wiring/refusal, shell timeout/environment/PYTHONPATH/temperature wiring using fake executables, one mocked KIRA loop-signature check.
- `experimental/harbor_meta_harness/tests/test_controller.py`: explicit suite resolution, command flags, interface/lexical rejection, reject-before-child, mocked mean/min aggregation, absolute jobs path, staged-child PYTHONPATH, functional state update and one synthetic Harbor result.
- `experimental/.../tasks/select-harness/tests/test_outputs.py`: verifier implementation inspected, not an independent test that proves its own tamper resistance.

These are **source-inspected test intentions**, not this worker's passing results. Fixtures/mocks do not establish real providers, Harbor infrastructure, runtime cost, held-out nonleakage, training or reproduction. Collection-suite test references downloaded task directories absent from the pinned source tree, so source presence alone does not establish a fresh checkout passes.

## 6. Paper, release and separate artifact must not be conflated

Paper read: `https://arxiv.org/html/2603.28052v1` (2026-03-30), especially §3, Algorithm 1, §4.1, §4.3, Appendix D. General method freezes base weights, exposes full prior code/scores/traces, permits proposer-chosen parents and returns frontier. Classification paper says 20 iterations × 2 candidates and online setting; release skill asks for 3 candidates, config defaults offline 1 epoch and trimmed baselines. Tree contains no math reference implementation. Therefore pinned release is not an exact archival reproduction of all paper experiments.

Paper §3's general held-out description has a domain-specific exception: §4.3 explicitly says TB2 search and final evaluation use the same 89 tasks. Do not call TB2 final resampling held-out evidence. Paper gains are author-reported results, not reproduced here and not transferable predictions for co-train.

Separate artifact: `stanford-iris-lab/meta-harness-tbench2-artifact@57fefdb2ff84af3fd81b69d67814acbe69bd0743`, resolved by public API during this research. Complete tree contains README, agent.py, anthropic_caching.py, prompt template, pyproject, and no tests/LICENSE. This is the published optimized TB2 agent, not the search controller. README describes environment bootstrapping and reports 76.4%; neither claimed saving nor score reproduced. This worker inspected metadata/tree and README diff, **not full artifact agent.py**, so makes no artifact runtime-code audit claim.

## 7. Licenses and approval boundaries

- Main pinned repository `LICENSE`: **MIT**, copyright 2026 Yoonho Lee. Preserve copyright and permission notice in copied/substantial portions. Acknowledge paper separately.
- Paper HTML advertises **CC BY 4.0**. Text/figures license differs from code license.
- Separate artifact has **no LICENSE file in complete inspected tree**. Do not assume main repository's MIT permission automatically covers this separate repository. Obtain explicit permission/license confirmation before copying artifact code.
- Vendored classification `data/README.md` lists MCE origins, not dataset license terms. Loader source lists runtime HF datasets; not every source is pinned. Dataset, model, Harbor, KIRA and dependency licenses/terms were **not fully audited**. Main MIT does not waive third-party obligations. Data README's FinancialPhraseBank name/config differs from actual loader (`FinanceMTEB/financial_phrasebank`); implementation wins for provenance.
- Direct manifests differ across reference/experimental/artifact contexts; these are not a single approved dependency stack. No installs, dependency resolution, code execution, model/data downloads or paid calls authorized by this note.

## 8. Five bounded decisions for co-train, tests before implementation

All acceptance criteria below are **proposed future tests**, not completed results. Non-goals: no training launch, version-rule/template shim, G/channel/reward/scorer/prompt/tool membership change, data/model selection, production deployment or benchmark-gain claim.

1. **Adopt selectively: immutable mechanism/trace ledger, not agent autonomy.** Record hypothesis, single changed mechanism, source SHA, scorer/split/runtime hashes, status and trace pointers; distinguish scripted/calibration/native evidence.
   - Acceptance: 10 candidate fixtures × 2 seeds × 2 tasks = exactly 40 terminal rows; 0 missing/duplicate rows; single-byte mutation to each source/scorer/split manifest causes 3/3 identity mismatches; killed/rejected candidates remain visible.
   - Approval: owner approves ledger/schema and write scope. Only already-approved offline fixtures initially. Runtime/model activity separately approved.

2. **Reject weak import validation; adopt static admission plus isolated child execution only after approval.**
   - Acceptance: 6 forbidden edits (reward, scorer, split membership, G, prompt/channel, native-template identity shim) rejected before 1 framework import, 1 output creation or 1 subprocess launch; malformed names/path traversal/duplicate candidate IDs rejected in 3/3 cases. Any future execution sandbox must demonstrate 0 host-secret reads, 0 external network requests and 0 writes outside allowlist across 10 adversarial fixtures.
   - Approval: owner chooses allowed search surface; security specialist reviews isolation, credentials and process-tree cleanup before untrusted execution. A lexical denylist alone never meets criteria.

3. **Adopt irrevocable freeze-before-first-held-out access, reject incomplete-finalization escape.**
   - Acceptance: freeze persisted before first held-out read; crashes injected at 4 finalization boundaries permit 0 subsequent proposer calls; 3 pairwise split intersections each empty by immutable task/database IDs; changing 1 split ID fails admission; resume can only finish identical frozen candidate hashes. No new membership chosen by worker.
   - Approval: scientific owner approves protocol/amendment and held-out access. Existing protected manifests unchanged until explicit approval. Offline state-machine fixtures can be designed without reading held-out payloads.

4. **Reject path-only cache and partial-result ranking.**
   - Acceptance: 8 independent mutations (candidate, model revision, tokenizer/template, scorer, split/database, decoding seed, generation config, runtime identity) yield 8/8 misses. Fixture grid 3 candidates × 2 tasks × 2 seeds = 12 required outcomes; removing any 1 yields no selectable result, not an 11-row higher score. Positive/negative replay accounting reports 1 logical call, 0 provider calls on a cache hit.
   - Approval: owner approves cache schema/retention and completeness semantics; deterministic provider-free fixtures only. Cache hits never certify fresh generation or native training.

5. **Adopt bounded fault semantics and transparent frontier, reject relabeling selection as training.**
   - Acceptance: timeout fixture 2s deadline + 1s grace leaves 0 child processes; missing/corrupt/nonfinite rewards rejected in 3/3 cases; Pareto fixture A=(0.8,100), B=(0.7,100), C=(0.8,120), D=(0.6,50) selects exactly A,D; improvement 0.70→0.75 logged as +0.05 versus pre-update best. 10/10 scripted receipts retain `training_verified=false` and `launch_authorized=false`.
   - Approval: owner chooses whether SQL candidate evaluation has any approved search surface at all. Changes to objective/cost metric require scientific approval. Real optimizer/weight/checkpoint proof remains separate native-runtime work, blocked by current spec.

## Limitations and verification

No git/clones/installs, shell networking, third-party execution, nested agents, dataset/model downloads, paid/model/GPU jobs, or project/reference edits. Agent-reach skill loaded; public GitHub/arXiv reads used FetchUrl. No multi-platform research/update job was needed or run. Only the two requested scratch deliverables were written.

VERIFY_REAL: pinned relevant source and six test/verifier files inspected; local native-training spec read; output files read back and JSON parsed. Runtime/tests/benchmarks/training not executed; no gains claimed.
