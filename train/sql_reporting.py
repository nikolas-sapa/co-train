"""Shared contract for opt-in defect-reporting evidence.

A ``ReportingConfig`` is the exact frozen allowlist a caller opted into; a
``ReportingSnapshot`` is validated canonical ``QaChannel.export()`` bytes.
Validation here mirrors the collector's reachable states exactly: every shape
the collector can produce is accepted, nothing else is. Reports remain
unverified allegations; nothing in this module executes actions, reads
artifact-supplied paths, or authenticates provenance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from ptc import sql_qa

__all__ = [
    "ReportingConfig",
    "ReportingSnapshot",
    "validate_config",
    "config_to_dict",
    "config_from_dict",
    "snapshot_to_dict",
    "snapshot_from_dict",
    "validate_snapshot",
    "make_channel",
    "snapshot_channel",
    "require_expected",
    "snapshots_equal",
    "instrument_sources",
]

REPORTING_VERSION = 1
REPORTING_MODE = "defect_reports"

_EXTRA_SOURCES = ("ptc/sql_qa.py", "train/sql_reporting.py")
_EVENT_BASE = frozenset({"arm", "seq", "type", "provenance"})
_EVENT_FIELDS = {
    "report": frozenset({"kind", "detail"}),
    "report_rejected": frozenset({"reason"}),
    "overflow": frozenset({"reason"}),
    "shortcut": frozenset({"shortcut_id"}),
}
_REJECT_REASONS = frozenset({"kind", "schema", "size", "raw"})
_OVERFLOW_REASON = "report_cap"
_PROVENANCES = frozenset({sql_qa.PROVENANCE_CALLBACK, sql_qa.PROVENANCE_OUTPUT})
_SNAPSHOT_KEYS = frozenset({"arms", "total_events", "version"})
_ARM_KEYS = frozenset({"dropped", "dropped_saturated", "events", "reports"})


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError("nonfinite JSON number")


# ---------------------------------------------------------------------------
# ReportingConfig
# ---------------------------------------------------------------------------


def _check_config_fields(config):
    if type(config.version) is not int:
        raise TypeError("reporting version must be an integer, not a boolean")
    if config.version != REPORTING_VERSION:
        raise ValueError("unsupported reporting version")
    if type(config.mode) is not str:
        raise TypeError("reporting mode must be a string")
    if config.mode != REPORTING_MODE:
        raise ValueError("unsupported reporting mode")
    ids = config.shortcut_ids
    if type(ids) is not tuple:
        raise TypeError("reporting shortcut_ids must be a tuple")
    if len(ids) > sql_qa.MAX_SHORTCUT_IDS:
        raise ValueError("too many reporting shortcut ids")
    for sid in ids:
        if not sql_qa._valid_shortcut_id(sid):
            raise ValueError("invalid reporting shortcut id")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate reporting shortcut ids")
    if ids != tuple(sorted(ids)):
        raise ValueError("reporting shortcut ids must be sorted")


@dataclass(frozen=True)
class ReportingConfig:
    version: int = REPORTING_VERSION
    mode: str = REPORTING_MODE
    shortcut_ids: tuple[str, ...] = ()

    def __post_init__(self):
        _check_config_fields(self)


def validate_config(config):
    if type(config) is not ReportingConfig:
        raise TypeError("expected an exact ReportingConfig")
    _check_config_fields(config)


def config_to_dict(config):
    validate_config(config)
    return {
        "version": config.version,
        "mode": config.mode,
        "shortcut_ids": list(config.shortcut_ids),
    }


def config_from_dict(value):
    if type(value) is not dict:
        raise TypeError("reporting configuration must be a JSON object")
    if set(value) != {"version", "mode", "shortcut_ids"}:
        raise ValueError("reporting configuration has missing or unknown keys")
    if type(value["shortcut_ids"]) is not list:
        raise TypeError("reporting shortcut_ids must be a JSON array")
    return ReportingConfig(
        version=value["version"],
        mode=value["mode"],
        shortcut_ids=tuple(value["shortcut_ids"]),
    )


# ---------------------------------------------------------------------------
# ReportingSnapshot: strict canonical collector export v1
# ---------------------------------------------------------------------------


def _check_report_fields(kind, detail):
    if type(kind) is not str or kind not in sql_qa.KINDS:
        raise ValueError("invalid report kind")
    if type(detail) is not str or not detail:
        raise ValueError("report detail must be a nonempty string")
    if len(detail) > sql_qa.MAX_REPORT_BYTES:
        raise ValueError("report detail exceeds the canonical payload bound")
    try:
        canonical = sql_qa._canonical_bytes(kind, detail)
    except UnicodeEncodeError:
        raise ValueError("report detail is not encodable as UTF-8") from None
    if len(canonical) > sql_qa.MAX_REPORT_BYTES:
        raise ValueError("canonical report payload exceeds the byte bound")


def _check_event(arm, event):
    if type(event) is not dict:
        raise TypeError("events must be JSON objects")
    etype = event.get("type")
    if etype not in _EVENT_FIELDS:
        raise ValueError("unknown event type")
    if set(event) != _EVENT_BASE | _EVENT_FIELDS[etype]:
        raise ValueError("event has missing or unknown keys")
    if event["arm"] != arm:
        raise ValueError("event arm disagrees with its arm section")
    if type(event["seq"]) is not int:
        raise TypeError("event sequence must be an integer, not a boolean")
    if event["seq"] < 1:
        raise ValueError("event sequence must be positive")
    provenance = event["provenance"]
    if etype == "shortcut":
        if not sql_qa._valid_provenance(provenance):
            raise ValueError("invalid shortcut provenance")
    elif provenance not in _PROVENANCES:
        raise ValueError("invalid event provenance")
    if etype == "report":
        _check_report_fields(event["kind"], event["detail"])
    elif etype == "report_rejected":
        if event["reason"] not in _REJECT_REASONS:
            raise ValueError("invalid rejection reason")
    elif etype == "overflow":
        if event["reason"] != _OVERFLOW_REASON:
            raise ValueError("invalid overflow reason")
    elif not sql_qa._valid_shortcut_id(event["shortcut_id"]):
        raise ValueError("invalid shortcut id")


def _check_arm(arm, doc):
    if type(doc) is not dict:
        raise TypeError("arm snapshot must be a JSON object")
    if set(doc) != _ARM_KEYS:
        raise ValueError("arm snapshot has missing or unknown keys")
    dropped = doc["dropped"]
    if type(dropped) is not int:
        raise TypeError("dropped must be an integer, not a boolean")
    if not 0 <= dropped <= sql_qa.DROPPED_MAX:
        raise ValueError("dropped counter out of bounds")
    saturated = doc["dropped_saturated"]
    if type(saturated) is not bool:
        raise TypeError("dropped_saturated must be a boolean")
    if saturated != (dropped == sql_qa.DROPPED_MAX):
        raise ValueError("dropped_saturated disagrees with the dropped counter")
    events = doc["events"]
    if type(events) is not list:
        raise TypeError("events must be a JSON array")
    if len(events) > sql_qa.MAX_EVENTS_PER_ARM:
        raise ValueError("too many events for one arm")
    reports = doc["reports"]
    if type(reports) is not int:
        raise TypeError("reports must be an integer, not a boolean")
    if not 0 <= reports <= sql_qa.MAX_REPORTS_PER_ARM:
        raise ValueError("reports counter out of bounds")
    last_seq = 0
    n_reports = 0
    for event in events:
        _check_event(arm, event)
        if event["seq"] <= last_seq:
            raise ValueError("event sequences are not in per-arm order")
        last_seq = event["seq"]
        if event["type"] == "report":
            n_reports += 1
        elif event["type"] == "overflow" and n_reports < sql_qa.MAX_REPORTS_PER_ARM:
            raise ValueError("overflow precedes the report cap")
    if n_reports != reports:
        raise ValueError("reports counter disagrees with stored report events")
    return events


def _check_snapshot_doc(doc):
    if type(doc) is not dict:
        raise TypeError("reporting snapshot must be a JSON object")
    if set(doc) != _SNAPSHOT_KEYS:
        raise ValueError("reporting snapshot has missing or unknown keys")
    if type(doc["version"]) is not int or doc["version"] != 1:
        raise ValueError("unsupported reporting snapshot version")
    total = doc["total_events"]
    if type(total) is not int:
        raise TypeError("total_events must be an integer, not a boolean")
    if not 0 <= total <= sql_qa.MAX_EVENTS_TOTAL:
        raise ValueError("total_events out of bounds")
    arms = doc["arms"]
    if type(arms) is not dict or set(arms) != set(sql_qa.ARMS):
        raise ValueError("reporting snapshot must carry exactly the two arms")
    per_arm = {}
    seqs = []
    for arm in sql_qa.ARMS:
        events = _check_arm(arm, arms[arm])
        per_arm[arm] = events
        seqs.extend(event["seq"] for event in events)
    if len(seqs) != total:
        raise ValueError("total_events disagrees with stored events")
    if sorted(seqs) != list(range(1, total + 1)):
        raise ValueError("event sequences are not contiguous and unique")
    for arm in sql_qa.ARMS:
        if arms[arm]["dropped"] and not (
            len(per_arm[arm]) == sql_qa.MAX_EVENTS_PER_ARM
            or total == sql_qa.MAX_EVENTS_TOTAL
        ):
            raise ValueError("dropped records require a full event log")


def _decode_snapshot(data):
    if type(data) is not bytes:
        raise TypeError("reporting snapshot must be bytes")
    if len(data) > sql_qa.MAX_EXPORT_BYTES:
        raise ValueError("reporting snapshot exceeds the export bound")
    try:
        doc = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise ValueError("reporting snapshot is not valid UTF-8 JSON") from exc
    _check_snapshot_doc(doc)
    try:
        canonical = _canonical(doc)
    except (ValueError, RecursionError, UnicodeEncodeError) as exc:
        raise ValueError("reporting snapshot is not canonically encodable") from exc
    if canonical != data:
        raise ValueError("reporting snapshot is not canonical export bytes")
    return doc


@dataclass(frozen=True)
class ReportingSnapshot:
    data: bytes

    def __post_init__(self):
        _decode_snapshot(self.data)


def _check_json_tree(value):
    stack = [value]
    while stack:
        node = stack.pop()
        node_type = type(node)
        if node_type is dict:
            for key, child in node.items():
                if type(key) is not str:
                    raise TypeError("export object keys must be strings")
                stack.append(child)
        elif node_type is list:
            stack.extend(node)
        elif node_type not in (str, int, bool):
            raise TypeError("export object must contain plain JSON values")


def snapshot_to_dict(snapshot):
    if type(snapshot) is not ReportingSnapshot:
        raise TypeError("expected an exact ReportingSnapshot")
    return _decode_snapshot(snapshot.data)


def snapshot_from_dict(value):
    if type(value) is not dict:
        raise TypeError("export object must be a JSON object")
    _check_snapshot_doc(value)
    _check_json_tree(value)
    try:
        data = _canonical(value)
    except (ValueError, RecursionError, UnicodeEncodeError) as exc:
        raise ValueError("export object is not canonically encodable") from exc
    return ReportingSnapshot(data)


def validate_snapshot(snapshot, config, *, arm=None):
    if type(snapshot) is not ReportingSnapshot:
        raise TypeError("expected an exact ReportingSnapshot")
    validate_config(config)
    if arm is not None:
        if type(arm) is not str:
            raise TypeError("arm must be a string")
        if arm not in sql_qa.ARMS:
            raise ValueError("arm must be one of the collector arms")
    doc = _decode_snapshot(snapshot.data)
    allowed = set(config.shortcut_ids)
    for name in sql_qa.ARMS:
        arm_doc = doc["arms"][name]
        for event in arm_doc["events"]:
            if event["type"] == "shortcut" and event["shortcut_id"] not in allowed:
                raise ValueError("shortcut event is not in the configured allowlist")
        if arm is not None and name != arm:
            if arm_doc["events"] or arm_doc["reports"] or arm_doc["dropped"]:
                raise ValueError("snapshot mixes evidence from the other arm")


def make_channel(config):
    validate_config(config)
    return sql_qa.QaChannel(shortcut_ids=config.shortcut_ids)


def snapshot_channel(channel, config, *, arm=None):
    if type(channel) is not sql_qa.QaChannel:
        raise TypeError("expected an exact QaChannel")
    validate_config(config)
    if channel.shortcut_ids != config.shortcut_ids:
        raise ValueError("channel allowlist differs from the configuration")
    snapshot = ReportingSnapshot(channel.export())
    validate_snapshot(snapshot, config, arm=arm)
    return snapshot


def require_expected(recorded, expected):
    if expected is None:
        if recorded is not None:
            raise ValueError("reported evidence is not expected")
        return None
    validate_config(expected)
    if recorded is None:
        raise ValueError("evidence is missing its reporting configuration")
    validate_config(recorded)
    if recorded != expected:
        raise ValueError("reporting configuration differs from the expectation")
    return None


def snapshots_equal(left, right):
    if type(left) is not ReportingSnapshot or type(right) is not ReportingSnapshot:
        raise TypeError("expected exact ReportingSnapshot records")
    snapshot_to_dict(left)
    snapshot_to_dict(right)
    return left.data == right.data


# ---------------------------------------------------------------------------
# Source instrumentation binding
# ---------------------------------------------------------------------------


def _check_source_name(name):
    if type(name) is not str or not name:
        raise ValueError("instrument source names must be nonempty strings")
    pure = PurePosixPath(name)
    if (
        not pure.parts
        or pure.is_absolute()
        or PureWindowsPath(name).drive
        or ".." in pure.parts
        or str(pure) != name
        or "\\" in name
    ):
        raise ValueError("instrument source names must be relative paths")


def instrument_sources(root, base_paths):
    if isinstance(base_paths, (str, bytes, bytearray)) or not isinstance(
        base_paths, Sequence
    ):
        raise TypeError("base_paths must be a sequence of source names")
    names = list(base_paths)
    for extra in _EXTRA_SOURCES:
        if extra not in names:
            names.append(extra)
    for name in names:
        _check_source_name(name)
    base = Path(root)
    sources = []
    for name in names:
        try:
            blob = (base / name).read_bytes()
        except OSError:
            raise ValueError("cannot read an instrument source") from None
        sources.append((name, hashlib.sha256(blob).hexdigest()))
    return tuple(names), hashlib.sha256(_canonical(sources)).hexdigest()
