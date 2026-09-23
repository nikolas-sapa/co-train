# 05 — Delta from user-supplied inputs (2026-09-23)
Sources: a coding-agent tier-list post, and a Perplexity deep-research report on benchmarks.
Only the parts that are NEW or that CORRECT the existing corpus are recorded here.

---

## Part 1 — The finding my bench lane should have caught and didn't

### Berkeley RDI, "How We Broke Top AI Agent Benchmarks"
`rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/`, fetched 2026-09-23. Verbatim:

> "We built an automated scanning agent that systematically audited **eight among the most prominent
> AI agent benchmarks** — SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, and
> CAR-bench — and discovered that **every single one** can be exploited to achieve near-perfect
> scores without solving a single task. No reasoning. No capability. Just exploitation of how the
> score is computed."

> "Zero tasks solved. Zero LLM calls (in most cases). Near-perfect scores."

| Benchmark | Tasks | Score achieved | Exploit |
|---|---|---|---|
| Terminal-Bench | 89 | **100%** | Binary wrapper trojans (a fake `curl`) |
| SWE-bench Verified | 500 | **100%** | Pytest hooks force all tests to pass (a 10-line `conftest.py`) |
| SWE-bench Pro | 731 | **100%** | In-container parser overwrite |
| WebArena | 812 | **~100%** | Config leakage + DOM injection + prompt injection |
| FieldWorkArena | 890 | **100%** | Validation never checks answer correctness |
| CAR-bench | all | **100%** | Reward components skipped entirely |
| GAIA | 165 | **~98%** | Public answers + normalization collisions |

The WebArena exploit is the cleanest illustration of R1: *"Navigating Chromium to a `file://` URL
reads the gold answer directly from the task config."* The agent is scored on state it can read.

**Three real-world incidents in the same post, not synthetic exploits:**
- **IQuest-Coder-V1** claimed 81.4% on SWE-bench. Researchers found **24.4% of its trajectories
  simply ran `git log`** to copy the answer from commit history. Corrected score 76.2%. *"The
  benchmark's shared environment made the cheat trivial."*
- **OpenAI dropped SWE-bench Verified** after an internal audit found **59.4% of audited problems
  had flawed tests** — *"meaning models were being scored against broken ground truth."*
- **KernelBench**: `torch.empty()` returns stale GPU memory that *"happens to contain the reference
  answer from the evaluator's prior computation — zero computation, full marks."*

### What this changes in `lanes/bench.md`

**R31 (verify the verifier both ways) is promoted to the single highest-value rule on the list.**
Previously it rested on LEGO-RL's ~2.5% broken-verifier rate in a screened pool. OpenAI found
**59.4% flawed tests in SWE-bench Verified** — the benchmark whose entire selling point was that
humans had verified it. Broken ground truth is not a 2.5% tail risk; in at least one flagship
benchmark it was the majority case.

**R1/R2 (never read the score from agent-writable state; isolate the verifier) graduate from
single-domain to systematically confirmed.** RECEIPT demonstrated it in web security. RDI
demonstrates it across eight benchmarks in four domains, with named exploits and a scorecard
showing 73-100% exploit coverage on all of them.

**New corollary — R1a: the exploit surface includes the runtime, not just the application.**
Three of RDI's exploits are below the task layer entirely: a fake binary on `$PATH`, a pytest
plugin hook, and uninitialized GPU memory. An environment designer who only audits *application*
state will miss all three. Enumerate: `$PATH`, test-framework plugin hooks, shared containers,
uninitialized memory, and the filesystem path the verifier itself reads from.

**The "zero LLM calls" detail matters most.** These are not capable agents outsmarting a verifier.
They are trivial scripts. A verifier that a 10-line `conftest.py` defeats will be defeated
accidentally, by an RL policy exploring at random, long before any model is smart enough to plan it.

### HORIZON — verified, and it is not what the title suggests
arXiv **2604.11978** resolves as *"The Long-Horizon Task Mirage? Diagnosing Where and Why Agentic
Systems Break."* Consistent with the report's summary (degradation past 20-50 steps, error
accumulation, poor recovery, intrinsic horizon H*). Complements `bench.md` §2 on why pass/fail
scoring hides degradation. Not yet read in full — **open item.**

### What the Perplexity report did NOT add
Its τ-bench `pass^k`, MCPAgentBench distractor-tools, BrowseComp-Plus fixed-corpus, AgentDojo,
AgentHarm, OSWorld, Vending-Bench, METR, AidanBench, and LiveBench material is already covered in
`lanes/bench.md` and `lanes/browser.md`, in several cases with fuller numbers (the full AgentDojo
per-model/per-defense ASR table, for instance). Its main contribution is **RDI**, which is decisive.

---

## Part 2 — Harnesses the research missed, and a scale check

Four repos named in the tier list were absent from `01-primary-sources.md`. All verified live,
all pushed 2026-09-23.

| Repo | Stars | Lang | License | Description |
|---|---|---|---|---|
| `NousResearch/hermes-agent` | **248,250** | Python | MIT | "The agent that grows with you" |
| `anomalyco/opencode` | **209,562** | TypeScript | MIT | "The open source coding agent." |
| `can1357/oh-my-pi` | 32,914 | TypeScript | MIT | "Coding agent with the IDE wired in" (the tier list's S pick; a pi fork) |
| `vercel-labs/fx` | 3,135 | Zig | Apache-2.0 | "Unix like coding agent" |

For comparison: `earendil-works/pi` 107,168 · `PrimeIntellect-ai/prime-agent` 21,048 ·
`PrimeIntellect-ai/nano-rlm` 62.

### Scale check — stars do not mean fork-suitability

`hermes-agent` is the most-starred agent repo found anywhere in this research and is Python + MIT,
which on paper makes it a candidate base. **It is not one.** Tree inspection: **6,882 Python files,
14,684 blobs.** Largest modules are platform adapters — `plugins/platforms/telegram/adapter.py`
(434 KB), `discord` (378 KB), `slack` (359 KB), plus `gateway/run.py` (329 KB) and a TUI gateway
test at 813 KB.

That is a **product platform**, not a harness. Compare `nano-rlm`: 20 modules, ~200 KB total.

**Conclusion: nano-rlm remains the right fork target for this project**, on the same reasoning as
before (minimal, Python, explicit ACP training contract, `verifiers` already speaks to it). The
248k-star repo is the wrong tool for a co-training experiment despite being 4,000x more popular.

Worth noting for the compaction thread: hermes-agent carries `agent/context_compressor.py` (319 KB)
and `agent/conversation_compression.py` (243 KB) — by far the largest compaction implementation
seen in this research. If the compaction policy in `lanes/tokens.md` needs a second reference
beyond nano-rlm's, that is where to look.

`oh-my-pi` is TypeScript like its parent, so it inherits pi's language mismatch with the RL stack.
Its value here is as a **behavior reference** for a thick tool surface (LSP, debugger, subagents,
60+ providers), not as a base.

### Not verified
- The tier list's rankings are one person's opinion with no methodology; treated as a **discovery
  list of repos**, not as evidence about quality. The reply thread's own correction (Hermes omitted
  despite being the most-starred) illustrates the problem.
- `oh-my-pi`, `fx`, and `opencode` internals were not read. Only metadata was checked.
- Star counts are engagement, not usage — the same caveat applied to x402 in `lanes/browser.md`.
