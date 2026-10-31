"""Consumer-only error-boundary regressions, synthetic artifacts throughout."""
import hashlib
import json

import pytest

from bench import prepare
from bench.test_prepare import _canonical_bytes, _staged_draw, _validate


def _published(tmp_path):
    root, draw, draw_sha = _staged_draw(prepare, tmp_path)
    supplement = tmp_path / "supplement.json"
    _validate(prepare, root, draw, supplement, draw_sha)
    return root, draw, supplement


def _load(root, draw, supplement):
    return prepare.load_validated_draw(
        root, draw, supplement,
        expected_draw_sha256=hashlib.sha256(draw.read_bytes()).hexdigest(),
        expected_supplement_sha256=hashlib.sha256(supplement.read_bytes()).hexdigest(),
        fixture=True,
    )


@pytest.mark.parametrize("document", ["draw", "supplement"])
def test_deep_json_refuses_before_corpus(tmp_path, monkeypatch, document):
    root, draw, supplement = _published(tmp_path)
    target = draw if document == "draw" else supplement
    target.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000 + b"\n")

    def forbidden(*args, **kwargs):
        pytest.fail("malformed document reached corpus access")

    monkeypatch.setattr(prepare, "_corpus", forbidden)
    # Runtime-dependent decoder depth is not the error-boundary oracle.
    with pytest.raises(prepare.PreparationError, match="document|unexpected keys"):
        _load(root, draw, supplement)


@pytest.mark.parametrize("document", ["draw", "supplement"])
def test_parser_recursion_error_is_bounded_at_consumer(tmp_path, monkeypatch, document):
    root, draw, supplement = _published(tmp_path)
    calls = 0
    sentinel = "PRIVATE_RECURSION_SENTINEL"

    def fault(raw):
        nonlocal calls
        calls += 1
        raise RecursionError(sentinel)

    def forbidden(*args, **kwargs):
        pytest.fail("parser failure reached corpus access")

    monkeypatch.setattr(prepare, f"_parse_{document}", fault)
    monkeypatch.setattr(prepare, "_corpus", forbidden)
    with pytest.raises(prepare.PreparationError, match="^invalid preparation document$") as caught:
        _load(root, draw, supplement)
    assert calls == 1
    assert sentinel not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_oversized_timeout_integer_is_bounded_preparation_error(tmp_path, monkeypatch):
    root, draw, supplement = _published(tmp_path)
    doc = json.loads(draw.read_bytes())
    doc["settings"]["timeout_s"] = 10 ** 400
    draw.write_bytes(_canonical_bytes(doc))

    def forbidden(*args, **kwargs):
        pytest.fail("oversized integer reached corpus access")

    monkeypatch.setattr(prepare, "_corpus", forbidden)
    with pytest.raises(prepare.PreparationError, match="document") as caught:
        _load(root, draw, supplement)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("phase", [1, 2])
def test_identity_oserror_is_neutral_and_unchained(tmp_path, monkeypatch, phase):
    root, draw, supplement = _published(tmp_path)
    original = prepare._identity
    calls = 0
    sentinel = "PRIVATE_FILESYSTEM_SENTINEL"

    def fault(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == phase:
            raise FileNotFoundError(sentinel)
        return original(*args, **kwargs)

    monkeypatch.setattr(prepare, "_identity", fault)
    with pytest.raises(prepare.PreparationError, match="identity") as caught:
        _load(root, draw, supplement)
    assert calls == phase
    assert sentinel not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
