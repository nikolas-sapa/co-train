"""V311 SOURCE-ONLY MUTATIONAL RED. UNRUN journal candidate, NOT runtime clearance.

Exactly two journal budget predicates intentionally disabled pending parent RED.
Historical V308 header below describes its source, NOT execution of this file.
V307 allocation-accounting correction; initial RED helper semantics. SOURCE ONLY, UNRUN; parent stages after review.

One maximum-volume case, not the old six controls. Actual A/C custody, hashes,
receipt/identity/close/seal/publication/release; synthetic process/channel/stager
observations and owned source/interpreter/SDK metadata stand-ins remain.
Four random blobs are NOT JSON checkpoints, native/tensor/science evidence.
No worker executes. No public admission approval or real-process permission.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import sys
import time
from types import SimpleNamespace

import pytest

from train import test_qualification_isolated_owner as base


# Expose only the process-denial fixture, never import old collected tests.
prohibit_real_effects = base.prohibit_real_effects
api, adapter, program, native = base.api, base.adapter, base.program, base.native
original = program.original
FILE_BYTES = 2 * 1024**3
TOTAL_BYTES = 4 * FILE_BYTES
RESERVE = 5_608_091_203
HEADROOM = 1024**2
MANIFEST_LIMIT = 65_536
KEYS = (
    "checkpoint-1/native-observation.json",
    "checkpoint-1/trainer_state.json",
    "checkpoint-2/native-observation.json",
    "checkpoint-2/trainer_state.json",
)
EVIDENCE_KEYS = ("attempt-latch.json", "attempt-observations.json", "verification.json")
# Set only by the pinned in-process Linux driver, never inferred from cache state.
_LINUX_V364_CONTEXT = None


def _linux_v364_context():
    context = _LINUX_V364_CONTEXT
    if context is None:
        return None
    _require(type(context) is dict and set(context) == {
        "version", "mode", "root", "start_ns", "deadline_ns", "completed"},
        "closed Linux driver context required")
    _require(context["version"] == "v364-linux-cpu-1"
             and context["mode"] == "fresh-generated-not-evicted"
             and context["root"] == str(Path(os.environ["HOME"]).parent)
             and type(context["start_ns"]) is int
             and type(context["deadline_ns"]) is int
             and context["deadline_ns"] == context["start_ns"] + 29_000_000_000
             and context["start_ns"] < time.monotonic_ns() < context["deadline_ns"]
             and context["completed"] is False, "matching active Linux driver required")
    return context


def _require(ok, label):
    if not ok:
        raise ValueError(label)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _directory_identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]


def _file_identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_blocks]


def _private_directory(info):
    _require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
             and info.st_uid == os.getuid(), "owned0700 directory required")


def _private_file(info):
    _require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
             and info.st_uid == os.getuid() and info.st_nlink == 1,
             "owned0600 single-link regular file required")


class _OwnedCustody:
    """Retain every acquired generation and required unresolved ancestry."""

    def __init__(self):
        self.records = []

    def _record(self, fd):
        for row in reversed(self.records):
            if row["fd"] == fd and row["state"] == "OPEN":
                return row
        raise RuntimeError("owned open generation required")

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        if any(row["state"] in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN")
               for row in self.records):
            raise RuntimeError("unresolved owned descriptor custody")
        parent = None if dir_fd is None else self._record(dir_fd)
        row = dict(fd=None, parent=parent, state="RESERVED", error=None)
        self.records.append(row)  # Reserve before acquisition.
        try:
            fd = os.open(path, flags, mode, dir_fd=dir_fd)
        except OSError as error:
            row["state"], row["error"] = "NO_FD", error
            raise
        except BaseException as error:
            row["state"], row["error"] = "UNKNOWN", error
            raise
        row["fd"] = fd  # Attach before validation, identity reads or exposure.
        row["state"] = "OPEN"
        return fd

    def close(self, fd):
        row = self._record(fd)
        try:
            row["state"] = "CLOSE_ATTEMPTED"
            os.close(fd)
        except BaseException as error:
            row["state"], row["error"] = "UNKNOWN", error
            raise
        row["state"] = "CLOSED"

    def _required(self, ancestor):
        for row in self.records:
            if row["state"] not in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN"):
                continue
            parent = row["parent"]
            while parent is not None:
                if parent is ancestor:
                    return True
                parent = parent["parent"]
        return False

    def close_all(self):
        first = None
        for row in reversed(self.records):
            if row["state"] != "OPEN" or self._required(row):
                continue
            try:
                self.close(row["fd"])
            except BaseException as error:
                if first is None:
                    first = error
        unresolved = [row for row in self.records
                      if row["state"] in ("RESERVED", "CLOSE_ATTEMPTED", "UNKNOWN")]
        if unresolved:
            # Preserve the original exception object, not only its text.
            error = next((row["error"] for row in unresolved
                          if row["error"] is not None), first)
            if error is not None:
                raise error
            raise RuntimeError("unresolved owned descriptor custody")
        if first is not None:
            raise first


_OWNED = _OwnedCustody()

def _close_fd(fd):
    primary = sys.exception()
    try:
        _OWNED.close(fd)
    except BaseException as secondary:
        if primary is None:
            raise
        primary.add_note("owned descriptor close failed: " + type(secondary).__name__
                         + ": " + str(secondary)[:512])


class _Anchors:
    """Hold and verify exact ancestry; no directory enumeration or global scan."""

    def __init__(self):
        self.entries = []

    def root(self, path):
        _require(type(path) is str and path == str(Path(path))
                 and Path(path).is_absolute() and ".." not in Path(path).parts
                 and "\\" not in path and "\0" not in path and path != "/",
                 "canonical absolute H191 root required")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = _OWNED.open("/", flags)
        self.entries.append((fd, None, None, _directory_identity(os.fstat(fd))))
        for name in Path(path).parts[1:]:
            parent = fd
            fd = _OWNED.open(name, flags, dir_fd=parent)
            self.entries.append((fd, parent, name, _directory_identity(os.fstat(fd))))
        _private_directory(os.fstat(fd))
        self.check()
        return fd

    def child(self, parent, name, *, create=False):
        if create:
            os.mkdir(name, 0o700, dir_fd=parent)
        fd = _OWNED.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                     | os.O_CLOEXEC, dir_fd=parent)
        self.entries.append((fd, parent, name, _directory_identity(os.fstat(fd))))
        _private_directory(os.fstat(fd))
        self.check()
        return fd

    def check(self):
        for fd, parent, name, identity in self.entries:
            _require(_directory_identity(os.fstat(fd)) == identity, "anchor changed")
            if parent is not None:
                _require(_directory_identity(os.stat(
                    name, dir_fd=parent, follow_symlinks=False)) == identity,
                    "named ancestry changed")

    def close(self):
        _OWNED.close_all()  # Retain UNKNOWN rows and their required ancestors.


def _absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError("refuse existing destination: " + name)


def _write_all(fd, raw):
    view = memoryview(raw)
    offset = 0
    while offset < len(view):
        count = os.write(fd, view[offset:offset + 65536])
        _require(count > 0, "write made no progress")
        offset += count


def _exclusive_bytes(parent, name, raw, limit):
    _require(type(raw) is bytes and len(raw) <= limit, "bounded owned output")
    fd = _OWNED.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | os.O_CLOEXEC, 0o600, dir_fd=parent)
    try:
        before = os.fstat(fd)
        _private_file(before)
        _write_all(fd, raw)
        os.fsync(fd)
        after = os.fstat(fd)
        _private_file(after)
        _require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                 and after.st_size == len(raw), "new output generation changed")
        _require(_file_identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                 == _file_identity(after), "new named output changed")
    finally:
        _close_fd(fd)
    os.fsync(parent)


def _closed(value, fields):
    _require(type(value) is dict and set(value) == set(fields), "closed manifest schema")
    return value


def _integer(value, minimum=0, maximum=2**64 - 1):
    _require(type(value) is int and minimum <= value <= maximum,
             "bounded exact manifest integer")
    return value


def _identity_array(value, count):
    _require(type(value) is list and len(value) == count, "identity array shape")
    for item in value:
        _integer(item)


def _same_file_generation(expected, actual):
    return (len(expected) == len(actual) == 10
            and expected[:9] == actual[:9]
            and expected[9] * 512 >= expected[6]
            and actual[9] * 512 >= actual[6])


def _same_rename_generation(before, after):
    return (len(before) == len(after) == 10
            and before[:8] == after[:8]
            and before[9] * 512 >= before[6]
            and after[9] * 512 >= after[6])

def _read_manifest(root_fd, bulk_fd, anchors):
    anchors.check()
    fd = _OWNED.open("manifest.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                 | os.O_CLOEXEC, dir_fd=bulk_fd)
    try:
        before = os.fstat(fd)
        _private_file(before)
        _require(0 < before.st_size <= MANIFEST_LIMIT, "bounded volume manifest")
        parts, count = [], 0
        while count <= before.st_size:
            block = os.read(fd, min(65536, before.st_size - count + 1))
            if not block:
                break
            parts.append(block)
            count += len(block)
        raw = b"".join(parts)
        _require(len(raw) == before.st_size, "manifest actual size changed")
        _require(_file_identity(os.fstat(fd)) == _file_identity(before),
                 "manifest open identity changed")
        _require(_file_identity(os.stat("manifest.json", dir_fd=bulk_fd,
                                       follow_symlinks=False)) == _file_identity(before),
                 "manifest named identity changed")
    finally:
        _close_fd(fd)
    anchors.check()
    _require(_file_identity(os.stat("manifest.json", dir_fd=bulk_fd,
                                   follow_symlinks=False)) == _file_identity(before),
             "closed manifest identity changed")
    doc = json.loads(raw)
    _require(_canonical(doc) == raw, "strict canonical manifest required")
    _closed(doc, ("v", "op", "root_identity", "bulk_identity", "files", "preparation"))
    _require(type(doc["v"]) is int and doc["v"] == 1
             and doc["op"] == "v290-owned-volume", "volume manifest version/op")
    _identity_array(doc["root_identity"], 5)
    _identity_array(doc["bulk_identity"], 5)
    _require(doc["root_identity"] == _directory_identity(os.fstat(root_fd))
             and doc["bulk_identity"] == _directory_identity(os.fstat(bulk_fd)),
             "manifest anchored root identity differs")
    _require(type(doc["files"]) is list and len(doc["files"]) == 4,
             "exactly four generated files required")
    identities = set()
    for number, (entry, key) in enumerate(zip(doc["files"], KEYS), 1):
        _closed(entry, ("name", "key", "size", "sha256", "identity"))
        _require(entry["name"] == f"blob-{number}.bin" and entry["key"] == key,
                 "exact ordered fixture paths required")
        _require(_integer(entry["size"]) == FILE_BYTES, "exact2GiB descriptor")
        _require(type(entry["sha256"]) is str and len(entry["sha256"]) == 64
                 and all(char in "0123456789abcdef" for char in entry["sha256"]),
                 "strict fixture SHA256")
        _identity_array(entry["identity"], 10)
        info = os.stat(entry["name"], dir_fd=bulk_fd, follow_symlinks=False)
        _private_file(info)
        _require(_same_file_generation(entry["identity"], _file_identity(info))
                 and info.st_size == FILE_BYTES and info.st_blocks * 512 >= FILE_BYTES,
                 "generated named blob identity/allocation differs")
        pair = info.st_dev, info.st_ino
        _require(pair != (before.st_dev, before.st_ino) and pair not in identities,
                 "fixture generation alias")
        identities.add(pair)
    prep = _closed(doc["preparation"], (
        "elapsed_ns", "written_bytes", "initial_free_bytes", "final_free_bytes",
        "buffer_bytes", "cache"))
    context = _linux_v364_context()
    _integer(prep["elapsed_ns"], 1, 50_000_000_000 if context is None else 29_000_000_000)
    _require(_integer(prep["written_bytes"]) == TOTAL_BYTES
             and _integer(prep["buffer_bytes"], 1, 8 * 1024**2) == 8 * 1024**2
             and prep["cache"] == (
                 "reused-generated-after-previous-full-read-not-evicted"
                 if context is None else context["mode"]),
             "exact preparation facts required")
    _integer(prep["initial_free_bytes"], TOTAL_BYTES + RESERVE + HEADROOM)
    _integer(prep["final_free_bytes"], RESERVE + HEADROOM)
    return doc


def _case(root, monkeypatch):
    """Reconstruct metadata only; request is8GiB BEFORE original issuance."""
    tmp = root / "volume-case"
    # Caller created this exclusive0700 directory, no external fixture paths.
    source = tmp / "source"
    for key in api.WORKER_SOURCE_KEYS:
        base.put(source / key, ("# owned " + key + "\n").encode())
    sdk = tmp / "sdk"
    for key in api.SDK_REQUIRED_KEYS:
        base.put(sdk / key, ("# owned " + key + "\n").encode())
    executable = base.put(tmp / "owned/python", b"fixture-interpreter", 0o700)
    scratch, home, export_parent = tmp / "scratch", tmp / "home", tmp / "export"
    for path in (scratch, home, export_parent):
        path.mkdir(mode=0o700)
    export = export_parent / "run"
    # Inherited owned-metadata stand-ins, not changes to validation checks.
    monkeypatch.setattr(api, "_DEPLOYED_ROOT", source)
    monkeypatch.setattr(base.guards, "REPO_ROOT", source)
    policy = base.put(tmp / "policy", b"owned independent policy")
    construction = base.put(source / "train/native_training.py", b"# fixture construction\n")
    construction_pin = base.pin(construction, "construction")
    monkeypatch.setattr(native, "_CONSTRUCTION_SHA", construction_pin.sha256)
    tasks = tuple(base.SqlTask(
        name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
        evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
        db_id=name, db_path=str(tmp / "data" / name / f"{name}.sqlite"),
        tier="simple", tier_source="derived", shape="fixture-select",
        coarse_shape="fixture-select", source="fixture") for name, _ in native._FIXTURES)
    request = native.QualificationRequest(
        tasks, tmp / "data", tmp / "model", export,
        (native.FilePin(construction, construction_pin.size, construction_pin.sha256),),
        tuple(native.FilePin(Path(task.db_path), 0, base.EMPTY) for task in tasks),
        native.FilePin(tmp / "inventory", 0, base.EMPTY), "sha256:" + "0" * 64,
        native.AttemptBounds(Decimal("25"), Decimal("0"), Decimal("25"),
                             600, 1024, TOTAL_BYTES, 60))
    items = tuple(SimpleNamespace(
        root="source", key=key, path=source / key,
        size=(source / key).stat().st_size, sha256=base.pin(source / key, key).sha256)
        for key in api.WORKER_SOURCE_KEYS)
    now = int(time.time())
    recipe = base.candidate_recipe()
    auth = base.authority.issue_engineering_authorization(
        request=request, policy_pin=native.FilePin(
            policy, policy.stat().st_size, _sha(policy.read_bytes())),
        terms=base.BudgetTerms(Decimal("25"), Decimal("5")),
        rates=base.ResourceRates("sandbox", *(
            base.RateObservation(Decimal("0.000001"), unit, "fixture", now - 1)
            for unit in ("USD/gpu-second", "USD/physical-core-second", "USD/GiB-second"))),
        workload=base.GpuWorkload(1, 4, Decimal("16"), 600),
        preparation=base.PreparationAccount(Decimal("1"), Decimal("0.5"), Decimal("2")),
        ancillary=base.AncillaryEstimates(Decimal("0.5"), Decimal("0.25"), Decimal("1")),
        now_seconds=now, expires_at_seconds=now + 3600, preparation_seconds=300,
        image_base_reference=recipe.base_reference,
        image_recipe_sha256=base.recipe_sha256(recipe), gpu_label="A100",
        uploads=tuple((item.root, item.key, item.size, item.sha256) for item in items),
        setup_argv=("python", "-m", "pip", "install", "--no-index"))
    assert auth.request is request and not auth.bound
    assert auth.request_binding == native._request_binding(request)
    binding = base.stop.OwnedAppStopBinding(
        interpreter=executable, interpreter_sha256=base.pin(executable, "python").sha256,
        adapter_sha256=base.pin(source / "train/modal_app_stop.py", "adapter").sha256,
        source_root=source / "train", sdk_root=sdk,
        sdk_pins={api._module_name(key): base.pin(sdk / key, key).sha256
                  for key in api.SDK_REQUIRED_KEYS},
        private_scratch=scratch,
        environment={"HOME": str(home), "PATH": f"{executable.parent}:/usr/bin:/bin"},
        rpc_seconds=1, arm_seconds=1, teardown_seconds=1, ownership_confirmed=True)
    timing = binding.timing_facts()
    assert timing.arm_ns == timing.teardown_ns == 1_000_000_000
    spec = base.dto.IsolatedOwnerSpec(
        executable, source, tuple(base.pin(source / key, key) for key in api.WORKER_SOURCE_KEYS),
        sdk, tuple(base.pin(sdk / key, key) for key in api.SDK_REQUIRED_KEYS),
        base.common.ResourceConfig("A100", (0.25, 4.0), (128, 16384)), binding,
        scratch, scratch / "evidence.json")
    return SimpleNamespace(request=request, auth=auth, spec=spec, items=items,
                           root=source, sdk=sdk, export=export, tmp=tmp)


def _documents(request, fixture):
    binding = native._request_binding(request)
    attempt = original._attempt_id(binding, base.APP, base.SANDBOX)
    links = dict(request_sha256=binding, attempt_id=attempt,
                 app_id=base.APP, sandbox_id=base.SANDBOX)
    manifest = [dict(key=entry["key"], size=entry["size"], sha256=entry["sha256"])
                for entry in fixture["files"]]
    assert sum(entry["size"] for entry in manifest) == TOTAL_BYTES
    by_key = {entry["key"]: entry for entry in manifest}
    phases = [dict(phase=phase, pid=100 + phase, returncode=0) for phase in (1, 2)]
    checkpoints = [dict(
        checkpoint=f"checkpoint-{phase}",
        members=["native-observation.json", "trainer_state.json"],
        observation_sha256=by_key[f"checkpoint-{phase}/native-observation.json"]["sha256"],
        trainer_state_sha256=by_key[f"checkpoint-{phase}/trainer_state.json"]["sha256"])
        for phase in (1, 2)]
    receipt = dict(
        v=1, op="remote-verification-receipt", scope=original._REMOTE_VERIFICATION_SCOPE,
        **links, phase_observations=phases, phase_returncodes=[0, 0],
        checkpoints=checkpoints, artifact_bytes=TOTAL_BYTES, manifest=manifest)
    evidence = {
        "attempt-latch.json": original._canonical_json(dict(v=1, op="native-attempt", **links)),
        "attempt-observations.json": original._canonical_json(
            dict(v=1, op="phase-observations", **links, observations=phases)),
        "verification.json": original._canonical_json(receipt),
    }
    assert tuple(sorted(original._EVIDENCE_KEYS)) == EVIDENCE_KEYS
    evidence_manifest = [dict(key=key, size=len(evidence[key]), sha256=_sha(evidence[key]))
                         for key in EVIDENCE_KEYS]
    exports = [dict(name=entry["key"], path=entry["key"], size=entry["size"],
                    sha256=entry["sha256"]) for entry in manifest]
    exports.extend(dict(name="evidence/" + entry["key"], path="evidence/" + entry["key"],
                        size=entry["size"], sha256=entry["sha256"])
                   for entry in evidence_manifest)
    exports.sort(key=lambda item: item["name"])
    document = dict(
        attempt_id=attempt, app_id=base.APP, sandbox_id=base.SANDBOX,
        phase_returncodes=[0, 0], receipt_size=len(evidence["verification.json"]),
        receipt_sha256=_sha(evidence["verification.json"]),
        evidence_manifest=evidence_manifest, exports=exports)
    outcome = program.canonical(document)
    assert len(outcome) <= base.dto.OUTCOME_LIMIT
    assert all(len(raw) <= base.dto.REQUEST_LIMIT for raw in evidence.values())
    return SimpleNamespace(binding=binding, attempt=attempt, manifest=manifest,
                           evidence=evidence, evidence_manifest=evidence_manifest,
                           document=document, outcome=outcome)


def _move_inputs(fixture, bulk, destinations, anchors):
    moved = []
    for entry in fixture["files"]:
        anchors.check()
        name = entry["name"]
        before = os.stat(name, dir_fd=bulk, follow_symlinks=False)
        _private_file(before)
        _require(_same_file_generation(entry["identity"], _file_identity(before)), "source fixture changed")
        fd = _OWNED.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | os.O_CLOEXEC, dir_fd=bulk)
        try:
            _require(_same_file_generation(entry["identity"], _file_identity(os.fstat(fd))),
                     "opened source generation differs")
            directory, leaf = entry["key"].split("/")
            destination = destinations[directory]
            _require(os.fstat(destination).st_dev == before.st_dev,
                     "same-filesystem move required, no copy fallback")
            # Reserve the destination exclusively. Replace only our own empty
            # placeholder, never a preexisting entry. Parent excludes same-UID
            # concurrent writers throughout this private owned tree.
            placeholder = _OWNED.open(
                leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                | os.O_CLOEXEC, 0o600, dir_fd=destination)
            try:
                reserved = os.fstat(placeholder)
                _private_file(reserved)
                _require(reserved.st_size == 0, "new empty destination required")
                anchors.check()
                _require(_file_identity(os.stat(
                    leaf, dir_fd=destination, follow_symlinks=False))
                    == _file_identity(reserved), "reserved destination changed")
                _require(_same_file_generation(entry["identity"], _file_identity(os.stat(
                    name, dir_fd=bulk, follow_symlinks=False))),
                    "named source changed before rename")
                os.rename(name, leaf, src_dir_fd=bulk, dst_dir_fd=destination)
                _require(os.fstat(placeholder).st_nlink == 0,
                         "rename must replace only owned placeholder")
            finally:
                _close_fd(placeholder)
            after = os.fstat(fd)
            _private_file(after)
            # Rename changes ctime on some systems, never content/mtime/allocation.
            old, new = _file_identity(before), _file_identity(after)
            _require(_same_rename_generation(old, new),
                     "rename changed fixture identity/content facts")
            _require(_same_file_generation(new, _file_identity(os.stat(
                leaf, dir_fd=destination, follow_symlinks=False))), "destination named generation differs")
            _absent(bulk, name)
            os.fsync(destination)
            os.fsync(bulk)
            anchors.check()
            moved.append(dict(key=entry["key"], source_identity=old, export_identity=new))
        finally:
            _close_fd(fd)
        _require(_same_file_generation(new, _file_identity(os.stat(
            leaf, dir_fd=destination, follow_symlinks=False))), "closed destination generation changed")
    return moved


# V311 observations only. These records never supply authority or deadlines.
_JOURNAL_NAME = "v311-progress.jsonl"
_JOURNAL_STEP = 256 * 1024**2
_JOURNAL_KEYS = (None, *KEYS, *("evidence/" + key for key in EVIDENCE_KEYS))
_JOURNAL_OPERATIONS = (
    "install", "c", "receipt", "open", "bulk", "inventory", "identity", "final-sweep",
    "close-validation", "publication", "release", "body",
)
_JOURNAL_STAGES = frozenset(
    ("progress", "eof") + tuple(
        operation + suffix for operation in _JOURNAL_OPERATIONS
        for suffix in ("-enter", "-exit", "-error")))


class _ProgressJournal:
    """Exclusive unbuffered owned journal with reserved write budgets."""

    def __init__(self, diagnostics, anchors):
        self.anchors = anchors
        self.fd = None
        self.record_count = 0
        self.byte_reserved = 0
        self.bulk_bytes = 0
        self.error = None
        self.close_error = None
        self.errors = []
        self.operation_errors = []
        self.close_attempted = False
        anchors.check()
        # _OWNED reserves before os.open and attaches the actual FD before fstat.
        self.fd = _OWNED.open(
            _JOURNAL_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=diagnostics)
        try:
            _private_file(os.fstat(self.fd))
        except BaseException as error:
            self._failed(error)
            raise

    def _failed(self, error):
        self.errors.append(error)
        if self.error is None:
            self.error = error

    def record(self, stage, *, bulk_bytes=0, key=None):
        if self.error is not None:
            raise self.error
        _require(not self.close_attempted, "journal already closed")
        _require(type(stage) is str and stage in _JOURNAL_STAGES, "journal stage")
        _require(key is None or type(key) is str and key in _JOURNAL_KEYS,
                 "journal key")
        _require(type(bulk_bytes) is int and 0 <= bulk_bytes <= TOTAL_BYTES,
                 "journal bulk byte count")
        raw = _canonical(dict(
            seq=self.record_count, stage=stage, wall_ns=time.monotonic_ns(),
            cpu_ns=time.process_time_ns(), bulk_bytes=bulk_bytes, key=key)) + b"\n"
        _require(len(raw) <= 1024, "journal record size")
        _require(self.record_count < 128, "journal record budget")
        _require(self.byte_reserved + len(raw) <= 32768, "journal byte budget")
        # Reserve both budgets BEFORE the first actual write, including failures.
        self.record_count += 1
        self.byte_reserved += len(raw)
        offset = 0
        try:
            while offset < len(raw):
                count = os.write(self.fd, memoryview(raw)[offset:])
                _require(type(count) is int and 0 < count <= len(raw) - offset,
                         "journal write made invalid progress")
                offset += count
        except BaseException as error:
            self._failed(error)
            raise

    def close(self, primary=None):
        # No retry/probe after either successful or uncertain close.
        if self.close_attempted:
            return
        primary = sys.exception() if primary is None else primary
        self.close_attempted = True
        try:
            _OWNED.close(self.fd)
        except BaseException as error:
            self.close_error = error
            self._failed(error)
            if primary is None:
                raise
            primary.add_note("journal close failed: " + type(error).__name__)


def _journal_observe(journal, stage, *, key=None):
    if journal is None or journal.error is not None or journal.close_attempted:
        return
    try:
        journal.record(stage, bulk_bytes=journal.bulk_bytes, key=key)
    except BaseException as error:
        if journal.error is not error:
            journal._failed(error)


def _journal_operation_error(journal, stage, error, *, key=None):
    if journal is not None:
        journal.operation_errors.append((stage, error))
    _journal_observe(journal, stage + "-error", key=key)


def _journal_sync(observer, stage, record_key, operation, /, *args, **kwargs):
    _journal_observe(observer, stage + "-enter", key=record_key)
    try:
        result = operation(*args, **kwargs)
    except BaseException as error:
        _journal_operation_error(observer, stage, error, key=record_key)
        raise
    _journal_observe(observer, stage + "-exit", key=record_key)
    return result


async def _journal_async(observer, stage, record_key, operation, /, *args, **kwargs):
    _journal_observe(observer, stage + "-enter", key=record_key)
    try:
        result = await operation(*args, **kwargs)
    except BaseException as error:
        _journal_operation_error(observer, stage, error, key=record_key)
        raise
    _journal_observe(observer, stage + "-exit", key=record_key)
    return result


def _install(c, o, fixture, bulk, case_fd, anchors, monkeypatch, *, journal=None):
    prepared, _ = base.register(c, o)
    # Capture originals BEFORE inherited installer can substitute either method.
    real_validate = adapter._ParentValidator.validate
    real_allocate = o._allocate_worker
    assert real_validate.__module__ == adapter.__name__
    events, born, channels = base.install_mocked_lifecycle(c, o, monkeypatch)
    monkeypatch.setattr(adapter._ParentValidator, "validate", real_validate)
    data = _documents(c.request, fixture)
    export_parent = anchors.child(case_fd, "export")
    export_fd = anchors.child(export_parent, "run")
    destinations = {name: anchors.child(export_fd, name, create=True)
                    for name in ("checkpoint-1", "checkpoint-2", "evidence")}
    moved = _move_inputs(fixture, bulk, destinations, anchors)
    for key, raw in data.evidence.items():
        _exclusive_bytes(destinations["evidence"], key, raw, base.dto.REQUEST_LIMIT)
    audit = SimpleNamespace(
        prepared=prepared, data=data, events=events, born=born, channels=channels,
        moved=moved, allocations=0, frames=[], validators=0, validated=[],
        bodies=0, originals=[], receipt_calls=0, receipt_accepted=[], opened=[],
        export_attempts=[], inventories=[], identities=[], close_boundaries=[],
        takes=0, published=[], counters={}, c_elapsed_ns=None, c_error=None,
        registry_live_descriptor_peak=0, registry_records_peak=0)

    def sample_registry():
        records = o._registry.records
        audit.registry_records_peak = max(audit.registry_records_peak, len(records))
        audit.registry_live_descriptor_peak = max(
            audit.registry_live_descriptor_peak,
            sum(record.kind == "descriptor" and record.handle is not None
                and not record.closed for record in records))

    def allocate():
        # Never call inherited b"{}" writer. Actual allocator returns empty owned FD.
        result = real_allocate()
        audit.allocations += 1
        fd = o._outcome.record.handle
        before = os.fstat(fd)
        _private_file(before)
        assert before.st_size == 0
        _write_all(fd, data.outcome)
        os.fsync(fd)
        after = os.fstat(fd)
        assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
        assert after.st_size == len(data.outcome)
        sample_registry()
        return result

    monkeypatch.setattr(o, "_allocate_worker", allocate)
    fixture_channel = api._ParentChannel

    class FixtureOutcomeChannel(fixture_channel):
        async def receive(self, *, allowed, end_ns):
            message = await super().receive(allowed=allowed, end_ns=end_ns)
            if message["kind"] != "OUTCOME":
                return message
            # Data substitution only, unchanged original closed DTO validation.
            frame = dict(message, body=dict(size=len(data.outcome), sha256=_sha(data.outcome)))
            result = base.dto.validate_message(
                frame, session=o._session, seq=self._recv_seq, allowed=allowed)
            audit.frames.append(result)
            return result

    monkeypatch.setattr(api, "_ParentChannel", FixtureOutcomeChannel)

    async def validate(validator, lease):
        audit.validators += 1
        start = time.monotonic_ns()
        try:
            result = await _journal_async(journal, "c", None, real_validate, validator, lease)
        except BaseException as error:
            audit.c_error = dict(type=type(error).__name__, message=str(error)[:1024])
            raise
        else:
            audit.validated.append(result)
            return result
        finally:
            audit.c_elapsed_ns = time.monotonic_ns() - start
            sample_registry()

    monkeypatch.setattr(adapter._ParentValidator, "validate", validate)
    real_body = program._validate_outcome_lease

    async def body(*args, **kwargs):
        audit.bodies += 1
        result = await real_body(*args, **kwargs)
        audit.originals.append(result)
        return result

    monkeypatch.setattr(program, "_validate_outcome_lease", body)
    real_receipt = original._validate_receipt

    def receipt(*args, **kwargs):
        audit.receipt_calls += 1
        result = _journal_sync(journal, "receipt", None, real_receipt, *args, **kwargs)
        audit.receipt_accepted.append(result)
        return result

    monkeypatch.setattr(original, "_validate_receipt", receipt)
    real_open_outcome = api.ParentReadLease.open_outcome
    real_open_export = api.ParentReadLease.open_export

    def observed_open(reader, key):
        assert id(reader) not in audit.counters
        record = reader._file.record
        registry_index = next(index for index, item in enumerate(o._registry.records)
                              if item is record)
        audit.opened.append((key, reader))
        audit.counters[id(reader)] = dict(
            key=key, registry_record_index=registry_index, bytes=0, positive_reads=0,
            eof_reads=0, maximum_positive_bytes=0, requested_maximum=0,
            closed_identity_checks=0)
        sample_registry()

    def open_outcome(lease):
        result = _journal_sync(journal, "open", None, real_open_outcome, lease)
        observed_open(result, None)
        return result

    def open_export(lease, key):
        audit.export_attempts.append((key, len(audit.receipt_accepted)))
        result = _journal_sync(journal, "open", key, real_open_export, lease, key)
        if key in KEYS:
            _journal_observe(journal, "bulk-enter", key=key)
        observed_open(result, key)
        return result

    monkeypatch.setattr(api.ParentReadLease, "open_outcome", open_outcome)
    monkeypatch.setattr(api.ParentReadLease, "open_export", open_export)
    real_read = api.RegisteredReader.read

    async def read(reader, maximum):
        try:
            result = await real_read(reader, maximum)
        except BaseException as error:
            _journal_operation_error(journal, "bulk", error,
                                     key=audit.counters[id(reader)]["key"])
            raise
        row = audit.counters[id(reader)]
        row["requested_maximum"] = max(row["requested_maximum"], maximum)
        if result:
            row["bytes"] += len(result)
            row["positive_reads"] += 1
            row["maximum_positive_bytes"] = max(row["maximum_positive_bytes"], len(result))
            if journal is not None and row["key"] in KEYS:
                before = journal.bulk_bytes
                journal.bulk_bytes += len(result)
                if before // _JOURNAL_STEP != journal.bulk_bytes // _JOURNAL_STEP:
                    _journal_observe(journal, "progress", key=row["key"])
        else:
            row["eof_reads"] += 1
            _journal_observe(journal, "eof", key=row["key"])
            if row["key"] in KEYS:
                _journal_observe(journal, "bulk-exit", key=row["key"])
        return result  # Never retain returned bytes in observation state.

    monkeypatch.setattr(api.RegisteredReader, "read", read)
    real_inventory = api.ParentReadLease.export_inventory

    async def inventory(lease):
        result = await _journal_async(journal, "inventory", None, real_inventory, lease)
        audit.inventories.append(result)
        sample_registry()
        return result

    monkeypatch.setattr(api.ParentReadLease, "export_inventory", inventory)
    real_identity = api.RegisteredReader.check_identity

    async def identity(reader):
        closed = reader._file.record.closed
        if closed and not any(was_closed for _, was_closed in audit.identities):
            _journal_observe(journal, "final-sweep-enter")
        try:
            result = await real_identity(reader)
        except BaseException as error:
            _journal_operation_error(journal, "final-sweep" if closed else "identity", error,
                                     key=audit.counters[id(reader)]["key"])
            raise
        audit.identities.append((reader, closed))
        if closed:
            audit.counters[id(reader)]["closed_identity_checks"] += 1
            if sum(was_closed for _, was_closed in audit.identities) == len(audit.opened):
                _journal_observe(journal, "final-sweep-exit")
        return result

    monkeypatch.setattr(api.RegisteredReader, "check_identity", identity)
    real_close = o._close_validation

    def close_validation():
        result = _journal_sync(journal, "close-validation", None, real_close)
        records = tuple(record for record in o._registry.records
                        if o._lease is not None and record.anchor is o._lease
                        and record.handle is not None)
        audit.close_boundaries.append(dict(
            before_seal=o._validated is None, validation_closed=o._validation_closed,
            all_closed=bool(records) and all(record.closed for record in records),
            closed_sweep=len([1 for _, closed in audit.identities if closed])))
        sample_registry()
        return result

    monkeypatch.setattr(o, "_close_validation", close_validation)
    real_take = o.take_validated_original

    def take(**kwargs):
        audit.takes += 1
        result = _journal_sync(journal, "publication", None, real_take, **kwargs)
        audit.published.append(result)
        return result

    monkeypatch.setattr(o, "take_validated_original", take)
    return audit


def _assert_success(c, o, audit, execution):
    assert c.auth.request is c.request
    assert c.auth.request_binding == audit.data.binding == o._reservation.request_binding
    assert c.request.bounds.artifact_bytes == TOTAL_BYTES
    assert c.request.bounds.lifetime_seconds == c.auth.workload.duration_seconds == 600
    assert audit.allocations == len(audit.frames) == audit.validators == audit.bodies == 1
    assert audit.c_error is None and audit.c_elapsed_ns > 0
    assert len(audit.validated) == len(audit.originals) == 1
    assert o._validated is audit.validated[0]
    assert o._validated.original is audit.originals[0]
    assert o._execution is execution and o._validation_closed and not o._validation_close_late
    assert audit.published == [] and not o._published
    assert [event[1] for event in audit.events if event[0] == "birth"] == [
        "worker", "controller", "gate"]
    assert sum(event[0] == "stage" for event in audit.events) == 1
    assert set(audit.born) == {"worker", "controller", "gate"}
    assert all(process.polls > 0 and process.returncode == 0 for process in audit.born.values())
    assert [kind for kind, _ in audit.channels["worker"].sent] == ["OPEN", "CREATE"]
    for role in ("controller", "gate"):
        assert [kind for kind, _ in audit.channels[role].sent].count("ARM") == 1
    assert audit.receipt_calls == len(audit.receipt_accepted) == 1
    assert audit.receipt_accepted[0] == tuple(audit.data.manifest)
    assert [(key, count) for key, count in audit.export_attempts if key in KEYS] == [
        (key, 1) for key in KEYS]
    assert [key for key, _ in audit.opened] == [
        None, *("evidence/" + key for key in EVIDENCE_KEYS), *KEYS]
    readers = tuple(o._lease._readers)
    assert len(readers) == len(audit.opened) == len(audit.counters) == 8
    assert tuple(reader for _, reader in audit.opened) == readers
    assert len({row["registry_record_index"] for row in audit.counters.values()}) == 8
    expected_bytes = {None: len(audit.data.outcome)}
    expected_bytes.update((entry["name"], entry["size"])
                          for entry in audit.data.document["exports"])
    assert len(expected_bytes) == 8
    for key, reader in audit.opened:
        row = audit.counters[id(reader)]
        assert row["key"] == key and row["bytes"] == expected_bytes[key]
        assert row["positive_reads"] > 0 and row["eof_reads"] == 1
        assert 0 < row["maximum_positive_bytes"] <= row["requested_maximum"] <= 65536
        assert row["closed_identity_checks"] == 1
        assert reader._generation == reader._file.record.generation
        assert reader._file.record.closed
        assert reader._file.record.closed_ns < o._booking.close_ns
    assert sum(row["bytes"] for row in audit.counters.values() if row["key"] in KEYS) == TOTAL_BYTES
    assert sum(row["bytes"] for row in audit.counters.values()) == sum(expected_bytes.values())
    assert len(audit.identities) == 24
    assert tuple(reader for reader, closed in audit.identities if closed) == readers
    assert audit.close_boundaries[0] == dict(
        before_seal=True, validation_closed=True, all_closed=True, closed_sweep=8)
    expected_inventory = {(entry["name"], "file", entry["size"])
                          for entry in audit.data.document["exports"]}
    expected_inventory.update((name, "directory", 0)
                              for name in ("checkpoint-1", "checkpoint-2", "evidence"))
    assert len(expected_inventory) == 10 and len(audit.inventories) == 2
    for entries in audit.inventories:
        assert len(entries) == 10
        assert {(entry.key, entry.kind, entry.size) for entry in entries} == expected_inventory
    facts = len(audit.data.outcome), _sha(audit.data.outcome)
    assert o._outcome_facts == facts
    assert (execution.outcome_size, execution.outcome_sha256) == facts
    assert audit.frames[0]["body"] == dict(size=facts[0], sha256=facts[1])
    assert tuple(child.role for child in execution.children) == ("worker", "controller", "gate")
    assert all(child.actual_reap_observed and child.returncode == 0 for child in execution.children)
    assert all(child.code == 0 and child.record.closed and child.reaped_ns is not None
               for child in o._children.values())
    assert all(record.closed or record.handle is None for record in o._runtime_records)


def _publish(c, o, audit, execution):
    result = adapter.validate_joined_outcome(
        c.request, owner=o, prepared=audit.prepared, execution=execution, export_root=c.export)
    actual = result.original_outcome
    assert actual is audit.originals[0] and result.local_containment == "JOINED"
    assert len(audit.published) == audit.takes == 1 and audit.published[0] is actual
    assert type(actual) is original.EngineeringRunOutcome
    assert (actual.attempt_id, actual.app_id, actual.sandbox_id, actual.phase_returncodes) == (
        audit.data.attempt, base.APP, base.SANDBOX, (0, 0))
    assert (actual.receipt_size, actual.receipt_sha256) == (
        audit.data.document["receipt_size"], audit.data.document["receipt_sha256"])
    assert actual.evidence_manifest == tuple(audit.data.evidence_manifest)
    assert [(entry.name, entry.path, entry.size, entry.sha256) for entry in actual.exports] == [
        (entry["name"], c.export / entry["name"], entry["size"], entry["sha256"])
        for entry in audit.data.document["exports"]]
    with pytest.raises(ValueError, match="one-use sealed original"):
        o.take_validated_original(
            request=c.request, prepared=audit.prepared, execution=execution, export_root=c.export)
    assert audit.takes == 2 and len(audit.published) == 1


def _metrics(audit, owner, start, error, released, preparation):
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Darwin ru_maxrss is bytes, Linux reports KiB. Never silently relabel.
    if sys.platform == "darwin":
        rss_unit, rss_bytes = "bytes", rss
    elif sys.platform.startswith("linux"):
        rss_unit, rss_bytes = "KiB", rss * 1024
    else:
        rss_unit, rss_bytes = "platform-native-unconverted", None
    return dict(
        v=1, status="BODY_COMPLETED" if error is None else "FAIL",
        error=None if error is None else dict(type=type(error).__name__, message=str(error)[:2048]),
        test_elapsed_ns=time.monotonic_ns() - start,
        timing_scope="test body including metadata setup, excludes metrics write/fixture teardown",
        process_elapsed_ns=None, process_timing_owner="parent external fresh-process supervisor",
        bulk_expected_bytes=TOTAL_BYTES, file_expected_bytes=FILE_BYTES, reader_expected_count=8,
        preparation=preparation, cache=(
            "reused-generated-after-previous-full-read-not-evicted-no-cold-cache-claim"
            if _LINUX_V364_CONTEXT is None
            else "fresh-generated-not-evicted-no-cold-cache-claim"),
        peak_rss_raw=rss, peak_rss_unit=rss_unit, peak_rss_bytes=rss_bytes,
        c_elapsed_ns=None if audit is None else audit.c_elapsed_ns,
        c_calls=0 if audit is None else audit.validators,
        c_error=None if audit is None else audit.c_error,
        receipt_calls=0 if audit is None else audit.receipt_calls,
        reader_counters=[] if audit is None else list(audit.counters.values()),
        moved=[] if audit is None else audit.moved,
        registry_records_observed_peak=0 if audit is None else audit.registry_records_peak,
        registry_live_descriptors_observed_peak=(
            0 if audit is None else audit.registry_live_descriptor_peak),
        fd_scope="sampled actual owner registry only, not OS-wide FD peak or ancestry anchors",
        registry_records_after_release=None if owner is None else len(owner._registry.records),
        registry_live_after_release=None if owner is None else sum(
            record.handle is not None and not record.closed for record in owner._registry.records),
        release_completed=released, native_science="0/7", lifecycle="synthetic observations")


def test_actual_ac_four_two_gib_files_full_validation(monkeypatch):
    start = time.monotonic_ns()
    context = _linux_v364_context()
    anchors = _Anchors()
    diagnostics = None
    journal = None
    audit = o = fixture = None
    primary = None
    release_attempted = released = False
    try:
        home_text = os.environ["HOME"]
        home = Path(home_text)
        _require(home_text == str(home) and home.name == "home" and home.is_absolute(),
                 "actual H191 HOME must be canonical ROOT/home")
        root = home.parent
        root_fd = anchors.root(str(root))
        anchors.child(root_fd, "home")  # Verify actual HOME ancestry, no content reads.
        # H191 may already own diagnostics. Never reuse our exclusive metrics leaf.
        try:
            diagnostics = anchors.child(root_fd, "diagnostics")
        except FileNotFoundError:
            diagnostics = anchors.child(root_fd, "diagnostics", create=True)
        _absent(diagnostics, "v290-volume.json")
        journal = _ProgressJournal(diagnostics, anchors)
        bulk = anchors.child(root_fd, "bulk-input")
        fixture = _read_manifest(root_fd, bulk, anchors)
        assert base.dto.FILE_LIMIT == FILE_BYTES and base.dto.TOTAL_LIMIT == TOTAL_BYTES
        case_fd = anchors.child(root_fd, "volume-case", create=True)
        c = _case(root, monkeypatch)
        export_parent = anchors.child(case_fd, "export")
        _absent(export_parent, "run")
        assert type(c.auth) is base.authority.EngineeringAuthorization
        assert not c.auth.bound and c.auth.request is c.request
        o = api.admit_isolated_owner(base.preflight(c))
        assert type(o._reservation) is base.authority.AttemptReservation
        assert base.authority._custody_for_reservation(o._reservation) is o._reservation_custody
        audit = _journal_sync(
            journal, "install", None, _install, c, o, fixture, bulk, case_fd, anchors,
            monkeypatch, journal=journal)
        execution = asyncio.run(o.run_once())
        _assert_success(c, o, audit, execution)
        _publish(c, o, audit, execution)
        release_attempted = True
        _journal_sync(journal, "release", None, adapter._release, o)
        assert o._released and not o._latch_held and base.common._ACTIVE_HOST is None
        o._reservation_custody.require_released()
        assert all(record.closed or record.handle is None for record in o._registry.records)
        released = True
        anchors.check()
        assert time.monotonic_ns() < (
            start + 29_000_000_000 if context is None else context["deadline_ns"])
    except BaseException as error:
        primary = error
        _journal_operation_error(journal, "body", error)
        raise
    finally:
        # Diagnostic failure must never bypass actual release or ancestry close.
        cleanup_errors = []
        try:
            if o is not None and not release_attempted and not o._running:
                release_attempted = True
                try:
                    _journal_sync(journal, "release", None, adapter._release, o, primary)
                    released = o._released
                except BaseException as cleanup:
                    cleanup_errors.append(cleanup)
            try:
                if diagnostics is not None:
                    anchors.check()
                    metrics = _metrics(
                        audit, o, start,
                        primary or (None if journal is None else journal.error),
                        released, None if fixture is None else fixture["preparation"])
                    _exclusive_bytes(diagnostics, "v290-volume.json", _canonical(metrics), 65_536)
            except BaseException as diagnostic_error:
                cleanup_errors.append(diagnostic_error)
        finally:
            try:
                if journal is not None:
                    try:
                        journal.close(primary or (cleanup_errors[0] if cleanup_errors else None))
                    except BaseException as close_error:
                        cleanup_errors.append(close_error)
            finally:
                try:
                    anchors.close()
                except BaseException as close_error:
                    cleanup_errors.append(close_error)
        if journal is not None and journal.error is not None:
            if all(error is not journal.error for error in cleanup_errors):
                cleanup_errors.append(journal.error)
        if primary is not None:
            for secondary in cleanup_errors:
                if secondary is not primary:
                    primary.add_note("diagnostic/cleanup failed: "
                                     + type(secondary).__name__ + ": " + str(secondary)[:512])
        elif cleanup_errors:
            raise cleanup_errors[0]
    if context is not None:
        _require(time.monotonic_ns() < context["deadline_ns"],
                 "shared internal29s exceeded after diagnostic/ancestry close")
        context["completed"] = True
