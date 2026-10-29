"""Stdlib admission for a contamination-test tokenizer, not model approval.

Symlinks are allowed: local HF snapshots use them. Hashes check observed bytes,
not upstream authenticity or cache immutability. Files can change between
admission and loader reads (TOCTOU); this diagnostic is not a security sandbox.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import re


class TokenizerArtifactError(ValueError):
    """Requested test artifact or tokenizer dependency cannot be admitted."""


def load_tokenizer_artifact(path, *, expected_files, loader=None):
    """Check every declared file before importing/calling the tokenizer loader.

    ``expected_files`` is a frozen test manifest, never digests generated from
    whatever happens to be in ``path``. No implicit cache/model-name resolver.
    ``loader`` injection is for interface tests; integration uses Transformers.
    """
    if not isinstance(expected_files, Mapping) or not expected_files:
        raise TokenizerArtifactError("invalid artifact manifest: nonempty mapping required")
    for name, digest in expected_files.items():
        if (not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) is None
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise TokenizerArtifactError("invalid artifact manifest filename or SHA256")
    if (not isinstance(path, (str, os.PathLike))
            or not isinstance(os.fspath(path), str)
            or not os.fspath(path).strip()):
        raise TokenizerArtifactError("explicit local artifact directory is required")
    if loader is not None and not callable(loader):
        raise TokenizerArtifactError("tokenizer loader must be callable")
    try:
        directory = Path(path)
        if not directory.is_dir():
            raise TokenizerArtifactError("explicit local artifact directory does not exist")
        for name, expected in expected_files.items():
            file_path = directory / name
            if not file_path.is_file():
                raise TokenizerArtifactError(f"missing required tokenizer file: {name}")
            digest = hashlib.sha256()
            with file_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise TokenizerArtifactError(f"tokenizer digest mismatch: {name}")
    except (OSError, ValueError) as exc:
        if isinstance(exc, TokenizerArtifactError):
            raise
        raise TokenizerArtifactError(f"cannot read local tokenizer artifact: {exc}") from exc

    if loader is None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise TokenizerArtifactError(
                "requested tokenizer integration requires transformers") from exc
        loader = AutoTokenizer.from_pretrained
    return loader(str(directory), local_files_only=True, trust_remote_code=False)
