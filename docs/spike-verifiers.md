# Spike — can `verifiers` carry the harness layer?
2026-09-26. Run in `~/scratch/verifiers-spike/`; the co-train repo was read-only
throughout. **Both headline results were re-executed by a second party on the same
machine, not taken on report.**

## Result

| Q | Verdict |
|---|---|
| Q1 — a non-LLM policy drives a **real** harness | **WORKS**, with a negative control that goes red — but via a monkeypatch, not the supported seam (see below) |
| Q2 — the PTC arm (`rlm`) | **NEEDS DOCKER**, ~1-2 days |
| Q3 — a ready-made verified environment | **WORKS** (`glossary`) |
| Q4 — cost of the untrained measurement | ~$10 and ~1 day for the *cheap* axis |

Environment: darwin/arm64, Python 3.13.12, `verifiers` installed from the clone at
commit `69cc0f9` into a fresh venv. Install clean, **no torch, no platform gates**.
Docker (colima) was installed but its VM was **not running** for any of this.

## Q1 — verified twice

A `Client` subclass with zero learned parameters drives the real `BashHarness` through
the real `SubprocessRuntime`, with the harness's chat program in its own uv-launched
process and the interception server on localhost.

Re-run independently:

```
positive          trace ... ok=True  reward=1.0  rewards={'wrote_sum': 1.0}   -> PASS
negative control  trace ... ok=True  reward=0.0  rewards={'wrote_sum': 0.0}   -> FAIL
```

The negative control is the same run with `+ 1` added to the canned shell command.
It returns `ok=True` with no errors and reward `0.0` — so **the reward reads the file
the harness's own bash wrote back out of the runtime**, and is not passing on
structure. This is the "verify the check can fail" rule satisfied for real, which is
why this result is trustworthy where a bare pass would not be.

Consequence: `research/08-gap-closure.md` §2.3's claim that the model-call seam is the
non-LLM entry point is now executed rather than inferred, and it needs no GPU and no
container.

## The caveat that changes what the $10 buys

**The pair actually executed in Q3 was `bash` vs `null`** — confirmed from the scripts
themselves (`q3_glossary_bash.py:68` sets `harness.id = "bash"`, `q3_glossary_null.py:68`
sets `"null"`).

`null` is the tool-less chat loop (`EXECUTES_CODE = False`). With MCP tools attached it
is a **typed-tool-calling** arm, not a programmatic-tool-calling one. So the cheap axis
measures **shell vs Tool-only** — which is the `+21.8-24.5 pp` pair the corpus already
has, and explicitly *not* the `+6.8 to +22.0 pp` bash-vs-PTC pair the thesis is about
(`08` §1.3, and `docs/superpowers/specs/...step1-nonsolver-gate-design.md` §2.1 on why
those are different pairs).

PTC as arXiv 2609.11999 defines it — a restricted program over a typed catalog with no
shell channel — is the `rlm` harness with `builtin_tools=["ipython"]`, and **that one
needs Docker plus 1-2 days of setup.**

So, precisely:

- **~$10 / ~1 day** buys a *replication of an already-published result* on our own
  stack. That is not nothing — it is a working end-to-end pipeline plus a sanity check
  that our setup reproduces a known effect — but it does **not** test the thesis.
- **The thesis pair costs that plus Docker and 1-2 more days.**

## What this does and does not settle for the build sequence

It settles the mechanism: harnesses, interception, a non-LLM policy, deterministic
rewards and a working negative control all run today, locally, for free.

It does **not** settle the premise. The premise check requires the `rlm` arm. The
argument for still doing it early is unchanged and arguably strengthened — 1-2 days of
Docker work is far less than the verifier-and-environment build it would otherwise sit
behind, and if the bash-over-PTC gap fails to reproduce, that build is wasted.

**Recommendation, pending the spike's own closing argument:** stand up the `rlm` arm
next and run the untrained bash-vs-PTC measurement before Step 3's verifier. Keep
`src/cotrain/contract.py` as-is; conform to `verifiers` at the point the real harnesses
are needed, exactly as `08` §2.6 proposed, now with the seam demonstrated rather than
assumed.

## The seam that was demonstrated is NOT the seam to build on

This qualifies Q1 above and is the most important correction in this document.

The working spike injected its policy by rebinding `resolve_client` **inside another
module's namespace**: `interception/server.py` does
`from verifiers.v1.clients import resolve_client`, so `server_mod.resolve_client = ...`
patches that module's local name. `resolve_client` is public
(`verifiers/v1/__init__.py:284`), but the rebinding target is not. **It breaks silently
if upstream inlines the call or renames the import** — no error, the real client is
simply used instead.

The supported seam is the one `Harness.launch` states verbatim: *every model call goes
through `endpoint` + `secret`*. The upgrade-safe form is `EvalClientConfig(base_url=...)`
pointed at your own OpenAI-compatible server, with no patching at all. **That variant was
not run** — roughly an hour of work, and it is what anything durable should use.

Treat the monkeypatch as spike scaffolding, not as the design. The *mechanism* is
proven; the *injection point* still needs doing properly.

### Two gotchas that cost real time, both found by running

- **`Response.raw` is mandatory.** A hand-built typed `Response` with `raw=None` kills
  the harness program with `openai.APIConnectionError: Model stream ended before a
  completion finished`. `server.py:764` frames SSE from `dialect.stream_events(response.raw or {})`
  and `server.py:116` serializes `raw` on the non-streaming path. The typed `Response`
  feeds the trace; `raw` feeds the wire. Emit a native dict and let
  `dialect.parse_response` build the typed half, as `clients/eval.py:93-100` does.
- **`client={"type": "train"}` is required or the policy is never called.**
  `server.py:600`: `relay = streaming and not isinstance(session.ctx.client, TrainClientConfig)`.
  With an eval client a streaming request relays straight upstream and `get_response`
  never fires — and the bash program always streams (`core.py:268`). The flag only flips
  that branch; `TrainClient` is never constructed.

## Why `glossary`, and the environments that are disqualified

`glossary` is the only shipped environment that is deterministic, offline,
container-free, **and** whose reward is 1.0 only if the agent actually used its tool
channel — which is what makes it able to discriminate between harnesses at all.

Confirmed with a discrimination control: a tool-using policy scores `[1.0]×5` and a
guessing policy `[0.0]×5`, in **both** harnesses. Tool lists measured off the wire:
`bash` → `['bash', 'facts_lookup']`, `null` → `['facts_lookup']`.

Ruled out, with reasons worth keeping:

| Environment | Why not |
|---|---|
| `wiki_search`, `interception`, `proposer_solver` | **LLM judge in the reward** — disqualified by project rule #5 |
| `deepwiki`, `web_search_interception`, `nemo_gym_weather`, `openenv_wordle` | external network or API key |
| `reverse_text`, `alphabet_sort`, `scratchpad`, `color_codeword`, `kuhn_poker` | deterministic, but no tool channel to discriminate between harnesses |
| `gsm8k` | deterministic and offline, but the harness barely participates |
| `code_golf` | the environment runs the program, not the harness |
| `bash_interception` | needs the tool gate that `rlm` lacks |

## Open

The spike's report truncated three times on budget cutouts. Outstanding: Q4's full
arithmetic (the headline ~$10 / ~1 day is recorded above), and the exact Docker
requirement for `rlm` on darwin/arm64 — whether colima suffices or it needs
linux/amd64.
