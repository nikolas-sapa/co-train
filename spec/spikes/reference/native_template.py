"""Reference: conditional native template rendering, real tokenizer and SQLite.

No TRL import, model, sampler, optimizer or actual generation. The final answer
is scripted and the response parser is a fixture. Cached-template helper
selection is tested without substitution; a separate canonical identity view
tests the recognized upstream Qwen3 branch, without mutating the tokenizer.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import warnings

ROOT = None  # Explicit local source directory; never fetched implicitly.
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from jinja2 import TemplateError
from transformers import AutoTokenizer, PreTrainedTokenizerBase, ProcessorMixin
from transformers.utils.chat_template_utils import get_json_schema

from bench.task import SqlTask
from train.grpo_ptc import THE_TOOL_SCHEMA, training_config
from train.sql_bridge import prepare_sql_training

PINNED = {
    "upstream_chat_template_utils.py": "0152999b59e2210fc125703f85d33f459f74fbb72ba61494d5f38d6cb04455e2",
    "qwen3.jinja": "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8",
    "qwen3_training.jinja": "1d944ff8f268b611abb296cdd24d0f51981eef1c8647ac321c3a0258f61eb6c9",
}
METHOD_PINS = {
    "_get_tool_suffix_ids": "7df4ed7d436f1dcc3084abd4813d2c5df92bbff9f0801cb122d84b8def220bd6",
    "_tool_call_loop": "3a513812b6988bb1bb4cc9cceee21ebf343b63f6810c7d12eb693af856027f79",
}
PROGRAM = 'rows = execute_sql(query="SELECT amount FROM readings")\nprint(rows[0]["amount"])'
FINAL = "```sql\nSELECT amount FROM readings\n```"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load_helpers():
    checked_sources = {}
    for name, digest in PINNED.items():
        data = (ROOT / name).read_bytes()
        require(sha(data) == digest, f"source hash mismatch: {name}")
        checked_sources[name] = data.decode("utf-8")
    source = checked_sources["upstream_chat_template_utils.py"]
    tree = ast.parse(source)
    names = {
        "has_generation_markers", "supports_tool_calling",
        "is_chat_template_prefix_preserving", "get_training_chat_template",
    }
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    require(len(nodes) == 4, "missing selected helper")
    # Non-Qwen family constants are opaque unequal sentinels. This is a
    # Qwen-only namespace, not an implementation of the other family routes.
    constants = {
        n.id: object() for node in nodes for n in ast.walk(node)
        if isinstance(n, ast.Name) and n.id.endswith("_chat_template")
    }
    namespace = {
        **constants, "re": re, "warnings": warnings,
        "TemplateError": TemplateError,
        "PreTrainedTokenizerBase": PreTrainedTokenizerBase,
        "ProcessorMixin": ProcessorMixin,
        "qwen3_chat_template": checked_sources["qwen3.jinja"],
        "qwen3_training_chat_template": checked_sources["qwen3_training.jinja"],
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<pinned-selected-helpers>", "exec"), namespace)
    return namespace


class TemplateView:
    """Explicit hypothetical template identity, never changes cached tokenizer."""

    def __init__(self, tokenizer, template):
        self.tokenizer = tokenizer
        self.chat_template = template

    def apply_chat_template(self, *args, **kwargs):
        return self.tokenizer.apply_chat_template(
            *args, chat_template=self.chat_template, **kwargs,
        )


def load_methods(break_mask):
    namespace = {
        # Scripted final answer, deliberately not native parse_response proof.
        "parse_response": lambda *a, **kw: {"role": "assistant", "content": FINAL},
    }
    for name, digest in METHOD_PINS.items():
        body = (ROOT / (name + ".source.py")).read_text().removesuffix("\n")
        require(sha(body.encode()) == digest, f"method hash mismatch: {name}")
        if name == "_tool_call_loop" and break_mask:
            old = "tool_mask[idx_with_tool] += [0] * tool_length"
            require(body.count(old) == 1, "mask mutation target missing")
            body = body.replace(old, "tool_mask[idx_with_tool] += [1] + [0] * (tool_length - 1)")
        exec(compile(body, "<pinned-native-method>", "exec"), namespace)
    return namespace


def boundary(tokenizer, template, *, break_prefix=False):
    call = {"type": "function", "function": {"name": "run_program", "arguments": {}}}
    messages = [{"role": "user", "content": "fixture"},
                {"role": "assistant", "content": "", "tool_calls": [call]}]
    options = dict(chat_template=template, tokenize=True, return_dict=False, enable_thinking=False)
    before = tokenizer.apply_chat_template(messages, add_generation_prompt=False, **options)
    full = tokenizer.apply_chat_template(
        messages + [{"role": "tool", "name": "run_program", "content": "17"}],
        add_generation_prompt=True, **options,
    )
    eos = [i for i, token in enumerate(before) if token == tokenizer.eos_token_id]
    if eos:
        before = before[:eos[-1] + 1]
    if break_prefix:
        before[0] = -1
    mismatch = next((i for i, (a, b) in enumerate(zip(before, full)) if a != b), None)
    return {
        "prefix_tokens": len(before), "full_tokens": len(full),
        "prefix_preserving": full[:len(before)] == before,
        "first_mismatch_index": mismatch,
        "external_suffix_tokens": len(full) - len(before),
    }


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True,
                        help="local vetted/hash-pinned source and template files")
    parser.add_argument("--break-prefix", action="store_true")
    parser.add_argument("--break-mask", action="store_true")
    parser.add_argument("--stock-prefix", action="store_true")
    parser.add_argument("--require-cached-selection", action="store_true")
    args = parser.parse_args()
    ROOT = args.source_dir.resolve()
    helpers = load_helpers()
    tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen3-0.6B", local_files_only=True)
    original_template = tokenizer.chat_template
    exact_match = original_template == helpers["qwen3_chat_template"]
    require(helpers["supports_tool_calling"](tokenizer), "cached template drops tools")
    require(not helpers["is_chat_template_prefix_preserving"](tokenizer), "stock should be red")
    try:
        cached_selected = helpers["get_training_chat_template"](tokenizer)
        selection_error = None
    except ValueError as exc:
        cached_selected = None
        selection_error = str(exc)
    if args.require_cached_selection:
        require(selection_error is None, f"cached native helper selection failed: {selection_error}")
    # If cached identity is unrecognized, preserve that failure. Independently
    # exercise the exact recognized Qwen3 branch with an explicit canonical view.
    # SHORTCUT: hypothetical recognized identity, not a production repair.
    canonical = TemplateView(tokenizer, helpers["qwen3_chat_template"])
    selected = helpers["get_training_chat_template"](canonical)
    require(selected == helpers["qwen3_training_chat_template"], "wrong Qwen training template")
    require(
        helpers["is_chat_template_prefix_preserving"](TemplateView(tokenizer, selected)),
        "native helper template fails exact helper probe",
    )
    stock_boundary = boundary(tokenizer, None)
    require(not stock_boundary["prefix_preserving"], "stock boundary must fail")
    if args.stock_prefix:
        require(stock_boundary["prefix_preserving"], "stock template token prefix mismatch at index 9")
    selected_boundary = boundary(tokenizer, selected, break_prefix=args.break_prefix)
    # PROVES: explicit upstream training rendering preserves this real token prefix.
    require(selected_boundary["prefix_preserving"], "selected template token prefix mismatch")
    methods = load_methods(args.break_mask)
    with tempfile.TemporaryDirectory(prefix="template-spike-", dir=ROOT) as directory:
        db = Path(directory) / "fixture" / "fixture.sqlite"
        db.parent.mkdir()
        with sqlite3.connect(db) as connection:
            connection.execute("CREATE TABLE readings (amount INTEGER)")
            connection.execute("INSERT INTO readings VALUES (17)")
        task = SqlTask(
            name="fixture", question="What amount is recorded?", evidence="",
            gold_sql="SELECT amount FROM readings /* PRIVATE_GOLD */",
            db_id="fixture", db_path=str(db), tier="simple", tier_source="derived",
            shape="fixture", coarse_shape="fixture", source="fixture",
        )
        prepared = prepare_sql_training([task], directory)
        row = prepared.dataset_rows[0]
        unchanged_rows = copy.deepcopy(prepared.dataset_rows)
        environment = prepared.environment_factory()
        require(environment.reset(**row) is None, "reset changed prompt")
        public = [method for name, method in inspect.getmembers(environment, inspect.ismethod)
                  if name not in {"reset", "get_reward"} and not name.startswith("_")]
        require([get_json_schema(m) for m in public] == [THE_TOOL_SCHEMA], "schema drift")
        # Native constructor discovers environment methods first, so self.tools
        # is truthy before the template-selection conditional is evaluated.
        config = training_config()
        native = SimpleNamespace(
            processing_class=tokenizer, _tokenizer=tokenizer,
            chat_template=selected, chat_template_kwargs={"enable_thinking": False},
            _is_vlm=False, use_vllm=False, tools=public,
            model=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=8192)),
            max_tool_calling_iterations=prepared.max_tool_calling_iterations,
            max_completion_length=config["max_completion_length"],
            _sync_tool_dicts=[{"run_program": environment.run_program}],
            _async_tool_dicts=[{}],
        )
        prompt_ids = tokenizer.apply_chat_template(
            row["prompt"], tools=public, chat_template=native.chat_template,
            add_generation_prompt=True, tokenize=True, return_dict=False,
            **native.chat_template_kwargs,
        )
        stock_prompt_ids = tokenizer.apply_chat_template(
            row["prompt"], tools=public, chat_template=None,
            add_generation_prompt=True, tokenize=True, return_dict=False,
            **native.chat_template_kwargs,
        )
        require("PRIVATE_GOLD" not in tokenizer.decode(prompt_ids), "gold leaked")
        captured_suffixes = []

        def suffix(messages):
            ids = methods["_get_tool_suffix_ids"](native, messages)
            captured_suffixes.append(ids[:])
            return ids

        native._get_tool_suffix_ids = suffix
        scripted_final = tokenizer.encode(FINAL + tokenizer.eos_token, add_special_tokens=False)
        native._generate_single_turn = lambda *a, **kw: ([scripted_final[:]], None)
        call = {"type": "function", "function": {"name": "run_program", "arguments": {"code": PROGRAM}}}
        assistant = {"role": "assistant", "content": "", "tool_calls": [call]}
        scripted_call = tokenizer.encode(
            "<tool_call>\n" + json.dumps({"name": "run_program", "arguments": {"code": PROGRAM}})
            + "\n</tool_call>" + tokenizer.eos_token,
            add_special_tokens=False,
        )
        result = methods["_tool_call_loop"](
            native, [copy.deepcopy(row["prompt"])], [prompt_ids],
            [scripted_call[:]], [[assistant]], None, None, {},
        )
        masks, transcripts, ids, logprobs, calls, failures, _ = result
        require(calls == 1 and failures == 0, "real SQL tool execution failed")
        require(transcripts[0][1]["content"].strip() == "17", "wrong SQL observation")
        require(len(captured_suffixes) == 1, "unexpected suffix count")
        external = captured_suffixes[0]
        expected_ids = scripted_call + external + scripted_final
        expected_mask = [1] * len(scripted_call) + [0] * len(external) + [1] * len(scripted_final)
        require(ids == [expected_ids], "external token insertion mismatch")
        require(masks == [expected_mask], "native external token mask mismatch")
        # MISSING: actual response parsing, sampling likelihoods and training.
        require(logprobs is None, "invented sampler logprobs")
        reward = prepared.reward(
            completions=transcripts, answer=[row["answer"]], db_id=[row["db_id"]],
        )
        require(reward == [1.0], "final scripted SQL reward mismatch")
        require(prepared.dataset_rows == unchanged_rows, "frozen row prompt mutated")
        require(tokenizer.chat_template == original_template, "stock tokenizer template mutated")
        output = {
            "stock_helper_prefix_preserving": False,
            "stock_boundary": stock_boundary, "native_template_boundary": selected_boundary,
            "cached_matches_official_qwen3_template": exact_match,
            "cached_native_helper_selection_error": selection_error,
            "cached_native_helper_selected": cached_selected is not None,
            "canonical_identity_view_selects_training_template": True,
            "selected_template_production_approved": False,
            "cached_template_sha256": sha(original_template.encode()),
            "native_template_sha256": sha(selected.encode()),
            "stock_prompt_tokens": len(stock_prompt_ids),
            "native_trainer_template_prompt_tokens": len(prompt_ids),
            "unchanged_completion_cap": native.max_completion_length,
            "required_minimum_context": len(prompt_ids) + native.max_completion_length,
            "scripted_call_tokens": len(scripted_call), "external_suffix_tokens": len(external),
            "scripted_final_tokens": len(scripted_final),
            "external_mask_zero_count": masks[0].count(0),
            "discovered_schema_count": len(public), "sql_value": 17,
            "execution_reward": reward, "sampler_logprobs": None,
            "parser": "fixture, not tested", "models_loaded": 0,
            "training_steps": 0, "gradients_observed": 0,
        }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("reference requires unoptimized Python")
    main()
