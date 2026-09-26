"""Step 2's own tests. Run with `pytest step2/ -q` (root pytest.ini pins
testpaths=tests, which is Step 1's gate and is left alone).

Nothing here needs a GPU. What is tested is exactly what can be tested on
darwin/arm64: the prefix-preserving predicate, the reward's spread, and the
pass criteria. The training run is verified on Kaggle by running it.
"""

from __future__ import annotations

import math

import pytest

from gate_chat_template import is_prefix_preserving
from verdict import ENTROPY_FLOOR, MIN_STEPS, TARGET_WORDS, verdict, word_count_reward

transformers = pytest.importorskip("transformers")


# --------------------------------------------------------------- fixtures

def _log(**over):
    row = {
        "loss": 0.01,
        "grad_norm": 0.5,
        "learning_rate": 3e-5,
        "completions/mean_length": 42.0,
        "entropy": 1.2,
        "reward": 0.4,
        "reward_std": 0.2,
    }
    row.update(over)
    return row


def _run(n=MIN_STEPS, **over):
    return [_log(**over) for _ in range(n)]


# Real jinja, real tokenizer, two templates. No mock: the only thing swapped
# is the template string, which is the variable under test.
APPEND_ONLY = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}"
    "<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)
# Rewrites an earlier turn once a later one exists — the Qwen3 <think> shape.
# The predicate renders a 2-message and a 3-message conversation, so keying on
# `messages|length == 2` makes the SOLO marker appear in the first render and
# vanish from the second, which is exactly what "not prefix-preserving" means.
REWRITES_HISTORY = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n"
    "{% if loop.first and messages|length == 2 %}SOLO {% endif %}"
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


@pytest.fixture(scope="module")
def tok():
    try:
        return transformers.AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B")
    except Exception as e:  # offline, rate-limited, gated
        pytest.skip(f"Qwen3-0.6B tokenizer unavailable: {e}")


# ------------------------------------------------- the predicate, both ways

def test_predicate_true_on_an_append_only_template(tok):
    tok.chat_template = APPEND_ONLY
    assert is_prefix_preserving(tok) is True


def test_predicate_false_on_a_template_that_rewrites_history(tok):
    tok.chat_template = REWRITES_HISTORY
    assert is_prefix_preserving(tok) is False


# Prefix-preserving for ordinary turns, but rewrites a tool-call turn once a
# later message exists. Catches a predicate that probes with plain assistant
# content instead of tool_calls.
TOOL_TURNS_ONLY = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n"
    "{% if m.tool_calls and messages|length == 2 %}SOLO {% endif %}"
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)
# Renders the FIRST message differently depending on add_generation_prompt.
# Catches a predicate that omits `add_generation_prompt=True` on the second
# render, which is how TRL asks the question.
GENPROMPT_SENSITIVE = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n"
    "{% if loop.first and not add_generation_prompt %}SOLO {% endif %}"
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


# Prefix-preserving unless a `tool`-role message is present. Catches a probe
# that appends the wrong role to the second conversation.
TOOL_ROLE_ONLY = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n"
    "{% if loop.first and not messages|selectattr('role','equalto','tool')|list %}SOLO {% endif %}"
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)
# Both reject dict-valued `arguments` with a TypeError and accept the string
# form — the transformers#45419 shape (DeepSeek-V3) the fallback exists for.
# They differ only in whether they preserve prefixes, so the fallback has to
# be reached AND has to actually compute: a constant return cannot satisfy
# both. `_REJECT` is the clause that forces the TypeError.
_REJECT = "{% if m.tool_calls %}{{ m.tool_calls[0]['function']['arguments'] + '' }}{% endif %}"
REJECTS_DICT_ARGS_OK = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n" + _REJECT +
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)
REJECTS_DICT_ARGS_BROKEN = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n" + _REJECT +
    "{% if loop.first and messages|length == 2 %}SOLO {% endif %}"
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


def test_predicate_appends_a_tool_role_message(tok):
    """TRL's second conversation ends in a `tool` message. A probe that
    appends some other role asks a question TRL never asks."""
    tok.chat_template = TOOL_ROLE_ONLY
    assert is_prefix_preserving(tok) is False


# Raises KeyError (not TypeError) on dict-valued `arguments`. Stands in for a
# genuine template bug, which must surface rather than be retried away.
RAISES_NON_TYPEERROR = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n"
    "{% if m.tool_calls %}{{ m.tool_calls[0]['function']['arguments'][0:2] }}{% endif %}"
    "{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


def test_only_typeerror_triggers_the_retry(tok):
    """TRL catches TypeError and nothing else. Broadening the catch would let
    a real template bug be retried into a confident verdict instead of
    surfacing — and the string retry happens to succeed here, so the wrong
    answer would look like a clean pass."""
    tok.chat_template = RAISES_NON_TYPEERROR
    with pytest.raises(Exception) as e:
        is_prefix_preserving(tok)
    assert not isinstance(e.value, TypeError)


@pytest.mark.parametrize(
    "template,expected",
    [(REJECTS_DICT_ARGS_OK, True), (REJECTS_DICT_ARGS_BROKEN, False)],
    ids=["preserving", "not-preserving"],
)
def test_typeerror_fallback_is_exercised_not_merely_present(tok, template, expected):
    """The dict-args fallback is dead code for Qwen3. Step 1's recurring
    defect was a guard that had never been observed running, so these
    templates make it run: dict `arguments` raise TypeError, the string retry
    renders, and the predicate returns an answer instead of propagating.

    Both verdicts are asserted through that path deliberately. With only the
    True case, a fallback that did nothing but `return True` would pass."""
    tok.chat_template = template
    assert is_prefix_preserving(tok) is expected


def test_predicate_probes_with_a_tool_call_turn(tok):
    """TRL's `_get_tool_suffix_ids` needs prefix preservation across a tool
    call specifically. A template that is fine for plain turns and broken for
    tool-call turns must still fail."""
    tok.chat_template = TOOL_TURNS_ONLY
    assert is_prefix_preserving(tok) is False


def test_predicate_passes_add_generation_prompt_on_the_second_render(tok):
    """The predicate exists to predict TRL. TRL renders the longer
    conversation with add_generation_prompt=True; a copy that drops it is
    asking a different question and can disagree on some future model."""
    tok.chat_template = GENPROMPT_SENSITIVE
    assert is_prefix_preserving(tok) is False


def test_qwen3_stock_template_fails_the_gate(tok):
    """The live finding, pinned. If Qwen ever ships a prefix-preserving
    template this flips, and Step 5/6's plan gets simpler — so it should
    fail loudly rather than drift."""
    stock = transformers.AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B").chat_template
    tok.chat_template = stock
    assert is_prefix_preserving(tok) is False


def test_trl_patch_repairs_qwen3(tok):
    ctu = pytest.importorskip("trl.chat_template_utils")
    fixed = ctu.get_training_chat_template(tok)
    assert fixed is not None, "TRL claims Qwen3 support but returned no patch"
    tok.chat_template = fixed
    assert is_prefix_preserving(tok) is True


# ------------------------------------------------------------- the reward

def test_reward_is_continuous_and_peaks_at_target():
    r = word_count_reward(["w " * TARGET_WORDS, "w " * (TARGET_WORDS // 2), ""])
    assert r[0] == 1.0
    assert 0.0 < r[1] < 1.0          # graded, not binary
    assert r[2] == 0.0
    assert r == sorted(r, reverse=True)


def test_reward_never_leaves_unit_interval():
    r = word_count_reward(["w " * n for n in (0, 1, 20, 100, 5000)])
    assert all(0.0 <= x <= 1.0 for x in r)


def test_reward_spreads_across_a_group():
    """A group with identical rewards yields zero GRPO advantage. This is the
    property the whole smoke test rests on."""
    group = ["w " * n for n in (3, 8, 14, 20, 27, 35, 50, 90)]
    r = word_count_reward(group)
    assert len(set(r)) > 1
    mean = sum(r) / len(r)
    assert math.sqrt(sum((x - mean) ** 2 for x in r) / len(r)) > 0.1


def test_reward_reads_conversational_completions():
    assert word_count_reward([[{"role": "assistant", "content": "w " * TARGET_WORDS}]]) == [1.0]


# ------------------------------------------------------------ the verdict

def test_clean_run_passes():
    ok, why = verdict(_run())
    assert ok, why


def test_empty_log_fails_rather_than_vacuously_passing():
    ok, why = verdict([])
    assert not ok
    assert any("0 training steps" in r for r in why)


def test_truncated_run_fails():
    ok, why = verdict(_run(MIN_STEPS - 1))
    assert not ok
    assert any(f"{MIN_STEPS - 1} training steps" in r for r in why)


@pytest.mark.parametrize(
    "tail",
    [
        {"train_runtime": 12.0, "train_loss": 0.01, "epoch": 1.0},  # HF end-of-run summary
        {"eval_loss": 0.02, "eval_runtime": 3.0},                    # eval pass
    ],
)
def test_non_training_lines_do_not_count_as_steps(tail):
    """`train_loss` and `eval_loss` must not be mistaken for `loss`, or a
    short run reaches MIN_STEPS on summary rows and reports a false pass."""
    ok, why = verdict(_run(MIN_STEPS - 1) + [tail])
    assert not ok
    assert any(f"{MIN_STEPS - 1} training steps" in r for r in why)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_grad_norm_fails(bad):
    logs = _run()
    logs[2]["grad_norm"] = bad
    ok, why = verdict(logs)
    assert not ok
    assert any("grad_norm" in r and "not finite" in r for r in why)


def test_non_finite_loss_fails():
    logs = _run()
    logs[0]["loss"] = float("nan")
    ok, why = verdict(logs)
    assert not ok
    assert any("loss" in r and "not finite" in r for r in why)


def test_all_zero_grad_norm_fails():
    ok, why = verdict(_run(grad_norm=0.0))
    assert not ok
    assert any("no gradient reached the weights" in r for r in why)


def test_one_nonzero_grad_norm_is_enough():
    logs = _run(grad_norm=0.0)
    logs[3]["grad_norm"] = 0.7
    ok, _ = verdict(logs)
    assert ok


def test_degenerate_reward_fails():
    ok, why = verdict(_run(reward_std=0.0))
    assert not ok
    assert any("degenerate reward" in r for r in why)


def test_entropy_collapse_fails():
    logs = _run()
    logs[4]["entropy"] = ENTROPY_FLOOR / 2
    ok, why = verdict(logs)
    assert not ok
    assert any("entropy collapsed" in r for r in why)


def test_entropy_exactly_at_the_floor_fails():
    """`> floor`, not `>=`. Pins the boundary so a mutation cannot widen it."""
    logs = _run()
    logs[0]["entropy"] = ENTROPY_FLOOR
    ok, _ = verdict(logs)
    assert not ok


@pytest.mark.parametrize("key", ["grad_norm", "completions/mean_length", "entropy", "reward_std"])
def test_each_required_health_signal_is_required(key):
    """HANDOFF.md names four signals to log from run 1. Dropping any one of
    them must fail, or the requirement is decorative."""
    logs = _run()
    del logs[1][key]
    ok, why = verdict(logs)
    assert not ok
    assert any(key in r for r in why)


def test_booleans_are_not_accepted_as_finite_numbers():
    logs = _run()
    logs[0]["entropy"] = True
    ok, why = verdict(logs)
    assert not ok
    assert any("entropy" in r for r in why)


def test_every_failure_is_reported_not_just_the_first():
    logs = _run(reward_std=0.0, grad_norm=0.0)
    ok, why = verdict(logs)
    assert not ok
    assert len(why) >= 2


# ------------------------------------------------- the Kaggle run's inputs
# smoke.py cannot be imported here (it needs torch + unsloth + a GPU), so the
# two things about it that fail silently and expensively — a config kwarg that
# does not exist on the TRL Kaggle installs, and a prompt that burns the
# completion budget on reasoning — are checked against source instead.

import ast
import dataclasses
import pathlib

STEP2 = pathlib.Path(__file__).parent


def _smoke_call(fn_name):
    """The kwargs smoke.py passes to a given call, read from its AST."""
    tree = ast.parse((STEP2 / "smoke.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == fn_name:
            return {k.arg for k in node.keywords}
    raise AssertionError(f"smoke.py has no {fn_name}(...) call")


def _grpo_config_fields(path):
    tree = ast.parse(path.read_text())
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "GRPOConfig")
    return {t.target.id for t in cls.body if isinstance(t, ast.AnnAssign)}


def test_every_grpo_config_kwarg_exists_in_trl_024():
    """Unsloth pins `trl>=0.18.2,!=0.19.0,<=0.24.0`, but this was written
    against 0.29's source. A kwarg that only exists in the newer one fails at
    GRPOConfig construction — after the Kaggle queue, the model download and
    the 12 h session slot. `max_prompt_length` is the live example: present
    in 0.24, gone by 0.29."""
    from transformers import TrainingArguments

    gc24 = STEP2 / "gc24.py"
    if not gc24.exists():
        pytest.skip("vendored trl 0.24 grpo_config.py not present")
    known = _grpo_config_fields(gc24) | {f.name for f in dataclasses.fields(TrainingArguments)}
    assert not (_smoke_call("GRPOConfig") - known)


def test_prompts_close_the_think_block_so_completions_are_answers(tok):
    """enable_thinking=False pre-closes an empty <think> block in the prompt.
    Without it the prompt ends at the assistant header and Qwen3 spends the
    128-token completion budget reasoning, so mean_response_length — one of
    the four signals Step 2 exists to read — measures the wrong thing."""
    tok.chat_template = transformers.AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B").chat_template
    m = [{"role": "user", "content": "Describe a harbour at dawn in about 20 words."}]
    off = tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    on = tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    assert off.endswith("<think>\n\n</think>\n\n")
    assert not on.endswith("</think>\n\n")      # the flag is doing the work
    assert len(tok(off).input_ids) < 256          # cfg.max_prompt_length


def test_smoke_renders_prompts_with_thinking_disabled():
    """The property above only helps if smoke.py passes the flag in a call.

    Grepping the source text for it is not enough — the docstring explaining
    why the flag matters contains the same string, so a grep stays green
    after the flag is deleted from the call. Read the AST."""
    tree = ast.parse((STEP2 / "smoke.py").read_text())
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "apply_chat_template"
    ]
    assert calls, "smoke.py renders no prompts"
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert "enable_thinking" in kw, "prompt rendered without enable_thinking"
        assert kw["enable_thinking"].value is False


# HANDOFF.md settles these. smoke.py cannot run on darwin/arm64, so drift in
# any of them would not surface until a Kaggle session had already been spent
# — and lr and num_iterations drift produces a *plausible-looking* collapse
# rather than an error, which is worse.
SETTLED = {
    "fp16": True,                        # T4 is sm_75; bf16 needs 8.0
    "bf16": False,
    "num_iterations": 1,                 # Garg: 16-step reuse collapses mid-run
    "learning_rate": 3e-5,               # Garg: 1e-4 drives entropy to zero
    "mask_truncated_completions": True,  # HANDOFF, explicit
    "use_vllm": False,                   # HANDOFF, explicit
    "max_steps": 5,                      # HANDOFF, explicit
}


def _resolve(node, tree):
    """Literal value of an AST node, following one hop through a module-level
    constant (`max_steps=MAX_STEPS`). Returns a sentinel for anything else, so
    a value that cannot be read statically fails the test rather than passing
    it."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        for n in tree.body:
            if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == node.id for t in n.targets
            ):
                if isinstance(n.value, ast.Constant):
                    return n.value.value
    return _UNREADABLE


_UNREADABLE = object()


@pytest.mark.parametrize("key,want", sorted(SETTLED.items(), key=str))
def test_settled_training_constraints_are_not_silently_changed(key, want):
    tree = ast.parse((STEP2 / "smoke.py").read_text())
    call = next(n for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "GRPOConfig")
    kw = {k.arg: k.value for k in call.keywords}
    assert key in kw, f"GRPOConfig no longer sets {key}"
    got = _resolve(kw[key], tree)
    assert got is not _UNREADABLE, f"{key} is not a statically readable literal"
    assert got == want and type(got) is type(want)


def test_nccl_cumem_is_disabled_before_torch_is_imported():
    """`NCCL_CUMEM_ENABLE=0` only takes effect if it is set before torch
    loads. Setting it anywhere in the file reads as done; setting it after
    the import does nothing, silently."""
    tree = ast.parse((STEP2 / "smoke.py").read_text())
    setenv = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "setdefault"
        and n.args and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == "NCCL_CUMEM_ENABLE" and n.args[1].value == "0"
    ]
    torch_import = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "torch" for a in n.names)
    ]
    assert setenv, "NCCL_CUMEM_ENABLE=0 is never set"
    assert torch_import, "smoke.py does not import torch"
    assert min(setenv) < min(torch_import)


def test_exit_code_follows_the_verdict():
    """If main() returns 0 unconditionally, every check in verdict.py becomes
    decorative and a collapsed run reports success to the shell."""
    tree = ast.parse((STEP2 / "smoke.py").read_text())
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    returns = [n.value for n in ast.walk(main) if isinstance(n, ast.Return)]
    assert returns and all(isinstance(r, ast.IfExp) for r in returns), \
        "main() has a return that ignores the verdict"


def test_lora_rank_stays_in_the_range_handoff_settled():
    """HANDOFF fixes rank at 16-32. A range, not a value — so this asserts
    the bounds rather than pinning a number the next session cannot tune."""
    tree = ast.parse((STEP2 / "smoke.py").read_text())
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and getattr(n.func, "attr", None) == "get_peft_model")
    kw = {k.arg: k.value for k in call.keywords}
    rank = _resolve(kw["r"], tree)
    assert rank is not _UNREADABLE
    assert 16 <= rank <= 32, f"LoRA rank {rank} is outside HANDOFF's 16-32"


# ------------------------------------- the transformers-5 tuple-poisoning check

import sys
import types

from gate_chat_template import poisoned_optional_flags


def test_no_poisoned_flags_on_the_installed_stack():
    """Non-mocked: runs against whatever trl is actually installed. Guards the
    detector against false positives, which would block every run."""
    assert poisoned_optional_flags() == []


def _stub_import_utils(monkeypatch, **flags):
    """Install a stand-in trl.import_utils. The stub is the detector's INPUT,
    not a stand-in for the thing under test — the real stack is covered by the
    test above, which is the non-mocked half."""
    mod = types.ModuleType("trl.import_utils")
    for name, value in flags.items():
        setattr(mod, name, lambda v=value: v)
    monkeypatch.setitem(sys.modules, "trl.import_utils", mod)
    return mod


def test_detects_the_tuple_return_that_transformers_5_introduces(monkeypatch):
    """(False, None) is the exact shape transformers 5 returns, and it is
    truthy — which is why the guards invert instead of erroring."""
    _stub_import_utils(
        monkeypatch,
        is_mergekit_available=(False, None),
        is_vllm_available=(True, None),
        is_deepspeed_available=False,
    )
    assert poisoned_optional_flags() == ["is_mergekit_available", "is_vllm_available"]


def test_a_healthy_stub_reports_nothing(monkeypatch):
    _stub_import_utils(monkeypatch, is_mergekit_available=False, is_vllm_available=True)
    assert poisoned_optional_flags() == []


def test_a_raising_flag_is_not_mistaken_for_poisoning(monkeypatch):
    """Unrelated breakage in an optional-dep probe must not be reported as this
    bug, or the fix message sends the reader somewhere wrong."""
    mod = types.ModuleType("trl.import_utils")
    def boom():
        raise RuntimeError("unrelated")
    mod.is_vllm_available = boom
    mod.is_mergekit_available = lambda: (False, None)
    monkeypatch.setitem(sys.modules, "trl.import_utils", mod)
    assert poisoned_optional_flags() == ["is_mergekit_available"]


def test_non_flag_attributes_are_ignored(monkeypatch):
    """Both halves of the name filter are load-bearing. `_mergekit_available`
    is the real module-level variable TRL sets next to the accessor, and it
    must not be probed as though it were the accessor."""
    mod = types.ModuleType("trl.import_utils")
    mod.is_mergekit_available = lambda: (False, None)
    mod._mergekit_available = lambda: (False, None)   # endswith, not startswith
    mod.available_is_not_a_flag = lambda: (False, None)
    mod.is_something_else = lambda: (False, None)     # startswith, not endswith
    monkeypatch.setitem(sys.modules, "trl.import_utils", mod)
    assert poisoned_optional_flags() == ["is_mergekit_available"]


def test_preflight_blocks_rather_than_only_reporting():
    """The gate exists to stop smoke.py starting into a stack where
    `from trl import GRPOTrainer` dies. If the poisoned branch printed and
    returned 0, the run would proceed — Step 1's recurring defect, a guard
    that reports without gating. Checked on the AST because main() needs a
    network round-trip and a real tokenizer."""
    tree = ast.parse((STEP2 / "gate_chat_template.py").read_text())
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    for node in ast.walk(main):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and node.test.id == "poisoned"):
            returns = [n.value for n in ast.walk(node) if isinstance(n, ast.Return)]
            assert returns, "the poisoned branch does not return at all"
            assert all(isinstance(r, ast.Constant) and r.value != 0 for r in returns), \
                "the poisoned branch returns 0 — smoke.py would run anyway"
            return
    raise AssertionError("main() has no `if poisoned:` guard")


def test_missing_trl_is_not_an_error(monkeypatch):
    """The gate must still report on a machine with no trl at all."""
    monkeypatch.setitem(sys.modules, "trl.import_utils", None)
    monkeypatch.setattr(
        "builtins.__import__",
        lambda name, *a, **k: (_ for _ in ()).throw(ImportError(name))
        if name == "trl.import_utils" else __import__(name, *a, **k),
    )
    assert poisoned_optional_flags() == []
