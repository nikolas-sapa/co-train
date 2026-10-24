# Prime and T3: opportunities for co-train

2026-10-24. Static-source synthesis and proposed experiments. No new benchmark,
training run, paid inference, or measured improvement.

## Source pins and scope

* [Prime Agent, `5c898d1b27b109bd2d383c68d60a30536e39cc22`](https://github.com/PrimeIntellect-ai/prime-agent/tree/5c898d1b27b109bd2d383c68d60a30536e39cc22)
* [T3 Code, `d53873b6a4799e87afd63c8d288ef0089f5a3748`](https://github.com/pingdotgg/t3code/tree/d53873b6a4799e87afd63c8d288ef0089f5a3748)

This note condenses the supplied source review, including independent corrections
to its refinement claims. Links identify reviewed snapshots, not current remote
heads. Static reachability, intended test contracts, author-reported results, and
executed experiments are different evidence classes. No upstream builds or
runtime reproductions were performed for this note.

## What Prime changes

Prime retains prompt additions, memories, skill references, subagent guidance,
and factory records. Successful compaction can trigger model review, subject to
enablement, scope, cooldown, and concurrency controls. Explicit requests reach
the same proposal/application path. The refiner proposes JSON edits from selected
experience and existing state; admission checks settings, scope, existence,
conflicts, consent, and structure before persistence.

The [application path](https://github.com/PrimeIntellect-ai/prime-agent/blob/5c898d1b27b109bd2d383c68d60a30536e39cc22/crates/pa-core/src/session_engine/refine.rs#L302-L467)
does not establish prospective held-out benefit. Generated rationale and expected
outcome are assertions. Accepted edits can change future fixed-weight inference
without improving it. Direct trusted Python CRUD can also write active state
without that model review. Production Prime's traced adaptation path does not
demonstrate an optimizer update or online model-weight learning.

The [automatic trigger](https://github.com/PrimeIntellect-ai/prime-agent/blob/5c898d1b27b109bd2d383c68d60a30536e39cc22/crates/pa-core/src/session_engine/auto_refine_trigger.rs#L125-L249)
has eligibility/cooldown checks. A configured `turnInterval=25` is not proof of a
connected production 25-turn scheduler.

### Where strategies and capabilities originate

Pretrained knowledge and recombination supply much proposed strategy. Runtime
programs supply computations, filters, experiments, and executable helpers.
Experience, user corrections, and child observations supply local feedback.
Existing packages, skills, and MCP servers supply external implementations.
Teacher-driven gradient learning belongs to a separate training pipeline.

Prime combines the first four sources. A strategy new to one run is not evidence
of global algorithmic novelty. Its [skill authoring contract](https://github.com/PrimeIntellect-ai/prime-agent/blob/5c898d1b27b109bd2d383c68d60a30536e39cc22/skills/skill-creator/SKILL.md#L8-L81)
requires real files and packaging for executable capability. Saving a skill
description or Python call reference does not create a working importable module.
Retained code still needs rediscovery, compatible dependencies, and invocation.

Persistent Python lets a model compute over data outside its prompt and expose
selected observations. That can reduce repeated reading, but a wrong filter can
hide decisive evidence. Prompt memory, transcript, live kernel state, and stored
harness records are separate. Compaction, value snapshots, and restart do not
preserve arbitrary instruction pointers or establish remote-effect completion.
Prime's [retrieval ranking](https://github.com/PrimeIntellect-ai/prime-agent/blob/5c898d1b27b109bd2d383c68d60a30536e39cc22/crates/pa-core/src/refinement/ranking.rs#L104-L175)
is deterministic lexical ranking, not a learned usefulness estimator.

The separate [Continual Harness paper](https://arxiv.org/html/2605.09998v1) and
[public training driver](https://github.com/sethkarten/continual-harness/blob/2a74aa2bcf17d019844a8b86e3748ed566aede69/train/dagger_prm.py#L206-L1443)
do include real trajectory collection, teacher correction, and SFT. This is not
Prime's production Rust adaptation path. Author-reported game progress does not
alone isolate weight changes from retained world/context state or prove
cross-family transfer and complete amortized economics.

## T3 lessons for delegated work

T3 owns accepted task intent and cross-provider lifecycle separately from native
provider children. Caller admission binds parent/thread/provider ownership;
caller-supplied task text cannot choose another parent.

Its [event transaction](https://github.com/pingdotgg/t3code/blob/d53873b6a4799e87afd63c8d288ef0089f5a3748/apps/server/src/orchestration-v2/EventSink.ts#L640-L703)
commits command receipt, events, projections, and effect outbox together.
External provider/Git effects happen afterward. Accepted intent is not completed
work, and a local transaction does not resolve "external effect happened, response
lost." Retry identities are scoped, not universal semantic deduplication.

Result transfer, task generation, delivery ownership, and durable read ACK are
useful patterns for retained workers. [Recovery scans](https://github.com/pingdotgg/t3code/blob/d53873b6a4799e87afd63c8d288ef0089f5a3748/apps/server/src/orchestration-v2/Orchestrator.ts#L12067-L12162)
can reconstruct missed terminal/delivery reactions. ACK proves a read, not model
understanding or artifact correctness. Wait timeout leaves work running; Stop,
task cancellation, provider interruption, and process termination differ.

Provider-native children remain provider-owned scheduling. Default shared cwd is
not isolation; explicit worktrees start from committed local HEAD without a dirty
overlay. Roles and mode ceilings are not portable OS confinement. These lessons
suggest explicit identity and evidence contracts, not a new general orchestrator.

## Immediate prerequisite: incremental execution capture

Existing co-train scripted evidence accepts complete actions in advance and can
replay/rescore them. It must keep v1 origin `scripted` and terminal
`scripted_final`. It cannot show a caller choosing B after observing actual A.

The bounded prerequisite, [SQL/PTC execution capture](../spec/sql-execution-capture.md)
with [acceptance tests](../train/test_sql_capture.py), is now implemented: literal-True execution
opt-in, canonical existing prompt/environment, 8 pre-dispatch attempts, distinct
executed/refused records, protected final-only scoring, and abort without score.
Capture requires current task/ID/DB/source/settings bindings and data-only
decoding. Finish must not replay actions.

Status: implemented trusted-host capture, including the 64 MiB per-invocation
extraction-work admission bound. Admitted answers use the unchanged extractor.
The historical default run was non-green (2,222 passed, one outer failure with
two nested bench failures). One nested ID and both assertion bodies were lost;
new fixture results cannot explain the unknown historical failure.

## Bounded executable workflow implemented

[Caller-authored executable skills](../spec/sql-executable-skills.md) now support
data-only candidate creation, provisional evaluation, actual four-case
qualification and externally approved reuse. Required `source_task` supplies
the exact routing fields absent from capture. Promotion independently rescores
the whole-envelope-pinned source to valid EX=0 and reruns the same program once
on each of four externally supplied, scope-matched cases. All four must return
valid EX=1. Distinct scoped IDs, task fingerprints, DB digests and non-source
splits are admission checks, not proof of independent draws or semantic diversity.
Reuse checks externally approved whole-envelope pins and current bindings.
Payload self-digests alone authorize nothing; evaluator/assets/approval remain
trusted-host responsibilities.

The combined skills/capture/exact-legacy scope passed **813 checks**, including
fresh-process reuse after origin/qualification DB deletion. Five separate
guard bypasses failed intended assertions. Catalog-discovering, identifier-quoting
code transferred across local fixture schemas; this demonstrates executable
mechanics, not model generation, learned policy or scientific generalization.
The bench readiness fixture now has a parent/grandchild handshake and targeted
positive/disabled-termination controls without changing production timeouts.
**Bounded offline acceptance, 2026-10-24:** complete configured default execution
finished **2,446 passed, 1 skipped, 2 deselected in 251.42s**, exit 0. Torch was
unavailable; the tokenizer-integration deselections were already configured.
Independent Python/general/security static reviews found no issues; execution
validation was separate. This clears the bounded offline gate, not a learning
or performance claim. Raw full-suite receipt, audit scope and historical
boundaries: [HANDOFF](../HANDOFF.md).

## Ranked backlog, capture and caller-authored mechanics complete

Automatic candidate generation and broader learned-policy experiments remain
unimplemented. All thresholds below are proposed screens, not achieved results
or build approval. Native discovery, default arms, graders and training gates
are unchanged; no T3 runtime or provider integration was added.

| Rank | Bet and prior art | Cheapest useful screen | Defer or kill when |
|---|---|---|---|
| 1 | Executable skills that transfer. Prime packaging, Voyager-style libraries, Continual Harness, GEPA motivate versioned code plus applicability contracts and independent promotion. | 20 development + 40 unseen schema/project variants, 3 paired seeds. Compare no library, descriptions only, frozen hand-written helpers, ordinary reflection, and evaluated executable promotion. Target at least 20% fewer repeated tool failures, success loss at most 1 percentage point, all-in cost at most 10% above strongest baseline. | Caller-authored qualification/reuse mechanics accepted through the bounded offline gate. Automatic generation and this comparison remain gated. Kill on any promoted known-wrong helper or no failure reduction. Local fresh-process invocation is not held-out cross-interface transfer or a learning claim. |
| 2 | Evidence/context and delegation economics. RLM computation, Prime retrieval/factory, T3 routing/handoff, GEPA motivate choosing observations and specialists under deterministic admission/budgets. | 30 development + 60 unseen tasks, 3 seeds, 8,000-token observation budget. Compare lexical, hybrid reranked, fixed-fanout, no-delegation, and learned allocation. Target 20% lower complete cost with at most 1-point success loss, or 5-point success gain at matched cost. | Defer adaptive retrieval and provider/native integration. Kill if savings disappear after child/summary charges or reasoning/tool options change silently. Strong deterministic routing may be enough. |
| 3 | Witnessed continuation and correct stopping. Prime goals/gates and T3 generation/transfer/ACK patterns motivate requirement-indexed evidence deltas. | 50 blocked + 50 solvable tasks, each with 3 fresh continuation points. Against fixed retries, deterministic evidence gates, and always-continue: 25% fewer unnecessary continuations, false success below 1%, success loss at most 1 point. At least 95% of unchanged blockers stop/escalate within 3 cycles. | Defer retained-worker protocol changes. Kill on false completion from a missing required artifact. Do not promise arbitrary exactly-once effects or restart continuation. |
| 4 | Small-model/tool co-specialization. Continual Harness DAgger/PRM/SFT and ordinary distillation motivate weight × tool/library ablations. | First prove 10 real rollout/update/reload examples: nonzero changed trainable tensors, checkpoint identity, fresh-process generation, and a zero-learning-rate negative control. Only then compare frozen/trained weights × frozen/updating library on 40 fresh tasks, 3 seeds, with a withheld task family. | Native training remains fail-closed. Stop on template/runtime/update/reload failure. Defer GPU/training until this gate and demand justify cost. Scripted replay or incremental capture does not satisfy it. |

For skill promotion, independent controls should include shuffled success labels,
fabricated successful traces, wrong implementations, and wrong-scope procedures.
For context policy, use irrelevant equal-length retrieval, shuffled descriptors,
and matched-extra-call controls. For continuation, delete required artifacts,
substitute always-true gates, and inject stale assignment-A results into B.
For training, use shuffled teacher labels and world/context resets.

## Economics and decision gates

Record model revision, reasoning settings, request/attempt/task/parent identity,
cache reads/writes, prices, tool compute, and missing-usage flags. Count root plus
exclusive descendants once, including rejected/failed/cancelled calls, summaries,
refinement, judges, routing fees, and failed jobs. Unknown charges remain unknown.
Prime's traced refinement/summary accounting omissions and T3's routing-dependent
session topology make token count or a displayed parent total insufficient.

Compare cold and equally prewarmed caches. Match all-role spend within 2% or
disclose the difference. Separate development/promotion cost from deployment;
report training amortization at 100, 1,000, and 10,000 uses. Immutable held-out
tasks and evaluator assets stay outside solver control. Negative controls must
actually fail before green results are trusted.

The bounded offline gate is accepted. The demonstrated fixture readiness gap is
repaired, not a reconstruction of both historical failures. Model-generated
skills, context/delegation policy, witnessed continuation and native model
training remain separate gated work.
Neither accepted refinement nor durable "done" status establishes improvement.
