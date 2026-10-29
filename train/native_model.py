"""Source-pinned local byte admission, not runtime or immutable-storage proof.

No download, materialization, framework import or permission change. The native
runtime gate separately refuses until exclusive read-only isolation is reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import BinaryIO

from train import dead_group_probe

MODEL_REVISION = "db4e90b8359f816f09bf5c944797ce116f26da3c"
INVENTORY_SHA256 = "76badf431bfa877225c6d5ea99935c4074af7b47d10065d4b4e7ccbaa5141c2e"
_MAX_INVENTORY = 64 * 1024
_MAX_FILES = 64
_MAX_BYTES = 2 * 1024 * 1024 * 1024


class LocalModelError(ValueError):
    """Local artifact identity admission failed."""


@dataclass(frozen=True)
class _File:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class _Inventory:
    model_id: str
    revision: str
    files: tuple[_File, ...]


@dataclass(frozen=True)
class VerifiedLocalModel:
    """Observed byte identity only; no authorization or persistent immutability."""

    path: str
    model_id: str
    revision: str
    inventory_sha256: str
    files_verified: int


def _require(condition: object, message: str) -> None:
    if not condition:
        raise LocalModelError(message)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        _require(key not in result, "duplicate inventory key")
        result[key] = value
    return result


def _parse_inventory(raw: bytes, expected_sha256: str) -> _Inventory:
    _require(len(raw) <= _MAX_INVENTORY, "inventory too large")
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256, "untrusted inventory")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise LocalModelError("invalid inventory JSON") from error
    _require(type(value) is dict and set(value) == {"model_id", "revision", "files"}, "invalid inventory fields")
    _require(type(value["model_id"]) is str and value["model_id"], "invalid inventory model ID")
    _require(type(value["revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", value["revision"]), "invalid inventory revision")
    rows = value["files"]
    _require(type(rows) is list and 1 <= len(rows) <= _MAX_FILES, "invalid inventory file count")
    files: list[_File] = []
    names: set[str] = set()
    total = 0
    for row in rows:
        _require(type(row) is dict and set(row) == {"path", "size", "sha256"}, "invalid inventory file")
        name, size, digest = row["path"], row["size"], row["sha256"]
        _require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name), "unsafe inventory path")
        _require(name not in names, "duplicate inventory file")
        _require(type(size) is int and 0 <= size <= _MAX_BYTES, "invalid inventory file size")
        _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid inventory file digest")
        total += size
        _require(total <= _MAX_BYTES, "inventory bytes exceed limit")
        names.add(name)
        files.append(_File(name, size, digest))
    return _Inventory(value["model_id"], value["revision"], tuple(files))


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _scan(fd: int) -> dict[str, os.stat_result]:
    result = {}
    with os.scandir(fd) as entries:
        for entry in entries:
            _require(len(result) < _MAX_FILES, "too many local model members")
            info = entry.stat(follow_symlinks=False)
            _require(stat.S_ISREG(info.st_mode), "nonregular local model member")
            _require(info.st_nlink == 1, "hardlinked local model member")
            result[entry.name] = info
    return result


def _stream_sha256(stream: BinaryIO, size: int) -> str:
    digest = hashlib.sha256()
    count = 0
    while True:
        block = stream.read(min(1024 * 1024, size - count + 1))
        if not block:
            break
        count += len(block)
        _require(count <= size, "local model file grew")
        digest.update(block)
    _require(count == size, "local model file size mismatch")
    return digest.hexdigest()


def _verify_directory(
    model_dir: str | os.PathLike[str], inventory: _Inventory, inventory_sha256: str,
) -> VerifiedLocalModel:
    root = Path(model_dir)
    _require(root.is_absolute() and ".." not in root.parts, "absolute canonical model directory required")
    _require(
        not str(root).lower().endswith(("-bf16", "-bnb-4bit", "-unsloth-bnb-4bit")),
        "model directory must avoid upstream precision/remapping suffixes",
    )
    try:
        # Check from the filesystem root down, before opening the source.
        for component in reversed((root, *root.parents)):
            _require(stat.S_ISDIR(component.lstat().st_mode), "symlinked or non-directory model ancestry")
        before_root = root.lstat()
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            _require(_signature(os.fstat(fd)) == _signature(before_root), "model directory changed")
            actual = _scan(fd)
            _require(set(actual) == {item.path for item in inventory.files}, "local model file inventory mismatch")
            for item in inventory.files:
                source = os.open(
                    item.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                    dir_fd=fd,
                )
                with os.fdopen(source, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "unsafe model file")
                    _require(_signature(before) == _signature(actual[item.path]), "model file changed before read")
                    _require(before.st_size == item.size, "local model file size mismatch")
                    digest = _stream_sha256(stream, item.size)
                    _require(_signature(before) == _signature(os.fstat(stream.fileno())), "model file changed during read")
                    _require(digest == item.sha256, "local model content digest mismatch")
            final = _scan(fd)
            _require(set(final) == set(actual), "local model directory changed")
            _require(all(_signature(final[name]) == _signature(info) for name, info in actual.items()), "model files changed")
            _require(_signature(root.lstat()) == _signature(before_root), "model directory changed")
        finally:
            os.close(fd)
    except OSError as error:
        raise LocalModelError("cannot verify local model source") from error
    return VerifiedLocalModel(
        str(root), inventory.model_id, inventory.revision,
        inventory_sha256, len(inventory.files),
    )


def verify_local_model(
    model_dir: str | os.PathLike[str], *, model_revision: str,
) -> VerifiedLocalModel:
    """Admit only this source-pinned inventory, never a caller-supplied manifest."""
    _require(model_revision == MODEL_REVISION, "unregistered model revision")
    path = Path(__file__).with_name("native_model_inventory.json")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_INVENTORY + 1)
    inventory = _parse_inventory(raw, INVENTORY_SHA256)
    _require(inventory.model_id == dead_group_probe.MODEL, "inventory model ID mismatch")
    _require(inventory.revision == model_revision, "inventory revision mismatch")
    return _verify_directory(model_dir, inventory, INVENTORY_SHA256)
