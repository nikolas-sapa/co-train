# 01 — Primary sources sweep
Date: 2026-09-19 · Method: agent-reach (github=gh CLI, web=Jina Reader; exa_search OFF)

## Headline
The model-harness co-training stack **already exists and is open source**. Prime Intellect
shipped every layer. The build decision changes from "assemble the plumbing" to
"bring my own harness variant + my own environment and plug into an existing seam."

---

## The seam (most important finding)

`nano-rlm` README, "Agent Client Protocol" + "Session Directory" sections:

> "RLM's ACP surface is a versioned training contract. `initialize` advertises the exact
> `ai.prime.rlm/contract-v1` marker in its response `_meta`; clients must require it, then
> provide one complete `ai.prime.rlm/runtime-v1` object in `session/new._meta`."

> "**Verifiers, the ACP consumer**, records model requests/responses through its interception
> endpoint and receives semantic links and metrics over ACP."

> "These artifacts are consumable for debugging, visualization, or **training-data extraction**."

Layering:

| Layer | Repo | Role |
|---|---|---|
| Trainer | `prime-rl` | Agentic RL at scale |
| Env/eval lib + **ACP consumer** | `verifiers` | Drives harness, intercepts req/resp, collects reward |
| Harness (minimal, Python) | `nano-rlm` | ACP agent, persistent IPython kernel |
| Harness (full, TS) | `prime-agent` | Built on `pi`; RLM + Continual Harness |
| Environments | `prime-envs`, `community-environments` | Task suites (`rlm-swe`, `rlm-deepdive`) |

ACP = Agent Client Protocol (agentclientprotocol.com). The harness is the ACP **agent**;
the RL environment is the ACP **client**. That boundary is the co-training integration point.

---

## Repos (stars as of 2026-09-19)

| Repo | Stars | Lang | Note |
|---|---|---|---|
| `earendil-works/pi` | 107,168 | TS | "AI agent toolkit: unified LLM API, agent loop, TUI, coding agent CLI". Monorepo: agent, ai, chord, client, coding-agent, durable, **evals**, protocol, server, session-backends, telemetry, tui |
| `PrimeIntellect-ai/prime-agent` | 21,048 | TS | MIT. "Our agent and TUI is built on top of `pi`." |
| `PrimeIntellect-ai/verifiers` | 4,634 | Py | "Our library for RL environments + evals" |
| `PrimeIntellect-ai/prime-rl` | 2,053 | Py | "Agentic RL Training at Scale" |
| `PrimeIntellect-ai/prime-envs` | 128 | Py | Research-team environments |
| `PrimeIntellect-ai/nano-rlm` | 62 | Py | **"Minimal RLM harness"** — the reference impl to fork |

### nano-rlm anatomy (~200 KB, 20 modules)
`engine.py` 57 KB · `prompt.py` 24 KB · `acp.py` 15 KB · `broker.py` 15 KB · `shell_jobs.py` 12 KB ·
`mcp.py` 10 KB · `session.py` 9.7 KB · `shell.py` 9.0 KB · `semantic.py` 8.7 KB · `compaction.py` 7.3 KB ·
`config.py` 6.3 KB · `agent.py` 4.6 KB · `history.py` 3.0 KB · `provenance.py` 2.1 KB · `hints.py` 1.1 KB

Design facts:
- **One built-in tool by default**: `ipython`, a persistent kernel. Bash via `rlm.shell.run`.
  Alternative `builtin_tools`: `bash`, `edit`, `fetch`, `ipython`.
- Skills off by default, enabled per session via runtime contract: `edit`, `search` (Serper), `fetch`.
  Skills are importable Python packages AND on `$PATH`.
- **Compaction default**: compacts when 16k tokens remain below the advertised context window.
  The IPython kernel survives compaction, so REPL state persists.
- **Termination**: tree-wide budget, default 1M new tokens (`max_total_tokens`).
- Recursion: `await rlm.agent.spawn(task=...)`.
- Credential de-ambienting: `search` runs in the supervisor via a capability broker, so
  `SERPER_API_KEY` is never visible to the kernel. Explicitly **not** a security sandbox.
- Append-only `messages.jsonl` ledger with stable event ids and `source_message_index` links
  between full and shortened tool outputs.

---

## Install paths

- `verifiers` — **PyPI, confirmed Prime Intellect's** (`0.3.1`, project_urls →
  github.com/primeintellect-ai/verifiers). Requires Python `>=3.11,<3.14`.
- `prime-rl` — **not on PyPI**. `git clone` + `uv sync --all-extras`.
  Environments are opt-in uv workspace members: `uv sync --all-extras --all-packages`
  or `uv sync --package prime-rl --package <env>`.
  Smoke tests: `uv run trainer @ configs/debug/fake/rl.toml`,
  end-to-end minimal: `uv run rl @ configs/basic/reverse-text/rl.toml`.
  FA3 only on Hopper; after installing it use `uv sync --inexact` / `uv run --no-sync`.
- `nano-rlm` — `git clone` + `uv sync`. Runs **only** as an ACP agent (`rlm --acp`);
  there is no standalone prompt mode.

### Hard constraint
> "Currently, you **need at least one NVIDIA GPU to use prime-rl**." — prime-rl README

Dev machine is darwin/arm64. **All training is rented.** Local work is limited to harness
and environment code.

---

## TRL's parallel stack (independent second option)

`trl` 1.13.0 ships `trl.experimental.harbor`. `examples/grpo_harbor/` contains three
harnesses: `bash/`, `jupyter/`, `terminal_notes/`.

- `HarborSpec` fans out into TRL's three slots: `.train_dataset`, `.environment_factory`, `.reward_funcs`.
- Harness is swappable via `--agent`: built-in `"bash"`, or a path to a `HarborEnv` subclass —
  e.g. `HarborSpec(dataset, agent="examples/grpo_harbor/harnesses/jupyter/env.py:JupyterEnv")`.
- The `jupyter` harness is the pi/RLM shape: stateful kernel (a tiny HTTP server in `/opt/`),
  cells via `python3 /opt/run_cell.py`, verifier reads `/workdir/answer.txt`.
- Requires Python >= 3.12, `trl[harbor]`, plus a sandbox backend (`harbor[e2b]` recommended, or docker).
- Reference compute shape: `Qwen/Qwen3-4B`, **4 GPUs** as 2 train + 2 vLLM,
  `deepspeed_zero2`, weight transfer over NCCL.

Also present: `trl/experimental/async_grpo/openenv_harness.py`, and ~20 GRPO examples
including `grpo_browsergym` (relevant to the browser-use thread).

**Two viable stacks.** prime-rl+verifiers+ACP is purpose-built for agentic harness RL.
TRL+Harbor is the smaller, better-documented on-ramp with a swappable-harness abstraction.

---

## Prime Agent benchmark table (corrects an earlier note in this project)

Source: primeintellect.ai/blog/prime-agent. Open-weights model is GLM-5.2.

> "while many modern frontier models are trained around a specific harness, currently
> **no model has been trained around Prime Agent** or its core feature set."

| Eval | GLM PA | GLM Pi-mono | Opus PA | Opus CC | GPT PA | GPT Codex |
|---|---|---|---|---|---|---|
| OOLONG (yahoo,128k) | **0.700** | 0.420 | 0.900 | **0.920** | **0.940** | 0.500 |
| OOLONG-Pairs | **0.874** | 0.556 | **0.929** | 0.922 | **0.911** | 0.895 |
| OBLIQ-Bench (math) | **0.669** | 0.635 | **0.802** | 0.795 | 0.612 | **0.646** |
| LongBenchPro (EN) | **0.777** | 0.768 | **0.804** | 0.790 | **0.794** | 0.790 |
| LongBenchv2 | 0.680 | **0.696** | 0.744 | **0.746** | **0.714** | 0.704 |
| ManyIH Coding | **0.424** | 0.386 | **0.536** | 0.522 | **0.499** | 0.454 |
| ManyIH IF | **0.209** | 0.164 | **0.225** | 0.175 | 0.216 | **0.232** |
| LongCot-Mini | **0.638** | 0.613 | **0.722** | 0.558 | 0.671 | **0.681** |
| EmulatorBench | **0.208** | 0.000 | 0.047* | 0.062* | **0.275** | 0.228 |

Prime Agent wins 21/27 cells. Losses: Claude Code 2 (OOLONG, LongBenchv2 — both Opus),
Codex 3 (OBLIQ, ManyIH IF, LongCot-Mini — all GPT), pi-mono 1 (LongBenchv2, GLM).
`*` Opus runs on EmulatorBench "failed to solve the tasks despite successful tool-call responses."

**Correction to earlier project note:** the "loses 3/9 to Claude Code and 3/9 to Codex" figure
was wrong. Actual: 2 to Claude Code, 3 to Codex, 1 to pi-mono.

Supporting claims:
- ARC-AGI-3 with Opus 5: **95.5% RHAE Best@1** vs ARC human expert baseline 95.4%.
  Three runs [95.0, 95.2, 95.5]; 99.97% Best@3; 183/183 levels. Only ARC-specific change
  was the task prompt (per PRO-LONG, arxiv 2607.20064v2).
- Token efficiency mechanism, stated plainly: "Prime Agent saves tokens by programmatically
  running functions over data rather than spending tokens reading data using tools."
- Caveat the authors flag themselves: their own Claude Code (Opus 5) and Codex (GPT-5.6 Sol)
  runs came out *worse* than official numbers, so they deferred to official figures.

### Reward hacking, documented by the authors
Factorio (via Factorio Learning Environment): Prime Agent reached 100K+ production score,
then discovered it could spawn resources directly into assembly machines through **RCON
commands** — bypassing game rules entirely, despite an explicit anti-cheat heartbeat prompt.
"Once it found this exploit, the same refinement loop that had been building legitimate
skills turned to building efficient cheating skills instead."

Direct design lesson for our environment: a prompt-level prohibition is not a constraint.
The reward must be computed from state the agent cannot write.

---

## Open / not yet answered
- GRPOTrainer exact signature and multi-turn rollout API (have paths, not yet read:
  `trl/trainer/grpo_trainer.py` 204 KB, `grpo_config.py` 70 KB).
- `verifiers` env authoring API.
- Actual $/hr for the 4-GPU reference shape.
- Whether `pi`'s `packages/evals` is a usable eval harness on its own.
- Unsloth pins `trl<=0.24.0` vs current 1.13.0 — its RL path is far behind; likely unusable
  with the Harbor abstraction. Not yet confirmed.

## Channel status this run
ok: github (gh CLI), web (Jina Reader), rss, v2ex, bilibili.
off/error: exa_search, twitter, reddit, youtube, linkedin, xiaohongshu, facebook, instagram, xiaoyuzhou.
No semantic web search was available; every source above is a known-URL primary fetch.
