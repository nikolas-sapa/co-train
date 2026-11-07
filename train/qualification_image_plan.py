"""Private frozen source recipe, not an image, runtime proof or authorization.

The parent observed public tag metadata, not signed manifest/layer bytes.
Expected runtime values below are requirements, not observations.

Future public conversion is the text returned by registry_call_source(). This
module deliberately has no SDK import, constructor, callback or build adapter.
The independently trusted synchronous host must admit the exact operation and
all gross charges BEFORE importing Modal or evaluating that text. Never eval
untrusted recipe text. Metadata, JSON, bools and asynchronous callbacks cannot
grant host authority. Construction does not admit build/hydration: Image.build,
App.run and deployment can resolve/build images and need separate approval.

Official Modal 1.6.3 _image.py:2281-2364 accepts a digest as its tag argument,
requires linux/amd64, has no platform parameter, and returns a lazy Image.
_registry_setup_commands:2235-2278 adds pip layers for builders <=2024.10.
Before any resolution, parent must independently constrain/review the builder
version (>2024.10), generated recipe, mounts and runtime injection. No config
change, add_python, dependency layer or fallback is authorized here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import hashlib
import json


@dataclass(frozen=True)
class _CandidateRecipe:
    base_reference: str = (
        "docker.io/library/python@"
        "sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af"
    )
    platform: str = "linux/amd64"
    implementation: str = "cpython"
    python_version: str = "3.12.13"
    distro_codename: str = "bookworm"
    libc_version: str = "2.36"
    reported_compressed_size_bytes: int = 45421630


_FUTURE_CHECKS = (
    "Parent synchronous trusted-host exact-operation admission before SDK constructor.",
    "Separate build/hydration approval, USD25 gross all-charge ceiling before credits.",
    "One job/GPU, no retry/reroll, aggregate GPU lifetime <=1800s, external watchdog.",
    "Review effective Modal builder >2024.10 and actual generated layers/injected mounts.",
    "Verify child manifest/layer bytes and platform; public metadata is not a signature.",
    "Record actual provider object identity after admitted build, never guess image ID.",
    "Bind provider identity/base digest/recipe hash in trusted custody, not worker labels.",
    "Observe Linux x86_64 CPython3.12.13 64-bit cpython-312-x86_64-linux-gnu in job.",
    "Observe Debian bookworm and glibc2.36 from runtime, not Modal ImageMetadata.",
    "Admit exact 220-wheel/4400067018-byte filename/version/hash closure separately.",
    "Install only admitted local hash-pinned wheels offline inside single bounded job.",
    "No dependency installation in image build; no indexes, resolution, sdists or fallback.",
    "Keep setup/export/retention/teardown inside externally bounded all-charge ownership.",
    "Verify QualificationRequest FilePins/runtime_inventory and native_model inventory.",
    "Recipe SHA256 and request.image_digest are labels, not provider/runtime identity.",
    "Run native_preflight and existing loaded selected-source/device/kernel checks.",
    "Run native nonzero update/save and actual fresh-process restore/update with gates.",
    "Production/scientific readiness remains separate even after engineering qualification.",
)
_UNKNOWN_CATEGORIES = (
    "preparation", "build", "provisioning", "teardown", "storage", "retention", "egress",
)


def candidate_recipe() -> _CandidateRecipe:
    return _CandidateRecipe()


def validate_recipe(recipe: _CandidateRecipe) -> None:
    expected = _CandidateRecipe()
    if type(recipe) is not _CandidateRecipe:
        raise ValueError("exact private candidate recipe required")
    for item in fields(expected):
        actual, frozen = getattr(recipe, item.name), getattr(expected, item.name)
        if type(actual) is not type(frozen) or actual != frozen:
            raise ValueError(f"candidate recipe drift: {item.name}")


def dockerfile(recipe: _CandidateRecipe) -> str:
    validate_recipe(recipe)
    return f"FROM --platform={recipe.platform} {recipe.base_reference}\n"


def registry_call_source(recipe: _CandidateRecipe) -> str:
    """Inert documented public call, never execute on the cold/source-plan path."""
    validate_recipe(recipe)
    return (
        f"modal.Image.from_registry({recipe.base_reference!r}, secret=None, "
        "setup_dockerfile_commands=[], force_build=False, add_python=None)"
    )


def canonical_recipe(recipe: _CandidateRecipe) -> bytes:
    validate_recipe(recipe)
    return json.dumps({
        "schema": 1, "scope": "private_candidate_only", "recipe": asdict(recipe),
        "dockerfile": dockerfile(recipe), "public_call": registry_call_source(recipe),
        "future_checks": _FUTURE_CHECKS,
        "runtime_dependencies": "admitted_exact_offline_220_wheels_in_bounded_job_only",
        "unknown_charge_categories": _UNKNOWN_CATEGORIES,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def recipe_sha256(recipe: _CandidateRecipe) -> str:
    return hashlib.sha256(canonical_recipe(recipe)).hexdigest()


@dataclass(frozen=True)
class RuntimeObservation:
    base_digest: str | None = None
    recipe_sha256: str | None = None
    system: str | None = None
    machine: str | None = None
    implementation: str | None = None
    python_version: str | None = None
    soabi: str | None = None
    pointer_bits: int | None = None
    distro_id: str | None = None
    distro_codename: str | None = None
    libc_name: str | None = None
    libc_version: str | None = None


@dataclass(frozen=True)
class _CandidateReadiness:
    issues: tuple[str, ...]
    scope: str = field(default="private_candidate_only", init=False)
    candidate_approved: bool = field(default=False, init=False)
    dependency_graph_verified: bool = field(default=False, init=False)
    publisher_signature_verified: bool = field(default=False, init=False)
    runtime_verified: bool = field(default=False, init=False)
    abi_verified: bool = field(default=False, init=False)
    training_verified: bool = field(default=False, init=False)
    launch_authorized: bool = field(default=False, init=False)
    build_authorized: bool = field(default=False, init=False)
    cost_approved: bool = field(default=False, init=False)


def runtime_readiness(
    recipe: _CandidateRecipe, observation: RuntimeObservation | None = None,
) -> _CandidateReadiness:
    """Compare untrusted observations only. Matching every field cannot authorize."""
    validate_recipe(recipe)
    if observation is not None and type(observation) is not RuntimeObservation:
        raise TypeError("explicit RuntimeObservation required, not provider metadata")
    expected = RuntimeObservation(
        base_digest=recipe.base_reference.split("@", 1)[1],
        recipe_sha256=recipe_sha256(recipe), system="Linux", machine="x86_64",
        implementation=recipe.implementation, python_version=recipe.python_version,
        soabi="cpython-312-x86_64-linux-gnu", pointer_bits=64, distro_id="debian",
        distro_codename=recipe.distro_codename, libc_name="glibc",
        libc_version=recipe.libc_version,
    )
    issues = [
        "host_admission_REQUIRED", "provider_image_identity_UNKNOWN",
        "publisher_signature_UNKNOWN", "runtime_observation_untrusted",
        "native_qualification_UNRUN", "all_charge_approval_UNKNOWN",
    ]
    for item in fields(expected):
        actual = getattr(observation, item.name) if observation is not None else None
        wanted = getattr(expected, item.name)
        if type(actual) is not type(wanted) or actual != wanted:
            issues.append("runtime:" + item.name)
    return _CandidateReadiness(tuple(issues))


@dataclass(frozen=True)
class _ImageFootprint:
    reported_compressed_size_bytes: int = field(default=45421630, init=False)
    uncompressed_pull_bytes: int | None = field(default=None, init=False)
    build_workspace_bytes: int | None = field(default=None, init=False)
    stored_image_bytes: int | None = field(default=None, init=False)
    transfer_bytes: int | None = field(default=None, init=False)
    setup_seconds: int | None = field(default=None, init=False)
    provisioning_seconds: int | None = field(default=None, init=False)
    retention_seconds: int | None = field(default=None, init=False)
    teardown_seconds: int | None = field(default=None, init=False)


def image_footprint(recipe: _CandidateRecipe) -> _ImageFootprint:
    validate_recipe(recipe)
    return _ImageFootprint()


def unknown_image_charges(recipe: _CandidateRecipe) -> tuple[tuple[str, None], ...]:
    """Existing CostLedger/evaluate_costs must reject these UNKNOWN inputs.

    Never replace None with zero from compressed bytes or a matching image label.
    Parent must independently bound quantities, tariffs and billing tails before
    supplying a complete ledger; arithmetic alone still grants no approval.
    """
    validate_recipe(recipe)
    return tuple((category, None) for category in _UNKNOWN_CATEGORIES)
