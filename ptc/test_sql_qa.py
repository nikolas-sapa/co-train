"""Tests for the stage-4 bounded allegation collector (`ptc/sql_qa.py`).

The collector records *unverified allegations* of task/verifier/environment
defects from either arm. Every guarantee under test is a bound or a non-claim:
fixed receipt text, closed schema, per-arm quotas, saturating overflow counters,
exact-marker output parsing that preserves the original bytes, and a shortcut
hook that fires only on explicit trusted-caller instrumentation. Nothing here
grants reward, validity, turns or authorization, and a marker found in shell
output is provenance `agent_output` -- forgeable, never authenticated.
"""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import MappingProxyType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ptc.sql_qa import (  # noqa: E402
    BASH_REPORT,
    FEEDBACK_CAPPED,
    KINDS,
    MAX_EXPORT_BYTES,
    MAX_OUTPUT_FEEDBACK,
    MAX_RAW_BYTES,
    MAX_REPORT_BYTES,
    MAX_REPORTS_PER_ARM,
    PTC_REPORT,
    REPORT_MARKER,
    REPORT_OVERFLOW,
    REPORT_REFUSED,
    REPORT_TOOL,
    SHORTCUT_MARKER,
    QaChannel,
    ReportRejected,
    install_report_wrapper,
    report_ack,
)

ACK = "report received (unverified allegation; outcome unchanged)"


def _report_line(payload: dict) -> str:
    return REPORT_MARKER + json.dumps(payload)


# ---------------------------------------------------------------------------
# Fixed receipt and prompt text.
# ---------------------------------------------------------------------------


def test_report_ack_exact():
    """The receipt is one fixed string; no success claim, no variability."""
    assert report_ack() == ACK


def test_prompt_semantics_constants():
    """REPORT_PROMPT carries the shared semantics; the two REPORT sentences name
    each arm's invocation surface without claiming verification or reward."""
    from ptc.sql_qa import REPORT_PROMPT

    for kind in KINDS:
        assert kind in REPORT_PROMPT
    assert "unverified" in REPORT_PROMPT
    assert "outcome" in REPORT_PROMPT or "scoring" in REPORT_PROMPT
    assert REPORT_TOOL in BASH_REPORT
    assert REPORT_TOOL in PTC_REPORT


# ---------------------------------------------------------------------------
# Schema and raw parsing strictness.
# ---------------------------------------------------------------------------


def test_submit_accepts_all_four_kinds():
    ch = QaChannel()
    for i, kind in enumerate(KINDS):
        assert ch.submit("ptc", kind=kind, detail=f"detail {i}") == ACK
    reports = [e for e in ch.events if e["type"] == "report"]
    assert len(reports) == len(KINDS)
    assert {e["kind"] for e in reports} == set(KINDS)
    assert all(e["provenance"] == "catalog_callback" for e in reports)


@pytest.mark.parametrize("kind", ["TASK_DEFECT", "bug", "", 1, None, ["task_defect"]])
def test_submit_rejects_bad_kind(kind):
    ch = QaChannel()
    with pytest.raises(ReportRejected):
        ch.submit("ptc", kind=kind, detail="x")


@pytest.mark.parametrize("detail", ["", 3, None, {"a": 1}, ["x"]])
def test_submit_rejects_bad_detail(detail):
    ch = QaChannel()
    with pytest.raises(ReportRejected):
        ch.submit("ptc", kind="task_defect", detail=detail)


def test_submit_rejects_unknown_arm():
    ch = QaChannel()
    with pytest.raises(ValueError):
        ch.submit("arm3", kind="task_defect", detail="x")


def test_submit_rejects_surrogate_detail():
    ch = QaChannel()
    with pytest.raises(ReportRejected):
        ch.submit("ptc", kind="other", detail="lone surrogate: \ud800")


def test_submit_raw_accepts_valid_bytes_and_str():
    ch = QaChannel()
    assert ch.submit_raw("bash", b'{"kind":"task_defect","detail":"d1"}') == ACK
    assert ch.submit_raw("ptc", '{"kind":"other","detail":"d2"}') == ACK
    assert len([e for e in ch.events if e["type"] == "report"]) == 2


@pytest.mark.parametrize(
    "raw",
    [
        b'{"kind":"task_defect","detail":"a","kind":"other"}',  # duplicate key
        b'{"kind":"task_defect","detail":"a","extra":1}',      # extra key
        b'{"kind":"task_defect"}',                             # missing detail
        b'{"detail":"a"}',                                     # missing kind
        b'{"kind":"other","detail":"a","kind2":null}',         # extra key variant
        b'{"kind":"other","detail":NaN}',                      # non-finite
        b'{"kind":"other","detail":Infinity}',                 # non-finite
        b'{"kind":"other","detail":-Infinity}',                # non-finite
        b'{"kind":"other","detail":5}',                        # wrong type
        b'{"kind":"bogus","detail":"a"}',                      # wrong kind
        b'{"kind":"other","detail":""}',                       # empty detail
        b'["kind","detail"]',                                  # not an object
        b'"just a string"',                                    # not an object
        b'{"kind":"other","detail":"\xff\xfe"}',               # bad utf-8
        '{"kind":"other","detail":"\\ud800"}'.encode(),        # escaped surrogate
        b'',                                                   # empty
        b'   ',                                                # whitespace only
        5,                                                     # not str/bytes
        {"kind": "other", "detail": "a"},                      # not str/bytes
    ],
)
def test_submit_raw_rejects_nonconforming(raw):
    ch = QaChannel()
    with pytest.raises(ReportRejected):
        ch.submit_raw("bash", raw)


def test_submit_raw_bounded_before_parse():
    """Raw input is refused on its byte bound before any JSON parse or decode."""
    ch = QaChannel()
    big = b'{"kind":"other","detail":"' + b"a" * MAX_RAW_BYTES + b'"}'
    with pytest.raises(ReportRejected):
        ch.submit_raw("bash", big)
    # A str whose code-point count already exceeds the byte bound never reaches
    # the encoder either.
    with pytest.raises(ReportRejected):
        ch.submit_raw("bash", "x" * (MAX_RAW_BYTES + 1))


def test_canonical_payload_byte_cap():
    """The 2,048-byte bound applies to canonical UTF-8 payload bytes, so a
    detail that needs escapes still counts its true size."""
    ch = QaChannel()
    # Binary search the largest accepted ASCII detail under the canonical cap.
    overhead = len(
        json.dumps({"detail": "", "kind": "other"}, sort_keys=True,
                   separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    ok = MAX_REPORT_BYTES - overhead
    assert ch.submit("ptc", kind="other", detail="a" * ok) == ACK
    with pytest.raises(ReportRejected):
        ch.submit("ptc", kind="other", detail="a" * (ok + 1))
    # Non-ASCII detail: UTF-8 bytes count, not code points.
    with pytest.raises(ReportRejected):
        ch.submit("ptc", kind="other", detail="é" * ok)


def test_rejection_messages_carry_no_raw_payload():
    """Rejections must not echo attacker bytes (bounded, and avoids unbounded
    str/bytes conversion on the rejection path)."""
    ch = QaChannel()
    payload = b'{"kind":"bogus","detail":"' + b"A" * 5000 + b'"}'
    with pytest.raises(ReportRejected) as ei:
        ch.submit_raw("bash", payload)
    assert "AAAA" not in str(ei.value)
    assert len(str(ei.value)) < 200


# ---------------------------------------------------------------------------
# Quotas: reports per arm, events per arm, total; saturating overflow.
# ---------------------------------------------------------------------------


def test_report_cap_eight_per_arm():
    ch = QaChannel()
    for i in range(MAX_REPORTS_PER_ARM):
        assert ch.submit("ptc", kind="other", detail=f"d{i}") == ACK
    with pytest.raises(ReportRejected):
        ch.submit("ptc", kind="other", detail="one too many")
    assert len([e for e in ch.events
                if e["type"] == "report" and e["arm"] == "ptc"]) == MAX_REPORTS_PER_ARM


def test_arm_quotas_are_independent():
    """One arm cannot consume the other's allowance."""
    ch = QaChannel()
    for i in range(MAX_REPORTS_PER_ARM):
        ch.submit("bash", kind="other", detail=f"d{i}")
    with pytest.raises(ReportRejected):
        ch.submit("bash", kind="other", detail="overflow")
    # The ptc arm is untouched and can still file its full quota.
    for i in range(MAX_REPORTS_PER_ARM):
        assert ch.submit("ptc", kind="other", detail=f"d{i}") == ACK
    assert len([e for e in ch.events if e["type"] == "report"]) == 2 * MAX_REPORTS_PER_ARM


def test_event_caps_and_saturating_dropped_counter():
    """32 events per arm, 64 total. Overflow stays visible through a bounded,
    saturating dropped counter -- never an unbounded decimal."""
    ch = QaChannel()
    # Burn the ptc arm's event budget with malformed raw reports: each attempt
    # records a report_rejected event until the log fills, then drops.
    for _ in range(1000):
        with pytest.raises(ReportRejected):
            ch.submit_raw("ptc", b'{"kind":"bogus","detail":"x"}')
    ptc_events = [e for e in ch.events if e["arm"] == "ptc"]
    assert len(ptc_events) == 32
    assert len(ch.events) <= 64
    doc = json.loads(ch.export())
    dropped = doc["arms"]["ptc"]["dropped"]
    assert dropped > 0
    assert doc["arms"]["ptc"]["dropped_saturated"] is True
    # The counter is saturating: the export does not grow unboundedly with the
    # flood size. A second identical-flood channel shows the same ceiling.
    ch2 = QaChannel()
    for _ in range(5000):
        with pytest.raises(ReportRejected):
            ch2.submit_raw("ptc", b'{"kind":"bogus","detail":"x"}')
    assert json.loads(ch2.export())["arms"]["ptc"]["dropped"] == dropped


def test_no_success_receipt_for_dropped_events():
    """Flood output past every cap: appended feedback contains refusals, never
    the success receipt, and stays bounded."""
    ch = QaChannel()
    text = "\n".join(_report_line({"kind": "other", "detail": f"d{i}"})
                     for i in range(50))
    out = ch.consume_output("bash", text)
    assert out.startswith(text)
    appended = out[len(text):]
    assert ACK not in appended or appended.count(ACK) <= MAX_REPORTS_PER_ARM
    # After the 8-report cap, every further marker draws a refusal, never an ack.
    tail = "\n".join(_report_line({"kind": "other", "detail": f"again{i}"})
                     for i in range(20))
    out2 = ch.consume_output("bash", tail)
    assert ACK not in out2[len(tail):]
    assert REPORT_OVERFLOW in out2 or REPORT_REFUSED in out2 or FEEDBACK_CAPPED in out2


# ---------------------------------------------------------------------------
# Export and snapshot properties.
# ---------------------------------------------------------------------------


def test_export_is_stable_canonical_and_bounded():
    ch = QaChannel()
    ch.submit("ptc", kind="task_defect", detail="schema lies")
    ch.submit("bash", kind="other", detail="x" * 1000)
    first = ch.export()
    assert first == ch.export()
    assert isinstance(first, bytes) and len(first) <= MAX_EXPORT_BYTES
    doc = json.loads(first)
    assert doc["arms"]["ptc"]["reports"] == 1
    assert doc["arms"]["bash"]["reports"] == 1
    # Deterministic: a channel built by the same calls exports identical bytes.
    ch2 = QaChannel()
    ch2.submit("ptc", kind="task_defect", detail="schema lies")
    ch2.submit("bash", kind="other", detail="x" * 1000)
    assert ch2.export() == first


def test_export_stays_bounded_and_stable_after_flood():
    """A saturated channel still exports <=64 KiB and identical bytes; accepted
    events are never dropped at export time."""
    ch = QaChannel()
    for i in range(MAX_REPORTS_PER_ARM):
        ch.submit("bash", kind="other", detail="d" * 2000)
        ch.submit("ptc", kind="other", detail="d" * 2000)
    for _ in range(200):
        with pytest.raises(ReportRejected):
            ch.submit_raw("bash", b'{"kind":"bogus"}')
        with pytest.raises(ReportRejected):
            ch.submit_raw("ptc", b'{"kind":"bogus"}')
    size_before = len(ch.export())
    assert size_before <= MAX_EXPORT_BYTES
    assert len([e for e in ch.events if e["type"] == "report"]) == 16
    doc = json.loads(ch.export())
    assert len(doc["arms"]["bash"]["events"]) == 32
    assert len(doc["arms"]["ptc"]["events"]) == 32
    assert ch.export() == ch.export()


def test_events_snapshot_is_immutable():
    """The snapshot is ordered by seq and hands out copies: mutating it cannot
    reach the channel's internal dicts."""
    ch = QaChannel()
    ch.submit("ptc", kind="other", detail="d")
    snap = ch.events
    assert isinstance(snap, tuple)
    ev = snap[0]
    assert isinstance(ev, MappingProxyType)
    with pytest.raises(TypeError):
        ev["kind"] = "tampered"
    for key in ("arm", "seq", "type", "provenance"):
        assert key in ev
    assert ev["arm"] == "ptc" and ev["type"] == "report"
    # Snapshots are also ordered across arms by the global sequence.
    ch.submit("bash", kind="other", detail="d2")
    seqs = [e["seq"] for e in ch.events]
    assert seqs == sorted(seqs)


# ---------------------------------------------------------------------------
# consume_output: exact markers, preservation, bounded feedback, provenance.
# ---------------------------------------------------------------------------


def test_consume_output_exact_marker_only():
    """Family startswith is not enough: only a line beginning with the exact
    public marker (including its trailing space) is a reporting line."""
    ch = QaChannel()
    lines = [
        "COTRAIN_QA_REPORT",                    # no trailing space/payload
        "COTRAIN_QA_REPORTED {}",               # family prefix, wrong token
        "COTRAIN_QA_REPORTX {}",                # family prefix, wrong token
        " COTRAIN_QA_REPORT {}",                # indented
        "note: COTRAIN_QA_REPORT {}",           # mid-line
        "XCOTRAIN_QA_REPORT {}",                # prefixed
    ]
    out = ch.consume_output("bash", "\n".join(lines))
    assert ch.events == ()
    assert out == "\n".join(lines)


def test_consume_output_accepts_exact_marker_and_preserves_text():
    ch = QaChannel()
    payload = {"kind": "task_defect", "detail": "answer key empty"}
    original = (
        "id|name\n1|Ada\n"
        + _report_line(payload)
        + "\nError: near line 1: no such table: missing\n"
    )
    out = ch.consume_output("bash", original)
    # Original bytes survive verbatim as the prefix; feedback is appended only.
    assert out.startswith(original)
    assert out[len(original):].startswith(ACK)
    (ev,) = ch.events
    assert ev["type"] == "report"
    assert ev["arm"] == "bash"
    assert ev["provenance"] == "agent_output"
    assert ev["kind"] == "task_defect"


def test_forged_marker_is_agent_output_allegation_not_authentication():
    """A marker can come from an ordinary SQL row: the event records it as
    forgeable agent_output, an allegation -- never an authenticated call."""
    ch = QaChannel()
    # The marker text is itself SQL *data* on this line-shaped payload; the host
    # still treats an exact-prefix line as an allegation with agent_output
    # provenance, and preserves it.
    text = _report_line({"kind": "verifier_defect", "detail": "claimed by row"})
    out = ch.consume_output("bash", text)
    assert text in out
    (ev,) = ch.events
    assert ev["provenance"] == "agent_output"
    assert "authentic" not in json.dumps(dict(ev)).lower()


def test_consume_output_malformed_marker_appends_bounded_refusal():
    ch = QaChannel()
    text = "SELECT output\n" + REPORT_MARKER + "not json\nmore output\n"
    out = ch.consume_output("ptc", text)
    assert out.startswith(text)
    appended = out[len(text):]
    assert ACK not in appended
    assert appended  # a visible refusal was appended
    # And the refusal attempt is itself a bounded, recorded event.
    assert any(e["type"] == "report_rejected" for e in ch.events)


def _appended(out: str, text: str) -> list[str]:
    """The feedback lines appended after `text`, with the delimiter newline
    consumed first: it is a separator, not a feedback line."""
    assert out.startswith(text)
    suffix = out[len(text):]
    if suffix.startswith("\n"):
        suffix = suffix[1:]
    return suffix.splitlines()


def test_consume_output_bounds_feedback_under_flood():
    ch = QaChannel()
    text = "\n".join(_report_line({"kind": "other", "detail": f"d{i}"})
                     for i in range(100))
    out = ch.consume_output("bash", text)
    assert out.startswith(text)
    appended_lines = _appended(out, text)
    assert 0 < len(appended_lines) <= MAX_OUTPUT_FEEDBACK + 1
    # The whole appended tail is also byte-bounded, not just line-bounded.
    assert len(out.encode("utf-8")) - len(text.encode("utf-8")) <= 1024


def test_exactly_max_feedback_markers_no_cap_notice():
    """Exactly MAX_OUTPUT_FEEDBACK markers yield that many receipts and NO
    flood notice -- the notice exists only when real extra feedback exists."""
    ch = QaChannel()
    text = "\n".join(_report_line({"kind": "other", "detail": f"d{i}"})
                     for i in range(MAX_OUTPUT_FEEDBACK))
    out = ch.consume_output("bash", text)
    appended = _appended(out, text)
    assert len(appended) == MAX_OUTPUT_FEEDBACK
    assert all(line == ACK for line in appended)
    assert FEEDBACK_CAPPED not in appended


def test_flood_fully_processed_quotas_and_overflow():
    """A 100-marker flood is fully accounted, not just the first few: every
    marker reaches quota accounting -- 8 reports retained, the event log
    bounded at 32 for the arm, and nonzero dropped/overflow evidence."""
    ch = QaChannel()
    text = "\n".join(_report_line({"kind": "other", "detail": f"d{i}"})
                     for i in range(100))
    out = ch.consume_output("bash", text)
    appended = _appended(out, text)
    assert len(appended) <= MAX_OUTPUT_FEEDBACK + 1
    assert appended.count(ACK) == MAX_REPORTS_PER_ARM
    assert appended[-1] == FEEDBACK_CAPPED
    # Quotas and overflow were reached, so the flood is visible in the record:
    assert len([e for e in ch.events if e["type"] == "report"]) \
        == MAX_REPORTS_PER_ARM
    assert len([e for e in ch.events if e["arm"] == "bash"]) == 32
    assert any(e["type"] == "overflow" for e in ch.events)
    doc = json.loads(ch.export())
    assert doc["arms"]["bash"]["dropped"] > 0
    assert doc["arms"]["bash"]["dropped_saturated"] is True
    assert len(ch.export()) <= MAX_EXPORT_BYTES


def test_export_stable_after_saturated_flood():
    """Once saturated, further floods change nothing: export bytes are
    identical and no stored record is dropped or rewritten to make room."""
    ch = QaChannel()
    flood = "\n".join(_report_line({"kind": "other", "detail": f"d{i}"})
                      for i in range(200))
    ch.consume_output("bash", flood)
    before = ch.export()
    ch.consume_output("bash", flood)
    with pytest.raises(ReportRejected):
        ch.submit("bash", kind="other", detail="still full")
    assert ch.export() == before
    assert len(ch.export()) <= MAX_EXPORT_BYTES


@pytest.mark.parametrize("sep", ["\u0085", "\u2028", "\u2029"])
def test_unicode_separators_inside_json_are_not_transport_newlines(sep):
    """A literal U+0085/U+2028/U+2029 inside a JSON detail is content, not a
    line break: the structured route and the output route must reach the same
    allegation (only the provenance differs, honestly)."""
    detail = f"first{sep}second"
    raw = json.dumps({"kind": "task_defect", "detail": detail},
                     ensure_ascii=False)

    cb = QaChannel()
    assert cb.submit_raw("ptc", raw) == ACK
    (ev_cb,) = cb.events
    assert ev_cb["provenance"] == "catalog_callback"
    assert ev_cb["kind"] == "task_defect"
    assert ev_cb["detail"] == detail

    out_ch = QaChannel()
    text = REPORT_MARKER + raw
    out = out_ch.consume_output("bash", text)
    assert out.startswith(text)
    assert ACK in _appended(out, text)
    (ev_out,) = out_ch.events
    assert ev_out["provenance"] == "agent_output"
    assert ev_out["kind"] == ev_cb["kind"]
    assert ev_out["detail"] == ev_cb["detail"]


def test_lf_and_crlf_still_separate_markers():
    """Actual LF remains the transport break, and a CRLF-carried marker still
    parses (the CR is transport framing, stripped before the payload)."""
    a = _report_line({"kind": "other", "detail": "a"})
    b = _report_line({"kind": "other", "detail": "b"})

    ch = QaChannel()
    text = a + "\n" + b
    out = ch.consume_output("bash", text)
    assert out.startswith(text)
    assert _appended(out, text).count(ACK) == 2
    assert len([e for e in ch.events if e["type"] == "report"]) == 2

    ch2 = QaChannel()
    text2 = a + "\r\n" + b
    out2 = ch2.consume_output("bash", text2)
    assert out2.startswith(text2)
    assert len([e for e in ch2.events if e["type"] == "report"]) == 2


def test_valid_report_then_malformed_then_flood():
    ch = QaChannel()
    ok = _report_line({"kind": "other", "detail": "fine"})
    bad = REPORT_MARKER + "{broken"
    flood = "\n".join(REPORT_MARKER + "{still broken}" for _ in range(60))
    text = f"{ok}\n{bad}\n{flood}"
    out = ch.consume_output("bash", text)
    assert out.startswith(text)
    appended = out[len(text):]
    assert appended.count(ACK) == 1
    assert REPORT_REFUSED in appended or REPORT_OVERFLOW in appended


def test_shortcut_marker_route_and_spoofing():
    """The shell shortcut marker validates the same allowlist and records
    agent_output (forgeable); non-allowlisted IDs get a bounded refusal."""
    ch = QaChannel(shortcut_ids=("probe_scout",))
    text = "rows\n" + SHORTCUT_MARKER + "probe_scout\nmore\n"
    out = ch.consume_output("bash", text)
    assert out.startswith(text)
    (ev,) = ch.events
    assert ev["type"] == "shortcut"
    assert ev["shortcut_id"] == "probe_scout"
    assert ev["provenance"] == "agent_output"

    ch2 = QaChannel(shortcut_ids=("probe_scout",))
    out2 = ch2.consume_output("bash", SHORTCUT_MARKER + "evil_id")
    assert out2.startswith(SHORTCUT_MARKER + "evil_id")
    assert all(e["type"] != "shortcut" for e in ch2.events)


def test_shortcut_comment_or_mention_records_nothing():
    """A line merely mentioning the identifier -- even a marker family line
    without the exact marker -- is not instrumentation."""
    ch = QaChannel(shortcut_ids=("probe_scout",))
    text = (
        "# the fixture id is probe_scout\n"
        "COTRAIN_QA_SHORTCUTX probe_scout\n"
        "x COTRAIN_QA_SHORTCUT probe_scout\n"
        "COTRAIN_QA_SHORTCUT\n"
    )
    out = ch.consume_output("bash", text)
    assert out == text or all(e["type"] != "shortcut" for e in ch.events)
    assert all(e["type"] != "shortcut" for e in ch.events)


# ---------------------------------------------------------------------------
# record_shortcut: trusted-caller instrumentation hook.
# ---------------------------------------------------------------------------


def test_record_shortcut_marks_actual_calls():
    ch = QaChannel(shortcut_ids=("probe_scout", "other_fixture"))
    ch.record_shortcut("ptc", "probe_scout", provenance="catalog_callback")
    ch.record_shortcut("ptc", "probe_scout", provenance="catalog_callback")
    ch.record_shortcut("ptc", "probe_scout", provenance="catalog_callback")
    events = [e for e in ch.events if e["type"] == "shortcut"]
    assert len(events) == 3
    assert all(e["shortcut_id"] == "probe_scout" for e in events)
    assert all(e["provenance"] == "catalog_callback" for e in events)


@pytest.mark.parametrize(
    "ids",
    [
        tuple(f"id_{i}" for i in range(9)),   # >8 ids
        ("",),                                 # empty
        ("has space",),                        # not an identifier
        ("9starts_digit",),                    # not an identifier
        ("dash-id",),                          # not an identifier
        ("é",),                                # non-ASCII
        ("a" * 65,),                           # >64 chars
        (42,),                                 # not a str
    ],
)
def test_shortcut_allowlist_validation(ids):
    with pytest.raises(ValueError):
        QaChannel(shortcut_ids=ids)


def test_record_shortcut_rejects_unknown_id():
    ch = QaChannel(shortcut_ids=("known",))
    with pytest.raises(ReportRejected):
        ch.record_shortcut("ptc", "unknown", provenance="catalog_callback")
    with pytest.raises(ValueError):
        ch.record_shortcut("bash", "known", provenance="")


# ---------------------------------------------------------------------------
# The opt-in shell wrapper, exercised through a real /bin/sh.
# ---------------------------------------------------------------------------


def _run_wrapper(bindir: Path, args: list[str]) -> subprocess.CompletedProcess:
    cmd = " ".join([str(bindir / REPORT_TOOL), *args])
    return subprocess.run(["/bin/sh", "-c", cmd], capture_output=True,
                          text=True, timeout=15)


def test_report_wrapper_real_shell(tmp_path):
    bindir = tmp_path / "bin"
    script = install_report_wrapper(bindir)
    assert script.name == REPORT_TOOL
    assert script.exists()

    # One single-line JSON arg -> exactly one marker line on stdout, no ack
    # (the wrapper must not claim host acceptance).
    proc = _run_wrapper(bindir, ["'{\"kind\":\"other\",\"detail\":\"d\"}'"])
    assert proc.returncode == 0
    assert proc.stdout.startswith(REPORT_MARKER)
    assert proc.stdout.count("\n") == 1
    assert ACK not in proc.stdout
    payload = proc.stdout[len(REPORT_MARKER):]
    assert json.loads(payload) == {"kind": "other", "detail": "d"}

    # The emitted line feeds consume_output as an agent_output allegation.
    ch = QaChannel()
    out = ch.consume_output("bash", proc.stdout)
    assert ACK in out
    assert ch.events[0]["provenance"] == "agent_output"


def test_report_wrapper_rejects_bad_arity_and_newlines(tmp_path):
    bindir = tmp_path / "bin"
    install_report_wrapper(bindir)

    for args in ([], ["'{}'", "'{}'"]):
        proc = _run_wrapper(bindir, args)
        assert proc.returncode == 2
        assert proc.stderr  # bounded, visible rejection
        assert REPORT_MARKER not in proc.stdout

    # A newline inside the argument is refused rather than smuggling extra
    # marker lines into the observation.
    proc = _run_wrapper(bindir, ["'{\"a\":1}\n{\"b\":2}'"])
    assert proc.returncode == 2
    assert REPORT_MARKER not in proc.stdout
    assert proc.stderr

    # The wrapper carries no durable sink path and no secrets.
    body = (bindir / REPORT_TOOL).read_text()
    assert "COTRAIN_QA_REPORT" in body
    assert "HOME" not in body and ".sqlite" not in body


# ---------------------------------------------------------------------------
# Concurrency.
# ---------------------------------------------------------------------------


def test_concurrent_callbacks_are_atomic():
    """Concurrent host callbacks from threads hit one atomic state: quotas hold,
    sequences stay unique and contiguous, export stays valid."""
    ch = QaChannel(shortcut_ids=("probe_scout",))
    errors: list[Exception] = []

    def work(i: int) -> None:
        arm = "bash" if i % 2 else "ptc"
        try:
            ch.submit(arm, kind="other", detail=f"d{i}")
        except ReportRejected:
            pass
        try:
            ch.record_shortcut(arm, "probe_scout", provenance="catalog_callback")
        except ReportRejected:
            pass
        ch.consume_output(arm, _report_line({"kind": "bogus", "detail": "x"}))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, range(60)))

    assert errors == []
    for arm in ("bash", "ptc"):
        reports = [e for e in ch.events
                   if e["arm"] == arm and e["type"] == "report"]
        assert len(reports) <= MAX_REPORTS_PER_ARM
        assert len([e for e in ch.events if e["arm"] == arm]) <= 32
    seqs = sorted(e["seq"] for e in ch.events)
    assert seqs == list(range(1, len(seqs) + 1))
    assert len(ch.export()) <= MAX_EXPORT_BYTES
