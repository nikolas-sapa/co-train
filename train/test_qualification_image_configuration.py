"""SYNTHETIC six-buffer cases. Source-only worker has NOT run these tests."""

import builtins
from contextlib import contextmanager
from dataclasses import fields, replace
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bench.task import SqlTask
from train import qualification_image_configuration as configuration
from train import qualification_image_evidence as evidence
from train import test_qualification_image_evidence as original
from train.native_qualification import AttemptBounds, FilePin


def _copy(value):
    return json.loads(original._json(value))


def _reviewed():
    return {
        "schema": "reviewed-effective-configuration-v1",
        "state": {
            "oci_config": {
                "architecture": "amd64", "os": "linux",
                "config": {
                    "Env": ["PATH=/usr/local/bin:/usr/bin:/bin", "PYTHON_VERSION=3.12.13"],
                    "Entrypoint": [], "Cmd": ["python3"],
                    "WorkingDir": "/", "User": "0",
                },
                "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "c" * 64]},
                "history": [{"created_by": "SYNTHETIC reviewed base layer",
                             "empty_layer": False}],
            },
            "manifest_layers": [{
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": "sha256:" + "d" * 64, "size": 123,
            }],
            "mount_targets": [], "injected_layers": [],
        },
    }


def _rebind(recipe, request, bundle):
    """Rehash synthetic bytes, not provider attestation."""
    manifest = json.loads(bundle.manifest.payload)
    manifest["config"]["digest"] = "sha256:" + bundle.config.pin.sha256
    manifest["config"]["size"] = bundle.config.pin.size
    bundle = replace(bundle, manifest=original._retained("manifest.json", original._json(manifest)))
    receipt = json.loads(bundle.receipt.payload)
    receipt["runtime_digest"] = "sha256:" + bundle.manifest.pin.sha256
    receipt["runtime_inventory_sha256"] = bundle.runtime_inventory.pin.sha256
    receipt["runtime_observation_sha256"] = bundle.runtime_observation.pin.sha256
    bundle = replace(bundle, receipt=original._retained("receipt.json", original._json(receipt)))
    request = replace(request, image_digest=receipt["runtime_digest"],
                      runtime_inventory=bundle.runtime_inventory.pin)
    return recipe, request, bundle


def _fixture(*, actual=None, observed=None, inventory=None):
    state = _copy(_reviewed()["state"] if actual is None else actual)
    recipe, request, bundle = original._fixture(
        config_changes=state["oci_config"],
        manifest_changes={"layers": state["manifest_layers"]},
        receipt_changes={"mount_targets": state["mount_targets"],
                         "injected_layers": state["injected_layers"]},
    )
    # Fully typed but entirely SYNTHETIC. No query/database/provenance is executed
    # or asserted. Unlike the old leaf fixture, bounds/tasks are never placeholders.
    tasks = tuple(SqlTask(
        name=name, question="SYNTHETIC inert question " + name, evidence="SYNTHETIC",
        gold_sql="SYNTHETIC_INERT_SQL_TEXT_" + name, db_id=name,
        db_path="/synthetic/data/" + name + "/" + name + ".sqlite",
        tier="simple", tier_source="derived", shape="fixture-select",
        coarse_shape="fixture-select", source="fixture",
    ) for name in ("first", "second", "third", "fourth"))
    request = replace(
        request, tasks=tasks,
        source_pins=(FilePin(Path("/synthetic/source/train/native_training.py"), 7, "a" * 64),),
        database_pins=tuple(FilePin(Path(task.db_path), 1, "b" * 64) for task in tasks),
        bounds=AttemptBounds(
            Decimal("12"), Decimal("0"), Decimal("12"), 1800,
            1024 * 1024, 64 * 1024 * 1024, 60,
        ),
    )
    correspondence = {
        "schema": "synthetic-effective-configuration-correspondence-v1",
        "config_sha256": bundle.config.pin.sha256,
        "manifest_sha256": bundle.manifest.pin.sha256,
        "runtime_observation_sha256": bundle.runtime_observation.pin.sha256,
        "state": state if observed is None else observed,
    }
    bundle = replace(bundle, runtime_inventory=original._retained(
        "inventory.json", original._json(correspondence if inventory is None else inventory),
    ))
    return _rebind(recipe, request, bundle)


@contextmanager
def _tripwire():
    calls = []
    real_import = builtins.__import__

    def forbidden(*args, **kwargs):
        calls.append("external effect")
        raise AssertionError("external effect forbidden")

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {
            "modal", "modal_proto", "socket", "requests", "urllib", "subprocess", "docker",
        }:
            return forbidden()
        return real_import(name, *args, **kwargs)

    fake = SimpleNamespace(Image=SimpleNamespace(from_registry=forbidden, from_id=forbidden))
    with patch.dict(sys.modules, {"modal": fake}), \
            patch("builtins.__import__", guarded_import), \
            patch("builtins.open", forbidden), patch.object(Path, "open", forbidden), \
            patch.object(socket, "socket", forbidden):
        try:
            yield
        finally:
            assert calls == [], "validation attempted an external effect"


def _freeze(fixture, declaration=None):
    return configuration.freeze_configuration_policy(
        *fixture, expected_provider_image_id=original._PROVIDER,
        reviewed_configuration=_reviewed() if declaration is None else declaration,
    )


def _check(fixture, *, policy=None, expected="frozen"):
    with _tripwire():
        policy = _freeze(fixture) if policy is None else policy
        return configuration.validate_image_configuration(
            *fixture, expected_provider_image_id=original._PROVIDER, policy=policy,
            expected_policy_sha256=policy.sha256 if expected == "frozen" else expected,
        )


def test_explicit_synthetic_configuration_compares_but_never_approves():
    fixture = _fixture()
    result = _check(fixture)
    assert result == _check(fixture)
    assert result.configuration_consistent is True
    assert result.consistency.retained_bytes_consistent is True
    assert len(result.consistency.retained_pins) == 6
    assert result.provider_review == "CLOSED"
    for name in ("provider_identity_verified", "publisher_signature_verified",
                 "effective_layers_authenticated", "runtime_verified", "image_verified",
                 "build_authorized", "launch_authorized", "cost_approved"):
        assert getattr(result, name) is False


def test_missing_expected_policy_digest_refuses():
    with pytest.raises(ValueError, match="explicit expected policy digest"):
        _check(_fixture(), expected=None)


def test_missing_frozen_policy_refuses():
    with _tripwire(), pytest.raises(ValueError, match="frozen policy required"):
        configuration.validate_image_configuration(
            *_fixture(), expected_provider_image_id=original._PROVIDER,
            policy=None, expected_policy_sha256="a" * 64,
        )


def test_missing_effective_config_refuses():
    state = _reviewed()["state"]
    del state["oci_config"]["config"]
    with pytest.raises(ValueError, match="invalid effective OCI config fields"):
        _check(_fixture(actual=state))


def test_existing_runtime_inventory_without_correspondence_is_unknown():
    with pytest.raises(ValueError, match="runtime effective correspondence UNKNOWN"):
        _check(_fixture(inventory={"synthetic_inventory": True}))


@pytest.mark.parametrize("env", (
    ["PATH=/bin", "PATH=/injected"],
    ["PATH=/usr/local/bin:/usr/bin:/bin", "PYTHON_VERSION=3.12.13", "NEW_PLUGIN=/injected"],
))
def test_duplicate_or_injected_env_refuses(env):
    state = _reviewed()["state"]
    state["oci_config"]["config"]["Env"] = env
    with pytest.raises(ValueError):
        _check(_fixture(actual=state))


@pytest.mark.parametrize("name,value", (
    ("Entrypoint", ["/injected/entrypoint"]), ("Cmd", ["python3", "-c", "unreviewed"]),
))
def test_entrypoint_or_command_drift_refuses(name, value):
    state = _reviewed()["state"]
    state["oci_config"]["config"][name] = value
    with pytest.raises(ValueError, match="differs from reviewed policy"):
        _check(_fixture(actual=state))


@pytest.mark.parametrize("name,value", (("WorkingDir", "/unreviewed"), ("User", "1001:1001")))
def test_working_directory_or_user_drift_refuses(name, value):
    state = _reviewed()["state"]
    state["oci_config"]["config"][name] = value
    with pytest.raises(ValueError, match="differs from reviewed policy"):
        _check(_fixture(actual=state))


@pytest.mark.parametrize("drift", ("inherited_env", "history", "diff_id", "layer", "mount"))
def test_inheritance_history_layer_and_mount_correspondence_refuses(drift):
    state = _reviewed()["state"]
    if drift == "inherited_env":
        state["oci_config"]["config"]["Env"].reverse()
    elif drift == "history":
        state["oci_config"]["history"][0]["created_by"] = "SYNTHETIC unreviewed injection"
    elif drift == "diff_id":
        state["oci_config"]["rootfs"]["diff_ids"][0] = "sha256:" + "a" * 64
    elif drift == "layer":
        state["manifest_layers"][0]["digest"] = "sha256:" + "a" * 64
    else:
        state["mount_targets"] = ["/injected"]
    with pytest.raises(ValueError):
        _check(_fixture(actual=state))


def test_unknown_nested_effective_config_key_refuses():
    state = _reviewed()["state"]
    state["oci_config"]["config"]["Healthcheck"] = {"Test": ["CMD", "unreviewed"]}
    with pytest.raises(ValueError, match="invalid effective process config fields"):
        _check(_fixture(actual=state))


def test_unsupported_correspondence_layout_refuses():
    fixture = _fixture()
    document = json.loads(fixture[2].runtime_inventory.payload)
    document["schema"] = "guessed-provider-layout"
    fixture = _fixture(inventory=document)
    with pytest.raises(ValueError, match="unsupported layout"):
        _check(fixture)


def test_declaration_is_deep_snapshotted_and_post_plan_input_mutation_refuses():
    fixture = _fixture()
    declaration = _reviewed()
    with _tripwire():
        policy = _freeze(fixture, declaration)
    before = policy.canonical
    declaration["state"]["oci_config"]["config"]["Env"].append("MUTATED=1")
    assert policy.canonical == before
    assert _check(fixture, policy=policy).configuration_consistent is True
    # A full supported request snapshot, not only image labels, is bound.
    changed_request = replace(fixture[1], runtime_inventory=replace(
        fixture[1].runtime_inventory, path=Path("/synthetic/changed-inventory.json"),
    ))
    with pytest.raises(ValueError, match="post-plan input mutation"):
        _check((fixture[0], changed_request, fixture[2]), policy=policy)


def test_post_plan_self_consistent_buffer_drift_refuses():
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    state = _reviewed()["state"]
    state["oci_config"]["config"]["Cmd"] = ["python3", "-V"]
    with pytest.raises(ValueError, match="post-plan input mutation"):
        _check(_fixture(actual=state), policy=policy)


@pytest.mark.parametrize("kind", ("path", "tuple"))
def test_request_type_substitution_cannot_alias_frozen_binding(kind):
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    predicate = (lambda value: isinstance(value, Path)) if kind == "path" else (
        lambda value: type(value) is tuple
    )
    name = next(item.name for item in fields(fixture[1])
                if predicate(getattr(fixture[1], item.name)))
    value = getattr(fixture[1], name)
    substituted = {"path": str(value)} if kind == "path" else list(value)
    changed = replace(fixture[1], **{name: substituted})
    with pytest.raises(ValueError, match="unsupported request value type"):
        _check((fixture[0], changed, fixture[2]), policy=policy)


@pytest.mark.parametrize("drift", ("expected_digest", "canonical_bytes"))
def test_policy_digest_and_policy_byte_corruption_refuse(drift):
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    if drift == "expected_digest":
        with pytest.raises(ValueError, match="policy digest mismatch"):
            _check(fixture, policy=policy, expected="a" * 64)
    else:
        policy = replace(policy, canonical=b"!" + policy.canonical[1:])
        with pytest.raises(ValueError, match="policy digest mismatch"):
            _check(fixture, policy=policy)


def test_source_byte_drift_refuses_before_json_parse():
    recipe, request, bundle = _fixture()
    with _tripwire():
        policy = _freeze((recipe, request, bundle))
    corrupt = replace(bundle.config, payload=b"!" + bundle.config.payload[1:])
    with patch.object(evidence, "_document", side_effect=AssertionError("parsed too early")):
        with pytest.raises(ValueError, match="retained evidence digest mismatch"):
            _check((recipe, request, replace(bundle, config=corrupt)), policy=policy)


@pytest.mark.parametrize("drift", ("nul", "unsafe_path", "ambiguous_history"))
def test_nul_unsafe_path_and_ambiguous_history_refuse(drift):
    state = _reviewed()["state"]
    if drift == "nul":
        state["oci_config"]["config"]["Cmd"] = ["python3\x00injected"]
    elif drift == "unsafe_path":
        state["oci_config"]["config"]["WorkingDir"] = "/app/../injected"
    else:
        del state["oci_config"]["history"][0]["empty_layer"]
    with pytest.raises(ValueError):
        _check(_fixture(actual=state))


def test_duplicate_nested_json_key_refuses():
    recipe, request, bundle = _fixture()
    duplicate = bundle.config.payload.replace(b'"User":"0"', b'"User":"0","User":"1"')
    assert duplicate != bundle.config.payload
    bundle = replace(bundle, config=original._retained("config.json", duplicate))
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _check(_rebind(recipe, request, bundle))


def test_runtime_correspondence_hash_mismatch_refuses():
    fixture = _fixture()
    document = json.loads(fixture[2].runtime_inventory.payload)
    document["runtime_observation_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="runtime effective correspondence digest mismatch"):
        _check(_fixture(inventory=document))


def test_effective_configuration_guard_loss_witness_ordinary_assertion():
    state = _reviewed()["state"]
    state["oci_config"]["config"]["Env"][1] = "PYTHON_VERSION=3.12.12"
    refused = False
    try:
        _check(_fixture(actual=state))
    except ValueError as error:
        assert str(error) == "effective configuration differs from reviewed policy"
        refused = True
    assert refused, "effective configuration equality guard lost"


def test_runtime_configuration_guard_loss_witness_ordinary_assertion():
    observed = _reviewed()["state"]
    observed["oci_config"]["config"]["Env"][1] = "PYTHON_VERSION=3.12.12"
    refused = False
    try:
        _check(_fixture(observed=observed))
    except ValueError as error:
        assert str(error) == "runtime effective correspondence drift"
        refused = True
    assert refused, "runtime configuration equality guard lost"


def test_actual_validation_tripwire_detects_forbidden_import():
    def attempted_import(*args, **kwargs):
        builtins.__import__("modal")

    with patch.object(configuration, "validate_image_configuration", attempted_import):
        with pytest.raises(AssertionError):
            _check(_fixture())


def test_noncanonical_policy_refuses_even_when_rehashed():
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    noncanonical = b" " + policy.canonical
    policy = replace(policy, canonical=noncanonical,
                     sha256=hashlib.sha256(noncanonical).hexdigest())
    with pytest.raises(ValueError, match="noncanonical"):
        _check(fixture, policy=policy)


@pytest.mark.parametrize("layout", (
    "null_env", "shell_cmd", "missing_entrypoint", "history_count",
    "unknown_history_key", "unknown_rootfs_key",
))
def test_unsupported_or_ambiguous_nested_layouts_refuse(layout):
    state = _reviewed()["state"]
    config = state["oci_config"]
    if layout == "null_env":
        config["config"]["Env"] = None
    elif layout == "shell_cmd":
        config["config"]["Cmd"] = "python3"
    elif layout == "missing_entrypoint":
        del config["config"]["Entrypoint"]
    elif layout == "history_count":
        config["history"][0]["empty_layer"] = True
    elif layout == "unknown_history_key":
        config["history"][0]["injected"] = True
    else:
        config["rootfs"]["unknown"] = True
    with pytest.raises(ValueError):
        _check(_fixture(actual=state))


@pytest.mark.parametrize("name", ("mount_targets", "injected_layers"))
def test_observed_runtime_mount_or_layer_injection_refuses(name):
    observed = _reviewed()["state"]
    observed[name] = ["/synthetic/injection"]
    with pytest.raises(ValueError, match="unsupported effective mounts or injected layers"):
        _check(_fixture(observed=observed))


def test_legacy_consistency_does_not_apply_effective_configuration_policy():
    state = _reviewed()["state"]
    state["oci_config"]["config"]["Env"].append("UNREVIEWED=1")
    fixture = _fixture(actual=state)
    with _tripwire():
        result = evidence.validate_image_evidence(
            *fixture, expected_provider_image_id=original._PROVIDER,
        )
    assert result.retained_bytes_consistent is True
    assert result.launch_authorized is False
    with pytest.raises(ValueError, match="effective configuration differs"):
        _check(fixture)


def _prehash_refuses(fixture):
    """Both entrypoints must reject invalid caller objects before hash/JSON."""
    with _tripwire():
        policy = _freeze(_fixture())
    with _tripwire(), \
            patch.object(evidence.hashlib, "sha256",
                         side_effect=AssertionError("hashed before primitive validation")), \
            patch.object(evidence, "_document",
                         side_effect=AssertionError("parsed before primitive validation")):
        with pytest.raises(ValueError):
            _freeze(fixture)
        with pytest.raises(ValueError):
            configuration.validate_image_configuration(
                *fixture, expected_provider_image_id=original._PROVIDER, policy=policy,
                expected_policy_sha256=policy.sha256,
            )


def test_nonempty_typed_tasks_and_attempt_bounds_roundtrip():
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
        identical = _freeze((fixture[0], replace(fixture[1]), fixture[2]))
    assert policy == identical
    snapshot = json.loads(policy.canonical)["binding"]["request"]
    tasks = snapshot["tasks"]
    assert tasks["kind"] == "tuple"
    assert len(tasks["items"]) == 4
    for actual, encoded in zip(fixture[1].tasks, tasks["items"], strict=True):
        assert type(actual) is SqlTask
        assert encoded["kind"] == "sql_task"
        assert {key: item["value"] for key, item in encoded["fields"].items()} == {
            item.name: getattr(actual, item.name) for item in fields(SqlTask)
        }
    assert type(fixture[1].bounds) is AttemptBounds
    bounds = snapshot["bounds"]
    assert bounds["kind"] == "attempt_bounds"
    assert bounds["fields"]["total_ceiling_usd"] == {
        "kind": "decimal", "sign": 0, "coefficient": "12", "exponent": 0,
    }
    assert bounds["fields"]["lifetime_seconds"] == {"kind": "int", "value": 1800}
    result = _check(fixture, policy=policy)
    assert result.configuration_consistent is True
    assert result.provider_review == "CLOSED"
    assert result.launch_authorized is False
    assert result.cost_approved is False


def test_nonempty_task_order_mutation_refuses_unchanged_policy():
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    changed = replace(fixture[1], tasks=tuple(reversed(fixture[1].tasks)))
    with pytest.raises(ValueError, match="post-plan input mutation"):
        _check((fixture[0], changed, fixture[2]), policy=policy)


@pytest.mark.parametrize("field", (
    "total_ceiling_usd", "prior_usage_usd", "remaining_worst_case_usd", "lifetime_seconds",
))
def test_actual_bound_values_mutation_refuses_unchanged_policy(field):
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    changes = {
        "total_ceiling_usd": {"total_ceiling_usd": Decimal("13")},
        "prior_usage_usd": {"prior_usage_usd": Decimal("0.5"),
                            "remaining_worst_case_usd": Decimal("11.5")},
        "remaining_worst_case_usd": {"remaining_worst_case_usd": Decimal("11")},
        "lifetime_seconds": {"lifetime_seconds": 1799},
    }
    changed = replace(fixture[1], bounds=replace(fixture[1].bounds, **changes[field]))
    with pytest.raises(ValueError, match="post-plan input mutation"):
        _check((fixture[0], changed, fixture[2]), policy=policy)


@pytest.mark.parametrize("invalid", ("missing_bounds", "empty_tasks", "unsupported_task"))
def test_missing_bounds_empty_tasks_and_unknown_task_types_refuse(invalid):
    recipe, request, bundle = _fixture()
    if invalid == "missing_bounds":
        request = replace(request, bounds=None)
    elif invalid == "empty_tasks":
        request = replace(request, tasks=())
    else:
        request = replace(request, tasks=(object(), *request.tasks[1:]))
    _prehash_refuses((recipe, request, bundle))


class _UnexpectedDecimal(Decimal):
    def as_tuple(self):
        raise AssertionError("Decimal subclass callback forbidden")

    def is_finite(self):
        raise AssertionError("Decimal subclass callback forbidden")


@pytest.mark.parametrize("field,value", (
    ("total_ceiling_usd", True), ("total_ceiling_usd", 12),
    ("total_ceiling_usd", 12.0), ("total_ceiling_usd", Decimal("NaN")),
    ("total_ceiling_usd", Decimal("Infinity")),
    ("total_ceiling_usd", _UnexpectedDecimal("12")),
    ("lifetime_seconds", True), ("lifetime_seconds", Decimal("1800")),
))
def test_strict_bound_primitive_types_refuse_before_hashing(field, value):
    recipe, request, bundle = _fixture()
    request = replace(request, bounds=replace(request.bounds, **{field: value}))
    _prehash_refuses((recipe, request, bundle))


def test_decimal_value_canonicalization_is_context_independent():
    fixture = _fixture()
    with _tripwire():
        policy = _freeze(fixture)
    equivalent = replace(fixture[1], bounds=replace(
        fixture[1].bounds, total_ceiling_usd=Decimal("12.000"),
        prior_usage_usd=Decimal("-0.000"), remaining_worst_case_usd=Decimal("1200e-2"),
    ))
    with localcontext() as context:
        context.prec = 1
        with _tripwire():
            assert _freeze((fixture[0], equivalent, fixture[2])) == policy
        assert _check((fixture[0], equivalent, fixture[2]), policy=policy).cost_approved is False


def test_bool_integer_and_decimal_tagged_bindings_do_not_alias():
    with _tripwire():
        bindings = [configuration._canonical(configuration._request_value(value))
                    for value in (True, 1, Decimal("1"))]
    assert len(set(bindings)) == 3
    assert [json.loads(value)["kind"] for value in bindings] == ["bool", "int", "decimal"]


@pytest.mark.parametrize("location", ("request_root", "request_pin", "retained_pin"))
def test_path_subclass_callbacks_are_never_invoked(location):
    calls = []

    class EvilPath(type(Path("/"))):
        def __str__(self):
            calls.append("str")
            raise AssertionError("Path subclass __str__ callback forbidden")

        def __fspath__(self):
            calls.append("fspath")
            raise AssertionError("Path subclass __fspath__ callback forbidden")

        def is_absolute(self):
            calls.append("is_absolute")
            raise AssertionError("Path subclass method callback forbidden")

    evil = EvilPath("/synthetic/evil")
    recipe, request, bundle = _fixture()
    if location == "request_root":
        request = replace(request, db_root=evil)
    elif location == "request_pin":
        request = replace(request, runtime_inventory=replace(request.runtime_inventory, path=evil))
    else:
        bundle = replace(bundle, receipt=replace(
            bundle.receipt, pin=replace(bundle.receipt.pin, path=evil),
        ))
    _prehash_refuses((recipe, request, bundle))
    assert calls == []


@pytest.mark.parametrize("location", ("request_root", "request_pin", "retained_pin"))
@pytest.mark.parametrize("layout", (
    "raw_string", "raw_count", "cached_tail", "cached_string", "cached_root",
    "raw_type", "partial",
))
def test_path_storage_refuses_before_format_hash_or_parse(location, layout):
    path = Path("/synthetic/bounded")
    if layout == "raw_string":
        path = Path("/" + "x" * 8192)
    elif layout == "raw_count":
        path = Path("/", *(["x"] * 512))
    elif layout in ("cached_tail", "cached_root"):
        path._drv = ""
        path._root = "/" if layout == "cached_tail" else "/" * 8193
        path._tail_cached = ["x" * 8192] if layout == "cached_tail" else []
    elif layout == "cached_string":
        path._str = "/" + "x" * 8192
    elif layout == "raw_type":
        path._raw_paths = ("/synthetic/bounded",)
    else:
        path._root = "/"
    if layout != "cached_string":
        with pytest.raises(AttributeError):
            object.__getattribute__(path, "_str")
    recipe, request, bundle = _fixture()
    if location == "request_root":
        request = replace(request, db_root=path)
    elif location == "request_pin":
        request = replace(request, runtime_inventory=replace(request.runtime_inventory, path=path))
    else:
        bundle = replace(bundle, receipt=replace(
            bundle.receipt, pin=replace(bundle.receipt.pin, path=path),
        ))
    formatted = []
    original_str = type(path).__str__

    def guarded_str(value):
        if value is path:
            formatted.append(True)
            raise AssertionError("formatted unbounded Path storage")
        return original_str(value)

    with patch.object(type(path), "__str__", guarded_str):
        _prehash_refuses((recipe, request, bundle))
    assert formatted == []


@pytest.mark.parametrize("oversized", ("integer", "coefficient", "exponent", "task_text"))
def test_oversized_request_representations_refuse_before_hashing(oversized):
    recipe, request, bundle = _fixture()
    if oversized == "integer":
        request = replace(request, bounds=replace(request.bounds, artifact_bytes=1 << 100000))
    elif oversized == "coefficient":
        request = replace(request, bounds=replace(
            request.bounds, total_ceiling_usd=Decimal("9" * 1000),
        ))
    elif oversized == "exponent":
        request = replace(request, bounds=replace(
            request.bounds, total_ceiling_usd=Decimal("1e100000000"),
        ))
    else:
        task = replace(request.tasks[0], question="x" * 8193)
        request = replace(request, tasks=(task, *request.tasks[1:]))
    _prehash_refuses((recipe, request, bundle))


@pytest.mark.parametrize("value", (True, 1, Decimal("1")))
def test_sql_task_fields_require_exact_bounded_strings(value):
    recipe, request, bundle = _fixture()
    task = replace(request.tasks[0], question=value)
    request = replace(request, tasks=(task, *request.tasks[1:]))
    _prehash_refuses((recipe, request, bundle))


def test_generic_canonical_integer_is_bounded_before_json_serialization():
    with patch.object(configuration.json, "dumps",
                      side_effect=AssertionError("JSON conversion before integer guard")):
        with pytest.raises(ValueError, match="integer exceeds canonical serialization bound"):
            configuration._canonical({"value": 1 << 100000})


def _shared_dag():
    value = []
    for _ in range(6):
        value = [value] * 512
    return value


@pytest.mark.parametrize("entrypoint", ("snapshot", "canonical"))
def test_shared_list_dag_refuses_with_bounded_visits_before_encoding(entrypoint):
    value = _shared_dag()
    budget = configuration._TraversalBudget()
    with pytest.raises(ValueError, match="shared or cyclic configuration container"):
        configuration._snapshot(value, budget, 0)
    assert budget.nodes <= 14
    assert budget.allocation_bytes <= configuration._ALLOCATION_LIMIT
    assert budget.encoded_bytes <= evidence._LIMIT
    with patch.object(configuration._CanonicalEncoder, "encode",
                      side_effect=AssertionError("encoder reached shared graph")):
        with pytest.raises(ValueError, match="shared or cyclic configuration container"):
            if entrypoint == "snapshot":
                configuration._plain(value)
            else:
                configuration._canonical(value)


@pytest.mark.parametrize("kind", ("list", "dict"))
def test_cycles_refuse_with_at_most_three_snapshot_visits(kind):
    if kind == "list":
        value = []
        value.append(value)
    else:
        value = {}
        value["loop"] = value
    budget = configuration._TraversalBudget()
    with pytest.raises(ValueError, match="shared or cyclic configuration container"):
        configuration._snapshot(value, budget, 0)
    assert budget.nodes <= 3
    with patch.object(configuration._CanonicalEncoder, "encode",
                      side_effect=AssertionError("encoder reached cycle")):
        with pytest.raises(ValueError, match="shared or cyclic configuration container"):
            configuration._canonical(value)


def test_aggregate_unique_node_budget_refuses_before_visit_16385():
    value = [list(range(256)) for _ in range(64)]
    budget = configuration._TraversalBudget()
    with pytest.raises(ValueError, match="aggregate snapshot node budget exceeded"):
        configuration._snapshot(value, budget, 0)
    assert budget.nodes == 16384 == configuration._NODE_LIMIT
    assert budget.allocation_bytes <= 8388608 == configuration._ALLOCATION_LIMIT
    assert budget.encoded_bytes <= 1048576 == evidence._LIMIT
    with patch.object(configuration._CanonicalEncoder, "encode",
                      side_effect=AssertionError("encoder reached oversized snapshot")):
        with pytest.raises(ValueError, match="aggregate snapshot node budget exceeded"):
            configuration._canonical(value)


def test_accumulated_strings_refuse_before_any_json_encoding():
    value = ["x" * 8192] * 512
    budget = configuration._TraversalBudget()
    with pytest.raises(ValueError, match="aggregate snapshot encoded byte budget exceeded"):
        configuration._snapshot(value, budget, 0)
    assert budget.nodes <= 130
    assert budget.encoded_bytes <= evidence._LIMIT
    assert budget.allocation_bytes <= configuration._ALLOCATION_LIMIT
    with patch.object(configuration.json, "dumps",
                      side_effect=AssertionError("JSON encoding reached oversized snapshot")):
        with pytest.raises(ValueError, match="aggregate snapshot encoded byte budget exceeded"):
            configuration._canonical(value)


@pytest.mark.parametrize("kind", ("unknown_extra", "nonstring_key"))
def test_unknown_declaration_top_level_refuses_before_descent_or_binding(kind):
    calls = []

    class HostileKey:
        def __hash__(self):
            calls.append("hash")
            return 0 if hash("schema") != 0 else 1

        def __eq__(self, other):
            calls.append("eq")
            raise AssertionError("caller key equality callback forbidden")

        def __str__(self):
            calls.append("str")
            raise AssertionError("caller key serialization callback forbidden")

    declaration = _reviewed()
    if kind == "unknown_extra":
        declaration["unknown"] = _shared_dag()
    else:
        declaration = {"schema": declaration["schema"], HostileKey(): _shared_dag()}
    calls.clear()  # Construction is caller-owned; observe only validation callbacks.
    fixture = _fixture()
    with _tripwire(), \
            patch.object(configuration, "_plain",
                         side_effect=AssertionError("snapshot reached unknown declaration")), \
            patch.object(configuration, "_binding",
                         side_effect=AssertionError("binding reached unknown declaration")):
        with pytest.raises(ValueError, match="invalid reviewed configuration declaration fields"):
            _freeze(fixture, declaration)
    assert calls == []


def _ascii_leaf_array(encoded_size):
    # 129 leaves: two brackets, 128 commas and 258 quotes = 388 bytes overhead.
    remaining = encoded_size - 388
    result = []
    for _ in range(129):
        length = min(8192, remaining)
        result.append("x" * length)
        remaining -= length
    assert remaining == 0
    return result


@pytest.mark.parametrize("encoded_size", (1048575, 1048576, 1048577))
def test_canonical_one_mib_boundary_is_checked_before_encoder_allocation(encoded_size):
    value = _ascii_leaf_array(encoded_size)
    if encoded_size <= evidence._LIMIT:
        with _tripwire():
            canonical = configuration._canonical(value)
        assert len(canonical) == encoded_size
        assert json.loads(canonical) == value
    else:
        with patch.object(configuration._CanonicalEncoder, "encode",
                          side_effect=AssertionError("encoder reached oversized canonical input")):
            with pytest.raises(ValueError, match="aggregate snapshot encoded byte budget exceeded"):
                configuration._canonical(value)


@pytest.mark.parametrize("bound", ("bytes", "nodes"))
def test_independent_canonical_encoder_never_appends_beyond_one_mib(bound):
    encoder = configuration._CanonicalEncoder()
    value = ["x" * 8192] * 512 if bound == "bytes" else [
        list(range(256)) for _ in range(64)
    ]
    message = ("canonical encoder byte budget exceeded" if bound == "bytes"
               else "canonical encoder traversal budget exceeded")
    with _tripwire(), pytest.raises(ValueError, match=message):
        encoder.encode(value)
    assert 0 < len(encoder.buffer) <= 1048576
    assert encoder.nodes <= 16384
    if bound == "nodes":
        assert encoder.nodes == 16384


def test_bounded_scalar_encoder_matches_canonical_stdlib_bytes():
    value = {"z": ["a\n\"\\\t\x7f", "\u2603", "\U0001f600", True, False, None, -7, ()],
             "a": "known"}
    original_dumps = json.dumps
    expected = original_dumps(value, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True, allow_nan=False).encode("ascii")
    calls = []

    def only_bounded_strings(item, *args, **kwargs):
        assert type(item) is str and len(item) <= 8192
        calls.append(len(item))
        return original_dumps(item, *args, **kwargs)

    with _tripwire(), patch.object(configuration.json, "dumps", only_bounded_strings):
        assert configuration._canonical(value) == expected
    assert 0 < len(calls) <= configuration._NODE_LIMIT


def test_aggregate_allocation_budget_refuses_before_container_materialization():
    budget = configuration._TraversalBudget(
        allocation_bytes=configuration._ALLOCATION_LIMIT - 128,
    )
    with pytest.raises(ValueError, match="aggregate snapshot allocation budget exceeded"):
        configuration._snapshot(["x"], budget, 0)
    assert budget.nodes == 1
    assert budget.allocation_bytes == configuration._ALLOCATION_LIMIT
    assert budget.encoded_bytes == 0
    assert budget.seen == set()
