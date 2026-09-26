# Spike — can `verifiers` carry the harness layer?
2026-09-26. Run in `~/scratch/verifiers-spike/`; the co-train repo was read-only
throughout. **Both headline results were re-executed by a second party on the same
machine, not taken on report.**

## Result

| Q | Verdict |
|---|---|
| Q1 — a non-LLM policy drives a **real** harness | **WORKS**, with a negative control that goes red — but via a monkeypatch, not the supported seam (see below) |
| Q2 — the PTC arm (`rlm`) | **RUNS on arm64** (minutes, not days) — but it is **not the paper's PTC interface at all**, and cannot be made into it |
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

---

# The PTC arm leaks a shell — executed 2026-09-26

The most consequential finding so far, and it invalidates the obvious way of building
Step 5. Everything below was run on this machine, not inferred.

## The Docker gate is cleared, and it was cheap

Estimated at 1-2 days. It took minutes. `colima start --cpu 4 --memory 8 --disk 40`
gives a **native aarch64** VM (Docker 29.5.2, Ubuntu 24.04 host, Debian trixie images),
so `rlm`'s installer — which shells out to `apt-get` and then fetches `uv` — works
without any x86 emulation. `rlm` with `builtin_tools=["ipython"]` installed inside the
container, launched, and reached a canned policy:

```
model calls intercepted: 1
   {'call': 1, 'n_msgs': 2, 'tools': ['ipython', 'wait'], 'roles': ['system','user'], 'stream': False}
trace 65e64661 ok=True reward=0.0 errors=[]
```

Note `stream: False` — unlike the bash harness, which always streams. And the advertised
tool list is `['ipython', 'wait']`: a program over a typed catalog, **no `bash` entry**.
On the wire it looks exactly like PTC.

## It is not PTC. The shell is reachable from inside it.

arXiv 2609.11999 defines PTC as a restricted program over the typed catalog with
*"no shell or other action channel"*. The `ipython` tool's own description, served to
the model in the system prompt, says:

> "Use `await rlm.shell.run(command, yield_after=10)` for Bash"

Two canned policies, same task, same harness, same container — differing only in the
body of the `ipython` call:

| Policy | How it solves | Reward |
|---|---|---|
| **PURE** — `open("answer.txt","w").write(str(a+b))` | Python only | **1.0, 1.0** |
| **SHELL** — `await rlm.shell.run("echo $(( a + b )) > answer.txt")` | shells out from inside the kernel | **1.0, 1.0** |

Both `ok=True`, no errors. **The shell escape works.** So a model in the "PTC" arm can
reach a shell whenever it wants, and the advertised tool list hides that completely.

## There is no configuration switch

- `rlm.shell` is core nano-rlm API, not a tool and not a skill. It is documented
  throughout `src/rlm/prompt.py` (`:45`, `:57`, `:125`, `:140`, `:143`, `:152`), including
  `rlm.shell.setenv`.
- Grepping nano-rlm for `allow_shell`, `disable_shell`, `no_shell` or an enabled-flag
  returns **nothing**.
- The rlm harness config *explicitly rejects* the one knob that sounds right:
  `reject_disabled_tools` (`harnesses/rlm/harness.py:126-130`) raises with *"the rlm
  harness does not support `disabled_tools`"*.
- `builtin_tools=["ipython"]` controls the **native tool list**, which is why `bash`
  vanished from the catalog while `rlm.shell` kept working.

## Why this matters more than it looks

This is the same class of confound the corpus already flagged for arXiv 2608.06370,
whose PTC executes *inside a shell subprocess* and which
`docs/superpowers/specs/2026-09-23-step1-nonsolver-gate-design.md` warns would
*"partially collapse the bash/PTC axis this project measures"*. Here it arrives from the
other direction — a PTC arm with a shell escape hatch — and it is **invisible in the
tool list**, so it would not have been caught by inspecting the config.

Left unaddressed it silently destroys Steps 5 and 6: a co-trained model would be free to
learn shell use *inside* the PTC arm, and the measured bash-vs-PTC gap would be a
measurement of nothing.

## Removing `rlm.shell` would not fix it — raw `subprocess` works too

Executed, third mode of the same script:

| Policy | Reward |
|---|---|
| `await rlm.shell.run("echo ... > answer.txt")` | 1.0, 1.0 |
| `import subprocess; subprocess.run(..., shell=True)` | **1.0, 1.0** |

nano-rlm's own prompt says it (`src/rlm/prompt.py:187`): *"The supervisor API is the only
shell: do not call subprocess or os.system from the kernel."* That is an **instruction to
the model, not an enforced restriction** — and this project's own rule #1 is that
prompting an agent not to do something is measured at zero effect.

**So forking nano-rlm to delete `rlm.shell` is pointless.** Any full Python kernel has
`subprocess`, `os.system`, `os.popen`, `pty`. A code-execution PTC arm cannot be
shell-free by construction unless the interpreter itself is restricted.

## What the source paper actually claims, and why that matters

arXiv 2609.11999 §3, verbatim:

> "PTC lets the model write a restricted program over the typed catalog. Our
> implementation uses Python as the program language and exposes the catalog as ordinary
> functions **within a restricted runtime that provides no shell or other action
> channel**."

So their PTC is Python **plus a restricted runtime**. The restriction *is* the interface.
The paper does not describe its mechanism, but it is load-bearing: without it, "PTC" is
just an interpreter, which is a strictly more capable interface than the one they
measured.

**Consequence: `rlm` cannot be the PTC arm at all.** Not "leaky and needs patching" —
it is a *different interface* from the one the published +6.8 to +22.0 pp gap was
measured on. Running bash-vs-`rlm` would be a construct-validity failure before a single
training step, and it would look like a clean result.

## Options, revised

1. ~~Fork nano-rlm and remove `rlm.shell`~~ — **dead**, `subprocess` remains.
2. **Build a minimal PTC harness with a genuinely restricted runtime** against the
   `Harness` ABC (`08` §2.5 established the ABC is small). The restriction is the
   deliverable, not the harness: an AST-validated program — allowlist the catalog
   functions, reject `import`, attribute access outside the allowlist, `exec`/`eval`,
   and dunder traversal — with OS-level backstop (seccomp denying `execve`, or simply no
   shell binaries and a non-fork-capable sandbox) because Python-level restriction alone
   is defeatable. This is the only route that reproduces the paper's interface.
3. **Keep `rlm` and report shell-use rate as a pre-declared covariate** — for the
   *untrained probe only*, and relabelled honestly: it is bash vs **unrestricted
   code-execution**, which is a real interface and an interesting arm, but it is not the
   paper's PTC and must not be reported as such.

**Decision: (2) is the real work, and it is now on the critical path.** (3) is acceptable
for a first probe provided the arm is named for what it is. The restricted runtime is
also a natural target for the Step 1 non-solver gate's state-tampering agent — the
escape-resistance of the PTC runtime is exactly the kind of claim that must be tested
adversarially rather than asserted, and this section is the evidence that asserting it
would have been wrong.

**Silver lining:** the escape tests above are a ready-made adversarial suite. Any
candidate restricted runtime must make all three modes go red — `rlm.shell`, raw
`subprocess`, and pure-Python-file-write must score 0.0 while the catalog path scores
1.0. That is a falsifiable acceptance test for option 2, written before the runtime
exists.

## Verified parity of the two arms

Before the leak was found, the PTC arm was shown to work as intended: the PURE policy
solves the task with Python only, reward `1.0, 1.0`, no errors. So `rlm` **is** a usable
PTC arm once the shell is removed — the problem is removal, not capability.
