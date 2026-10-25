"""Future-only financially closed request workflow.

An externally reviewed whole-profile pin is the authority, not a self-digest.
No current provider charge schedule or USD receipt collector is supplied here.
Fixtures exercise local protocol only, never certify provider billing.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ptc.sql_isolation import (
    ExecutionProfile, SourcePin, execution_profile_sha256,
    build_execution_binding, installed_source_root,
)
from train.sql_pilot_assets import (
    MAX_BYTES, canonical_bytes, closed, digest, envelope_bytes, fsync_dir,
    integer, manifest_sha256, open_envelope, read_file, safe_path, sha,
    strict_json, text, validate_manifest, write_new,
)
from train.sql_pilot_budget import BudgetConfig, BudgetLedger

ENDPOINT = "https://vyceai.com/v1/chat/completions"
MAX_CONTEXT_BYTES = 131072
MAX_PROGRAM_BYTES = 65536
DEADLINE_S = 120
SYSTEM = (
    "Solve the supplied single-user-table ROWCOUNT task. Submit exactly one action "
    "using submit. A program has catalog access but receives no question argument; "
    "print FINAL_SQL: followed by the SQL answer. Use only an explicitly advertised "
    "approved skill reference, or supply a direct program. Do not request another turn."
)
DESCRIPTION = "ROWCOUNT candidate qualified on four distinct databases; use only within its advertised scope."


class FinancialBlocked(RuntimeError):
    """No safe next request. Unknown exposure remains fully reserved."""


class ModelActionError(ValueError):
    """One consumed model attempt, no action execution/fallback/repair."""

    telemetry = None


class ProtocolStop(ModelActionError):
    """Provider tool protocol unsupported or delivery/result unusable. STOP."""


def _pins(pins):
    if type(pins) is not tuple or not pins or any(type(x) is not SourcePin for x in pins):
        raise TypeError("nonempty concrete evidence pin tuple required")
    if len({x.path for x in pins}) != len(pins):
        raise ValueError("duplicate evidence path")
    for pin in pins:
        pin.__post_init__()


@dataclass(frozen=True, slots=True)
class Charge:
    name: str
    unit: str
    rate_numerator_micros: int
    rate_denominator: int
    max_units_per_request: int

    def __post_init__(self):
        text(self.name, maximum=256)
        text(self.unit, maximum=256)
        integer(self.rate_numerator_micros)
        integer(self.rate_denominator, minimum=1)
        integer(self.max_units_per_request, minimum=1)
        integer((self.rate_numerator_micros * self.max_units_per_request
                 + self.rate_denominator - 1) // self.rate_denominator)


@dataclass(frozen=True, slots=True)
class Authorization:
    run_id: str
    manifest_sha256: str
    execution_profile_sha256: str
    budget_directory: str
    limit_usd_micros: int
    request_limit: int

    def __post_init__(self):
        text(self.run_id, maximum=64)
        sha(self.manifest_sha256)
        sha(self.execution_profile_sha256)
        if str(safe_path(Path(text(self.budget_directory)))) != self.budget_directory:
            raise ValueError("canonical budget path string required")
        if (type(self.limit_usd_micros) is not int or self.limit_usd_micros != 50_000_000
                or type(self.request_limit) is not int or self.request_limit != 25):
            raise ValueError("authorization must be exact $50 / 25 requests")


@dataclass(frozen=True, slots=True)
class BillingProfile:
    provider: str
    endpoint: str
    model: str
    valid_from: int
    valid_until: int
    authority_ref: str
    evidence: tuple[SourcePin, ...]
    charges: tuple[Charge, ...]
    settlement_mode: str
    authorization: Authorization
    receipt_directory: str

    def __post_init__(self):
        for name in ("provider", "model", "authority_ref"):
            text(getattr(self, name), maximum=256)
        if type(self.endpoint) is not str or self.endpoint != ENDPOINT:
            raise ValueError("only the explicitly approved endpoint is permitted")
        integer(self.valid_from)
        integer(self.valid_until, minimum=self.valid_from + 1)
        _pins(self.evidence)
        if type(self.charges) is not tuple or not self.charges or len(self.charges) > 256:
            raise ValueError("complete bounded nonempty charge classes required")
        for charge in self.charges:
            if type(charge) is not Charge:
                raise TypeError("concrete Charge required")
            charge.__post_init__()
        if len({x.name for x in self.charges}) != len(self.charges):
            raise ValueError("duplicate charge class")
        if type(self.authorization) is not Authorization:
            raise TypeError("concrete authorization required")
        self.authorization.__post_init__()
        if self.settlement_mode != "authoritative_receipt_only":
            raise ValueError("authoritative USD receipts required")
        if str(safe_path(Path(text(self.receipt_directory)))) != self.receipt_directory:
            raise ValueError("canonical receipt path string required")
        # A zero/absurd maximum does not establish a usable future paid path.
        integer(maximum_charge(self), minimum=1)


def maximum_charge(profile: BillingProfile) -> int:
    return integer(sum((x.rate_numerator_micros * x.max_units_per_request
                        + x.rate_denominator - 1) // x.rate_denominator for x in profile.charges))


def billing_profile_bytes(profile: BillingProfile) -> bytes:
    if type(profile) is not BillingProfile:
        raise TypeError("concrete billing profile required")
    profile.__post_init__()
    return envelope_bytes("sql_pilot_billing_profile", asdict(profile))


def _pins_from(value):
    if type(value) is not list:
        raise TypeError("evidence array required")
    result = tuple(SourcePin(**closed(x, ("path", "sha256"))) for x in value)
    _pins(result)
    return result


def billing_profile_from_bytes(raw: bytes) -> BillingProfile:
    obj = dict(closed(open_envelope(raw, "sql_pilot_billing_profile"),
                      tuple(f.name for f in fields(BillingProfile))))
    obj["evidence"] = _pins_from(obj["evidence"])
    if type(obj["charges"]) is not list:
        raise TypeError("charges array required")
    obj["charges"] = tuple(Charge(**closed(x, tuple(f.name for f in fields(Charge)))) for x in obj["charges"])
    obj["authorization"] = Authorization(**closed(obj["authorization"], tuple(f.name for f in fields(Authorization))))
    return BillingProfile(**obj)


def validate_billing_profile(profile: BillingProfile, *, now: int | None = None):
    billing_profile_bytes(profile)
    current = int(time.time()) if now is None else integer(now)
    if not profile.valid_from <= current < profile.valid_until:
        raise FinancialBlocked("billing approval is not current")


def _evidence(pins, root):
    safe_path(root, exists=True, directory=True)
    _pins(pins)
    for pin in pins:
        path = root.joinpath(*pin.path.split("/"))
        if not path.is_relative_to(root) or digest(read_file(path)) != pin.sha256:
            raise FinancialBlocked("authoritative evidence pin mismatch")


def load_billing_profile(path: Path, *, approval_sha256: str) -> BillingProfile:
    raw = read_file(path)
    if sha(approval_sha256) != digest(raw):
        raise FinancialBlocked("external whole-profile approval does not match")
    profile = billing_profile_from_bytes(raw)
    validate_billing_profile(profile)
    _evidence(profile.evidence, path.parent)
    return profile


def billing_config(profile: BillingProfile, approval_sha256: str) -> BudgetConfig:
    if digest(billing_profile_bytes(profile)) != sha(approval_sha256):
        raise FinancialBlocked("whole approved envelope required")
    # Zero is permitted only as an authoritative actual receipt, never as an
    # unsupported zero reservation; maximum_charge is separately positive.
    return BudgetConfig(profile.authorization.run_id, profile.model, approval_sha256,
                        profile.authority_ref, zero_charge_authorized=True)


def authorize(profile, approval_sha256, *, manifest, execution_profile, budget_dir):
    validate_billing_profile(profile)
    validate_manifest(manifest)
    if type(execution_profile) is not ExecutionProfile:
        raise TypeError("concrete execution profile required")
    authorization = profile.authorization
    if (authorization.run_id != manifest.run_id
            or authorization.manifest_sha256 != manifest_sha256(manifest)
            or authorization.execution_profile_sha256 != execution_profile_sha256(execution_profile)
            or str(safe_path(budget_dir)) != authorization.budget_directory):
        raise FinancialBlocked("run, assets, execution profile or budget path not authorized")
    if (Path(profile.receipt_directory) == budget_dir
            or Path(profile.receipt_directory).is_relative_to(budget_dir)
            or budget_dir.is_relative_to(Path(profile.receipt_directory))):
        raise FinancialBlocked("budget and receipt storage must be separate")
    return billing_config(profile, approval_sha256)


def init_budget(*, billing_profile_path, approval_sha256, manifest, execution_profile, budget_dir):
    profile = load_billing_profile(billing_profile_path, approval_sha256=approval_sha256)
    config = authorize(profile, approval_sha256, manifest=manifest,
                       execution_profile=execution_profile, budget_dir=budget_dir)
    # This is the only creation path. The committed primitive refuses replacement.
    return BudgetLedger.create(str(budget_dir), config)


def load_receipt(profile, request_id, request_sha256, response_sha256, *, evidence_root):
    try:
        path = Path(profile.receipt_directory) / (digest(request_id.encode("utf-8")) + ".json")
        raw = read_file(path)
        obj = closed(open_envelope(raw, "sql_pilot_billing_receipt"), (
            "run_id", "request_id", "model_request_sha256", "model_response_sha256",
            "currency", "actual_charge_usd_micros", "authority_ref", "evidence"))
        if (obj["run_id"] != profile.authorization.run_id or obj["request_id"] != request_id
                or obj["model_request_sha256"] != sha(request_sha256)
                or obj["model_response_sha256"] != sha(response_sha256)
                or obj["currency"] != "USD" or obj["authority_ref"] != profile.authority_ref):
            raise ValueError("receipt identity mismatch")
        actual = integer(obj["actual_charge_usd_micros"])
        pins = _pins_from(obj["evidence"])
        _evidence(pins, evidence_root)
        return actual, digest(raw)
    except (ValueError, TypeError, OSError) as exc:
        raise FinancialBlocked("missing or unapproved authoritative receipt; reservation HELD") from None


def submit_tool():
    return {"type": "function", "function": {"name": "submit",
        "description": "Submit one direct program or one exact advertised approved skill.",
        "strict": True, "parameters": {"type": "object", "additionalProperties": False,
            "properties": {"kind": {"type": "string", "enum": ["program", "approved_skill"]},
                           "program": {"type": "string"}, "skill_id": {"type": "string"},
                           "promotion_sha256": {"type": "string"}},
            "required": ["kind", "program", "skill_id", "promotion_sha256"]}}}


def build_request(model: str, payload: dict) -> bytes:
    text(model, maximum=256)
    if type(payload) is not dict:
        raise TypeError("canonical user object required")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": canonical_bytes(payload).decode("utf-8")}]
    tools = [submit_tool()]
    if len(canonical_bytes({"messages": messages, "tools": tools})) > MAX_CONTEXT_BYTES:
        raise ValueError("messages+tools exceed 131072 UTF-8 bytes; no truncation")
    return canonical_bytes({"model": model, "messages": messages, "tools": tools,
                            "tool_choice": {"type": "function", "function": {"name": "submit"}},
                            "temperature": 0, "top_p": 1, "n": 1, "max_tokens": 2048,
                            "stream": False, "parallel_tool_calls": False})


@dataclass(frozen=True, slots=True)
class PilotAction:
    kind: str
    program: str
    skill_id: str
    promotion_sha256: str

    def __post_init__(self):
        for name in ("kind", "program", "skill_id", "promotion_sha256"):
            text(getattr(self, name), nonempty=False)
        if self.kind == "program":
            text(self.program, maximum=MAX_PROGRAM_BYTES)
            if not self.program.strip() or self.skill_id != "" or self.promotion_sha256 != "":
                raise ValueError("direct program requires empty reference fields")
        elif self.kind == "approved_skill":
            if self.program != "":
                raise ValueError("approved skill requires exactly empty program")
            text(self.skill_id)
            sha(self.promotion_sha256)
        else:
            raise ValueError("unknown submission kind")


def _provider_arguments(raw: bytes) -> str:
    try:
        obj = strict_json(raw)
        if type(obj) is not dict or type(obj.get("choices")) is not list or len(obj["choices"]) != 1:
            raise ProtocolStop("one complete tool choice required")
        choice = obj["choices"][0]
        if type(choice) is not dict or choice.get("finish_reason") != "tool_calls":
            raise ProtocolStop("forced tool protocol not established")
        message = choice.get("message")
        if type(message) is not dict or message.get("role") != "assistant":
            raise ProtocolStop("assistant tool message required")
        calls = message.get("tool_calls")
        if type(calls) is not list or len(calls) != 1:
            raise ProtocolStop("exactly one submit call required")
        call = closed(calls[0], ("id", "type", "function"))
        text(call["id"], maximum=256)
        function = closed(call["function"], ("name", "arguments"))
        if call["type"] != "function" or function["name"] != "submit":
            raise ProtocolStop("unknown tool or call type")
        return text(function["arguments"])
    except ProtocolStop:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ProtocolStop("malformed outer provider JSON/envelope; STOP") from None


def parse_response(raw: bytes, *, library, program_only=False) -> PilotAction:
    arguments = _provider_arguments(raw)
    try:
        action = PilotAction(**closed(strict_json(arguments.encode("utf-8")),
                                      ("kind", "program", "skill_id", "promotion_sha256")))
        if action.kind == "approved_skill":
            if program_only or not any(type(entry) is dict and
                    entry.get("skill_id") == action.skill_id and
                    entry.get("promotion_sha256") == action.promotion_sha256 for entry in library):
                raise ModelActionError("reference not in the exact advertised library")
        return action
    except ModelActionError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ModelActionError("malformed submit action; no fallback or repair") from None


_CREDENTIAL_SCAN_WORK_BYTES = 64 * 1024 * 1024
_CREDENTIAL_SCAN_NODES = 65536
_CREDENTIAL_SCAN_DEPTH = 32


def _reject_credential(value, key, *, raw=None):
    """Inspect actual strings, never repr. Decode bounded JSON-in-JSON.

    Ambiguous JSON-looking strings/work exhaustion fail closed. This is not a
    general decoder or a transformation of persisted/sent program bytes.
    """
    if raw is not None and key.encode("utf-8") in raw:
        raise FinancialBlocked("credential collision/echo suppressed; reservation HELD")
    pending = [(value, 0)]
    work = nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > _CREDENTIAL_SCAN_NODES or depth > _CREDENTIAL_SCAN_DEPTH:
            raise FinancialBlocked("credential inspection bound exceeded; reservation HELD")
        if type(item) is str:
            work += len(item.encode("utf-8", "strict"))
            if work > _CREDENTIAL_SCAN_WORK_BYTES:
                raise FinancialBlocked("credential inspection work exceeded; reservation HELD")
            if key in item:
                raise FinancialBlocked("credential collision/echo suppressed; reservation HELD")
            stripped = item.lstrip()
            if stripped.startswith(("{", "[", '"')):
                try:
                    nested = strict_json(item.encode("utf-8", "strict"))
                except (ValueError, TypeError, UnicodeError):
                    if "\\" in item:
                        raise FinancialBlocked("credential inspection uncertain; reservation HELD") from None
                    continue
                pending.append((nested, depth + 1))
        elif type(item) is dict:
            if nodes + len(pending) + 2 * len(item) > _CREDENTIAL_SCAN_NODES:
                raise FinancialBlocked("credential inspection node bound exceeded; reservation HELD")
            for name, child in item.items():
                pending.extend(((name, depth + 1), (child, depth + 1)))
        elif type(item) is list:
            if nodes + len(pending) + len(item) > _CREDENTIAL_SCAN_NODES:
                raise FinancialBlocked("credential inspection node bound exceeded; reservation HELD")
            pending.extend((child, depth + 1) for child in item)
        elif item is not None and type(item) not in (int, float, bool):
            raise FinancialBlocked("credential inspection unsupported; reservation HELD")


def _deadline_available():
    if threading.current_thread() is not threading.main_thread():
        raise FinancialBlocked("absolute deadline requires the main POSIX thread")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise FinancialBlocked("preexisting timer must not be stolen")


@contextmanager
def absolute_deadline(seconds=DEADLINE_S):
    _deadline_available()
    original = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise FinancialBlocked("absolute request deadline; reservation HELD")
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original)


def _read_credential():
    # Deliberately late, only following durable dispatch claim and both opt-ins.
    key = os.environ.get("VYCEAI_API_KEY")
    if type(key) is not str or not key or len(key.encode("utf-8")) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise FinancialBlocked("credential unavailable; reservation HELD")
    return key


def _httpx_post(endpoint, request: bytes, key: str):
    """One installed HTTPX SDK attempt. Low-level endpoint is for loopback tests.

    Production invokes only ENDPOINT, after profile/approval/ledger admission.
    The surrounding absolute_deadline includes reading and cleanup, preventing
    per-socket timeout resets/slowloris from extending the total deadline.
    """
    import httpx
    try:
        transport = httpx.HTTPTransport(retries=0, verify=True, trust_env=False)
        with httpx.Client(transport=transport, verify=True, trust_env=False,
                          follow_redirects=False, timeout=DEADLINE_S) as client:
            with client.stream("POST", endpoint, content=request,
                               headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                        "Accept-Encoding": "identity"}) as response:
                body = bytearray()
                for chunk in response.iter_raw():
                    if len(body) + len(chunk) > MAX_BYTES:
                        raise FinancialBlocked("HTTP body exceeds 8 MiB; reservation HELD")
                    body.extend(chunk)
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise FinancialBlocked("encoded HTTP body unsupported; reservation HELD")
                return response.status_code, bytes(body)
    except FinancialBlocked:
        raise
    except Exception:
        # Never preserve HTTPX exception/header/body text, which may echo auth.
        raise FinancialBlocked("HTTP transport uncertain; reservation HELD") from None


def _http_attempt(request, key):
    return _httpx_post(ENDPOINT, request, key)


def _telemetry(raw, *, request_id, request_sha256, latency_ms, charge):
    result = {"request_id": request_id, "request_sha256": request_sha256,
              "response_sha256": digest(raw), "latency_ms": latency_ms,
              "actual_charge_usd_micros": charge, "usage": None, "reported_model": None,
              "effective_version": "UNKNOWN", "cache_protocol": "UNKNOWN"}
    try:
        obj = strict_json(raw)
        if type(obj) is dict:
            if type(obj.get("model")) is str:
                result["reported_model"] = text(obj["model"], maximum=1024)
            usage = obj.get("usage")
            if type(usage) is dict:
                # Keep documented observations, never infer billable units.
                result["usage"] = {name: integer(usage[name]) for name in (
                    "prompt_tokens", "completion_tokens", "total_tokens") if name in usage}
    except (TypeError, ValueError):
        pass
    return result


@dataclass(frozen=True, slots=True)
class ModelReply:
    action: PilotAction
    telemetry: dict


class PilotAPI:
    def __init__(self, *, billing_profile_path, approval_sha256, manifest,
                 execution_profile, budget_dir, output_dir,
                 allow_execution=False, allow_model_requests=False):
        if allow_execution is not True or allow_model_requests is not True:
            raise ValueError("both execution and model opt-ins must be literal True")
        self.profile_path = safe_path(billing_profile_path, exists=True)
        self.approval = sha(approval_sha256)
        self.manifest = manifest
        self.execution_profile = execution_profile
        self.budget_dir = safe_path(budget_dir, exists=True, directory=True)
        self.output_dir = safe_path(output_dir, exists=True, directory=True)
        self.profile, self.ledger = self._admit()

    def _admit(self):
        profile = load_billing_profile(self.profile_path, approval_sha256=self.approval)
        config = authorize(profile, self.approval, manifest=self.manifest,
                           execution_profile=self.execution_profile, budget_dir=self.budget_dir)
        ledger = BudgetLedger.open(str(self.budget_dir), config)  # NEVER create/reset
        snapshot = ledger.snapshot()
        if snapshot.status != "active" or any(x.state != "settled" for x in snapshot.requests):
            raise FinancialBlocked("unsettled or halted ledger; no replay")
        build_execution_binding(self.execution_profile, source_root=installed_source_root())
        return profile, ledger

    def request(self, request_id, payload, *, library, program_only=False):
        text(request_id, maximum=128)
        if not request_id.startswith(self.manifest.run_id + ":"):
            raise FinancialBlocked("request ID must bind this run")
        profile, ledger = self._admit()
        request = build_request(profile.model, payload)
        _deadline_available()  # fail before reserve/claim/key on unsupported thread/timer
        request_sha = digest(request)
        stem = digest(request_id.encode("utf-8"))
        ledger.reserve(request_id, maximum_charge(profile))
        ledger.claim_dispatch(request_id)
        started = time.monotonic_ns()
        key = None
        try:
            with absolute_deadline():
                key = _read_credential()
                _reject_credential(payload, key)
                _reject_credential(strict_json(request), key, raw=request)
                # Credential admission follows durable claim, but precedes any
                # credential-bearing artifact. Safe exact bytes precede HTTP.
                write_new(self.output_dir / (stem + ".request.json"), request)
                status, raw = _http_attempt(request, key)
                if type(raw) is not bytes or len(raw) > MAX_BYTES:
                    raise FinancialBlocked("bounded complete HTTP body required; reservation HELD")
                # Suppress credential echoes, including escaped JSON strings.
                if key.encode("utf-8") in raw:
                    raise FinancialBlocked("credential echo suppressed; reservation HELD")
                try:
                    decoded = strict_json(raw)
                except (ValueError, TypeError):
                    decoded = None
                    outer_decodable = False
                else:
                    outer_decodable = True
                    _reject_credential(decoded, key, raw=raw)
        except FinancialBlocked:
            raise
        except Exception:
            raise FinancialBlocked("request uncertain; reservation HELD") from None
        finally:
            key = None
        elapsed = (time.monotonic_ns() - started) // 1_000_000
        if outer_decodable:
            write_new(self.output_dir / (stem + ".response.json"), raw)
        else:
            # Never save undecodable raw bytes that might recover a credential.
            write_new(self.output_dir / (stem + ".response-rejection.json"),
                      envelope_bytes("sql_pilot_response_rejection", {
                          "request_id": request_id, "response_sha256": digest(raw),
                          "reason": "undecodable_outer_json"}))
        # Reload the approved evidence before accepting external settlement.
        load_billing_profile(self.profile_path, approval_sha256=self.approval)
        charge, receipt_sha = load_receipt(profile, request_id, request_sha, digest(raw),
                                          evidence_root=self.profile_path.parent)
        settlement = ledger.settle(request_id, charge, receipt_sha)
        if settlement.halted:
            raise FinancialBlocked("actual charge exceeded reservation; ledger durably HALTED")
        telemetry = _telemetry(raw, request_id=request_id, request_sha256=request_sha,
                               latency_ms=elapsed, charge=charge)
        write_new(self.output_dir / (stem + ".receipt.json"),
                  envelope_bytes("sql_pilot_request_record", telemetry))
        try:
            if status != 200:
                raise ProtocolStop("provider HTTP protocol unsuccessful; STOP")
            action = parse_response(raw, library=library, program_only=program_only)
            return ModelReply(action, telemetry)
        except ModelActionError as error:
            error.telemetry = telemetry
            raise
