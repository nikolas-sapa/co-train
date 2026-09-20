# Research Lane: Training Models For A Specific Agent Harness

Compiled 2026-09-19. Tooling note: `WebSearch` was unavailable (Bedrock rejects the
`web_search` tool type, HTTP 400). All bibliographic search was done through the arXiv
Atom API; full text via `arxiv.org/html/`, `arxiv.org/pdf/` + `pdftotext`, and
`r.jina.ai`. **The Semantic Scholar Graph API returned HTTP 429 on every attempt**, so
this report has zero S2 coverage (see Known Gaps §7.2).

---

## 0. Bottom line

1. **Harness-specific training is real, recent, and almost entirely a 2026 literature.**
   The term of art is "agent harness"; it barely exists before 2026.
2. **Harness-overfitting is measured, not speculative.** The strongest single result is
   **DCAS (arXiv:2608.06113, ASE '26)**: open models fine-tuned on OpenHands trajectories
   degrade badly under other scaffolds, with one model dropping **52.6% -> 8.4%** on
   SWE-bench Verified purely from a scaffold swap, while the *untrained base models* show
   no comparable divergence. The gap is fine-tuning-induced.
3. **Frontier vendors do ship harness-scoped models.** OpenAI's GPT-5-Codex carries an
   explicit deployment restriction to Codex-like environments. No equivalent public
   statement was found for Anthropic/Claude Code (negative result, §7.1).
4. **The inverse-capability hypothesis is refuted as a monotone law.** Two papers name the
   *opposite* effects: "harness leverage" (gain correlates **positively** with baseline
   strength, r=0.99, n=6) and a **non-monotone inverted-U** harness-benefit curve. A
   narrower mechanistic version survives (§4.4).
5. **Vendor-native model+harness pairing shows no measurable average advantage** in the one
   paired-contrast study that tested it.

---

## 1. Q1: Who has actually trained a model around a specific harness

### 1.1 Vendor / native-harness cases

#### OpenAI GPT-5-Codex — the clearest public case (confidence: STRONG)

Source: `https://openai.com/index/introducing-upgrades-to-codex/` (Sept 2025).

Verbatim:

> "GPT-5-Codex is a version of GPT-5 further optimized for agentic software engineering in
> Codex."

> "GPT-5-Codex was purpose-built for Codex CLI, the Codex IDE extension, the Codex cloud
> environment, and working in GitHub, and also supports versatile tool use. **Unlike GPT-5,
> which is a general-purpose model, we recommend using GPT-5-Codex only for agentic coding
> tasks in Codex or Codex-like environments.**"

That last sentence is a vendor-issued *deployment restriction*. It is as close to an
admission of model-harness coupling as exists in public vendor material: the model is
scoped to a harness family, not to a task family.

Supporting detail from the same page: GPT-5-Codex is *"more steerable, adheres better to
AGENTS.md instructions"*, and on OpenAI's own employee traffic *"for the bottom 10% of user
turns sorted by model-generated tokens ... GPT-5-Codex uses 93.7% fewer tokens than GPT-5"*
— i.e. the harness-specific training also reshaped the token-budget policy, not just
accuracy.

#### OpenAI codex-1 — points the *other* way (confidence: STRONG)

Source: `https://openai.com/index/introducing-codex/` (May 2025).

Verbatim:

> "Codex is powered by codex-1, a version of OpenAI o3 optimized for software engineering.
> It was trained using reinforcement learning on real-world coding tasks **in a variety of
> environments** to generate code that closely mirrors human style and PR preferences,
> adheres precisely to instructions, and can iteratively run tests until it receives a
> passing result."

> "On coding evaluations and internal benchmarks, codex-1 shows strong performance **even
> without AGENTS.md files or custom scaffolding**."

So OpenAI advertised harness-*robustness* for codex-1 (May 2025) and harness-*specificity*
for GPT-5-Codex (Sept 2025). The trajectory within one vendor runs from "trained across
environments, robust without scaffolding" to "purpose-built for this harness, use it only
here." That is a decision-relevant direction of travel.

#### Anthropic — nothing found (confidence: NEGATIVE, INCOMPLETE)

See §7.1. Searched arXiv `abs:"Claude Code" AND abs:"training"` (10 hits, none from
Anthropic) and fetched `anthropic.com/engineering/claude-code-best-practices` and
`anthropic.com/news/claude-sonnet-4-5`. Neither claims the model was RL-trained inside the
Claude Code harness. The best-practices page is about harness *usage* (context management,
verification loops), and the Sonnet 4.5 announcement talks about agentic capability and
alignment, not harness-specific training. **This negative is incomplete**: I did not
retrieve the Claude 4 / Sonnet 4.5 / Opus 4.5 system-card PDFs, the likeliest home for such
a statement.

### 1.2 Published harness-native training (research)

| Paper | arXiv | Harness(es) | What it did / headline numbers |
|---|---|---|---|
| **LEGO-RL: Harness-Native Reinforcement Learning for Coding Agents** (Huawei) | 2608.17393 | OpenHands SDK, **Claude Code**, OpenCode | GSPO on Qwen3.5-35B-A3B *inside production harnesses*. SWE-bench Verified: OpenHands SDK **64.0 -> 70.4**, Claude Code **62.4 -> 68.2**, OpenCode **57.2 -> 66.6**. Rollout-training probability correlation >0.99 |
| **Polar: Agentic RL on Any Harness at Scale** | 2605.24220 | Codex, Claude Code, Qwen Code, Pi | GRPO on Qwen3.5-4B via API-proxy trajectory reconstruction. SWE-bench Verified gains: **+22.6 (Codex), +4.8 (Claude Code), +0.6 (Qwen Code), +6.2 (Pi)** |
| **Agent Lightning v1.0: Towards Harnessed Agentic RL** (Microsoft) | 2608.17528 | arbitrary | Coins **"harnessed agentic RL, where the deploy-time harness directly participates in model post-training."** Qwen3.5-9B: SWE-bench Verified **41.8 -> 56.4** (+14.6 abs) on 6K examples, ~3,500 LoC framework |
| **DCAS** | 2608.06113 | Claude Code (CC 2.0.76 pinned) | SFT on 576 planning-aware trajectories collected **under Claude Code specifically**, captured via `claude-trace` HTTP interception. See §2 |
| **HarnessBandit: Joint Learnability-Transferability Scheduling for Multi-Harness Agentic RL** | 2609.13739 | six harnesses on ClawGym | Online bandit scheduler picking one harness per GRPO step from *learnability* (mean abs advantage) and *transferability* (cosine of gradient sketches vs EMAs of other harnesses). Qwen3.5-2B; eval on PinchBench (in-distribution OpenClaw) and ClawEval (**held-out harness**) |
| **What Does Multi-Harness RL Learn? Credit Assignment and Portability in Coding Agents** | 2609.04518 | Aider, OpenHands, Qwen Code, SWE-agent + held-out minimal harness | Qwen3-8B, frozen replayed records, Within vs Cross GRPO grouping, sealed SWE-bench Verified oracle, 24,000 evaluations. See §3.3 |
| **HarnessForge: Joint Harness and Policy Evolution** | 2606.01779 | 5 benchmarks | Formulates the agent system as a **harness--policy pair**; does *"fault-guided harness tailoring and **harness-conditioned policy alignment**"*. Qwen3-4B/8B, up to **+12.0%** over strongest baseline |
| **HASE: Harness-Aware Self-Evolving** | 2607.03935 | self-edited | Agentic RL where one model either solves the task *or edits selected harness components* in a multi-turn action space. A Qwen3-8B under HASE matches GPT-OSS-120B that uses Claude Code as harness proposer |
| **MemoryWalker: Stop Training Agents on Contexts They Never Saw** | 2609.00865 | **Claude Code**, OpenCode, Qwen-Agent, TC-RAG, AgentFold, MemexRL | Fixes the *training objective* for harness-side context compression. See §3.6 |
| **Co-Evolving Harnesses and Models** | 2609.09134 | evolved enterprise harnesses | Harness evolution + lightweight fine-tuning jointly, 7 enterprise tasks, Qwen3-Coder + Gemma 4. See §3.4 |
| **Ecdysis: Efficient and Effective Training of Runtime Harnesses** | 2609.11677 | runtime harnesses | Trains the *harness* rather than the weights; 1.84x speedup over prior harness-evolution methods, +18.56% reasoning accuracy |
| **JIT-Agent: Scaling Harness Intelligence via Just-in-Time Harness Evolution** | 2608.25593 | generates them | Inverts the problem: trains a model to **synthesize harnesses on the fly**. *"the first model purpose-built for just-in-time harness generation"* |
| **Coaching Qwen3 Coder 30B to Think Like a CodeClash Arena Agent** | 2609.16096 | CodeClash arena protocol | ReAct SFT rewriting teacher trajectories into explicit `[obs][thought][act]` chains for one specific interaction protocol; fine-tuned model beats Qwen3 Coder Plus in tournament |

**The Polar spread is the most striking number in this section.** The *same* GRPO recipe,
the *same* 4B model, the *same* benchmark, four harnesses: **+22.6, +4.8, +0.6, +6.2**. Yield
from harness-native RL varies by roughly 38x depending on which harness you train inside.
Confidence: MODERATE (single paper, single 4B model, no ablation of why).

**LEGO-RL's own limitation is load-bearing for Q2.** Verbatim from the Limitations section:

> "Our evaluation has several limitations. First, all experiments use Qwen3.5-35B-A3B, and
> **each coding-agent harness is trained separately, so generalization to other model
> architectures and mixed-harness training remains to be evaluated.**"

They trained one model per harness and explicitly did *not* test cross-harness transfer.
The most production-scale harness-native RL result available leaves the transfer question
open by its own admission. Confidence: STRONG (their own words).

### 1.3 Lab tech reports with harness-coupled post-training

- **Qwen3-Coder-Next Technical Report** (2603.00729) — the deliberate *anti*-overfit
  strategy. Trajectories generated under **six** frameworks: *"SWE-agent, Mini-SWE-agent,
  OpenHands, Claude-Code, Qwen-Code, and Terminus"*, teacher
  Qwen3-Coder-480B-A35B-Instruct. They report the transfer finding directly (§3.2).
- **MiniMax-M2 Series** (2605.26494) — *"Forge, a scalable **agent-native** RL system that
  adapts to long-horizon agent trajectories ... and a clean training-inference-agent
  decoupling that supports both white-box and black-box agents"*; and *"the latest M2.7
  checkpoint takes an early step toward self-evolution -- autonomously debugging training
  runs and **modifying its own scaffold**."*
- **Macaron-V1** (2608.09819) — the most explicit co-design framing found: *"recursive
  improvement of **versioned model-harness pairs**, where experience from one configuration
  is evaluated under an external contract and used to construct its successor"*; the
  algorithm section names *"**Model-Harness Co-design**"* and a *"versioned Harness Context
  Protocol contract."*
- **NeoHorse-1** (2609.08183) — *"a family of **agent-native models** developed to explore
  this path through agentic post-training"*; training examples *"preserve interleaved
  reasoning, tool calls, and **harness context**"*. Post-training raises macro-average
  58.94 -> 64.87 at 4B and 65.60 -> 69.04 at 9B across eleven benchmarks including
  harness-based agents.
- **Kimi K2** (2507.20534) / **Kimi K2.5** (2602.02276) — agentic RL *"through interactions
  with real and synthetic environments"*; K2.5 adds *Agent Swarm* orchestration. Not
  harness-specific, but the reference point DCAS compares against (K2 at 65.8% via
  large-scale agentic RL).
- **GLM-4.5** (2508.06471) — ARC (Agentic, Reasoning, Coding) foundation models, expert
  modes; included for completeness, no harness-specific claim located.
- **EnvCraft** (2609.05576) — synthesizes 139 interactive environments / ~20K tasks for
  agentic RL targeted at *"Claw-like agents"*; +11.9% on Claw-style benchmarks, +8.0% on
  general tool use for Qwen3/3.5 8B-32B. Environment-specific rather than harness-specific,
  but the same methodological family.

### 1.4 Adjacent: the harness-evolution subfield

Large and fast-growing; relevant because it is the "train the harness instead of the
weights" alternative, and because several of its papers report the transfer failures that
matter for Q2:

2605.30621 (Harness Updating Is Not Harness Benefit), 2608.09096 (Evo-Bench),
2609.04280 (EvoHarnessBench), 2608.19013 (Harness Continual Learning),
2609.01437 (HarnessDev), 2608.25593 (JIT-Agent), 2609.11677 (Ecdysis),
2606.01779 (HarnessForge), 2607.13683 (HarnessBank), 2608.10178 (One Recipe, Many
Harnesses), 2608.06301 (HarnessOpt-Bench), 2605.23904 (SkillOpt),
2606.12882 (HarnessBridge, a *learnable* harness controller trained by instruction tuning),
2603.25723 (Natural-Language Agent Harnesses).

---

## 2. DCAS in full (arXiv:2608.06113) — the central result

**Title:** DCAS: Decoupling CLI Agent Scaffolding to Internalize Planning across Scaffolds
**Venue:** ASE '26 (Automated Software Engineering), October 12-16 2026, Munich.
ACM DOI `10.1145/3832783.3834485`. Huawei-affiliated corresponding authors.
**Confidence: STRONG** — peer-reviewed, full cross-scaffold grid published, includes
untrained base-model controls, releases raw `claude-trace` HTTP logs.

### 2.1 The claim

Abstract, verbatim:

> "CLI-based software-engineering agents have matured rapidly, yet the open ecosystem has
> converged on a single training environment: trajectory datasets used to fine-tune open
> models are collected almost exclusively under OpenHands. **Models fine-tuned on this data
> score well under OpenHands but degrade substantially when deployed under any non-training
> scaffold. Untrained base models do not show this divergence, indicating the gap is
> fine-tuning-induced and tied to the conventions of the training scaffold.**"

Introduction, verbatim on the monoculture:

> "DCAS enables cross-scaffold evaluation of the SWE-Gym [19], Nebius [28], SWE-Lego [24],
> and CoderForge [2] same backend model and planning-aware trajectory collection all
> collect under OpenHands."

(Text is column-interleaved in the PDF; the claim is that SWE-Gym, Nebius, SWE-Lego and
CoderForge all collect their trajectories under OpenHands.)

And on why practitioners cannot route around it:

> "licensing, latency, and data-privacy constraints [7, 8], **not on which scaffold the
> available open models happen to have been trained under**."

### 2.2 Table 1 — the cross-scaffold grid (reproduced)

Caption, verbatim: *"Table 1: Pass@1 on SWE-bench Verified, max 100 turns. Italicized rows
are untrained base models. † reported result; all others are our runs. OH = OpenHands
(v0.50.0), CC = Claude Code, OC = OpenCode, Mini-SWE = mini-swe-agent."*

| Model | OH | CC | OC | Mini-SWE | max-min spread |
|---|---|---|---|---|---|
| *Qwen3-32B (base)* | 29.0 | 23.2 | 18.4 | 8.0 | 21.0 |
| **SWE-Lego-Qwen3-32B** [24] | **52.6†** | 44.2 | **8.4** | 37.6 | **44.2** |
| SERA-32B [21] | 54.2†ᵃ | 33.4 | 35.8 | 26.4 | 27.8 |
| Qwen3-32B-Nex-N1 [16]ᵇ | 50.5† | 50.8 | 26.2 | 15.6 | 35.2 |
| *Qwen3-30B-A3B-Instruct-2507 (base)* | 25.2† | 26.8 | 27.6 | 14.0 | 13.6 |
| Nebius-SWE-Rebench-30B [28] | 49.7† | 46.0 | 35.8 | 20.4 | 29.3 |

Footnotes, verbatim:
- ᵃ *"Public score at 64K context; model trained to 32,768 tokens."*
- ᵇ *"Trained on diverse multi-format trajectories [16], not a single scaffold."*

### 2.3 The 52.6% -> 8.4% collapse: exactly which model, exactly which pair

**Model:** `SWE-Lego-Qwen3-32B` — a Qwen3-32B fine-tuned on the SWE-Lego trajectory dataset,
which (like SWE-Gym, Nebius and CoderForge) was collected **under OpenHands**.

**Scaffold pair:** trained under **OpenHands** (52.6% Pass@1, reported figure), deployed
under **OpenCode** (**8.4%** Pass@1, DCAS's own run). A **44.2 percentage-point** drop from a
scaffold swap alone, with model weights, benchmark and turn budget held fixed.

**The authors' own stated explanation** for this specific cell, verbatim:

> "**Tool-call format incompatibility produces sharper failures: SWE-Lego-Qwen3-32B reaches
> only 8.4% on OpenCode because its tool-call** [format is incompatible]"

So the worst cell is attributed to a comparatively banal cause: the fine-tuned model emits
tool calls in the training scaffold's format, and OpenCode's parser rejects them. This
matters for interpretation — the extreme number is a *format* failure, not evidence that
deep planning behavior was lost.

**The secondary, better-controlled number** is the one the authors lead with in the body,
verbatim:

> "**Lego-Qwen3-32B drops from 52.6% on OpenHands to 44.2% on Claude Code**, and
> Nebius-SWE-Rebench-30B drops from 49.7% on ..."

i.e. **-8.4 pp** (OpenHands -> Claude Code) for SWE-Lego, and Nebius-SWE-Rebench-30B
49.7% -> 46.0% (**-3.7 pp**) on the same pair. These are the "clean" cross-scaffold drops,
free of format incompatibility. DCAS uses the -8.4 pp figure as its reference magnitude
throughout, not the -44.2 pp one.

**Other notable cells:**
- **SERA-32B**: 54.2% (OH) -> **33.4%** (CC), -20.8 pp. Part-attributed to a context-length
  conflict, verbatim: *"both SERA-32B and Qwen3-32B-Nex-N1 are fine-tuned to a context
  length that conflicts with Claude Code's hard-coded ceiling."*
- **Qwen3-32B-Nex-N1** (the *multi-format*-trained model): 50.5% (OH) / **50.8%** (CC) —
  effectively no OH->CC gap — but still *"degrades substantially on OpenCode (26.2%) and
  mini-swe-agent (15.6%)."* Verbatim: *"Qwen3-32B-Nex-N1 was trained on diverse
  multi-format trajectories [16] rather than under a single scaffold. It narrows the gap on
  Claude Code (50.8%, comparable to its OpenHands score) but still degrades substantially on
  OpenCode (26.2%) and mini-swe-agent (15.6%)."* **Multi-harness training buys partial, not
  full, immunity.**

### 2.4 The base-model control — the reason this is causal rather than correlational

The two italicized rows are the untrained base models the fine-tunes were derived from:

- **Qwen3-32B (base)**: 29.0 / 23.2 / 18.4 / 8.0 — spread 21.0 pp
- **Qwen3-30B-A3B-Instruct-2507 (base)**: 25.2 / 26.8 / 27.6 / 14.0 — spread 13.6 pp, and
  note it is *non-monotone*: it scores **higher** on OpenCode (27.6) and Claude Code (26.8)
  than on OpenHands (25.2)

Against fine-tuned spreads of 27.8-44.2 pp. The authors' framing, verbatim:

> "**The divergence is fine-tuning-induced.** ... Whatever causes the post-fine-tuning
> divergence is therefore something **installed by training**, not a property of the
> underlying model."

And on where the gap is largest:

> "[the spread is smaller] for the untrained base model in Table 1 than for any fine-tuned
> model, indicating that the divergence is **installed by training rather than fixed by the
> scaffold interface**"

**Caveat worth stating:** the base models score so low overall (8.0-29.0) that some of the
compressed spread is a floor effect. The base rows are a weaker control than they first
appear. Confidence on the causal claim: MODERATE-TO-STRONG (design is right, but the
controls sit near the floor).

### 2.5 The mechanism DCAS proposes: planning conventions

Their hypothesis distinguishes two senses of planning, verbatim from the abstract:

> "We argue that a load-bearing scaffold-specific behavior is planning structure, in two
> senses this paper distinguishes: **explicit planning**, a pre-execution plan produced as
> a first-class artifact, and **implicit planning**, the structural conventions that shape
> execution throughout the agent loop."

And from the body on why planning rather than the loop:

> "Scaffolds differ most visibly in their planning structure (Section 2.1), but underneath
> they share a similar execution loop: all four scaffolds in our study run a ReAct-style
> act/observe loop in which the model emits an action or a planning step, the scaffold
> returns an observation, and the loop continues until completion. **A model trained under
> one scaffold therefore** [has internalized one combination of conventions]"

> "**The cross-scaffold deployment gap is, to a substantial degree, a planning-convention
> mismatch**: a model trained under one scaffold has internalized one combination of
> explicit and implicit planning conventions, and deployment under another exposes that
> combination."

Implicit planning is defined as *"the structural behavior every scaffold imposes on the
agent loop turn by turn (sub-step granularity, when exploration gives way to action,
tool-call sequencing, failure recovery)."*

### 2.6 DCAS the system

A **backend-substitution interception layer**: it proxies API traffic between any CLI
scaffold and any backend model *without modifying the scaffold*. Built on top of an
open-source SWE-bench runner (McMillan [15]) *"which demonstrated the feasibility of
intercepting CLI scaffold API traffic for multi-model evaluation, and which we extended
with planning-stage separation, structured trajectory logging"* and multi-scaffold support.
Claude Code traffic is captured with `claude-trace` [40]. Scaffold versions are pinned:
**CC 2.0.76** throughout, **CC 2.1.73** for the version-transfer test, OpenCode v0.0.55,
mini-swe-agent v2.2.8, OpenHands v0.50.0.

This is the practically reusable artifact: an API-proxy shim is how you get cross-harness
evaluation and harness-specific trajectory collection without forking every harness.

### 2.7 RQ1 — plan quality is the high-leverage variable (+15 pp)

Controlled plan-source intervention, model/benchmark/scaffold fixed:

> "providing Qwen3-Coder-30B-A3B-Instruct with a plan from Claude Sonnet 4.5 improves Pass@1
> on SWE-bench Verified from **42.8% to 57.8%**, a **15-point swing that comes purely from
> varying the plan source**."

> "**The magnitude of this leverage exceeds the cross-scaffold drops observed in Section
> 2.2**, motivating the methodological investment of RQ2 and RQ3."

> "The SWE-Lego-Qwen3-32B drop of 8.4% from OpenHands to Claude Code is **smaller in
> magnitude than the available leverage from planning**. A model trained under OpenHands has
> not learned Claude Code's planning conventions, and the resulting planning deficit can
> plausibly account for a substantial fraction of that drop, although the present experiment
> isolates only the explicit-planning contribution."

**Plan-executor calibration anomaly worth flagging** (relevant to §4): Claude Sonnet 4.5
*"consistently outperformed Claude Opus 4.5 as a planner (57.8% versus 54.2-56.0%), despite
Opus being the more capable general-purpose"* model. Their explanation: *"plans from a more
capable model may implicitly assume a level of reasoning that a 30B executor"* cannot
supply. The *stronger* planner produced *worse* downstream results. This is a
capability-mismatch effect inside the scaffold, and it cuts against naive "use the best
model for every component" scaffolding.

Also verbatim, corroborating that plan quality is the driver: *"[13] provide independent
corroboration: across 16,991 CLI agent trajectories, **plan quality and plan adherence are
the primary drivers of resolution rate**."*

### 2.8 RQ2 — planning is learnable, and the two senses separate in training data

Training data: 576 verified two-phase trajectories from the SWE-Lego Real Data dataset
(~5,000 resolvable GitHub issues built on SWE-rebench, *"explicitly decontaminated against
SWE-bench Verified"*), collected **under Claude Code**, with rejection sampling to retain
only trajectories whose patch verifiably resolves the issue.

Pass@1 on SWE-bench Verified, backend Qwen3-Coder-30B-A3B-Instruct:

| Fine-tuned variant | Planning condition | Pass@1 | delta vs base |
|---|---|---|---|
| Base (no SFT) | No plan | 42.8 | — |
| **PlanOnly** | No plan | **53.8** | **+11.0** |
| PlanOnly | Self-plan | 53.2 | +10.4 |
| **Plan+Exec** | No plan | **52.8** | **+10.0** |
| **Plan+Exec** | Self-plan | **55.8** | **+13.0** |

Verbatim interpretation:

> "**PlanOnly installs the implicit planning conventions alone** (53.8% no-plan, no further
> self-plan benefit), while **Plan+Exec installs both** (52.8% no-plan plus +3.0% under
> self-plan to 55.8%), matching or approaching the performance of an external frontier
> planner without requiring one at inference."

> "The [gain is] carried by the **planning structure of the trajectory, not the volume of
> the data.**"

Note the odd ordering: PlanOnly's no-plan score (53.8) slightly *exceeds* Plan+Exec's no-plan
score (52.8). The authors flag it: *"The PlanOnly model achieved 53.8% without a plan (+11.0%
over base), even slightly exceeding the Plan+Exec no-plan score of 52.8%."*

### 2.9 RQ3 — what transferred (this is the positive result)

Setup: the *same* Plan+Exec model, trained on trajectories collected **exclusively under
Claude Code 2.0.76**, deployed into three unseen environments.

**Version transfer** (newer release of the training scaffold):

| Setting | No plan | Self-plan |
|---|---|---|
| CC 2.0.76 (training version) | 52.8 | 55.8 |
| **CC 2.1.73 (newer)** | **54.6** | **57.2** |

Verbatim: *"Evaluating the Plan+Exec model on CC 2.1.73 yielded 54.6% without a plan and
57.2% with self-generated plans, **the highest result in this paper that does not require an
external planner** ... scores exceed their counterparts on the training version CC 2.0.76
(52.8% and 55.8% respectively), confirming that the planning behavior **transferred robustly
to a newer release**."*

**Cross-scaffold transfer** (two scaffolds never seen in training):

> "it improves further to 57.2% under a newer release of the training scaffold, and **gains
> consistently on OpenCode (+3.4%) and mini-swe-agent (+7.0%) under self-plan, despite the
> model never** [seeing them]"

(also reported: *"Under mini-swe-agent, the SFT model reaches 42.4%"*, and a no-plan
cross-scaffold row of *"+1.8% on mini-swe-agent"*.)

The falsification logic, verbatim:

> "**A model that had only memorized the training scaffold's surface conventions would
> degrade on these unseen scaffolds, not gain on them.**"

Conclusion, verbatim:

> "**The planning capability acquired by Plan+Exec is a structural skill that transfers, not
> scaffold-specific memorization.**"

**Confidence: MODERATE.** The gains are real but small (+3.4, +7.0) relative to the drops
they are meant to answer (-8.4 to -44.2), the backbone is a single 30B model, and the
benchmark is SWE-bench Verified only.

### 2.10 DCAS's own stated threats to validity

Verbatim:

> "All experiments use SWE-bench Verified; results may not transfer to other code bases or
> task types."

> "All experiments also use Qwen3-Coder-30B-A3B-Instruct as the backend model, and the +15%
> gain from plan injection and the +13% gain from Plan+Exec fine-tuning **may not transfer
> directly to models of different scale, architecture** [or family]."

> "Attributing the cross-scaffold gap to planning structure is supported **only in part by
> our design.**"

> "We mitigate this by specifying exact versions (CC 2.0.76 and CC 2.1.73) and by releasing
> the raw claude-trace HTTP logs so that API interactions can be inspected independently."

> "DCAS training trajectories were collected exclusively under Claude Code, and
> cross-scaffold evaluation covers OpenCode v0.0.55 and mini-swe-agent v2.2.8."

### 2.11 DCAS on the field

- Independent corroboration, verbatim: *"Industrial labs have already begun moving in this
  direction: **Qwen3-Coder-Next [4] reports scores under several scaffolds rather than a
  single number, finding the same limited cross-scaffold transfer our results reveal.**"*
- Benchmark-hygiene consequence, verbatim: *"The results in Table 1 show this practice
  **systematically inflates apparent** [performance]"* — i.e. reporting a single number
  under the training scaffold overstates a model.
- Efficiency framing: *"Kimi K2 [11] reaches 65.8% via large-scale agentic RL; the DCAS
  Plan+Exec variant reaches 55.8% at 30B scale with SFT alone, providing a simpler"*
  approach.
- Positioning vs prior data work: *"SWE-Gym [19] established that SFT on expert trajectories
  transfers behavioral capabilities across model scales"*, and *"[Kimi-Dev shows] that
  Agentless-style training transfers planning and localization skills to SWE-agent
  frameworks."*
- Tooling novelty: *"While proxy tools exist in practice [40], **DCAS is the first to build a
  systematic research approach on top of this capability**, enabling controlled measurement
  of planning contributions and scaffold-specific trajectory"* collection.

---

## 3. Q2: What transferred and what did not

### 3.1 Summary

| Transfers | Does NOT transfer |
|---|---|
| Plan quality / planning *structure* as a skill (DCAS RQ3: +3.4 OC, +7.0 mini-SWE, +1.8 pp) | Tool-call formats (SWE-Lego -> OpenCode, 52.6 -> 8.4) |
| Scaffold *version* upgrades (CC 2.0.76 -> 2.1.73, scores improved) | Trained context-length assumptions vs a harness's hard ceiling (SERA-32B, Nex-N1 on CC) |
| Cross-*paradigm* skill priors (Kimi-Dev: Agentless -> SWE-Agent) | Planning *conventions* specific to one loop (DCAS's central claim) |
| A "shared core" of evolved harness logic (2608.10178) | The "ecosystem margin" of evolved harnesses, which *"requires native re-evolution"* |
| Localization / edit / self-reflection priors (Kimi-Dev) | Cross-harness *credit assignment* benefit (2609.04518: no portability gain) |
| | Expert trajectory imitation under an evolved harness (2609.09134: -4 to -30 points) |
| | Harness-evolution gains to unseen tasks (2609.11677, 2609.01437) |

### 3.2 Independent frontier-lab corroboration: Qwen3-Coder-Next (2603.00729)

**Confidence: STRONG** — a major lab reporting the negative finding about its own pipeline,
and acting on it by training on six harnesses.

Figure 3 caption, verbatim:

> "Figure 3: Scaling analysis of code agent pretraining on SWE tasks, SWE-Bench Verified and
> SWE-Bench Multilingual. **Left: Within-scaffold scaling shows consistent improvement with
> the increase of mid-training tokens. Right: Cross-scaffold transfer reveals limited
> generalization across different agent frameworks.**"

Body, verbatim:

> "we observe that **within the same scaffold, performance consistently improves with
> increased mid-training tokens**, demonstrating the effectiveness of large-scale agentic
> pretraining. **Second, cross-scaffold transfer remains limited. Models trained on
> trajectories from one scaffold do not transfer strongly to others. Third, framework
> specialization plays an important role. For example, OpenHands, which is highly
> specialized for SWE tasks, transfers poorly to SWE-Agent, while transfer in the opposite
> direction is moderately successful. This highlights a trade-off between framework
> generality and specialization.**"

Two structural facts here are decision-relevant:
1. **Harness-specific scaling works.** Mid-training tokens buy monotone within-scaffold
   gains. So there *is* a scaling curve to ride if you commit to one harness.
2. **Transfer is asymmetric.** Specialized -> general transfers poorly; general ->
   specialized transfers moderately. Direction matters, which suggests training on the more
   general harness and deploying to the specialized one, not the reverse.

Their mitigation is the six-harness trajectory mix (§1.3), plus reporting **per-scaffold**
scores rather than one number (Table 3, reproduced in §4.3).

### 3.3 The evaluation harness dominates the training recipe (2609.04518)

**What Does Multi-Harness RL Learn? Credit Assignment and Portability in Coding Agents.**
Qwen3-8B from one supervised warm start; frozen replayed task-harness records from Aider,
OpenHands, Qwen Code and SWE-agent; equal update counts; two GRPO grouping rules (**Within**
= one group per task-harness pair, **Cross** = harnesses pooled within a task); every
checkpoint scored by a *sealed* SWE-bench Verified oracle on the four source harnesses plus
a minimal harness **held out of training**.

Verbatim:

> "**The evaluation harness is the dominant variable: across 24,000 sealed evaluations it
> moves the mean solve rate from 2.14% to 9.27%, a factor of 4.3, where the training recipe
> moves it by 1.16.** The grouping rule is not."

> "On the held-out harness, **Cross minus Within is +0.25 pp, 95% confidence interval
> [-0.48, +1.02]**, at eight attempts per task, and +0.16 [-0.41, +0.72] pooled over three
> training seeds whose individual estimates change sign. **Each rule's own seed range, 0.42
> to 0.45 pp, exceeds the difference between them.**"

The most interesting mechanistic result: the advantage signal *encodes harness identity*.

> "**The pooled advantage carries the harness: an out-of-fold classifier recovers the
> generating harness from Cross's advantage +4.48 pp above the shuffled-label baseline and
> from Within's not at all**, and the two rules still reach the same held-out score and
> action distribution inside each harness. **Re-collecting half the training data on-policy
> does not change this.**"

Conclusion, verbatim:

> "**Cross-harness credit yields configuration adaptation and no more portable capability
> than within-harness credit. Multi-harness RL reports should state the grouping boundary
> and test under an unseen harness.**"

**Confidence: MODERATE-TO-STRONG.** Large sealed evaluation, seed-level variance reported,
a real held-out harness. Limits: one 8B model, one warm start, replayed (frozen) records for
the main contrast.

### 3.4 Harness-fit can be actively destroyed by imitation (2609.09134)

**Co-Evolving Harnesses and Models: On-Policy Correction Helps Weaker Models Catch Up Where
Imitation Fails.** Seven enterprise agent tasks; Qwen3-Coder and Gemma 4 as the weaker
models.

Verbatim:

> "Across seven enterprise agent tasks, we first evolve a harness with the weaker model,
> then find that **a stronger expert often uses it more effectively**, suggesting expert
> supervision could close the remaining gap. However, **training the weaker model on the
> expert's complete trajectories under the evolved harness backfires: performance regresses
> on all seven tasks by 4 to 30 points across Qwen3-Coder and Gemma 4, even though the same
> procedure helps under the unevolved harness.**"

> "Our analysis shows that **imitation transfers knowledge and increases scaffold usage, but
> disrupts model-harness fit: the weaker model adopts the expert's planning strategy without
> the competence to execute it and no longer matches the harness evolved around its native
> planning style.**"

Their fix is on-policy expert *correction*: localize the failing turn in the weak model's own
rollout and have the expert rewrite **only that turn**, *"preserv[ing] the model's planning
style"*. They call the result *"a compatibility-preserving recipe for economical
co-evolution."*

This is the sharpest statement of **model-harness fit** as a real quantity that training can
break. It also interacts with DCAS's planner anomaly (§2.7) and the Qwen3-Coder-Next
asymmetry (§3.2): all three say the same thing, that a stronger source of plans/trajectories
is not automatically better for a weaker executor.

**Confidence: MODERATE** (7 tasks, 2 model families, no third-party replication), but the
effect size (-4 to -30 points, all seven tasks) and the clean control (same procedure helps
under the *unevolved* harness) make it hard to dismiss.

### 3.5 What DID transfer across paradigms: Kimi-Dev (2509.23045)

**Kimi-Dev: Agentless Training as Skill Prior for SWE-Agents.** Verbatim:

> "We argue these paradigms are not mutually exclusive: **reasoning-intensive Agentless
> training induces skill priors, including localization, code edit, and self-reflection that
> enable efficient and effective SWE-Agent adaptation.**"

> "we first curate the Agentless training recipe and present Kimi-Dev, an open-source SWE
> LLM achieving **60.4% on SWE-bench Verified**, the best among workflow approaches. **With
> additional SFT adaptation on 5k publicly-available trajectories, Kimi-Dev powers
> SWE-Agents to 48.6% pass@1**, on par with that of Claude 3.5 Sonnet (241022 version)."

> "structured skill priors from Agentless training **can bridge workflow and agentic
> frameworks for transferable coding agents.**"

This is the strongest *positive* transfer result in the whole lane, and it is a
cross-*paradigm* one (single-turn workflow -> multi-turn agent), which is a bigger gap than
harness-to-harness. It suggests the transferable unit is a **skill prior** (localize, edit,
reflect) rather than a loop convention. Confidence: STRONG.

Related: **SWE-Gym** (2412.21139) established that *"SFT on expert trajectories transfers
behavioral capabilities across model scales"* (up to 19% absolute resolve-rate gains; 32.0%
Verified / 26.0% Lite with verifiers). **SWE-smith** (2504.21798) scaled the data (50k
instances, 128 repos, SWE-agent-LM-32B at 40.2% Verified) — note SWE-agent-LM-32B is itself
a single-harness-named model. **Yet Even Less Is Even Better** (2604.00824) reports a
counterpoint on data volume: STITCH trains across *multiple* agent frameworks
(mini-SWE-agent, MSWE-agent) with <1K trajectories and still gets large gains, e.g.
*"MiniMax-M2.5-STITCH achieves 43.75% with our CodeArts Agent scaffold (+16.67%)"* and
*"GLM-4.7-STITCH improves the compilation pass rate to 61.31% (+43.34%) with less than 1K
training trajectories."*

### 3.6 Training under harness-side context compression (2609.00865)

**MemoryWalker: Stop Training Agents on Contexts They Never Saw.** This is the most
technically specific harness-conditioned-training paper found. Verbatim:

> "**Production agent harnesses such as Claude Code and Qwen-Agent compress context during
> rollout, but training under compression creates a conditioning problem: every eviction
> branches the effective history, so the learning object is a tree rather than a sequence.**
> Existing linearizations either retain the rightmost path, causing **time-travel leakage**,
> or replay a depth-first traversal, causing **train-inference mismatch**."

Their corrections: **LogitTree** (segmented K-forward traversal, K+1 backward passes), a
packed **4D attention mask** (needs a custom kernel and *white-box eviction records*), and
**SDCC** (self-distillation for conditioning consistency, single backward pass, applies to
*black-box* harnesses, with an O(sqrt(eps_KL)) bound on the train-deployment total-variation
gap).

Result, verbatim: *"On seven web-search benchmarks with TC-RAG, AgentFold, MemexRL, **Claude
Code**, and **OpenCode**, naive training inflates the train-rollout log-probability gap,
especially on eviction-heavy batches. The exact methods stay at the no-compression floor, and
SDCC substantially closes the gap, with lower logit drift and higher rollout rewards."*

Decision-relevant: if you train inside a harness that compacts context (Claude Code does),
the naive objective is *wrong*, and the correction needs either white-box eviction records
or a distillation relaxation. This is a concrete engineering prerequisite for harness-native
training, not a nice-to-have.

Corroborating on the same problem from the RL-systems side: **LEGO-RL** needs *"in-process
LLM proxying that captures raw generation streams for token-level alignment and robust
trainer-side log-probability recomputation, **even under harness-side compaction or
re-serialization**"*; **Polar** *"proxies LLM API calls, records token-level model
interactions, and reconstructs token-faithful trajectories"*; **Agent Lightning v1.0** names
the same class of problems — *"retokenization, sample merging, advantage calculation, loss
normalization, and backend scheduling, which can substantially affect training stability and
effectiveness"* — because *"the harness, rather than the training engine, owns the
environment interaction loop, while the trainer observes only sequences of LLM
request-response pairs."*

### 3.7 Counter-evidence: vendor-native pairing is not measurably better

**Harness or Model? Isolating the Harness Effect in Agentic Coding with a
Contamination-Controlled Private Suite** (2609.11987). The only paper found that directly
tests the vendor-native assumption with paired same-model contrasts.

Setup, verbatim: *"**Vendors ship harnesses tuned to their own models, and practitioners
assume the vendor-native pairing solves more tasks.** We measure that assumption with paired
same-model contrasts on a private, contamination-controlled suite of 256 repository and
post-cutoff contest tasks. The same 80 tasks ran under **claude-agent-sdk** and under
**deepagents** on **claude-opus-4-8**, and under the **openai-codex SDK** and deepagents on
**gpt-5.5**, with gemini-3.5-flash and deepseek-v3.2 as side cells. 792 of 800 planned runs
were graded by an isolated oracle."*

Headline, verbatim:

> "**Neither contrast resolves an average advantage for either harness: -1.25 pp for Opus
> 4.8 (48.8% vs 50.0%, task-bootstrap 95% CI [-10.0, +7.5]) and +1.25 pp for GPT-5.5 (55.6%
> vs 54.4%, CI [-4.4, +6.9]).**"

The stratification, with the authors' own warning:

> "The Opus average combines opposite strata: **the native harness trails by 9.0 pp on the 61
> repository tasks and leads by 23.7 pp on the 19 contest tasks** (label-permutation
> p = 0.003). **The partition was chosen after seeing the data and needs a designed
> replication.**"

Two other findings worth carrying:
- *"Correctness and completion also separate: **22 of 81 runs cancelled at the wall-clock
  ceiling had produced a passing patch.**"* (Your harness's stop policy is silently
  discarding correct work.)
- Cost: *"Re-priced from raw per-turn usage at frozen list prices, the neutral harness cost
  **1.3 to 1.6 times as much per solved task** on Opus 4.8 and 1.2 times on GPT-5.5"* — but
  *"On the Anthropic account 58 runs left no usage record, and allocating that spend to
  either cell would move the Opus ratio between 0.7 and 2.3, **so the billed ordering is
  unresolved.**"*
- The paper is a self-correction: *"This revision corrects an August 2026 manuscript whose
  cost figures rested on a usage-semantics defect in our own telemetry."*

**Confidence: MODERATE for the null result; SPECULATIVE for the repo-vs-contest
stratification** (authors flag it as post hoc).

Corroborating null: **HarnessOpt-Bench** (2608.06301) evaluated *"5 frontier LLMs as
optimizers both under a shared coding harness and under their native harnesses across 4
downstream tasks, over 111 scored runs"* and found *"optimizer models separate more than the
coding harnesses they act through, **native harnesses are not consistently superior**, and
gains vary substantially across tasks and seed regimes."*

### 3.8 Harness-side evolution overfits too

- **Ecdysis** (2609.11677), verbatim: harness search *"incurs substantial time overhead due
  to repeated agent executions and code modifications, and **may overfit to observed tasks
  and specific failure patterns, resulting in degraded generalization to unseen tasks.**"*
  Their diagnosis is the useful part: *"an observed failure can reflect either
  **model-specific deficiencies or systematic harness deficiencies**, and directly
  optimizing against individual failures can lead to unnecessary **model-specific
  accommodation**."*
- **HarnessDev** (2609.01437), verbatim: *"**Evolution produces some performance gains, but
  they are unstable and transfer only partially to held-out tasks.** Experiments with a fixed
  runtime model further show that **the gains depend strongly on the model executing the
  harness, indicating limited transfer across models.**"* Also: generated harnesses *"remain
  substantially behind mature human-engineered references on code and on search and
  research, while matching or exceeding the selected references on writing and
  machine-learning experimentation."*
- **One Recipe, Many Harnesses** (2608.10178), grid of 8 languages (Multi-SWE-Bench) x 3 base
  models with a fixed evolution recipe, verbatim: *"(1) The loop improves held-out solve
  rates over both a minimal seed and the manually designed mini-SWE-agent scaffold in most
  cells, **but with two null regions**. ... (3) **Evolved harnesses share an abstract playbook
  across languages but instantiate it with almost disjoint language ecosystem machinery.**
  (4) **The shared core transfers and can be distilled into one universal harness, while an
  ecosystem margin resists both and requires native re-evolution.**"*
- **Harness Continual Learning** (2608.19013): *"Because these contents jointly shape later
  execution, a harness update can disrupt pre..."* — harness updates as a source of
  catastrophic-forgetting-analogue.

### 3.9 Harness churn as a moving target

**Don't Blame the Large Language Model: How Agent Harness Evolution Shapes Coding Agent
Quality** (2607.03691). First controlled longitudinal study that fixes the model and varies
only the harness. Verbatim:

> "**Practitioners regularly report quality regressions after agent harness updates, yet
> consistently attribute them to the underlying model rather than the harness itself.**"

> "Unlike prior work that fixes the agent harness and varies the model, **we fix the model
> and vary only the agent harness, evaluating 35 sequential releases** to measure their
> impact on agent effectiveness and efficiency. We first empirically study the development
> and release evolution of five major open-source agent harnesses (i.e., Codex, Qwen Code,
> Gemini, OpenCode, and OpenHands), revealing **extreme release velocities exceeding two
> releases per day** and thousands of issues within months. We then perform a controlled
> deep dive into **35 sequential releases of the Qwen Code CLI**, evaluating each against 50
> stratified SWE-bench Verified tasks while holding the underlying LLM constant."

Implication for harness-specific training: the target moves faster than a training run. Two
releases per day. DCAS's version-transfer test (CC 2.0.76 -> 2.1.73, §2.9) is therefore not a
nice-to-have robustness check, it is the *minimum* viable generalization requirement.

### 3.10 Benchmark-validity consequences

- **Stop Comparing LLM Agents Without Disclosing the Harness** (2605.23950) formalizes the
  **Binding Constraint Thesis** (see §4.2.6) and proposes a disclosure standard plus a
  variance-decomposition protocol: *"Until harness specifications are disclosed, leaderboard
  comparisons for long-horizon agents should be treated as incomplete and potentially
  misleading."*
- **The Scaffold Effect in Coding Agents** (2607.22585): Qwen 3.6 Plus and MiniMax M2.5
  across Goose / OpenCode / OpenHands-SDK on 50 Terminal-Bench Pro tasks. *"**Harness choice
  induces up to a 40x difference in tokens per solved task, while paired within-model
  pass-rate differences remain 0-8 percentage points** (95% paired-task bootstrap CIs include
  zero except for the largest gap). **Failure fingerprints replicate across models** (REASON
  for Goose, VERIFY/MAX_TURNS for OpenHands-SDK, idle-loop/TIME for OpenCode), indicating
  harness-level biases that are largely model-independent."*
- **The Double Measurement Confound in Agent Benchmarks** (2609.09218): names **de-scaffolding**
  as an audit step — *"execution-critical decisions are performed by a fixed scaffold instead
  of the model"* — and finds *"**scaffold ownership is an uncontrolled axis wherever we
  probed it.**"*
- **What Twelve LLM Agent Benchmark Papers Disclose About Themselves** (2605.21404): audit of
  harness disclosure in benchmark papers.
- **Harbor Adapters / Harbor-Index** (2609.04298): unified evaluation infrastructure for
  porting agents across benchmarks — the practical prerequisite for any cross-harness study.
- **Same Model, Different Harness: Different Coding-Agent Results** (2608.26218): two
  configurations of the *same* harness, model and task fixed. *"The tight-window Verified
  comparison uses 169 tasks, a 20,480-token window, and a fixed 480-second attempt endpoint;
  on this cohort, **treatment raises mean per-task F2PF from 28 percent to 49 percent and
  complete solutions from 43 to 72.** Without model-specific retuning, the same frozen
  treatment also raises both endpoints on the same cohort for three additional models with
  different designs."* A context-management change inside one harness moved results as much
  as a model change would. Confidence: WEAK-MODERATE (see §7.7 on this source cluster).

---

## 4. Q3: The inverse-capability hypothesis

**The hypothesis as posed:** harness/scaffold gain is inversely proportional to base model
capability; stronger models benefit less from elaborate scaffolding.

**Verdict: refuted as a monotone law. Partially supported as a defect-compensation law.**
Both directions have direct evidence, and the best-designed paper on each side contradicts
the other.

### 4.1 Evidence FOR

#### 4.1.1 An Empirical Study of Harness Design for Coding Agents (2609.20804) — the best-designed study on this axis

**Confidence: STRONG for the planning finding, MODERATE for the tool finding.**
UMass Amherst / Emory / UNC Charlotte, work during internships at Zoom. arXiv 17 Sep 2026.
Design: a lightweight harness with a **fixed execution loop** while three components vary
(planning, action space, context management). **176 matched settings**, four models spanning
a real capability ladder (**Nemotron-3 30B, 120B, 550B; Mistral-Medium-3.5-128B**), on
SWE-Bench Verified and Terminal-Bench 2.1, five context-management strategies (T0-T4), four
context-window budgets (32k/64k/96k/128k). Significance by two-sided exact McNemar with
Benjamini-Hochberg q<0.05.

Headline findings, verbatim:

> "**(3) Planning shifts from an accuracy scaffold for weaker models to a cost saver for
> stronger models, with little change in accuracy.** (4) **Predefined tools improve
> performance for models with weaker bash proficiency, whereas bash-capable models can
> operate effectively with a bash-only interface and achieve substantially lower cost**,
> especially on command-line-centric tasks."

> "**Planning changes from an accuracy scaffold to an efficiency aid as model capability
> increases.**"

**The planning numbers** (T4 context management, 128k budget, full tool set):

| Model | SWE-Bench effect | Terminal-Bench effect | Cost effect |
|---|---|---|---|
| **Nemotron-3 30B** (weakest) | **+11.6 pp** success | **+4.5 pp** success | higher on both |
| **Nemotron-3 120B** | *"no consistent success-rate gain"* | — | up on SWE-Bench, down on Terminal-Bench |
| **Nemotron-3 550B** | **-2.0 pp** success | — | **-~30%** |
| **Mistral-Medium-3.5-128B** | **-0.4 pp** success | — | **-~32%** |

Verbatim: *"For Nemotron-3 30B, planning increases success rate by 11.6 percentage points on
SWE-Bench and 4.5 points on Terminal-Bench, at higher cost on both benchmarks. For
Nemotron-3 120B, planning yields no consistent success-rate gain; it increases cost on
SWE-Bench but reduces it on Terminal-Bench. For Nemotron-3 550B and Mistral-Medium-3.5-128B,
planning reduces cost on both benchmarks, accompanied by small decreases in success rate. On
SWE-Bench, their costs fall by approximately 30% and 32%, respectively, while success rates
decrease by 2.0 and 0.4 percentage points."*

Takeaway as stated: *"**Planning trades additional computation for accuracy on the weaker
model, but primarily reduces cost on the stronger models; its value at intermediate
capability remains task-type-dependent.**"*

**The mechanism is the most useful part.** It is not that strong models "need less
structure"; it is that planning fixes a *specific failure mode* that only weak models have,
namely premature termination before an edit is attempted. Verbatim:

> "**Planning sustains the weakest model's trajectory long enough to attempt an edit.** ...
> **Disabling planning reduces the median SWE-Bench trajectory length from 40 to 5 turns.
> Without planning, 68.6% of runs terminate without an edit and 58.4% terminate during
> Localize, compared with 27.8% and 10.4%, respectively, with planning.** These results
> suggest that planning helps the least capable model sustain execution through an initial
> edit attempt, with the additional turns contributing to higher cost. For Nemotron-3 120B,
> trajectory-length distributions nearly overlap, consistent with the absence of an accuracy
> gain."

> "**Planning shortens SWE-Bench trajectories for stronger models by reducing post-edit
> verification.**" — median trajectory 108 -> 74 turns for Nemotron-3 550B, 68 -> 53 for
> Mistral.

Turn/tool-call deltas from planning off -> on (Table 5) show the divergence starkly:
- Nemotron-3 30B: **+293.2% turns, +474.0% tool calls, +104.1% input tokens** (SWE-Bench)
- Nemotron-3 120B: +20.1% turns, +42.7% tool calls, +10.3% input tokens
- Strongest tier: **-23.2% turns, -23.3% tool calls, -15.1% input tokens**

Failure-stage analysis confirms distinct defect profiles: *"for Nemotron-3 30B, more than
half of unresolved runs fail at file localization, whereas for Nemotron-3 550B and
Mistral-Medium-3.5-128B, the majority reach the correct file and lines but fail at patch
implementation."*

**The action-space finding, and its counterexample inside the same paper.** Verbatim: *"**The
predefined tool set scaffolds weaker models, while bash-only can benefit stronger ones.**
Figure 7 shows that the predefined tool set benefits the weaker Nemotron-3 models most. **For
Nemotron-3 30B, the predefined tool set raises success by 15.0% on SWE-Bench and 10.1% on
Terminal-Bench.** These gains reflect **alignment between the model's learned action
vocabulary and the harness interface.**"* Takeaway: *"The predefined tool set scaffolds weaker
models that cannot reliably express intent through bash alone, but **can add overhead for
stronger models** capable of composing complex, multi-step shell commands."*

**But**: *"the Mistral bash-only setting is **the only strong-model configuration in which
file-localization failures rise sharply, from 16.0% to 41.4%**, which indicates that its
**23.2-point drop** under bash-only originates mainly before the repair step."* So a strong
model lost 23.2 points when the scaffold was simplified. Not monotone.

**Context management goes the other way entirely** — it is governed by context pressure, not
capability: *"(1) Context management becomes increasingly valuable as the context-window
budget tightens, with most of its benefit coming from preventing context-overflow
failures."* At 32k, T0 (no context management) scores **0** for Nemotron-3 30B; at 128k the
tiers barely differ.

And a nice "strong models ignore affordances" result: *"**Models, especially stronger ones,
almost never call `recall_event` to recover elided observations, so lossless recall yields no
accuracy gain over elision alone.**"* Of 64 T2/T4 settings, *"36 (56.3%) never call
`recall_event`, the median invocation rate is zero"*, and the mean falls from 0.540 calls/task
at 32k to 0.007 at 128k. Building recovery machinery that strong models don't use is a real
and specific waste.

The paper also cites the prompt-level analogue explicitly: *"Individual interventions can
likewise become less useful or even harmful for stronger models, as observed for
prompt-engineering strategies in software engineering (Wang et al., 2026)."*

#### 4.1.2 AI4AI at Test-Time: Strong-to-Weak Capability Transfer via Harnesses (2608.12307)

**Confidence: MODERATE.** Four Theory-of-Mind benchmarks; each builder model uses 5% of data
as validation to iteratively refine a harness over multiple rounds; finalized harness
evaluated on the full test set.

Verbatim: *"Empirically, this form of test-time capability transfer is highly effective,
**nearly doubling average target-model performance from 0.49 to 0.91**."*

The FOR quote: *"We further find that builder-model reasoning effort improves harness quality
monotonically, platform effects are modest relative to the builder model's own capability,
and **weaker target models receive the largest gains.**"*

**The mechanism caveat is essential and cuts against a generous reading:** *"Our analysis
shows that the gains come primarily from **offloading unstable model reasoning into
deterministic code, benchmark-specific routing, and strict answer-format enforcement**, rather
than from encouraging the target model to reason more extensively or sample more broadly."*
"Benchmark-specific routing" is close to benchmark fitting; the gain is compensation and
format enforcement, exactly the categories that vanish as a model gets better at formats.

#### 4.1.3 One Recipe, Many Harnesses (2608.10178) — the cleanest mechanistic statement

**Confidence: MODERATE-TO-STRONG.** This is the paper that states the *correct* version of
the hypothesis. Verbatim:

> "**(2) Gains compensate recoverable execution defects, where defect mass is near zero, and
> gain is near zero; which defect dominates is cell-specific. A harness closes the gap
> between what a policy can do and what it does.**"

And the framing conclusion: *"these results **recast the evolved harness as a legible
compensation layer, shaped jointly by the language's engineering demands and the model's
behavioral gaps**, rather than an opaque benchmark-tuned scaffold."*

This reframes the axis correctly: gain tracks **defect mass**, not capability. Capability
predicts gain only to the extent that it predicts defect mass — and defect mass is also driven
by the *task environment* (their finding (3): evolved harnesses *"instantiate [the playbook]
with almost disjoint language ecosystem machinery"*), which is why the relationship to
capability is noisy.

#### 4.1.4 The prompt-level analogue (2411.02093, ACM TOSEM 35(8) 2026)

**Do Advanced Language Models Eliminate the Need for Prompt Engineering in Software
Engineering?** Three SE tasks (code generation, translation, summarization), GPT-4o
(non-reasoning) vs o1 (reasoning). **Confidence: STRONG** — peer-reviewed in TOSEM, and it is
the citation 2609.20804 uses for this pattern.

Verbatim: *"Our findings reveal that **prompt engineering techniques developed for earlier
LLMs may provide diminished benefits or even hinder performance when applied to advanced
models. In reasoning LLMs, the ability of sophisticated built-in reasoning reduces the impact
of complex prompts, sometimes making simple zero-shot prompting more effective.**
Furthermore, while reasoning models outperform non-reasoning models in tasks requiring complex
reasoning, they offer minimal advantages in tasks that do not need reasoning and may incur
unnecessary costs."*

This is the strongest *peer-reviewed* support for the general shape of the hypothesis, but it
is about **prompt-level** scaffolding, not agent harnesses, and the capability axis is
non-reasoning vs reasoning rather than a scale ladder.

#### 4.1.5 Derived: cross-harness spread vs capability in Qwen3-Coder-Next Table 3

**Confidence: SPECULATIVE. This is my derivation from their table, not a claim they make, and
it is confounded.**

Qwen3-Coder-Next Table 3, SWE-Bench Verified, max 300 agent turns, all baselines replicated
by the Qwen team on each scaffold with hacking-free mechanisms applied:

| Model | Size | SWE-Agent | MiniSWE-Agent | OpenHands | spread (my calc) |
|---|---|---|---|---|---|
| Claude-Opus-4.5 | ? | 78.2 | 77.8 | **79.0** | **1.2** |
| Claude-Sonnet-4.5 | ? | **76.0** | 68.4 | 74.6 | **7.6** |
| DeepSeek-V3.2 | 671A37 | 70.2 | 67.2 | **72.6** | 5.4 |
| GLM-4.7 | 358A32 | **74.2** | 70.4 | 70.6 | 3.8 |
| MiniMax-M2.1 | 230A10 | **74.8** | 70.4 | 71.0 | 4.4 |
| Kimi-K2.5 | 1000A32 | **73.2** | 70.8 | – | 2.4 |
| Qwen3-Coder-Next | 80A3 | 70.6 | 71.1 | **71.3** | **0.7** |

Suggestive: the strongest model in the table (Opus 4.5) has the *smallest* harness
sensitivity among the proprietary models (1.2 pp), while Sonnet 4.5 one tier down swings
7.6 pp.

**The confound is fatal to a clean reading.** Qwen3-Coder-Next, the *weakest* model in the
table, has the smallest spread of all (0.7 pp) — and it is precisely the model trained on
six-harness trajectory data. Harness sensitivity therefore tracks **training-data harness
diversity** at least as much as it tracks capability. This is also DCAS's Nex-N1 result
(§2.3) in another form. Which means: if you want harness-insensitivity, the evidence says buy
it with multi-harness training data, not by buying a bigger model.

Note also which harness wins is model-dependent, as 2609.20804 observes of this very table:
*"a cross-harness evaluation by Cao et al. (2026) reports that **Claude-Opus-4.5 performs
best with OpenHands** among the evaluated harnesses, whereas **Claude-Sonnet-4.5 performs
best with SWE-Agent**, suggesting that harness preferences can vary across models."*

#### 4.1.6 Ancestor claim: Agentless (2407.01489)

The original "simpler beats elaborate" result, and the intellectual ancestor of this whole
question. It is about **scaffold complexity at a fixed model**, not a capability axis, so it
supports the hypothesis only by analogy. Included because every paper in this lane cites it.

### 4.2 Evidence AGAINST

#### 4.2.1 The Harness Effect (2607.06906) — "harness leverage", r=0.99 POSITIVE

**This is the direct contradiction.** Confidence: **MODERATE, discount for conflict of
interest.**

Setup, verbatim: *"We isolate it with a controlled swap: **22 locked evaluation tasks, six
foundation models (Claude Sonnet 4.6, Gemini 3.1, Gemini Flash 3.5, Qwen 3.6, GLM 5.1,
Palmyra X6), changing only the orchestration layer** -- a frozen conventional production loop
versus the Writer Agent Harness."*

Efficiency results (model-held-constant): *"the harness cuts blended cost per task **41%
($0.21->$0.12)**, median wall-clock **44% (48s->27s)**, and tokens per task **38%
(14.2k->8.8k)**, with task-completion quality at parity (0.78->0.81, directional at this
sample size)."*

**The key sentence, verbatim:**

> "**Efficiency is model-invariant -- every model gets cheaper (33-61%) -- while quality
> gains are capability-dependent: a model's gain correlates almost perfectly with its
> baseline strength (r=0.99, n=6), a phenomenon we term harness leverage.**"

**The exact quantities correlated:** (x) each model's *baseline* task-completion quality
under the frozen conventional production loop, against (y) that model's *gain* in
task-completion quality from swapping to the Writer Agent Harness. **r = 0.99, n = 6.**

Also: *"Quality per dollar rises 82%; task-completions per million tokens rise from 54.9 to
92.0"*, and *"**On this workload the orchestration layer moved cost per task more than the
full spread of the model menu did.**"*

**How much to discount.** Three reasons for caution: (i) the paper benchmarks **Writer's own
harness** against a generic loop, a clear conflict of interest; (ii) **n = 6** for an r=0.99
claim, so the correlation is estimated from six points and is fragile to any single model;
(iii) the authors themselves call the aggregate quality delta *"directional at this sample
size"* (0.78 -> 0.81), which means the *levels* driving the correlation are individually
noisy. Treat "harness leverage" as a named hypothesis with one supporting measurement, not a
law. But it is the single most direct challenge to the inverse hypothesis, it is a controlled
model-held-constant swap, and it spans six models from five vendors.

#### 4.2.2 Harness Updating Is Not Harness Benefit (2605.30621) — inverted U, not inverse

**Confidence: MODERATE.** The most useful *correction* to the hypothesis. It decomposes the
question into two distinct capabilities.

Verbatim:

> "We analyze two harness self-evolution capabilities: (i) **harness-updating**, the
> capability to produce useful persistent harness updates from execution evidence; (ii)
> **harness-benefit**, the capability to benefit from updated harnesses during task solving.
> Our analysis reveals two findings. First, **harness-updating is flat in base capability:
> models from different capability tiers produce harness updates that lead to surprisingly
> similar gains; even Qwen3.5-9B's updates yield gains comparable to those of Claude Opus
> 4.6.** Second, **harness-benefit is non-monotonic in base capability: weak-tier models
> benefit little from updated harnesses, mid-tier models benefit most, and strong-tier
> models benefit less than mid-tier.**"

The mechanism for the weak-tier shortfall, verbatim: *"We trace low gains at the weak tier to
two failure modes: **weak-tier models may fail to activate relevant harness artifacts, or
activate them but fail to follow them faithfully.**"*

**Why this matters more than it looks:** it establishes that *benefiting from a harness is
itself a capability* — specifically harness invocation plus long-horizon instruction
following. That is why the curve is an inverted U rather than a downward slope: the weakest
models cannot cash in the scaffold at all. Their own recommendation: *"invest capability
budget in the task-solving agent rather than the evolver, and target harness invocation and
long-horizon instruction following in agent training."* That last clause is a direct
training-target recommendation for anyone doing harness-specific training.

Code released: `github.com/A-EVO-Lab/a-evolve/tree/release/harness-evolution`.

#### 4.2.3 It's Not the Capability: Harness Sensitivity Is Non-Monotone Across LLM Agent Tiers (2605.26731) — tests the hypothesis by name

**Confidence: MODERATE for the refutation, WEAK for the specific magnitudes** (one model per
tier, self-flagged; see §7.7).

This paper states the hypothesis in exactly the terms posed in this lane's brief, verbatim:

> "A prevalent assumption in LLM agent deployment holds that more structured harnesses
> universally improve reliability, and that **higher-capability models need proportionally
> less structural guidance -- together implying a monotone inverse relationship between model
> capability tier and optimal harness complexity.**"

Design: *"a controlled **432-run experiment crossing six models across four capability tiers
with three harness conditions (light, balanced, strict) on HEAT-24**, a 24-task synthetic
benchmark with git-based workspace verification."*

Result, verbatim:

> "**Our results refute the monotone inverse relationship on two fronts. First, for the
> frontier chat model evaluated (Gemini 2.5 Flash), increased harness verbosity lowers VTSR
> by 29-38 percentage points -- a harness-complexity paradox. Second, for the frontier
> reasoning model evaluated (Qwen3.5-122B, extended thinking enabled), strict harness
> achieves the highest VTSR (91.7%) and the lowest latency, the opposite of the prediction.
> Within the constrained tier, a 2B model (Gemma4:e2B) matches strong-open-tier stability at
> 91.7% across all harnesses.**"

Their identified mediator is **model type, not capability tier**, verbatim: *"harness
sensitivity appears non-monotone across the models evaluated, and **depends critically on
model type (chat vs reasoning)**."*

Failure taxonomy (six labels), verbatim: *"**`format_violation` dominates capable-model
failures while `wrong_file` dominates low-capability failures**"* — i.e. strong and weak
models fail for structurally different reasons, so a single scaffold cannot have a single
capability-indexed value.

Their own caveat, verbatim: *"**Because each tier is represented by a single model in this
study, these results should be interpreted as model-specific observations.**"*

#### 4.2.4 More Is Not Always Better: Cross-Component Interference (2605.05716) — components that hurt the weak model HELP the strong one

**Confidence: MODERATE** — rigorous design, narrow model coverage.

Design: full-factorial over **all 2^5 = 32 subsets** of five scaffolding components (planning,
tools, memory, self-reflection, retrieval) on HotpotQA and GSM8K with **Llama-3.1-8B and
70B**, 96 conditions, up to 10 seeds.

Headline: *"**The All-In system is consistently suboptimal**: on HotpotQA, a single-tool agent
surpasses All-In by 32% (F1 0.233 vs 0.177, p=0.023); on GSM8K, a 3-component subset beats
All-In by 79% (0.43 vs 0.24, p=0.010)."*

**The AGAINST quote, verbatim:** *"**Optimal component count is task-dependent (k*=1-4) and
scale-sensitive: at 70B, combinations that hurt at 8B provide gains, though All-In still
trails the best subset.**"*

That is the inverse hypothesis run backwards: scaffold *composition* that damaged the smaller
model became beneficial at 10x the scale. Methodological rigor: main-effects regression
R^2=0.916, adj-R^2=0.899, LOOCV=0.872; exact Shapley values; **183/325 (56.3%) submodularity
violations, "showing greedy selection is unreliable"**. Replicates across model families
(Qwen2.5) and is robust to prompt paraphrasing. A three-body synergy among Tool Use,
Self-Reflection and Retrieval (INT_3=+0.175, 95% CI [+0.003, +0.351]) is reported as
exploratory.

Practical consequence they draw: *"maximally-equipped agent defaults should be replaced by
task-specific subset selection via interaction-aware analysis."*

#### 4.2.5 Frontier models still take large harness gains

- **JIT-Agent** (2608.25593): *"Equipped with JIT-Agent as a harness helper, DeepSeek-V4-Flash
  surpasses GPT-5.6 on DeepSearchQA (+9.1) and OdysseyBench (+4.3), while the **already
  strong GLM-5.2 gains up to +20.2 points**."* And: *"**Agent capability is not determined by
  the model alone. The agent harness ... can dominate the contribution of the underlying
  foundation model.**" It closes by calling harness intelligence *"a trainable, transferable,
  and compounding dimension of agent capability **orthogonal to model scaling**."*
- **icat-agent** (2606.25514): with the strongest available backbone, *"**icat-agent
  +GPT-5.4-xhigh resolves 67.4% of SWE-bench Pro problems, outperforming the current best
  result on SWE-bench Pro (59.10%, mini-swe-agent+GPT-5.4-xhigh) by 8.3 percentage
  points**."* Same backbone, +8.3 pp from scaffold alone, at the frontier. Against Claude Code
  on identical models: *"improving by 3.6-8.4% on SWE-bench Verified and 6.3-18.5% on
  SWE-bench Pro"* while *"reducing the average cost by $1.18 per instance"*. Their framing:
  *"a robust scaffold such as icat-agent **unlocks substantial latent capability within a
  fixed model**."*
- **Recursive Agent Harnesses** (2606.13643): *"With the backbone held fixed at GPT-5 to match
  the published Codex and RLM baselines, **RAH improves the Codex coding-agent baseline from
  71.75% to 81.36% on Oolong-Synthetic** (199 samples, 13 context-length buckets up to 4M
  tokens), **a gain attributable to the harness rather than the model. With a stronger
  backbone, Claude Sonnet 4.5, the same design reaches 89.77%.**" The harness gain did not
  shrink when the backbone got stronger.
- **LCM: Lossless Context Management** (2605.04050): *"a deterministic architecture for LLM
  memory that **outperforms Claude Code on long-context tasks**. When benchmarked using Opus
  4.6, our LCM-augmented coding agent, Volt, achieves higher scores than Claude Code on the
  OOLONG long-context eval, **including at every context length between 32K and 1M tokens**."*
  Frontier model, harness swap, uniform win.
- **VISTA / state proprioception** (2606.30005): *"**frontier language models are
  proprioceptively blind to their own context**"* — a training-free interface layer lifts
  Gemini-3-Flash from 22.7% to 50.7% on LOCA-Bench, and *"Gains grow with context pressure and
  transfer across backbones."* Gain indexed to **context pressure**, not capability.
- **HarnessBridge** (2606.12882): a *learned* harness controller that *"matches or surpasses
  strong specialized harnesses while substantially reducing token usage and trajectory
  length, and **generalizes from smaller generators to larger commercial models**."*

#### 4.2.6 The Binding Constraint Thesis (2605.23950)

Asserts the frontier-regime opposite of the inverse hypothesis. Verbatim:

> "This position paper argues that, **for long-horizon tasks evaluated across models with
> comparable frontier capability, the agent execution harness ... is often a stronger
> determinant of agent performance than the model it wraps.** We formalize and defend the
> **Binding Constraint Thesis**: in this regime, **performance variance is governed more by
> harness configuration than by model choice**, and current evaluation protocols therefore
> systematically misattribute harness-level gains to model improvements."

Support offered: a control-theoretic formalization (harness as controller, LLM as stochastic
policy), plus *"published benchmarks, industry deployments, and a controlled variance
decomposition [that] show that harness-induced variance can substantially exceed
model-induced variance, **including cases of model ranking reversal**."*

**Confidence: SPECULATIVE.** Position paper, no new primary experiment beyond the variance
decomposition, and part of the source cluster flagged in §7.7. Included because it is the
cleanest statement of the anti-inverse position and because "Binding Constraint Thesis" is a
searchable handle.

#### 4.2.7 Non-monotonicity even among tiny models (2605.12129)

**It's Not the Size: Harness Design Determines Operational Stability in Small Language
Models.** Three harness conditions (model-only raw prompt / minimal-shell wrapper tags /
4-stage plan->execute->verify->recover pipeline) x three 2-3B models (Gemma4 E2B, Qwen3.5:2B,
LLaMA 3.2 3B) x 24 tasks.

Verbatim: *"The pipeline harness achieves **TSR=0.952 and VTSR=1.000 on Gemma4 E2B** (T1-T5,
21 tasks). **A non-monotonic phenomenon - minimal-shell TSR < model-only TSR - is observed in
two models.** In LLaMA 3.2 3B model-only, seven format violations yield TSR=0.429, revealing
**scaffold collapse**: the model abandons JSON structure under complex format requirements
without harness support. Ablation shows planning and recovery each contribute approximately
24.7% of total gain. VCR (Verification Catch Rate)=0.625 across all pipeline runs."*

Relevant twice over: (i) non-monotonicity in *harness complexity* appears even within a
single tiny-model tier, so "more structure" is not monotone in either variable; (ii) a 2-3B
model reaching VTSR=1.000 under a 4-stage pipeline is the strongest single datapoint for
"scaffolding substitutes for capability" — which, if it generalized, would be the inverse
hypothesis's best evidence. Confidence: WEAK (24 tasks, 3 models, source cluster §7.7).

### 4.3 Also relevant: the harness-complexity-vs-cost axis

Several papers find the accuracy effect of harness choice is small at fixed strong models
while the *cost* effect is enormous. This is the shape that keeps recurring and it is probably
the real answer:

- **Scaffold Effect** (2607.22585): *"**up to a 40x difference in tokens per solved task,
  while paired within-model pass-rate differences remain 0-8 percentage points**"* (CIs mostly
  include zero). Models were Qwen 3.6 Plus and MiniMax M2.5.
- **The Scaffolding Matters More Than the Interface** (2608.08654): seven scaffoldings x five
  models x one fixed six-operation git task, verified by inspecting repository state rather
  than trusting self-reports. *"**The dominant effect was the scaffolding.**"* Two of seven
  scaffoldings ship no MCP support, completed every run over CLI, and *"were **5.0x to 28x
  cheaper** than the five scaffoldings that do support MCP."* And on the capability axis:
  *"**The effect was largest for a small 27-billion-parameter model running locally, whose
  cost varied 139x across scaffoldings while it completed the task under all of them.**"*
  Note what that says: the weak model completed the task under *every* scaffolding — the
  scaffold changed its **cost by 139x**, not its success. Also: *"**Agents frequently ignored
  the interface they were assigned**, so comparisons that do not verify actual behaviour
  measure an unknown mixture."*
- **The Harness Effect** (2607.06906): 41% cost, 44% latency, 38% tokens, quality at parity.
- **2609.20804**: ~30-32% cost reduction from planning at the strong tier, with -0.4 to -2.0 pp
  accuracy.

### 4.4 The defensible narrow version

The monotone inverse claim does not survive. What the evidence collectively supports:

**1. Gain tracks defect mass, not capability.**
Sources: 2608.10178 (*"where defect mass is near zero, and gain is near zero"*), 2609.20804
(planning removes premature termination, which only the 30B model has; failure profiles
differ by tier), 2605.26731 (`format_violation` vs `wrong_file` split by tier).
Capability predicts harness gain only insofar as it predicts defect mass — and defect mass is
*also* driven by the task ecosystem (2608.10178's disjoint language machinery) and by context
pressure (2609.20804, 2606.30005), which is why the capability correlation is weak and
sign-unstable.

**2. Gain does not vanish at the frontier; it changes currency from accuracy to cost.**
Sources: 2609.20804 (~30-32% cost cut, -0.4/-2.0 pp accuracy at the strong tier),
2607.06906 (41% cost / 44% latency / 38% tokens, quality at parity), 2607.22585 (40x tokens
per solved task, 0-8 pp accuracy), 2608.08654 (139x cost spread on a task the weak model
solved under every scaffolding). If you measure scaffold value only in pass rate, you will
conclude the inverse hypothesis is true at the frontier; measure in cost or latency and it is
false.

**3. Benefiting from a harness is itself a capability, so the curve is an inverted U.**
Source: 2605.30621 (*"weak-tier models benefit little ... mid-tier models benefit most ...
strong-tier models benefit less than mid-tier"*; weak-tier failure modes are failing to
activate harness artifacts, or activating them without following them faithfully). Corroborated
by 2609.09134 (weak model given an expert's planning strategy *"without the competence to
execute it"* regresses 4-30 points) and DCAS §2.7 (Sonnet 4.5 out-plans Opus 4.5 for a 30B
executor because Opus's plans *"implicitly assume a level of reasoning that a 30B executor"*
lacks).

**4. Model *type* mediates more strongly than model *tier*.**
Source: 2605.26731 — the frontier *reasoning* model took the **strictest** harness best
(highest VTSR 91.7%, lowest latency), while the frontier *chat* model lost 29-38 pp to the
same verbosity. Corroborated at the prompt level by 2411.02093 (built-in reasoning reduces the
impact of complex prompts).

**5. Component *kind* determines the sign.**
- **Compensation-type** components (predefined tool sets, format enforcement, plan scaffolds
  that prevent premature termination, deterministic offloading) shrink toward zero as
  capability rises. Sources: 2609.20804 (4), 2608.12307, 2608.10178.
- **Leverage-type** components (context engineering, recursive/parallel decomposition,
  verification loops, cache-shape discipline) can scale **with** capability. Sources:
  2607.06906 (r=0.99), 2605.05716 (8B->70B sign reversal), 2606.13643 (recursion: GPT-5
  71.75->81.36, Sonnet 4.5 -> 89.77), 2605.04050, 2608.25593 (+20.2 on already-strong GLM-5.2).

**6. Harness *insensitivity* is bought with multi-harness training data, not with capability.**
Sources: Qwen3-Coder-Next Table 3 (the 80B multi-harness-trained model has the smallest spread
in the table, 0.7 pp, smaller than Opus 4.5's 1.2 pp), DCAS Table 1 (Qwen3-32B-Nex-N1,
*"[t]rained on diverse multi-format trajectories ... not a single scaffold"*, closes the
OH->CC gap entirely, 50.5 vs 50.8). This is the single most actionable finding in the lane.

**What nobody has measured:** a properly powered scaffold-delta-vs-capability curve. Every
study is underpowered on this exact axis — see §7.5.

---

## 5. Q4: Terminology sweep and productive search terms

### 5.1 The term of art is "agent harness", and it is new

`all:"agent harness"` returns a dense, on-topic, almost entirely-2026 field. There is now
even a definitional paper: **What makes a harness a harness: necessary and sufficient
conditions for an agent harness** (2606.10106), which diagnoses the polysemy directly,
verbatim:

> "The usage is loose and polysemous. **Sometimes the term denotes the whole product (Claude
> Code, Codex CLI); sometimes it denotes the evaluation scaffold that runs an agent against
> tasks (the SWE-bench harness); sometimes it gets conflated with an agent framework, an SDK,
> an IDE plugin, or an orchestrator.**"

It traces the genealogy *"from the horse's tack to the classic test harness, to the
machine-learning evaluation harness, and finally to the agent harness"*, proposes an
inclusion/exclusion test, and applies it to *"six real harnesses (**Claude Code, Codex CLI,
Aider, Cline, OpenHands, and SWE-agent**)"*.

**Practical warning from this:** "harness" is ambiguous between *the product*, *the eval
scaffold*, and *the middleware layer*. When searching, expect all three senses; when writing,
disambiguate.

Working definition used across the field (from 2607.03691): *"agent harness: **a middleware
layer in between a developer and a large language model that orchestrates system prompts, tool
execution, context management, and iterative reasoning loops**."*

### 5.2 Productive arXiv API queries (ranked by yield on this topic)

| Query (arXiv `search_query=`) | Yield |
|---|---|
| `all:"agent harness"` | **best single query**; surfaces essentially the whole 2026 field |
| `abs:"harness" AND abs:"capability" AND abs:"gain"` | found the entire inverse-capability cluster (2605.30621, 2607.06906, 2608.12307, 2609.01437, 2608.25593, 2609.04280, 2608.09096) |
| `abs:"harness" AND abs:"reinforcement learning" AND abs:"coding agent"` | found LEGO-RL |
| `abs:"agentic reinforcement learning" AND abs:"harness"` | found HASE, 2609.04518 |
| `abs:"harness-conditioned"` | found HarnessForge, **2605.26731**, 2605.12129 (high-precision, low-volume) |
| `all:"multi-harness training"` | found HarnessBandit (one hit, exactly on target) |
| `abs:"scaffold-specific"` | found DCAS |
| `abs:"model capability" AND abs:"scaffold"` | found DCAS, 2609.09218, 2607.08774 |
| `all:"trained in the harness"` | found Ecdysis, NeoHorse-1, ForgeTrain |
| `abs:"scaffolding" AND abs:"weaker models"` | found 2609.09134, 2608.12307, 2609.20804 |
| `all:"native harness"` | found **2609.11987** (Harness or Model?), HarnessOpt-Bench, CORAL |
| `abs:"co-design" AND abs:"harness" AND abs:"model"` | found Macaron-V1 |
| `abs:"SWE-agent" AND abs:"scaffold" AND abs:"transfer"` | found One Recipe, Many Harnesses |

### 5.3 Coined terms worth grepping for

Each of these is a distinct handle into a sub-literature:

- **cross-scaffold deployment gap** / **cross-scaffold transfer** (DCAS 2608.06113,
  Qwen3-Coder-Next 2603.00729) — the harness-overfitting phenomenon itself
- **harness-native RL** (LEGO-RL 2608.17393) / **harnessed agentic RL** (Agent Lightning
  2608.17528) — the "harness participates in post-training" paradigm
- **explicit planning** vs **implicit planning** (DCAS) — the two senses that come apart in
  training data
- **harness leverage** (2607.06906) — gain positively correlated with baseline strength
- **harness-benefit** vs **harness-updating** (2605.30621) — the two-capability decomposition
- **model-harness fit** (2609.09134); **model-harness pairs** / **Model-Harness Co-design**
  (Macaron-V1 2608.09819); **harness-conditioned policy alignment** (HarnessForge 2606.01779)
- **harness sensitivity**, **harness-complexity paradox** (2605.26731)
- **scaffold effect** (2607.22585), **the harness effect** (2607.06906), **Binding Constraint
  Thesis** (2605.23950)
- **de-scaffolding**, **double measurement confound** (2609.09218)
- **scaffold collapse** (2605.12129)
- **cross-component interference (CCI)** (2605.05716)
- **agent-native models** (NeoHorse-1 2609.08183); **agent-native RL** (MiniMax-M2 2605.26494)
- **harness recursion** / **Recursive Agent Harness (RAH)** (2606.13643)
- **code as agent harness** (2605.18747, survey)
- **harness evolution** / **self-evolving harness** — the largest adjacent subfield
- **Natural-Language Agent Harness (NLAH)** (2603.25723) — harness policy as an editable
  natural-language document

### 5.4 Dead ends (searched, low or zero yield)

| Term | Outcome |
|---|---|
| `abs:"agent-environment interface"` | almost entirely classical RL, 2017-2022. One relevant hit: HarnessBridge (2606.12882). Not a productive handle for this topic. |
| "inference scaffold", "inference-time architecture" | near-zero. The closest was **inference-time control** (CogniConsole, 2607.08774): *"Reliability in large language model (LLM) systems is typically framed as a function of model capability. We challenge this by demonstrating that reliability is significantly influenced by **inference-time control**."* |
| `abs:"harness identity" OR abs:"harness token"` | zero relevant hits. See §7.3. |
| `abs:"harness-conditioned"` alone | high precision but the top hit is a 2005 math paper on quadratic harnesses |
| `all:"harness-specific"` | low yield as a literal phrase, and heavily polluted by **human activity recognition (HAR)** papers |
| `all:"harness gap"` | zero hits |
| "scaffolding ablation" as a literal phrase | unproductive; the ablation work is titled differently (AgentSpec, 2609.20804, 2605.05716) |
| `all:"harness diversity"` | zero relevant; drags in RF/antenna and disaster-prediction papers |
| "agent framework" | too generic to be useful |
| `abs:"scaffold"` / `abs:"scaffolding"` alone | badly polluted by **education** (self-regulated learning scaffolds, parent-child tutoring) and **biomaterials** (tissue/hydroxyapatite scaffolds) |
| `abs:"scaffold" AND abs:"overfit"` | almost nothing on-topic; mostly molecular-generation papers |
| `abs:"prompt engineering" AND abs:"stronger models" AND abs:"gains"` | zero hits |

### 5.5 Useful non-obvious search move

Follow the **reference lists of the harness-design papers**, not the keywords. 2609.20804's
bibliography alone surfaced 2608.26218, 2605.05716, 2604.03515, 2603.00729, 2604.02547 and
2411.02093 — several of which no keyword query I tried had returned. With Semantic Scholar
down (§7.2), parsing the HTML reference list of one good paper was the highest-yield discovery
method available.

---

## 6. Full source list

### 6.1 Full text retrieved and parsed

| Source | What it contained | Local extract |
|---|---|---|
| `arxiv.org/pdf/2608.06113v1` (DCAS) | Table 1 cross-scaffold grid, RQ1-RQ3 numbers, threats to validity, ACM DOI | `/tmp/dcas.txt2` |
| `arxiv.org/html/2609.20804v1` (Harness Design) | Planning/tool/context ablations per model, Figures 6-8, Tables 5/6/11, full reference list | `/tmp/hd.html` |
| `arxiv.org/html/2608.17393v1` (LEGO-RL) | Limitations (no cross-harness test), per-harness numbers, related-work table | `/tmp/lego.html` |
| `arxiv.org/html/2603.00729v1` (Qwen3-Coder-Next) | Figure 3 cross-scaffold text, Table 3 per-harness scores, six-framework trajectory list, reward-hacking blocker | `/tmp/qcn.html` |
| `openai.com/index/introducing-upgrades-to-codex/` | GPT-5-Codex harness-restriction statement, token-budget figures | — |
| `openai.com/index/introducing-codex/` | codex-1 training description, "without custom scaffolding" claim | — |
| `anthropic.com/engineering/claude-code-best-practices` | Harness usage guidance; **no** harness-specific-training claim | — |
| `anthropic.com/news/claude-sonnet-4-5` | Agentic capability + alignment; **no** harness-specific-training claim | — |

Helper scripts used: `/tmp/axq.py` (arXiv Atom query -> compact index), `/tmp/ss.py`
(Semantic Scholar, non-functional, see §7.2).

### 6.2 Abstracts retrieved

Every ID below was fetched through the arXiv `id_list` endpoint, which returns entries only
for papers that exist. **No ID in this report is unverified.**

**Core (harness-specific training / transfer):** 2608.06113 (DCAS), 2608.17393 (LEGO-RL),
2609.04518 (Multi-Harness RL credit assignment), 2609.13739 (HarnessBandit),
2605.24220 (Polar), 2608.17528 (Agent Lightning v1.0), 2603.00729 (Qwen3-Coder-Next),
2609.00865 (MemoryWalker), 2606.01779 (HarnessForge), 2607.03935 (HASE),
2609.09134 (Co-Evolving Harnesses and Models), 2608.10178 (One Recipe, Many Harnesses),
2509.23045 (Kimi-Dev), 2504.21798 (SWE-smith), 2412.21139 (SWE-Gym),
2511.16108 (SkyRL-Agent), 2604.00824 (Yet Even Less Is Even Better),
2609.05576 (EnvCraft), 2609.16096 (Coaching Qwen3 Coder 30B).

**Inverse-capability:** 2609.20804 (Harness Design), 2608.12307 (AI4AI at Test-Time),
2605.30621 (Harness Updating Is Not Harness Benefit),
2605.26731 (It's Not the Capability), 2605.12129 (It's Not the Size),
2607.06906 (The Harness Effect), 2605.05716 (More Is Not Always Better),
2411.02093 (Do Advanced LMs Eliminate Prompt Engineering), 2403.02419 (Are More LLM Calls All
You Need), 2407.01489 (Agentless).

**Harness effect / evaluation validity:** 2609.11987 (Harness or Model?),
2608.06301 (HarnessOpt-Bench), 2609.01437 (HarnessDev), 2608.25593 (JIT-Agent),
2609.11677 (Ecdysis), 2608.19013 (Harness Continual Learning),
2609.04280 (EvoHarnessBench), 2608.09096 (Evo-Bench), 2607.13683 (HarnessBank),
2605.23950 (Stop Comparing LLM Agents), 2607.22585 (The Scaffold Effect),
2608.08654 (Scaffolding Matters More Than the Interface),
2607.03691 (Don't Blame the LLM), 2608.26218 (Same Model, Different Harness),
2609.09218 (Double Measurement Confound), 2605.21404 (Twelve Benchmark Papers),
2609.04298 (Harbor Adapters), 2604.02547 (Beyond Resolution Rates),
2604.00594 (Agent psychometrics).

**Definitional / taxonomic / survey:** 2606.10106 (What makes a harness a harness),
2604.03515 (Inside the Scaffold), 2606.14674 (AgentSpec), 2605.18747 (Code as Agent Harness),
2603.25723 (Natural-Language Agent Harnesses), 2606.12882 (HarnessBridge),
2606.13643 (Recursive Agent Harnesses), 2607.11423 (ToFu).

**Lab tech reports:** 2605.26494 (MiniMax-M2), 2507.20534 (Kimi K2), 2602.02276 (Kimi K2.5),
2508.06471 (GLM-4.5), 2608.09819 (Macaron-V1), 2609.08183 (NeoHorse-1).

**Scaffold-as-substitute / context:** 2606.25514 (icat-agent), 2605.04050 (LCM),
2606.30005 (VISTA / state proprioception), 2508.21433 (The Complexity Trap),
2602.05302, 2607.08774 (CogniConsole), 2609.02730 (CORAL), 2511.13646 (Live-SWE-agent),
2506.23667 (L0), 2509.01684 (RL for MLE agents).

### 6.3 Confidence summary by finding

| Finding | Confidence | Why |
|---|---|---|
| Harness-overfitting exists and is fine-tuning-induced (DCAS) | **STRONG** | ASE '26 peer-reviewed, full grid, base-model control, logs released |
| The specific 52.6 -> 8.4 collapse | **STRONG** as a measurement, **but** authors attribute it to tool-call format incompatibility, so do not read it as loss of deep capability | their own explanation |
| Cross-scaffold transfer is limited (Qwen3-Coder-Next) | **STRONG** | independent frontier lab, reported against its own interest, acted on |
| Evaluation harness dominates training recipe (4.3x vs 1.16) | **MODERATE-TO-STRONG** | 24,000 sealed evals, seeds reported; one 8B model |
| Planning transfers as a structural skill (DCAS RQ3) | **MODERATE** | small gains (+3.4/+7.0), one 30B backbone, one benchmark |
| Cross-paradigm skill priors transfer (Kimi-Dev) | **STRONG** | clear result, open model, replicated framing in DCAS related work |
| Imitation can destroy model-harness fit (-4 to -30 pts) | **MODERATE** | 7 tasks, 2 model families; clean control (helps under unevolved harness) |
| GPT-5-Codex is harness-scoped | **STRONG** | primary vendor source, explicit restriction |
| Anthropic trains Claude for Claude Code | **UNKNOWN / NOT FOUND** | see §7.1; negative is incomplete |
| Vendor-native pairing gives no average advantage | **MODERATE** | paired contrasts, 792 graded runs, CIs span zero |
| Repo-vs-contest stratification (-9.0 / +23.7 pp) | **SPECULATIVE** | post hoc partition, authors say so |
| Planning: accuracy scaffold (weak) -> cost saver (strong) | **STRONG** | 176 matched settings, 4 models, McNemar+BH, mechanism traced |
| Weaker targets get largest harness gains (AI4AI) | **MODERATE** | one task family; gains via format enforcement + benchmark-specific routing |
| Gain tracks defect mass | **MODERATE-TO-STRONG** | stated in 2608.10178, mechanistically corroborated in 2609.20804 |
| "Harness leverage": gain correlates +0.99 with baseline strength | **MODERATE, discount for COI** | vendor's own harness, n=6, quality delta "directional" |
| Harness-benefit is non-monotone (inverted U) | **MODERATE** | clean two-capability decomposition, code released |
| Monotone inverse relationship is refuted | **MODERATE** | 2605.26731 tests it directly but has n=1 per tier; corroborated by 2605.05716 and 2607.06906 |
| Components that hurt at 8B help at 70B | **MODERATE** | rigorous factorial (R^2=0.916, Shapley), only 2 scales / 1 family |
| Harness insensitivity comes from multi-harness training data | **MODERATE** | two independent tables (Qwen Table 3, DCAS Nex-N1) pointing the same way |
| Harness churn > 2 releases/day | **STRONG** | 2607.03691, direct repo measurement, 35 sequential releases evaluated |

---

## 7. Known gaps and negative results

### 7.1 No Anthropic public claim of Claude Code-specific training (NEGATIVE, INCOMPLETE)

Searched:
- arXiv `abs:"Claude Code" AND abs:"training"` — 10 hits, none from Anthropic. The on-topic
  ones (MemoryWalker 2609.00865, LEGO-RL 2608.17393, Polar 2605.24220) are third parties
  training *other* models inside the Claude Code harness.
- Fetched `anthropic.com/engineering/claude-code-best-practices` — about harness *usage*
  (context-window management, "give Claude a way to verify its work"). No training claim.
- Fetched `anthropic.com/news/claude-sonnet-4-5` — agentic capability, partner quotes
  (GitHub Copilot: *"we went from 9% error rate on Sonnet 4 to 0% on our internal code
  editing benchmark"*), alignment. No harness-specific training claim.

**This negative is incomplete.** I did not retrieve the Claude 4 / Sonnet 4.5 / Opus 4.5
system-card PDFs, nor `anthropic.com/docs/en/how-claude-code-works`, nor Anthropic's
engineering posts on building agents. Those are the likeliest homes for such a statement.
**Recommended follow-up: fetch the system cards directly.** Note that one Anthropic-authored
paper *was* found doing production-RL research (2511.18397, *Natural Emergent Misalignment
from Reward Hacking in Production RL*, which trains *"on a selection of real Anthropic
produc[tion RL environments]"*), which confirms Anthropic publishes about its production RL
environments — just not, in what I retrieved, about harness-coupling.

### 7.2 Semantic Scholar: total blackout (HTTP 429)

Five attempts, all failed:
1. bare `curl` to `api.semanticscholar.org/graph/v1/paper/search` -> `HTTP Error 429`
2. same after a 20s backoff -> 429
3. same after a 45s backoff, two queries -> 429, 429
4. with an explicit `User-Agent: research-agent/1.0` header -> `curl: (56) ... error: 429`
5. proxied through `r.jina.ai` -> body returned: *"Too Many Requests. Please wait and try
   again or apply for a key for higher rate limits.
   https://www.semanticscholar.org/product/api#api-key-form"*

**Consequences for this report:**
- No citation-count ranking, so I could not sort by impact or identify the canonical papers
  by citation volume.
- No citation-chain following by impact (the brief asked for this explicitly).
- **No non-arXiv venues.** Work published only in ACM/IEEE proceedings is invisible here
  except where an arXiv preprint cites it. 2411.02093 (TOSEM 35(8)) and DCAS (ASE '26) are
  visible only because they have arXiv preprints.
- Cannot rule out that a non-arXiv paper already answers a question I marked as a gap.

**Fix: obtain a Semantic Scholar API key** and re-run. This is the single largest
methodological hole in the lane.

### 7.3 Nobody conditions a model on harness identity as an explicit input (RESEARCH GAP)

Searched `abs:"harness-conditioned"` (6 hits, one relevant) and
`abs:"harness identity" OR abs:"harness token"` (1 hit, irrelevant — a DeAI governance paper).

The closest existing work is **HarnessForge** (2606.01779), which does *"harness-conditioned
policy alignment"* — but it conditions the *training procedure* on the harness, not the model's
*input*. There is no harness-ID token, no harness embedding, no system-prompt harness
descriptor that the policy is trained to read. Given that 2609.04518 showed the GRPO advantage
signal *already implicitly encodes harness identity* (+4.48 pp above a shuffled-label baseline
for an out-of-fold classifier), making that conditioning explicit looks like an obvious
unexplored move.

### 7.4 No frontier-lab train-A / eval-B matrix

The only clean cross-harness training-transfer experiments are:
- **DCAS** (2608.06113) — 30B backbone, academic/Huawei, publishes the grid
- **2609.04518** — 8B backbone, academic, publishes the held-out-harness result
- **Qwen3-Coder-Next** (2603.00729) — frontier lab, but reports the finding in one figure
  caption and does not release the transfer grid
- **LEGO-RL** (2608.17393) — production-scale (35B MoE, three real harnesses) but explicitly
  did not test transfer

Nobody at frontier scale has published a full "train on harness A, evaluate on harnesses
A/B/C/D" matrix.

### 7.5 The inverse-capability question has no adequately powered study

Every relevant paper is underpowered on the capability axis:

| Paper | Capability-axis power | Self-flagged? |
|---|---|---|
| 2605.26731 (tests the hypothesis by name) | **1 model per tier**, 4 tiers | yes, explicitly |
| 2607.06906 ("harness leverage", r=0.99) | **n=6**, vendor's own harness | partially ("directional at this sample size") |
| 2609.20804 (best design) | 4 models, 2 families (3x Nemotron-3 + 1 Mistral) | no |
| 2605.05716 (factorial) | **2 scales, 1 family** (Llama-3.1 8B/70B), + Qwen2.5 replication | no |
| 2605.30621 (inverted U) | tiers described but per-tier n not stated in abstract | no |
| 2608.12307 (weakest gain most) | 1 task family (Theory of Mind) | no |

**Nobody has run** >=3 models per capability tier x >=3 tiers x a fixed component ablation.
Until someone does, every claim about the *shape* of scaffold-gain-vs-capability, including
mine in §4.4, is under-determined.

### 7.6 Domain coverage is thin outside coding

Scaffold-delta-across-capability data exists for: coding (2609.20804, 2607.06906),
Theory-of-Mind (2608.12307), multi-hop QA + math (2605.05716), enterprise tasks (2609.09134),
small-model CLI tasks (2605.12129). **Nothing found** with a capability axis for computer-use /
GUI agents, deep research, or long-horizon tool use. (Embodied scaffolds are covered
compositionally by AgentSpec 2606.14674 across DeliveryBench / ALFRED / MiniGrid / RoboTHOR —
with the relevant finding that *"RL-trained policies compose best when optimized with
deployment-time scaffold structure"*, which is a harness-conditioned-training claim for
embodied agents — but not on a capability axis.)

### 7.7 Source-quality warning on a cluster of 2026 preprints

A group of the preprints cited here share a distinctive signature: self-similar titles, position-paper
framing, apparent single or very small authorship, no identifiable lab affiliation, and no peer
review. Specifically:

**2605.23950** (Stop Comparing LLM Agents Without Disclosing the Harness), **2605.26731** (It's
Not the Capability), **2605.12129** (It's Not the Size), **2607.22585** (The Scaffold Effect),
**2608.26218** (Same Model, Different Harness), **2605.21404** (What Twelve LLM Agent Benchmark
Papers Disclose), **2606.10106** (What makes a harness a harness), **2608.08654** (The
Scaffolding Matters More Than the Interface), **2607.06906** (The Harness Effect — plus a vendor
COI), **2606.13643** (Recursive Agent Harnesses), **2605.04050** (LCM — vendor claim vs Claude
Code).

**Treat these as hypothesis generators and terminology sources, not as established results.**
Several are internally careful (2605.26731 flags its own n=1-per-tier; 2608.08654 verifies
repository state rather than trusting agent self-reports; 2609.11987 corrects its own prior
manuscript), which is to their credit — but none has external replication.

**The load-bearing claims in this report deliberately rest instead on:**
- **2608.06113** (DCAS) — ASE '26, ACM DOI 10.1145/3832783.3834485
- **2603.00729** (Qwen3-Coder-Next) — Qwen/Alibaba technical report
- **2608.17393** (LEGO-RL) — Huawei
- **2608.17528** (Agent Lightning v1.0) — Microsoft
- **2609.20804** (Harness Design) — UMass Amherst / Emory / UNC Charlotte
- **2609.04518** (Multi-Harness RL) — sealed-oracle design, 24,000 evals
- **2411.02093** — ACM TOSEM 35(8)
- **2509.23045** (Kimi-Dev), **2412.21139** (SWE-Gym), **2504.21798** (SWE-smith) — established
  open-model work
- OpenAI's own product pages for the vendor claims

### 7.8 Read from abstract only (numbers not independently verified in full text)

2607.06906, 2605.30621, 2605.26731, 2608.12307, 2609.09134, 2609.11987, 2605.05716,
2608.10178, 2609.04518, 2605.24220, 2608.17528, 2608.25593, 2606.25514, 2606.13643,
2605.04050, 2606.30005, 2609.00865. Full text was read for DCAS, 2609.20804, LEGO-RL and
Qwen3-Coder-Next only.

### 7.9 Other unanswered questions

- **Is the DCAS effect present at frontier scale?** All the overfitting evidence is at 8B-35B.
  Qwen3-Coder-Next's Table 3 hints that stronger models have smaller spreads (§4.1.5), but
  confounded by training-data diversity.
- **Does harness-native RL transfer at all?** LEGO-RL did not test it; 2609.04518 says
  cross-harness *credit* buys no portability; DCAS says planning-aware SFT does transfer a
  little. These are not the same experiment and do not settle it.
- **What is the right harness-diversity mix?** Qwen3-Coder-Next used six harnesses and got the
  flattest spread in its own table; nobody has ablated *how many* or *which* harnesses are
  needed, or whether there is a diversity/peak-performance tradeoff (Qwen3-Coder-Next's peak
  per-harness score, 71.3, is below Opus 4.5's 79.0 — but it is an 80B-A3B model, so the
  comparison is not clean).
- **Cost of harness-specific training.** No paper reports the marginal cost of per-harness
  training vs multi-harness training vs harness-agnostic training. Polar's +0.6-to-+22.6
  spread implies the ROI varies enormously by harness, but nobody priced it.

---

## 8. Decision-relevant takeaways

1. **Harness-overfitting is the empirically established fact of this lane.** DCAS Table 1 is
   the citation: fine-tuned models diverge 27.8-44.2 pp across four scaffolds; their untrained
   base models diverge 13.6-21.0 pp. The clean, format-artifact-free number is **-8.4 pp**
   (OpenHands -> Claude Code for SWE-Lego-Qwen3-32B); the headline -44.2 pp collapse is a
   tool-call-format failure and should be quoted with that caveat.
2. **Buy harness-robustness with multi-harness training data, not with a bigger model.** Two
   independent tables say so (DCAS's Nex-N1 row; Qwen3-Coder-Next's Table 3, where the
   six-harness-trained 80B has a smaller spread than Opus 4.5). Qwen's own conclusion is that
   within-scaffold scaling works but cross-scaffold transfer does not, and the transfer is
   *asymmetric* (general -> specialized transfers better than the reverse).
3. **The inverse-capability hypothesis is false as stated and should be replaced by the
   defect-compensation version.** Gain tracks defect mass (2608.10178, 2609.20804), not
   capability; at the frontier the gain persists but converts from accuracy into cost
   (30-44% reductions across 2609.20804 / 2607.06906 / 2607.22585); benefiting from a harness
   is itself a capability so the curve is an inverted U (2605.30621); and model *type* (chat
   vs reasoning) mediates more strongly than model *tier* (2605.26731). Anyone planning work
   on the premise of a clean monotone inverse law should know that the one paper that tested
   it directly refutes it, and that "harness leverage" (2607.06906) reports a **positive**
   r=0.99.
