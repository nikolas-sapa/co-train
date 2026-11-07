"""Opt-in synthetic CPU reader conformance, not native training qualification."""

from __future__ import annotations

import importlib
import io
from pathlib import Path
import pickle
import random
from types import SimpleNamespace
from typing import Any, Callable


MAX_FILE_BYTES = 65536
MAX_TOTAL_BYTES = 524288
MAX_FILES = 16
MAX_TENSOR_ELEMENTS = 8192
MAX_TENSOR_BYTES = 65536
CASE_NAMES = (
    "optimizer", "scheduler", "scaler", "rng", "adapter",
    "unapproved_member", "sentinel_optimizer", "sentinel_rng",
    "numpy_optimizer", "ambient_globals", "nonzip", "malformed_safetensors",
)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _runtime() -> SimpleNamespace:
    try:
        return SimpleNamespace(
            torch=importlib.import_module("torch"),
            numpy=importlib.import_module("numpy"),
            safetensors_torch=importlib.import_module("safetensors.torch"),
            safetensors=importlib.import_module("safetensors"),
        )
    except ImportError as error:
        raise RuntimeError(
            "real CPU probe requires installed torch, numpy and safetensors"
        ) from error


class _LimitedBuffer(io.BytesIO):
    def write(self, data: bytes) -> int:
        _require(self.tell() + len(data) <= MAX_FILE_BYTES,
                 "serialized file exceeds fixed cap")
        return super().write(data)


def _write_bytes(path: Path, raw: bytes, sizes: dict[Path, int]) -> None:
    _require(len(raw) <= MAX_FILE_BYTES, "individual file cap exceeded")
    _require(len(sizes) < MAX_FILES, "file count cap exceeded")
    _require(sum(sizes.values()) + len(raw) <= MAX_TOTAL_BYTES,
             "aggregate file cap exceeded")
    with path.open("xb") as stream:
        _require(stream.write(raw) == len(raw), "short probe file write")
    sizes[path] = len(raw)


def _check_tensors(value: Any, dependencies: SimpleNamespace) -> None:
    total = 0

    def visit(item: Any) -> None:
        nonlocal total
        if dependencies.torch.is_tensor(item):
            _require(item.device.type == "cpu", "CPU tensors only")
            count, size = item.numel(), item.numel() * item.element_size()
        elif isinstance(item, dependencies.numpy.ndarray):
            count, size = item.size, item.nbytes
        elif type(item) is dict:
            for child in item.values():
                visit(child)
            return
        elif type(item) in (tuple, list):
            for child in item:
                visit(child)
            return
        else:
            return
        _require(count <= MAX_TENSOR_ELEMENTS, "tensor element cap exceeded")
        total += size
        _require(total <= MAX_TENSOR_BYTES, "aggregate tensor byte cap exceeded")

    visit(value)


def _layout(value: Any, dependencies: SimpleNamespace) -> Any:
    if dependencies.torch.is_tensor(value):
        return (str(value.dtype), tuple(value.shape), value.device.type)
    if isinstance(value, dependencies.numpy.ndarray):
        return (str(value.dtype), tuple(value.shape))
    if type(value) is dict:
        return {key: _layout(item, dependencies) for key, item in value.items()}
    if type(value) in (tuple, list):
        return type(value)(_layout(item, dependencies) for item in value)
    return type(value).__name__


def _save_state(
    path: Path, value: Any, dependencies: SimpleNamespace, sizes: dict[Path, int],
) -> None:
    _check_tensors(value, dependencies)
    with _LimitedBuffer() as stream:
        dependencies.torch.save(value, stream)
        _write_bytes(path, stream.getvalue(), sizes)


def _expect_refusal(
    label: str, action: Callable[[], Any], expected: type[Exception], message: str,
) -> None:
    try:
        action()
    except Exception as error:
        if type(error) is not expected or message not in str(error):
            raise AssertionError(f"{label}: wrong refusal: {type(error).__name__}") from error
    else:
        raise AssertionError(f"{label}: refusal control unexpectedly accepted")


def _refused_callable() -> None:
    raise RuntimeError("safe conformance sentinel was incorrectly executed")


class _Sentinel:
    def __reduce__(self) -> tuple[Any, tuple[Any, ...]]:
        return _refused_callable, ()


def run_cpu_conformance(work_dir: Path, *, opt_in: bool = False) -> dict[str, Any]:
    """Parent-only call in an approved runtime; keeps generated files, no cleanup."""
    _require(opt_in is True, "explicit opt_in=True required")
    native = importlib.import_module("train.native_qualification")
    native._path(work_dir)
    _require(not work_dir.exists(), "fresh probe destination required")
    _require(work_dir.parent.is_dir(), "existing probe parent required")
    dependencies = _runtime()
    torch, numpy = dependencies.torch, dependencies.numpy
    serialization = torch.serialization
    _require(callable(getattr(serialization, "get_safe_globals", None)),
             "Torch safe-global inspection API required")
    _require(callable(getattr(serialization, "safe_globals", None)),
             "Torch scoped safe-global API required")
    before_globals = serialization.get_safe_globals()
    _require(before_globals == [], "probe requires empty ambient Torch safe globals")
    work_dir.mkdir(mode=0o700)
    sizes: dict[Path, int] = {}
    cases: list[str] = []

    def checkpoint(name: str) -> Path:
        directory = work_dir / name
        directory.mkdir(mode=0o700)
        return directory

    def compare(label: str, expected: Any, actual: Any) -> None:
        _check_tensors(actual, dependencies)
        _require(native._equal(expected, actual, dependencies),
                 f"{label}: reader round trip differs")
        _require(_layout(expected, dependencies) == _layout(actual, dependencies),
                 f"{label}: reader tensor layout differs")
        cases.append(label)

    def refuse(label: str, action: Callable[[], Any],
               expected: type[Exception], message: str) -> None:
        _expect_refusal(label, action, expected, message)
        cases.append(label)

    positive = checkpoint("positive")
    vector = torch.tensor([0.25, -0.5], dtype=torch.float32, device="cpu")
    states = {
        "optimizer.pt": {
            "state": {0: {"step": torch.tensor(1.0, device="cpu"),
                          "exp_avg": vector, "exp_avg_sq": vector.square()}},
            "param_groups": [{"params": [0], "lr": 0.001, "betas": (0.9, 0.999),
                              "eps": 1e-8, "weight_decay": 0.01}],
        },
        "scheduler.pt": {"last_epoch": 1, "_step_count": 2, "base_lrs": [0.001],
                         "_last_lr": [0.001]},
        "scaler.pt": {"scale": 65536.0, "growth_factor": 2.0,
                      "backoff_factor": 0.5, "growth_interval": 2000,
                      "_growth_tracker": 1},
        "rng_state.pth": {
            "python": random.Random(17).getstate(),
            "numpy": numpy.random.RandomState(17).get_state(),
            "cpu": torch.Generator(device="cpu").manual_seed(17).get_state(),
        },
    }
    try:
        for label, name in (
            ("optimizer", "optimizer.pt"), ("scheduler", "scheduler.pt"),
            ("scaler", "scaler.pt"), ("rng", "rng_state.pth"),
        ):
            _save_state(positive / name, states[name], dependencies, sizes)
            compare(label, states[name], native._load_native_state(positive, name, dependencies))

        adapter = {"probe.lora_A.weight": vector.reshape(1, 2).contiguous()}
        _check_tensors(adapter, dependencies)
        _write_bytes(positive / "adapter_model.safetensors",
                     dependencies.safetensors_torch.save(adapter), sizes)
        compare("adapter", adapter, native._load_adapter_state(positive))

        refuse("unapproved_member",
               lambda: native._load_native_state(positive, "training_args.bin", dependencies),
               ValueError, "unapproved native deserializer member")
        for label, name in (
            ("sentinel_optimizer", "optimizer.pt"), ("sentinel_rng", "rng_state.pth"),
        ):
            directory = checkpoint(label)
            _save_state(directory / name, {"sentinel": _Sentinel()}, dependencies, sizes)
            refuse(label, lambda directory=directory, name=name:
                   native._load_native_state(directory, name, dependencies),
                   pickle.UnpicklingError, "_refused_callable")

        numpy_directory = checkpoint("numpy_optimizer")
        _save_state(numpy_directory / "optimizer.pt", states["rng_state.pth"],
                    dependencies, sizes)
        refuse("numpy_optimizer",
               lambda: native._load_native_state(numpy_directory, "optimizer.pt", dependencies),
               pickle.UnpicklingError, "_reconstruct")

        # Deliberately pollute only this scoped control; never deserialize the sentinel here.
        with serialization.safe_globals([_refused_callable]):
            refuse("ambient_globals",
                   lambda: native._load_native_state(positive, "optimizer.pt", dependencies),
                   ValueError, "unreviewed ambient Torch deserialization allowlist")

        invalid_zip = checkpoint("nonzip")
        _write_bytes(invalid_zip / "optimizer.pt", b"not a torch archive", sizes)
        refuse("nonzip",
               lambda: native._load_native_state(invalid_zip, "optimizer.pt", dependencies),
               ValueError, "invalid native tensor archive")
        invalid_adapter = checkpoint("malformed_safetensors")
        _write_bytes(invalid_adapter / "adapter_model.safetensors", b"bad", sizes)
        refuse("malformed_safetensors", lambda: native._load_adapter_state(invalid_adapter),
               dependencies.safetensors.SafetensorError, "header")
    finally:
        _require(serialization.get_safe_globals() == before_globals,
                 "probe changed ambient Torch safe globals")

    _require(tuple(cases) == CASE_NAMES, "incomplete CPU reader conformance cases")
    _require(len(sizes) == 10, "unexpected generated probe file count")
    return {
        "scope": "SYNTHETIC_CPU_CHECKPOINT_READERS_ONLY",
        "passed_cases": tuple(cases),
        "versions": {"torch": torch.__version__, "numpy": numpy.__version__,
                     "safetensors": dependencies.safetensors.__version__},
        "files": {str(path.relative_to(work_dir)): size for path, size in sizes.items()},
        "total_bytes": sum(sizes.values()),
        "training_verified": False,
        "production_admitted": False,
    }
