"""Contracts for the shared source-bound SQL reporting contract module.

Covers spec/sql-reporting-evidence.md's `train/sql_reporting.py`: the frozen
`ReportingConfig`, the strict canonical `ReportingSnapshot` parser over real
`ptc.sql_qa` collector exports, channel construction and snapshot binding,
independent expected configuration, and expanded instrument source digests.
Real `QaChannel` collectors are the export oracle; no fake events, scorer
results or backend output. A missing implementation fails inside test
bodies, never during collection.
"""

from __future__ import annotations

import builtins
import copy
import dataclasses
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ptc import sql_qa
from ptc.sql_qa import QaChannel, ReportRejected, report_ack

REJECT = (TypeError, ValueError)
MAX_EXPORT_BYTES = 65_536
ROOT = Path(__file__).resolve().parents[1]
BASE_SOURCE_PATHS = (
    "bench/score.py",
    "ptc/sql_arms.py",
    "ptc/runtime.py",
    "ptc/sql_runtime.py",
    "ptc/sqlite_safety.py",
    "ptc/harness.py",
)
REPORTING_SOURCE_PATHS = ("ptc/sql_qa.py", "train/sql_reporting.py")


def _api():
    try:
        return importlib.import_module("train.sql_reporting")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_reporting":
            raise
        pytest.fail("train.sql_reporting is not implemented", pytrace=False)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _config(api, shortcut_ids=()):
    return api.ReportingConfig(shortcut_ids=shortcut_ids)


def _populated_channel(shortcut_ids=("fixture_alpha",)):
    """A real channel exercising every legitimate event/provenance kind."""
    channel = QaChannel(shortcut_ids=shortcut_ids)
    channel.submit("ptc", kind="task_defect", detail="ptc allegation")
    with pytest.raises(ReportRejected):
        channel.submit_raw("ptc", "not json at all")
    channel.record_shortcut(
        "ptc", "fixture_alpha", provenance="fixture.probe_v2")
    channel.consume_output(
        "bash",
        sql_qa.REPORT_MARKER
        + '{"kind":"other","detail":"bash allegation"}',
    )
    channel.consume_output("bash", sql_qa.SHORTCUT_MARKER + " fixture_alpha")
    return channel


def _overflow_channel():
    """A real channel whose ninth report produced a `report_cap` overflow."""
    channel = QaChannel()
    for index in range(9):
        try:
            channel.submit("ptc", kind="other", detail=f"report-{index}")
        except ReportRejected:
            pass
    return channel


def _caps_channel():
    """A real channel at every bound: 32 events/arm, 64 total, saturated drop."""
    channel = QaChannel(shortcut_ids=("fixture_alpha",))
    for _ in range(sql_qa.MAX_EVENTS_PER_ARM):
        channel.record_shortcut(
            "ptc", "fixture_alpha", provenance="fixture.probe_v2")
    for _ in range(sql_qa.MAX_EVENTS_PER_ARM):
        channel.record_shortcut(
            "bash", "fixture_alpha", provenance="out.route-7")
    for _ in range(sql_qa.DROPPED_MAX):
        with pytest.raises(ReportRejected):
            channel.record_shortcut(
                "ptc", "fixture_alpha", provenance="sentry")
    return channel


def _export_dict(channel):
    return json.loads(channel.export())


def _snapshot(api, channel):
    return api.ReportingSnapshot(channel.export())


@pytest.fixture(autouse=True)
def no_model_stack(monkeypatch):
    """Fail even when an implementation catches an unwanted import."""
    original_import = builtins.__import__
    original_module = importlib.import_module
    attempted = []
    forbidden = {
        "torch", "transformers", "trl", "unsloth", "vllm", "verifiers",
        "datasets", "huggingface_hub", "httpx", "pydantic",
    }

    def check(name):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"model/framework import attempted: {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return original_import(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        check(name)
        return original_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    yield
    assert attempted == []


# --------------------------------------------------------------------------
# ReportingConfig: frozen exact type, version/mode and canonical allowlist.
# --------------------------------------------------------------------------

def test_config_defaults_exact_type_and_frozen():
    api = _api()
    config = api.ReportingConfig()
    assert type(config) is api.ReportingConfig
    assert dataclasses.is_dataclass(config)
    assert config.__dataclass_params__.frozen
    assert config.version == 1
    assert config.mode == "defect_reports"
    assert config.shortcut_ids == ()
    assert api.validate_config(config) is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.version = 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.shortcut_ids = ("x",)
    full = _config(api, ("alpha", "beta_2"))
    assert api.validate_config(full) is None


@pytest.mark.parametrize("field,value", (
    ("version", True), ("version", False), ("version", 2), ("version", 0),
    ("version", "1"), ("version", 1.0), ("version", None),
    ("mode", "other"), ("mode", ""), ("mode", None), ("mode", True),
    ("mode", "DEFECT_REPORTS"),
    ("shortcut_ids", ["alpha"]), ("shortcut_ids", {"alpha"}),
    ("shortcut_ids", "alpha"), ("shortcut_ids", ("beta", "alpha")),
    ("shortcut_ids", ("alpha", "alpha")), ("shortcut_ids", ("1alpha",)),
    ("shortcut_ids", ("has-dash",)), ("shortcut_ids", ("has space",)),
    ("shortcut_ids", ("",)), ("shortcut_ids", (None,)), ("shortcut_ids", (7,)),
    ("shortcut_ids", ("a" * 65,)), ("shortcut_ids", ("café",)),
    ("shortcut_ids", ("a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9")),
))
def test_config_rejects_noncanonical_inputs_before_execution(field, value):
    api = _api()
    with pytest.raises(REJECT):
        api.ReportingConfig(**{field: value})


@pytest.mark.parametrize("impostor", ("class", "factory", "subclass", "tuple"))
def test_config_requires_exact_concrete_instance(impostor):
    api = _api()
    if impostor == "class":
        value = api.ReportingConfig
    elif impostor == "factory":
        value = lambda: api.ReportingConfig()
    elif impostor == "subclass":
        class Subclass(api.ReportingConfig):
            pass
        value = Subclass()
    else:
        value = (api.ReportingConfig(),)
    with pytest.raises(REJECT):
        api.validate_config(value)


@pytest.mark.parametrize("value", (None, 1, True, "defect_reports", [], {}))
def test_validate_config_rejects_nonconfigs(value):
    api = _api()
    with pytest.raises(REJECT):
        api.validate_config(value)


def test_config_wire_shape_is_exact_and_roundtrips():
    api = _api()
    config = _config(api, ("alpha", "beta_2"))
    wire = api.config_to_dict(config)
    assert wire == {
        "version": 1, "mode": "defect_reports", "shortcut_ids": ["alpha", "beta_2"],
    }
    assert type(wire["shortcut_ids"]) is list
    empty = api.config_to_dict(api.ReportingConfig())
    assert empty == {"version": 1, "mode": "defect_reports", "shortcut_ids": []}
    assert api.config_from_dict(wire) == config
    assert api.config_from_dict(json.loads(_canonical(wire))) == config
    with pytest.raises(REJECT):
        api.config_to_dict("not a config")


@pytest.mark.parametrize("mutation", (
    "extra_key", "missing_key", "version_bool", "version_two", "version_str",
    "mode_other", "ids_tuple_not_list", "ids_unsorted", "ids_duplicate",
    "ids_invalid", "ids_too_many", "not_a_dict", "nested_garbage",
))
def test_config_from_dict_rejects_invalid_wire(mutation):
    api = _api()
    wire = {"version": 1, "mode": "defect_reports", "shortcut_ids": ["alpha"]}
    if mutation == "extra_key":
        wire["extra"] = 1
    elif mutation == "missing_key":
        del wire["mode"]
    elif mutation == "version_bool":
        wire["version"] = True
    elif mutation == "version_two":
        wire["version"] = 2
    elif mutation == "version_str":
        wire["version"] = "1"
    elif mutation == "mode_other":
        wire["mode"] = "other"
    elif mutation == "ids_tuple_not_list":
        wire["shortcut_ids"] = ("alpha",)
    elif mutation == "ids_unsorted":
        wire["shortcut_ids"] = ["beta", "alpha"]
    elif mutation == "ids_duplicate":
        wire["shortcut_ids"] = ["alpha", "alpha"]
    elif mutation == "ids_invalid":
        wire["shortcut_ids"] = ["not-an-id"]
    elif mutation == "ids_too_many":
        wire["shortcut_ids"] = [f"id{i}" for i in range(9)]
    elif mutation == "nested_garbage":
        wire["shortcut_ids"] = [None]
    value = wire if mutation != "not_a_dict" else ["version", 1]
    with pytest.raises(REJECT):
        api.config_from_dict(value)


# --------------------------------------------------------------------------
# QaChannel accessor and unchanged export v1 bytes.
# --------------------------------------------------------------------------

def test_channel_shortcut_ids_property_is_sorted_immutable_and_export_unchanged():
    channel = QaChannel(shortcut_ids=("beta", "alpha"))
    assert channel.shortcut_ids == ("alpha", "beta")
    assert type(channel.shortcut_ids) is tuple
    empty = QaChannel()
    assert empty.shortcut_ids == ()
    doc = _export_dict(_populated_channel())
    assert set(doc) == {"version", "total_events", "arms"}
    assert doc["version"] == 1
    assert set(doc["arms"]) == {"bash", "ptc"}
    for arm in ("bash", "ptc"):
        assert set(doc["arms"][arm]) == {
            "dropped", "dropped_saturated", "events", "reports",
        }
    channel = _populated_channel()
    assert channel.export() == _populated_channel().export()
    assert channel.export() == _canonical(_export_dict(channel))


# --------------------------------------------------------------------------
# Reachable snapshots: every legitimate collector export is accepted.
# --------------------------------------------------------------------------

def test_snapshot_accepts_empty_and_fully_populated_exports():
    api = _api()
    for channel in (QaChannel(), _populated_channel(), _overflow_channel()):
        snapshot = _snapshot(api, channel)
        assert type(snapshot) is api.ReportingSnapshot
        assert type(snapshot.data) is bytes
        assert snapshot.data == channel.export()
        assert api.snapshot_to_dict(snapshot) == _export_dict(channel)
        assert api.validate_snapshot(
            snapshot, _config(api, ("fixture_alpha",))) is None
        restored = api.snapshot_from_dict(api.snapshot_to_dict(snapshot))
        assert api.snapshots_equal(snapshot, restored) is True


def test_snapshot_accepts_custom_shortcut_provenance_and_saturated_caps():
    api = _api()
    channel = _caps_channel()
    doc = _export_dict(channel)
    assert doc["total_events"] == 64
    assert len(doc["arms"]["ptc"]["events"]) == 32
    assert len(doc["arms"]["bash"]["events"]) == 32
    assert doc["arms"]["ptc"]["dropped"] == 64
    assert doc["arms"]["ptc"]["dropped_saturated"] is True
    assert doc["arms"]["bash"]["dropped"] == 0
    provenances = {
        event["provenance"]
        for arm in doc["arms"].values() for event in arm["events"]
    }
    assert "fixture.probe_v2" in provenances
    assert "out.route-7" in provenances
    snapshot = _snapshot(api, channel)
    assert api.validate_snapshot(
        snapshot, _config(api, ("fixture_alpha",))) is None


def test_snapshot_accepts_report_cap_overflow_after_eight_reports():
    api = _api()
    channel = _overflow_channel()
    doc = _export_dict(channel)
    assert doc["arms"]["ptc"]["reports"] == 8
    overflow = [e for e in doc["arms"]["ptc"]["events"] if e["type"] == "overflow"]
    assert len(overflow) == 1 and overflow[0]["reason"] == "report_cap"
    assert api.validate_snapshot(_snapshot(api, channel), _config(api)) is None


def test_validate_snapshot_arm_isolation_and_shortcut_membership():
    api = _api()
    snapshot = _snapshot(api, _populated_channel(
        shortcut_ids=("fixture_alpha", "fixture_beta")))
    config = _config(api, ("fixture_alpha", "fixture_beta"))
    assert api.validate_snapshot(snapshot, config) is None
    with pytest.raises(REJECT):
        api.validate_snapshot(snapshot, config, arm="ptc")
    with pytest.raises(REJECT):
        api.validate_snapshot(snapshot, config, arm="bash")
    only = QaChannel(shortcut_ids=("fixture_alpha",))
    only.submit("ptc", kind="other", detail="single arm allegation")
    assert api.validate_snapshot(
        _snapshot(api, only), _config(api, ("fixture_alpha",)),
        arm="ptc") is None
    with pytest.raises(REJECT):
        api.validate_snapshot(
            _snapshot(api, only), _config(api, ("fixture_alpha",)),
            arm="bash")
    foreign = _populated_channel(shortcut_ids=("fixture_alpha", "fixture_beta"))
    with pytest.raises(REJECT):
        api.validate_snapshot(
            _snapshot(api, foreign), _config(api, ("fixture_beta",)))
    with pytest.raises(REJECT):
        api.validate_snapshot(_export_dict(only), _config(api))
    with pytest.raises(REJECT):
        api.validate_snapshot(
            _snapshot(api, only), "not a config")


def test_make_channel_and_snapshot_channel_exact_binding():
    api = _api()
    config = _config(api, ("fixture_alpha",))
    first, second = api.make_channel(config), api.make_channel(config)
    assert type(first) is QaChannel and first is not second
    assert first.shortcut_ids == second.shortcut_ids == ("fixture_alpha",)
    snapshot = api.snapshot_channel(first, config)
    assert type(snapshot) is api.ReportingSnapshot
    assert api.snapshot_to_dict(snapshot) == json.loads(first.export())
    populated = _populated_channel()
    doc = api.snapshot_to_dict(
        api.snapshot_channel(populated, _config(api, ("fixture_alpha",))))
    assert doc == _export_dict(populated)
    ptc_channel = QaChannel(shortcut_ids=("fixture_alpha",))
    ptc_channel.submit("ptc", kind="other", detail="only ptc")
    assert type(api.snapshot_channel(
        ptc_channel, _config(api, ("fixture_alpha",)),
        arm="ptc")) is api.ReportingSnapshot
    with pytest.raises(REJECT):
        api.snapshot_channel(
            ptc_channel, _config(api, ("fixture_alpha",)), arm="bash")
    with pytest.raises(REJECT):
        api.snapshot_channel(populated, _config(api, ("fixture_alpha",)), arm="ptc")
    with pytest.raises(REJECT):
        api.snapshot_channel(populated, _config(api, ("other_id",)))

    class Subclass(QaChannel):
        pass

    for bad in (Subclass(("fixture_alpha",)), QaChannel, {}, "channel", None):
        with pytest.raises(REJECT):
            api.snapshot_channel(bad, config)


def test_snapshots_equal_compares_canonical_bytes_and_rejects_wrong_types():
    api = _api()
    left = _snapshot(api, _populated_channel())
    right = _snapshot(api, _populated_channel())
    assert api.snapshots_equal(left, right) is True
    different = _snapshot(api, _overflow_channel())
    assert api.snapshots_equal(left, different) is False
    for value in (api.snapshot_to_dict(left), left.data, "snapshot", None):
        with pytest.raises(REJECT):
            api.snapshots_equal(value, left)
        with pytest.raises(REJECT):
            api.snapshots_equal(left, value)


def test_require_expected_returns_none_on_equality_and_rejects_differences():
    api = _api()
    config = _config(api, ("fixture_alpha",))
    wire = api.config_to_dict(config)
    assert api.require_expected(api.config_from_dict(wire), config) is None
    assert api.require_expected(None, None) is None
    for recorded, expected in (
        (_config(api, ("fixture_beta",)), config),
        (_config(api), config),
        (None, config),
        (config, None),
        (wire, config),
        ("not-a-config", config),
        ({"version": 1, "mode": "defect_reports", "shortcut_ids": ["9bad"]},
         config),
    ):
        with pytest.raises(REJECT):
            api.require_expected(recorded, expected)


# --------------------------------------------------------------------------
# Malformed snapshots: strict parser rejects, never truncates.
# --------------------------------------------------------------------------

def _mutated(change):
    doc = _export_dict(_populated_channel())
    change(doc)
    return _canonical(doc)


def _mutated_overflow(change):
    doc = _export_dict(_overflow_channel())
    change(doc)
    return _canonical(doc)


def _arm_events(doc, arm="ptc"):
    return doc["arms"][arm]["events"]


def _padded_arm_events(doc):
    ptc = [
        {"arm": "ptc", "seq": index, "type": "report_rejected",
         "provenance": "catalog_callback", "reason": "schema"}
        for index in range(1, 34)
    ]
    bash = doc["arms"]["bash"]["events"]
    for offset, event in enumerate(bash):
        event["seq"] = 34 + offset
    doc["arms"]["ptc"]["events"] = ptc
    doc["arms"]["ptc"]["reports"] = 0
    doc["total_events"] = len(ptc) + len(bash)


_MALFORMED = {
    "top_unknown_key": lambda: _mutated(lambda d: d.__setitem__("extra", 1)),
    "top_missing_key": lambda: _mutated(lambda d: d.__delitem__("arms")),
    "version_two": lambda: _mutated(lambda d: d.__setitem__("version", 2)),
    "version_bool": lambda: _mutated(lambda d: d.__setitem__("version", True)),
    "version_string": lambda: _mutated(lambda d: d.__setitem__("version", "1")),
    "arms_not_object": lambda: _mutated(lambda d: d.__setitem__("arms", [])),
    "arm_unknown": lambda: _mutated(
        lambda d: d["arms"].__setitem__("gpu", d["arms"]["ptc"])),
    "arm_missing": lambda: _mutated(lambda d: d["arms"].__delitem__("bash")),
    "arm_extra_key": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("extra", 0)),
    "arm_missing_key": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__delitem__("dropped_saturated")),
    "events_not_list": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("events", {})),
    "event_extra_key": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("extra", 1)),
    "event_missing_key": lambda: _mutated(
        lambda d: _arm_events(d)[0].__delitem__("provenance")),
    "event_unknown_type": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("type", "telemetry")),
    "report_bad_provenance": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("provenance", "made_up")),
    "rejection_bad_reason": lambda: _mutated(
        lambda d: _arm_events(d)[1].__setitem__("reason", "bogus")),
    "seq_gap": lambda: _mutated(
        lambda d: _arm_events(d)[2].__setitem__("seq", 7)),
    "seq_duplicate": lambda: _mutated(
        lambda d: _arm_events(d)[2].__setitem__("seq", 1)),
    "seq_bool": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("seq", True)),
    "seq_out_of_order": lambda: _mutated(
        lambda d: _arm_events(d).__setitem__(
            slice(0, 2), [_arm_events(d)[1], _arm_events(d)[0]])),
    "reports_mismatch": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("reports", 5)),
    "reports_over_cap": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("reports", 9)),
    "reports_bool": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("reports", True)),
    "events_over_arm_cap": lambda: _mutated(_padded_arm_events),
    "total_mismatch": lambda: _mutated(
        lambda d: d.__setitem__("total_events", 99)),
    "dropped_negative": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("dropped", -1)),
    "dropped_over_max": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("dropped", 65)),
    "dropped_bool": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("dropped", True)),
    "saturated_before_64": lambda: _mutated(
        lambda d: (d["arms"]["ptc"].__setitem__("dropped", 63),
                   d["arms"]["ptc"].__setitem__("dropped_saturated", True))),
    "unsaturated_at_64": lambda: _mutated(
        lambda d: (d["arms"]["ptc"].__setitem__("dropped", 64),
                   d["arms"]["ptc"].__setitem__("dropped_saturated", False))),
    "drop_without_full_log": lambda: _mutated(
        lambda d: d["arms"]["ptc"].__setitem__("dropped", 1)),
    "kind_unknown": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("kind", "made_up_kind")),
    "detail_empty": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("detail", "")),
    "detail_oversized": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("detail", "x" * 2100)),
    "detail_nonstring": lambda: _mutated(
        lambda d: _arm_events(d)[0].__setitem__("detail", 42)),
    "shortcut_bad_provenance": lambda: _mutated(
        lambda d: _arm_events(d)[2].__setitem__("provenance", "bad token!")),
    "shortcut_bad_id": lambda: _mutated(
        lambda d: _arm_events(d)[2].__setitem__("shortcut_id", "not-an-id")),
    "overflow_bad_reason": lambda: _mutated_overflow(
        lambda d: _arm_events(d)[-1].__setitem__("reason", "quota_cap")),
    "overflow_without_eight_reports": lambda: _mutated(
        lambda d: (
            _arm_events(d, "bash").append(
                {"arm": "bash", "seq": 6, "type": "overflow",
                 "provenance": "agent_output", "reason": "report_cap"}),
            d.__setitem__("total_events", 6))),
}


@pytest.mark.parametrize("case", sorted(_MALFORMED))
def test_malformed_snapshot_rejected(case):
    api = _api()
    with pytest.raises(REJECT):
        api.ReportingSnapshot(_MALFORMED[case]())


@pytest.mark.parametrize("data", (
    pytest.param(b"", id="empty"),
    pytest.param(b"\xff\xfe{", id="invalid_utf8"),
    pytest.param(b'{"version":1,"version":1,"arms":{},"total_events":0}',
                 id="duplicate_keys"),
    pytest.param(
        b'{"arms":{"bash":{"dropped":0,"dropped_saturated":false,"events":[],'
        b'"reports":0},"ptc":{"dropped":0,"dropped_saturated":false,"events":[]'
        b',"reports":0}},"total_events":NaN,"version":1}',
        id="nonfinite_number"),
    pytest.param(b" " * (MAX_EXPORT_BYTES + 1), id="over_byte_cap"),
    pytest.param(
        b'{"arms":{"bash":{"dropped":0,"dropped_saturated":false,"events":[],'
        b'"reports":0},"ptc":{"dropped":0,"dropped_saturated":false,"events":'
        b'[{"arm":"ptc","detail":"\\ud800","kind":"other","provenance":'
        b'"catalog_callback","seq":1,"type":"report"}],"reports":1}},'
        b'"total_events":1,"version":1}',
        id="unencodable_surrogate"),
    pytest.param(b'[]', id="not_an_object"),
    pytest.param(b'null', id="json_null"),
))
def test_malformed_snapshot_bytes_rejected(data):
    api = _api()
    with pytest.raises(REJECT):
        api.ReportingSnapshot(data)


def test_snapshot_never_truncates_or_pads_to_fit():
    api = _api()
    valid = QaChannel().export()
    assert len(valid) <= MAX_EXPORT_BYTES
    snapshot = api.ReportingSnapshot(valid)
    assert type(snapshot) is api.ReportingSnapshot
    with pytest.raises(REJECT):
        api.ReportingSnapshot(valid + b"\n{}")
    with pytest.raises(REJECT):
        api.ReportingSnapshot(valid + b" " * (MAX_EXPORT_BYTES - len(valid) + 1))
    with pytest.raises(REJECT):
        api.ReportingSnapshot("not bytes")
    with pytest.raises(REJECT):
        api.ReportingSnapshot(_export_dict(QaChannel()))


# --------------------------------------------------------------------------
# instrument_sources: expanded path set and canonical source digest.
# --------------------------------------------------------------------------

def test_instrument_sources_appends_reporting_paths_and_hashes_canonically():
    api = _api()
    paths, digest = api.instrument_sources(ROOT, BASE_SOURCE_PATHS)
    expected_paths = BASE_SOURCE_PATHS + REPORTING_SOURCE_PATHS
    assert paths == expected_paths
    pairs = tuple(
        (name, hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
        for name in expected_paths
    )
    assert digest == hashlib.sha256(_canonical(pairs)).hexdigest()
    again, again_digest = api.instrument_sources(ROOT, expected_paths)
    assert again == expected_paths
    assert again_digest == digest
    minimal, _ = api.instrument_sources(ROOT, ())
    assert minimal == REPORTING_SOURCE_PATHS


@pytest.mark.parametrize("name", (
    "/etc/passwd", "/abs.py", "../escape.py", "a/../b.py", "..",
    "ptc/../../outside.py", "", " ",
))
def test_instrument_sources_rejects_absolute_or_traversing_names(name):
    api = _api()
    with pytest.raises(REJECT) as raised:
        api.instrument_sources(ROOT, (name,))
    assert str(raised.value) in {
        "instrument source names must be nonempty strings",
        "instrument source names must be relative paths",
        "cannot read an instrument source",
    }


def test_snapshot_from_dict_rejects_cycles_without_hanging():
    child = (
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
        "from train import sql_reporting as reporting\n"
        "value = {}; value['arms'] = value\n"
        "try:\n"
        "    reporting.snapshot_from_dict(value)\n"
        "except (TypeError, ValueError):\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('cyclic snapshot accepted')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", child],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_snapshots_equal_revalidates_forged_snapshot_instances():
    api = _api()
    forged = object.__new__(api.ReportingSnapshot)
    object.__setattr__(forged, "data", b"{}")
    with pytest.raises(REJECT):
        api.snapshots_equal(forged, forged)


def test_instrument_sources_reads_real_current_bytes(tmp_path):
    api = _api()
    root = tmp_path / "source-root"
    for name in REPORTING_SOURCE_PATHS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    assert api.instrument_sources(root, ()) == api.instrument_sources(ROOT, ())
    changed = root / "ptc" / "sql_qa.py"
    changed.write_bytes(changed.read_bytes() + b"\n# bound-source-change\n")
    clean_paths, clean_digest = api.instrument_sources(ROOT, ())
    moved_paths, moved_digest = api.instrument_sources(root, ())
    assert moved_paths == clean_paths == REPORTING_SOURCE_PATHS
    assert moved_digest != clean_digest


def test_reporting_module_is_light_and_adds_only_declared_api():
    api = _api()
    for name in (
        "ReportingConfig", "ReportingSnapshot", "validate_config",
        "config_to_dict", "config_from_dict", "snapshot_to_dict",
        "snapshot_from_dict", "validate_snapshot", "make_channel",
        "snapshot_channel", "require_expected", "snapshots_equal",
        "instrument_sources",
    ):
        assert callable(getattr(api, name)), f"missing reporting API {name}"
