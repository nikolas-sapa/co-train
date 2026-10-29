# Harness research, round 2: what co-train should improve next

2026-10-23. Research baseline: `ea6d2f6`. Research and proposed work only.
No training, dependency change, scientific amendment or launch authorization.

## Recommendation

Prove the existing learner before adding a search platform. The next substantive
milestone is a genuinely sampled SQL tool trajectory, followed by a finite,
non-skipped native optimizer update, changed adapter weights and a fresh-process
checkpoint restoration. More constructor tests or scripted receipts cannot
substitute for that evidence.

The most useful immediately available engineering work is smaller: stop
timed-out SQL sweeps instead of leaving daemon computation running, then make
offline tokenizer requirements explicit. In parallel, the owner must resolve
the frozen/native runtime contradiction and the unsupported exact template
identity before any native execution can be proposed.

The literature strengthens this ordering. WHALE is close prior art for
alternating weight/harness optimization, but uses success-only SFT rather than
GRPO and reports best-on-test checkpoints. RRSI supports small attributable
edits, negative-result history and cost-aware search. Rethinking Evaluation
shows that simple test-time sampling can beat harness evolution in its terminal
setup, while finding benefits for task-specific long-horizon games. None
establishes our small-model, frozen-interface, PTC-trained versus bash-trained
comparison. [Papers](2026-10-23-harness-round2/papers.md)

Keep the six cells: base/PTC-trained/bash-trained, each evaluated under both
harnesses. Count full compute and retain rejected, failed and incomplete
attempts. Do not select checkpoints or harnesses using final evaluation.
H1 remains closed; BIRD remains H3/H4/H5 evidence, not N1.

## Scope and evidence

This round used two independent source reviews per repository: one traced the
working mechanism, the other challenged admission, selection, cleanup and
restoration. Two paper reviewers covered the original four studies; parent
full-text analysis and an additional validity pass covered the three new
studies. SkyRL's paper was reviewed separately from current source.

| Repository | Exact revision | License | Paired dossiers |
| --- | --- | --- | --- |
| Meta-Harness | `8123ccabe2b19fa1123090b2e5f1bacc20963ce8` | MIT | [Mechanisms](2026-10-23-harness-round2/meta-mechanisms.md), [failure/validity paths](2026-10-23-harness-round2/meta-failures.md) |
| rLLM | `4e828c81680e5a85b638ceedeaf09d1e90109ca8` | Apache-2.0 | [Mechanisms](2026-10-23-harness-round2/rllm-mechanisms.md), [trace admission](2026-10-23-harness-round2/rllm-failures.md) |
| SkyRL | `3a6e3b4e0ea08dc9b0e134fbd58eb135a6f3681d` | Apache-2.0 | [Mechanisms](2026-10-23-harness-round2/skyrl-mechanisms.md), [failure/restore paths](2026-10-23-harness-round2/skyrl-failures.md) |

Each dossier has an adjacent `*-sources.json` with pinned URLs, symbols and
coverage limits. This extends the [earlier source review](2026-10-23-harness-deep-analysis.md),
which covered Harbor, OpenEnv, Agent Lightning and Reasoning Gym and built on
Prime/Verifiers, Pi, T3, ART, OpenHands and mini-SWE-agent work. Earlier pins and
claims were not all re-audited in this round.

Evidence levels used throughout:

1. **Author result:** reported in a paper, not reproduced here.
2. **Source deduction:** a concrete reachable path or counterexample in pinned
   source, conditional on the inputs/configuration described.
3. **Test-body evidence:** an actual assertion was inspected. It did not pass
   merely because its source exists.
4. **Local verification:** report existence, JSON parsing, hashes and repository
   state checked here. This is not framework execution.
5. **Proposal:** a future test, design or experiment. No proposed numeric
   criterion is an approved scientific threshold.

No upstream test suite, model generation, optimizer update, checkpoint restore,
GPU job or paid training/inference API was executed. Source reachability to
`backward()` is not proof of learning. No third-party code was copied into
production or executed. Full paper text and inert source caches remain in
scratch, not vendored here.

## 1. Meta-Harness: borrow the search evidence, strengthen the boundary

The mechanism is useful: freeze weights, let a proposer inspect prior source,
scores and selected trajectories, propose executable changes, evaluate, and
retain a frontier/history. This makes diagnosis richer than a scalar-only
search. It does not train weights.

The release contains distinct classification, TB2 and experimental Harbor
controllers. They are not one identical implementation of every paper result.
Classification defaults to offline application-memory learning; the paper's
main classification protocol differs. The optimized TB2 artifact is another
repository. [Mechanism trace](2026-10-23-harness-round2/meta-mechanisms.md)

Both reviewers found the same consequential weaknesses:

- Classification finalization blocks evolution only after `status="complete"`.
  Its test explicitly permits evolution after incomplete finalization. Partial
  test exposure can therefore precede further selection.
- Complete seeds within an observed dataset are required, but complete dataset
  coverage is not. A candidate evaluated only on an easy subset can enter the
  aggregate frontier. TB2 likewise counts failed existing directories as zero
  but does not reject entirely absent task/trial directories.
- Names and mutable source paths identify many cached results. Numeric accuracy
  is not evidence that source, scorer, model revision and dataset bytes match.
- TB2's optional five-trial final run uses the same 89 search tasks. More trials
  reduce rollout noise; they do not remove adaptive task selection.
- Ordinary imports and proposer Read/Write/Bash permissions are cooperative
  research conventions, not isolation from labels or the scorer.

These are source-supported protocol risks, not observed benchmark fraud or
runtime incidents. [Failure review, F1–F9](2026-10-23-harness-round2/meta-failures.md)

For a future approved search, copy the idea of mechanism-labeled proposals and
trace-backed rejection history. Freeze before the **first** final-test request,
including when that request fails. Require the complete expected result grid
and content-bound identities. Do not copy arbitrary candidate execution beside
our scorer, a substring denylist as security, or best-history scores as final
artifact certification.

The separate optimized artifact is pinned at
`57fefdb2ff84af3fd81b69d67814acbe69bd0743`. Its inspected complete tree lacks a
LICENSE file. Main-repository MIT does not automatically clear copying that
artifact. This round did not fully audit its agent implementation.

## 2. rLLM: trace capture is not training admission

The source chain really reaches grouped advantages, backend loss/backward,
optimizer APIs, sampler refresh and checkpoint APIs. The same agent-flow
interface is used for training and evaluation. Neither observation establishes
numerical parity across backends or execution of a real update here.
[Mechanism trace](2026-10-23-harness-round2/rllm-mechanisms.md)

The failure review supplies specific witnesses:

- Two concurrent calls in one session finish in reverse order. Positional trace
  enrichment can attach A's reward/action to B's tokens.
- Retry cleanup failure is logged while the session identity is reused.
  Old-attempt traces can contaminate a later successful attempt.
- A nonempty partial stream can be persisted without a terminal finish reason.
  Nonempty token IDs alone do not establish a usable rollout.
- Cumulative streaming converts upstream `text` to client `delta.content`, but
  capture reads the original chunks as chat deltas, losing captured answer text.
  Fragmented tool calls are appended instead of rebuilt by index.
- A malformed trajectory can be dropped after its group's advantages were
  computed, leaving survivor-only training with the old group normalization.

These are static, configuration-dependent counterexamples, not executed rLLM
reproductions. Pending-write flushing and useful prefix/shifted-mask safeguards
also exist. The paired reviews agree on both protections and limits.
[Admission review, F1–F11](2026-10-23-harness-round2/rllm-failures.md)

Our transferable requirement is explicit task/group/rollout/attempt/call
identity plus terminal disposition. For scientific admission, requested G,
scored G and actually trained G must agree under the frozen policy. A retry,
redraw, mask, survivor drop or failure-as-zero policy is an experimental choice,
not a harmless infrastructure repair.

Do not install the gateway as a shortcut. Its current dependency declarations,
model-provider interfaces and hosted training backends are not our approved
stack. The original rLLM citation in its README is a Notion blog, not a
peer-reviewed framework paper or a paper-era pin for today's source.

## 3. SkyRL: preserve sampled identity through context changes and restore

SkyRL makes several useful distinctions explicit: generated tokens versus
external observations; attention, response and loss masks; sampler likelihood
versus old/current policy likelihood; rollout identity versus segmented loss
rows. Current SkyCap's default path rule targets a sampled model node exactly
once even when several context paths share it.
[Mechanism trace](2026-10-23-harness-round2/skyrl-mechanisms.md)

These protections are mode-specific. The failure review found that an ordinary
postprocessed action can replace sampled token IDs while retaining the
original logprobs. Equal sequence lengths cannot detect this substitution.
Environment closure occurs only on the normal generator path; the finalizer
finishes the inference session but need not close the environment on error.

Checkpoint APIs save meaningful optimizer/scheduler/RNG state, and a GPU test
body genuinely compares resumed versus uninterrupted next-update logits.
However, other paths can publish `latest` before all required state is complete,
and FSDP restoration can tolerate empty optimizer or missing RNG state.
“Save returned,” “weights restored,” and “exact continuation” remain distinct
claims. The strong test body was inspected, not run.
[Failure review, F1–F6](2026-10-23-harness-round2/skyrl-failures.md)

Current retry protections deserve credit: Harbor attempts use fresh capture
graphs, and certain failures mask an entire prompt instance rather than quietly
shrinking it to G−1. This is still not permission to adopt that policy here.
Async capacity-based staleness is explicitly not a hard per-trajectory policy
bound. HTTP 200 can carry a Responses `failed`/`incomplete` event.

Current SkyCap is not paper-era SkyRL-Agent. The paper's SWE recipe uses RLOO
without standard-deviation normalization, not our normalized GRPO. Its modified
template and external-constraint loss policy are separate treatments. Root
Apache-2.0 does not resolve model/data rights or compute costs.

## 4. “GRPO” and “same agent” do not guarantee the same experiment

| Dimension | Concrete difference found | Implication |
| --- | --- | --- |
| Group scale | rLLM's helper uses population standard deviation; SkyRL's inspected helper uses default sample standard deviation | The same rewards/G can produce different gradients |
| Likelihood denominator | rLLM Tinker uses sampler logprobs; normal verl and SkyRL PPO routes recompute old-policy scores | Record sampler, old, current and reference separately |
| Sampling support | SkyRL can record processed probabilities and optionally replay support | Same weights do not imply identical raw/processed probabilities |
| Objective reduction | Token-sum, token-mean, per-row mean and prompt-mean paths differ | Length/segmentation changes can reweight learning |
| Failed members | Retry, drop, zero, mask and whole-group refusal differ | Expected G is not trained G |
| Context forks | A rollout may emit several loss rows | Row count is not independent sample count |
| Evaluation reuse | Shared agent code can still use different sampling, models or budgets | Code reuse is not harness parity |

Sources: both [rLLM](2026-10-23-harness-round2/rllm-mechanisms.md) and
[SkyRL](2026-10-23-harness-round2/skyrl-mechanisms.md) mechanism dossiers.
Do not “fix” our objective by importing another framework's defaults. Diagnose
the actual native implementation against the approved contract.

## 5. Prioritized work, tests before implementation

Rank reflects leverage. Execution order depends on the approval lane.
No implementation below was performed by this research.

| Priority | Proposed acceptance test | Scope and dependencies |
| --- | --- | --- |
| P0, owner decision | `test_exact_native_contract`: zero unresolved frozen/native conflicts; actual helper accepts exact approved template bytes without an identity shim; prefix corruption and one-token context undersize both refuse | Approve runtime/template contract first. Full resolver, CUDA ABI and exact model revision remain separate requirements |
| P1, best offline slice | `test_sweep_deadline_stops_owned_work`: .10 s fixture deadline; zero executing owned workers/descendants or late side-effect marker within 1 s; independent supervisor <3 s; 17/29 task binding preserved | Narrow owned-subprocess change around `bench/sql_parity_sweep.py`; preserve production timeout, row and comparison semantics |
| P2, offline bootstrap | `test_declared_offline_tokenizer`: empty isolated caches plus network denial produce zero network attempts; pure suite stays tokenizer-free; declared integration uses exact local bytes or reports missing artifact | Preserve both contamination tokenization assertions. An explicit skip/missing artifact is not an integration pass |
| P3, first runtime milestone | `test_sampled_native_boundary`: actual sampled tool call, real observation and sampled continuation; zero token/logprob/mask alignment errors; zero external tokens trained; shift and mask-bit corruptions each refuse | Exact runtime/model/template/channel/corpus/launch approval and real preflight required. No scripted tool call or forced final answer |
| P4, learning smoke | `test_native_update_and_restore`: exactly 1 real non-skipped optimizer step; finite loss/gradients, ≥1 nonzero trainable gradient and changed LoRA tensor; frozen base unchanged; fresh-process trained-weight restoration | Preserve G4 and effective batch `(8,2)`, not a smaller surrogate. Need genuinely informative sampled groups. Restore tolerance must be approved before running |
| P5, scientific readiness | `test_frontier_provenance_and_group_admission`: exact frozen revision/channel/corpus/G/sampling/scorer/splits; 100% outcomes disclosed; zero reused confirmation samples or undeclared evaluation overlaps | Resolve invalid-gold policy and measurement/amendment authority. Do not activate unsigned retention logic |
| P6, scientific comparison | `test_registered_six_cells`: exactly six artifact-bound cells, paired held-out tasks, uncertainty and complete costs; zero final-evaluation-driven promotions | Build the missing bash-trained comparator only under a separate approved spec. Learning smoke is not RUN PASS |
| P7, later optimization | `test_single_mechanism_candidate`: one attributable edit, complete expected result grid, immutable candidate/evaluator identities; no post-test evolution; cost/failure history retained | Only after the learner and comparison work. Search treatment and budget need explicit approval |

The .10 s/1 s/3 s bounds are proposed local lifecycle test targets, not measured
new capabilities. Existing watchdog tests already use real process fixtures,
but they do not cancel the sweep's daemon thread.

For P4, the reviewers proposed inconsistent illustrative logit tolerances
(`1e-5` and `1e-3`). **Neither is adopted.** Predeclare dtype/device-specific
tolerances and deterministic/nondeterministic expectations in the approved
runtime test plan. Exact equality of restored saved tensors is a different
check. Resumable training additionally requires optimizer/scheduler/scaler/RNG,
data position and global step, then a resumed second update.

One optimizer step is an engineering smoke. It cannot satisfy the existing
minimum five-step probe or sustained-run verdict. `build_sql_trainer` calls
real frontier preflight even for one requested step. Missing manifest blocks
this constructor today; no private test seam or synthetic manifest may bypass
that dependency. A narrower engineering-only launch would require its own
explicit owner authorization.

Detailed file/symbol mapping and rationale:
[local gap analysis](2026-10-23-harness-round2/project-gaps.md).

## 6. What the scientific design should distinguish

The frozen six-cell design separates training-arm gains from runtime
assistance. Compare each trained checkpoint with base under the **same**
evaluation harness. Report transfer across harnesses and the interaction:

`(PTCtrained_PTC − bashtrained_PTC) − (PTCtrained_bash − bashtrained_bash)`.

Do not attribute joint-system gains to weight/harness synergy without crossed
cells. CoTrace's displayed transition `78/82; 82/86` has interaction zero.
This is useful additive improvement, not evidence that the prior weight update
was necessary for the harness gain. [Paper audit](2026-10-23-harness-round2/papers.md)

Recipe-matched training is not necessarily compute-matched training. Record
sampling/prefill, generated tokens, automatic harness actions, scorer work,
proposer/critic/judge calls, retries, screening, updates, synchronization,
checkpointing and final evaluation. Separate logical requests, fresh calls,
cache replay and unknown costs. Missing cost is not zero.

Direct sampling/refinement controls are valuable counterevidence, but adding
them changes the experimental plan. They need separate approval and cannot
use private gold as a deployment-time selector. Likewise RSFT warm starts,
curriculum, adaptive task choice, richer tools, compaction and new procedural
tasks are distinct treatments, not repairs silently folded into the main arm.

The prior 59-task floor does not ensure power for every six-cell interaction
or clustered/training-seed comparison. Preserve the existing task-paired
analysis and void policy. Additional seeds, multiplicity/power changes,
evaluation membership and compute-equivalence margins require approval.
If evaluation already informed selection, rerunning it establishes
reproducibility, not untouched-task generalization.

## 7. Cost, licensing and approval boundaries

This research used public source/paper reads and local metadata/file checks.
No paid inference/training, GPU or sandbox jobs were launched. Research-tool
billing was not inspected.

Do not import a new training backend to evade the runtime block. rLLM and
SkyRL declare different Transformers/Torch/vLLM stacks and training
objectives. Their current source is not a compatibility certificate for
frozen Unsloth/TRL. Tinker/Fireworks APIs cost money; self-hosted code still
needs hardware, sandboxing, storage and operational ownership. Published
H100-hours or rollout counts are not an all-in quote for our model.

Main Meta-Harness MIT and rLLM/SkyRL Apache-2.0 permit source reuse subject to
their terms; model, dataset, image and dependency licenses remain separate.
No source adoption occurred. The separate Meta-Harness artifact needs license
clarification before copying.

Owner decisions still required: runtime/version contract, exact supported
template/model revision, channel/G/corpus/sampling/evaluation membership,
invalid-gold handling, measurement/manifest authority, experimental treatments,
installs/downloads, resource/spend ceilings and actual launch. Existing guards,
thresholds/windows, signatures and main fail-closed entrypoint stay unchanged.

## Limitations and reproducibility record

The paired reviews cover selected critical implementation and test bodies,
not every file or configuration. Conditional source witnesses are not observed
incidents. Paper figures/HTML and selected appendices were read; no PDF visual
audit, benchmark reproduction or independent numerical training replication
was performed. Current HEAD, old paper recipe and released artifact are
explicitly separated.

[Source audit](2026-10-23-harness-round2/source-audit.json) records six dossier
and manifest digests, cached paper hashes and cache integrity checks.
It indexes 251 source entries **with overlap**, not 251 uniquely reviewed
implementations. All 218 listed cache paths existed. Of 211 cache entries
carrying Git blob IDs, 206 matched and 5 differed. The differences are listed
in the audit, not treated as executable authenticated source. Cached Markdown
may differ from raw repository bytes.

The accompanying verification record is authoritative for final totals and
document checks. No cached upstream source was executed.

VERIFY_REAL: research artifacts and local provenance checked; upstream tests,
native generation, gradients, changed weights and restoration not executed.
Historical `1861 passed, 1 optional Torch skip` belongs to the preceding
implementation receipt, not this research run.
