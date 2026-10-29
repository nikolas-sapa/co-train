# Harness papers: mechanisms, controls and limits

2026-10-23. Primary-text research, not reproduced results. This is a
parent-written synthesis of two independent reviews of the first four papers,
parent full-text analysis of the next three, and a separate SkyRL source/paper
review. The custom paper reviewers lacked file-writing tools; this document
persists their returned conclusions without claiming they created files.

Version-specific URLs matter. GEPA v1 and v2 have different headline results;
Rethinking v4 adds positive game results. Current repositories are not assumed
to be the paper experiment code. Search-only leads are excluded from the
evidence table.

## Reading map

| Study | Primary text | What it optimizes | Most useful question for co-train |
| --- | --- | --- | --- |
| Meta-Harness | [2603.28052v1](https://arxiv.org/html/2603.28052v1) | Executable harness code, fixed weights | Does full diagnostic history help search, and is selection genuinely held out? |
| Co-Harness | [2607.22688v1](https://arxiv.org/html/2607.22688v1) | Harness repair alternating with success-filtered SFT | Can model and runtime gains be separated? |
| CoTrace | [2610.10426v1](https://arxiv.org/html/2610.10426v1) | Runtime-matched training recipes and coordinate promotion; SFT/DPPO tracks | Is provenance causal, or bundled with coverage/freshness/replay? |
| GEPA | [2507.19457v1](https://arxiv.org/html/2507.19457v1), [v2](https://arxiv.org/html/2507.19457v2) | Reflective prompt evolution, fixed weights | Is comparison matched in feedback, search compute and selection? |
| WHALE | [2609.00196v1](https://arxiv.org/html/2609.00196v1) | Alternating RSFT and executable harness search | Do alternating small updates beat single-component/stagewise schedules? |
| RRSI | [2609.24972v3](https://arxiv.org/html/2609.24972v3) | Regularized harness search, fixed weights | Do small attributable edits transfer with less search-induced complexity? |
| Rethinking Evaluation | [2607.12227v4](https://arxiv.org/html/2607.12227v4) | Compares search/refinement/harness adaptation | Does harness evolution beat direct inference scaling under its protocol? |
| SkyRL-Agent | [2511.16108v1](https://arxiv.org/html/2511.16108v1) | Multi-turn RL infrastructure and agent recipes | Are sampled tokens, objective, masks and restored updates really the same? |

## 1. Meta-Harness

### Mechanism

Weights stay fixed. A proposer reads a filesystem archive of prior harness
source, scores and trajectories, chooses useful parents, writes executable
candidates and receives their evaluation artifacts. The archive exposes more
diagnostic detail than a single scalar score or a short accumulated summary.
Parent choice is proposer-driven, not a single mandatory tournament rule.
[§3, Algorithm 1](https://arxiv.org/html/2603.28052v1#S3)

The raw-trace ablation reports median/best 50.0/56.7 versus 34.9/38.7 for
summaries. This supports the value of the tested diagnostic interface. It does
not isolate information benefit from all extra proposer/diagnostic expenditure.
[§4.1, ablations](https://arxiv.org/html/2603.28052v1#S4.SS1)

### Result denominators

Classification 48.6 versus ACE 40.9 is +7.7 percentage points averaged across
three datasets, not a pooled task denominator. Math 38.8 versus 34.1 averages
the reported model/problem/sample setup, approximately +4.7 points. The
released TB2 artifact reports 76.4% on 89 tasks ×5 trials =445 outcomes.
These are author results, not this project's measurements.
[§4, Tables 2–7](https://arxiv.org/html/2603.28052v1#S4)

### Validity and release correspondence

The coding search and final report reuse the same 89 tasks. Anti-hardcoding
rules and leakage audits do not undo adaptive specialization. Classification
and math describe separate search/test procedures, so this criticism must not
be generalized to every domain.

The abstract's five held-out math models include GPT-OSS-20B, used for search
selection in the methods. Four of the five are unseen during search; held-out
problems and held-out models are different claims. The text also gives 250
math search examples in the main discussion versus 88 in the appendix, an
unresolved reporting discrepancy, not permission to choose a favorable count.
[§4.2](https://arxiv.org/html/2603.28052v1#S4.SS2)

Retrieval decontamination includes prefix/fuzzy matching with Jaccard .8.
That is a meaningful protection, not a semantic or pretraining-contamination
proof. [Appendix C.2](https://arxiv.org/html/2603.28052v1)

The October reference release defaults differ from the paper's classification
protocol, and it contains no math reference implementation. The optimized TB2
artifact is a separate inference scaffold, not the whole search optimizer.
Source-level freeze/cache/completeness findings:
[mechanisms](meta-mechanisms.md), [validity](meta-failures.md).

### Adoption

Retain raw failure evidence, rejected hypotheses and immutable candidate
snapshots. Require complete grids and irreversible freeze before first final
test exposure. Do not infer that trace access necessarily improves our model
or transplant the same-task TB2 protocol into a generalization claim.

## 2. Co-Harness

### Mechanism

Two outer rounds alternate harness optimization with model optimization.
Each harness phase has five failure-attribution/validated-repair iterations.
A HarnessCritic diagnoses trajectories and proposes local updates; high-quality
success trajectories then train weights with SFT. This is not the current
project's GRPO objective.
[Algorithm and §3](https://arxiv.org/html/2607.22688v1)

### Claims and limits

The reported 58.5→78.9, +20.4 percentage points, averages two models ×three
benchmarks. Each benchmark has 30 distinct problems. R0 already includes an
evolved harness; it is not the untouched initial system. Repetition counts,
full SFT membership/hyperparameters and sufficient independent training/search
replication were not located in the inspected methods.
[§4.1–4.2, Figure 5/Table 6](https://arxiv.org/html/2607.22688v1)

Joint system improvement does not establish co-evolution synergy without
fixed-harness SFT, harness-only, compute-matched and crossed-checkpoint
controls. Repeated patch-validation sets are selection data, not automatically
independent confirmation.

The autonomous case changes thinking, batching, sampling, turn cap 15→30 and
eventually six-trajectory majority voting. Ensemble gains are not single-draw
pass@1. Printed 3.78 h→1.11 h is 3.41×, not 8.7×. Another reference timing
could explain the latter claim, but it is not supplied beside it.
[§4.3, Appendix H](https://arxiv.org/html/2607.22688v1)

No authoritative executable paper revision was located in targeted searches.
This does not establish that code is unreleased.

### Adoption

Failure attribution and local validated edits are useful. Keep SFT warm starts,
turn-budget changes and voting in separate approved treatments. Do not use
joint headline gains to reopen H1 or claim a causal weight/harness interaction.

## 3. CoTrace

### Mechanism

The study fingerprints actual runtime components, routes failures and successes
differently, searches candidates and promotes model/harness coordinates
separately. Solved-and-harvested tasks retire from its curriculum. Search uses
5+5 candidate stages; Qwen3.5-9B/4B tracks include SFT and DPPO-based RL.
[Algorithm 1, §2–3](https://arxiv.org/html/2610.10426v1#alg1)

The transferable point is to bind data to the actual runtime that generated
it and report rejected updates. Its curriculum, filtering, objective and
promotion policies are not approved changes here.

### Promotion is not test

SFT 78→88/102 and RL incumbent 78→90/102 are +9.80/+11.76 points on repeatedly
consulted promotion data. Final rejected RL candidate scores 85/102. The paper
explicitly says promotion is not test, reports single chains and notes typical
variation about ±2 tasks with a five-task excursion.
[Table 1, Appendix C](https://arxiv.org/html/2610.10426v1#S3.T1)

The completed factorial is:

| | Old harness | New harness |
| --- | --- | --- |
| Old weights | 78 | 82 |
| New weights | 82 | 86 |

The interaction is `(86−82)−(82−78)=0`. This transition supports additive
contributions, not synergy or necessity of the preceding weight update.
[Table 3](https://arxiv.org/html/2610.10426v1#S4.T3)

### Provenance, transfer and cost

The recipe comparison changes provenance matching alongside freshness, coverage,
prompt conditioning, per-task caps and replay. The paper acknowledges that
causal credit cannot be assigned to each. Large trajectory-count differences
also do not equal disjoint supervised training-pair counts.
[§3.3, Table 2](https://arxiv.org/html/2610.10426v1#S3.T2)

Matched SFT's 47 versus mixed 54 GPU-h/iteration does not mean the whole chain
is cheaper: roughly 235 versus 162 GPU-h across their different iteration
counts, excluding anchors. SFT and RL are explicitly not compute matched.
[Appendix C.4, Table 5](https://arxiv.org/html/2610.10426v1#A3.T5)

SWE-bench Lite has 300 instances and paired tests. SFT under its own runtime
is 105/300, below base 112/300. RL reaches 123/300, but paired comparison with
base is nonsignificant under the co-evolved pairs (p=.16), and under mini-SWE
(p=.52). Changing both runtime and checkpoint does not isolate a weight effect.
[Appendix E.5, Table 12](https://arxiv.org/html/2610.10426v1#A5.SS5)

Reported TB values 18.3±2.5 and 18.7±1.5 are tasks out of 89, not percentages.
Appendix G.1 also develops a recipe on 15 TB2.1 tasks in three pilot runs.
Main-loop exclusion therefore does not make the entire research program's
benchmark pristine. Main-checkpoint training leakage is not established;
pilot membership/separation needs clarification. Only two pilot rows share
400 trajectories; the undifferentiated mix has 107.
[Appendix G, Table 16](https://arxiv.org/html/2610.10426v1#A7.T16)

### Adoption

Use actual runtime fingerprints and coordinate-specific comparisons. Hold
coverage, freshness, caps and replay constant before claiming provenance is
causal. Preserve our six cells and unchanged corpus; no curriculum or DPPO
switch follows from this paper.

## 4. GEPA, with version drift

### Mechanism

GEPA freezes model weights and evolves compound-system prompts. Small
minibatches expose raw traces for reflection; a per-instance Pareto frontier
helps select parents. Ancestry/source/score history persists, and optional
system-aware merge combines complementary candidates. This is richer feedback
than scalar reward alone.
[v2 §3](https://arxiv.org/html/2507.19457v2#S3)

Distinct train/validation/test roles and IFBench's unseen constraint families
are strengths. AIME's 30 questions repeated five times remain 30 unique task
clusters, not 150 independent problems.
[v2 Appendix E.1](https://arxiv.org/html/2507.19457v2#A5.SS1)

### Headline corrections

V1 reports four tasks and about +10 points over GRPO. V2 reports six tasks:
54.85 versus 48.91, +5.94 points, with plain GEPA beating GRPO on five of six;
AIME is 32 versus 38. These aggregate benchmark-specific metrics, not one
pooled accuracy denominator.
[v1 Table 1](https://arxiv.org/html/2507.19457v1#S5.T1),
[v2 Table 1](https://arxiv.org/html/2507.19457v2#S4.T1)

“35× fewer rollouts” compares IFBench GRPO 24,000 against the first best
GEPA prefix at 678. Total GEPA search there is 3,593 optimization rollouts.
Reflection is extra, with 17 calls listed for Qwen IFBench. The headline is
not a complete compute, dollar or full-search ratio. The paper separately
reports costs for other model/optimizer experiments; do not apply those
prices to our model.
[v2 Appendix E.3–E.4, N](https://arxiv.org/html/2507.19457v2)

Textual reflection versus scalar reward changes available information as well
as search space. V1 limits its LoRA comparison; v2 adds full-parameter
experiments, not every compound-system cell. Today's README teacher examples
are not proof that the original experiment used a stronger teacher.

Current library version, old pinned GEPA source and the distinct reproduction
artifact are not interchangeable. Artifact dependencies include modified
DSPy/Arbor forks; exact paper-to-current-release equivalence was not verified.
The original four-paper reviewers did not establish independent optimization
seed counts/significance for every main comparison.

### Adoption

Retain raw trace reflection, explicit validation and rejected proposals.
Track all inference work, including reflection and judge calls. Reflection may
use training evidence only; no final-evaluation traces or gold may enter it.

## 5. WHALE

### Mechanism and relation to our question

WHALE alternates online verifier-success-only rejection-sampling fine-tuning
(RSFT) and Meta-Harness code search. RSFT applies supervised likelihood to
model-generated positions, excluding prompts/tool results, with token-normalized
accepted trajectories and one SFT epoch before worker synchronization.
It is not GRPO.
[§3–4](https://arxiv.org/html/2609.00196v1#S3)

Search sees prior source, scores and trajectories. It can change prompts,
tool formatting, feedback, termination and turn allocations while verifier,
reference answers and environment transitions stay fixed. That is broader
than our frozen treatment and requires approval before adoption.

### Data and metric

SearchQA/Math use Qwen3.5-2B; Chess uses 4B. Training samples G8; candidate
evaluation uses one rollout per example; tests average eight trajectories
per example as mean@8, **not pass@8**. Harness sets have 256 examples. Tests
contain 700 SearchQA questions, AIME24/25's 60 problems and 256 chess puzzles.
Chess weight/search/test sets are mutually disjoint; Math's 256 harness
examples come from its DAPO weight-training corpus. Do not call every pair
of update datasets disjoint.
[§5.1–5.2, Appendix B](https://arxiv.org/html/2609.00196v1#S5)

The proposer is Claude Opus 4.7; three candidates ×256 examples cost 768 agent
rollouts per iteration. Rollout budgets exclude proposer compute and are not
all-in training/inference costs.
[§6.1, Appendix B.1](https://arxiv.org/html/2609.00196v1#S6)

### Selection caveat and schedule evidence

Algorithm 1 line 17 and adaptive Algorithm 2 line 24 return the pair with best
accuracy on `D_test`; Figure 2
is best-so-far test accuracy, and Appendix C reports best-test points. Phase
switches driven solely by training signals do not make that final selection
an untouched-test estimate. This is a reporting/selection caveat, not evidence
that gradient updates used test examples.
[Algorithm 1](https://arxiv.org/html/2609.00196v1#alg1),
[Figure 2](https://arxiv.org/html/2609.00196v1#S5.F2),
[Appendix C.2](https://arxiv.org/html/2609.00196v1#A3.T3)

Selected author-reported best-test points:

| Method | SearchQA mean@8 | Rollouts to point | Math mean@8 | Rollouts to point |
| --- | --- | --- | --- | --- |
| Weight-only | 38.27 | 530,432 | 15.42 | 645,120 |
| Harness-only | 38.29 | 30,720 | .42 | 46,080 |
| Stagewise | 43.02 | 604,160 | 15.63 | 893,952 |
| Fixed (.2 epoch,6 iterations) | 50.09 | 589,824 | 28.33 | 599,040 |
| Fixed (.6,6) | 48.34 | 382,464 | 24.79 | 720,384 |
| Adaptive | 52.82 | 295,424 | 26.46 | 689,152 |

Source: [Table 3](https://arxiv.org/html/2609.00196v1#A3.T3).
These are different stopping points, not a universal compute-equivalent
endpoint. Adaptive wins SearchQA but not the best fixed Math schedule.

The prompt-only FST control is reinstantiated using WHALE's RSFT and MH,
restricted to prompts; it is not a reproduction of original FST's RL engine.
The abstract's 4.15–24.38-point range spans different comparators. Strongest
single-component gains and FST gains must not be collapsed into one guarantee.
[§5.2, Appendix B.1](https://arxiv.org/html/2609.00196v1#A2.SS1)

The additional independent validity review found no optimization-run
replication or confidence intervals in the inspected text. It also flagged
a budget-accounting ambiguity: Table 1's six/nine/six cycles at (.6,6) imply
3.6/5.4/3.6 weight epochs and 36/54/36 search iterations, while Appendix B.1
describes cumulative matching to 4/6/4 epochs and 40/60/40 iterations.
Rounding or extra evaluations may explain this; exact equality was not
established. Do not call this demonstrated unfairness.

### Adoption

Treat generic alternating weight/harness optimization as established prior
art. Its useful future hypothesis is that the bottleneck changes after a
weight update. Test that with crossed artifacts and budget controls, rather
than importing its G8, SFT, schedule or best-test selection.

## 6. RRSI

### Mechanism

RRSI regularizes the search trajectory while keeping harness components
editable. An annealed edit budget shrinks roughly 3–4 atomic changes to one.
History includes failed proposals. Stalls reserve exploration for untouched
components. A critic checks candidate diffs for benchmark specificity;
selection enforces an empirical noise-adjusted score floor and gain/cost
trade-offs; pruning removes persistently unproductive structure.
[§3, Appendix D](https://arxiv.org/html/2609.24972v3#S3)

The L0/L1/L2 language is explicitly analogy, not optimized norm penalties or
a generalization theorem. The measured baseline noise band is not a
familywise/type-I guarantee under adaptive search. Within the band, novelty
and cost can make a candidate admissible; “every accepted edit improves
score significantly” would be false.
[Appendix D.3](https://arxiv.org/html/2609.24972v3#A4.SS3)

### Generalization, cost and replication

Evolve sets are TB2.1's 89 tasks, Harvey120 and EngDesign61. Harvey has an
additional 40-task ID holdout; the others have no separate ID task holdout.
OOD evaluation spans SWE-bench Verified, JobBench, GDPval, APEX and Frontier.
Reported metrics include task success, rubric criteria and medals; they are
not interchangeable accuracies.
[§4, Appendix E](https://arxiv.org/html/2609.24972v3#S4)

Table 1's Harvey RRSI row gives 89.2 on ID holdout and OOD 40.7/52.3/37.9
versus base 86.9 and 36.0/48.8/34.2. JobBench's +4.7 exceeds the abstract's
“up to 4.3” OOD phrasing. Use the table's exact context, not the headline range.
Its Harvey ID result ties Meta-Harness at 89.2, so superiority over every
optimizer on every holdout is too strong. Table 6's bootstrap intervals test
gains against base, not superiority over every competing optimizer.

Table 2 gives RRSI 2.42M policy tokens/trial versus unregularized 3.80M, about
36.3% fewer. Base is1.56M: RRSI is about 55% more expensive than base, not
cheaper. This is policy-token cost, excluding complete proposer/critic/judge
and hardware accounting.
[Table 1–2](https://arxiv.org/html/2609.24972v3#S4)

Appendix E.2 separates uncertainty sources: paired task-level bootstrap with
10,000 resamples and 95% intervals, plus two independent search runs. Task
clustering is preserved; repeated task trials are not independent samples.
The author reports positive held-out intervals and similar gains in the
second run. This is stronger evidence than a single selected frontier,
but no result was reproduced here.
[Appendix E.2, Tables 6–7](https://arxiv.org/html/2609.24972v3#A5.SS2)

Cross-model transfer of one frozen searched harness onto Gemini3.1Lite
11.2→14.6 uses the same TB tasks. It tests unseen-model transfer, not unseen
task generalization. Independently evolved per-policy rows answer a different
question.
[Tables 3–4](https://arxiv.org/html/2609.24972v3#S4)

Cost parameters are described as fixed before runs/no holdout tuning, while
Appendix E.1 calibrates against opening-round candidates. This is not evidence
of held-out tuning, but prospective fixed rules and adaptive calibration need
to be distinguished. Critics can miss generic rubric fitting without explicit
task names; Appendix F gives examples of that failure. D.3 says the within-band
weights are reported in Table 5, but their numerical values are absent there;
the domain-specific guard also lacks a concrete specification in that table.

### Adoption

Single-mechanism edits, explicit negative history and cost-aware independent
confirmation are the useful ideas. Do not copy the empirical noise band as a
signed significance threshold, cost constants or a security guarantee.

## 7. Rethinking the Evaluation of Harness Evolution

### Controlled question

This study compares parallel sampling, sequential refinement, harness evolution
and harness scaling. Its TB implementation uses an AHE instantiation with the
exploration agent disabled and shared underlying models/summarization. It
does not disprove every Meta-Harness/RRSI variant or weight training.
[§3, Appendix A.1](https://arxiv.org/html/2607.12227v4#S3)

TB2.1 repairs 28 of 89 TB2.0 tasks. Three frontier models, K=5 rollouts and two
independent runs are used. Matching rollout count is not a complete all-in
compute match; Appendix A cost explicitly excludes harness-editing cost.
[§4.1, Appendix A](https://arxiv.org/html/2607.12227v4#S4)

### Terminal counterevidence

Without unit tests, average scores are base 68.2, parallel 72.3, harness
evolution 67.4, harness scaling 71.8. With unit tests, oracle-selected parallel
pass@1 is 82.0 versus evolution 69.7; sequential pass@5 is 87.1 versus 79.0.
The oracle selector is not a deployable SQL selector with access to private
gold. These results concern their explicit feedback conditions.
[Tables 1–2](https://arxiv.org/html/2607.12227v4#S4)

The paper's test-oracle-selected “pass@1” is not mean individual-rollout
accuracy; the appendix's metric definition makes that labeling ambiguous.
At K=10 with tests, Opus harness scaling is 90.5/94.4 for pass@1/pass@10,
versus sequential 89.6/93.1. The authors call the difference within run
variance. Even this terminal study does not establish that adaptation
never beats direct scaling.
[Appendix A.3, Table 8](https://arxiv.org/html/2607.12227v4#A1.T8)

With 45 train/10 validation/34 held-out test tasks, base and evolved macro
averages are both 63.2. Per-model changes are +1.2/0/−1.4. This is limited
generalization in that protocol, not a universal negative theorem.
[Table 3](https://arxiv.org/html/2607.12227v4#S4.T3)

### Positive games evidence, a different estimand

The v4 game experiments intentionally optimize each task using granular
feedback, not one reusable harness that transfers to unseen games.
ARC-AGI-3 uses 25 public games and a 2,000 `play`-action cap. RHAE measures
completion and human-relative action efficiency. Full harness versus
memory-disabled VISTA is 43.3→77.5 and 21.1→38.2: +79.0%/+81.0%
**relative**, not +80 percentage points.
[§5.1–5.2, Table 4, Appendix B](https://arxiv.org/html/2607.12227v4#S5.T4)

EdgeBench uses five game tasks, two runs and a12-hour wall-clock window,
reporting highest score over the run. Means 48.3→54.7 and 45.9→49.8 are
relative gains 13.3%/8.5%, or +6.4/+3.9 score points. The roughly 11%
headline is not 11 percentage points or cross-task held-out improvement.
Host-side hidden-judge snapshots also contribute to the best-so-far metric
without showing those snapshots to the agent.
[Table 5, Appendix C.1](https://arxiv.org/html/2607.12227v4#S5.T5)

The 2,000-action and 12-hour constraints do not establish equal total
inference tokens, proposer calls or dollar costs. EdgeBench's wall clock does
include summarization and edit downtime; ARC's action cap does not meter all
internal reasoning/read-only inspection. ARC's replication count is
unspecified in the inspected appendix. Positive and negative
results fit together: task-specific adaptation with rich feedback can help
even when transferred terminal-harness edits do not.

### Adoption

Require direct-sampling/refinement baselines and feedback disclosure for any
future search claim. Separate test-time adaptation from reusable harness
generalization. New baselines or treatment budgets require approval.

## 8. SkyRL-Agent

The official paper is 2511.16108v1, submitted 2025-11-20, not the 2026
Responses API implementation. The SWE recipe uses Qwen3-32B and 4.5K
R2E-Gym tasks, G8, leave-one-out advantages, no standard-deviation or
length normalization, no KL/entropy, and a modified thinking-preserving
template. External-constraint terminations are loss-masked without changing
their rewards/advantages.
[Paper](https://arxiv.org/html/2511.16108v1)

SA-SWE reports 24.4→39.4 SWE-bench Verified pass@1 under simple ReAct.
The table's 4601 versus 9180 H100-hours is about 1.995×, not independently
audited “more than 2×.” DeepSWE's simple-ReAct 36.4 and own-setup 42.2 are
different scaffold columns. Reported dispatcher speedup 1.55× is a specific
author hardware/workload comparison, not an expected local benefit.

The current source contains older agent adapters, current Gym training and
new SkyCap capture paths. Their APIs and probability fidelity differ. No
paper-era execution pin was established by this study. See
[full mechanism/era/test audit](skyrl-mechanisms.md) and
[restore/failure audit](skyrl-failures.md).

## Cross-paper conclusions

Generic harness/weight co-evolution already has close prior art. Our defensible
question is the constrained, crossed small-model training comparison, with
honest token/probability evidence, unchanged scoring and full compute.

The papers repeatedly separate into different questions:

- Frozen-weight search versus actual weight training.
- Promotion-set improvement versus independent confirmation.
- Within-task adaptation versus reusable cross-task generalization.
- Same rollout counts versus equal total computation.
- Model transfer versus task transfer.
- Additive crossed gains versus interaction/synergy.

Do not average their headline percentages or import a more convenient
algorithm, G, cap, scorer, template or selection rule into our primary
experiment.

### Future falsifiers, not an execution plan

1. Remove the optimizer step: a real-learning check must fail despite finite
   logged loss/reward.
2. Flip one observation loss-mask bit or shift sampled logprobs one position:
   training admission must fail.
3. Delete one required group member or result-grid cell: no complete-group or
   promotion certificate may be emitted.
4. Fail final evaluation after one successful result: search must remain frozen.
5. Compare a selected harness with matched-budget direct sampling/refinement;
   count proposer/critic/judge/retry work and disclose available feedback.
6. Cross old/new weights with old/new harnesses before claiming synergy.
7. Hold coverage/freshness/replay constant before attributing provenance.
8. Lock selected artifacts before independent confirmation; reruns of exposed
   tasks measure reproducibility, not pristine-task generalization.

Reviewer-suggested new sample counts, seeds, significance gates, cost margins
and restore tolerances are not adopted. Existing frozen policy remains in
force. See the [ranked roadmap](../2026-10-23-harness-round2.md).

## Method and limits

Both original paper reviewers read indexed primary methods/results and
selected appendices, with v1/v2 differences tracked. Parent cached all seven
core full-text HTML versions, then GEPA v2, and directly read new-paper
methods, evaluation and appendix sections. The SkyRL reviewer fetched its
official paper. Full-text cache hashes are in `source-audit.json`; transformed
Markdown is not a PDF-byte archive.

No paper result, statistical interval, hardware saving, source test or learning
claim was independently reproduced. No complete artifact license/dependency
audit was performed. Full source execution, PDF visual checking, author-data
reanalysis and CI-history verification were outside this task.

VERIFY_REAL: primary-text and pinned-source research only. All experimental
criteria above are proposals; no model/GPU/training/restore jobs ran.
