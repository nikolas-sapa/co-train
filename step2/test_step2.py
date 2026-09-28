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
from verdict import DEGENERATE_FRAC, MIN_STEPS, TARGET_WORDS, verdict, word_count_reward

transformers = pytest.importorskip("transformers")


# --------------------------------------------------------------- fixtures

def _log(**over):
    row = {
        "loss": 0.01,
        "grad_norm": 0.5,
        "learning_rate": 3e-5,
        "completions/mean_length": 42.0,
        "reward": 0.4,
        "reward_std": 0.2,
        "frac_reward_zero_std": 0.25,
        "kl": 0.0,
    }
    row.update(over)
    return row


def _run(n=MIN_STEPS, **over):
    """A healthy run. `kl` varies across steps unless the caller pins it,
    because a constant kl is exactly what verdict() must reject — a fixture
    that repeated one value would make the clean-run test assert the failure
    mode instead of the healthy one."""
    rows = [_log(**over) for _ in range(n)]
    if "kl" not in over:
        for i, row in enumerate(rows):
            row["kl"] = i * 1e-3     # 0.0 on step 0: LoRA B starts at zero
    return rows


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


def test_one_step_with_reward_spread_is_enough():
    """`any`, not `all`. Mirrors test_one_nonzero_grad_norm_is_enough, whose
    absence for reward_std let a mutation tightening the quantifier survive:
    with only the all-zero case tested, `any` and `all` are indistinguishable,
    and the tightened version fails a run that is degenerate on one step of
    five. The README records that leniency as a deliberate known hole, so it
    needs a test pinning it rather than an accident of fixture choice."""
    logs = _run(reward_std=0.0)
    logs[3]["reward_std"] = 0.2
    ok, why = verdict(logs)
    assert ok, why


def test_every_group_degenerate_fails():
    """`entropy`'s replacement. frac_reward_zero_std pinned at 1.0 means every
    group had zero reward spread, so no advantage existed anywhere and fp16 was
    never exercised — a clean exit proving nothing."""
    ok, why = verdict(_run(frac_reward_zero_std=1.0))
    assert not ok
    assert any("every group degenerate" in r for r in why)


def test_one_step_with_spread_is_enough():
    """`all`, not `any`: a run that recovers on one step still had a gradient.
    Pins the quantifier so a mutation to `any` cannot pass unnoticed."""
    logs = _run(frac_reward_zero_std=1.0)
    logs[2]["frac_reward_zero_std"] = 0.5
    ok, _ = verdict(logs)
    assert ok


def test_degenerate_frac_boundary_is_inclusive():
    """`>= DEGENERATE_FRAC`. A run at exactly 1.0 is fully degenerate and must
    fail; nudging the constant or the comparison must break this."""
    ok, _ = verdict(_run(frac_reward_zero_std=DEGENERATE_FRAC))
    assert not ok


def test_constant_kl_fails_even_though_it_is_finite():
    """The trap this check exists for. Unsloth logs `kl` with no beta guard, so
    at beta=0 it is a literal constant 0.0 — present, finite, and meaningless.
    A finiteness-only check would pass it and leave a JSONL that reads as a KL
    curve to the next person who opens it."""
    ok, why = verdict(_run(kl=0.0))
    assert not ok
    assert any("no KL was measured" in r for r in why)


def test_constant_nonzero_kl_also_fails():
    """Spread, not positivity. A frozen non-zero value is just as much an
    artifact as a frozen zero, and a `> 0.0` check would wave it through."""
    ok, why = verdict(_run(kl=0.07))
    assert not ok
    assert any("kl is constant" in r for r in why)


def test_a_real_kl_curve_passes_with_a_zero_first_step():
    """Step 0's KL is legitimately 0.0: LoRA initialises B to zero, so the
    policy IS the reference on the first step. A check demanding kl > 0 on
    every step would fail every correct run."""
    logs = _run()
    assert logs[0]["kl"] == 0.0
    ok, why = verdict(logs)
    assert ok, why


def test_first_step_inf_grad_norm_is_tolerated():
    """fp16's GradScaler starts at init_scale=65536 and calibrates down by
    overflowing, so step 0's grad_norm is legitimately inf on a healthy run."""
    logs = _run()
    logs[0]["grad_norm"] = float("inf")
    ok, why = verdict(logs)
    assert ok, why


def test_the_first_step_exemption_does_not_cover_other_keys():
    """Narrow on purpose. If the exemption widened to the whole row, a NaN
    reward on step 0 would pass."""
    logs = _run()
    logs[0]["reward_std"] = float("nan")
    ok, why = verdict(logs)
    assert not ok
    assert any("reward_std" in r and "not finite" in r for r in why)


def test_the_first_step_exemption_does_not_cover_later_steps():
    """Pins the index. `i == 0`, not a blanket grad_norm pass — an overflow on
    step 1 is the real fp16 failure Step 2 exists to catch."""
    logs = _run()
    logs[1]["grad_norm"] = float("inf")
    ok, why = verdict(logs)
    assert not ok
    assert any("grad_norm" in r and "not finite" in r for r in why)


def test_entropy_is_not_required():
    """The defect that made this revision necessary, pinned so it cannot come
    back: `entropy` is never logged on the Unsloth path, so a healthy run has
    no such key and must still pass."""
    logs = _run()
    assert not any("entropy" in row for row in logs)
    ok, why = verdict(logs)
    assert ok, why


@pytest.mark.parametrize(
    "key",
    ["grad_norm", "completions/mean_length", "reward_std", "frac_reward_zero_std", "kl"],
)
def test_each_required_health_signal_is_required(key):
    """HANDOFF.md names the signals to log from run 1. Dropping any one of them
    must fail, or the requirement is decorative."""
    logs = _run()
    del logs[1][key]
    ok, why = verdict(logs)
    assert not ok
    assert any(key in r for r in why)


def test_booleans_are_not_accepted_as_finite_numbers():
    logs = _run()
    logs[0]["reward_std"] = True
    ok, why = verdict(logs)
    assert not ok
    assert any("reward_std" in r for r in why)


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
    "beta": 0.04,                        # gap-closure section 7: KL is the run's
                                         # only unpublished output. At beta=0 the
                                         # metric is still logged, as a constant
                                         # 0.0, so drift here does not crash —
                                         # it silently produces a fake curve.
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
