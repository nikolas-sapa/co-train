"""The guards a co-training run must pass before it costs anything. Pure stdlib.

`docs/spec-cotrain.md` §156 names three ways a built pipeline runs clean and
measures the wrong thing. The property they share is that **none produces an
error at any point** -- the run completes, the logs are green, and the artifact
is a confident wrong answer. The only thing that catches them is a check that
fires before the money is spent, so everything in this file is testable with no
GPU and with none of the training stack installed.

Four groups:

1. `check_stack` / `require_stack` -- the version floor. Below unsloth 2026.10.3
   this is **not a degraded run, it is a different experiment**, so it raises.
2. `assert_one_tool`, `completion_cap` / `assert_cap`, `eval_max_turns` /
   `assert_turn_budget` -- the spec's three invariants.
3. `frontier_taskset_status` / `require_frontier_taskset` -- the blocking
   precondition of §344. Currently unmet; that is correct, not a bug.
4. `TurnBudget` -- the per-rollout state invariant 3 needs.

**Why these raise rather than `assert`.** The spec writes each invariant as a
one-line `assert`, and that is the right shape, but `python -O` deletes `assert`
statements outright. A guard an interpreter flag can remove is not a guard, and
this project's whole failure mode is checks that silently do not run. Each
raises `InvariantViolation`, which *is* an `AssertionError`, so the spec's
semantics survive while the statement stops depending on `__debug__`.
"""

from __future__ import annotations

import ast
import importlib.metadata as md
import json
import pathlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import takewhile
from typing import Any

from ptc.paired import power_pairs  # stdlib-only path: pulls no training stack

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class InvariantViolation(AssertionError):
    """One of the spec's invariants does not hold. See the module docstring."""


class StackError(RuntimeError):
    """The resolved dependency set is a different experiment, not a worse one."""


class PreconditionUnmet(RuntimeError):
    """The blocking requirement of spec §344 is not satisfied."""


# ------------------------------------------------------------------ the stack
#
# unsloth>=2026.10.3   trl==1.13.0   transformers<5   fp16     (spec §21-54)

UNSLOTH_FLOOR = (2026, 10, 3)
"""Hard floor, not a recommendation (spec §27).

2026.9.12 -- the version the Step 2 run used -- declares `trl<=0.24.0`, where
every seam this spec depends on is at *zero* occurrences in `grpo_trainer.py`:
`rollout_func` 0, `self.tools` 0, `environment_factory` 0, `tool_mask` 0.
2026.10.3, released 2026-10-08, lifts the pin to `trl<=1.13.0`, which has
13/17/19/27. An install that resolves below the floor produces no tool loop, no
external rollout entry point, no tool-token masking, and `vllm_mode` defaulting
the other way -- a different experiment, with no error to announce it.
"""

TRL_PIN = (1, 13, 0)
"""Pinned explicitly. trl 1.13.0 needs only `transformers>=4.56.2`, so
`transformers<5` does **not** constrain it; nothing else pins it either, and the
resolver is free to pick anything inside unsloth's range (spec §48)."""

TRANSFORMERS_MAJOR_CEILING = 5
"""`transformers<5`. At 5.5.0 on trl 0.24.0, 11 of 12 chat-template flags invert
and the error names neither package -- measured, `step2/README.md`."""


def _parse_version(v: str) -> tuple[int, ...]:
    """Leading numeric components of a version string, as ints.

    Tuples, never strings. `"2026.9.12" > "2026.10.3"` is **true** under string
    comparison and false under version comparison, and that one character is the
    whole floor: the version this project actually ran is the one a string
    compare waves through.
    """
    out: list[int] = []
    for part in re.split(r"[.\-+]", v.strip()):
        digits = "".join(takewhile(str.isdigit, part))
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def check_stack_common(versions: Mapping[str, str | None]) -> list[str]:
    """The Unsloth floor and TRL pin shared by default and native policies."""
    faults: list[str] = []
    floor = ".".join(map(str, UNSLOTH_FLOOR))
    pin = ".".join(map(str, TRL_PIN))

    unsloth = versions.get("unsloth")
    if not unsloth:
        faults.append(f"unsloth is not installed; the floor is {floor} (spec §27)")
    elif _parse_version(unsloth) < UNSLOTH_FLOOR:
        faults.append(
            f"unsloth {unsloth} is below the {floor} floor. This is NOT a degraded "
            "run, it is a different experiment: below the floor unsloth pins "
            "trl<=0.24.0, where rollout_func, self.tools, environment_factory and "
            "tool_mask are all at zero occurrences and vllm_mode defaults to "
            "'server'. Nothing errors to announce it."
        )

    trl = versions.get("trl")
    if not trl:
        faults.append(f"trl is not installed; pin it to {pin}")
    elif _parse_version(trl)[: len(TRL_PIN)] != TRL_PIN:
        faults.append(
            f"trl {trl} is not the pinned {pin}. Nothing else in the stack "
            "constrains trl, so the resolver picks freely inside unsloth's range "
            "-- pin it, do not infer it."
        )

    return faults


def check_stack(versions: Mapping[str, str | None]) -> list[str]:
    """Every fault in a resolved dependency set. An empty list means usable.

    Takes a mapping instead of importing, so the guard is testable offline
    against synthetic version sets. The training stack is not installed on the
    dev machine and is not going to be: `trl`, `unsloth` and `torch` all resolve
    to absent here, which is exactly the input this has to reject.
    """
    faults = check_stack_common(versions)
    transformers = versions.get("transformers")
    if not transformers:
        faults.append("transformers is not installed")
    elif _parse_version(transformers)[:1] >= (TRANSFORMERS_MAJOR_CEILING,):
        faults.append(
            f"transformers {transformers} violates "
            f"transformers<{TRANSFORMERS_MAJOR_CEILING}: at 5.x the chat-template "
            "flags invert and the error names neither package (measured, "
            "step2/README.md)."
        )

    return faults


def resolved_versions(
    packages: Iterable[str] = ("unsloth", "trl", "transformers", "torch"),
) -> dict[str, str | None]:
    """What the environment actually resolved to. `None` for absent.

    Read from installed metadata rather than from a requirements file, because
    the spec's instruction is to "assert the resolved version at startup rather
    than trusting the resolver" (§32).
    """
    out: dict[str, str | None] = {}
    for p in packages:
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def require_stack(versions: Mapping[str, str | None] | None = None) -> None:
    """Raise unless the resolved stack is the one the spec measured."""
    faults = check_stack(resolved_versions() if versions is None else versions)
    if faults:
        raise StackError(
            "resolved stack is not the measured stack:\n  - " + "\n  - ".join(faults)
        )


# --------------------------------- invariant 1: exactly one registered tool
#
#     assert len(tools) == 1        # run_program(code: str) -> str

THE_TOOL = "run_program"
"""The only tool that may be registered with TRL.

TRL passes `tools=self.tools` into `apply_chat_template`
(`grpo_trainer.py:1293,1387,1425,1466`), so every registered tool is rendered as
a schema in the system prompt. Registering `ledger`'s `ids`/`get`/`links_to`
**builds the typed-tool-calling comparator instead of PTC** -- the exact axis
this project measures, since `ptc/harness.py`'s premise is that the catalog
lives *inside* the program. The catalog must reach the model via
`ptc.runtime.Catalog` plus prompt text, never as sibling tool schemas.

H4 cannot catch this and in fact rewards it: `tool_success_rate` is pinned at
exactly 1.000 for a flipped arm, because `ledger`'s tools return JSON or `null`
and can never match `_is_failure`. The flipped pipeline therefore reads as a
spectacular confirmation of a prediction the project signed in advance (spec
§206-238). This assertion is the only thing standing in front of that.
"""


def _tool_name(tool: object) -> str | None:
    """The function name out of an OpenAI-style tool dict, or a callable's name."""
    if isinstance(tool, Mapping):
        fn = tool.get("function")
        if isinstance(fn, Mapping):
            return fn.get("name")
        return tool.get("name")
    return getattr(tool, "__name__", None)


def assert_one_tool(tools: Iterable[object]) -> None:
    """Invariant 1. Exactly one registered tool, and it is `run_program`."""
    tools = list(tools)
    if len(tools) != 1:
        raise InvariantViolation(
            f"invariant 1: {len(tools)} registered tools, need exactly 1 "
            f"({THE_TOOL}). Every registered tool is rendered as a schema in the "
            "system prompt, so more than one builds the typed-tool-calling "
            f"comparator instead of PTC. Got {[_tool_name(t) for t in tools]}."
        )
    name = _tool_name(tools[0])
    if name != THE_TOOL:
        raise InvariantViolation(
            f"invariant 1: the one registered tool is {name!r}, not {THE_TOOL!r}"
        )


# ------------- invariant 2: one cap per experiment, shared across compared arms
#
#     assert cap == 3072 >= observed_max["ptc"]                  # PTC arm only
#     assert cap_ptc == cap_bash >= max(observed_max.values())   # both arms

OBSERVED_MAX = {"ptc": 2642, "bash": 4258}
"""Max completion tokens per rollout, measured on run 3d (spec §298-308).

**Floors, not forecasts.** These are `deepseek-v4-flash` rollouts under no
training pressure. Qwen3-0.6B will not beat its PTC tool-call success of 0.561,
so expect more turns and longer programs, and GRPO drifts longer before it
drifts better. Log the realised distribution from step 1.
"""

_CAP_GRANULARITY = 1024
"""Single-arm caps round up to this. **Reconstructed, not stated by the spec**:
the spec gives 3,072 for the PTC-only arm against an observed max of 2,642 and
says only "because PTC's observed max is 2,642". 3,072 is that max rounded up to
the next 1,024. The load-bearing property is the *inequality*, asserted below;
this constant only reproduces the spec's published figure from the measurement.
"""


@dataclass(frozen=True)
class CompletionCap:
    """A completion cap bound to the arm set it is valid for.

    **The condition is structurally inseparable from the value**, which is the
    point and not decoration. There is deliberately no module-level `3072` and
    no `__int__`: the only way to obtain a cap is `completion_cap(arms)`, and the
    only way to use one is `assert_cap(cap, arms)` and then `cap.value`. This
    project has already shipped a real number attached to the wrong denominator
    -- `$0.0071` travelled into four documents and an OSF package because nobody
    recorded what it was a number *of*. A cap quoted bare is the same fault
    waiting to happen (spec §96-116).
    """

    arms: frozenset[str]
    value: int

    def __str__(self) -> str:
        return f"{self.value} tokens (valid ONLY for arms={sorted(self.arms)})"


def completion_cap(arms: Iterable[str]) -> CompletionCap:
    """The cap for exactly this set of *trained* arms. Derived, not looked up.

    - one arm: its own observed max, rounded up to `_CAP_GRANULARITY` -> 3,072 for PTC
    - two or more: exactly the global observed max -> 4,258

    The two rules differ because they answer different questions. A single-arm
    cap only has to not truncate its own arm, so it can be rounded to something
    tidy. A cross-arm cap is a *validity* constraint: the caps must be identical
    and at least the global observed max, or each arm's tail is masked at a
    different rate and the comparison is confounded by the cap itself -- which
    would bias the cost co-primary, the one finding that survived the audit.
    `mask_truncated_completions=True` means an over-cap rollout is **dropped from
    the loss, not truncated**: at cap 1,024, 8/29 PTC rollouts vanish (27.6%,
    measured), all from the full-scan tier, the only tier with headroom.
    """
    arms = frozenset(arms)
    if not arms:
        raise InvariantViolation(
            "invariant 2: no trained arms declared, so no cap is defined"
        )
    unknown = sorted(arms - set(OBSERVED_MAX))
    if unknown:
        raise InvariantViolation(
            f"invariant 2: no measured completion max for arm(s) {unknown}; "
            f"known arms are {sorted(OBSERVED_MAX)}"
        )

    binding = max(OBSERVED_MAX[a] for a in arms)
    if len(arms) > 1:
        value = binding
    else:
        value = -(-binding // _CAP_GRANULARITY) * _CAP_GRANULARITY

    if value < binding:  # unreachable by construction; the guard is the point
        raise InvariantViolation(
            f"invariant 2: derived cap {value} is below the binding observed max {binding}"
        )
    return CompletionCap(arms, value)


def assert_cap(cap: CompletionCap, trained_arms: Iterable[str]) -> None:
    """Invariant 2. The cap in hand is the cap for the arms being trained.

    Fires on the reuse the bare number invites: a 3,072 built for the PTC-only
    experiment, carried into a two-arm run, would silently delete bash rollouts
    that PTC keeps.
    """
    trained = frozenset(trained_arms)
    if not trained:
        raise InvariantViolation("invariant 2: no trained arms declared")
    if cap.arms != trained:
        raise InvariantViolation(
            f"invariant 2: cap is {cap}, but the trained arms are {sorted(trained)}. "
            "A cap is not transferable between experiments."
        )
    binding = max(OBSERVED_MAX[a] for a in trained)
    if cap.value < binding:
        raise InvariantViolation(
            f"invariant 2: cap {cap.value} < binding observed max {binding} over "
            f"{sorted(trained)}"
        )
    if len(trained) > 1 and cap.value != binding:
        raise InvariantViolation(
            f"invariant 2: a cross-arm cap must be exactly the global observed max "
            f"{binding}, got {cap.value}; a shared cap that is not the global max "
            "still masks each arm's tail at a different rate"
        )


# ------------------------- invariant 3: max_turns reaches the trained arm
#
#     assert env.max_turns == EVAL_MAX_TURNS     # 8, PTCHarnessConfig default


def _source(path: str, root: pathlib.Path) -> ast.Module:
    return ast.parse((root / path).read_text())


def eval_max_turns(root: pathlib.Path = REPO_ROOT) -> int:
    """The eval arm's turn budget, **read out of `ptc/harness.py`**, not written here.

    Parsed rather than imported: `ptc.harness` needs `verifiers` and `httpx`, and
    this file has to stay importable with nothing installed. Parsed rather than
    copied, because a literal `8` here would go stale the first time the harness
    default moved, and the trained arm would quietly get a different budget from
    the measured one -- which is defect 1 again.
    """
    tree = _source("ptc/harness.py", root)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "PTCHarnessConfig"):
            continue
        for stmt in node.body:
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
                continue
            if stmt.target.id != "max_turns" or stmt.value is None:
                continue
            # `max_turns: int = Field(8, gt=0)` -- the default is Field's first arg.
            value = stmt.value
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, int):
                return value.value
            raise InvariantViolation(
                "invariant 3: PTCHarnessConfig.max_turns default is not a literal int "
                f"({ast.dump(stmt.value)[:80]}); the trained arm cannot read it"
            )
    raise InvariantViolation(
        "invariant 3: could not find PTCHarnessConfig.max_turns in ptc/harness.py"
    )


def module_literal(path: str, name: str, root: pathlib.Path = REPO_ROOT) -> Any:
    """A module-level literal assignment, read from source rather than imported.

    Same motive as `eval_max_turns`: `ptc.metrics` and `ptc.harness` need
    `verifiers` and `httpx`, this file must stay importable with nothing
    installed, and a copied literal goes stale the first time the original moves.
    """
    for stmt in _source(path, root).body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in stmt.targets
        ):
            return ast.literal_eval(stmt.value)
    raise InvariantViolation(f"could not find a literal {name} in {path}")


def failure_prefixes(root: pathlib.Path = REPO_ROOT) -> tuple[str, ...]:
    """`ptc.metrics.FAILURE_PREFIXES`, read from source for the same reason."""
    return tuple(module_literal("ptc/metrics.py", "FAILURE_PREFIXES", root))


@dataclass
class TurnBudget:
    """Per-rollout turn state. The budget invariant 3 says must exist somewhere.

    trl's `_tool_call_loop` is `while idxs_with_tool:` whose only exit is "all
    overlong", and `tool_call_count` is a logging counter, not a limit
    (measured). So the limit has to live in per-rollout state handed out by the
    `environment_factory` -- which is why this needs trl 1.13.0 and not 0.26 --
    and exhaustion has to return a refusal the model reads, matching
    `ptc/runtime.py`'s existing "a rejection the model reads, not a hang".
    """

    max_turns: int
    used: int = 0

    EXHAUSTED = (
        "no turns remain: the {max_turns}-program budget for this task is spent. "
        "Submit no further programs."
    )
    """Deliberately **not** prefixed with one of `ptc.metrics.FAILURE_PREFIXES`.

    A turn-budget refusal is a harness event, not a rejected program, and
    prefixing it would fold mode-3 turn exhaustion into H4's
    `tool_success_rate` -- where the spec says H4's response is
    sign-indeterminate and the remedy is to "log turn counts separately from H4"
    (§238). `assert_turn_budget` checks the prefix is absent, so the conflation
    cannot be reintroduced quietly. **Owner decision, surfaced not settled:** the
    spec does not say which way this goes.
    """

    def remaining(self) -> int:
        return max(0, self.max_turns - self.used)

    def consume(self) -> str | None:
        """Spend one turn. Returns the refusal text once the budget is gone."""
        if self.remaining() <= 0:
            return self.exhausted_message()
        self.used += 1
        return None

    def exhausted_message(self) -> str:
        return self.EXHAUSTED.format(max_turns=self.max_turns)


def assert_turn_budget(env: object, root: pathlib.Path = REPO_ROOT) -> None:
    """Invariant 3. The trained arm's budget equals the eval arm's, and runs out loud."""
    expected = eval_max_turns(root)
    actual = getattr(env, "max_turns", None)
    if actual != expected:
        raise InvariantViolation(
            f"invariant 3: env.max_turns is {actual!r}, the eval arm's is {expected} "
            "(PTCHarnessConfig default). trl's tool loop has no turn limit of its "
            "own, so a mismatch is a turn-unbounded trained arm measured against an "
            f"{expected}-turn eval arm."
        )
    message = getattr(env, "exhausted_message", None)
    text = message() if callable(message) else message
    if not isinstance(text, str) or not text.strip():
        raise InvariantViolation(
            "invariant 3: exhausting the budget must return a refusal the model "
            f"reads, not a hang; env.exhausted_message() gave {text!r}"
        )
    hit = [p for p in failure_prefixes(root) if text.lower().startswith(p)]
    if hit:
        raise InvariantViolation(
            f"invariant 3: the exhaustion refusal starts with {hit[0]!r}, which "
            "ptc.metrics counts as a tool failure. Turn exhaustion would then be "
            "folded into H4, whose response to it is sign-indeterminate; log turn "
            "counts separately instead (spec §238)."
        )


# --------------------------------- the blocking precondition (spec §344)

FRONTIER_MANIFEST = "bench/frontier/manifest.json"
"""Where the frontier taskset declares itself.

**This path and schema are this lane's declared contract and need reconciling
with whoever builds the taskset.** The gate fails closed either way: an absent
or non-conforming manifest means the pipeline does not run.
"""

MANIFEST_REQUIRED = (
    "policy",
    "pre_registration_amendment",
    "n_tasks",
    "solve_rate_min",
    "solve_rate_max",
    "measurement",
)
"""`policy` is in here because the number that sets every expectation in the spec
is `deepseek-v4-flash`'s 23/29, and the policy being trained is Qwen3-0.6B. A
solve-rate band measured on the wrong model is not evidence about this one.

`measurement` was added 2026-10-11 after the bench lane pointed out that the
first four keys **cannot fail once the band is produced by discarding
out-of-band tasks** — which is the only semantics under which they can ever pass,
because the raw min and max of per-task solve rates over a real suite are 0.0 and
1.0. A guard that cannot fail is this repo's signature defect, so the teeth moved
to where the information is: `measurement`.
"""

MEASUREMENT_REQUIRED = ("g", "dead_ceiling", "trainable_band", "n_candidates", "retention")
"""The measurement context, and what each one is for.

- **`g` and `dead_ceiling`** must match the values this lane trains at. The
  trainable band *widens* with `g`, so a subset retained against G=8 contains
  tasks that are dead at G=4: the retained set is only valid for the parameters
  it was retained under. This is the completion-cap fault in another costume — a
  number whose meaning depends on a parameter nobody re-checked — and it is the
  one check here that a conformant-by-construction band cannot satisfy for free.
- **`trainable_band`** must equal this lane's own `viable_band(g, ceiling)`. Two
  independent bisections of the same function; if they disagree, one of them
  retained the wrong tasks.
- **`n_candidates` and `retention`** are what carry information after subsetting.
  `n_tasks > 0` passes on a suite where 197 of 198 drawn tasks were discarded as
  untrainable, and that suite is not "near the frontier" in any sense §344 means.
"""

MIN_FRONTIER_TASKS = power_pairs(0.25, 0.5)
"""Paired tasks the gate requires, DERIVED rather than stored: it is `ptc.paired`'s own
answer for the +25 pp effect A6 signed, at band-centre discordance 0.500 -- 59 as of
2026-10-12. Derived because the alternative is a second copy of a number that moves
whenever the power function is corrected, and the power function was corrected on
2026-10-12 (an int-to-float OverflowError across delta 0.02-0.04).

This floor exists because the band is a band over the RETAINED subset and so conformant
by construction: `n_tasks > 0` passes on a suite where 197 of 198 drawn tasks were
discarded as untrainable, which is not "near the frontier" in any sense §344 means.
Deliberately no separate retention floor -- retention is reported in the failure text,
but gating on both it and n double-counts one constraint, and n is the one power depends
on.
"""

SOLVE_RATE_SCOPE = "per_task, over the retained frontier subset"
"""What `solve_rate_min`/`max` are a band *of*, stated because the alternative
reading is both plausible and useless.

A **marginal** accuracy over a corpus and a **per-task** solve-rate band come
apart completely: at a marginal 0.25 with G=4, a suite where every task sits at
p=0.25 has a mean dead-group fraction of 0.320 and every task trainable, while a
suite where a quarter of tasks are always solved and three quarters never are has
a mean of **1.000** and nothing trainable. Identical marginals, opposite
verdicts. The gate reads per-task rates and a marginal must never be substituted
for them. (Worked out by the bench lane, 2026-10-11.)
"""


@dataclass(frozen=True)
class Precondition:
    ok: bool
    reasons: tuple[str, ...]


def retention_floor(band: tuple[float, float]) -> float:
    """The retention a difficulty-blind suite would get, which is the floor.

    **Derived, not chosen.** If a suite's per-task solve rates were uniform on
    [0, 1] — i.e. the tasks were drawn with no regard for the policy at all — the
    fraction landing inside the trainable band is exactly the band's width, 0.760
    at G=4. §344 asks for "a taskset whose tasks sit near a 0.6B model's
    frontier. **Not merely more shapes**", so a suite that retains *less* than a
    difficulty-blind draw would is positive evidence that its tasks are
    concentrated in the dead tails, which is the opposite of the requirement.

    This is the strictest defensible floor and it is the one threshold in this
    gate that the spec does not supply. It is a keyword argument everywhere it is
    used, so lowering it is a one-line owner decision with a recorded reason
    rather than an edit to this function. **Expect to revisit it on the first
    real measurement:** nothing has measured a 0.6B policy's per-task solve rates
    on anything yet, so whether a genuinely frontier-adjacent suite clears 0.760
    is unknown.
    """
    lo, hi = band
    return hi - lo


def _check_measurement(
    manifest: Mapping[str, Any], g: int, ceiling: float, band: tuple[float, float],
    n_tasks: Any, min_retention: float | None,
) -> list[str]:
    """The `measurement` block: the half of the manifest that can still fail.

    Split out because `frontier_taskset_status` was already at the length where a
    reader stops reading, and because every check in here exists for a different
    reason — see `MEASUREMENT_REQUIRED`.
    """
    reasons: list[str] = []
    block = manifest.get("measurement")
    if not isinstance(block, Mapping):
        return [f"measurement is not an object: {block!r}"]

    missing = [k for k in MEASUREMENT_REQUIRED if k not in block]
    if missing:
        reasons.append(f"measurement is missing {', '.join(missing)}")

    measured_g = block.get("g")
    if measured_g != g:
        reasons.append(
            f"measurement.g is {measured_g!r} but this lane trains at G={g}. The "
            "trainable band widens with G, so a subset retained at another G "
            "contains tasks that are dead at this one — the retained set is only "
            "valid for the parameters it was retained under."
        )

    measured_ceiling = block.get("dead_ceiling")
    if measured_ceiling != ceiling:
        reasons.append(
            f"measurement.dead_ceiling is {measured_ceiling!r}, this lane aborts at "
            f"{ceiling}. Tasks were retained against a different ceiling."
        )

    declared_band = block.get("trainable_band")
    if isinstance(declared_band, (list, tuple)) and len(declared_band) == 2:
        if any(abs(a - b) > 1e-6 for a, b in zip(declared_band, band)):
            reasons.append(
                f"measurement.trainable_band {list(declared_band)} disagrees with this "
                f"lane's own derivation {list(band)} at G={g}, ceiling {ceiling}. Two "
                "bisections of the same function; one of them retained the wrong tasks."
            )
    elif "trainable_band" in block:
        reasons.append(f"measurement.trainable_band is not a pair: {declared_band!r}")

    candidates = block.get("n_candidates")
    if not (isinstance(candidates, int) and not isinstance(candidates, bool) and candidates > 0):
        reasons.append(f"measurement.n_candidates is not a positive int: {candidates!r}")
    elif isinstance(n_tasks, int) and not isinstance(n_tasks, bool):
        if n_tasks > candidates:
            reasons.append(
                f"n_tasks {n_tasks} exceeds measurement.n_candidates {candidates}: more "
                "tasks were retained than were measured"
            )
        else:
            realised = n_tasks / candidates
            declared = block.get("retention")
            if isinstance(declared, (int, float)) and not isinstance(declared, bool):
                if abs(declared - realised) > 1e-6:
                    reasons.append(
                        f"measurement.retention {declared} does not match n_tasks / "
                        f"n_candidates = {realised:.6f}; the counts and the rate disagree"
                    )
            elif "retention" in block:
                reasons.append(f"measurement.retention is not a number: {declared!r}")

            floor = retention_floor(band) if min_retention is None else min_retention
            if realised < floor:
                reasons.append(
                    f"retention {realised:.1%} ({n_tasks}/{candidates}) is below the "
                    f"{floor:.1%} floor, which is the width of the trainable band and so "
                    "the retention a suite drawn with no regard for the policy would "
                    "get. §344 asks for tasks that sit near the frontier, not for a thin "
                    "subset cherry-picked out of a suite that mostly does not. **This is "
                    "the one threshold the spec does not supply — see "
                    "guards.retention_floor; lowering it is an owner decision.**"
                )
    return reasons


def _amendment_is_signed(amendment: str, root: pathlib.Path) -> bool:
    """True when `docs/pre-registration.md` carries a signed heading for this id.

    That file is append-only and owner-signed; its amendments head as
    `### A6 -- <date>, ...: <title>, signed`. Read, never written:
    pre-registration content is an owner decision and this lane does not author
    it.
    """
    try:
        text = (root / "docs" / "pre-registration.md").read_text()
    except OSError:
        return False
    pattern = re.compile(
        r"^#{2,4}\s*" + re.escape(amendment) + r"\b[^\n]*\bsigned\b",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(pattern.search(text))


def frontier_taskset_status(
    root: pathlib.Path = REPO_ROOT, num_generations: int | None = None
) -> Precondition:
    """Is there a taskset whose tasks sit near a 0.6B model's frontier?

    Reports every reason it fails, not just the first. The band check is the
    spec's blocking requirement made numeric: a 0/1 reward needs tasks the policy
    *sometimes* solves, because saturation (p->1) and uniform failure (p->0) both
    produce zero-advantage groups, and the second is the likelier failure for a
    0.6B policy. `ledger` fails this on two counts -- the cheap tier's shape count
    is a record-schema ceiling, and run 3d scored an exact 23/23 tie -- so no
    value of n or G rescues it.
    """
    # Imported here, not at module scope: `dead_group_probe` owns the derivation
    # and imports this module inside its own `main()`. Keeping this one edge lazy
    # is what stops the two files forming an import cycle.
    from train.dead_group_probe import (
        ABORT_CEILING,
        NUM_GENERATIONS,
        zero_advantage_fraction,
    )

    g = NUM_GENERATIONS if num_generations is None else num_generations
    # Coerced, because a str root raised TypeError from the `/` operator -- a gate whose
    # job is to explain why it is shut should not fail with an operator error on a
    # perfectly ordinary argument.
    root = pathlib.Path(root)
    path = root / FRONTIER_MANIFEST
    reasons: list[str] = []

    if not path.exists():
        return Precondition(
            False,
            (
                f"no frontier taskset: {FRONTIER_MANIFEST} does not exist. Spec §344 "
                "-- until a taskset whose tasks sit near a 0.6B model's frontier "
                "exists, every number in the spec is preparation for a measurement "
                "that cannot yet be made.",
            ),
        )

    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return Precondition(False, (f"{FRONTIER_MANIFEST} is not readable JSON: {exc}",))
    if not isinstance(manifest, dict):
        return Precondition(False, (f"{FRONTIER_MANIFEST} is not a JSON object",))

    missing = [k for k in MANIFEST_REQUIRED if k not in manifest]
    if missing:
        reasons.append(f"{FRONTIER_MANIFEST} is missing {', '.join(missing)}")

    if not str(manifest.get("policy") or "").strip():
        reasons.append("manifest does not say which policy the solve rates were measured on")

    lo, hi = manifest.get("solve_rate_min"), manifest.get("solve_rate_max")
    numeric = [
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lo, hi)
    ]
    if all(numeric):
        if lo > hi:
            reasons.append(f"solve_rate_min {lo} > solve_rate_max {hi}")
        else:
            if not 0.0 < lo:
                reasons.append(
                    f"solve_rate_min is {lo}: a task the policy never solves yields a "
                    "uniformly-wrong group and zero advantage"
                )
            if not hi < 1.0:
                reasons.append(
                    f"solve_rate_max is {hi}: a saturated task yields a uniformly-right "
                    "group and zero advantage (run 3d's exact 23/23 tie)"
                )
            for label, p in (("solve_rate_min", lo), ("solve_rate_max", hi)):
                if 0.0 <= p <= 1.0:
                    frac = zero_advantage_fraction(p, g)
                    if frac > ABORT_CEILING:
                        reasons.append(
                            f"at {label}={p} and G={g} the zero-advantage fraction is "
                            f"{frac:.3f}, above the {ABORT_CEILING} abort ceiling -- "
                            "this end of the band is dead on arrival"
                        )
    elif not missing:
        reasons.append(f"solve_rate_min/max are not numbers: {lo!r}, {hi!r}")

    n = manifest.get("n_tasks")
    if not (isinstance(n, int) and not isinstance(n, bool) and n > 0):
        reasons.append(f"n_tasks is not a positive int: {n!r}")
    elif n < MIN_FRONTIER_TASKS:
        realised = manifest.get("measurement", {})
        drawn = realised.get("n_candidates") if isinstance(realised, dict) else None
        kept = realised.get("retention") if isinstance(realised, dict) else None
        detail = f" (retained {n} of {drawn}, {kept:.1%})" if isinstance(drawn, int) \
            and isinstance(kept, (int, float)) else ""
        reasons.append(
            f"n_tasks {n} is below the {MIN_FRONTIER_TASKS} paired tasks the +25 pp "
            f"effect needs at band-centre discordance{detail}. A band over a retained "
            "subset is conformant by construction -- n is where the information is, so "
            "n is where the floor goes."
        )

    amendment = str(manifest.get("pre_registration_amendment") or "").strip()
    if not amendment:
        reasons.append("manifest names no pre-registration amendment")
    elif not _amendment_is_signed(amendment, root):
        reasons.append(
            f"pre-registration amendment {amendment!r} is not signed in "
            "docs/pre-registration.md. A taskset change is a change to the "
            "instrument and needs its own signed amendment before any run on it is "
            "reported as evidence (pre-registration A5)."
        )

    return Precondition(not reasons, tuple(reasons))


def require_frontier_taskset(
    root: pathlib.Path = REPO_ROOT, num_generations: int | None = None
) -> None:
    """Raise unless §344's precondition holds. This is the pipeline's gate."""
    status = frontier_taskset_status(root, num_generations)
    if not status.ok:
        raise PreconditionUnmet(
            "the co-training pipeline is gated on spec §344 and the gate is shut:\n  - "
            + "\n  - ".join(status.reasons)
            + "\n\nThe dead-group probe (train/dead_group_probe.py) is NOT gated on "
            "this, and is the only GPU spend the spec authorises."
        )
