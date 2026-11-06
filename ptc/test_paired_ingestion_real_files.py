"""Parent checks for real file errors omitted by in-memory stream tests."""

import pytest

from ptc import paired


@pytest.mark.parametrize("reader", (paired.load, paired.rollouts))
def test_real_malformed_utf8_refuses_generically(tmp_path, reader):
    path = tmp_path / "invalid.jsonl"
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="^invalid paired trace record$") as error:
        reader(str(path))
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("reader", (paired.load, paired.rollouts))
def test_real_missing_input_preserves_oserror(tmp_path, reader):
    path = tmp_path / "absent.jsonl"
    with pytest.raises(FileNotFoundError) as error:
        reader(str(path))
    assert error.value.filename == str(path)
