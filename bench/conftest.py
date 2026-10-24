"""Explicit, test-only tokenizer integration. Default collection does no loading."""

import json
from pathlib import Path

import pytest

from bench.tokenizer_artifact import load_tokenizer_artifact


def pytest_addoption(parser):
    parser.addoption(
        "--tokenizer-artifact", default=None,
        help="Explicit local directory matching bench/tokenizer_artifact.json; no acquisition.")


@pytest.fixture(scope="session")
def contamination_tokenizer(request):
    # Reading the manifest and importing Transformers happen only on request.
    manifest = json.loads(Path(__file__).with_name("tokenizer_artifact.json").read_text())
    return load_tokenizer_artifact(
        request.config.getoption("--tokenizer-artifact"), expected_files=manifest["files"])
