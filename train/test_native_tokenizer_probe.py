"""Synthetic interface checks only; no real tokenizer/native execution."""
from __future__ import annotations

import builtins
import hashlib
import importlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest


REVISION = "db4e90b8359f816f09bf5c944797ce116f26da3c"
TEMPLATE = "synthetic registered template"
SUFFIX = "<think>\n\n</think>\n\n"


def _api():
    path = Path(__file__).with_name("native_tokenizer_probe.py")
    assert path.is_file(), "missing bounded tokenizer probe"
    module = importlib.import_module("train.native_tokenizer_probe")
    assert callable(getattr(module, "_probe_local_tokenizer", None))
    return module


class SyntheticTokenizer:
    chat_template = TEMPLATE

    def __init__(self):
        self.calls = []
        self.ids = [11, 22, 33]
        self.suffix = SUFFIX
        self.failure = None

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.failure:
            raise RuntimeError(self.failure)
        if kwargs["tokenize"]:
            return self.ids
        return messages[-1]["content"] + self.suffix


@pytest.fixture
def rig(tmp_path, monkeypatch):
    native = importlib.import_module("train.native_model")
    directory = tmp_path / "synthetic-model"
    directory.mkdir()
    (directory / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": TEMPLATE}), encoding="utf-8")
    tokenizer = SyntheticTokenizer()
    events = []

    def verify(path, *, model_revision):
        events.append("verify")
        assert str(path) == str(directory)
        assert model_revision == REVISION
        return SimpleNamespace(path=str(directory))

    def load(path, **kwargs):
        events.append(("load", path, kwargs))
        return tokenizer

    monkeypatch.setattr(native, "verify_local_model", verify)

    class Rig(SimpleNamespace):
        @property
        def api(self):
            if "_module" not in self.__dict__:
                self._module = _api()
                monkeypatch.setattr(self._module, "_load_tokenizer", load)
            return self._module

    def run(**kwargs):
        options = {
            "model_revision": REVISION, "max_seq_length": 16,
            "completion_cap": 4, "admit": lambda: events.append("admit"),
        }
        options.update(kwargs)
        return state.api._probe_local_tokenizer(directory, **options)

    state = Rig(native=native, directory=directory, tokenizer=tokenizer,
                events=events, run=run)
    return state


def test_cold_import_has_zero_effects(monkeypatch):
    path = Path(__file__).with_name("native_tokenizer_probe.py")
    assert path.is_file(), "missing bounded tokenizer probe"
    source = path.read_text(encoding="utf-8")
    code = compile(source, str(path), "exec")
    original_import = builtins.__import__
    events = []

    def denied(*args, **kwargs):
        events.append("effect")
        raise AssertionError("cold import effect")

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] not in {"__future__", "hashlib", "json", "re"}:
            return denied()
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", denied)
        patch.setattr(Path, "open", denied)
        patch.setattr(socket, "socket", denied)
        patch.setattr(builtins, "__import__", guarded_import)
        exec(code, {"__name__": "cold_tokenizer_probe"})
    assert events == []


def test_wrong_revision_has_zero_loads(rig):
    with pytest.raises(rig.api.TokenizerProbeError, match="revision"):
        rig.run(model_revision="0" * 40)
    assert rig.events == []


def test_tamper_has_zero_loads(rig, monkeypatch):
    raw = b'{"chat_template":"synthetic registered template"}'
    member = rig.directory / "tokenizer_config.json"
    member.write_bytes(raw)
    inventory = rig.native._Inventory(
        "synthetic", REVISION,
        (rig.native._File("tokenizer_config.json", len(raw),
                          hashlib.sha256(raw).hexdigest()),),
    )

    def verify(path, *, model_revision):
        return rig.native._verify_directory(path, inventory, "0" * 64)

    assert verify(rig.directory, model_revision=REVISION).files_verified == 1
    member.write_bytes(b"!" + raw[1:])
    monkeypatch.setattr(rig.native, "verify_local_model", verify)
    with pytest.raises(rig.api.TokenizerProbeError, match="byte admission"):
        rig.run()
    assert rig.events == ["admit"]


def test_host_admission_precedes_reads(rig):
    def denied():
        raise RuntimeError("synthetic custody denied")

    with pytest.raises(rig.api.TokenizerProbeError, match="host admission"):
        rig.run(admit=denied)
    assert rig.events == []


def test_original_local_flags_and_four_prompts(rig):
    result = rig.run()
    assert rig.events == [
        "admit", "verify",
        ("load", str(rig.directory),
         {"local_files_only": True, "trust_remote_code": False}),
    ]
    schema = importlib.import_module("train.grpo_ptc").THE_TOOL_SCHEMA
    assert len(result["fixtures"]) == 4
    assert len(rig.tokenizer.calls) == 8
    for _, kwargs in rig.tokenizer.calls:
        assert kwargs == {
            "tools": [schema], "chat_template": TEMPLATE,
            "add_generation_prompt": True, "tokenize": kwargs["tokenize"],
            "return_dict": False, "enable_thinking": False,
        }
    assert [kw["tokenize"] for _, kw in rig.tokenizer.calls] == [False, True] * 4


def test_template_mismatch_refuses(rig):
    rig.tokenizer.chat_template = "changed template"
    with pytest.raises(rig.api.TokenizerProbeError, match="template identity"):
        rig.run()
    assert rig.tokenizer.calls == []


def test_thinking_mismatch_refuses(rig, monkeypatch):
    original = importlib.import_module("train.dead_group_probe")
    with monkeypatch.context() as patch:
        patch.setattr(original, "CHAT_TEMPLATE_KWARGS", {"enable_thinking": True})
        with pytest.raises(rig.api.TokenizerProbeError, match="thinking-off"):
            rig.run()
    assert not any(isinstance(event, tuple) for event in rig.events)
    rig.tokenizer.suffix = "<think>synthetic reasoning</think>"
    with pytest.raises(rig.api.TokenizerProbeError, match="thinking-off"):
        rig.run()
    assert len(rig.tokenizer.calls) == 1


def test_context_boundary_and_one_token_over(rig):
    result = rig.run(max_seq_length=7)
    assert [row["token_length"] for row in result["fixtures"]] == [3] * 4
    with pytest.raises(rig.api.TokenizerProbeError, match="context limit"):
        rig.run(max_seq_length=6)


def test_unicode_and_diagnostics_privacy(rig, capsys):
    result = rig.run()
    rendered = [messages[-1]["content"] + SUFFIX
                for messages, kwargs in rig.tokenizer.calls if not kwargs["tokenize"]]
    assert len(rendered) == 4
    assert any(not text.isascii() for text in rendered)
    assert result == {
        "max_seq_length": 16, "completion_cap": 4,
        "template_sha256": hashlib.sha256(TEMPLATE.encode("utf-8")).hexdigest(),
        "fixtures": [{
            "rendered_bytes": len(text.encode("utf-8")),
            "rendered_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "token_length": 3,
            "tokens_sha256": hashlib.sha256(b"[11,22,33]").hexdigest(),
        } for text in rendered],
    }
    serialized = json.dumps(result)
    for text in rendered + [str(rig.directory), TEMPLATE, "[11, 22, 33]"]:
        assert text not in serialized
    assert capsys.readouterr() == ("", "")


def test_dependency_exception_is_private(rig, monkeypatch):
    private = "synthetic-private-path-and-prompt"

    def fail(*args, **kwargs):
        raise RuntimeError(private)

    with monkeypatch.context() as patch:
        patch.setattr(rig.api, "_load_tokenizer", fail)
        with pytest.raises(rig.api.TokenizerProbeError) as caught:
            rig.run()
        assert private not in str(caught.value)
        assert caught.value.__suppress_context__ is True
    rig.tokenizer.failure = private
    with pytest.raises(rig.api.TokenizerProbeError) as caught:
        rig.run()
    assert private not in str(caught.value)
    assert caught.value.__suppress_context__ is True


def test_invalid_limits_and_token_ids(rig):
    for options in (
        {"max_seq_length": True}, {"completion_cap": 0},
        {"max_seq_length": 131073}, {"completion_cap": 16},
    ):
        with pytest.raises(rig.api.TokenizerProbeError, match="limit"):
            rig.run(**options)
    assert rig.events == []
    for ids in ([], [True], [-1], [1.5], [2**32]):
        rig.tokenizer.ids = ids
        with pytest.raises(rig.api.TokenizerProbeError, match="token IDs"):
            rig.run()
    rig.tokenizer.ids = [1]
    rig.tokenizer.suffix = "x" * 65537 + SUFFIX
    with pytest.raises(rig.api.TokenizerProbeError, match="render limit"):
        rig.run()
