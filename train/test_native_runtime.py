"""Metadata-only native-runtime contract. No training/runtime verification.

Source of truth: spec/native-training.md, Track A, plus the parent's versioned
PyPI evidence in research/2026-10-23-native-runtime-metadata.json.

The missing implementation is imported inside ``api`` so RED is a collected
test failure, never a collection error or an optional-dependency skip.

Output contract fixed here:
  schema_version, metadata_source ("installed"/"fixture"), platform
  (system/machine/python), versions, candidate_core, metadata_scope, limitations,
  policy_id, issues (missing/invalid/frozen/native/selected/policy/unresolved),
  and six false proof flags.
Missing/invalid issues map package -> nonempty diagnostic. Frozen issues are
the existing guards.check_stack list. Native/selected issues map package ->
nonempty diagnostic lists. Policy/unresolved issues are diagnostic lists.
Frozen issues describe the default policy, not the native enforcement decision.
NativeRuntimeError carries the complete installed-source report as ``report``.
"""

from __future__ import annotations

import builtins
import copy
import importlib
import importlib.metadata as metadata
import inspect
import os
import pathlib
import platform
import socket
import subprocess
import sys
import urllib.request
from collections import Counter

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

PACKAGES = (
    "unsloth", "unsloth_zoo", "trl", "transformers", "torch", "vllm",
    "datasets", "accelerate", "peft",
)
CANDIDATE_CORE = {
    "unsloth": "2026.10.3",
    "unsloth_zoo": "2026.10.3",
    "trl": "1.13.0",
    "transformers": "5.17.0",
}
# Selected version constraints only. Not a complete environment or ABI recipe.
SELECTED = {
    **CANDIDATE_CORE,
    "torch": "2.11.0",
    "vllm": "0.23.0",
    "datasets": "4.7.0",
    "accelerate": "1.4.0",
    "peft": "0.18.0",
}
PROOF_FLAGS = (
    "candidate_approved",
    "dependency_graph_verified",
    "abi_verified",
    "runtime_verified",
    "training_verified",
    "launch_authorized",
)
ISSUE_CATEGORIES = {
    "missing", "invalid", "frozen", "native", "selected", "policy", "unresolved",
}


@pytest.fixture(autouse=True)
def no_runtime_side_effects(monkeypatch):
    """Catch attempted imports/network/processes even if implementation hides them."""
    attempted = []
    before_environment = {
        key: value for key, value in os.environ.items() if key != "PYTEST_CURRENT_TEST"
    }
    real_import = builtins.__import__
    real_import_module = importlib.import_module
    forbidden = {
        "torch", "trl", "unsloth", "unsloth_zoo", "transformers", "vllm",
        "datasets", "accelerate", "peft", "huggingface_hub", "triton",
        "xformers", "bitsandbytes", "httpx", "requests",
    }

    def check(name):
        if name.split(".")[0] in forbidden:
            attempted.append(name)
            raise AssertionError(f"native metadata report imported {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return real_import(name, *args, **kwargs)

    def guarded_import_module(name, *args, **kwargs):
        check(name)
        return real_import_module(name, *args, **kwargs)

    def reject(*args, **kwargs):
        attempted.append("network/process")
        raise AssertionError("native metadata report attempted network/process execution")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(urllib.request, "urlopen", reject)
    monkeypatch.setattr(subprocess, "Popen", reject)
    monkeypatch.setattr(subprocess, "run", reject)
    monkeypatch.setattr(subprocess, "check_call", reject)
    monkeypatch.setattr(subprocess, "check_output", reject)
    monkeypatch.setattr(os, "system", reject)
    yield
    assert attempted == []
    after_environment = {
        key: value for key, value in os.environ.items() if key != "PYTEST_CURRENT_TEST"
    }
    changed_keys = {
        key for key in before_environment.keys() | after_environment.keys()
        if before_environment.get(key) != after_environment.get(key)
    }
    assert not changed_keys, f"environment keys changed: {sorted(changed_keys)}"


@pytest.fixture
def api():
    try:
        return importlib.import_module("train.native_runtime")
    except ModuleNotFoundError as exc:
        if exc.name == "train.native_runtime":
            pytest.fail("missing train.native_runtime implementation (expected TDD RED)", pytrace=False)
        raise


def _versions(**changes):
    return {**SELECTED, **changes}


def _installed(monkeypatch, versions):
    """Replace only distribution metadata, never framework/model constructors."""
    calls = []

    def version(name):
        canonical = name.replace("-", "_")
        calls.append(canonical)
        value = versions.get(canonical)
        if value is None:
            raise metadata.PackageNotFoundError(name)
        return value

    monkeypatch.setattr(metadata, "version", version)
    return calls


def _assert_report(report, *, source, versions):
    assert isinstance(report, dict)
    assert type(report["schema_version"]) is int
    assert report["schema_version"] == 2
    assert report["policy_id"] == "native-sql-tf517-v1"
    assert report["metadata_source"] == source
    assert report["versions"] == versions
    assert set(report["versions"]) == set(PACKAGES)
    assert report["platform"] == {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    assert report["candidate_core"] == CANDIDATE_CORE
    assert report["metadata_scope"] == "selected_direct_constraints_only"
    for key in PROOF_FLAGS:
        assert report[key] is False, (key, report[key])
    limitations = report["limitations"]
    assert isinstance(limitations, list) and limitations
    assert all(isinstance(item, str) and item.strip() for item in limitations)
    text = " ".join(limitations).lower()
    assert "transitive" in text
    assert "abi" in text
    issues = report["issues"]
    assert isinstance(issues, dict)
    assert set(issues) == ISSUE_CATEGORIES
    for category in ("missing", "invalid"):
        assert isinstance(issues[category], dict)
        for package, diagnostic in issues[category].items():
            assert package in PACKAGES
            assert isinstance(diagnostic, str) and diagnostic.strip()
            assert package in diagnostic
    for category in ("frozen", "policy", "unresolved"):
        assert isinstance(issues[category], list)
        assert all(isinstance(item, str) and item.strip() for item in issues[category])
    for category in ("native", "selected"):
        assert isinstance(issues[category], dict)
        for package, diagnostics in issues[category].items():
            assert package in PACKAGES
            assert isinstance(diagnostics, list) and diagnostics
            assert all(isinstance(item, str) and item.strip() for item in diagnostics)


def _diagnostics(report, category, package):
    return " ".join(report["issues"][category].get(package, [])).lower()


def test_public_api_and_named_failure_have_no_fixture_requirement_bypass(api):
    assert list(inspect.signature(api.native_runtime_report).parameters) == ["versions"]
    assert inspect.signature(api.native_runtime_report).parameters["versions"].default is None
    assert list(inspect.signature(api.require_native_runtime).parameters) == []
    assert issubclass(api.NativeRuntimeError, RuntimeError)
    with pytest.raises(TypeError):
        api.require_native_runtime(SELECTED)
    with pytest.raises(TypeError):
        api.require_native_runtime(versions=SELECTED)


def test_runtime_report_never_certifies_execution(api):
    report = api.native_runtime_report(SELECTED)
    _assert_report(report, source="fixture", versions=SELECTED)
    assert report["issues"]["missing"] == {}
    assert report["issues"]["invalid"] == {}
    assert report["issues"]["native"] == {}
    assert report["issues"]["selected"] == {}
    assert report["issues"]["policy"] == []
    # The default policy is preserved; genuine native blockers remain separate.
    assert report["issues"]["frozen"]
    assert report["issues"]["unresolved"]
    assert not any(report.get(key, False) for key in ("ready", "compatible", "install_ready"))


@pytest.mark.parametrize("supplied", [{}, dict.fromkeys(PACKAGES)])
def test_reports_all_nine_missing_packages_not_only_first(api, supplied):
    report = api.native_runtime_report(supplied)
    _assert_report(report, source="fixture", versions=dict.fromkeys(PACKAGES))
    assert set(report["issues"]["missing"]) == set(PACKAGES)
    assert report["issues"]["invalid"] == {}
    assert report["issues"]["frozen"]


def test_none_is_absent_not_invalid(api):
    report = api.native_runtime_report(_versions(peft=None))
    assert set(report["issues"]["missing"]) == {"peft"}
    assert "peft" not in report["issues"]["invalid"]
    assert report["versions"]["peft"] is None


def test_installed_source_collects_all_selected_distribution_metadata(api, monkeypatch):
    local = dict.fromkeys(PACKAGES)
    local.update(transformers="5.18.0", datasets="5.0.1")
    calls = _installed(monkeypatch, local)
    report = api.native_runtime_report()
    _assert_report(report, source="installed", versions=local)
    assert Counter(calls) == Counter(PACKAGES)
    assert set(report["issues"]["missing"]) == set(PACKAGES) - {"transformers", "datasets"}
    assert "transformers" in report["issues"]["selected"]
    assert "datasets" in report["issues"]["selected"]


def test_explicit_none_means_installed_but_empty_fixture_never_does(api, monkeypatch):
    calls = _installed(monkeypatch, SELECTED)
    report = api.native_runtime_report({})
    assert report["metadata_source"] == "fixture"
    assert calls == []
    assert set(report["issues"]["missing"]) == set(PACKAGES)
    report = api.native_runtime_report(None)
    _assert_report(report, source="installed", versions=SELECTED)
    assert Counter(calls) == Counter(PACKAGES)


def test_real_available_distribution_metadata_matches_independent_reads(api):
    """Real metadata I/O only, no mock and no package/framework imports."""
    actual = {}
    for name in PACKAGES:
        try:
            actual[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual[name] = None
    report = api.native_runtime_report()
    _assert_report(report, source="installed", versions=actual)
    assert report["issues"]["frozen"] or report["issues"]["native"]


def test_fixture_report_never_reads_installed_metadata(api, monkeypatch):
    def forbidden(name):
        pytest.fail(f"fixture report read installed metadata for {name}")

    monkeypatch.setattr(metadata, "version", forbidden)
    before = copy.deepcopy(SELECTED)
    report = api.native_runtime_report(SELECTED)
    _assert_report(report, source="fixture", versions=before)
    assert SELECTED == before


def test_reports_do_not_share_mutable_candidate_or_issue_state(api):
    first = api.native_runtime_report(SELECTED)
    first["candidate_core"]["transformers"] = "0.0.0"
    first["issues"]["frozen"].clear()
    first["versions"]["torch"] = None
    second = api.native_runtime_report(SELECTED)
    _assert_report(second, source="fixture", versions=SELECTED)
    assert second["issues"]["frozen"]
    assert SELECTED["torch"] == "2.11.0"


def test_installed_metadata_is_fresh_not_cached_between_reports(api, monkeypatch):
    installed = dict(SELECTED)
    _installed(monkeypatch, installed)
    first = api.native_runtime_report()
    installed["datasets"] = "5.0.1"
    second = api.native_runtime_report()
    assert first["versions"]["datasets"] == "4.7.0"
    assert second["versions"]["datasets"] == "5.0.1"
    assert "datasets" in second["issues"]["selected"]


@pytest.mark.parametrize("transformers", ["4.57.6", "5.17.0", "5.18.0"])
def test_default_diagnostics_remain_explicit_and_use_existing_guard(api, transformers):
    from train import guards

    versions = _versions(transformers=transformers)
    report = api.native_runtime_report(versions)
    assert report["issues"]["frozen"] == guards.check_stack(versions)
    if transformers == "4.57.6":
        assert report["issues"]["frozen"] == []
        native = _diagnostics(report, "native", "transformers")
        assert "5.2" in native
    else:
        assert report["issues"]["frozen"]
        assert report["issues"]["native"] == {}
    if transformers == "5.18.0":
        assert "5.17" in _diagnostics(report, "selected", "transformers")
    else:
        assert "transformers" not in report["issues"]["selected"]


def test_existing_frozen_guard_is_called_not_reimplemented(api, monkeypatch):
    from train import guards

    seen = []

    def check_stack(versions):
        seen.append(dict(versions))
        return ["parent-frozen-guard-sentinel"]

    monkeypatch.setattr(guards, "check_stack", check_stack)
    report = api.native_runtime_report(SELECTED)
    assert seen == [SELECTED]
    assert report["issues"]["frozen"] == ["parent-frozen-guard-sentinel"]


def test_general_trl_floor_does_not_replace_native_feature_floor(api):
    report = api.native_runtime_report(_versions(transformers="4.57.6"))
    assert report["issues"]["frozen"] == []
    assert "transformers" not in report["issues"]["selected"]
    assert "5.2" in _diagnostics(report, "native", "transformers")


def test_local_transformers_and_datasets_violations_both_reported(api):
    report = api.native_runtime_report(_versions(transformers="5.18.0", datasets="5.0.1"))
    assert "5.17" in _diagnostics(report, "selected", "transformers")
    assert "5" in _diagnostics(report, "selected", "datasets")
    assert report["issues"]["frozen"]


@pytest.mark.parametrize(("package", "version"), [
    ("unsloth_zoo", "2026.10.2"),
    ("transformers", "5.17.1"),
    ("datasets", "4.6.9"),
    ("datasets", "5.0.0"),
    ("torch", "2.3.9"),
    ("torch", "2.15.0"),
    ("vllm", "0.19.0"),
    ("vllm", "0.28.1"),
    ("accelerate", "1.3.9"),
    ("peft", "0.17.9"),
])
def test_selected_direct_constraint_violations_are_named(api, package, version):
    report = api.native_runtime_report(_versions(**{package: version}))
    assert report["issues"]["invalid"] == {}
    assert _diagnostics(report, "selected", package), (package, version, report)


@pytest.mark.parametrize(("package", "version"), [
    ("vllm", "0.19.1"),
    ("vllm", "0.28.0"),
    ("datasets", "4.7.0"),
    ("datasets", "4.9.9"),
    ("accelerate", "1.4.0"),
    ("peft", "0.18.0"),
    ("unsloth_zoo", "2026.10.3"),
])
def test_inclusive_selected_boundaries_add_no_selected_error(api, package, version):
    report = api.native_runtime_report(_versions(**{package: version}))
    assert report["issues"]["selected"] == {}
    assert report["issues"]["frozen"]  # metadata bounds never imply execution authority


@pytest.mark.parametrize("torch", ["2.4.0", "2.10.0", "2.12.0", "2.14.9"])
def test_vllm_023_requires_torch_211_not_just_unsloth_broad_range(api, torch):
    report = api.native_runtime_report(_versions(torch=torch))
    diagnostic = _diagnostics(report, "selected", "torch")
    assert "vllm" in diagnostic
    assert "2.11" in diagnostic


def test_vllm_023_torch_211_is_only_selected_metadata_not_abi_proof(api):
    report = api.native_runtime_report(SELECTED)
    assert "torch" not in report["issues"]["selected"]
    assert report["abi_verified"] is False
    assert report["runtime_verified"] is False


@pytest.mark.parametrize("transformers", [
    "5.0.0", "5.0.9", "5.1.0", "5.1.9", "5.2.0", "5.2.3",
    "5.3.0", "5.3.9", "5.4.0", "5.4.8", "5.5.0",
])
def test_vllm_023_excludes_early_transformers_5_even_inside_broad_range(api, transformers):
    report = api.native_runtime_report(_versions(transformers=transformers))
    diagnostic = _diagnostics(report, "selected", "transformers")
    assert "vllm" in diagnostic, (transformers, report)
    assert transformers in diagnostic


def test_vllm_023_exclusion_does_not_accidentally_include_transformers_551(api):
    report = api.native_runtime_report(_versions(transformers="5.5.1"))
    assert "transformers" not in report["issues"]["selected"]
    assert report["issues"]["native"] == {}
    assert report["issues"]["frozen"]


@pytest.mark.parametrize(("package", "version"), [
    ("unsloth", "2026.9.12"),
    ("trl", "1.12.0"),
    ("trl", "1.13.1"),
])
def test_original_unsloth_floor_and_trl_pin_still_block(api, package, version):
    from train import guards

    versions = _versions(**{package: version})
    report = api.native_runtime_report(versions)
    assert report["issues"]["frozen"] == guards.check_stack(versions)
    assert any(package in diagnostic for diagnostic in report["issues"]["frozen"])
    common = guards.check_stack_common(versions)
    assert common
    assert all(diagnostic in report["issues"]["policy"] for diagnostic in common)


@pytest.mark.parametrize("package", PACKAGES)
def test_prerelease_is_unevaluable_for_every_selected_package(api, package):
    version = SELECTED[package] + "rc1"
    report = api.native_runtime_report(_versions(**{package: version}))
    assert package in report["issues"]["invalid"]
    assert report["versions"][package] == version


@pytest.mark.parametrize("bad", [
    "", " 5.17.0", "5.17.0 ", "v5.17.0", "5.17.*", "5..17.0",
    "5.17.0garbage", "5.17.0.dev1", "5.17.0a1", "5.17.0.post1",
    "1!5.17.0", "5.17.0+unknown-build", "-5.17.0", "５.１７.０",
    True, False, 5, 5.17, [], {}, ("5", "17", "0"),
    "9" * 10_000, "5.17." + "9" * 10_000, "5.17.0" + ".0" * 100,
])
def test_malformed_unsupported_or_unbounded_versions_fail_closed(api, bad):
    report = api.native_runtime_report(_versions(transformers=bad))
    assert "transformers" in report["issues"]["invalid"]
    assert "transformers" not in report["issues"]["missing"]
    for key in PROOF_FLAGS:
        assert report[key] is False


def test_all_invalid_versions_are_reported_without_first_error_short_circuit(api):
    invalid = {package: value + "rc1" for package, value in SELECTED.items()}
    report = api.native_runtime_report(invalid)
    assert set(report["issues"]["invalid"]) == set(PACKAGES)
    assert report["versions"] == invalid


def test_missing_invalid_and_independent_bounds_are_all_visible(api):
    versions = _versions(
        unsloth=None, peft=None, torch="not-a-release",
        transformers="5.18.0", datasets="5.0.1", accelerate="1.3.0",
    )
    report = api.native_runtime_report(versions)
    assert set(report["issues"]["missing"]) == {"unsloth", "peft"}
    assert set(report["issues"]["invalid"]) == {"torch"}
    assert {"transformers", "datasets", "accelerate"} <= set(report["issues"]["selected"])
    assert report["issues"]["frozen"]


@pytest.mark.parametrize("transformers", ["4.57.6", "5.17.0", "5.18.0"])
def test_require_remains_closed_under_fixed_native_policy(
    api, monkeypatch, transformers,
):
    installed = _versions(transformers=transformers)
    _installed(monkeypatch, installed)
    with pytest.raises(api.NativeRuntimeError) as caught:
        api.require_native_runtime()
    report = caught.value.report
    _assert_report(report, source="installed", versions=installed)
    assert report["issues"]["unresolved"]
    if transformers == CANDIDATE_CORE["transformers"]:
        assert report["issues"]["policy"] == []
    else:
        assert report["issues"]["policy"]


def test_require_collects_actual_metadata_not_previous_fixture_or_report_cache(api, monkeypatch):
    actual = dict.fromkeys(PACKAGES)
    _installed(monkeypatch, actual)
    api.native_runtime_report(SELECTED)
    with pytest.raises(api.NativeRuntimeError) as caught:
        api.require_native_runtime()
    _assert_report(caught.value.report, source="installed", versions=actual)
    assert set(caught.value.report["issues"]["missing"]) == set(PACKAGES)


def test_require_refuses_unevaluable_installed_metadata(api, monkeypatch):
    installed = _versions(transformers="5.17.0rc1")
    _installed(monkeypatch, installed)
    with pytest.raises(api.NativeRuntimeError) as caught:
        api.require_native_runtime()
    assert caught.value.report["metadata_source"] == "installed"
    assert "transformers" in caught.value.report["issues"]["invalid"]


@pytest.mark.parametrize("package", CANDIDATE_CORE)
@pytest.mark.parametrize("variant", [
    "short", "padded", "next_patch", "rc", "dev", "post", "local", "epoch", "missing",
])
def test_fixed_core_policy_rejects_every_nonliteral_version(api, package, variant):
    exact = CANDIDATE_CORE[package]
    versions = {
        "short": exact.rsplit(".", 1)[0],
        "padded": exact + ".0",
        "next_patch": exact.rsplit(".", 1)[0] + "." + str(int(exact.rsplit(".", 1)[1]) + 1),
        "rc": exact + "rc1",
        "dev": exact + ".dev1",
        "post": exact + ".post1",
        "local": exact + "+local",
        "epoch": "0!" + exact,
        "missing": None,
    }
    report = api.native_runtime_report(_versions(**{package: versions[variant]}))
    diagnostics = report["issues"]["policy"]
    assert any(package in diagnostic and exact in diagnostic for diagnostic in diagnostics)
    for key in PROOF_FLAGS:
        assert report[key] is False


def test_native_policy_calls_shared_guard_independently_of_default_diagnostics(api, monkeypatch):
    from train import guards

    seen = []

    def common(versions):
        seen.append(dict(versions))
        return ["shared-stack-sentinel"]

    monkeypatch.setattr(guards, "check_stack_common", common)
    monkeypatch.setattr(guards, "check_stack", lambda versions: ["default-only-sentinel"])
    report = api.native_runtime_report(SELECTED)
    assert seen == [SELECTED]
    assert report["issues"]["policy"] == ["shared-stack-sentinel"]
    assert report["issues"]["frozen"] == ["default-only-sentinel"]


def test_perfect_installed_metadata_still_refuses_every_unverified_requirement(api, monkeypatch):
    calls = _installed(monkeypatch, SELECTED)
    with pytest.raises(api.NativeRuntimeError) as caught:
        api.require_native_runtime()
    report = caught.value.report
    _assert_report(report, source="installed", versions=SELECTED)
    assert Counter(calls) == Counter(PACKAGES)
    for category in ("missing", "invalid", "native", "selected", "policy"):
        assert not report["issues"][category]
    blockers = report["issues"]["unresolved"]
    text = " ".join(blockers).lower()
    for required in ("transitive", "build", "hardware", "abi", "patch", "template",
                     "exclusive", "read-only", "measurement"):
        assert required in text
    for blocker in blockers:
        assert blocker in str(caught.value)
    assert all(report[key] is False for key in PROOF_FLAGS)


def test_require_reads_fresh_installed_metadata_on_every_call(api, monkeypatch):
    installed = dict(SELECTED)
    calls = _installed(monkeypatch, installed)
    with pytest.raises(api.NativeRuntimeError) as first:
        api.require_native_runtime()
    installed["transformers"] = "5.17.0.0"
    with pytest.raises(api.NativeRuntimeError) as second:
        api.require_native_runtime()
    assert first.value.report["issues"]["policy"] == []
    assert second.value.report["issues"]["policy"]
    assert Counter(calls) == Counter({package: 2 for package in PACKAGES})


@pytest.mark.parametrize("category", [
    "missing", "invalid", "native", "selected", "policy", "unresolved", None,
])
def test_enforcement_categories_exclude_default_frozen_diagnostics(api, monkeypatch, category):
    """Isolate aggregation only; real reports always retain unresolved blockers."""
    report = api.native_runtime_report(SELECTED)
    for entries in report["issues"].values():
        entries.clear()
    report["metadata_source"] = "installed"
    report["issues"]["frozen"] = ["default-only-sentinel"]
    if category in ("policy", "unresolved"):
        report["issues"][category] = ["blocking-sentinel"]
    elif category in ("missing", "invalid"):
        report["issues"][category] = {"torch": "blocking-sentinel"}
    elif category is not None:
        report["issues"][category] = {"torch": ["blocking-sentinel"]}
    monkeypatch.setattr(api, "_installed_report", lambda: report)
    if category is None:
        assert api.require_native_runtime() is report
    else:
        with pytest.raises(api.NativeRuntimeError, match="blocking-sentinel"):
            api.require_native_runtime()
