"""Selected distribution-metadata diagnostics, never runtime authorization.

The constraints describe the candidate in ``spec/native-training.md`` and
``research/2026-10-23-native-runtime-metadata.json``. They are not a dependency
resolver, complete graph, dynamic inspection of installed requirements or ABI
certificate. No training frameworks are imported.

The frozen Transformers<5 rule is delegated to ``guards.check_stack`` unchanged.
Native environments additionally require >=5.2, so production enforcement is
closed today regardless of whether the selected metadata bounds look plausible.
"""

from __future__ import annotations

import copy
import importlib.metadata as metadata
import platform
import re
from collections.abc import Mapping
from typing import Any

from train import guards

_PACKAGES = (
    "unsloth", "unsloth_zoo", "trl", "transformers", "torch", "vllm",
    "datasets", "accelerate", "peft",
)
_CANDIDATE_CORE = (
    ("unsloth", "2026.10.3"),
    ("unsloth_zoo", "2026.10.3"),
    ("trl", "1.13.0"),
    ("transformers", "5.17.0"),
)
_LIMITATIONS = (
    "Only selected direct constraints of the proposed core are checked; this "
    "is not full transitive dependency, extra or environment-marker resolution.",
    "Version metadata does not verify CUDA builds, driver/kernel ABI, hardware "
    "fit, released Unsloth patches or import order.",
    "Prerelease, development, postrelease, epoch and local/build version "
    "formats are unevaluable here, not assumed equivalent to release versions.",
    "Actual platform and Python are recorded, not certified as a supported "
    "Linux CUDA environment by these selected package checks.",
    "The candidate core is not owner-approved. No sampling, gradients, "
    "optimizer step, checkpoint restoration or launch authority is established.",
)

# Deliberately a small release-only grammar, not a partial PEP 440 parser.
# Length is checked before matching or integer conversion. Numeric components
# are ASCII, at most nine digits, with no leading-zero coercion.
_MAX_VERSION_LENGTH = 64
_RELEASE_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){1,3}"
)
_Release = tuple[int, int, int, int]

# Combined selected bounds where their intersection can be stated as an interval.
# Exclusions and vLLM's version-specific edges are checked separately below.
# package, inclusive lower, upper, upper inclusive, source/constraint diagnostic
_BOUNDS = (
    ("unsloth", (2026, 10, 3, 0), None, False,
     "selected Unsloth floor >=2026.10.3"),
    ("unsloth_zoo", (2026, 10, 3, 0), None, False,
     "Unsloth selected metadata requires unsloth_zoo>=2026.10.3"),
    ("trl", (0, 18, 2, 0), (1, 13, 0, 0), True,
     "Unsloth selected metadata requires trl>=0.18.2,<=1.13.0"),
    ("transformers", (4, 56, 2, 0), (5, 17, 0, 0), True,
     "TRL's general package floor and selected Unsloth/Zoo metadata require "
     "transformers>=4.56.2,<=5.17.0"),
    ("torch", (2, 4, 0, 0), (2, 15, 0, 0), False,
     "Unsloth selected metadata requires torch>=2.4.0,<2.15.0"),
    ("vllm", (0, 19, 1, 0), (0, 28, 0, 0), True,
     "TRL's selected vllm extra requires vllm>=0.19.1,<=0.28.0"),
    ("datasets", (4, 7, 0, 0), (5, 0, 0, 0), False,
     "selected TRL and Unsloth/Zoo metadata require datasets>=4.7.0,<5.0.0"),
    ("accelerate", (1, 4, 0, 0), None, False,
     "selected TRL metadata requires accelerate>=1.4.0"),
    ("peft", (0, 18, 0, 0), None, False,
     "selected Unsloth metadata requires peft>=0.18.0"),
)
_UNSLOTH_TRANSFORMERS_EXCLUSIONS = frozenset({
    (4, 53, 0, 0), (4, 54, 0, 0), (4, 55, 0, 0), (4, 55, 1, 0),
    (4, 57, 0, 0), (4, 57, 4, 0), (4, 57, 5, 0),
    (5, 0, 0, 0), (5, 1, 0, 0),
})


class NativeRuntimeError(RuntimeError):
    """Installed metadata has blockers; ``report`` preserves every diagnostic."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        diagnostics = []
        for category, entries in report["issues"].items():
            if isinstance(entries, list):
                diagnostics.extend(f"{category}: {message}" for message in entries)
            else:
                for package, messages in entries.items():
                    if isinstance(messages, str):
                        messages = [messages]
                    diagnostics.extend(
                        f"{category}/{package}: {message}" for message in messages
                    )
        super().__init__(
            "native runtime metadata is blocked; no launch is authorized:\n  - "
            + "\n  - ".join(diagnostics)
        )


def _parse_release(value: Any) -> _Release | None:
    if (
        type(value) is not str
        or not 1 <= len(value) <= _MAX_VERSION_LENGTH
        or _RELEASE_PATTERN.fullmatch(value) is None
    ):
        return None
    parts = [int(component) for component in value.split(".")]
    parts.extend([0] * (4 - len(parts)))
    return parts[0], parts[1], parts[2], parts[3]


def _issue(issues: dict[str, list[str]], package: str, message: str) -> None:
    issues.setdefault(package, []).append(message)


def _build_report(
    versions: Mapping[str, Any],
    source: str,
    read_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    # Preserve supplied values without sharing nested invalid fixture objects.
    values = copy.deepcopy({package: versions.get(package) for package in _PACKAGES})
    missing: dict[str, str] = {}
    invalid: dict[str, str] = dict(read_errors or {})
    parsed: dict[str, _Release] = {}
    for package, value in values.items():
        if package in invalid:
            continue
        if value is None:
            missing[package] = f"{package} distribution metadata is absent"
            continue
        release = _parse_release(value)
        if release is None:
            invalid[package] = (
                f"{package} version is unevaluable: require a release string with "
                "2-4 bounded ASCII numeric components (at most 64 characters, "
                "nine digits per component); no prerelease, postrelease or build suffix"
            )
        else:
            parsed[package] = release

    # Invalid metadata must not reach the older permissive parser. Passing None
    # means that frozen rule cannot evaluate it; ``invalid`` retains the distinct
    # reason. Valid/missing inputs reach the actual existing guard unchanged.
    frozen_values = {
        package: values[package] if package in parsed else None
        for package in _PACKAGES
    }
    frozen = guards.check_stack(frozen_values)
    native: dict[str, list[str]] = {}
    selected: dict[str, list[str]] = {}
    transformers = parsed.get("transformers")
    if transformers is not None and transformers < (5, 2, 0, 0):
        _issue(
            native, "transformers",
            "native TRL environment_factory requires transformers>=5.2.0, "
            "independently of TRL's general package floor",
        )

    for package, lower, upper, upper_inclusive, constraint in _BOUNDS:
        release = parsed.get(package)
        if release is None:
            continue
        above = upper is not None and (
            release > upper if upper_inclusive else release >= upper
        )
        if release < lower or above:
            _issue(selected, package, f"{package} {values[package]} violates {constraint}")

    if parsed.get("trl") == (0, 19, 0, 0):
        _issue(selected, "trl", "Unsloth selected metadata excludes trl 0.19.0")
    if transformers in _UNSLOTH_TRANSFORMERS_EXCLUSIONS:
        _issue(
            selected, "transformers",
            f"selected Unsloth metadata excludes transformers {values['transformers']}",
        )

    # The broad ranges above are not sufficient for this known vLLM release.
    if parsed.get("vllm") == (0, 23, 0, 0):
        torch = parsed.get("torch")
        if torch is not None and torch != (2, 11, 0, 0):
            _issue(
                selected, "torch",
                f"vllm 0.23.0 requires torch==2.11.0; found {values['torch']}; "
                "even release equality does not verify the CUDA build or ABI",
            )
        if transformers is not None and (
            transformers[:2] in {(5, minor) for minor in range(5)}
            or transformers == (5, 5, 0, 0)
        ):
            _issue(
                selected, "transformers",
                f"vllm 0.23.0 excludes transformers {values['transformers']} "
                "(5.0.* through 5.4.*, and 5.5.0)",
            )

    return {
        "schema_version": 1,
        "metadata_source": source,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "versions": values,
        "candidate_core": dict(_CANDIDATE_CORE),
        "metadata_scope": "selected_direct_constraints_only",
        "limitations": list(_LIMITATIONS),
        "issues": {
            "missing": missing,
            "invalid": invalid,
            "frozen": frozen,
            "native": native,
            "selected": selected,
        },
        "candidate_approved": False,
        "dependency_graph_verified": False,
        "abi_verified": False,
        "runtime_verified": False,
        "training_verified": False,
        "launch_authorized": False,
    }


def _installed_report() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    errors = {}
    for package in _PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
        except Exception as exc:
            # Continue collecting independent packages. Do not echo filesystem
            # paths or arbitrary exception values into the diagnostic.
            versions[package] = None
            errors[package] = (
                f"{package} installed distribution metadata could not be read "
                f"({type(exc).__name__})"
            )
    return _build_report(versions, "installed", errors)


def native_runtime_report(versions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Report fresh installed or explicitly labelled fixture metadata only."""
    if versions is None:
        return _installed_report()
    if not isinstance(versions, Mapping):
        raise TypeError("versions must be a package/version mapping or None")
    return _build_report(versions, "fixture")


def require_native_runtime() -> dict[str, Any]:
    """Enforce selected installed-metadata checks, never consume fixture reports.

    Current frozen/native Transformers requirements contradict, so this raises.
    Even a future return after an explicitly approved contract change would be
    a metadata report, not runtime verification or authorization to launch.
    """
    report = _installed_report()
    if any(report["issues"].values()):
        raise NativeRuntimeError(report)
    return report
