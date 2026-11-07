"""Private, explicitly admitted observations. Never production authorization.

Cold import uses stdlib only and performs no discovery. The trusted host must
admit the requested operations and bound the process lifetime, logs and billing
externally. An in-process probe cannot interrupt a stuck import/CUDA call.
Source hashes describe selected files, not loaded code identity or full custody.
The optional kernel observation covers one tiny FP16 matmul, not native training,
vLLM/Unsloth kernels, ABI compatibility or scientific readiness.
"""

from __future__ import annotations

import platform
import re
import struct
import sys
import sysconfig
from typing import Any, Callable

_EXACT = {
    "unsloth": "2026.10.3",
    "unsloth_zoo": "2026.10.3",
    "trl": "1.13.0",
    "transformers": "5.17.0",
    "vllm": "0.23.0",
    "torch": "2.11.0",
    "accelerate": "1.4.0",
    "datasets": "4.8.5",
}
_FLAGS = (
    "candidate_approved", "dependency_graph_verified", "abi_verified",
    "runtime_verified", "training_verified", "launch_authorized",
)
_CATEGORIES = ("missing", "invalid", "native", "selected", "policy")


def _implementation_name() -> str:
    return sys.implementation.name


def _load_frameworks() -> Any:
    from train import native_training

    return native_training._load_runtime()


def _safe_version(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is str and 1 <= len(value) <= 64 and re.fullmatch(
        r"[0-9A-Za-z.+_-]+", value
    ):
        return value
    return "<invalid>"


def _host_issues() -> list[str]:
    issues = []
    if sys.version_info[:2] != (3, 12):
        issues.append("host:python")
    if platform.system() != "Linux":
        issues.append("host:system")
    if platform.machine() != "x86_64":
        issues.append("host:architecture")
    if struct.calcsize("P") != 8:
        issues.append("host:pointer_width")
    if _implementation_name() != "cpython":
        issues.append("host:implementation")
    if sysconfig.get_config_var("SOABI") != "cpython-312-x86_64-linux-gnu":
        issues.append("host:soabi")
    return issues


def _inspect_loaded(report: dict[str, Any], versions: dict[str, Any]) -> bool:
    from train import native_qualification

    roots = {}
    sources = {}
    issues = report["issues"]
    for name in _EXACT:
        module = sys.modules.get(name)
        if module is None:
            roots[name] = "not_loaded"
            issues.append(f"not_loaded:{name}")
        elif _safe_version(getattr(module, "__version__", None)) != versions[name]:
            roots[name] = "version_mismatch"
            issues.append(f"loaded_version:{name}")
        else:
            roots[name] = "version_observed"
    # Reuse the frozen qualification representation pins, never caller hashes.
    for name in native_qualification._SELECTED_SOURCES:
        if sys.modules.get(name) is None:
            sources[name] = "not_loaded"
            issues.append(f"not_loaded:{name}")
            continue
        try:
            native_qualification._selected_module(name)
        except Exception:
            sources[name] = "drift_or_unreadable"
            issues.append(f"source:{name}")
        else:
            sources[name] = "selected_bytes_observed"
    clean = not issues
    report["loaded"] = {
        "status": "observed" if clean else "blocked",
        "roots": roots, "sources": sources,
        "scope": "version_attributes_and_selected_file_bytes_only",
    }
    return clean


def _inspect_device(torch: Any, report: dict[str, Any]) -> bool:
    try:
        build = getattr(torch.version, "cuda", None)
        if (
            type(build) is not str or len(build) > 16
            or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}", build) is None
        ):
            raise ValueError("CUDA build marker absent or malformed")
        available = torch.cuda.is_available()
        count = torch.cuda.device_count()
        if available is not True or type(count) is not int or count != 1:
            raise ValueError("exactly one available CUDA device required")
        props = torch.cuda.get_device_properties(0)
        values = {
            name: getattr(props, name, None)
            for name in ("major", "minor", "total_memory", "multi_processor_count")
        }
        bounds = {
            "major": (1, 99), "minor": (0, 99),
            "total_memory": (1, 2**63 - 1),
            "multi_processor_count": (1, 1000000),
        }
        if any(
            type(values[name]) is not int or not low <= values[name] <= high
            for name, (low, high) in bounds.items()
        ):
            raise ValueError("malformed device properties")
    except Exception:
        report["device"] = {"status": "blocked"}
        report["issues"].append("device_unavailable_or_malformed")
        return False
    report["device"] = {
        "status": "observed", "cuda_build_marker": build, **values,
        "scope": "device_properties_only_not_hardware_or_abi_support",
    }
    return True


def _inspect_kernel(torch: Any, report: dict[str, Any]) -> None:
    report["kernel"] = {
        "status": "failed", "scope": "single_fp16_2x2_matmul_only",
    }
    try:
        value = torch.ones((2, 2), device="cuda:0", dtype=torch.float16)
        result = value @ value
        torch.cuda.synchronize(0)
        if result.tolist() != [[2.0, 2.0], [2.0, 2.0]]:
            raise ValueError("kernel result mismatch")
    except Exception:
        report["issues"].append("kernel_operation_failed")
        return
    report["kernel"]["status"] = "observed"


def _probe_runtime(
    *, admit: Callable[..., None], exercise_kernel: bool = False,
) -> dict[str, Any]:
    """Call only in an externally admitted disposable process.

    ``admit(exercise_kernel=...)`` must raise unless the trusted owner has
    independently admitted this scope, identity, lifetime and all-charge budget.
    No default adapter, bool/token/report approval, CLI or production wiring is
    provided. Admission errors propagate; inspection errors become fixed codes.
    Returned report is JSON-safe and <16384 bytes for the frozen tables. Imported
    frameworks may emit logs outside this report, requiring host output limits.
    """
    if type(exercise_kernel) is not bool or not callable(admit):
        raise TypeError("explicit admission callback and bool kernel choice required")
    if admit(exercise_kernel=exercise_kernel) is not None:
        raise TypeError("admission callback must return None or raise")
    report: dict[str, Any] = {
        "schema_version": 1,
        "scope": "private_runtime_observations_only",
        "host": {"status": "UNRUN"},
        "installed": {"status": "UNRUN"},
        "loaded": {"status": "UNRUN"},
        "device": {"status": "UNRUN"},
        "kernel": {"status": "UNRUN"},
        "issues": [],
        **dict.fromkeys(_FLAGS, False),
    }
    try:
        host_issues = _host_issues()
    except Exception:
        host_issues = ["host_inspection_failed"]
    report["issues"].extend(host_issues)
    report["host"]["status"] = "blocked" if host_issues else "observed"
    try:
        from train import native_runtime

        installed = native_runtime.native_runtime_report()
        versions = installed["versions"]
        metadata_issues = [
            f"metadata:{name}" for name in _CATEGORIES
            if installed["issues"][name]
        ]
        if installed["metadata_source"] != "installed":
            metadata_issues.append("metadata:not_installed")
        for name, exact in _EXACT.items():
            if type(versions.get(name)) is not str or versions[name] != exact:
                metadata_issues.append(f"exact:{name}")
        report["installed"] = {
            "status": "blocked" if metadata_issues else "observed",
            "source": "installed",
            "versions": {
                name: _safe_version(versions.get(name)) for name in (*_EXACT, "peft")
            },
            "unresolved_count": len(installed["issues"]["unresolved"]),
            "frozen_count": len(installed["issues"]["frozen"]),
            "scope": "selected_distribution_metadata_only",
        }
        report["issues"].extend(metadata_issues)
    except Exception:
        report["installed"] = {"status": "blocked"}
        report["issues"].append("metadata_inspection_failed")
    if report["issues"]:
        return report
    try:
        runtime = _load_frameworks()
        clean = _inspect_loaded(report, versions)
    except Exception:
        report["loaded"] = {"status": "blocked"}
        report["issues"].append("framework_inspection_failed")
        return report
    if not clean or not _inspect_device(runtime.torch, report):
        return report
    if exercise_kernel:
        _inspect_kernel(runtime.torch, report)
    return report
