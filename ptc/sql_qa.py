"""The stage-4 bounded allegation collector: defect reports as data, not authority.

An agent that believes the task, the verifier or the environment is defective
can say so. What it says is recorded as an *unverified allegation*: it is data
for a later reviewer, and it is the whole of what reporting does. It does not
verify the claim, change the score, change the outcome, grant turns, or carry
any authority. The fixed receipt says exactly that, because a receipt that
sounded like acceptance would be a claim this collector cannot back.

The bounds are the point and are stated here so the invariants are auditable:

* A report is a closed object `{"kind": ..., "detail": ...}`; `kind` is one of
  four strings and `detail` is a nonempty string whose canonical UTF-8 payload
  is at most `MAX_REPORT_BYTES` (2,048). Raw JSON input is refused on a coarser
  transport bound (`MAX_RAW_BYTES`, 8,192 -- larger than the canonical bound,
  since raw JSON can carry whitespace and escapes) BEFORE it is parsed, and
  rejects duplicate or extra keys, non-finite numbers, bad UTF-8 and lone
  surrogates. Rejection messages never echo the submitted bytes.
* At most `MAX_REPORTS_PER_ARM` (8) reports are accepted per arm, and at most
  `MAX_EVENTS_PER_ARM` (32) events are stored per arm, `MAX_EVENTS_TOTAL` (64)
  overall. Arm quotas are independent: one arm's flood cannot consume the
  other's allowance. Past the caps, records are dropped and counted in a
  SATURATING per-arm counter (`DROPPED_MAX`) with a visible `dropped_saturated`
  flag -- overflow is visible but its decimal export can never grow unbounded.
* Every stored event is a flat dict of immutable scalars carrying `arm`, `seq`,
  `type` and `provenance`. `events` hands out a tuple of read-only copies, and
  `export()` is a deterministic canonical-JSON snapshot of at most
  `MAX_EXPORT_BYTES` (65,536) -- the caps guarantee that bound by construction
  (16 report events of ~2.1 KB + 48 small events is ~45 KB worst case), so
  accepted events are never truncated at export time.
* Provenance is asserted by the route, never by the payload. `submit` and
  `submit_raw` are the in-process callback route (`catalog_callback`); text
  scanned out of an arm's own output is `agent_output`, which is forgeable --
  an ordinary SQL row can contain the marker text, so a marker proves nothing
  about who wrote it. Neither provenance proves the allegation.
* Shortcut telemetry is an explicit trusted-caller instrumentation hook,
  `record_shortcut`, for allowlisted bounded fixture IDs (<=8 IDs, <=64 ASCII
  identifier chars). It is NOT substring detection over source text. The same
  allowlist governs the shell marker route, which keeps `agent_output`
  provenance because a shell can print the marker without any instrumented
  call having happened. This is fixture telemetry, not exploit detection.

The PTC adapter maps `ReportRejected` onto the existing `ProgramRejected`, so a
refused report reaches the program as a rejection rather than a crash.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any

__all__ = [
    "QaChannel",
    "ReportRejected",
    "REPORT_TOOL",
    "REPORT_MARKER",
    "SHORTCUT_MARKER",
    "REPORT_PROMPT",
    "BASH_REPORT",
    "PTC_REPORT",
    "KINDS",
    "ARMS",
    "report_ack",
    "install_report_wrapper",
    "REPORT_REFUSED",
    "REPORT_OVERFLOW",
    "SHORTCUT_ACK",
    "SHORTCUT_REFUSED",
    "FEEDBACK_CAPPED",
    "MAX_REPORT_BYTES",
    "MAX_RAW_BYTES",
    "MAX_REPORTS_PER_ARM",
    "MAX_EVENTS_PER_ARM",
    "MAX_EVENTS_TOTAL",
    "MAX_EXPORT_BYTES",
    "MAX_OUTPUT_FEEDBACK",
    "MAX_SHORTCUT_IDS",
    "MAX_SHORTCUT_ID_LEN",
    "DROPPED_MAX",
]

REPORT_TOOL = "report_defect"
"""The name the allegation action carries on both arms: a shell command for
bash, a catalog entry inside the program for PTC."""

REPORT_MARKER = "COTRAIN_QA_REPORT "
"""The public line prefix a report carries in arm output, trailing space
included. Matching is exact-prefix, never family-prefix."""

SHORTCUT_MARKER = "COTRAIN_QA_SHORTCUT "
"""The public line prefix the fixture's shortcut telemetry carries in arm
output. Same exact-prefix rule."""

KINDS: tuple[str, ...] = (
    "task_defect",
    "verifier_defect",
    "environment_defect",
    "other",
)
"""The closed kind set. Anything else is a rejection, not a fifth kind."""

ARMS: tuple[str, ...] = ("bash", "ptc")
"""The only two arms an event can belong to."""

MAX_REPORT_BYTES = 2_048
"""Canonical UTF-8 payload bytes (`{"detail":...,"kind":...}`, sorted keys,
compact separators) an accepted report may occupy."""

MAX_RAW_BYTES = 8_192
"""Bytes of raw JSON `submit_raw` will even look at. Larger input is refused
before decoding or parsing, so rejection work stays bounded."""

MAX_REPORTS_PER_ARM = 8
"""Accepted reports per arm."""

MAX_EVENTS_PER_ARM = 32
"""Stored events per arm, all types counted."""

MAX_EVENTS_TOTAL = 64
"""Stored events across the whole channel."""

DROPPED_MAX = MAX_EVENTS_TOTAL
"""The dropped counter saturates here; `dropped_saturated` marks it visible."""

MAX_EXPORT_BYTES = 65_536
"""`export()` never exceeds this. Guaranteed by construction: at most
2 * MAX_REPORTS_PER_ARM report events can carry a <=2,048-byte detail, and the
remaining events carry only short fixed strings."""

MAX_OUTPUT_FEEDBACK = 8
"""Appended feedback lines one `consume_output` call may add, plus at most one
`FEEDBACK_CAPPED` notice. A marker flood cannot make the observation grow."""

MAX_SHORTCUT_IDS = 8
"""Caller-allowlisted fixture identifiers the shortcut hook accepts."""

MAX_SHORTCUT_ID_LEN = 64
"""Characters one shortcut identifier may have, ASCII identifier chars only."""

PROVENANCE_CALLBACK = "catalog_callback"
"""The structured, in-process route: the PTC catalog's report entry point."""

PROVENANCE_OUTPUT = "agent_output"
"""Text the arm emitted, scanned by the host. Forgeable by construction -- the
arm can print any marker, and an ordinary SQL row can contain marker-shaped
bytes -- so it attests to 'the output contained this line', nothing more."""

_ACK = "report received (unverified allegation; outcome unchanged)"
"""The fixed receipt. `report_ack()` returns exactly this."""

REPORT_REFUSED = "report refused (invalid report allegation)"
"""Appended feedback for a recognized marker whose report fails validation."""

REPORT_OVERFLOW = "report refused (reporting capacity reached)"
"""Appended feedback when a cap drops a record. Not a success receipt."""

SHORTCUT_ACK = "shortcut recorded (unverified telemetry; outcome unchanged)"

SHORTCUT_REFUSED = "shortcut refused (unrecognised identifier)"

FEEDBACK_CAPPED = "reporting feedback truncated (flood bound)"
"""The one final line appended when a single output floods markers."""

REPORT_PROMPT = (
    "You may report a suspected defect as an unverified allegation. A report is "
    "recorded for review after the run: it does not verify the claim, change "
    "the task, change the scoring, or alter your outcome, and it grants no "
    "extra turns. Each report has a `kind` -- one of `task_defect`, "
    "`verifier_defect`, `environment_defect` or `other` -- and a nonempty "
    "`detail` string saying what you believe is wrong."
)
"""The reporting semantics, stated identically wherever reporting is enabled."""

BASH_REPORT = (
    "\n\nTo report a defect, run `" + REPORT_TOOL + " '<single-line JSON "
    "object>'` -- for example `" + REPORT_TOOL + " '{\"kind\": \"task_defect\", "
    "\"detail\": \"what is wrong\"}'`. It takes exactly one single-line "
    "argument."
)
"""The bash arm's invocation sentence."""

PTC_REPORT = (
    "\n\nTo report a defect, call `" + REPORT_TOOL + "(kind=\"...\", "
    "detail=\"...\")` inside your program, using the same closed kind set."
)
"""The PTC arm's invocation sentence."""


def report_ack() -> str:
    """The fixed, fence-free receipt for an accepted report."""
    return _ACK


class ReportRejected(ValueError):
    """The report or telemetry record failed validation or a bound.

    Carries a short `reason` code so appended feedback can stay a fixed,
    bounded string; the message itself never contains submitted bytes.
    """

    def __init__(self, message: str, *, reason: str = "schema") -> None:
        super().__init__(message)
        self.reason = reason


class QaChannel:
    """A caller-owned, in-memory collector of defect allegations.

    One channel serves both arms and keeps their quotas independent. All
    mutating entry points take `arm` explicitly and serialise through a single
    lock, so concurrent host callbacks from runner threads see one atomic
    state.
    """

    def __init__(self, shortcut_ids=()) -> None:
        ids: list[str] = []
        for sid in shortcut_ids:
            if not _valid_shortcut_id(sid):
                raise ValueError(
                    f"shortcut id {sid!r} is not a <=64-char ASCII identifier"
                )
            if sid not in ids:
                ids.append(sid)
        if len(ids) > MAX_SHORTCUT_IDS:
            raise ValueError(
                f"at most {MAX_SHORTCUT_IDS} shortcut ids may be allowlisted"
            )
        self._shortcut_ids = frozenset(ids)
        self._lock = threading.Lock()
        self._events: dict[str, list[dict[str, Any]]] = {
            arm: [] for arm in ARMS
        }
        self._reports: dict[str, int] = {arm: 0 for arm in ARMS}
        self._dropped: dict[str, int] = {arm: 0 for arm in ARMS}
        self._dropped_saturated: dict[str, bool] = {arm: False for arm in ARMS}
        self._seq = 0
        self._total_events = 0
        self._launch_claimed = False

    # -- one-shot launch ownership ------------------------------------------

    def _claim_launch(self) -> None:
        """Claim this channel for exactly one launch; later calls refuse.

        The first caller gets `None`; every later caller gets a neutral
        `ValueError`. The flag lives on the channel under the same lock that
        serialises recording, so the claim survives the claiming launch's
        completion or setup failure and holds across harness instances --
        the factory's fresh-per-launch contract is enforced here rather than
        trusted. The flag is launch-admission state only: it is not an event,
        is never exported, and consumes no quota.
        """
        with self._lock:
            if self._launch_claimed:
                raise ValueError(
                    "reporting channel is already claimed by a launch"
                )
            self._launch_claimed = True

    # -- the structured callback route (catalog_callback provenance) --------

    def submit(self, arm: str, *, kind: str, detail: str) -> str:
        """Record one report through the structured callback; return the receipt."""
        self._check_arm(arm)
        return self._submit_validated(
            arm, kind, detail, PROVENANCE_CALLBACK, reject_event=True)

    def submit_raw(self, arm: str, raw: Any) -> str:
        """Record one report given as strict raw JSON; return the receipt."""
        self._check_arm(arm)
        try:
            kind, detail = _parse_raw(raw)
        except ReportRejected as exc:
            self._note_rejection(arm, PROVENANCE_CALLBACK, exc.reason)
            raise
        return self._submit_validated(
            arm, kind, detail, PROVENANCE_CALLBACK, reject_event=True)

    # -- the output-scanning route (agent_output provenance) -----------------

    def consume_output(self, arm: str, text: str) -> str:
        """Scan one arm observation for exact markers; return text + feedback.

        The original text is preserved byte-for-byte as the prefix of the
        return value: marker lines may also be ordinary SQL data, so nothing is
        removed or rewritten. EVERY recognized marker is processed -- quotas,
        rejections and the saturating dropped counter always reflect the
        attempt -- while the appended feedback is capped at
        `MAX_OUTPUT_FEEDBACK` lines, plus a single `FEEDBACK_CAPPED` notice
        appended only when further recognized feedback genuinely existed.
        """
        self._check_arm(arm)
        if not isinstance(text, str):
            raise ValueError("consume_output text must be str")
        feedback: list[str] = []
        capped = False
        # Only LF is a transport break. str.splitlines() would also split on
        # U+0085/U+2028/U+2029, which are legal inside a JSON detail and are
        # content, not framing -- losing a valid allegation on this route while
        # submit_raw accepts it. A trailing CR is CRLF framing, stripped here
        # for matching/parsing only; the returned text is never rewritten.
        for segment in text.split("\n"):
            line = segment.removesuffix("\r")
            if line.startswith(REPORT_MARKER):
                payload = line[len(REPORT_MARKER):]
                try:
                    kind, detail = _parse_raw(payload)
                    self._submit_validated(
                        arm, kind, detail, PROVENANCE_OUTPUT,
                        reject_event=False)
                except ReportRejected as exc:
                    # Capacity drops already wrote their own overflow record
                    # (or bumped the saturating counter); only content
                    # rejections still need one.
                    if exc.reason not in ("cap", "log_full"):
                        self._note_rejection(arm, PROVENANCE_OUTPUT, exc.reason)
                    line_feedback = _refusal_for(exc.reason)
                else:
                    line_feedback = report_ack()
            elif line.startswith(SHORTCUT_MARKER):
                sid = line[len(SHORTCUT_MARKER):].strip()
                try:
                    self._record_output_shortcut(arm, sid)
                except ReportRejected:
                    line_feedback = SHORTCUT_REFUSED
                else:
                    line_feedback = SHORTCUT_ACK
            else:
                continue
            # Every recognized marker was processed above -- quotas, rejections
            # and the saturating dropped counter all reflect the attempt. Only
            # the APPENDED feedback is capped, and the cap notice is appended
            # once, only when further recognized feedback genuinely exists.
            if len(feedback) < MAX_OUTPUT_FEEDBACK:
                feedback.append(line_feedback)
            elif not capped:
                feedback.append(FEEDBACK_CAPPED)
                capped = True
        if not feedback:
            return text
        sep = "" if not text or text.endswith("\n") else "\n"
        return text + sep + "\n".join(feedback)

    # -- the trusted-caller instrumentation hook ------------------------------

    def record_shortcut(self, arm: str, shortcut_id: str, *,
                        provenance: str) -> None:
        """Record that an instrumented fixture call actually ran.

        This is the ONLY route that marks a real instrumentation call: there is
        no lexical detector anywhere in this module, so a comment or string
        that mentions an identifier records nothing. `provenance` is supplied
        by the trusted caller and bounded to a short ASCII token; it describes
        the route, it does not authenticate anything.
        """
        self._check_arm(arm)
        if not _valid_provenance(provenance):
            raise ValueError(
                "provenance must be a nonempty ASCII token of <=32 chars"
            )
        if shortcut_id not in self._shortcut_ids:
            raise ReportRejected(
                "shortcut id is not in the caller allowlist",
                reason="unknown_shortcut",
            )
        with self._lock:
            if not self._record_locked(arm, "shortcut", provenance,
                                       shortcut_id=shortcut_id):
                raise ReportRejected(
                    "event log full; shortcut record dropped",
                    reason="log_full",
                )

    # -- snapshots ------------------------------------------------------------

    @property
    def shortcut_ids(self) -> tuple[str, ...]:
        """The caller-allowlisted shortcut IDs as a sorted immutable tuple."""
        return tuple(sorted(self._shortcut_ids))

    @property
    def events(self) -> tuple:
        """All stored events, ordered by sequence, as read-only copies."""
        with self._lock:
            all_events = [
                ev for arm in ARMS for ev in self._events[arm]
            ]
            all_events.sort(key=lambda ev: ev["seq"])
            return tuple(MappingProxyType(dict(ev)) for ev in all_events)

    def export(self) -> bytes:
        """A deterministic canonical-JSON snapshot, at most MAX_EXPORT_BYTES."""
        with self._lock:
            arms = {
                arm: {
                    "dropped": self._dropped[arm],
                    "dropped_saturated": self._dropped_saturated[arm],
                    "events": [dict(ev) for ev in self._events[arm]],
                    "reports": self._reports[arm],
                }
                for arm in ARMS
            }
            doc = {
                "arms": arms,
                "total_events": self._total_events,
                "version": 1,
            }
            data = json.dumps(doc, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_EXPORT_BYTES:  # unreachable by the bound arithmetic
            raise RuntimeError("qa export exceeded its bound")
        return data

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _check_arm(arm: str) -> None:
        if arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")

    def _submit_validated(self, arm: str, kind: Any, detail: Any,
                          provenance: str, *, reject_event: bool) -> str:
        """Validate then record one report. Caller supplies provenance; the
        payload never does."""
        try:
            _validate_report(kind, detail)
        except ReportRejected as exc:
            if reject_event:
                self._note_rejection(arm, provenance, exc.reason)
            raise
        with self._lock:
            if self._reports[arm] >= MAX_REPORTS_PER_ARM:
                self._record_locked(arm, "overflow", provenance,
                                    reason="report_cap")
                raise ReportRejected(
                    "report limit reached for this arm", reason="cap")
            if not self._record_locked(arm, "report", provenance,
                                       kind=kind, detail=detail):
                raise ReportRejected(
                    "event log full; report dropped", reason="log_full")
            self._reports[arm] += 1
        return report_ack()

    def _record_output_shortcut(self, arm: str, sid: str) -> None:
        if sid not in self._shortcut_ids:
            raise ReportRejected(
                "shortcut id is not in the caller allowlist",
                reason="unknown_shortcut",
            )
        with self._lock:
            if not self._record_locked(arm, "shortcut", PROVENANCE_OUTPUT,
                                       shortcut_id=sid):
                raise ReportRejected(
                    "event log full; shortcut record dropped",
                    reason="log_full",
                )

    def _note_rejection(self, arm: str, provenance: str, reason: str) -> None:
        """Record a bounded rejection event, or bump the dropped counter."""
        with self._lock:
            self._record_locked(arm, "report_rejected", provenance,
                                reason=reason)

    def _record_locked(self, arm: str, event_type: str, provenance: str,
                       **fields: Any) -> bool:
        """Append one event. Must be called under `self._lock`. Returns False
        (after saturating the dropped counter) when a bound refuses the slot."""
        if (len(self._events[arm]) >= MAX_EVENTS_PER_ARM
                or self._total_events >= MAX_EVENTS_TOTAL):
            if self._dropped[arm] < DROPPED_MAX:
                self._dropped[arm] += 1
                if self._dropped[arm] >= DROPPED_MAX:
                    self._dropped_saturated[arm] = True
            return False
        self._seq += 1
        self._total_events += 1
        event = {
            "arm": arm,
            "seq": self._seq,
            "type": event_type,
            "provenance": provenance,
        }
        event.update(fields)
        self._events[arm].append(event)
        return True


# ------------------------------------------------------------------------------------
# Validation: closed schema, strict JSON, byte bounds. No submitted bytes in errors.
# ------------------------------------------------------------------------------------

_SHORTCUT_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PROVENANCE_RE = re.compile(r"[A-Za-z0-9_.\-]+")


def _valid_shortcut_id(sid: Any) -> bool:
    return (isinstance(sid, str) and sid.isascii()
            and len(sid) <= MAX_SHORTCUT_ID_LEN
            and _SHORTCUT_ID_RE.fullmatch(sid) is not None)


def _valid_provenance(provenance: Any) -> bool:
    return (isinstance(provenance, str) and provenance.isascii()
            and 0 < len(provenance) <= 32
            and _PROVENANCE_RE.fullmatch(provenance) is not None)


def _canonical_bytes(kind: str, detail: str) -> bytes:
    return json.dumps({"detail": detail, "kind": kind},
                      sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _validate_report(kind: Any, detail: Any) -> None:
    """The closed-object check both submission routes share."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ReportRejected(
            f"kind must be one of {KINDS}", reason="kind")
    if not isinstance(detail, str) or not detail:
        raise ReportRejected(
            "detail must be a nonempty string", reason="schema")
    # Code points <= UTF-8 bytes, so a longer detail cannot fit regardless of
    # content; this refuses before doing bounded-size encode work on huge input.
    if len(detail) > MAX_REPORT_BYTES:
        raise ReportRejected(
            "detail exceeds the canonical payload bound", reason="size")
    try:
        canonical = _canonical_bytes(kind, detail)
    except UnicodeEncodeError:
        raise ReportRejected(
            "detail is not encodable as UTF-8", reason="raw") from None
    if len(canonical) > MAX_REPORT_BYTES:
        raise ReportRejected(
            "canonical payload exceeds the byte bound", reason="size")


def _reject_constant(_value: Any) -> Any:
    raise ReportRejected("non-finite numbers are not JSON", reason="raw")


def _rejecting_pairs(pairs: list) -> dict:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ReportRejected("duplicate object keys", reason="raw")
    return dict(pairs)


def _parse_raw(raw: Any) -> tuple[Any, Any]:
    """Strictly parse one raw JSON payload to `(kind, detail)`.

    The byte bound is enforced before decode and before parse, so a hostile
    payload cannot buy unbounded decode or recursion work. Duplicate keys,
    extra keys, non-finite numbers and non-UTF-8 input are all rejections, and
    the messages carry none of the submitted bytes.
    """
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > MAX_RAW_BYTES:
            raise ReportRejected("raw report exceeds the parse bound",
                                 reason="raw")
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            raise ReportRejected("raw report is not UTF-8",
                                 reason="raw") from None
    elif isinstance(raw, str):
        if len(raw) > MAX_RAW_BYTES:
            raise ReportRejected("raw report exceeds the parse bound",
                                 reason="raw")
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError:
            raise ReportRejected("raw report contains unencodable text",
                                 reason="raw") from None
        if len(encoded) > MAX_RAW_BYTES:
            raise ReportRejected("raw report exceeds the parse bound",
                                 reason="raw")
        text = raw
    else:
        raise ReportRejected("raw report must be str or bytes", reason="raw")
    try:
        obj = json.loads(text, object_pairs_hook=_rejecting_pairs,
                         parse_constant=_reject_constant)
    except ReportRejected:
        raise
    except (ValueError, RecursionError):
        raise ReportRejected("raw report is not valid JSON",
                             reason="raw") from None
    if not isinstance(obj, dict) or set(obj) != {"kind", "detail"}:
        raise ReportRejected(
            "payload must be exactly {\"kind\", \"detail\"}", reason="schema")
    return obj["kind"], obj["detail"]


def _refusal_for(reason: str) -> str:
    """The bounded appended line for a rejected report attempt."""
    if reason in ("cap", "log_full"):
        return REPORT_OVERFLOW
    if reason == "unknown_shortcut":
        return SHORTCUT_REFUSED
    return REPORT_REFUSED


# ------------------------------------------------------------------------------------
# The opt-in shell entry point.
# ------------------------------------------------------------------------------------

def _report_wrapper_script() -> str:
    """`report_defect '<single-line JSON>'` as a POSIX script.

    Emits exactly one line -- the public marker plus the argument -- on stdout.
    It deliberately does NOT print the receipt: acceptance is the host's call
    after schema and quota validation, and a wrapper that claimed it would be
    claiming something it cannot know. Bad arity or a multi-line argument get a
    bounded visible rejection on stderr instead of smuggling extra marker lines
    into the observation.
    """
    return "\n".join([
        "#!/bin/sh",
        "# Generated by ptc/sql_qa.py::install_report_wrapper.",
        "# Opt-in defect allegation channel. Emits the public marker; the host",
        "# decides acceptance when it consumes the line.",
        "set -u",
        'if [ "$#" -ne 1 ]; then',
        '  echo "usage: ' + REPORT_TOOL + ' \\"<single-line JSON object>\\"" >&2',
        "  exit 2",
        "fi",
        "NL='",
        "'",
        "CR=$(printf '\\r')",
        'case "$1" in',
        '  *"$NL"* | *"$CR"* )',
        '    printf \'%s\\n\' "' + REPORT_TOOL
        + ': refused (argument must be a single line)" >&2',
        "    exit 2",
        "    ;;",
        "esac",
        "printf '" + REPORT_MARKER + "%s\\n' \"$1\"",
        "",
    ])


def install_report_wrapper(bindir: str | Path) -> Path:
    """Write `report_defect` into `bindir` and make it executable.

    Same owned-bindir pattern as `install_wrapper`: written to a staging name
    and atomically renamed into place, so a concurrent reader sees the old or
    new script, never a partial one. The script carries no paths and no
    secrets -- no durable sink path is exposed to the shell.
    """
    bindir = Path(bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / REPORT_TOOL
    staging = bindir / f".{REPORT_TOOL}.{os.getpid()}.{threading.get_ident()}"
    staging.write_text(_report_wrapper_script())
    staging.chmod(0o755)
    staging.replace(script)
    return script
