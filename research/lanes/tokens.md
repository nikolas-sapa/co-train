# What Makes an Agent Harness Token-Efficient — Measured, Not Claimed

Research lane report. Compiled 2026-09-19.

Every finding below is labelled **MEASURED (independent)** / **MEASURED (vendor)** / **CLAIMED (no measurement)** with a confidence rating. No conclusion appears without a source. All arXiv IDs were verified to resolve via the arXiv API `id_list` endpoint with matching titles.

---

## VERDICT

The central claim survives, but not in the form vendors state it.

1. Programmatic access to data does beat reading tool output as tokens — but the crossover is at roughly **26 concurrent calls in one turn**, not "always," and below it programmatic tool calling costs *more*.
2. The strongest independent end-to-end measurement finds **plain bash beats programmatic tool calling on both quality and cost**.
3. Anthropic's headline 98.7% figure has **no measurement behind it**, and the filesystem mechanism its post proposes is the one condition that measurably collapsed in independent testing (mean −32.0% accuracy under catalog flooding).
4. Anthropic's shipped context-compaction endpoint measures at **random-guess** on a set-membership retrieval task where a same-sized Bloom filter errs on a third.
5. Token count is not a valid proxy for cost: one controlled study cut delivered tool-output tokens 38.4% and **increased billed cost 6.8%** (Pearson r = 0.15 between token reduction and cost reduction).

---

# Q1. Programmatic tool calling vs conventional tool calling

## 1.1 The vendor claims

### Prime Intellect — CLAIMED (no measurement). Confidence: strong.

Verbatim from primeintellect.ai/blog/prime-agent:

> "Prime Agent saves tokens by programmatically running functions over data rather than spending tokens reading data using tools."

Supporting artifacts are ARC-AGI-3 score-vs-output-token and score-vs-estimated-cost scaling charts comparing **whole harnesses**. No ablation isolates programmatic tool calling (PTC) from the other simultaneous changes: Continual Harness, persistent subagents, the `/refine` self-improvement loop, and the persistent IPython kernel. The claim as stated is unmeasured.

Related vendor claim, same source (arXiv 2608.23552, "Prime Agent: A Self-Improving RLM Harness"): ARC-AGI-3 RHAE Best@1 raised **30% → 95.5%**. Same bundling problem.

### Anthropic — CLAIMED (no measurement). Confidence: strong.

From anthropic.com/engineering/code-execution-with-mcp:

> "This reduces the token usage from 150,000 tokens to 2,000 tokens—a time and cost saving of 98.7%."

This is a worked hypothetical about the cost of loading tool definitions upfront, not a benchmark run. There is no model named, no task set, no baseline harness, no n, no variance. The post's own mechanism examples (a 10,000-row spreadsheet filtered to 5 logged rows; a Slack polling loop) are illustrative code samples, not measurements.

To Anthropic's credit the post states its own cost honestly:

> "Running agent-generated code requires a secure execution environment with appropriate sandboxing, resource limits, and monitoring. These infrastructure requirements add operational overhead and security considerations that direct tool calls avoid."

### Cloudflare — CLAIMED (no measurement). Confidence: strong.

From blog.cloudflare.com/code-mode/ (2025-09-26): *"The results are striking"* — followed by **zero numbers in the entire post**. The argument is qualitative and mechanistic (LLMs have seen vast real-world TypeScript and only contrived synthetic tool-call traces; "Making an LLM perform tasks with tool calling is like putting Shakespeare through a month-long class in Mandarin and then asking him to write a play in it"). Plausible, unmeasured.

---

## 1.2 Independent measurement #1 — "Is Bash All You Need?"

**arXiv 2609.11999** (Microsoft Corporation + Carnegie Mellon University, submitted 2026-09-10). 13 pages, 7 figures, 12 tables.

The most decision-relevant paper found. Five tool interfaces held constant on model, task text, base prompt, and stopping criteria, with interface-specific prompts only for synthesis and PTC.

**Interfaces**: Tool-only (typed catalog), Bash+Tool, Bash (shell only), Bash+Synthesis (shell + persistent agent-authored tool directory), PTC (restricted Python program over the typed catalog, no shell or other action channel).

**Benchmarks**: TheAgentCompany (174 evaluated tasks; 4 self-hosted services, local workspace, 17 GPT-5-simulated coworkers over RocketChat; authors constructed a 60-tool typed catalog — 54 service + 6 workspace file tools — and patched coworker reliability defects uniformly across interfaces). APEX-Agents (all 480 tasks; investment banking, management consulting, corporate law; fixed June 2026 Archipelago snapshot with 9 MCP servers, 20 typed application tools, its code-execution server used as Bash).

**Models**: Claude Opus-4.8 and GPT-5.5, default reasoning levels.

**Grading**: TheAgentCompany uses the benchmark's Python checkpoint evaluators (effort-weighted checkpoint rate). APEX-Agents uses an Archipelago-derived LLM judge over rubric criteria, scoring the final response and workspace-file changes.

### Table 1 — full results (tokens are means/task in thousands; input includes cache-read; total = input + output; $/task at GitHub Copilot list rates)

| Interface | Model | Score (95% CI) | Pass rate | Input | Output | Cache-read | Total | $/task | Time/task |
|---|---|---|---|---|---|---|---|---|---|
| **TheAgentCompany** | | | | | | | | | |
| Tool-only | Opus-4.8 | 44.9% [38.7, 51.0] | 24.1% | 929k | 16k | 855k | 945k | $1.20 | 5.1m |
| Tool-only | GPT-5.5 | 45.3% [39.3, 51.3] | 25.3% | 458k | 7k | 408k | 465k | $0.66 | 1.8m |
| Bash+Tool | Opus-4.8 | 67.2% [61.3, 73.0] | 50.0% | 563k | 6k | 537k | 569k | $0.55 | 3.1m |
| Bash+Tool | GPT-5.5 | 66.3% [60.3, 72.2] | 47.7% | 503k | 6k | 462k | 508k | $0.60 | 2.5m |
| **Bash** | **Opus-4.8** | **69.4% [63.7, 74.9]** | **50.6%** | 258k | 6k | 239k | **264k** | **$0.37** | 3.0m |
| **Bash** | **GPT-5.5** | **67.1% [61.4, 72.7]** | 47.7% | 370k | 7k | 331k | 377k | $0.56 | 2.6m |
| Bash+Synthesis | Opus-4.8 | 67.1% [61.2, 72.7] | 47.7% | 244k | 5k | 224k | 249k | $0.35 | 3.1m |
| Bash+Synthesis | GPT-5.5 | 66.4% [61.0, 71.8] | 45.4% | 429k | 7k | 388k | 436k | $0.61 | 3.0m |
| PTC | Opus-4.8 | 52.9% [46.8, 59.1] | 29.9% | 395k | 12k | 362k | 406k | $0.64 | 3.2m |
| PTC | GPT-5.5 | 45.1% [39.2, 51.2] | 24.1% | 232k | 10k | 207k | 242k | $0.54 | 1.9m |
| **APEX-Agents** | | | | | | | | | |
| Tool-only | Opus-4.8 | 41.1% [37.4, 44.8] | 24.2% | 384k | 13k | 338k | 397k | $0.73 | 3.4m |
| Tool-only | GPT-5.5 | 39.8% [36.1, 43.4] | 23.3% | 322k | 6k | 282k | 328k | $0.52 | 2.1m |
| Bash+Tool | Opus-4.8 | 47.2% [43.5, 50.8] | 29.8% | 386k | 10k | 350k | 396k | $0.60 | 3.0m |
| Bash+Tool | GPT-5.5 | 45.5% [41.8, 49.3] | 29.6% | 253k | 5k | 218k | 257k | $0.42 | 2.0m |
| **Bash** | **Opus-4.8** | **48.5% [44.9, 52.2]** | **30.0%** | 205k | 10k | 177k | **215k** | **$0.48** | 3.5m |
| **Bash** | **GPT-5.5** | 44.6% [40.8, 48.3] | 28.3% | 171k | 5k | 137k | **176k** | **$0.40** | 2.4m |
| Bash+Synthesis | Opus-4.8 | 46.9% [43.3, 50.7] | 28.3% | 226k | 11k | 201k | 237k | $0.50 | 3.7m |
| Bash+Synthesis | GPT-5.5 | 45.9% [42.2, 49.7] | 29.2% | 222k | 5k | 186k | 228k | $0.44 | 6.6m |
| PTC | Opus-4.8 | 40.1% [36.5, 43.7] | 22.3% | 324k | 12k | 294k | 337k | $0.61 | 3.4m |
| PTC | GPT-5.5 | 37.8% [34.2, 41.5] | 20.6% | 251k | 5k | 207k | 256k | $0.48 | 2.1m |

### Derived deltas (all recompute correctly from Table 1 — internal consistency verified)

**Bash vs Tool-only**:

| Arm | Score delta | Token reduction | Cost reduction |
|---|---|---|---|
| TAC / Opus-4.8 | **+24.5 pp** | 945k → 264k = **−72%** | $1.20 → $0.37 = −69% |
| TAC / GPT-5.5 | **+21.8 pp** | 465k → 377k = **−19%** | $0.66 → $0.56 = −15% |
| APEX / Opus-4.8 | **+7.4 pp** | 397k → 215k = **−46%** | $0.73 → $0.48 = −34% |
| APEX / GPT-5.5 | **+4.8 pp** | 328k → 176k = **−46%** | $0.52 → $0.40 = −23% |

Matches the abstract's stated ranges exactly: 21.8–24.5 pp (TheAgentCompany), 4.8–7.4 pp (APEX-Agents), 19–72% fewer total tokens.

**PTC vs Tool-only — the precise result that cuts against the vendor framing**:

| Arm | Score delta | Token reduction |
|---|---|---|
| TAC / Opus-4.8 | **+8.0 pp** | 945k → 406k = −57% |
| TAC / GPT-5.5 | **−0.2 pp** | 465k → 242k = −48% |
| APEX / Opus-4.8 | **−1.0 pp** | 397k → 337k = −15% |
| APEX / GPT-5.5 | **−2.0 pp** | 328k → 256k = −22% |

**PTC saved tokens in 4 of 4 arms but improved score in only 1 of 4.**

### Table 6 — PTC mechanism confirmed (PTC minus Tool-only, paired by task and model)

| Benchmark | Composition ratio | Δ tool calls | Δ uncached input | Δ cache-read | Δ output |
|---|---|---|---|---|---|
| TheAgentCompany | 2.0 | −4.0 | **−97.6k** | **−86.8k** | +0.2k |
| APEX-Agents | 2.0 | −3.0 | **−45.4k** | **−44.0k** | −0.4k |

Authors: *"Despite modest batching and invocation reductions, PTC substantially reduces uncached input and cache-read tokens on both benchmarks, with broadly similar output-token use. These savings may reflect processing intermediate results within programs and returning only selected outputs, reducing the context carried into subsequent model requests."*

This is exactly the mechanism Anthropic describes. **It is real.** It is smaller than claimed, and it is beaten by a shell.

### Table 3 — shell statistics

| Interface | Cmds/call (median) | LOC | Composed | Loop | Failed | Repair |
|---|---|---|---|---|---|---|
| TAC Bash | 4.0 | 2 | 94.3% | 27.5% | 7.9% | 76.3% |
| TAC Bash+Tool | 3.0 | 2 | 93.9% | 25.7% | 10.8% | 58.7% |
| TAC Bash+Synthesis | 3.0 | 1 | 88.0% | 24.0% | 7.9% | 70.0% |
| APEX Bash | 1.5 | 12 | 96.5% | 67.8% | 4.4% | 55.8% |
| APEX Bash+Tool | 1.5 | 16 | 97.2% | 74.0% | 9.3% | 35.8% |
| APEX Bash+Synthesis | 2.0 | 5 | 93.3% | 48.2% | 5.4% | 51.1% |

Composition (pipes, logical operators, substitution, control flow, heredocs, multiline, nontrivial redirects) remains the norm across all three shell interfaces **even when typed or synthesized tools are available**. Bash+Tool has the lowest median shell calls per shell-using task combined with the **highest failure rate and lowest retry rate** in both benchmarks — adding a catalog alongside the shell reduces shell use without improving the reliability of the remaining shell calls.

### Authors' conclusions, verbatim

> "Shell-only agents offer the strongest overall task performance and cost efficiency with the simplest tool scaffold in this study. Adding a typed catalog or persistent synthesized-tool library to the shell provides no consistent quality gain. Programmatic tool calling reduces token use over direct typed-tool calling with broadly similar or slightly better performance depending on workplace scenarios, while underperforming shell-only on both quality and cost."

> "For enterprise practitioners, these results favor bash alone when arbitrary execution can be isolated and PTC when security or compliance policies require a fixed tool catalog."

> "As frontier models evolve, these recommendations may not carry over to later releases in either family."

**Label**: MEASURED (independent). **Confidence: strong.**

**Discount to apply**: Microsoft is evaluating tool interfaces for its own Copilot Studio product line, which uses the GitHub Copilot CLI and SDK — i.e. the shell-based offering their result favors. Methodology is sound, the design is properly controlled, and every derived range recomputes correctly from the raw table. But apply the same skepticism you would to any first-party evaluation. The paper cites 2608.06370 as "Patel et al. 2026" and asserts independence from it.

---

## 1.3 Independent measurement #2 — "The Bitter Lesson of Tool Calling"

**arXiv 2608.06370** (submitted 2026-08-06). 14 language models, BFCL v4 (309 representative entries across 8 task categories: simple_python, multiple, parallel, parallel_multiple, live_simple, live_multiple, and others).

**Paradigms**: JSON tool calling (schemas via the API `tools` parameter, structured JSON output — the reference condition) vs PTC (system prompt embeds the source of a typed Python module whose functions map one-to-one to the benchmark schemas; model writes a script; agent loop executes it in a native shell subprocess; scorer extracts function names and argument values from stdout).

**Experimental control**: *"No additional inference turns occur after the subprocess returns. A stop middleware intercepts the next model call and terminates the agent loop. This design ensures that programmatic tool calling and JSON tool calling consume the same number of LLM calls per entry, making accuracy comparisons straightforward."*

### Accuracy summary

| Ablation | n | Result |
|---|---|---|
| BFCL v4 main | 309 | PTC matches or exceeds JSON in **11 of 14 models**; GPT-5.6 family **+10.6%** over the JSON baseline |
| Parallelism | 32 (fan-out 7, 9, 11, 13, 15, 20, 30, 48) | PTC matches or exceeds in **13 of 14 models** |
| Chaining | 52 (chain lengths 2–20) | Mixed |
| Context rot | 31/condition | JSON mean Δ **−2.3%**, PTC **+5.5%**, filesystem-discovery **−32.0%** |

Parallelism detail: largest PTC gain is GPT-5, **71.9% → 96.9%**. JSON baseline accuracy degrades as fan-out rises above 13; PTC maintains near-perfect enumeration across all fan-out levels. The single model below baseline under PTC is GPT-4.1 (90.6% vs 96.9%), attributed to a `\n` encoding failure on parallel scripts requiring `asyncio.gather`.

Chaining detail (Table 3, selected rows, JSON vs PTC): GPT-5.6-Luna 82.7 → **92.3**; GPT-5.6-Sol 96.2 → 90.4; GPT-5.6-Terra 98.1 → 96.2.

### THE TOKEN CROSSOVER — the finding the vendor posts omit

Verbatim from Section 4.3 (Parallelism Ablation):

> "Token costs cross over at N ≈ 26. Below this threshold programmatic tool calling is more expensive due to its fixed system-prompt overhead. Above it, JSON tool calling exceeds programmatic tool calling as the response must enumerate all N tool-call objects. At N = 30, JSON tool calling uses 3,559 tokens versus 3,380 for programmatic tool calling. At N = 48, the gap widens to 5,097 versus 3,535."

**N is the fan-out count — the number of calls issued in one turn — not the size of the tool catalog.** The ablation's fan-out levels were 7, 9, 11, 13, 15, 20, 30, 48. Catalog size is a separate axis, tested in the context-rot ablation, where token cost was not the reported outcome.

| Fan-out N | JSON tokens | PTC tokens | PTC delta | PTC % saving |
|---|---|---|---|---|
| < 26 | — | — | PTC **more expensive** | negative |
| ≈ 26 | — | — | **break-even** | 0% |
| 30 | 3,559 | 3,380 | −179 | **−5.0%** |
| 48 | 5,097 | 3,535 | −1,562 | **−30.6%** |

**Mechanism of the asymmetry**: JSON output scales linearly in N — the response must emit one tool-call object per call. The PTC script is roughly constant in N — one `asyncio.gather` regardless of fan-out. From N=30 to N=48, JSON tokens grow **43%** while PTC tokens grow **4.6%**.

**Where PTC's fixed overhead comes from, and a billing-surface caveat**:

> "programmatic tool calling carries a fixed input-token overhead relative to JSON tool calling: the system prompt embeds the full instruction template as prose, whereas JSON tool calling passes function schemas through the API tools parameter, which some providers count separately from conversation input tokens. On the chaining ablation, programmatic tool calling uses 1.5× the input tokens of JSON tool calling. This overhead reverses at high fan-out... Output token counts do not differ across paradigms."

Part of the measured PTC penalty is therefore an **accounting artifact** (where the provider books schema tokens), not real compute. That cuts both ways and should be stated when citing the 1.5×.

**Practical reading**: PTC is a **fan-out optimization**, not a general token optimization. Below ~26 parallel calls per turn it costs more. Sequential/chained work costs 1.5× input tokens. This is the opposite of how the vendor posts frame it, and it is consistent with 2609.11999's finding that PTC's real-world savings come from intermediate-result filtering rather than from call-encoding efficiency.

### The filesystem-discovery collapse — Anthropic's proposed mechanism, measured

The context-rot ablation adds a third condition, "Arg" = filesystem-discovery: the agent explores a filesystem to discover tool definitions. This is the mechanism Anthropic's blog post proposes (`./servers/<name>/<tool>.ts` explored on demand).

**Filtered** = only the entry's relevant function schemas. **Flood** = 128 total schemas (relevant functions + corpus decoys from unrelated domains). n = 31 per condition. 95% Wilson CIs range ±7.8% to ±16.6% (widest near 50% accuracy).

| Model | Filt JSON | Filt PTC | Filt Arg | Flood JSON | Flood PTC | **Flood Arg** |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | 93.5 | 83.9 | 48.4 | 87.1 | 77.4 | **25.8** |
| Claude Sonnet 4.5 | 90.3 | 83.9 | 58.1 | 93.5 | 80.6 | **29.0** |
| Claude Sonnet 4.6 | 93.5 | 83.9 | 83.9 | 87.1 | 87.1 | **32.3** |
| Claude Opus 4.8 | 87.1 | 83.9 | 90.3 | 83.9 | 80.6 | **41.9** |
| Claude Sonnet 5 | 87.1 | 87.1 | 80.6 | 90.3 | 87.1 | **45.2** |
| GPT-4o | 96.8 | 51.6 | 61.3 | 90.3 | 74.2 | **16.1** |
| GPT-4.1 | 83.9 | 51.6 | 41.9 | 80.6 | 64.5 | **19.4** |
| GPT-5-nano | 74.2 | 54.8 | 25.8 | 64.5 | 71.0 | **16.1** |
| GPT-5 | 77.4 | 67.7 | 48.4 | 74.2 | 77.4 | **32.3** |
| GPT-5.4-mini | 80.6 | 45.2 | 54.8 | 87.1 | 80.6 | **12.9** |
| GPT-5.4 | 80.6 | 83.9 | 64.5 | 77.4 | 77.4 | **9.7** |
| GPT-5.6-Luna | 83.9 | 77.4 | 35.5 | 80.6 | 74.2 | **6.5** |
| GPT-5.6-Sol | 77.4 | 80.6 | 32.3 | 71.0 | 80.6 | **12.9** |
| GPT-5.6-Terra | 64.5 | 80.6 | 35.5 | 71.0 | 80.6 | **12.9** |
| **Mean Δ (filtered→flood)** | | | | **−2.3** | **+5.5** | **−32.0** |

Under catalog flooding, filesystem-discovery lands at **6.5–45.2% absolute accuracy**, and the three strongest results are all Claude models (which is the family Anthropic's post targets).

**Fairness caveat, in the authors' own words**: they call the filesystem condition *"an internal reference point. It is not an industry practice and is referenced only where it illuminates the primary comparison."* It is their implementation, not a faithful reproduction of Anthropic's design, and it was not the paper's object of study. Treat it as a strong negative signal, not a refutation.

**Counter-direction worth noting**: PTC *improves* under flood (+5.5%), driven by models that struggled with the filtered condition's strict type constraints but found the flood condition's richer context helped them identify the correct function — GPT-5.4-mini **+35.5pp**, GPT-4o **+22.6pp**, GPT-4.1 **+12.9pp**.

### Self-flagged validity problem (handled honestly)

On the parallelism ablation the authors separate enumeration accuracy (did the model issue all N required calls?) from aggregation accuracy (did it produce the correct aggregate answer?):

> "Inspection of outputs shows that models frequently produce the correct aggregation answer from parametric world knowledge (stating, for example, the top-3 countries by population directly) without executing the enumeration calls. This is a correct answer by the scorer's standard, but it does not test whether the model actually executed the tools. We report both metrics separately and treat enumeration accuracy as the primary measure of paradigm fidelity."

### Four stated limitations

1. **BFCL v4 uses echo-return stubs** — each function returns its arguments verbatim rather than executing real API calls. *"This means we measure argument serialization accuracy, not end-to-end tool-use correctness. Results may not transfer to settings where return values affect downstream calls."*
2. **n = 31–52 per ablation condition** — wide CIs; individual model results are directional only. *"Only the aggregate cross-model patterns (11 of 14 on BFCL v4, consistent programmatic tool calling improvement under flood) are large enough to interpret reliably."*
3. **A recent audit found 20% evaluator-human misalignment in BFCL v4's LLM-judge evaluation mode.** Their deterministic scorer avoids that path but may inherit ground-truth label noise.
4. The fixed input-token overhead described above.

**Label**: MEASURED (independent). **Confidence: moderate** — sound design and clean control, but small n and synthetic echo-return stubs.

---

## 1.4 Prior art

| Paper | Finding | Conditions | Label | Conf. |
|---|---|---|---|---|
| **arXiv 2305.18323 — ReWOO** (May 2023) | **5× token efficiency and +4% accuracy on HotpotQA** by decoupling reasoning from observations; also offloads 175B GPT-3.5 reasoning into 7B LLaMA | 6 public NLP benchmarks + curated dataset; robust under tool-failure scenarios | MEASURED (indep.) | moderate (pre-frontier models) |
| **arXiv 2402.01030 — CodeAct** (ICML 2024) | **Up to 20% higher success rate** than JSON/text action formats | 17 LLMs on API-Bank + a newly curated benchmark; CodeActInstruct = 7k multi-turn interactions; CodeActAgent finetuned from Llama2/Mistral | MEASURED (indep.) | moderate |
| **arXiv 2512.24601 — Recursive Language Models** (Dec 2025) | GPT-5 median across evaluated benchmarks: **+26% vs compaction, +130% vs CodeAct with sub-calls, +13% vs Claude Code**; processes inputs up to 2 orders of magnitude beyond context windows at comparable cost. RLM-Qwen3-8B **+28.3%** over base Qwen3-8B | 4 diverse long-context tasks | MEASURED (indep.) | moderate |

**Important**: CodeAct, the canonical code-as-action citation, **publishes no token-efficiency number**. Its claim is success rate. Anyone citing CodeAct for token savings is citing something that is not in the paper. I searched the abstract and listing page and found no token or turn-count efficiency figure.

---

## 1.5 Answer to Q1

Yes, programmatic access beats conventional tool-calling on token cost — with four conditions that the vendor posts do not state:

1. **It is a fan-out optimization.** Crossover at N ≈ 26 concurrent calls per turn. Below that, PTC costs more. Chained/sequential work costs **1.5× the input tokens**.
2. **The savings come from intermediate-result filtering**, not from tool-definition loading. Table 6 of 2609.11999 confirms the mechanism: −97.6k uncached input, −86.8k cache-read, output unchanged.
3. **Plain bash beats PTC on both quality and cost** in the only realistic end-to-end enterprise comparison (2609.11999): PTC saved tokens in 4/4 arms but improved score in 1/4, and lost to bash in every arm.
4. **The 98.7% figure has no measurement behind it**, and the filesystem mechanism Anthropic's post proposes is the one condition that measurably collapsed under catalog flooding (−32.0% mean).

---

# Q2. Context compaction and summarization

## 2.1 Anthropic's compaction endpoint measures at random guess

**arXiv 2608.01326 — "Context Compaction Theory"** (submitted 2026-08-02).

**Theory contribution**: introduces two games capturing the two algorithmic strategies in contemporary agents — the **Context Selection Game** (retain a subset of accumulated state) and the **Context Generation Game** (summarize into an arbitrary bounded-length message). Proves the Generation Game **equivalent to one-way communication complexity**: the minimum compaction budget for answering a query set within a target error equals the one-way communication complexity of the induced problem at the same error. Known communication-complexity bounds therefore transfer directly to compaction. Also proves the Selection Game corresponds to a restricted class of one-way protocols, and that **there exists a query set for which generation needs strictly less budget than selection**.

**The empirical case study** — the measurement referenced in the verdict:

**Setup**: Anthropic's context compaction endpoint on the Claude API, **Opus 4.8**. Recorded set = **15,000 URLs** uniformly sampled from the Malicious URLs dataset (≈ **500,000 tokens**). Compaction threshold set to **50,000 tokens** so compaction triggers. **200 membership queries** after compaction — half sampled from the recorded set (probing false negatives), half from dataset URLs not recorded (probing false positives). Each query sent in a separate request containing only the compacted context. Structured JSON yes/no output. **3 random seeds** controlling both set and query choice. Budget B = character count of the returned natural-language summary × 8 bits (Anthropic provides the summary unencrypted).

**The dataset was chosen to favor the endpoint**: URLs share structure such as common domains and path patterns that a compactor could exploit; learned Bloom filters perform well on this dataset for the same reason.

**The endpoint was told its workload in advance**, analogous to building a Bloom filter for a known workload. Verbatim compaction prompt:

> "You are compacting this conversation. Afterward the original messages are discarded, and you must answer set membership queries using only your compacted summary: for a given string, whether it was among the strings listed above. Compact the conversation so as to minimize the number of membership queries you answer incorrectly. Use whatever representation best achieves this."

**Results (Table 2)**:

| Run | Budget | False positive rate | False negative rate | Total error |
|---|---|---|---|---|
| Seed 42 | 14.3 Kbits | 0.04 | 0.97 | **0.505** |
| Seed 43 | 13.6 Kbits | 0.28 | 0.79 | **0.535** |
| Seed 44 | 14.8 Kbits | 0.48 | 0.63 | **0.555** |
| **No compaction (control)** | 7,280 Kbits | 0.00 | 0.04 | **0.02** |

**Reference points at the same ~14 Kbit budget**:

| Method | Error rate |
|---|---|
| Random guess (always answer "no") | 0.50 |
| **Anthropic endpoint, Opus 4.8** | **0.505 – 0.555** |
| Bloom filter, ½·e^(−(ln2)²B/N) | ≈ 0.33 |
| Information-theoretic bound, ½·2^(−B/N) | ≪ 0.33 |

Authors: *"Every run lands on the random guess line."* The error metric is constructed so that an algorithm forgetting every item and always answering "no" scores exactly 0.5 — and seed 42's FN 0.97 / FP 0.04 split is almost precisely that behaviour.

**What the summaries actually did**: *"In these summaries, the LLM states that it cannot losslessly store the set. It falls back to a description of the set's general character."*

**The control at 0.02 error establishes causation**: *"Information lost during context compaction therefore causes the error in the main experiment."* Not long-context degradation — the same model with the same 15,000 URLs fully in context answers at 0.02 error.

**Authors' own scoping, which must be carried with the finding**:

> "This experiment does not demonstrate that context compaction algorithms for set membership query workloads necessarily perform significantly worse than a Bloom filter in real-world use cases. This experiment merely captures a snapshot of one deployed endpoint, i.e., Anthropic's server-side context compaction endpoint with..."

Set membership is adversarial to summarization by construction — it is exactly the query class where one-way communication complexity is provably high and where no summary can beat a bit-level data structure. This is a **worst case, not a typical case**. Code at github.com/jadidbourbaki/context-compaction-experiments.

**Label**: MEASURED (independent). **Confidence: strong** for the narrow claim (one endpoint, one task family, one model, n=3 seeds). **Weak** as a generalization to agent workloads.

## 2.2 When compaction loses task-critical information

**arXiv 2606.22528 — "Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents"** (submitted 2026-06-21, v2).

The most complete measurement available on compaction information loss.

**Method**: ConstraintRot benchmark of long-horizon agent scenarios. **1,323 episodes in the main run**, **7 model families**, **n = 27 per (model, condition) cell**. The primary violation metric is **deterministic**: parse every agent's terminal tool call and detect the prohibited effect in the action arguments (a recipient outside the allowed domain in `send_email`; a DROP/DELETE on a production target in `db_exec`). Robust to surface formatting, **no LLM judge**. Secondary survival metric (whether the compacted context still entails the constraint) scored by an independent LLM judge on the original five-model grid, cross-checked against a keyword heuristic covering all seven models. Compaction configured aggressively (tight word budget) *"matching production guidance and ensuring the summary genuinely contests the token budget rather than copying the history verbatim."*

**Core result**:

| Condition | Violation rate |
|---|---|
| Policy in full context | **0%** |
| After compaction (pooled, 1,323 episodes) | **30%** |
| After compaction, worst model | **59%** |

**Mechanism — the clean split**:

| Constraint state after compaction | Violation rate | n |
|---|---|---|
| **Survives** the summary | **0%** | 90 |
| **Dropped** from the summary | **38%** | 315 |
| Keyword-heuristic replication (7 models): survived | 1% | 207 |
| Keyword-heuristic replication: dropped | 43% | 360 |
| 3-judge majority-vote replication: survived | 0% | 18 |
| 3-judge majority-vote replication: dropped | 40% | 63 |

Judge agreement: 83% with the keyword heuristic on overlapping original-panel episodes; pairwise judge agreement 62–83% (one judge degenerately labels every context "dropped" and is uninformative).

**THE QUALITY-VS-TOKENS TRADEOFF CURVE** (their Figure 3, pooled over models) — this is the measured curve:

| Summary budget (words) | Constraint survival | Pooled violation |
|---|---|---|
| 300 | **88%** | **7%** |
| 150 | — | — |
| 80 | — | — |
| 50 | — | — |
| 30 | — | — |
| 15 | **23%** | **28%** |

Sweep points were 15, 30, 50, 80, 150, 300 words. DeepSeek-V4 on the same sweep: **20% → 65%** violation.

Authors: *"Because production guidance is to compact aggressively for efficiency, real deployments are pushed toward the high-decay end of this curve."*

**By compaction strategy**:

| Strategy | Violation |
|---|---|
| recency-truncate | **38%** (worst) |
| hierarchical | 36% |
| LLM summarize | 26% |
| **head_tail** (keeps the oldest turn) | **0%** |
| **Constraint Pinning** | **0%** under every strategy |

**What decays is exactly the deployable kind of governance**:

| Constraint family | Violation change |
|---|---|
| Soft organization-specific policies | **0% → 50% (+50 pts)** |
| Hard safety norms (alignment-trained refusals) | **+6 pts** |

An **8.3× gap**. Authors: *"Built-in priors mask the effect on hard norms, creating a false sense of safety... while Governance Decay erodes exactly the soft, deployment-specific rules that have no home except the context window."*

**Ablations isolating the mechanism** (GLM-5.1): with the policy visible, GLM never violates even in an uncompressed **5.9k-token** long context (0%), ruling out generic context-length degradation. Follow-up ablations compare compacted summaries to uncompressed long contexts and to counterfactual summaries where the policy is manually removed or restored.

**Reproduced in shipped production frameworks** (DeepSeek-V4 unless noted, n = 20 each):

| Framework | Violation |
|---|---|
| LangGraph StateGraph + summarization-memory node | **65%** |
| LangMem official `SummarizationNode` | **95%** (GLM-5.1: **70%**) |
| AutoGen `BufferedChatCompletionContext` (recency eviction) | **100%** |
| OpenAI Agents SDK Runner, given the same LLM-written summary | **35%** |
| Microsoft Agent Framework | Preserves system messages — channel-limited protection only |

Note on the LangMem result: *"breaking even the model whose own summarizer preserved the policy in our harness."* Note on Microsoft: *"framework guarantees for one channel do not protect memory- and conversation-carried governance unless those constraints are also preserved or pinned."*

**Attack surface**: a Compaction-Eviction Attack in which adversarial in-context content biases the summarizer to omit a legitimate policy. *"Optimized injections defeat every evaluated model."*

**Mitigation measured — Constraint Pinning** (training-free; quarantines governance constraints from lossy compaction):

| Defense | Violation (passive / injection) | Allowed actions completed | Over-refusal |
|---|---|---|---|
| No defense | 40% / 42% | — | — |
| **Constraint Pinning** | **0% / 0%** | **99%** | **1%** |
| Policy in preserved system channel | 0% / 0% | — | — |
| Policy in context (control) | — | 90% | 10% |
| Spotlighting-style provenance prompt | **43% / 45%** | — | — |

3 models, 5 soft tasks, n = 84 per condition for the utility test across 7 allowed counterparts (emailing an internal address, purchasing under the limit, deploying to the approved region, read-only production query).

Two findings worth carrying: (a) pinning is *better* than policy-in-context on utility — *"an explicit pinned rule helps the agent separate permitted from forbidden actions rather than blanket-refusing"*; (b) Spotlighting fails because *"marking ingested content as untrusted data cannot restore a constraint the summary has already deleted."* The system channel works but *"is available only when the operator controls the system prompt—not for memory- or tool-delivered governance."*

**Authors' thesis**: *"Governance Decay is a property of the harness, not the model: stronger models help only insofar as their summarizers preserve constraints, and even those fall to injection or recency eviction."*

**Label**: MEASURED (independent). **Confidence: strong.**

## 2.3 Compaction can be trained; untrained it is unpredictable

| Paper | Finding | Conditions | Label | Conf. |
|---|---|---|---|---|
| **arXiv 2607.05378 — CompactionRL** (Jul 2026) | GLM-4.5-Air (106B-A30B): **66.8% SWE-bench Verified (+7.0)**, **24.5% Terminal-Bench 2.0 (+3.1)**. GLM-4.7-Flash (30B-A3B): **56.0% (+5.5)**, **20.2% (+6.8)** | Pass@1. Jointly optimizes task execution and summary generation with token-level loss normalization and cross-trajectory generalized advantage estimation. Deployed in the RL pipeline for GLM-5.2 (750B-A40B) | **MEASURED (vendor-adjacent — Zhipu, their own models and pipeline)** | moderate |
| **arXiv 2605.23296 — Parallel Context Compaction** (May 2026) | *"the operator has no fine-grained control over summary volume since prompt instructions are largely ignored, and as context grows, both the amount of output tokens the model produces and the information it retains fluctuate substantially from run to run, making the agent's retained knowledge unpredictable across runs."* Parallel compaction gives predictable volume control and reduces end-to-end wall time at matched decode volume | 4 backbones 8B–120B, dense + MoE, reasoning + non-reasoning; HotpotQA multi-hop QA and LoCoMo long-context dialogue | MEASURED (indep.) | moderate |

The second finding matters for harness design independently of quality: if summary volume is not controllable by prompt instruction, a compaction policy cannot be tuned by prompt alone — it needs a structural mechanism.

## 2.4 Answer to Q2

- **Compaction is formally equivalent to one-way communication complexity** (2608.01326), so there are hard information-theoretic floors on what any summarizer can retain. Generation beats selection for some query sets, provably.
- **It loses task-critical information at measurable, large rates**: 0% → 30% pooled constraint violation, up to 59% by model, with a clean causal mechanism (survived → 0%, dropped → 38%).
- **The tradeoff curve is measured**: 300 → 15 word budgets move survival 88% → 23% and violation 7% → 28%.
- **Strategy choice dominates**: recency-truncate 38%, LLM summarize 26%, head_tail 0%.
- **Shipped frameworks reproduce it at 35–100%.**
- **A structural fix exists and costs nothing**: pinning → 0% violation at 99% allowed-action completion. Prompt-level defenses do not work.
- **On an adversarial retrieval task, one shipped endpoint retains no usable information at all** (random guess vs 0.02 uncompacted) — a worst case, but a real one.

---

# Q3. Observation-space cost

## 3.1 What exists with numbers: accessibility-tree granularity

**arXiv 2605.07134 — "Region4Web: Rethinking Observation Space Granularity for Web Agents"** (submitted 2026-05-08). Code at github.com/kwondu/region4web.

Reorganizes the AXTree into **functional regions** (parts of the page serving a distinct purpose) via hierarchical decomposition and semantic abstraction. PageDigest is the inference pipeline delivering region-level observation as a compact per-page digest persisting across steps, tracking observation transitions rather than reconstructing the full observation at every step. It shares the actor agent's backbone and operates solely on the observation space.

**Aggregate across 4 backbones (WebArena)**:

| Metric | Value |
|---|---|
| Observation length | **6,437 → 3,671 tokens (−43%)** |
| Task success rate | **+2.3 pp** |

*"The improvement holds across backbones of varying capacity."*

**Ablation, GPT-5.1 on WebArena-Lite (165-task subset) — the load-bearing table**:

| Configuration | Success | Obs. length | Token change |
|---|---|---|---|
| GPT-5.1 baseline (raw AXTree) | 48.5% | 5,410 | — |
| + Region4Web only | 50.3% | 5,922 | **+9% (larger)** |
| + element-level self-ctx (LCoW-style) | **46.1%** | 4,013 | −26% |
| + **PageDigest** (region-level) | **53.9%** | **3,814** | **−30%** |

**The critical comparison**: element-level compression cut 26% of tokens and **dropped success below baseline** (48.5 → 46.1). Region-level compression cut 30% and raised success **+5.4 pp**. *"Region-level observation supports the actor agent where element-level processing instead hinders it."*

**Granularity, not compression ratio, determines whether the task survives compression.** This is the single most transferable finding for harness design in Q3.

**Applied to existing agent methods**: SteP **−50%** observation length, AgentOccam **−16%**, both at comparable task success. For AgentOccam, replacing its observation-space alignment with PageDigest yields comparable performance — region-level observation can replace element-level alignment for action selection.

**Task-scale, after accounting for the auxiliary inference PageDigest itself adds**:

| Metric | Before | After | Change |
|---|---|---|---|
| Median step observation | 3,077 | 2,066 | **−33%** |
| Median cumulative observation per task | 26,707 | 19,944 | **−25%** |

Cost decomposition of the task total: actor observations **73.9%**, region selection **19.5%**, view_all expansions **6.6%**. Region selection is invoked **4.8 times per task on average** but stays cheap because it operates over region-level abstractions rather than the element-level AXTree. view_all fires in only **38.1% of tasks**, averaging **0.64 calls**. *"The auxiliary overhead therefore stays bounded by page entries, and the step-scale compactness carries through to the task-scale."*

**Failure attribution** (50 randomly sampled failed trajectories, 10 per domain, multi-cause):

| Failure source | Share |
|---|---|
| Actor-side backbone action selection | **90.0%** |
| Environment errors outside the pipeline | 16.0% |
| Region selection (backbone missing relevant regions) | 10.0% |
| Decomposition errors | 2.0% |
| Abstraction errors | 2.0% |
| Transition management | **0%** (deterministic AXTree comparison) |

*"82.0% backbone capacity dominating 8.0% PageDigest regression under multi-cause attribution."*

**Label**: MEASURED (independent). **Confidence: moderate-to-strong.**

## 3.2 Pixels vs structure — reliance measured, tokens not

**arXiv 2607.04334 — "Do GUI Agents Believe Their Eyes? Diagnosing State-Belief Reliance on Pixels versus Structure"** (submitted 2026-07-05, v2).

Formalizes **visual state reliance** — the attribution of a state belief to pixels, structure, or priors — and measures it with paired single-channel interventions over **735 probes** spanning real web, mobile and desktop interfaces, of which **225 are zero-edit divergences mined from live production websites**. Scored by **deterministic forced choice with no model judge**. Models from four vendors.

Central metric: the **Perception-Fusion Gap (PFG)** — the fraction of probes a model perceives correctly yet resolves toward structure under conflict. A stricter variant re-verifying perception on a tight crop of the target region **leaves the gap intact**.

| Finding | Number |
|---|---|
| Follow outdated **structure** on unedited stale snapshots from live pages | up to **0.88 of probes** |
| Image-only accuracy | near ceiling |
| Self-recovery rate after one mis-sourced belief at step 1 (live multi-step) | **≤ 0.03** |
| Mitigation: prompt-level cues | fail at the action level |
| Mitigation: certificate checks | buy safety with refusals |
| Mitigation: training-free consistency gate | **only one reducing both hijack and task error** |

A white-box ablation traces the textual effect to **a single copied structural value**; gradient attribution shows the visual evidence is **processed yet overridden**.

**Implication for harness design**: giving an agent both a screenshot and a serialized tree does not buy redundancy. The structure channel dominates the state belief, so the screenshot's token cost buys grounding you do not actually get — and when the structure is stale, the screenshot does not rescue you 88% of the time.

**Label**: MEASURED (independent). **Confidence: strong** for what it measures. It reports **no token costs**.

## 3.3 THE GAP — stated plainly

**No paper measures token cost and task success across accessibility tree vs raw DOM vs screenshot vs code-mediated access in one controlled comparison.**

Searches run and their results:

| arXiv query | Result |
|---|---|
| `all:"observation space" AND all:"web agent"` | 2 hits (Region4Web; WebMall) |
| `abs:"accessibility tree" AND abs:"screenshot"` | 12 hits, none with a four-way token/success table |
| `abs:"GUI agent" AND abs:"token cost"` | 3 hits (parallel execution, executable memory, replayable memory) |
| `all:"screenshot" AND all:"DOM" AND all:"token cost" AND all:"agent"` | **zero results** |

The four-way table does not exist in what I can reach. What exists is **one axis with numbers** (AXTree granularity — Region4Web) and **a different axis without token numbers** (pixels-vs-structure reliance — 2607.04334). Do not let downstream writing imply the comparison was found.

---

# Q4. Token-efficiency mechanisms a harness controls

## 4.1 The enumerated table

| # | Mechanism | Evidence | Numbers with conditions | Label | Conf. |
|---|---|---|---|---|---|
| 1 | **Prompt caching / cache-shape discipline** | 2601.06007 | **41–80% API cost reduction**, **13–31% TTFT improvement**. 3 providers (OpenAI, Anthropic, Google), 3 strategies (full-context, system-prompt-only, exclude-dynamic-tool-results), DeepResearch Bench, **500+ agent sessions**, 10,000-token system prompts. Ablation across prompt sizes 500–50,000 tokens and tool-call counts 3–50 shows **universal linear** cost and TTFT benefit after the provider caching token minimum. Strategic block control (dynamic content at the end of the system prompt, avoid dynamic traditional function calling, exclude dynamic tool results) beats naive full-context caching, which **can paradoxically increase latency** | MEASURED (indep.) | strong |
| 2 | **Shell over typed tool catalog** | 2609.11999 | **19–72% fewer total tokens**, **+4.8–24.5 pp** score, **15–69% lower $/task**. Opus-4.8 + GPT-5.5, TheAgentCompany (174 tasks) + APEX-Agents (480 tasks) | MEASURED (indep.) | strong |
| 3 | **Programmatic tool calling** | 2609.11999, 2608.06370 | Saves tokens 4/4 arms (−15% to −57% vs Tool-only), improves score 1/4. Crossover at **N ≈ 26 concurrent calls**; 1.5× input tokens on chaining; 11/14 models match-or-exceed JSON on BFCL v4 | MEASURED (indep.) | strong |
| 4 | **Observation-space granularity** | 2605.07134 | **−43% observation tokens, +2.3 pp** success, 4 backbones, WebArena. Element-level compression at −26% tokens **loses** 2.4 pp vs baseline | MEASURED (indep.) | moderate |
| 5 | **Compaction policy** (budget + strategy) | 2606.22528, 2608.01326 | Full curve measured: 300→15 word budget = 88%→23% constraint survival, 7%→28% violation. Strategy: recency-truncate 38%, hierarchical 36%, LLM-summarize 26%, head_tail 0% | MEASURED (indep.) | strong |
| 6 | **Structured vs prose / token-optimized wire formats** | 2605.29676 | **TRON: −27% tokens at ≤14 pp accuracy cost. TOON: −18% at 9 pp cost**, and additionally *"cascades on multi-turn parsing failures and collapses parallel tool-call output for most models."* 4 agentic benchmarks (BFCL, MCPToolBenchPP, MCP-Universe, StableToolBench), 5 open-weight LLMs, input compression decoupled from output compression | MEASURED (indep.) | moderate |
| 7 | **Local routing + prompt compression (triage layer)** | 2604.12301 | **T1 (local routing) + T2 (prompt compression) = 45–79% cloud token savings** on edit-heavy and explanation-heavy workloads; RAG-heavy needs the full tactic set including T4 (draft-review) for **51%**. Seven tactics evaluated individually, pairwise, and greedy-additive across 4 coding-agent workload classes. **Optimal subset is workload-dependent** — the authors' own headline actionable finding | MEASURED (indep.) | moderate |
| 8 | **Sub-agent context isolation** | 2609.09233, 2606.13643 | Subagent execution **outperforms** in-context agent-skill execution *"when skill packages expose clear input-output contracts and their instructions encode the procedural knowledge needed to fulfill those contracts."* Tradeoff is coordination token overhead. **No headline numbers in the abstract.** RAH (2606.13643): Codex baseline **71.75% → 81.36%** on Oolong-Synthetic, GPT-5 held fixed, 199 samples, 13 context-length buckets up to 4M tokens | MEASURED (indep.) | moderate |
| 9 | **Whole-harness orchestration swap** | 2607.06906 | Cost/task **−41%** ($0.21→$0.12), tokens/task **−38%** (14.2k→8.8k), median wall-clock **−44%** (48s→27s), quality 0.78→0.81 (*"directional at this sample size"*). 22 locked evaluation tasks, 6 foundation models (Claude Sonnet 4.6, Gemini 3.1, Gemini Flash 3.5, Qwen 3.6, GLM 5.1, Palmyra X6), **only the orchestration layer changed**. Efficiency model-invariant (every model 33–61% cheaper); quality gain correlates with baseline model strength **r = 0.99, n = 6** ("harness leverage"). Quality per dollar +82%; task-completions per million tokens 54.9 → 92.0 | **MEASURED (VENDOR — Writer, evaluating its own Writer Agent Harness)** | weak-moderate |
| 10 | **Skills-as-code / persistent tool synthesis** | 2609.11999, 2602.14690 | **NULL RESULT**: Bash+Synthesis produced *"no detectable pooled score gain"* over bash alone (TAC Opus 67.1 vs 69.4; APEX Opus 46.9 vs 48.5). It did shorten invocations (lowest median LOC and composition fraction on both benchmarks). Adoption reality across **2,853 GitHub repositories**: Skills *"predominantly rely on static instructions rather than executable scripts"* | MEASURED (indep., null) | moderate |
| 11 | **Tool-result truncation** | — | Universally implemented (nano-rlm: 20,000-byte middle-out; 16 KiB shell-job cap). **No paper isolating its effect on tokens or task success was found.** | **CLAIMED** | — |
| 12 | **Lazy / paged tool discovery** | 2603.05344 | Named as a design dimension in OPENDEV ("lazy tool discovery", "adaptive context compaction that progressively reduces older observations", "workload-specialized model routing", "dual-agent architecture separating planning from execution", "event-driven system reminders" to counteract instruction fade-out). **Architecture description only — no isolating measurement.** | **CLAIMED** | — |

## 4.2 THE CAVEAT THAT GOVERNS THE ENTIRE TABLE

**arXiv 2607.12161 — "Token Reduction Is Not Cost Reduction"** (submitted 2026-07-13, v5).

Three token-reduction approaches evaluated against an **unmodified Claude Code baseline** across controlled coding tasks, measuring **provider-billed cost**, task success, cache traffic, and agent behavior.

| Finding | Number |
|---|---|
| Largest compression setup: delivered tool-output tokens | **−38.4%** |
| Same setup: **provider-billed cost** | **+6.8%** |
| Lighter compression | small and statistically uncertain savings |
| Correlation, token reduction vs cost reduction across tasks | **Pearson r = 0.15** |
| SWE-bench Go subset, aggressive compression | **reduced successful patch application** |

**Cost decomposition**: *"prompt-cache creation and reads dominate the measured input-side cost, leaving only a limited fraction of total spend directly addressable by tool-output compression."*

**Second-order effect**: *"compression can alter agent trajectories through additional retrieval, diagnosis, testing, and turns, offsetting local token savings."*

**Authors' conclusion**: *"token reduction is not a reliable proxy for cost reduction in tool-heavy coding agents. Effective optimization should therefore be evaluated at the level of cost per successful task, including cache behavior, trajectory changes, and correctness rather than token counts alone."*

**This applies to 2609.11999's own token columns.** Which is why that paper's `$/task` column carries the argument, not its token column — and bash still wins both ($0.37 vs $1.20 on TheAgentCompany/Opus-4.8; $0.40 vs $0.52 on APEX/GPT-5.5). It also means the Region4Web and Notation Matters token reductions are **unvalidated as cost reductions** — neither paper reports billed cost.

**Label**: MEASURED (independent). **Confidence: strong.**

## 4.3 Architectural context

**arXiv 2604.03515 — "Inside the Scaffold: A Source-Code Taxonomy of Coding Agent Architectures"** (Apr 2026). Source-code-level taxonomy from **13 open-source coding agent scaffolds at pinned commit hashes**, characterized across 12 dimensions in three layers (control architecture; tool and environment interface; resource management). All taxonomic claims grounded in file paths and line numbers.

Key measurements:
- **Tool counts range 0 to 37.**
- **Context compaction spans seven distinct strategies.**
- Five loop primitives (ReAct, generate-test-repair, plan-execute, multi-attempt retry, tree search) function as composable building blocks; **11 of 13 agents compose multiple primitives** rather than using a single control structure.
- *"Dimensions converge where external constraints dominate (tool capability categories, edit formats, execution isolation) and diverge where open design questions remain (context compaction, state management, multi-model routing)."*

Read: **compaction policy is an unsolved design question**, not a converged practice. The seven-way divergence is the field admitting it does not know.

**arXiv 2602.14690 — "Harness Engineering for Agentic AI Coding Tools: An Exploratory Study"** (Feb 2026, v5). Covers Claude Code, GitHub Copilot, Cursor, Gemini, Codex. Eight configuration mechanisms identified; empirical study of **2,853 GitHub repositories**.

- Context Files dominate the configuration landscape and are often the **sole** mechanism in a repository; `AGENTS.md` is emerging as an interoperable cross-tool standard.
- **Few repositories adopt advanced mechanisms such as Skills and Subagents.**
- Skills predominantly rely on **static instructions rather than executable scripts**.
- Distinct configuration practices are forming per tool, with Claude Code users employing the broadest range.

Read: the mechanisms this report evaluates (#8, #10) are **largely unadopted in the wild**, so "best practice" claims about them rest on very little field evidence.

## 4.4 Answer to Q4

Mechanisms with real independent measurement: **prompt caching (1), shell-over-catalog (2), PTC (3), observation granularity (4), compaction policy (5), wire format (6), local triage (7), sub-agent isolation (8, partial), skills-as-code (10, null result)**.

Mechanisms with only vendor measurement: **whole-harness orchestration (9)**.

Mechanisms with **no measurement at all** despite universal implementation: **tool-result truncation (11), lazy/paged tool discovery (12)**.

And the governing correction: **none of these should be reported in tokens.** Report cost per successful task.

---

# Q5. nano-rlm — the actually implemented compaction policy and prompt structure

Read from source at `main`. Files inspected: `src/rlm/compaction.py` (7,321 B), `src/rlm/engine.py` (57,032 B), `src/rlm/config.py` (6,288 B), `src/rlm/prompt.py` (24,396 B), `README.md` (32,961 B). Repo inventory via the GitHub trees API (40 .py/.toml/.md files; largest are `supervisor.py` 56,269 B and `engine.py` 57,032 B).

## 5.1 Constants, verbatim from compaction.py

```python
RESERVE_TOKENS = 16_384
"""Compact when this many tokens remain below the model context window."""

TOOL_OUTPUT_MAX_BYTES = 20_000
"""Middle-out truncation budget for one tool result before it enters the conversation."""

def default_threshold(context_window: int) -> int:
    """Leave a fixed reserve below the window; small windows keep at least half."""
    return max(context_window - RESERVE_TOKENS, context_window // 2)

def estimated_tokens(chars: str) -> int:
    """Rough token count at four characters per token."""
    return (len(chars) + 3) // 4
```

Two consequences worth noting:
- The `context_window // 2` floor means a small-window model keeps **at least half** its window rather than being driven to a 16k-remainder that may exceed the window itself.
- Token estimation is a flat **4-chars-per-token heuristic**, so the trigger threshold is **approximate, not tokenizer-exact**. On code-heavy or non-English content the real token count can diverge materially from the estimate.

## 5.2 Two trigger paths

### Proactive — `_should_compact()`, engine.py:1037

```python
def _should_compact(
    self, messages: list[dict], usage: TokenUsage, extra_text: str = ""
) -> bool:
    if self.summarize_at_tokens is None or not self._can_compact():
        return False
    # A spent tree cap stops the session next iteration: don't burn a model
    # call summarizing a conversation that is about to end. (The reactive
    # overflow path stays available - that call was already permitted.)
    if self._spent_tree_cap() is not None:
        return False
    if not compactable(messages):
        return False
    tokens = usage.total + estimated_tokens(extra_text)
    return tokens >= self.summarize_at_tokens
```

Three details a paraphrase would miss:
1. It counts **`extra_text`** — the pending tool output — *before* it enters the conversation, not just current usage. The check is forward-looking.
2. A **spent tree cap suppresses proactive compaction**: don't spend a model call summarizing a session about to terminate. The reactive path stays available because that call was already permitted.
3. `compactable()` requires history beyond the system message and the first user message; otherwise there is nothing to reclaim.

Threshold discovery (`discover_threshold`, compaction.py) calls `client.models.list()` — with `max_retries=0, timeout=10.0` when the client supports `with_options`, to bound startup latency — and reads the model card's `model_extra` for any of `max_model_len`, `context_length`, `context_window`, `max_context_length`. Cached per `(base_url, model)`. A transient listing failure returns `None` **without poisoning the cache**: *"A transient listing failure must not disable compaction for the rest of the process - leave the cache empty so the next engine retries."*

**Failure mode worth flagging**: if the provider advertises no context window and no explicit `summarize_at_tokens` is configured, **proactive compaction never runs**. Only the reactive path remains.

### Reactive — `is_context_overflow()`, compaction.py

```python
def is_context_overflow(error: APIStatusError) -> bool:
    details = f"{error} {error.body or ''}"
    # An overflow is deterministic: a 400, or a 413 for a byte-size cap.
    return error.status_code in (400, 413) and any(
        marker in details.casefold() for marker in _OVERFLOW_MARKERS
    )
```

The nine markers, each commented with its provider in the source:

| Marker | Provider |
|---|---|
| `context_length_exceeded` | OpenAI error code; OpenRouter relays the raw body |
| `exceeds the context window` | OpenAI Responses/Completions |
| `reduce the length of the messages` | OpenAI chat; Groq words it the same |
| `maximum context length` | vLLM, Mistral |
| `prompt is too long` | Anthropic |
| `request_too_large` | Anthropic HTTP 413 byte-size overflow |
| `request entity too large` | HTTP proxies, 413 |
| `exceeds the maximum number of tokens` | Google |
| `maximum prompt length is` | xAI |

**This is string-matching against vendor error prose.** It is carefully done and well-documented, but it is structurally brittle: if a provider rewords an error message, overflow silently stops being detected and the run hard-fails instead of compacting.

## 5.3 Budgets (config.py)

| Field | Default | Source docstring / note |
|---|---|---|
| `max_total_tokens` | **1_000_000** | *"Tree-total budget of NEW tokens across the whole recursive session tree, live: each model call contributes its completion plus uncached prompt tokens (the cached context...)"*. Exhaustion sets `stop_reason=max_total_tokens` and blocks further sub-agent spawns. *"This budget is the default terminator (compaction never runs out of context...)"* |
| `max_total_turns` | (set) | *"Tree-total turn budget (one turn = one work-loop model call, any engine; compaction..."* — compaction calls excluded |
| `compaction` | `True` | *"Compact the context once it outgrows `summarize_at_tokens` (and recover from...)"* |
| `summarize_at_tokens` | `None` | *"None = auto-discover from the provider's advertised context window (~16k tokens of headroom); when the provider advertises no window, compaction stays overflow-reactive only."* |
| `max_compactions` | `None` (unlimited) | *"every compaction cycle itself spends new tokens, so `max_total_tokens`"* is the real bound |
| `max_compaction_attempts` | **5** | *"Summary-generation attempts within one compaction cycle."* |
| `max_tool_output_bytes` | 20,000 | *"Byte budget for a single tool result entering the conversation (middle truncation...)"* |
| sub-agent spawn cap | `None` (uncapped) | *"Tree-total cap on sub-agent spawns... `max_total_tokens`"* bounds it |

**Doc/code mismatch found by reading both**: `README.md` line 174 states *"after three failed attempts the run ends cleanly."* The code default is **5** — `config.py:84` `max_compaction_attempts: int = Field(default=5, gt=0)`, consumed at `engine.py:1187` as `for _ in range(self.max_compaction_attempts)`. The README understates the retry budget.

## 5.4 Tool-output truncation (runs before, and independently of, compaction)

```python
def truncate_tool_output(text: str, max_bytes: int = TOOL_OUTPUT_MAX_BYTES) -> str:
    """Keep the head and tail of an oversized tool result and say what was cut."""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    keep = max_bytes // 2
    head = data[:keep].decode("utf-8", errors="ignore")
    tail = data[-keep:].decode("utf-8", errors="ignore")
    return (
        f"Warning: truncated output (original token count: {estimated_tokens(text)})\n"
        f"Total output lines: {text.count(chr(10)) + 1}\n\n"
        f"{head}\n[... {len(data) - 2 * keep} bytes truncated ...]\n{tail}"
    )
```

Middle-out: 10,000 bytes head + 10,000 bytes tail. `errors="ignore"` means a multibyte character split at the boundary is dropped rather than producing mojibake. The warning preserves the **original estimated token count and total line count**, so the model knows the scale of what it lost — a small but real design choice: truncation is *announced*, not silent.

Separately, supervisor shell jobs cap `.text` at **16 KiB** (first and last 8 KiB around a marker naming the omitted byte range) *"so the first failure and the final summary both survive without piping through `tail`"*, with up to **16 MiB retained per job** and cursor-paged retrieval: `chunk = await job.read(cursor=8192, max_bytes=65536)` returning `.text`, `.next_cursor`, `.done`, `.truncated`.

## 5.5 The compaction cycle — `_compact_branch()`, engine.py:1151

Docstring: *"Ask the model for a handoff summary and replace the session context. Installs the session context as `[system, user(framing + summary)]` while preserving the IPython kernel. A summary attempt is housekeeping, not a work turn: it does not count toward `max_total_turns`. Its tokens still land in `_total_usage` for cost accounting and count toward token budgets."*

Steps as implemented:

1. **Prompt assembly**: `CHECKPOINT_PROMPT`, plus `REPL_NOTE` if a REPL exists, plus — if there are kernel notices — `"\n\nPreserve this latest kernel recovery warning in the continuation summary:\n" + self._prompt_kernel_notices[-1]`.
2. **Model call** with `checkpoint=True`, which sets `tool_choice: "none"`. **Active tool schemas are still forwarded.** The docstring gives the reason: *"Forwarding active tool schemas preserves vLLM's system-message tool block and prime-rl's trajectory extension property across compaction."* Compaction shape here is constrained by **RL-training compatibility**, not inference alone — this harness is designed to be trained against.
3. **Acceptance test**: `if choice.finish_reason == "stop" and not message.tool_calls and text:`. **Reasoning content is explicitly excluded** — *"Reasoning never enters the summary: only the reply's final text counts, so a reply that lives entirely in the reasoning channel is resampled like an empty one."*
4. **Overflow during the checkpoint itself**: retry against `base = messages[: self._last_good]` — the newest state that passed a threshold check, *"by definition a state with a full reserve of room, so a checkpoint over it fits."*
5. **Exhaustion**: after `max_compaction_attempts` (5) → `raise CompactionFailed(f"no usable summary after {self.max_compaction_attempts} attempts")` → `stop_reason = "compaction_failed"`, `final_text = "[context exhausted: compaction failed]"`. Ends cleanly; no infinite loop. Exception path distinguishes `cancelled` from `failed` in the semantic graph.
6. **Context replacement**: exactly **two messages** — `self.session.replace_context([system_msg, compaction_message], reason="compaction")`.

Accounting detail from `_call_model`: when `checkpoint=True`, `self._own_turns` is **not** incremented and `self._supervisor.record_usage(new_tokens)` is called instead of `record_call(new_tokens)`. Compaction spends budget without spending turns.

## 5.6 What CHECKPOINT_PROMPT actually asks for

Not "summarize the conversation." Verbatim:

```
Create a concise continuation summary for the current task.
Preserve what is needed to resume accurately:
- The user's objective, exact requirements, constraints, and unresolved decisions.
- Completed work, evidence/results, important paths or sources, and remaining next steps.
- Ongoing orchestration: child names/IDs, assignments and pending follow-ups; Bash job IDs,
  commands and last-known outcomes; subscriptions/targets; unread or retrieved events still
  requiring action; output cursors and useful history message/window references.
- Any interrupted or uncertain operation and side effects that must be inspected before retrying.

Include runnable commands, test filters, or concrete edits when relevant and known.
Use only APIs/tools actually available; do not invent edits, results, resource IDs, or state.
Distinguish last-observed state from assumptions: background work may progress during compaction.
If resources are no longer needed, note that they can be cancelled; do not imply they were cancelled.

Summarize from the existing conversation. Do not call tools. Reply with the summary as plain text.
```

Three anti-hallucination clauses are doing real work here: no inventing resource IDs or results; distinguish last-observed from assumed because **background work progresses during compaction**; and do not imply cancellation that did not happen.

`REPL_NOTE` (appended when a REPL exists):

> "Compaction itself preserves the IPython kernel and supervisor-owned resources. Record useful Python variable names and what they contain, but account for any recovery notice: variables lost in a restart must not be described as still available. Conversation history remains queryable. Preserve resource names/IDs so handles can be recovered through the registries. After compaction, refresh resource metadata and inbox state before deciding whether to repeat work or wait."

`SUMMARY_FRAMING` (prepended to the surviving message):

> "The earlier conversation was compacted. The summary below preserves task progress, constraints, and references for continuing. Compaction does not finish or restart background work. Treat resource statuses as last-observed: refresh metadata and inbox state with the available tools. Consult original history for exact instructions or missing evidence, and do not duplicate work merely because its full conversation is absent."

## 5.7 The design choice that matters most

The compacted user message ends with an explicit pointer back to the full record:

> `Full conversation history is available in {session_dir}/messages.jsonl. Use `from rlm import history; h = await history()` to inspect `h.windows[w].messages[i]`, `h.messages[i]`, or `h.user_messages()`. Search or read relevant records with Python when the summary lacks context. The log includes failed attempts: prompt_rollback.prompt_id identifies the user record whose attempt was rolled back.`

**Compaction here means eviction from the prompt, not forgetting.** The supporting machinery:

- Append-only `messages.jsonl` per agent; a session refuses to reopen an existing ledger for writing.
- **Closed windows never change.** Each `context_window` record declares a zero-based `window` index, a `reason` (`start`, `compaction`, or `rollback`), and the ordered `message_indices` seeding it.
- **Full tool outputs and shortened context versions carry separate indices**; the shortened record links via `source_message_index`. Both are addressable.
- The **IPython kernel survives compaction intact** — all variables, imports, and in-memory data. The model is instructed to name important variables in the summary.
- `h.user_messages()` returns original user inputs distinct from generated summaries and supervisor notices.
- Rollback opens a new window containing the restored context, preserving addresses in the failed window.

**Assessed against the Governance Decay result (2606.22528)**: this is the right architecture but **not the measured fix**. That paper found Constraint Pinning — structurally quarantining the constraint from lossy compaction — reaches 0% violation. nano-rlm instead offers **recovery by agent initiative**. The agent must know to go look. Governance Decay's central finding is precisely that a dropped constraint **leaves no trace prompting the agent to look for it** (survived → 0% violation, dropped → 38%, with the agent behaving confidently in both cases).

**No measurement exists that nano-rlm's recovery path actually fires in practice.** This is the single highest-value experiment someone could run on this harness.

## 5.8 Prompt structure — `build_system_prompt()`, prompt.py

Assembled as `"\n\n".join(parts)`, conditionally, in this order:

1. `task_instructions` (or fallback `"You are an agent. Complete the user's task using the available tools."`)
2. `extra_instructions` if present
3. `## Agent context`
4. Supervisor identity as JSON: `{id, parent_id, name, persistent}`
5. Role framing — if `depth > 0`: *"You are a sub-agent. Work on the task delegated by your immediate parent; do not widen its scope. Return a self-contained answer with relevant evidence, sources, paths, and uncertainties."* Plus a persistent/non-persistent lifecycle note. If depth 0: *"You are the root agent. A final answer returns control to the caller. Do not claim completion while required work remains pending."*
6. `Working directory: {cwd}`
7. `Conversation log: {session_dir}/messages.jsonl`
8. `"Available native tools: " + names + ". Call at most one native tool per model step."`
9. **If ipython active**: `RUNTIME_PROMPT`, `HISTORY_PROMPT`, `IPYTHON_CONTROL_PROMPT`, `KERNEL_PACKAGES_PROMPT`
10. `AGENT_PROMPT` (delegation) if `allow_recursion`, else *"Delegation is disabled at this depth. Work directly with your available tools."*
11. Parent/child messaging paragraph (depth-dependent: `rlm.agent.send_to_parent` for children; *"You have no parent"* for root)
12. Native bash note / native edit note if those tools are active
13. `Local skills live under {skills_dir}. Read their SKILL.md files when helpful.`
14. `"Installed skills (pre-imported): " + names + ". Each is async; use help(skill) for its signature."` followed by one curated line per built-in skill from `BUILTIN_SKILL_PROMPTS`
15. Shell-enabled skills list
16. `GIT_HISTORY_GUARD_PROMPT` if a shell tool is active and `allow_git` is false

`BASE_TOOLKIT` surfaced in the prompt so the agent does not probe: `requests, httpx, yaml, tomli, dotenv, pandas, numpy, scipy, bs4, lxml, pydantic`. Comment: *"keep in sync with the dependency list."*

## 5.9 Correction to a premise in the brief

**nano-rlm is not strictly a one-tool harness.** From prompt.py:

```python
parts.append(
    "Available native tools: "
    + ", ".join(
        [tool.name for tool in active_tools] + (["wait"] if has_ipython else [])
    )
    + ". Call at most one native tool per model step."
)
```

`src/rlm/tools/` contains `bash.py`, `fetch.py`, `ipython.py`, `git_block.py`, `skills.py`, `registry.py`, `base.py`. `prompt.py` branches on `_has_tool(active_tools, "bash")` and `_has_tool(active_tools, "edit")`, and `_builtin_skill_prompt()` swaps the bash guidance when the native bash tool is *also* active (`BASH_SKILL_WITH_TOOL_PROMPT` vs `BASH_SKILL_PROMPT`) — *"the skill is then the secondary shell path."*

So: the canonical RLM configuration is **ipython + the native `wait` tool** (minimum two). bash, edit, fetch, and search exist as **both** native tools and pre-imported IPython skills, selectable by configuration.

**The brief's other three premises verified exactly**: 16,384-token reserve below the context window; 1,000,000-token tree-wide default budget; kernel state survives compaction.

## 5.10 Token-efficiency instructions embedded in the prompt prose

The harness pushes the model toward programmatic filtering **rhetorically**, on top of enabling it structurally:

- From `RUNTIME_PROMPT`: *"Prefer `grep -n`, `sed -n 'A,Bp'`, and `head` over printing whole files; print the parts needed for your next decision."*
- From `RUNTIME_PROMPT`: *"Act on the exit code before reading the text: a nonzero .exit_code means the command failed even if .text looks plausible, so branch on it rather than only printing it."*
- From `HISTORY_PROMPT`: *"Recover exact instructions and evidence by searching/selectively printing records, not the entire ledger."*
- From `RUNTIME_PROMPT`: *"Use Python to program over tools and coordinate concurrent work."*
- From `SEARCH_SKILL_PROMPT`: *"To cover several angles at once, fan out with `asyncio.gather(search(...), search(...))`."*

This is the Prime Intellect thesis implemented as prompt engineering. **It is unmeasured** — no ablation exists comparing this harness with and without these instructions.

---

# SOURCES CONSULTED

## Source code, read directly (GitHub `main` branch, raw.githubusercontent.com)

| Path | What it contained |
|---|---|
| `PrimeIntellect-ai/nano-rlm/src/rlm/compaction.py` | `RESERVE_TOKENS = 16_384`; `TOOL_OUTPUT_MAX_BYTES = 20_000`; nine `_OVERFLOW_MARKERS` with provider comments; `default_threshold`, `discover_threshold`, `_model_context_window`, `truncate_tool_output`, `estimated_tokens`, `compactable`, `is_context_overflow`, `CompactionFailed`; `CHECKPOINT_PROMPT`, `REPL_NOTE`, `SUMMARY_FRAMING` verbatim |
| `.../src/rlm/prompt.py` | `build_system_prompt()` assembly order; `BASE_TOOLKIT`; `RUNTIME_PROMPT`, `AGENT_PROMPT`, `HISTORY_PROMPT`, `IPYTHON_CONTROL_PROMPT`, `KERNEL_PACKAGES_PROMPT`; per-skill prompts (bash/edit/search/fetch); `GIT_HISTORY_GUARD_PROMPT`; `PROJECT_ENV_PROMPT`; `_has_tool`, `_builtin_skill_prompt` |
| `.../src/rlm/engine.py` | `_should_compact` (line 1037), `_can_compact` (1015), `_spent_tree_cap` (1021), `_call_model` checkpoint path (1051), `_complete` retry cycle (1102), `_compact_branch` (1151); truncation call site (879); compaction trigger (899) |
| `.../src/rlm/config.py` | `max_total_tokens=1_000_000`, `max_compaction_attempts=5`, `max_compactions=None`, `summarize_at_tokens=None`, `compaction=True`, tool-output byte budget, spawn caps — all with docstrings |
| `.../README.md` | Stated policy (source of the 3-vs-5 attempts mismatch); ledger/window semantics; history API |
| GitHub trees API (`/git/trees/main?recursive=1`) | Repo inventory: 40 .py/.toml/.md files; `supervisor.py` 56,269 B, `engine.py` 57,032 B, `prompt.py` 24,396 B, `tools/ipython.py` 23,583 B |

## Vendor publications

| URL | What it contained |
|---|---|
| anthropic.com/engineering/code-execution-with-mcp | The 150,000→2,000 token / 98.7% claim; the `./servers/<name>/<tool>.ts` filesystem tree; progressive disclosure; `search_tools` with detail-level parameter; 10,000-row spreadsheet filtering example; Slack polling loop example; PII tokenization; state persistence and skills; their own sandboxing-overhead caveat |
| blog.cloudflare.com/code-mode (2025-09-26) | "Code Mode"; MCP→TypeScript API conversion; Agents SDK `codemode()` helper; tool-call special-token anatomy; the Shakespeare-in-Mandarin analogy; **zero numerical results** |
| primeintellect.ai/blog/prime-agent | The PTC token claim verbatim; RLM + Continual Harness abstractions; append-only JSONL session history with `/tree`; `compact.run()` and `compact.status()`; the CRUD harness surface (`create_prompt_note`, `create_memory`, `create_skill`, `create_subagent`); `/refine` two-phase pipeline; persistent sub-agents; goals/heartbeats/autonomous mode; gate command; ARC-AGI-3 scaling charts; OOLONG comparison table; Factorio and MazeBench case studies |

## arXiv papers — all IDs verified to resolve via the API `id_list` endpoint with matching titles

| arXiv ID | Title | Role in this report |
|---|---|---|
| 2609.11999 | Is Bash All You Need? An Empirical Study of Tool Interfaces for Enterprise Digital Worker Agents | **Primary Q1 evidence.** Microsoft + CMU. Table 1 (full), Table 3 (shell stats), Table 6 (PTC deltas), Discussion |
| 2608.06370 | The Bitter Lesson of Tool Calling | **Primary Q1 evidence.** N≈26 token crossover, parallelism/chaining/context-rot ablations, filesystem-discovery collapse, four limitations |
| 2608.01326 | Context Compaction Theory | **Primary Q2.** Communication-complexity equivalence; Anthropic endpoint case study at random guess; Table 2 |
| 2606.22528 | Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents | **Primary Q2.** ConstraintRot; aggressiveness curve; strategy sweep; real-harness reproduction; Constraint Pinning |
| 2607.12161 | Token Reduction Is Not Cost Reduction | **Governing caveat for Q4.** 38.4% tokens / +6.8% cost; r=0.15; cache-dominance decomposition |
| 2601.06007 | Don't Break the Cache: An Evaluation of Prompt Caching for Long-Horizon Agentic Tasks | Q4 #1. 41–80% cost, 13–31% TTFT, 3 providers, 500+ sessions |
| 2605.07134 | Region4Web: Rethinking Observation Space Granularity for Web Agents | **Primary Q3.** −43% obs tokens / +2.3pp; granularity ablation; task-scale decomposition; failure attribution |
| 2607.04334 | Do GUI Agents Believe Their Eyes? Diagnosing State-Belief Reliance on Pixels versus Structure | Q3. 735 probes, PFG, 0.88 stale-structure deference, ≤0.03 self-recovery |
| 2605.29676 | Notation Matters: A Benchmark Study of Token-Optimized Formats in Agentic AI Systems | Q4 #6. TOON/TRON measured inside end-to-end agentic loops |
| 2604.12301 | Local-Splitter: A Measurement Study of Seven Tactics for Reducing Cloud LLM Token Usage on Coding-Agent Workloads | Q4 #7. Seven tactics, 45–79%, workload dependence |
| 2607.06906 | The Harness Effect: How Orchestration Design Sets the Token Economics of Enterprise Agentic AI | Q4 #9. **Vendor (Writer).** −41% cost, −38% tokens, harness leverage r=0.99 |
| 2609.09233 | Subagents vs Agent Skills: Executing Reusable Knowledge for Long-Horizon Agentic Tasks | Q4 #8. Subagent isolation vs in-context skill loading |
| 2606.13643 | Recursive Agent Harnesses | Q4 #8. Codex 71.75%→81.36% on Oolong-Synthetic, GPT-5 fixed, 199 samples |
| 2604.03515 | Inside the Scaffold: A Source-Code Taxonomy of Coding Agent Architectures | Architecture context. 13 scaffolds at pinned commits, 7 compaction strategies, 0–37 tools |
| 2602.14690 | Harness Engineering for Agentic AI Coding Tools: An Exploratory Study | Adoption reality. 2,853 repos; Skills mostly static instructions |
| 2603.05344 | Building Effective AI Coding Agents for the Terminal: Scaffolding, Harness, Context Engineering, and Lessons Learned (OPENDEV) | Q4 #12. Lazy tool discovery, adaptive compaction — named, unmeasured |
| 2607.05378 | CompactionRL: Reinforcement Learning with Context Compaction for Long-Horizon Agents | Q2. +7.0 SWE-bench Verified, +3.1 Terminal-Bench 2.0 |
| 2605.23296 | Parallel Context Compaction for Long-Horizon LLM Agent Serving | Q2. Compaction volume uncontrollable by prompt; run-to-run variance |
| 2512.24601 | Recursive Language Models | Cited by Prime Intellect. GPT-5 median: +26% vs compaction, +130% vs CodeAct w/ sub-calls, +13% vs Claude Code; RLM-Qwen3-8B +28.3% |
| 2605.09998 | Continual Harness: Online Adaptation for Self-Improving Foundation Agents | Cited by Prime Intellect. Gemini Plays Pokemon; reset-free online adaptation |
| 2608.23552 | Prime Agent: A Self-Improving RLM Harness | Vendor. ARC-AGI-3 RHAE Best@1 30%→95.5% |
| 2402.01030 | Executable Code Actions Elicit Better LLM Agents (CodeAct, ICML 2024) | Prior art. Up to 20% success rate, 17 LLMs, API-Bank. **No token claim** |
| 2305.18323 | ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models | Prior art. 5× token efficiency, +4% HotpotQA |

**Papers surfaced in searches but not used as evidence** (listed for audit completeness): 2605.03195 Terminus-4B; 2601.02365 FUSE; 2604.23938 TSAssistant; 2607.29422 AgenticRepair; 2602.04634 WideSeek-R1; 2608.01507 Deep Agentic Search; 2609.20519 SoL-Pi; 2601.02577 Orchestral AI; 2607.21653 Molt; 2608.00101 Agentic Coding in the Wild; 2605.24775 PRIMA; 2606.19926 MemGUI-Agent; 2508.13024 WebMall; 2604.20940 Sema; 2608.24898 MCP-Driven Accessibility Tree Standardization; 2411.17465 ShowUI; 2608.24848 BrowserForge; 2507.16704 Screen2AX; 2604.08516 MolmoWeb; 2410.13824 Harnessing Webpage UIs; 2603.04364 Dual-Modality Adversarial Safety Training; 2506.14866 OS-Harm; 2607.10079 MAG; 2410.05243 Universal Visual Grounding; 2512.15813 CodeMem; 2605.05247 DADL; 2506.03691 LogSage; 2606.07074 SlimSearcher; 2609.12839 Context Segmentation in SLMs; 2511.07426 Network and Systems Performance of MCP-Enabled LLM Agents; 2606.29537 OSWorld 2.0; 2604.07911 Dynamic Attentional Context Scoping; 2606.00953 When Parallelism Pays Off; 2603.21278 Conversation Tree Architecture; 2605.08478 When Independent Sampling Outperforms Agentic Reasoning; 2605.24785 PANDO; 2606.11869 Agents All the Way Down; 2606.13361 Can I Buy Your KV Cache?; 2609.00749 ContextPipe; 2608.23992 Hybrid Semantic Tool Discovery; 2607.22689 Beyond Sequential Interaction; 2605.12294 Executable Agentic Memory for GUI Agent; 2609.16635 EchoPath.

## Tooling note

WebSearch was unavailable (HTTP 400) for this lane. All discovery ran through the arXiv API full-text search endpoint; page text via r.jina.ai; source via raw.githubusercontent.com and the GitHub API. **Semantic Scholar returned HTTP 429 (rate-limited) on every attempt**, so citation-count-weighted ranking was unavailable.

---

# KNOWN GAPS

1. **No four-way observation-space comparison exists.** AXTree vs raw DOM vs screenshot vs code-mediated access, measured on both token cost and task success in one controlled setup. Four targeted arXiv searches (listed in §3.3) found nothing; one returned zero results entirely. Do not let downstream writing imply this comparison was found.

2. **Tool-result truncation has no isolating measurement.** Every harness implements it (nano-rlm at 20 KB middle-out, 16 KiB for shell jobs). Nobody has published an ablation of its effect on tokens or task success. CLAIMED only.

3. **Lazy / paged tool discovery has no isolating measurement.** OPENDEV (2603.05344) names it as a design dimension; the paper is an architecture description, not an evaluation.

4. **No ablation isolates PTC within Prime Agent.** The ARC-AGI-3 30%→95.5% result bundles PTC, Continual Harness, persistent sub-agents, and `/refine`. The specific claim in the brief — that PTC is what saves the tokens — is unmeasured as stated by its own author.

5. **CodeAct, the canonical code-as-action citation, publishes no token-efficiency number.** Its claim is success rate (up to 20%). Anyone citing CodeAct for token savings is citing something not in the paper.

6. **Both crux Q1 papers are unreplicated, and one is first-party.** 2609.11999 is Microsoft evaluating interfaces for its own Copilot Studio line, which ships the shell-based offering its result favors — methodology sound, table internally consistent, but apply the vendor discount. It cites 2608.06370 as "Patel et al. 2026" and asserts independence. Neither result has been reproduced by a third party.

7. **Everything here is model-generation-bound with a short shelf life.** 2609.11999: *"As frontier models evolve, these recommendations may not carry over to later releases in either family."* 2608.06370 finds PTC performance *tracks model capability across release generations* — meaning the N≈26 crossover point itself will move with model releases. Treat every number as dated 2024–2026.

8. **Governance Decay's severity depends on aggressive compaction being the production default.** The authors configure *"a tight word budget, matching production guidance."* A harness compacting at 300-word budgets sits at 7% violation on their curve, not 28%. Check your own budget before importing the headline number.

9. **The Context Compaction Theory case study is a deliberate worst case.** Set membership is adversarial to summarization by construction — it is precisely the query class with provably high one-way communication complexity. The authors say so explicitly. It is a real result about a shipped endpoint; it is not a claim about typical agent workloads, and n=3 seeds on one task with one model.

10. **Token-based findings in Q3 and Q4 #6 are unvalidated as cost findings.** Neither Region4Web nor Notation Matters reports billed cost. Given 2607.12161's r=0.15, their token reductions may not translate.

11. **Sub-agent context isolation lacks headline numbers.** 2609.09233 states a directional conclusion (subagents beat in-context skills under clear I/O contracts, at coordination-token cost) without a quantified tradeoff in the abstract. The full-text numbers were not retrieved for this lane.

12. **Semantic Scholar rate-limiting means non-arXiv venues may be under-covered.** ACL/ICML/NeurIPS proceedings not mirrored on arXiv would not have surfaced.
