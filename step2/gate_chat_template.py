"""The TRL trainability gate, checked before any training code runs.

HANDOFF.md records this as "TRL raises at grpo_trainer.py:1981-1982 if the
chat template is not prefix-preserving". Checking it against TRL's source
rather than its docs (rule 7) turned up three things that reference does not
say, and they change what Step 2 has to do:

1. The raise is guarded by `if self.tools`. It is inside the multi-turn
   tool-calling loop. A GRPO run with no tools never reaches it.
2. Neither the check nor the tool loop exists in TRL <= 0.24.0 — the file
   `trl/chat_template_utils.py` is 404 at that tag, and `self.tools` appears
   zero times in its grpo_trainer.py. They land in 0.26.0.
3. Unsloth pins `trl>=0.18.2,!=0.19.0,<=0.24.0`. So on the Step 2 stack the
   gate is not merely unfired, it is absent.

And on TRL >= 0.26, where it does exist, Qwen3-0.6B fails it — Qwen3 drops
the `<think></think>` block from an assistant turn once a later turn is
appended, so rendering message N changes retroactively. TRL's own docstring
for `get_training_chat_template` uses Qwen3-0.6B as its worked example of
this, and ships the repair. The escape hatch (proxying the model call) is
not needed on that path.

Run this on Kaggle before `smoke.py`. Exits non-zero only when the template
is broken AND this TRL cannot repair it.

    python step2/gate_chat_template.py [model_id]
"""

from __future__ import annotations

import ast
import dataclasses
import os

import sys

# Must match `smoke.py`'s MODEL, and that is not cosmetic. TRL's repair
# (`get_training_chat_template`) does `tokenizer.chat_template ==
# qwen3_chat_template` — an EXACT string equality against a vendored copy.
# trl 0.26's copy is byte-identical to `Qwen/Qwen3-0.6B` (4168 chars, sha1
# b066ba71c1b5) and NOT to `unsloth/Qwen3-0.6B` (4905 chars, sha1
# 2006cdc006d3), which is what smoke.py loads. Both repos fail
# prefix-preservation, so the equality check is reached for both: Qwen's gets
# repaired, Unsloth's raises ValueError. Defaulting to Qwen here measured a
# model the run does not use and reported the comfortable answer.
MODEL = sys.argv[1] if len(sys.argv) > 1 else "unsloth/Qwen3-0.6B"

def _probe(arguments):
    """The two conversations TRL's helper renders, built fresh per call.

    Built inline rather than held as module constants because the TypeError
    fallback below rewrites `tool_calls` in place; shared constants would
    stay corrupted for every later call.

    The assistant turn must carry `tool_calls`, not plain content. TRL's
    `_get_tool_suffix_ids` depends on prefix preservation specifically across
    a tool call, and a template can be well-behaved for ordinary turns while
    rewriting tool-call ones.
    """
    m1 = [
        {"role": "user", "content": "dummy"},
        {"role": "assistant", "content": "", "tool_calls":
            [{"type": "function", "function": {"name": "dummy", "arguments": arguments}}]},
    ]
    return m1, m1 + [{"role": "tool", "name": "dummy", "content": "dummy"}]


def is_prefix_preserving(tok) -> bool:
    """Verbatim reimplementation of
    trl/chat_template_utils.py::is_chat_template_prefix_preserving.

    Inlined rather than imported so the gate still reports on a TRL that has
    no such helper — which is the case on the Unsloth-pinned stack. Because
    its job is to predict TRL's behaviour, it must stay byte-identical to
    TRL's version, including `add_generation_prompt=True` on the second
    render: a template may render earlier turns differently depending on that
    flag, and dropping it would make this predicate answer a question TRL
    never asks.
    """
    m1, m2 = _probe({})
    try:
        ids1 = tok.apply_chat_template(m1, tokenize=True, return_dict=False)
        ids2 = tok.apply_chat_template(m2, tokenize=True, return_dict=False, add_generation_prompt=True)
    except TypeError:
        # Templates that reject dict-valued arguments (transformers#45419).
        m1, m2 = _probe("{}")
        ids1 = tok.apply_chat_template(m1, tokenize=True, return_dict=False)
        ids2 = tok.apply_chat_template(m2, tokenize=True, return_dict=False, add_generation_prompt=True)
    return ids2[: len(ids1)] == ids1


def poisoned_optional_flags() -> list[str]:
    """TRL flags whose `is_X_available()` does not return a bool.

    TRL 0.24 declares `transformers>=4.56.1` with **no upper bound**, and
    transformers 5.x changed `_is_package_available` to return
    `tuple[bool, str]`. TRL calls it without `return_version=True` and stores
    the raw result, so every optional-dependency flag becomes `(False, None)`
    — a non-empty tuple, therefore truthy. Every `if is_X_available():` guard
    in TRL then fires against a missing package. The first one the GRPO import
    path reaches is mergekit, so `from trl import GRPOTrainer` dies with a
    bare `ModuleNotFoundError: No module named 'mergekit'` that names neither
    transformers nor the real cause.

    Measured 2026-09-26: 11 of 12 flags inverted on trl 0.24.0 +
    transformers 5.5.0; zero on trl 0.24.0 + transformers 4.57.6.

    Worth a preflight rather than a comment because the failure lands after
    the Kaggle queue and the model download, and burns a session slot.
    """
    try:
        import trl.import_utils as iu
    except ImportError:
        return []
    bad = []
    for name in dir(iu):
        if not (name.startswith("is_") and name.endswith("_available")):
            continue
        try:
            value = getattr(iu, name)()
        except Exception:
            continue  # unrelated breakage; not this bug
        if not isinstance(value, bool):
            bad.append(name)
    return bad  # dir() is documented to return a sorted list; no re-sort needed


def unknown_grpo_config_kwargs() -> list[str]:
    """GRPOConfig kwargs `smoke.py` passes that the INSTALLED trl does not accept.

    `test_step2.py` validates the same kwargs against `gc24.py`, a vendored
    snapshot of trl 0.24's GRPOConfig, so the suite stays green whatever pip
    actually resolved. That was a declared hole in `README.md`, and it fired:
    Unsloth 2026.10.3 (2026-10-08) lifted its ceiling from `trl<=0.24.0` to
    `trl<=1.13.0`, and trl 1.13.0 requires only `transformers>=4.56.2` — which
    `transformers<5` satisfies. So `pip install unsloth "transformers<5"` now
    resolves trl 1.13.0, where `max_prompt_length` is gone (present in 0.24,
    count 0 in 1.13.0's `grpo_config.py`). GRPOConfig would then raise AFTER
    the install, the queue and the model download — the failure shape this
    preflight exists to move to second 20.

    Reads the installed class via `dataclasses.fields`, which includes the
    TrainingArguments fields it inherits, so it cannot drift from reality the
    way a vendored snapshot can.
    """
    smoke = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke.py")
    if not os.path.exists(smoke):
        return []  # dev-side invocation without the run script beside it
    with open(smoke) as f:
        tree = ast.parse(f.read())
    passed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "GRPOConfig":
            passed = {k.arg for k in node.keywords if k.arg}
            break
    if not passed:
        return []
    try:
        from trl import GRPOConfig
    except Exception:
        return []  # no trl here; the poisoned-flag gate already reports that
    try:
        known = {f.name for f in dataclasses.fields(GRPOConfig)}
    except TypeError:
        return []  # not a dataclass on this version; nothing to compare against
    return sorted(passed - known)


def main() -> int:
    import transformers
    from transformers import AutoTokenizer

    try:
        import trl

        trl_version = trl.__version__
    except ImportError:
        trl_version = None

    tok = AutoTokenizer.from_pretrained(MODEL)
    print(f"model            {MODEL}")
    print(f"trl              {trl_version or 'not installed'}")
    print(f"transformers     {transformers.__version__}")

    poisoned = poisoned_optional_flags()
    if poisoned:
        print(
            f"\nFAIL — {len(poisoned)} TRL optional-dependency flags return a tuple, not a\n"
            f"bool, so every `if is_X_available():` guard is truthy and fires against a\n"
            f"missing package. `from trl import GRPOTrainer` will die on mergekit.\n"
            f"  poisoned: {', '.join(poisoned)}\n"
            f"  cause:    trl {trl_version} pins transformers>=4.56.1 with no upper bound;\n"
            f"            transformers {transformers.__version__} returns tuple[bool, str].\n"
            f"  fix:      pip install 'transformers<5'   (4.57.6 verified)"
        )
        return 1

    unknown = unknown_grpo_config_kwargs()
    if unknown:
        print(
            f"\nFAIL — smoke.py passes {len(unknown)} GRPOConfig kwarg(s) that trl "
            f"{trl_version} does not\naccept, so GRPOConfig would raise after the model "
            f"download.\n"
            f"  unknown: {', '.join(unknown)}\n"
            f"  cause:   Unsloth lifted its ceiling to `trl<=1.13.0`, and `transformers<5`\n"
            f"           does not hold trl down — trl 1.13.0 needs only transformers>=4.56.2.\n"
            f"  fix:     pip install unsloth \"transformers<5\" \"trl<=0.24\""
        )
        return 1
    print("optional flags   bool (not poisoned by the transformers 5 tuple change)")

    try:
        from trl.chat_template_utils import (
            get_training_chat_template,
            qwen3_training_chat_template,
        )

        gate_present = True
    except ImportError:
        get_training_chat_template = None
        qwen3_training_chat_template = None
        gate_present = False
    print(f"gate in this trl {gate_present}   (trl/chat_template_utils.py)")

    stock = is_prefix_preserving(tok)
    print(f"prefix-preserving {stock}")

    if stock:
        print("\nPASS — template is prefix-preserving as shipped.")
        return 0

    if not gate_present:
        # Absent gate is not a pass. It means the multi-turn tool path this
        # gate protects does not exist here either, so Step 2 is unblocked
        # and Step 5/6's PTC harness needs the proxy hatch or a newer TRL.
        print(
            "\nPASS for Step 2 — template is NOT prefix-preserving, but this TRL has no\n"
            "multi-turn tool loop to break. Step 5/6 PTC needs trl>=0.26 (drops Unsloth)\n"
            "or the proxy escape hatch that LEGO-RL and OpenForgeRL use."
        )
        return 0

    # TRL's contract, `chat_template_utils.py:353-362`, is three branches and
    # the middle one is an exact string equality:
    #     prefix-preserving already        -> return None   ("no patch NEEDED")
    #     template == qwen3_chat_template  -> return the repair
    #     otherwise                        -> RAISE ValueError ("unsupported")
    # The old code read None as "no patch available" — the opposite — and did
    # not catch the raise at all, so the genuine no-patch case exited with a
    # traceback rather than a verdict. `auto` records whether TRL will apply
    # the repair by itself when `tools=` is set, because that is the difference
    # between "nothing to do" and "you must set this or the trainer raises".
    try:
        fixed = get_training_chat_template(tok)
        auto = fixed is not None
    except ValueError as exc:
        # TRL declines this template. Its equality dispatch is keyed to
        # `Qwen/Qwen3-0.6B` (4168 chars) and `unsloth/Qwen3-0.6B` ships 4905,
        # so the repo this project trains is refused while the one it does not
        # is repaired. The repair itself still works on it — measured, not
        # assumed — so try it by hand rather than reporting a dead end.
        print(f"TRL repair        refused ({exc.__class__.__name__}: {str(exc)[:60]}...)")
        fixed, auto = qwen3_training_chat_template, False

    if fixed is None:
        print(
            "\nFAIL — TRL's own predicate calls this template prefix-preserving while\n"
            "the tool-call probe here does not, so no repair is offered and the\n"
            "disagreement is unresolved. Use the proxy hatch."
        )
        return 1

    tok.chat_template = fixed
    repaired = is_prefix_preserving(tok)
    print(f"after TRL patch   {repaired}   ({len(fixed)} chars)")
    if not repaired:
        print("\nFAIL — TRL's patch did not repair it. Use the proxy hatch.")
        return 1
    if auto:
        print(
            "\nPASS — TRL auto-applies this patch when `tools=` is set. No proxy needed.\n"
            "Note it is applied to a template copy; the tokenizer on disk stays unfixed."
        )
        return 0
    print(
        "\nPASS, CONDITIONALLY — the repair works on this template but TRL will NOT\n"
        "apply it: its dispatch is an exact equality against a vendored copy of\n"
        "`Qwen/Qwen3-0.6B`, and this repo's template differs. Under `tools=` the\n"
        "trainer raises at construction unless you set it yourself:\n"
        "    from trl.chat_template_utils import qwen3_training_chat_template\n"
        "    tokenizer.chat_template = qwen3_training_chat_template\n"
        "Do that before GRPOTrainer(...), or pass `Qwen/Qwen3-0.6B` instead."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
