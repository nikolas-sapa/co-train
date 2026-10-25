"""Frozen synthetic ROWCOUNT assets. Trusted generation only, never model SQL."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import stat
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from bench.task import SqlTask
from ptc.sql_isolation import canonical_json_bytes
from train import sql_episodes as evidence

MAX_BYTES = 8 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
PAIR_FIRST = ("B", "L", "L", "B", "B", "L", "L", "B")
SCOPE = ("fixture", "select-count", "aggregate")
SEEDS = tuple(827300 + i * 7919 for i in range(20))


def canonical_bytes(value) -> bytes:
    try:
        raw = canonical_json_bytes(value)
    except (RecursionError, OverflowError, UnicodeError) as exc:
        raise ValueError("invalid bounded JSON") from exc
    if len(raw) > MAX_BYTES:
        raise ValueError("artifact exceeds 8 MiB")
    return raw


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def closed(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("unknown/missing closed fields")
    return value


def integer(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= (1 << 63) - 1:
        raise ValueError("bounded integer required")
    return value


def text(value, *, nonempty=True, maximum=MAX_BYTES):
    if type(value) is not str:
        raise TypeError("string required")
    if not (1 if nonempty else 0) <= len(value.encode("utf-8", "strict")) <= maximum:
        raise ValueError("string size outside bound")
    return value


def sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("lowercase SHA256 required")
    return value


def strict_json(raw: bytes):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("bounded bytes required")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON")
    try:
        value = json.loads(raw.decode("utf-8", "strict"),
                           object_pairs_hook=pairs, parse_constant=constant)
        # Also rejects overflowed finite syntax (1e999), invalid surrogate text.
        canonical_bytes(value)
        return value
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid UTF-8 JSON") from exc


def envelope_bytes(format, payload):
    raw = canonical_bytes({"format": format, "schema_version": 1,
                           "payload": payload, "sha256": digest(canonical_bytes(payload))}) + b"\n"
    if len(raw) > MAX_BYTES:
        raise ValueError("whole envelope exceeds 8 MiB")
    return raw


def open_envelope(raw, format):
    obj = closed(strict_json(raw), ("format", "schema_version", "payload", "sha256"))
    if (type(obj["schema_version"]) is not int or obj["schema_version"] != 1
            or obj["format"] != format or sha(obj["sha256"]) != digest(canonical_bytes(obj["payload"]))
            or canonical_bytes(obj) + b"\n" != raw):
        raise ValueError("noncanonical or mismatched envelope")
    return obj["payload"]


def safe_path(path: Path, *, exists=False, directory=False) -> Path:
    """No traversal, symlink components, checkout writes or noncanonical aliases.

    Storage is operator-owned and trusted against concurrent ancestor replacement,
    as for the committed ledger. Never follow a final file symlink/hardlink.
    """
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError("canonical absolute path required")
    if "\x00" in str(path) or str(path) != os.path.normpath(str(path)):
        raise ValueError("noncanonical path")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError("symlink path forbidden")
    if path.is_relative_to(ROOT):
        raise ValueError("pilot data must live outside checkout")
    if exists:
        info = path.lstat()
        if directory:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("directory required")
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("single-link regular file required")
    return path


def read_file(path: Path) -> bytes:
    safe_path(path, exists=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            raise ValueError("unsafe/oversized input file")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input exceeds 8 MiB")
    return raw


def fsync_dir(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path: Path, raw: bytes):
    safe_path(path)
    safe_path(path.parent, exists=True, directory=True)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("bounded bytes required")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_dir(path.parent)


@dataclass(frozen=True, slots=True)
class PilotAsset:
    case_id: str
    partition: str
    seed: int
    task: SqlTask
    ids: evidence.EpisodeIds
    task_fingerprint: str
    db_sha256: str

    def __post_init__(self):
        text(self.case_id)
        if self.partition not in ("development", "qualification", "heldout"):
            raise ValueError("invalid partition")
        integer(self.seed)
        if type(self.task) is not SqlTask or type(self.ids) is not evidence.EpisodeIds:
            raise TypeError("concrete task and IDs required")
        self.task.__post_init__()
        evidence._validate_ids(self.ids)
        payload = evidence._task_payload(self.task)
        if (self.task.source, self.task.shape, self.task.coarse_shape) != SCOPE:
            raise ValueError("ROWCOUNT scope mismatch")
        if sha(self.task_fingerprint) != evidence._fingerprint(payload):
            raise ValueError("task fingerprint mismatch")
        sha(self.db_sha256)
        if str(safe_path(Path(self.task.db_path))) != self.task.db_path:
            raise ValueError("canonical database path string required")


@dataclass(frozen=True, slots=True)
class PilotManifest:
    schema_version: int
    run_id: str
    assets: tuple[PilotAsset, ...]
    pair_first: tuple[str, ...]

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported manifest version")
        if type(self.run_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", self.run_id) is None:
            raise ValueError("safe ASCII run ID required")
        if type(self.assets) is not tuple or len(self.assets) != 20:
            raise ValueError("exactly 20 frozen assets required")
        if type(self.pair_first) is not tuple or self.pair_first != PAIR_FIRST:
            raise ValueError("pair order differs from frozen protocol")
        for i, asset in enumerate(self.assets):
            if type(asset) is not PilotAsset:
                raise TypeError("concrete asset required")
            asset.__post_init__()
            partition = "development" if i < 8 else "qualification" if i < 12 else "heldout"
            if asset.partition != partition or asset.seed != SEEDS[i]:
                raise ValueError("frozen partition/seed order differs")
            if (asset.ids.run_id != self.run_id or asset.ids.split_id != partition
                    or asset.ids.episode_id != asset.case_id
                    or (asset.ids.corpus_id, asset.ids.policy_id, asset.ids.policy_revision)
                    != ("sql-pilot-rowcount-v1", "sql-pilot", "v1")):
                raise ValueError("ID provenance differs")
        for getter in (lambda a: a.case_id, lambda a: a.seed, lambda a: a.task_fingerprint,
                       lambda a: a.db_sha256, lambda a: a.task.name, lambda a: a.task.question,
                       lambda a: a.task.db_id, lambda a: a.task.db_path, lambda a: a.ids):
            if len({getter(a) for a in self.assets}) != 20:
                raise ValueError("assets must be pairwise disjoint")


def manifest_bytes(manifest: PilotManifest) -> bytes:
    if type(manifest) is not PilotManifest:
        raise TypeError("concrete manifest required")
    manifest.__post_init__()
    return envelope_bytes("sql_pilot_manifest", asdict(manifest))


def manifest_sha256(manifest: PilotManifest) -> str:
    return digest(manifest_bytes(manifest))


def load_manifest(path: Path) -> PilotManifest:
    payload = closed(open_envelope(read_file(path), "sql_pilot_manifest"),
                     ("schema_version", "run_id", "assets", "pair_first"))
    if type(payload["assets"]) is not list or type(payload["pair_first"]) is not list:
        raise TypeError("JSON arrays required")
    assets = []
    for value in payload["assets"]:
        obj = dict(closed(value, tuple(f.name for f in fields(PilotAsset))))
        obj["task"] = SqlTask(**closed(obj["task"], tuple(f.name for f in fields(SqlTask))))
        obj["ids"] = evidence.EpisodeIds(**closed(obj["ids"], tuple(f.name for f in fields(evidence.EpisodeIds))))
        assets.append(PilotAsset(**obj))
    result = PilotManifest(payload["schema_version"], payload["run_id"],
                           tuple(assets), tuple(payload["pair_first"]))
    validate_manifest(result)
    return result


def validate_manifest(manifest: PilotManifest) -> None:
    manifest_bytes(manifest)
    for asset in manifest.assets:
        safe_path(Path(asset.task.db_path), exists=True)
        evidence._check_database(asset.task, asset.db_sha256)


def prepare_manifest(target: Path, *, output_dir: Path, run_id: str) -> PilotManifest:
    safe_path(target)
    safe_path(output_dir)
    # Validate run identity before creating any files.
    if type(run_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", run_id) is None:
        raise ValueError("safe ASCII run ID required")
    if target.exists() or output_dir.exists():
        raise FileExistsError("prepare requires a new asset directory and manifest")
    if target.parent != output_dir:
        safe_path(target.parent, exists=True, directory=True)
    safe_path(output_dir.parent, exists=True, directory=True)
    output_dir.mkdir(mode=0o700)
    fsync_dir(output_dir.parent)
    assets = []
    for i, seed in enumerate(SEEDS):
        partition = "development" if i < 8 else "qualification" if i < 12 else "heldout"
        case_id = f"rowcount-{i + 1:02d}"
        rng = random.Random(seed)  # independent DB construction, no copy/relabel
        table = "records " + format(rng.getrandbits(64), "016x") + ' "α'
        quoted = '"' + table.replace('"', '""') + '"'
        path = output_dir / (case_id + ".sqlite")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        db = sqlite3.connect(path)
        try:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("CREATE TABLE " + quoted + " (value INTEGER, label TEXT)")
            db.executemany("INSERT INTO " + quoted + " VALUES (?, ?)",
                           [(rng.randrange(-1000000, 1000000), format(rng.getrandbits(64), "016x"))
                            for _ in range(rng.randrange(0, 48))])
            db.commit()
        finally:
            db.close()
        path.chmod(0o400)
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        task = SqlTask(case_id, f"For case {case_id}, count rows in the only user table.",
                       "", "SELECT COUNT(*) FROM " + quoted, case_id, str(path),
                       "simple", "derived", "select-count", "aggregate", "fixture")
        ids = evidence.EpisodeIds("sql-pilot-rowcount-v1", partition, run_id, case_id, "sql-pilot", "v1")
        assets.append(PilotAsset(case_id, partition, seed, task, ids,
                                evidence._fingerprint(evidence._task_payload(task)), evidence._db_digest(task)))
    fsync_dir(output_dir)
    manifest = PilotManifest(1, run_id, tuple(assets), PAIR_FIRST)
    validate_manifest(manifest)
    write_new(target, manifest_bytes(manifest))
    return manifest
