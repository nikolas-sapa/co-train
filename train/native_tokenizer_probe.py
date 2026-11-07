"""Private stock-tokenizer diagnostic, never native-template or launch approval.

Cold import performs no artifact/framework access. Trusted host admission must
hold exclusive read-only custody through verification and loading: observed
hashes alone do not close the verifier/loader TOCTOU boundary. No CLI or default
host adapter is provided. Real tokenizer execution is separate from fixture tests.
"""
from __future__ import annotations

import hashlib
import json
import re


_MAX_CONTEXT = 131072
_MAX_RENDER_BYTES = 65536
_MAX_CONFIG_BYTES = 1024 * 1024
_PROMPTS = (
    "Return SQL selecting the integer 1.",
    "Return SQL counting rows in synthetic_table.",
    "Return SQL selecting a literal containing a quote: O'Brien.",
    "Return SQL selecting the Unicode literal: caf\u00e9 \u6771\u4eac.",
)


class TokenizerProbeError(ValueError):
    """Fixed privacy-safe diagnostic; never includes artifact or prompt text."""


def _load_tokenizer(path, **kwargs):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(path, **kwargs)


def _registered_template(path):
    from pathlib import Path

    try:
        with (Path(path) / "tokenizer_config.json").open("rb") as stream:
            raw = stream.read(_MAX_CONFIG_BYTES + 1)
        if len(raw) > _MAX_CONFIG_BYTES:
            raise TokenizerProbeError("tokenizer configuration limit exceeded")
        value = json.loads(raw)
        template = value.get("chat_template")
        if type(template) is not str or not template:
            raise TokenizerProbeError("registered template identity unavailable")
        return template
    except Exception:
        raise TokenizerProbeError("registered template identity unavailable") from None


def _probe_local_tokenizer(
    model_dir, *, model_revision, max_seq_length, completion_cap, admit,
):
    """Explicit host-only operation; returns lengths/hashes/limits, not text.

    `admit` is mandatory trusted host code, not a caller-supplied proof record.
    It must reject absent tokenizer-only authority or mutable source custody.
    This operation does not call or relax any native training preflight gate.
    """
    from train import native_model

    if model_revision != native_model.MODEL_REVISION:
        raise TokenizerProbeError("unregistered tokenizer revision")
    if (
        type(max_seq_length) is not int
        or not 1 <= max_seq_length <= _MAX_CONTEXT
        or type(completion_cap) is not int
        or not 1 <= completion_cap < max_seq_length
    ):
        raise TokenizerProbeError("invalid tokenizer context limit")
    if not callable(admit):
        raise TokenizerProbeError("explicit host admission required")
    try:
        admit()
    except Exception:
        raise TokenizerProbeError("host admission refused") from None
    try:
        source = native_model.verify_local_model(
            model_dir, model_revision=model_revision,
        )
    except Exception:
        raise TokenizerProbeError("registered byte admission failed") from None

    template = _registered_template(source.path)
    from train import dead_group_probe, grpo_ptc

    thinking_kwargs = dict(dead_group_probe.CHAT_TEMPLATE_KWARGS)
    if (
        set(thinking_kwargs) != {"enable_thinking"}
        or thinking_kwargs["enable_thinking"] is not False
    ):
        raise TokenizerProbeError("original thinking-off settings mismatch")
    try:
        tokenizer = _load_tokenizer(
            source.path, local_files_only=True, trust_remote_code=False,
        )
        loaded_template = tokenizer.chat_template
    except Exception:
        raise TokenizerProbeError("local tokenizer load failed") from None
    if type(loaded_template) is not str or loaded_template != template:
        raise TokenizerProbeError("loaded template identity mismatch")

    fixtures = []
    for prompt in _PROMPTS:
        messages = [{"role": "user", "content": prompt}]
        options = {
            "tools": [grpo_ptc.THE_TOOL_SCHEMA],
            "chat_template": template,
            "add_generation_prompt": True,
            "return_dict": False,
            **thinking_kwargs,
        }
        try:
            rendered = tokenizer.apply_chat_template(
                messages, tokenize=False, **options,
            )
        except Exception:
            raise TokenizerProbeError("local template render failed") from None
        if type(rendered) is not str or len(rendered) > _MAX_RENDER_BYTES:
            raise TokenizerProbeError("template render limit exceeded")
        try:
            encoded = rendered.encode("utf-8")
        except UnicodeError:
            raise TokenizerProbeError("invalid template Unicode") from None
        if len(encoded) > _MAX_RENDER_BYTES:
            raise TokenizerProbeError("template render limit exceeded")
        if re.search(r"<think>\s*</think>\s*\Z", rendered) is None:
            raise TokenizerProbeError("template thinking-off suffix mismatch")
        try:
            ids = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=True, **options,
            )
        except Exception:
            raise TokenizerProbeError("local template tokenization failed") from None
        if (
            type(ids) is not list or not ids or len(ids) > _MAX_CONTEXT
            or any(type(token) is not int or not 0 <= token < 2**32 for token in ids)
        ):
            raise TokenizerProbeError("invalid template token IDs")
        if len(ids) + completion_cap > max_seq_length:
            raise TokenizerProbeError("tokenizer context limit exceeded")
        fixtures.append({
            "rendered_bytes": len(encoded),
            "rendered_sha256": hashlib.sha256(encoded).hexdigest(),
            "token_length": len(ids),
            "tokens_sha256": hashlib.sha256(
                json.dumps(ids, separators=(",", ":")).encode("ascii"),
            ).hexdigest(),
        })
    return {
        "max_seq_length": max_seq_length,
        "completion_cap": completion_cap,
        "template_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
        "fixtures": fixtures,
    }
