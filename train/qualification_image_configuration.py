"""Pure exact-declaration comparison, never effective-layer authenticity.

The correspondence layout below is explicitly synthetic/supported input, not a
claim that Modal emits it. Existing observations without it are UNKNOWN/refused.
No files, environment, SDK, callbacks, resolution or provider lookup are used.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
import hashlib
import json
from pathlib import PosixPath
import re
from types import MethodDescriptorType

from bench.task import SqlTask
from train import qualification_image_evidence as evidence
from train import qualification_image_plan as image
from train.native_qualification import AttemptBounds, FilePin, QualificationRequest


_DOMAIN = "qualification-effective-configuration-policy-v1"
_DECLARATION = "reviewed-effective-configuration-v1"
_OBSERVATION = "synthetic-effective-configuration-correspondence-v1"
_NAMES = ("receipt", "manifest", "config", "generated_recipe",
          "runtime_observation", "runtime_inventory")
_TASK_FIELDS = ("name", "question", "evidence", "gold_sql", "db_id", "db_path",
                "tier", "tier_source", "shape", "coarse_shape", "source")
_USD_FIELDS = ("total_ceiling_usd", "prior_usage_usd", "remaining_worst_case_usd")
_INTEGER_BOUNDS = ("lifetime_seconds", "output_bytes_per_phase",
                   "artifact_bytes", "retention_seconds")
_REQUEST_FIELDS = ("tasks", "db_root", "model_dir", "output_dir", "source_pins",
                   "database_pins", "runtime_inventory", "image_digest", "bounds")
_NODE_LIMIT = 16384
_ALLOCATION_LIMIT = 8388608
_require = evidence._require
_closed = evidence._closed


@dataclass(frozen=True)
class FrozenConfigurationPolicy:
    canonical: bytes
    sha256: str


@dataclass(frozen=True)
class ImageConfigurationConsistency:
    consistency: evidence.ImageEvidenceConsistency
    policy_sha256: str
    configuration_consistent: bool = field(default=True, init=False)
    provider_review: str = field(default="CLOSED", init=False)
    provider_identity_verified: bool = field(default=False, init=False)
    publisher_signature_verified: bool = field(default=False, init=False)
    effective_layers_authenticated: bool = field(default=False, init=False)
    runtime_verified: bool = field(default=False, init=False)
    image_verified: bool = field(default=False, init=False)
    build_authorized: bool = field(default=False, init=False)
    launch_authorized: bool = field(default=False, init=False)
    cost_approved: bool = field(default=False, init=False)


def _text(value, label):
    _require(type(value) is str and len(value) <= 8192 and "\x00" not in value,
             "invalid or NUL-containing " + label)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("invalid Unicode " + label) from error


def _path(value):
    _text(value, "path")
    _require(value.startswith("/") and (
        value == "/" or all(part not in ("", ".", "..") for part in value[1:].split("/"))
    ) and not any(ord(char) < 32 or ord(char) == 127 for char in value),
             "unsafe absolute path")


@dataclass
class _TraversalBudget:
    nodes: int = 0
    allocation_bytes: int = 0
    encoded_bytes: int = 0
    seen: set[int] = field(default_factory=set)

    def take(self, *, nodes=0, allocation=0, encoded=0):
        # Deterministic accounting units, not an assertion of measured Python RSS.
        _require(self.nodes + nodes <= _NODE_LIMIT, "aggregate snapshot node budget exceeded")
        _require(self.allocation_bytes + allocation <= _ALLOCATION_LIMIT,
                 "aggregate snapshot allocation budget exceeded")
        _require(self.encoded_bytes + encoded <= evidence._LIMIT,
                 "aggregate snapshot encoded byte budget exceeded")
        self.nodes += nodes
        self.allocation_bytes += allocation
        self.encoded_bytes += encoded


def _string_size(value):
    """Exact ensure_ascii JSON string size, without creating the encoded string."""
    size = 2
    for character in value:
        code = ord(character)
        if character in ('"', "\\", "\b", "\f", "\n", "\r", "\t"):
            size += 2
        elif code < 32 or 127 <= code <= 65535:
            size += 6
        elif code > 65535:
            size += 12
        else:
            size += 1
    return size


def _snapshot(value, budget, depth):
    """Bound work BEFORE allocation/descent; shared containers are unsupported."""
    _require(type(budget) is _TraversalBudget, "exact traversal budget required")
    _require(depth <= 32, "configuration nesting exceeds bound")
    budget.take(nodes=1, allocation=128)
    if value is None or type(value) is bool:
        budget.take(encoded=4 if value is None or value is True else 5)
        return value
    if type(value) is int:
        _require(value.bit_length() <= 256, "integer exceeds canonical serialization bound")
        budget.take(encoded=len(str(value)))
        return value
    if type(value) is str:
        _require(len(value) <= 8192, "invalid or NUL-containing string")
        budget.take(allocation=4 * len(value))
        _text(value, "string")
        budget.take(encoded=_string_size(value))
        return value
    _require(type(value) in (list, tuple, dict), "unsupported configuration primitive")
    count = len(value)
    _require(count <= 512, "configuration container exceeds bound")
    identity = id(value)
    _require(identity not in budget.seen, "shared or cyclic configuration container refused")
    budget.take(allocation=64 + 32 * count,
                encoded=2 + max(0, count - 1) + (count if type(value) is dict else 0))
    budget.seen.add(identity)
    if type(value) is dict:
        _require(all(type(key) is str for key in value), "exact configuration string keys required")
        result = {}
        for key, item in value.items():
            copied_key = _snapshot(key, budget, depth + 1)
            copied_item = _snapshot(item, budget, depth + 1)
            result[copied_key] = copied_item
        return result
    result = []
    for item in value:
        result.append(_snapshot(item, budget, depth + 1))
    return result


def _plain(value, depth=0):
    """Aggregate-budgeted immutable-leaf snapshot, no serialization hooks."""
    return _snapshot(value, _TraversalBudget(), depth)


class _CanonicalEncoder:
    """No whole-document dumps or oversized buffer, even without snapshot proof."""

    def __init__(self):
        self.buffer = bytearray()
        self.nodes = 0

    def append(self, fragment):
        _require(type(fragment) is bytes
                 and len(self.buffer) + len(fragment) <= evidence._LIMIT,
                 "canonical encoder byte budget exceeded")
        self.buffer.extend(fragment)

    def encode(self, value, depth=0):
        _require(depth <= 32 and self.nodes < _NODE_LIMIT,
                 "canonical encoder traversal budget exceeded")
        self.nodes += 1
        if value is None:
            self.append(b"null")
        elif type(value) is bool:
            self.append(b"true" if value else b"false")
        elif type(value) is int:
            _require(value.bit_length() <= 256, "integer exceeds canonical serialization bound")
            self.append(str(value).encode("ascii"))
        elif type(value) is str:
            _text(value, "canonical string")
            # Only a single <=8192-character exact string, never a container.
            self.append(json.dumps(value, ensure_ascii=True).encode("ascii"))
        elif type(value) is list:
            _require(len(value) <= 512, "canonical array exceeds bound")
            self.append(b"[")
            for index, item in enumerate(value):
                if index:
                    self.append(b",")
                self.encode(item, depth + 1)
            self.append(b"]")
        elif type(value) is dict:
            _require(len(value) <= 512 and all(type(key) is str for key in value),
                     "canonical object layout unsupported")
            for key in value:
                _text(key, "canonical key")
            self.append(b"{")
            for index, key in enumerate(sorted(value)):
                if index:
                    self.append(b",")
                self.encode(key, depth + 1)
                self.append(b":")
                self.encode(value[key], depth + 1)
            self.append(b"}")
        else:
            raise ValueError("unsupported canonical primitive")


def _canonical(value):
    snapshot = _plain(value)
    encoder = _CanonicalEncoder()
    encoder.encode(snapshot)
    return bytes(encoder.buffer)


def _concrete_path(value):
    # Check BEFORE str, fspath, property access, or any inherited Path operation.
    _require(type(value) is PosixPath,
             "unsupported request value type: exact concrete PosixPath required")

    def bounded_parts(parts):
        _require(type(parts) is list and len(parts) <= 512,
                 "unsupported or oversized Path storage")
        total = max(len(parts) - 1, 0)
        for part in parts:
            _require(type(part) is str, "unsupported Path component")
            total += len(part)
            _require(total <= 8192, "Path storage exceeds representation bound")
        return total

    # CPython 3.12 storage only. Neither _tail/parts properties nor __str__ may
    # run before the raw and already-cached representations are bounded.
    try:
        raw = object.__getattribute__(value, "_raw_paths")
    except AttributeError as error:
        raise ValueError("unsupported Path storage layout") from error
    bounded_parts(raw)
    cached = {}
    for name in ("_str", "_drv", "_root", "_tail_cached"):
        try:
            cached[name] = object.__getattribute__(value, name)
        except AttributeError:
            pass
    if "_str" in cached:
        _require(type(cached["_str"]) is str and len(cached["_str"]) <= 8192,
                 "unsupported or oversized cached Path string")
    parsed = sum(name in cached for name in ("_drv", "_root", "_tail_cached"))
    _require(parsed in (0, 3), "unsupported partial Path storage")
    if parsed:
        drive, root = cached["_drv"], cached["_root"]
        _require(type(drive) is str and type(root) is str,
                 "unsupported parsed Path storage")
        _require(len(drive) + len(root) <= 8192,
                 "Path storage exceeds representation bound")
        tail_size = bounded_parts(cached["_tail_cached"])
        _require(len(drive) + len(root) + tail_size <= 8192,
                 "Path storage exceeds representation bound")
    text = str(value)
    _path(text)
    return text


def _integer(value, minimum, maximum, label):
    _require(type(value) is int and minimum <= value <= maximum,
             "invalid bounded integer " + label)


def _request_pin(pin, *, retained=False):
    _require(type(pin) is FilePin, "exact FilePin required")
    _concrete_path(pin.path)
    _integer(pin.size, 1 if retained else 0,
             evidence._LIMIT if retained else 2 * 1024**3, "FilePin size")
    _text(pin.sha256, "FilePin digest")
    _require(evidence._SHA.fullmatch(pin.sha256) is not None, "invalid FilePin digest")


def _decimal_value(value):
    _require(type(value) is Decimal, "exact finite Decimal required")
    _require(all(type(getattr(Decimal, name)) is MethodDescriptorType
                 for name in ("is_finite", "as_tuple", "__sizeof__")),
             "unsupported Decimal implementation")
    _require(value.is_finite(), "exact finite Decimal required")
    # Exact C Decimal only. Bound backing storage before allocating its digit tuple.
    _require(Decimal.__sizeof__(value) <= 512, "Decimal coefficient storage exceeds bound")
    parts = value.as_tuple()
    _require(len(parts.digits) <= 64 and type(parts.exponent) is int
             and -64 <= parts.exponent <= 64, "Decimal representation exceeds bound")
    digits = list(parts.digits)
    exponent = parts.exponent
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = int("".join(str(digit) for digit in digits))
    sign = parts.sign if coefficient else 0
    exponent = exponent if coefficient else 0
    # Exact fixed-scale integer, no Decimal arithmetic/context/normalization hooks.
    units = coefficient * 10 ** (exponent + 64)
    if sign:
        units = -units
    return ({"kind": "decimal", "sign": sign, "coefficient": str(coefficient),
             "exponent": exponent}, units)


def _bounds_value(value):
    _require(type(value) is AttemptBounds, "exact nonmissing AttemptBounds required")
    _require(tuple(item.name for item in fields(AttemptBounds)) == _USD_FIELDS + _INTEGER_BOUNDS,
             "unsupported AttemptBounds layout")
    encoded = {}
    units = {}
    for name in _USD_FIELDS:
        encoded[name], units[name] = _decimal_value(getattr(value, name))
    _require(0 < units["total_ceiling_usd"] <= 25 * 10**64
             and units["prior_usage_usd"] >= 0 and units["remaining_worst_case_usd"] >= 0
             and units["prior_usage_usd"] + units["remaining_worst_case_usd"]
             <= units["total_ceiling_usd"], "invalid existing all-charge bounds")
    for name in _INTEGER_BOUNDS:
        member = getattr(value, name)
        _integer(member, 1, 1800 if name == "lifetime_seconds" else 2**63 - 1, name)
        encoded[name] = {"kind": "int", "value": member}
    return {"kind": "attempt_bounds", "fields": encoded}


def _task_value(value):
    _require(type(value) is SqlTask, "exact SqlTask required")
    _require(tuple(item.name for item in fields(SqlTask)) == _TASK_FIELDS,
             "unsupported SqlTask layout")
    encoded = {}
    for name in _TASK_FIELDS:
        member = getattr(value, name)
        _text(member, "SqlTask " + name)
        _require(name == "evidence" or member != "", "missing SqlTask field")
        encoded[name] = {"kind": "str", "value": member}
    _path(value.db_path)
    _require(value.tier in ("simple", "moderate", "challenging")
             and value.tier_source in ("annotated", "derived")
             and value.source in ("bird", "spider", "fixture"), "unsupported SqlTask labels")
    return {"kind": "sql_task", "fields": encoded}


def _request_value(value, depth=0):
    _require(depth <= 32, "request nesting exceeds bound")
    if type(value) is PosixPath:
        return {"kind": "absolute_path", "value": _concrete_path(value)}
    if type(value) is FilePin:
        _request_pin(value)
        return {"kind": "file_pin", "fields": {
            item.name: _request_value(getattr(value, item.name), depth + 1)
            for item in fields(FilePin)
        }}
    if type(value) is AttemptBounds:
        return _bounds_value(value)
    if type(value) is SqlTask:
        return _task_value(value)
    if type(value) is Decimal:
        return _decimal_value(value)[0]
    if type(value) is tuple:
        _require(len(value) <= 512, "request tuple exceeds bound")
        return {"kind": "tuple", "items": [_request_value(item, depth + 1) for item in value]}
    if value is None or type(value) in (str, bool, int):
        return {"kind": "none" if value is None else type(value).__name__,
                "value": _plain(value)}
    raise ValueError("unsupported request value type")


def _preflight(request, bundle, selected):
    """Shape/type/resource checks only, BEFORE all evidence hashing and parsing."""
    _require(type(request) is QualificationRequest, "QualificationRequest required")
    _require(tuple(item.name for item in fields(QualificationRequest)) == _REQUEST_FIELDS,
             "unsupported QualificationRequest layout")
    _require(type(request.tasks) is tuple,
             "unsupported request value type: tasks tuple required")
    _require(len(request.tasks) == 4, "exactly four typed synthetic/fixture tasks required")
    for task in request.tasks:
        _task_value(task)
    for name in ("db_root", "model_dir", "output_dir"):
        _concrete_path(getattr(request, name))
    for name in ("source_pins", "database_pins"):
        pins = getattr(request, name)
        _require(type(pins) is tuple,
                 "unsupported request value type: FilePin tuple required")
        _require(1 <= len(pins) <= 512 if name == "source_pins" else len(pins) == 4,
                 "invalid bounded request FilePin count")
        for pin in pins:
            _request_pin(pin)
    _request_pin(request.runtime_inventory)
    _bounds_value(request.bounds)
    _text(request.image_digest, "request image digest")
    _require(evidence._DIGEST.fullmatch(request.image_digest) is not None,
             "invalid request image digest")
    _require(type(bundle) is evidence.ImageEvidence, "ImageEvidence required")
    retained = [getattr(bundle, name) for name in _NAMES]
    for item in retained:
        _require(type(item) is evidence.RetainedBytes, "missing or invalid retained evidence")
        _request_pin(item.pin, retained=True)
        _require(type(item.payload) is bytes and len(item.payload) <= evidence._LIMIT,
                 "bounded immutable retained bytes required")
    _text(selected, "provider selection")
    _require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", selected) is not None,
             "explicit provider object selection required")
    return {name: _request_value(getattr(request, name)) for name in _REQUEST_FIELDS}, retained


def _binding(recipe, request, bundle, selected):
    snapshot, retained = _preflight(request, bundle, selected)
    image.validate_recipe(recipe)
    # Verify ALL six raw payload hashes before any configuration JSON is parsed.
    for item in retained:
        evidence._retained(item)
    return {
        "recipe_sha256": image.recipe_sha256(recipe),
        "provider_image_id": selected,
        "request": snapshot,
        "buffers": [
            {"name": name, "path": str(item.pin.path), "size": item.pin.size,
             "sha256": item.pin.sha256}
            for name, item in zip(_NAMES, retained)
        ],
    }


def _state(state):
    _closed(state, ("oci_config", "manifest_layers", "mount_targets", "injected_layers"),
            "reviewed effective state")
    _require(type(state["mount_targets"]) is list and state["mount_targets"] == []
             and type(state["injected_layers"]) is list and state["injected_layers"] == [],
             "unsupported effective mounts or injected layers")
    config = state["oci_config"]
    _closed(config, ("architecture", "os", "config", "rootfs", "history"),
            "effective OCI config")
    _require(config["architecture"] == "amd64" and config["os"] == "linux",
             "unsupported effective platform")
    process = config["config"]
    _closed(process, ("Env", "Entrypoint", "Cmd", "WorkingDir", "User"),
            "effective process config")
    env = process["Env"]
    _require(type(env) is list and len(env) <= 256, "bounded explicit Env required")
    keys = set()
    for entry in env:
        _text(entry, "Env")
        key, separator, _ = entry.partition("=")
        _require(separator == "=" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                 is not None, "unsupported Env assignment")
        _require(key not in keys, "duplicate Env key")
        keys.add(key)
    for name in ("Entrypoint", "Cmd"):
        command = process[name]
        _require(type(command) is list and len(command) <= 128,
                 "explicit ordered command array required")
        for argument in command:
            _text(argument, name)
            _require(argument != "", "empty command argument unsupported")
    _require(bool(process["Entrypoint"] or process["Cmd"]), "missing effective command")
    _path(process["WorkingDir"])
    _text(process["User"], "User")
    _require(re.fullmatch(r"(0|[1-9][0-9]{0,9})(:(0|[1-9][0-9]{0,9}))?",
                         process["User"]) is not None,
             "explicit numeric User required; name resolution unsupported")
    layers = state["manifest_layers"]
    _require(type(layers) is list and 1 <= len(layers) <= 128, "bounded layers required")
    for layer in layers:
        evidence._descriptor(layer, ("application/vnd.oci.image.layer.v1.tar+gzip",))
    rootfs = config["rootfs"]
    _closed(rootfs, ("type", "diff_ids"), "effective rootfs")
    _require(rootfs["type"] == "layers" and type(rootfs["diff_ids"]) is list
             and len(rootfs["diff_ids"]) == len(layers), "effective layer count mismatch")
    for digest in rootfs["diff_ids"]:
        _require(type(digest) is str and evidence._DIGEST.fullmatch(digest) is not None,
                 "invalid effective diff ID")
    history = config["history"]
    _require(type(history) is list and 1 <= len(history) <= 256,
             "explicit bounded history required")
    count = 0
    for entry in history:
        _closed(entry, ("created_by", "empty_layer"), "effective history")
        _text(entry["created_by"], "history command")
        _require(entry["created_by"] != "" and type(entry["empty_layer"]) is bool,
                 "ambiguous history layer semantics")
        count += not entry["empty_layer"]
    _require(count == len(layers), "history layer correspondence mismatch")


def freeze_configuration_policy(
    recipe, request, bundle, *, expected_provider_image_id, reviewed_configuration,
) -> FrozenConfigurationPolicy:
    """Snapshot explicit declaration; caller must review/pin returned SHA separately.

    Creating or pinning a policy proves no review took place. In particular, do
    not derive a declaration from arbitrary evidence and call it trusted.
    """
    # Reject unknown top-level keys BEFORE following any caller-owned value.
    _require(type(reviewed_configuration) is dict and len(reviewed_configuration) == 2,
             "invalid reviewed configuration declaration fields")
    _require(all(type(key) is str and key in ("schema", "state")
                 for key in reviewed_configuration),
             "invalid reviewed configuration declaration fields")
    _require(type(reviewed_configuration["schema"]) is str
             and reviewed_configuration["schema"] == _DECLARATION,
             "unsupported reviewed policy schema")
    binding = _binding(recipe, request, bundle, expected_provider_image_id)
    declaration = _plain(reviewed_configuration)
    _closed(declaration, ("schema", "state"), "reviewed configuration declaration")
    _require(declaration["schema"] == _DECLARATION, "unsupported reviewed policy schema")
    _state(declaration["state"])
    canonical = _canonical({"domain": _DOMAIN, "binding": binding, "reviewed": declaration})
    return FrozenConfigurationPolicy(canonical, hashlib.sha256(canonical).hexdigest())


def validate_image_configuration(
    recipe, request, bundle, *, expected_provider_image_id,
    policy: FrozenConfigurationPolicy, expected_policy_sha256: str,
) -> ImageConfigurationConsistency:
    """Primitive preflight, old consistency, then frozen configuration correspondence.

    All success means is consistency of supplied bytes under supplied policy.
    Missing effective observations remain UNKNOWN. No authorization is granted.
    """
    _preflight(request, bundle, expected_provider_image_id)
    consistency = evidence.validate_image_evidence(
        recipe, request, bundle, expected_provider_image_id=expected_provider_image_id,
    )
    _require(type(policy) is FrozenConfigurationPolicy and type(policy.canonical) is bytes
             and 0 < len(policy.canonical) <= evidence._LIMIT, "frozen policy required")
    _require(type(expected_policy_sha256) is str
             and evidence._SHA.fullmatch(expected_policy_sha256) is not None,
             "explicit expected policy digest required")
    _require(type(policy.sha256) is str and policy.sha256 == expected_policy_sha256
             == hashlib.sha256(policy.canonical).hexdigest(), "policy digest mismatch")
    binding = _binding(recipe, request, bundle, expected_provider_image_id)
    document = evidence._document(policy.canonical)
    _closed(document, ("domain", "binding", "reviewed"), "frozen configuration policy")
    _require(document["domain"] == _DOMAIN and _canonical(document) == policy.canonical,
             "noncanonical or unsupported policy domain")
    _require(_canonical(document["binding"]) == _canonical(binding),
             "post-plan input mutation or buffer binding mismatch")
    declaration = document["reviewed"]
    _closed(declaration, ("schema", "state"), "reviewed configuration declaration")
    _require(declaration["schema"] == _DECLARATION, "unsupported reviewed policy schema")
    _state(declaration["state"])
    config = evidence._document(bundle.config.payload)
    manifest = evidence._document(bundle.manifest.payload)
    receipt = evidence._document(bundle.receipt.payload)
    _require(manifest["mediaType"] == "application/vnd.oci.image.manifest.v1+json",
             "effective configuration supports OCI manifest only")
    actual = {
        "oci_config": config, "manifest_layers": manifest["layers"],
        "mount_targets": receipt["mount_targets"], "injected_layers": receipt["injected_layers"],
    }
    _state(actual)
    # Guard-loss witness 1: delete ONLY this equality, keep test assertions intact.
    _require(_canonical(actual) == _canonical(declaration["state"]),
             "effective configuration differs from reviewed policy")
    observed = evidence._document(bundle.runtime_inventory.payload)
    _closed(observed, ("schema", "config_sha256", "manifest_sha256",
                      "runtime_observation_sha256", "state"),
            "runtime effective correspondence UNKNOWN")
    _require(observed["schema"] == _OBSERVATION,
             "runtime effective correspondence UNKNOWN: unsupported layout")
    for name, retained in (("config", bundle.config), ("manifest", bundle.manifest),
                           ("runtime_observation", bundle.runtime_observation)):
        _require(observed[name + "_sha256"] == retained.pin.sha256,
                 "runtime effective correspondence digest mismatch")
    _state(observed["state"])
    # Guard-loss witness 2: delete ONLY this equality, keep test assertions intact.
    _require(_canonical(observed["state"]) == _canonical(actual),
             "runtime effective correspondence drift")
    return ImageConfigurationConsistency(consistency, policy.sha256)
