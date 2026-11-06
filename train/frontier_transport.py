"""Create-only, explicitly UNVERIFIED transport of bounded frontier declarations.

Archive SHA and producer pins establish byte agreement, not independent custody,
freshness, genuine measurement or training permission. No opaque payload is parsed.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from bench import prepare
from train import frontier_bindings as core

__all__ = [
    "TransportError", "TransportPublicationIndeterminateError",
    "TransportedBindings", "write_unverified_bindings", "load_unverified_bindings",
]

_KIND = "cotrain-unverified-frontier-transport"
_MAX_ARCHIVE_BYTES = 32 << 20
_MAX_DEPTH = 12
_MAX_OBJECT_MEMBERS = 40
_MAX_VALUES = 500000
_MAX_NUMBER_CHARS = 32
_MAX_ENCODED_BLOB_CHARS = 1398104
_MAX_STRING_TOKEN_CHARS = 1398104
_MIN_INTEGER = -(1 << 63)
_MAX_INTEGER = (1 << 63) - 1
_PATH_TYPE = type(Path())
_HEX = frozenset("0123456789abcdef")
_B64 = {c: i for i, c in enumerate(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")}
_TOP = ("kind", "version", "plan", "retention_pins", "samples", "blobs")
_BLOB = ("evidence_id", "payload_base64")
# Fixed v1 allowlists, not dynamically accepted dataclass extensions.
_FIELDS = {
    core.MeasurementPlan: (
        "plan_id", "execution_id", "policy_revision", "checkpoint_sha256",
        "adapter_sha256", "runtime_id", "provider_id", "route_id",
        "generation_sha256", "prompt_sha256", "template_sha256", "tool_sha256",
        "instrument_sha256", "source_sha256", "draw_sha256", "supplement_sha256",
        "tasks", "eligible_ids", "exclusions", "g", "dead_ceiling", "scorer",
        "resource_limits_id", "grant_reference",
    ),
    core.TaskBinding: ("task_id", "task_sha256", "database_sha256"),
    core.PreparationExclusion: ("task_id", "reason"),
    core.ScorerBinding: (
        "extraction_source_sha256", "scorer_source_sha256", "comparison",
        "timeout_s", "max_rows",
    ),
    core.ExpectedEvidence: (
        "evidence_id", "purpose", "plan_id", "execution_id", "task_id",
        "slot_index", "attempt_id", "generation_evidence_id",
        "prediction_sha256", "byte_count", "sha256",
    ),
    core.SampleRecord: (
        "task_id", "slot_index", "attempt_id", "status", "score",
        "generation_evidence_id", "scoring_evidence_id", "prediction_sha256",
    ),
}


class TransportError(ValueError):
    """Fixed public refusal, never supplied filesystem/content detail."""

    def __init__(self):
        super().__init__("invalid unverified frontier transport")


class TransportPublicationIndeterminateError(TransportError):
    """Final artifact must not be deleted/retried on this outcome."""

    def __init__(self):
        ValueError.__init__(self, "unverified frontier transport publication indeterminate")


def _fail():
    raise TransportError() from None


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class TransportedBindings:
    plan: core.MeasurementPlan
    retention_pins: tuple[core.ExpectedEvidence, ...]
    batch: core.EvidenceBatch
    report: core.BindingReport


@dataclass(frozen=True, slots=True, repr=False)
class _Base64Value:
    payload: bytes


def _flat(value, cls):
    return {name: object.__getattribute__(value, name) for name in _FIELDS[cls]}


def _plan_document(plan):
    doc = _flat(plan, core.MeasurementPlan)
    doc["tasks"] = [_flat(t, core.TaskBinding) for t in plan.tasks]
    doc["eligible_ids"] = list(plan.eligible_ids)
    doc["exclusions"] = [_flat(e, core.PreparationExclusion) for e in plan.exclusions]
    doc["scorer"] = _flat(plan.scorer, core.ScorerBinding)
    return doc


def _same_value(left, right):
    # Internal exact primitives only. Python's numerical equality is insufficient.
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _same_value(value, right[key]) for key, value in left.items())
    if type(left) is list:
        return len(left) == len(right) and all(
            _same_value(a, b) for a, b in zip(left, right, strict=True))
    if type(left) is float:
        return left.hex() == right.hex()
    return left == right


def _detached(plan, pins, batch, limits):
    try:
        plan, pins, batch, limits = core._snapshot(plan, pins, batch, limits)
        core.validate_frontier_bindings(plan, pins, batch, limits=limits)
        if not _same_value(_plan_document(plan), _plan_document(batch.plan)):
            _fail()
        # A second detached boundary, then a fresh report, never a cached report
        # or an acceptance decision based on truncated diagnostic examples.
        plan, pins, batch, limits = core._snapshot(plan, pins, batch, limits)
        report = core.validate_frontier_bindings(plan, pins, batch, limits=limits)
    except core.BindingError:
        _fail()
    return plan, pins, batch, limits, report


def _document(plan, pins, batch):
    return {
        "kind": _KIND, "version": 1, "plan": _plan_document(plan),
        "retention_pins": [_flat(p, core.ExpectedEvidence) for p in pins],
        "samples": [_flat(s, core.SampleRecord) for s in batch.samples],
        "blobs": [{"evidence_id": b.evidence_id, "payload_base64": _Base64Value(b.payload)}
                  for b in batch.blobs],
    }


def _number_text(value):
    if type(value) is int:
        if not _MIN_INTEGER <= value <= _MAX_INTEGER:
            _fail()
        text = str(value)
    elif type(value) is float and math.isfinite(value):
        text = repr(value)
    else:
        _fail()
    if len(text) > _MAX_NUMBER_CHARS:
        _fail()
    return text


def _string_size(value):
    """Exact canonical escaped UTF8 bytes and lexical chars, including quotes."""
    if type(value) is not str:
        _fail()
    size = chars = 2
    for character in value:
        point = ord(character)
        if character in ('"', "\\") or character in "\b\f\n\r\t":
            size += 2
            chars += 2
        elif point < 0x20:
            size += 6
            chars += 6
        elif 0xD800 <= point <= 0xDFFF:
            _fail()
        else:
            size += 1 if point < 0x80 else 2 if point < 0x800 else 3 if point < 0x10000 else 4
            chars += 1
        if chars > _MAX_STRING_TOKEN_CHARS or size > _MAX_ARCHIVE_BYTES:
            _fail()
    if chars > _MAX_STRING_TOKEN_CHARS:
        _fail()
    return size


def _measure_document(doc):
    """No JSON/base64 encoder is invoked until all output ceilings pass."""
    total, values = 1, 0  # exactly one trailing newline

    def add(amount):
        nonlocal total
        total += amount
        if total > _MAX_ARCHIVE_BYTES:
            _fail()

    def visit(value, depth):
        nonlocal values
        values += 1
        if values > _MAX_VALUES:
            _fail()
        kind = type(value)
        if kind in (dict, list):
            depth += 1
            if depth > _MAX_DEPTH:
                _fail()
            add(2)
            if kind is dict:
                if len(value) > _MAX_OBJECT_MEMBERS:
                    _fail()
                for index, (key, item) in enumerate(value.items()):
                    if index:
                        add(1)
                    visit(key, depth)  # key strings count as lexical values
                    add(1)
                    visit(item, depth)
            else:
                for index, item in enumerate(value):
                    if index:
                        add(1)
                    visit(item, depth)
        elif kind is _Base64Value:
            length = 4 * ((len(value.payload) + 2) // 3)
            if (length > _MAX_ENCODED_BLOB_CHARS
                    or length + 2 > _MAX_STRING_TOKEN_CHARS):
                _fail()
            add(length + 2)
        elif kind is str:
            add(_string_size(value))
        elif value is None:
            add(4)
        elif kind is bool:
            add(4 if value else 5)
        else:
            add(len(_number_text(value)))

    visit(doc, 0)
    return total


def _materialize(doc):
    for blob in doc["blobs"]:
        pending = blob["payload_base64"]
        blob["payload_base64"] = base64.b64encode(pending.payload).decode("ascii")
    return doc


def _path_parts(value):
    if type(value) is str:
        path = value
    elif type(value) is _PATH_TYPE:
        path = str(value)
    else:
        _fail()
    if not path.startswith("/") or "\x00" in path:
        _fail()
    raw = path.split("/")
    if ".." in raw:
        _fail()
    parts = [part for part in raw if part and part != "."]
    if not parts:
        _fail()
    return parts


def _open_parent(parts, descriptors):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open("/", flags)
    descriptors.append(current)
    for part in parts[:-1]:
        current = os.open(part, flags, dir_fd=current)
        descriptors.append(current)
    return current


def _close_all(descriptors, active):
    first = None
    for fd in reversed(descriptors):
        try:
            os.close(fd)
        except BaseException as error:
            if (first is None or (isinstance(first, Exception)
                                  and not isinstance(error, Exception))):
                first = error
    if first is not None and not active:
        if isinstance(first, OSError):
            _fail()
        raise first


def _precheck_output(path):
    parts, descriptors = _path_parts(path), []
    failed = False
    try:
        parent = _open_parent(parts, descriptors)
        try:
            os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _fail()  # ANY existing entry stays untouched, including symlinks
    except (OSError, UnicodeError):
        failed = True
        _fail()
    except BaseException:
        failed = True
        raise
    finally:
        _close_all(descriptors, failed)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink, info.st_uid, info.st_gid)


def _read_regular(path):
    parts, descriptors = _path_parts(path), []
    failed = False
    try:
        parent = _open_parent(parts, descriptors)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_ARCHIVE_BYTES:
            _fail()
        chunks, total = [], 0
        while total <= _MAX_ARCHIVE_BYTES:
            block = os.read(fd, min(65536, _MAX_ARCHIVE_BYTES + 1 - total))
            if not block:
                break
            total += len(block)
            if total > _MAX_ARCHIVE_BYTES:
                _fail()
            chunks.append(block)
        after = os.fstat(fd)
        entry = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if _identity(before) != _identity(after) or _identity(after) != _identity(entry):
            _fail()
        return b"".join(chunks)
    except (OSError, UnicodeError):
        failed = True
        _fail()
    except BaseException:
        failed = True
        raise
    finally:
        # Track THIS operation, not sys.exc_info inherited from a caller's
        # unrelated except block. Preserve its own active BaseException only.
        _close_all(descriptors, failed)


def _archive_pin(value):
    if (type(value) is not str or len(value) != 64
            or any(c not in _HEX for c in value)):
        _fail()


def _check_archive_sha(raw, expected):
    if hashlib.sha256(raw).hexdigest() != expected:
        _fail()


def _decode_utf8(raw):
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail()


def _lexical(text):
    """Quote-aware bounded preflight, not a repairing JSON parser.

    Containers and every primitive/key string count as values. Depth counts
    open containers. Object members count unquoted colons in their own frame.
    JSON grammar/escape correctness is additionally enforced by json.loads.
    """
    index, values, stack = 0, 0, []
    length = len(text)
    whitespace = " \t\r\n"
    while index < length:
        character = text[index]
        if character in whitespace or character == ",":
            index += 1
            continue
        if character in "{[":
            stack.append([character, 0])
            if len(stack) > _MAX_DEPTH:
                _fail()
            values += 1
            index += 1
        elif character in "}]":
            if not stack or stack[-1][0] != ("{" if character == "}" else "["):
                _fail()
            stack.pop()
            index += 1
        elif character == ":":
            if not stack or stack[-1][0] != "{":
                _fail()
            stack[-1][1] += 1
            if stack[-1][1] > _MAX_OBJECT_MEMBERS:
                _fail()
            index += 1
        elif character == '"':
            start = index
            index += 1
            while index < length:
                current = text[index]
                if ord(current) < 0x20:
                    _fail()
                if current == '"':
                    index += 1
                    break
                index += 2 if current == "\\" else 1
                if index - start + 1 > _MAX_STRING_TOKEN_CHARS:
                    _fail()
            else:
                _fail()
            if index > length or index - start > _MAX_STRING_TOKEN_CHARS:
                _fail()
            values += 1
        elif character == "-" or "0" <= character <= "9":
            start = index
            while index < length and text[index] not in whitespace + "[]{}:,\"":
                index += 1
                if index - start > _MAX_NUMBER_CHARS:
                    _fail()
            values += 1
        else:
            for literal in ("true", "false", "null"):
                if text.startswith(literal, index):
                    index += len(literal)
                    values += 1
                    break
            else:
                _fail()
        if values > _MAX_VALUES:
            _fail()
    if stack:
        _fail()


def _parse_int(text):
    if len(text) > _MAX_NUMBER_CHARS:
        _fail()
    try:
        value = int(text)
    except ValueError:
        _fail()
    if not _MIN_INTEGER <= value <= _MAX_INTEGER:
        _fail()
    return value


def _parse_float(text):
    if len(text) > _MAX_NUMBER_CHARS:
        _fail()
    try:
        value = float(text)
    except (ValueError, OverflowError):
        _fail()
    if not math.isfinite(value):
        _fail()
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _constant(text):
    _fail()


def _parse(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_int=_parse_int,
                          parse_float=_parse_float, parse_constant=_constant)
    except (ValueError, RecursionError):
        _fail()


def _keys(value, expected):
    if type(value) is not dict or len(value) != len(expected) or set(value) != set(expected):
        _fail()


def _array(value, maximum):
    if type(value) is not list or len(value) > maximum:
        _fail()
    return value


def _construct(value, cls):
    names = _FIELDS[cls]
    _keys(value, names)
    return cls(*(value[name] for name in names))


def _from_plan(value, limits):
    _keys(value, _FIELDS[core.MeasurementPlan])
    tasks = _array(value["tasks"], limits.max_planned_tasks)
    eligible = _array(value["eligible_ids"], limits.max_planned_tasks)
    exclusions = _array(value["exclusions"], limits.max_planned_tasks)
    _keys(value["scorer"], _FIELDS[core.ScorerBinding])
    data = dict(value)
    data["tasks"] = tuple(_construct(t, core.TaskBinding) for t in tasks)
    data["eligible_ids"] = tuple(eligible)
    data["exclusions"] = tuple(_construct(e, core.PreparationExclusion) for e in exclusions)
    data["scorer"] = _construct(value["scorer"], core.ScorerBinding)
    return core.MeasurementPlan(**data)


def _decoded_size(text):
    if type(text) is not str or len(text) > _MAX_ENCODED_BLOB_CHARS or len(text) % 4:
        _fail()
    if not text:
        return 0
    padding = 2 if text.endswith("==") else 1 if text.endswith("=") else 0
    for index in range(len(text) - padding):
        if text[index] not in _B64:
            _fail()
    if padding == 2 and (_B64[text[-3]] & 15):
        _fail()
    if padding == 1 and (_B64[text[-2]] & 3):
        _fail()
    return len(text) // 4 * 3 - padding


def _charge_payload(budget, length, limits):
    if length > limits.max_item_bytes:
        _fail()
    budget.charge(length)


def _decode_document(doc, limits):
    _keys(doc, _TOP)
    if type(doc["kind"]) is not str or doc["kind"] != _KIND:
        _fail()
    if type(doc["version"]) is not int or doc["version"] != 1:
        _fail()
    plan = _from_plan(doc["plan"], limits)
    raw_pins = _array(doc["retention_pins"], limits.max_expected_evidence)
    raw_samples = _array(doc["samples"], limits.max_scheduled_slots)
    raw_blobs = _array(doc["blobs"], limits.max_raw_evidence)
    pins = tuple(_construct(p, core.ExpectedEvidence) for p in raw_pins)
    samples = tuple(_construct(s, core.SampleRecord) for s in raw_samples)
    for blob in raw_blobs:
        _keys(blob, _BLOB)
    # Admit the ENTIRE graph, including both plan projections and every raw ID,
    # before ANY base64 decoder/ASCII conversion/decoded payload allocation.
    try:
        budget = core._Budget(limits)
        plan = core._snapshot_plan(plan, budget)
        projection = core._snapshot_plan(plan, budget)
        pins = tuple(core._snapshot_expected(p, budget) for p in pins)
        samples = tuple(core._snapshot_sample(s, budget) for s in samples)
        identifiers = []
        for blob in raw_blobs:
            identifiers.append(budget.identifier(blob["evidence_id"]))
            length = _decoded_size(blob["payload_base64"])
            _charge_payload(budget, length, limits)
        empty = core.EvidenceBatch(projection, (), samples)
        core._validate_values(plan, pins, empty)
        core._check_unique(pins, empty)
        core._unique(tuple(identifiers))
        core._check_membership(plan)
    except core.BindingError:
        _fail()
    try:
        blobs = tuple(core.EvidenceBlob(
            evidence_id, base64.b64decode(blob["payload_base64"], validate=True))
            for evidence_id, blob in zip(identifiers, raw_blobs, strict=True))
    except (binascii.Error, ValueError):
        _fail()
    return plan, pins, core.EvidenceBatch(plan, blobs, samples)


def write_unverified_bindings(
    plan: core.MeasurementPlan,
    retention_pins: tuple[core.ExpectedEvidence, ...],
    batch: core.EvidenceBatch,
    output_path: Path | str,
    *,
    limits: core.BindingLimits,
) -> str:
    """Publish canonical v1 bytes once, never overwrite or grant authority."""
    plan, pins, batch, limits, _ = _detached(plan, retention_pins, batch, limits)
    document = _document(plan, pins, batch)
    _measure_document(document)
    _materialize(document)
    _precheck_output(output_path)
    # Existing pathname publisher assumes trusted, non-racing host filesystem.
    # Nofollow prechecks are NOT universal containment or snapshot guarantees.
    try:
        return prepare._publish(document, output_path)
    except prepare.PublicationIndeterminateError:
        raise TransportPublicationIndeterminateError() from None
    except (OSError, prepare.PreparationError, UnicodeError):
        _fail()


def load_unverified_bindings(
    path: Path | str,
    *,
    expected_archive_sha256: str,
    limits: core.BindingLimits,
) -> TransportedBindings:
    """Reload detached declarations with a fresh report, always unverified."""
    _archive_pin(expected_archive_sha256)
    try:
        limits = core._snapshot_limits(limits)
    except core.BindingError:
        _fail()
    raw = _read_regular(path)
    _check_archive_sha(raw, expected_archive_sha256)
    text = _decode_utf8(raw)
    _lexical(text)
    document = _parse(text)
    plan, pins, batch = _decode_document(document, limits)
    plan, pins, batch, limits, report = _detached(plan, pins, batch, limits)
    # Re-encode only after all quotas and fresh core checks, never repair input.
    _measure_document(document)
    if prepare._canonical_bytes(document) != raw:
        _fail()
    return TransportedBindings(
        plan, pins, core.EvidenceBatch(plan, batch.blobs, batch.samples), report)
