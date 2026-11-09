"""Static publication checks only. Never imports project modules or runs probes."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 131_072
MAX_TOTAL_BYTES = 5 * 1024 * 1024
PINNED = {
    "train/qualification_isolated_owner.py": "684a5ed32b5642415aa50b7be69c255a106363100eeacdedc67050ba08eee99a",
    "train/qualification_isolated_deadline.py": "9611f2c81c2ba8bbeb5da442c52149178ca1520369138fc2b7850d0132117d5d",
    "train/qualification_isolated_program.py": "9802e2a2a94e1004260f685aac951fa180c801b3d2b9063e940055e42c0d0022",
    "train/qualification_isolated_worker.py": "0b332f5f2d4b58904d9543c8f5a64cfbeae0ba2dba7ae7f4f90bee187c652d73",
    "train/qualification_owned_stop.py": "8da0f651085b95427bdec9c5ef5e55dd7e2a8189ddbd8780a2958f1ece4a96f1",
    "train/qualification_modal_host.py": "0e343c797a8f8bcfe89947390fe7ff1371d1bed6f8838884fc06d782cc021197",
    "train/qualification_isolated_run.py": "0e44e19da1a28d66b4cdbf1f92a5686f9fce6103db86eb0410cc429f73f27291",
    "train/qualification_engineering_host.py": "87f2e77703f14ade5428cf25b9641760c271c33d7959ee3c9407c42585989196",
    "train/qualification_engineering_run.py": "8fb10c1571867d920e8479d6e5352900b71d83b7c35b4232089e9aa5e770b8e9",
    "train/qualification_modal_transport.py": "c438546519b1c6999a774667235eec3d91c9fc35c2b4ca7dedd481a7912ce04d",
    "train/qualification_isolated_contract.py": "1f041021535135b3b6827fafb503f5a37c94e7c0127fb58ebbf5764a9595b5ee",
    "train/qualification_isolated_validation.py": "2b454f5e13be83cdcec3656e521ca0c364a7775d4943e164909bfc1ecd54f89a",
}


def read_source(relative: str) -> bytes:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Publication path escapes repository")
    target = ROOT / path
    if not stat.S_ISREG(target.lstat().st_mode):
        raise ValueError("Publication source is not a regular file")
    target.resolve(strict=True).relative_to(ROOT)
    with target.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Publication source exceeds per-file ceiling")
    return data


def assignments(source: bytes) -> dict[str, ast.expr]:
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                result[target.id] = node.value
    return result


def check_guard(source: bytes, expected: tuple[str, ...]) -> None:
    values = assignments(source)
    observed = ast.literal_eval(values["_PARENT_ONLY_TESTS"])
    if len(observed) != 19 or set(observed) != set(expected):
        raise ValueError("Parent-only collection exclusions differ")
    required = ast.parse(
        '[str(_ROOT / name) for name in '
        '(*_PARENT_ONLY_TESTS, "qualification_controls", "spec/spikes")]',
        mode="eval",
    ).body
    root = ast.parse("Path(__file__).parent", mode="eval").body
    if ast.dump(values["collect_ignore"]) != ast.dump(required):
        raise ValueError("Collector does not bind exclusions to repository root")
    if ast.dump(values["_ROOT"]) != ast.dump(root):
        raise ValueError("Collector root changed")


def check_reference_constants(
    directories: dict[str, list[int]], partial: list[int],
    expected_directories: dict[str, list[int]], expected_partial: list[int],
) -> None:
    if directories != expected_directories or partial != expected_partial:
        raise ValueError("Synthetic reference fixture constants disagree")


def main() -> None:
    manifest = json.loads(read_source("docs/engineering-publication-manifest.json"))
    rows = manifest["files"]
    if not 1 <= len(rows) <= 200 or len({row["path"] for row in rows}) != len(rows):
        raise ValueError("Publication manifest cardinality/uniqueness")
    total = 0
    python_sources = 0
    credential = re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|"
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
    )
    for row in rows:
        data = read_source(row["path"])
        total += len(data)
        if hashlib.sha256(data).hexdigest() != row["published_sha256"]:
            raise ValueError("Publication hash mismatch: " + row["path"])
        if re.search(rb"/Users/[A-Za-z0-9_.-]+(?:/|$)", data) or credential.search(data):
            raise ValueError("Private path/credential signature: " + row["path"])
        if re.search(
            rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            data,
        ):
            raise ValueError("Internal workflow identifier: " + row["path"])
        if row["path"].endswith(".py"):
            ast.parse(data, filename=row["path"])
            python_sources += 1
    if total > MAX_TOTAL_BYTES:
        raise ValueError("Publication text exceeds aggregate ceiling")
    for name, expected in PINNED.items():
        if hashlib.sha256(read_source(name)).hexdigest() != expected:
            raise ValueError("Frozen canonical source changed: " + name)
    guard = read_source("conftest.py")
    expected = tuple(manifest["parent_only_tests"])
    check_guard(guard, expected)
    tree = ast.parse(guard)
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_PARENT_ONLY_TESTS"
                    for t in node.targets)
        ):
            node.value.elts = [
                item for item in node.value.elts
                if ast.literal_eval(item) != "train/test_qualification_ac_volume.py"
            ]
            break
    try:
        check_guard(ast.unparse(tree).encode(), expected)
    except ValueError:
        negative_control = "MISSING_BULK_EXCLUSION_REFUSED"
    else:
        raise ValueError("Static negative control did not fail")
    fixture = assignments(read_source("train/test_qualification_timeout_recovery.py"))
    generation = json.loads(ast.literal_eval(fixture["GENERATION"]))
    receipt = json.loads(ast.literal_eval(fixture["RECEIPT"]))
    timeout = assignments(read_source("train/_qualification_timeout_recovery_fixture.py"))
    recovery = assignments(read_source("train/_qualification_volume_recovery_fixture.py"))
    directories = ast.literal_eval(timeout["DIRECTORIES"])
    partial = ast.literal_eval(recovery["PARTIAL_IDENTITY"])
    expected_directories = generation["source_directories"]
    expected_partial = receipt["partial_root_identity"]
    check_reference_constants(
        directories, partial, expected_directories, expected_partial,
    )
    mutant = {name: list(identity) for name, identity in directories.items()}
    mutant["."][1] += 1
    try:
        check_reference_constants(
            mutant, partial, expected_directories, expected_partial,
        )
    except ValueError:
        fixture_negative_control = "SYNTHETIC_FIXTURE_DRIFT_REFUSED"
    else:
        raise ValueError("Synthetic fixture negative control did not fail")
    print(json.dumps({
        "status": "STATIC_PUBLICATION_CHECKS_PASS",
        "listed_files": len(rows),
        "python_sources_parsed": python_sources,
        "text_bytes": total,
        "frozen_source_pins": len(PINNED),
        "parent_only_exclusions": len(expected),
        "negative_control": negative_control,
        "fixture_negative_control": fixture_negative_control,
        "synthetic_fixture_constant_crossrefs": "PASS",
        "historical_tests_executed": 0,
        "gpu_operations": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
