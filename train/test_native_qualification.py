"""Model-free contracts, not native qualification or service authorization.

Only the parent runs these tests. Missing implementation fails inside each test,
not during collection. Tensor/serialization/assembly doubles are labelled unit
protocols; SQLite, preparation, Python tracing and harmless children are real.
"""

from __future__ import annotations

import builtins
from collections import Counter
from contextlib import contextmanager, nullcontext
import copy
import dataclasses
from decimal import Decimal
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import pickle
import random
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import weakref
import zipfile

import pytest


MODULE = "train.native_qualification"
REFUSAL = (ValueError, RuntimeError)
FORBIDDEN_IMPORTS = {
    "torch", "transformers", "trl", "unsloth", "unsloth_zoo", "vllm",
    "accelerate", "peft", "datasets", "modal", "boto3", "huggingface_hub",
}
FIXTURES = (("first", 17), ("second", 29), ("third", 41), ("fourth", 53))


def _implementation():
    assert importlib.util.find_spec(MODULE) is not None, (
        "missing train.native_qualification implementation, intended baseline RED"
    )
    return importlib.import_module(MODULE)


def _four_tasks(root):
    import sqlite3

    from bench.task import SqlTask

    tasks = []
    for name, value in FIXTURES:
        directory = root / name
        directory.mkdir(parents=True)
        database = directory / f"{name}.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE readings (amount INTEGER NOT NULL)")
            connection.execute("INSERT INTO readings VALUES (?)", (value,))
        tasks.append(SqlTask(
            name=name, question=f"What amount is recorded? FIXTURE_{name.upper()}",
            evidence="Use readings.", gold_sql=f"SELECT amount FROM readings /* GOLD_{name} */",
            db_id=name, db_path=str(database), tier="simple", tier_source="derived",
            shape="fixture-select", coarse_shape="fixture-select", source="fixture",
        ))
    return tuple(tasks)


def _bounds(api, **changes):
    values = dict(
        total_ceiling_usd=Decimal("25"), prior_usage_usd=Decimal("1"),
        remaining_worst_case_usd=Decimal("24"), lifetime_seconds=1800,
        output_bytes_per_phase=1024, artifact_bytes=1048576, retention_seconds=60,
    )
    values.update(changes)
    return api.AttemptBounds(**values)


def _pin(api, path):
    data = path.read_bytes()
    return api.FilePin(path=path, size=len(data), sha256=hashlib.sha256(data).hexdigest())


def _request(api, root):
    tasks = _four_tasks(root / "data")
    model = root / "model"
    model.mkdir()
    (model / "config.json").write_text('{"fixture":"transport-only"}', encoding="utf-8")
    inventory = root / "runtime-inventory.json"
    inventory.write_text('{"fixture":"not-runtime-proof"}', encoding="utf-8")
    source = Path(__file__).with_name("native_training.py")
    return api.QualificationRequest(
        tasks=tasks, db_root=root / "data", model_dir=model,
        output_dir=root / "export", source_pins=(_pin(api, source),),
        database_pins=tuple(_pin(api, Path(task.db_path)) for task in tasks),
        runtime_inventory=_pin(api, inventory), image_digest="sha256:" + "a" * 64,
        bounds=_bounds(api),
    )


def _refuses(label, action):
    with pytest.raises(REFUSAL, match=r".+") as caught:
        action()
    assert str(caught.value), f"{label}: refusal must explain the failed contract"


class TinyTensor:
    """Labelled scalar/vector protocol double, never a native tensor witness."""

    def __init__(self, values):
        self.values = list(values) if isinstance(values, (tuple, list)) else [values]
        self.requires_grad = True
        self.grad = None
        self.device = SimpleNamespace(type="cpu")
        self.dtype = "float32"

    def detach(self):
        return self

    def clone(self):
        return TinyTensor(self.values)

    def cpu(self):
        return self

    def to(self, *args, **kwargs):
        return self

    def float(self):
        return self

    def double(self):
        return self

    def flatten(self):
        return self

    def numel(self):
        return len(self.values)

    def item(self):
        assert len(self.values) == 1
        return self.values[0]

    def tolist(self):
        return list(self.values)

    def all(self):
        return TinyTensor(all(self.values))

    def any(self):
        return TinyTensor(any(self.values))

    def abs(self):
        return TinyTensor([abs(value) for value in self.values])

    def max(self):
        return TinyTensor(max(self.values))

    def sum(self):
        return TinyTensor(sum(self.values))

    def isfinite(self):
        return TinyTensor([math.isfinite(value) for value in self.values])

    def __bool__(self):
        return bool(self.item())

    def __sub__(self, other):
        values = other.values if isinstance(other, TinyTensor) else [other] * len(self.values)
        return TinyTensor([left - right for left, right in zip(self.values, values, strict=True)])

    def __eq__(self, other):
        if isinstance(other, TinyTensor):
            return TinyTensor(self.values == other.values)
        return TinyTensor([value == other for value in self.values])

    def __ne__(self, other):
        result = self == other
        return TinyTensor([not value for value in result.values])

    __hash__ = object.__hash__


class _Hook:
    def __init__(self, hooks, callback):
        self.hooks, self.callback = hooks, callback

    def remove(self):
        self.hooks.remove(self.callback)


class TinyOptimizer:
    """Original-step protocol double, with independently mutable native state."""

    def __init__(self, parameters):
        self.param_groups = [{"params": parameters, "lr": 0.01}]
        self.state = {parameter: {"step": TinyTensor(0), "exp_avg": TinyTensor(0)}
                      for parameter in parameters}
        self.pre_hooks, self.post_hooks = [], []
        self.steps = 0

    def register_step_pre_hook(self, callback):
        self.pre_hooks.append(callback)
        return _Hook(self.pre_hooks, callback)

    def register_step_post_hook(self, callback):
        self.post_hooks.append(callback)
        return _Hook(self.post_hooks, callback)

    def state_dict(self):
        return {
            "state": {index: copy.deepcopy(self.state[parameter])
                      for index, parameter in enumerate(self.param_groups[0]["params"])},
            "param_groups": [{"params": list(range(len(self.state))), "lr": 0.01}],
        }

    def step(self, *, move=True, advance=True):
        for hook in tuple(self.pre_hooks):
            assert hook(self, (), {}) is None, "observer pre-hook must not alter optimizer call"
        self.steps += 1
        for parameter in self.param_groups[0]["params"]:
            if move and parameter.grad is not None:
                parameter.values = [value - 0.01 * grad for value, grad in
                                    zip(parameter.values, parameter.grad.values, strict=True)]
            if advance:
                self.state[parameter]["step"].values[0] += 1
                self.state[parameter]["exp_avg"].values[0] += 0.1
        for hook in tuple(self.post_hooks):
            assert hook(self, (), {}) is None, "observer post-hook must not alter optimizer return"


def _optimizer_spec():
    roles = {
        role: (function.__code__, function.__globals__, function.__defaults__,
               function.__kwdefaults__)
        for role, function in (
            ("base_init", TinyOptimizer.__init__), ("raw", TinyOptimizer.step),
            ("pre_hook", TinyOptimizer.register_step_pre_hook),
            ("post_hook", TinyOptimizer.register_step_post_hook),
        )
    }
    return SimpleNamespace(
        topology="direct", base=TinyOptimizer,
        classes=((TinyOptimizer, (object,), "base_init"),), roles=roles,
    )


def _unit_patch_optimizer_step(accelerated_optimizer, method):
    def patched_step(*args, **kwargs):
        accelerated_optimizer._called = True
        return method(*args, **kwargs)
    return patched_step


def _wrapped_optimizer_fixture(api, monkeypatch, unit):
    """Known harmless wrapper graph, not native optimizer qualification."""
    class Native(TinyOptimizer):
        def __init__(self, parameters):
            super().__init__(parameters)

        def step(self, *, move=True, advance=True):
            self.steps += 1
            for parameter in self.param_groups[0]["params"]:
                if move and parameter.grad is not None:
                    parameter.values = [value - 0.01 * grad for value, grad in
                                        zip(parameter.values, parameter.grad.values, strict=True)]
                if advance:
                    self.state[parameter]["step"].values[0] += 1
                    self.state[parameter]["exp_avg"].values[0] += 0.1

        def _optimizer_step_code(self):
            pass

        def _patch_step_function(self):
            pass

    class Scaler:
        def __init__(self):
            self._enabled = True

        def step(self, optimizer, **kwargs):
            return self._maybe_opt_step(optimizer, **kwargs)

        def _maybe_opt_step(self, optimizer, **kwargs):
            return optimizer.step(**kwargs)

    class Outer(TinyOptimizer):
        def __init__(self, optimizer, scaler):
            self.optimizer, self.scaler = optimizer, scaler
            self._optimizer_original_step_method = optimizer.step
            self._optimizer_patched_step_method = _unit_patch_optimizer_step(self, optimizer.step)

        def step(self, **kwargs):
            self.optimizer.step = self._optimizer_patched_step_method
            try:
                return self.scaler.step(self.optimizer, **kwargs)
            finally:
                self.optimizer.step = self._optimizer_original_step_method

    class Scheduler:
        pass

    def grad_wrapper(func):
        def use_grad(*args, **kwargs):
            return func(*args, **kwargs)
        use_grad.__wrapped__ = func
        return use_grad

    def profile_wrapper(func):
        def wrapper(*args, **kwargs):
            optimizer = args[0]
            for hook in tuple(optimizer.pre_hooks):
                assert hook(optimizer, args, kwargs) is None
            result = func(*args, **kwargs)
            optimizer._optimizer_step_code()
            for hook in tuple(optimizer.post_hooks):
                assert hook(optimizer, args, kwargs) is None
            return result
        wrapper.__wrapped__ = func
        return wrapper

    def scheduler_wrapper(func, opt_ref):
        def wrapper(*args, **kwargs):
            optimizer = opt_ref()
            return func.__get__(optimizer, type(optimizer))(*args, **kwargs)
        wrapper.__wrapped__ = func
        return wrapper

    raw = Native.step
    grad = grad_wrapper(raw)
    profile = profile_wrapper(grad)
    Native.step = profile
    base = Native(unit.parameters)
    scale = Scaler()
    outer = Outer(base, scale)
    wrapper = scheduler_wrapper(Outer.step, weakref.ref(outer))
    outer.step = wrapper
    scheduler = Scheduler()
    scheduler.optimizer, scheduler.last_epoch = outer, 0
    trainer = unit.trainer
    trainer.optimizer, trainer.lr_scheduler, trainer.accelerator.scaler = outer, scheduler, scale
    functions = {
        "base_init": TinyOptimizer.__init__, "native_init": Native.__init__,
        "outer_init": Outer.__init__, "scaler_init": Scaler.__init__,
        "pre_hook": TinyOptimizer.register_step_pre_hook,
        "post_hook": TinyOptimizer.register_step_post_hook,
        "step_code": Native._optimizer_step_code, "patch_function": Native._patch_step_function,
        "raw": raw, "grad": grad, "profile": profile, "outer": Outer.step,
        "patch": outer._optimizer_patched_step_method, "scheduler": wrapper,
        "scaler_step": Scaler.step, "scaler_maybe": Scaler._maybe_opt_step,
    }
    spec = SimpleNamespace(
        topology="accelerated", base=Native, outer=Outer, scaler=Scaler, scheduler=Scheduler,
        classes=((TinyOptimizer, (object,), "base_init"),
                 (Native, (TinyOptimizer,), "native_init"),
                 (Outer, (TinyOptimizer,), "outer_init"), (Scaler, (object,), "scaler_init")),
        roles={name: (fn.__code__, fn.__globals__, fn.__defaults__, fn.__kwdefaults__)
               for name, fn in functions.items()},
    )
    monkeypatch.setattr(api, "_expected_optimizer_implementations", lambda: spec)
    return SimpleNamespace(
        base=base, outer=outer, scale=scale, raw=raw, grad=grad, profile=profile,
        wrapper=wrapper, spec=spec, scheduler_wrapper=scheduler_wrapper,
        profile_wrapper=profile_wrapper, grad_wrapper=grad_wrapper,
        patch_optimizer_step=_unit_patch_optimizer_step,
    )


class _UnitTrainer:
    """Harmless loaded Python methods, not an alternative training engine."""

    def _inner_training_loop(self):
        if hasattr(self, "_unit_action"):
            return self._unit_action()
        return None

    def _load_rng_state(self, checkpoint):
        if self.restore_error:
            raise RuntimeError("restore raised with profile return argument None")
        saved = self.saved_rng
        random.setstate(saved["python"])
        self.rng.numpy = copy.deepcopy(saved["numpy"])
        self.rng.cpu = saved["cpu"].clone()
        self.rng.cuda = saved["cuda"].clone()
        if self.rng_mismatch == "python":
            random.random()
        elif self.rng_mismatch == "numpy":
            self.rng.numpy[1][0] += 1
        elif self.rng_mismatch == "cpu":
            self.rng.cpu.values[0] += 1
        elif self.rng_mismatch == "cuda":
            self.rng.cuda.values[0] += 1
        self.events.append("restore-normal")
        return None

    def _generate_and_score_completions(self, inputs):
        self.events.append("generation")
        return inputs

    def _save_checkpoint(self, model, trial=None):
        self.events.append("native-save")

    def train(self, *, resume_from_checkpoint=None):
        self.train_calls.append(resume_from_checkpoint)
        if hasattr(self, "_unit_action"):
            return self._inner_training_loop()
        return None


def _unit_trainer(api, monkeypatch, root):
    root.mkdir(parents=True, exist_ok=True)
    parameters = [TinyTensor(1.0), TinyTensor(2.0)]
    parameters[0].grad, parameters[1].grad = TinyTensor(0.5), TinyTensor(0.0)
    names = (
        "base_model.model.layer.lora_A.default.weight",
        "base_model.model.layer.lora_B.default.weight",
    )
    optimizer = TinyOptimizer(parameters)
    rng = SimpleNamespace(
        numpy=("MT19937", [11, 12], 0, 0, 0.0),
        cpu=TinyTensor([21, 22]), cuda=TinyTensor([31, 32]),
    )
    trainer = _UnitTrainer()
    trainer.__dict__.update(
        model=SimpleNamespace(
            named_parameters=lambda: iter(zip(names, parameters, strict=True)),
            parameters=lambda: iter(parameters),
            state_dict=lambda *, keep_vars=False: {
                name: parameter if keep_vars else parameter.detach().clone()
                for name, parameter in zip(names, parameters, strict=True)
            },
            peft_config={"default": SimpleNamespace(peft_type="LORA")},
            active_adapter="default",
        ),
        optimizer=optimizer,
        lr_scheduler=SimpleNamespace(
            last_epoch=0, state_dict=lambda: {"last_epoch": trainer.lr_scheduler.last_epoch},
        ),
        accelerator=SimpleNamespace(
            sync_gradients=True, optimizer_step_was_skipped=False,
            scaler=SimpleNamespace(state_dict=lambda: {
                "scale": 65536.0, "growth_factor": 2.0, "backoff_factor": 0.5,
                "growth_interval": 2000, "_growth_tracker": 0,
            }),
            unwrap_model=lambda model: model,
        ),
        args=SimpleNamespace(
            max_steps=2, num_generations=4, per_device_train_batch_size=8,
            gradient_accumulation_steps=2, generation_batch_size=16,
            steps_per_generation=2, num_iterations=1, save_only_model=False,
            output_dir=str(root), fp16=True,
        ),
        state=SimpleNamespace(global_step=0, max_steps=2, epoch=0),
        control=SimpleNamespace(should_save=False, should_training_stop=False),
        use_adaptive_entropy=True, entropy_coef=0.1, _last_world_entropy=0.5,
        _entropy_window_stats=None, _step=2,
        events=[], train_calls=[], restore_error=False, rng_mismatch=None,
        rng=rng,
    )
    trainer.saved_rng = {
        "python": random.getstate(), "numpy": copy.deepcopy(rng.numpy),
        "cpu": rng.cpu.clone(), "cuda": rng.cuda.clone(),
    }
    loads = []
    checkpoint_states = {}

    def load(path, *, weights_only, **kwargs):
        assert weights_only is True, "every checkpoint torch.load must use weights_only=True"
        if isinstance(path, (str, os.PathLike)):
            assert Path(path).is_file(), "reader must not synthesize missing native members"
        name = Path(getattr(path, "name", path)).name
        assert name != "training_args.bin", "training_args.bin must never be deserialized"
        loads.append((name, weights_only))
        assert name in checkpoint_states, f"unexpected serializer member: {name}"
        return copy.deepcopy(checkpoint_states[name])

    allowed_globals = []

    @contextmanager
    def safe_globals(allowed):
        assert all(getattr(value, "__module__", "").startswith("numpy") for value in allowed), (
            "allowlist must be native NumPy RNG types only"
        )
        previous = list(allowed_globals)
        allowed_globals.extend(allowed)
        try:
            yield
        finally:
            allowed_globals[:] = previous

    def export(model, *, state_dict, adapter_name, save_embedding_layers):
        assert adapter_name == "default" and save_embedding_layers is False
        assert all(state_dict[name] is parameter for name, parameter in model.named_parameters())
        return {name.replace(".default.", "."): parameter
                for name, parameter in state_dict.items() if "lora_" in name}

    torch = SimpleNamespace(
        Tensor=TinyTensor, is_tensor=lambda value: isinstance(value, TinyTensor),
        isfinite=lambda value: value.isfinite(),
        equal=lambda left, right: left.values == right.values,
        allclose=lambda left, right, **kwargs: left.values == right.values,
        any=lambda value: value.any(), all=lambda value: value.all(),
        count_nonzero=lambda value: TinyTensor(sum(item != 0 for item in value.values)),
        load=load, get_rng_state=lambda: rng.cpu.clone(),
        set_rng_state=lambda value: setattr(rng, "cpu", value.clone()),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_rng_state=lambda: rng.cuda.clone(),
            set_rng_state=lambda value: setattr(rng, "cuda", value.clone()),
            get_rng_state_all=lambda: [rng.cuda.clone()],
            set_rng_state_all=lambda values: setattr(rng, "cuda", values[0].clone()),
        ),
        serialization=SimpleNamespace(
            safe_globals=safe_globals, get_safe_globals=lambda: list(allowed_globals),
        ),
    )
    torch.cuda.random = torch.cuda
    dependencies = SimpleNamespace(
        torch=torch, TrainerCallback=type("UnitTrainerCallback", (), {}),
        get_peft_model_state_dict=export,
        numpy=SimpleNamespace(
            random=SimpleNamespace(
                get_state=lambda: copy.deepcopy(rng.numpy),
                set_state=lambda value: setattr(rng, "numpy", copy.deepcopy(value)),
            ),
            array_equal=lambda left, right: left == right,
        ),
    )
    expected_codes = {
        name: getattr(_UnitTrainer, name).__code__ for name in (
            "train", "_inner_training_loop", "_load_rng_state",
            "_generate_and_score_completions", "_save_checkpoint",
        )
    }
    monkeypatch.setattr(api, "_observer_dependencies", lambda: dependencies)
    monkeypatch.setattr(api, "_expected_method_codes", lambda current: expected_codes)
    optimizer_spec = _optimizer_spec()
    monkeypatch.setattr(api, "_expected_optimizer_implementations", lambda: optimizer_spec)
    return SimpleNamespace(
        trainer=trainer, parameters=parameters, dependencies=dependencies,
        states=checkpoint_states, loads=loads, codes=expected_codes,
    )


def _callback(api, unit, phase=1, checkpoint=None):
    return api._make_callback(unit.trainer, phase, checkpoint)


def _event(callback, name, trainer):
    return getattr(callback, name)(
        trainer.args, trainer.state, trainer.control, model=trainer.model,
        optimizer=trainer.optimizer, lr_scheduler=trainer.lr_scheduler,
    )


def _update(callback, trainer, *, move=True, advance=True):
    _event(callback, "on_pre_optimizer_step", trainer)
    trainer.optimizer.step(move=move, advance=advance)
    _event(callback, "on_optimizer_step", trainer)
    trainer.lr_scheduler.last_epoch += 1
    trainer.state.global_step += 1
    _event(callback, "on_step_end", trainer)


def _checkpoint(api, unit, root, step=1, omit=()):
    checkpoint = root / f"checkpoint-{step}"
    checkpoint.mkdir()
    trainer = unit.trainer
    while trainer.optimizer.steps < step:
        trainer.optimizer.step()
        trainer.lr_scheduler.last_epoch += 1
    trainer.state.global_step = step
    (checkpoint / "trainer_state.json").write_text(
        json.dumps({"global_step": step, "max_steps": 2}), encoding="utf-8",
    )
    (checkpoint / "adapter_config.json").write_text(
        '{"peft_type":"LORA","r":32,"lora_alpha":32}', encoding="utf-8",
    )
    unit.states.update({
        "optimizer.pt": trainer.optimizer.state_dict(),
        "scheduler.pt": trainer.lr_scheduler.state_dict(),
        "scaler.pt": trainer.accelerator.scaler.state_dict(),
        "rng_state.pth": copy.deepcopy(trainer.saved_rng),
    })
    if trainer.use_adaptive_entropy and "entropy_ctrl_state.json" not in omit:
        (checkpoint / "entropy_ctrl_state.json").write_text(json.dumps({
            "entropy_coef": trainer.entropy_coef,
            "last_world_entropy": trainer._last_world_entropy,
        }), encoding="utf-8")
    for name in (*unit.states, "adapter_model.safetensors"):
        if name not in omit:
            if name in unit.states:
                # Stored envelope is real; Tiny load above is only a wiring double.
                with zipfile.ZipFile(checkpoint / name, "w", compression=zipfile.ZIP_STORED) as archive:
                    archive.writestr("archive/data.pkl", b"UNIT_WIRING_DOUBLE_NOT_PICKLE")
                    archive.writestr("archive/version", b"3\n")
                    archive.writestr("archive/byteorder", b"little")
                    archive.writestr("archive/data/0", b"\0")
            else:
                (checkpoint / name).write_bytes(b"SERIALIZER_PROTOCOL_DOUBLE")
    adapter = {
        name.replace(".default.", "."): parameter.clone()
        for name, parameter in trainer.model.named_parameters()
    }
    return checkpoint, adapter


def _assembly_spies(api, monkeypatch, request, trainer):
    from train import grpo_ptc, native_model, native_training, sql_bridge

    calls = []
    prepared = SimpleNamespace(
        dataset_rows=[{"task_id": task.name} for task in request.tasks],
        reward=object(), environment_factory=object(), max_tool_calling_iterations=7,
    )
    source = native_model.VerifiedLocalModel(
        path=str(request.model_dir), model_id=grpo_ptc.MODEL,
        revision=native_model.MODEL_REVISION,
        inventory_sha256=native_model.INVENTORY_SHA256, files_verified=1,
    )

    def invariants(arms, root, steps):
        calls.append(("invariants", arms, root, steps))
        return grpo_ptc.training_config(arms, steps)

    def verify(path, *, model_revision):
        calls.append(("model", Path(path), model_revision))
        return source

    def prepare(tasks, db_root, **kwargs):
        calls.append(("prepare", tuple(tasks), Path(db_root)))
        return prepared

    def construct(inputs, verified, config, *, output, max_seq_length):
        calls.append(("construct", inputs, verified, dict(config), Path(output), max_seq_length))
        return trainer

    monkeypatch.setattr(api, "_validate_request", lambda current: None)
    monkeypatch.setattr(grpo_ptc, "_preflight_invariants", invariants)
    monkeypatch.setattr(native_model, "verify_local_model", verify)
    monkeypatch.setattr(sql_bridge, "prepare_sql_training", prepare)
    monkeypatch.setattr(native_training, "_construct_sql_trainer", construct)
    monkeypatch.setattr(api, "_check_sampler", lambda current: calls.append(("sampler",)))
    return calls, prepared, source


def test_05_cold_import_has_zero_effects(monkeypatch, capsys):
    assert importlib.util.find_spec(MODULE) is not None, (
        "missing train.native_qualification implementation, intended baseline RED"
    )
    effects = []
    original_import = builtins.__import__
    original_open = builtins.open

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in FORBIDDEN_IMPORTS:
            effects.append(("import", name))
            raise AssertionError(f"cold import attempted framework/provider: {name}")
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        effects.append(("effect", str(args[:1])))
        raise AssertionError("cold import attempted process/network/model/output action")

    def guarded_open(file, mode="r", *args, **kwargs):
        path = os.fspath(file) if isinstance(file, (str, os.PathLike)) else ""
        if any(flag in mode for flag in "wax+") or (
            path and not path.endswith((".py", ".pyc"))
        ):
            return forbidden(file, mode)
        return original_open(file, mode, *args, **kwargs)

    capsys.readouterr()
    with monkeypatch.context() as patch:
        patch.delitem(sys.modules, MODULE, raising=False)
        patch.setattr(sys, "dont_write_bytecode", True)
        patch.setattr(builtins, "__import__", guarded_import)
        patch.setattr(builtins, "open", guarded_open)
        for name in ("open", "read_bytes", "read_text", "write_bytes", "write_text", "mkdir", "touch"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(os, "system", forbidden)
        for name in ("open", "mkdir", "makedirs", "fork", "posix_spawn", "posix_spawnp"):
            if hasattr(os, name):
                patch.setattr(os, name, forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        importlib.import_module(MODULE)
    captured = capsys.readouterr()
    assert effects == [], f"cold import effects: {effects}"
    assert captured.out == captured.err == "", "cold import must emit zero output bytes"


def test_06_scope_authority_and_closed_transport(monkeypatch, tmp_path):
    api = _implementation()
    from train import native_training

    request = _request(api, tmp_path)
    fields = {
        "FilePin": ("path", "size", "sha256"),
        "AttemptBounds": (
            "total_ceiling_usd", "prior_usage_usd", "remaining_worst_case_usd",
            "lifetime_seconds", "output_bytes_per_phase", "artifact_bytes", "retention_seconds",
        ),
        "QualificationRequest": (
            "tasks", "db_root", "model_dir", "output_dir", "source_pins", "database_pins",
            "runtime_inventory", "image_digest", "bounds",
        ),
        "OwnedJobResult": ("service_handle", "exported_root", "phase_returncodes"),
    }
    for name, expected in fields.items():
        cls = getattr(api, name)
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen, name
        assert tuple(field.name for field in dataclasses.fields(cls)) == expected, name
    assert tuple(inspect.signature(api.attempt_sql_qualification).parameters) == (
        "request", "controller",
    ), "no public injection knobs"
    controller_parameter = inspect.signature(api.attempt_sql_qualification).parameters["controller"]
    assert controller_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert controller_parameter.default is inspect.Parameter.empty
    calls = []

    class RejectingController:
        def require_approved(self, current):
            calls.append(("approval", current))
            raise RuntimeError("operator refused exact operation")

        def run_once(self, current):
            calls.append(("launch", current))
            raise AssertionError("unapproved launch")

    with pytest.raises(TypeError):
        api.attempt_sql_qualification(request)
    with monkeypatch.context() as patch:
        patch.setattr(api, "_validate_request", lambda current: None)
        def forbidden(*args, **kwargs):
            raise AssertionError("unapproved request must not load runtime or launch a process")
        patch.setattr(native_training, "_load_runtime", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        _refuses("external approval", lambda: api.attempt_sql_qualification(
            request, controller=RejectingController(),
        ))
    assert calls == [("approval", request)], "one refusal, zero launches/retries"
    def forbidden_runtime(*args, **kwargs):
        raise AssertionError("nonmatching scope must cause zero runtime loads/launches")
    monkeypatch.setattr(native_training, "_load_runtime", forbidden_runtime)
    monkeypatch.setattr(subprocess, "Popen", forbidden_runtime)
    for label, altered in (
        ("two tasks", dataclasses.replace(request, tasks=request.tasks[:2])),
        ("repeated ID", dataclasses.replace(request, tasks=(request.tasks[0],) * 4)),
        ("question substitution", dataclasses.replace(
            request, tasks=(dataclasses.replace(request.tasks[0], question="substitute"),
                            *request.tasks[1:]),
        )),
        ("missing DB pins", dataclasses.replace(request, database_pins=())),
        ("missing source pins", dataclasses.replace(request, source_pins=())),
        ("runtime pin digest", dataclasses.replace(
            request, runtime_inventory=dataclasses.replace(request.runtime_inventory, sha256="0" * 64),
        )),
        ("source pin digest", dataclasses.replace(
            request, source_pins=(dataclasses.replace(request.source_pins[0], sha256="0" * 64),),
        )),
        ("path overlap", dataclasses.replace(request, output_dir=request.model_dir)),
        ("nonfresh export", dataclasses.replace(request, output_dir=request.db_root)),
        ("bad image", dataclasses.replace(request, image_digest="latest")),
    ):
        _refuses(label, lambda altered=altered: api._validate_request(altered))

    model_pins = (_pin(api, request.model_dir / "config.json"),)
    with monkeypatch.context() as patch:
        patch.setattr(api, "_validate_request", lambda current: None)
        patch.setattr(api, "_verified_model_members", lambda current: model_pins)
        payload, assets = api._prepare_worker_transport(request)
        assert isinstance(payload, bytes) and len(payload) <= 1048576
        document = api._decode_worker_transport(payload)
        assert set(document) == {"schema", "assets", "tasks", "image_digest", "bounds"}
        assert document["schema"] == "native-sql-worker-v1"
        assert len(document["tasks"]) == 4
        assert str(tmp_path) not in payload.decode("utf-8"), "host paths must not cross wire"
        staged = {(asset.kind, asset.key): asset for asset in assets}
        assert len(staged) == len(assets) == len(document["assets"])
        for member in document["assets"]:
            assert set(member) == {"kind", "key", "size", "sha256"}
            asset = staged[(member["kind"], member["key"])]
            data = asset.host_path.read_bytes()
            assert len(data) == member["size"] == asset.size
            assert hashlib.sha256(data).hexdigest() == member["sha256"] == asset.sha256
            assert api._check_asset_bytes(
                asset.host_path, size=member["size"], sha256=member["sha256"],
            ) is None
            root = {"source": "source", "model": "model", "data": "data"}[member["kind"]]
            assert api._asset_path(member["kind"], member["key"]) == (
                Path("/opt/qualification") / root / member["key"]
            )
        assert ("source", "qualification/runtime-inventory.json") in staged
        worker_request = api._request_from_wire(document)
        assert worker_request.model_dir == Path("/opt/qualification/model")
        assert worker_request.db_root == Path("/opt/qualification/data")
        assert worker_request.output_dir == Path("/var/tmp/qualification/output")
        assert worker_request.runtime_inventory.path == (
            Path("/opt/qualification/source/qualification/runtime-inventory.json")
        )
        assert worker_request.bounds == request.bounds
        for task, row in zip(request.tasks, document["tasks"], strict=True):
            expected = dataclasses.asdict(task)
            expected.pop("db_path")
            assert {key: value for key, value in row.items() if key != "db_asset"} == expected
            assert ("data", row["db_asset"]) in staged
        for task, row in zip(worker_request.tasks, document["tasks"], strict=True):
            assert Path(task.db_path) == api._asset_path("data", row["db_asset"])
        for label, mutation in (
            ("unknown key", lambda doc: doc.update(controller={"approved": True})),
            ("duplicate asset", lambda doc: doc["assets"].append(copy.deepcopy(doc["assets"][0]))),
            ("absolute key", lambda doc: doc["assets"][0].update(key="/host/absolute")),
            ("traversal", lambda doc: doc["assets"][0].update(key="../escape")),
            ("invalid kind", lambda doc: doc["assets"][0].update(kind="command")),
            ("asset unknown key", lambda doc: doc["assets"][0].update(host_path="/secret")),
            ("task host path", lambda doc: doc["tasks"][0].update(db_path="/host/data")),
            ("unknown bound", lambda doc: doc["bounds"].update(command="execute")),
            ("reserved collision", lambda doc: next(
                asset for asset in doc["assets"]
                if (asset["kind"], asset["key"]) != ("source", "qualification/runtime-inventory.json")
            ).update(
                kind="source", key="qualification/runtime-inventory.json",
            )),
        ):
            invalid = copy.deepcopy(document)
            mutation(invalid)
            _refuses(label, lambda invalid=invalid: api._decode_worker_transport(
                json.dumps(invalid).encode("utf-8"),
            ))
        for label, invalid in (
            ("duplicate JSON field", b'{"schema":"native-sql-worker-v1","schema":"other"}'),
            ("oversize", b" " * 1048577), ("invalid UTF8", b"\xff"),
        ):
            _refuses(label, lambda invalid=invalid: api._decode_worker_transport(invalid))
        for key in ("/absolute", "../escape", "a/../../escape"):
            _refuses(key, lambda key=key: api._asset_path("source", key))
        _refuses("duplicate staging pins", lambda: api._prepare_worker_transport(
            dataclasses.replace(request, source_pins=request.source_pins * 2),
        ))
        database = Path(request.tasks[0].db_path)
        original = database.read_bytes()
        database.write_bytes(original + b"mutation")
        _refuses("mounted byte verifier mutation", lambda: api._check_asset_bytes(
            database, size=request.database_pins[0].size, sha256=request.database_pins[0].sha256,
        ))
        _refuses("changed approved bytes", lambda: api._prepare_worker_transport(request))
        database.write_bytes(original)
        link = tmp_path / "database-link.sqlite"
        link.symlink_to(database)
        _refuses("mounted byte verifier link", lambda: api._check_asset_bytes(
            link, size=request.database_pins[0].size, sha256=request.database_pins[0].sha256,
        ))
        bad_pin = dataclasses.replace(request.database_pins[0], path=link)
        _refuses("linked source asset", lambda: api._prepare_worker_transport(
            dataclasses.replace(request, database_pins=(bad_pin, *request.database_pins[1:])),
        ))
    assert not any(call[0] == "launch" for call in calls)


def test_07_bounds_are_cheap_finite_and_all_charge(monkeypatch):
    api = _implementation()
    from train import native_model, native_training

    effects = []

    def forbidden(*args, **kwargs):
        effects.append("expensive")
        raise AssertionError("bounds validation must precede model reads/runtime/launch")

    monkeypatch.setattr(native_model, "verify_local_model", forbidden)
    monkeypatch.setattr(native_training, "_load_runtime", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert api._validate_bounds(_bounds(api)) is None
    for field, amount in (
        ("total_ceiling_usd", 25), ("prior_usage_usd", 1), ("remaining_worst_case_usd", 24),
    ):
        for value in (float(amount), amount, True, False, str(amount)):
            _refuses(f"{field}={value!r}", lambda field=field, value=value:
                     api._validate_bounds(_bounds(api, **{field: value})))
    for field, invalids in {
        "total_ceiling_usd": (Decimal("25.01"), Decimal("0"), Decimal("NaN"), Decimal("Infinity")),
        "prior_usage_usd": (Decimal("-1"), Decimal("26"), Decimal("NaN")),
        "remaining_worst_case_usd": (Decimal("-1"), Decimal("25"), Decimal("Infinity")),
        "lifetime_seconds": (None, 0, True, 1801, 1.5),
        "output_bytes_per_phase": (None, 0, True, -1),
        "artifact_bytes": (None, 0, True, -1),
        "retention_seconds": (None, 0, True, -1),
    }.items():
        for value in invalids:
            _refuses(f"{field}={value!r}", lambda field=field, value=value:
                     api._validate_bounds(_bounds(api, **{field: value})))
    assert effects == []


def test_08_four_real_sqlite_fixtures_prepare_four_distinct_rows(tmp_path):
    api = _implementation()
    import sqlite3

    from datasets import Dataset
    from train import sql_bridge

    tasks = _four_tasks(tmp_path / "data")
    original = [(dataclasses.asdict(task), Path(task.db_path).read_bytes()) for task in tasks[:2]]
    api._validate_fixture_scope(tasks, tmp_path / "data")
    for task, (name, amount) in zip(tasks, FIXTURES, strict=True):
        with sqlite3.connect(f"file:{task.db_path}?mode=ro", uri=True) as connection:
            assert connection.execute("SELECT amount FROM readings").fetchall() == [(amount,)]
        assert task.name == task.db_id == name
        assert task.question == f"What amount is recorded? FIXTURE_{name.upper()}"
        assert task.gold_sql == f"SELECT amount FROM readings /* GOLD_{name} */"
    prepared = sql_bridge.prepare_sql_training(tasks, tmp_path / "data")
    rows = prepared.dataset_rows
    assert len(rows) == len({row["task_id"] for row in rows}) == 4
    assert [row["task_id"] for row in rows] == [name for name, _ in FIXTURES]
    assert [row["answer"] for row in rows] == [task.gold_sql for task in tasks]
    assert len({row["prompt"][0]["content"] for row in rows}) == 4
    dataset = Dataset.from_list(rows)
    assert len(dataset) == 4 and dataset["task_id"] == [name for name, _ in FIXTURES]
    for task, (fields, database) in zip(tasks[:2], original, strict=True):
        assert dataclasses.asdict(task) == fields
        assert Path(task.db_path).read_bytes() == database, "first two fixture DB bytes frozen"
    for label, invalid in (
        ("two rows", tasks[:2]), ("duplicate", (tasks[0], tasks[1], tasks[0], tasks[1])),
        ("substitution", (*tasks[:3], dataclasses.replace(tasks[3], db_path=tasks[2].db_path))),
    ):
        _refuses(label, lambda invalid=invalid: api._validate_fixture_scope(invalid, tmp_path / "data"))
    for field in dataclasses.fields(tasks[3]):
        value = {"tier": "moderate", "tier_source": "annotated"}.get(
            field.name, str(getattr(tasks[3], field.name)) + "_other",
        )
        altered = dataclasses.replace(tasks[3], **{field.name: value})
        _refuses(f"all-fields scope: {field.name}", lambda altered=altered:
                 api._validate_fixture_scope((*tasks[:3], altered), tmp_path / "data"))


def test_09_private_assembly_preserves_original_configuration(monkeypatch, tmp_path):
    api = _implementation()
    from train import dead_group_probe, grpo_ptc, guards, native_model

    request = _request(api, tmp_path)
    unit = _unit_trainer(api, monkeypatch, tmp_path / "unit")
    trainer = unit.trainer
    callbacks = []
    trainer.add_callback = callbacks.append
    calls, prepared, source = _assembly_spies(api, monkeypatch, request, trainer)
    observer = object()
    monkeypatch.setattr(api, "_make_callback", lambda current, phase, checkpoint: observer)
    monkeypatch.setattr(api, "_observe_calls", lambda current, callback: nullcontext())
    monkeypatch.setattr(api, "_check_checkpoint", lambda *args, **kwargs: None)
    api._run_phase(request, 1)
    invariants = [call for call in calls if call[0] == "invariants"]
    assert len(invariants) == 1
    assert invariants[0][1:] == (grpo_ptc.TRAINED_ARMS_DEFAULT, guards.REPO_ROOT, 2)
    assert [call[0] for call in calls].count("model") == 1
    assert next(call for call in calls if call[0] == "model")[2] == native_model.MODEL_REVISION
    constructed = [call for call in calls if call[0] == "construct"]
    assert len(constructed) == 1
    _, inputs, verified, config, output, context = constructed[0]
    assert inputs is prepared and verified is source
    assert inputs.reward is prepared.reward and inputs.environment_factory is prepared.environment_factory
    assert config == grpo_ptc.training_config(grpo_ptc.TRAINED_ARMS_DEFAULT, steps=2)
    assert (config["max_steps"], config["num_generations"], config["max_completion_length"],
            config["num_iterations"], context) == (2, 4, 3072, 1, 8192)
    assert dead_group_probe.batch_for(4) == (8, 2)
    assert source.model_id == grpo_ptc.MODEL and source.path == str(request.model_dir)
    assert output == request.output_dir
    assert callbacks == [observer] and trainer.train_calls == [None]
    assert trainer.optimizer.steps == 0, "wiring spy must not invent an optimizer update"


def test_10_sampler_checks_actual_bounded_yields_and_batches(monkeypatch, tmp_path):
    api = _implementation()
    selected_codes = api._expected_method_codes
    _unit_trainer(api, monkeypatch, tmp_path)
    before = random.getstate()

    class Sampler:
        def __init__(self, values, advertised=32):
            self.values, self.advertised, self.visited = values, advertised, 0

        def __len__(self):
            return self.advertised

        def __iter__(self):
            random.random()
            for value in self.values:
                self.visited += 1
                assert self.visited <= 33, "sampler gate enumerated beyond refusal bound"
                yield value

    def trainer_for(values, batch_sizes=(16, 16)):
        sampler = Sampler(values)
        ids = [name for name, _ in FIXTURES]
        batches = [[{"task_id": ids[index % 4]} for index in range(size)]
                   for size in batch_sizes]
        trainer = SimpleNamespace(
            args=SimpleNamespace(
                num_generations=4, generation_batch_size=16, steps_per_generation=2,
                per_device_train_batch_size=8, gradient_accumulation_steps=2, num_iterations=1,
            ),
            train_dataset=[{"task_id": name} for name in ids],
            _get_train_sampler=lambda *args: sampler,
            get_train_dataloader=lambda: iter(batches),
        )
        return trainer, sampler

    values = list(range(4)) * 8
    assert Counter(values) == {0: 8, 1: 8, 2: 8, 3: 8}
    trainer, sampler = trainer_for(values)
    assert api._check_sampler(trainer) is None
    assert sampler.visited == 32 and random.getstate() == before
    for label, indices, batches in (
        ("misleading len32 but zero yields", [], (16, 16)),
        ("only two IDs", [0, 1] * 16, (16, 16)),
        ("wrong repeats", [0] * 9 + [1] * 7 + [2] * 8 + [3] * 8, (16, 16)),
        ("33rd yield", values + [0] * 1000, (16, 16)),
        ("no prepared batches", values, ()),
        ("short prepared batch", values, (16, 15)),
        ("third prepared batch", values, (16, 16, 16)),
    ):
        trainer, sampler = trainer_for(indices, batches)
        _refuses(label, lambda trainer=trainer: api._check_sampler(trainer))
        assert sampler.visited <= 33, label
    assert random.getstate() == before, "disposable probe must restore touched RNG"
    with monkeypatch.context() as patch:
        def trainer_loader(self):
            return "transformers-owner"

        def grpo_loader(self):
            return "trl-generation-sized-owner"

        def harmless(self, *args, **kwargs):
            return None

        trainer_methods = {
            name: harmless for name in (
                "train", "_load_rng_state", "_run_epoch", "_clip_grad_norm",
                "_load_from_checkpoint", "_load_scaler", "_inner_training_loop",
            )
        }
        trainer_methods.update(get_train_dataloader=trainer_loader, __module__="transformers.unit")
        Trainer = type("Trainer", (), trainer_methods)
        trl_methods = {
            name: harmless for name in (
                "_generate_and_score_completions", "_save_checkpoint",
                "_load_optimizer_and_scheduler", "_get_train_sampler",
            )
        }
        trl_methods.update(get_train_dataloader=grpo_loader, __module__="trl.unit")
        GRPOTrainer = type("GRPOTrainer", (Trainer,), trl_methods)
        Accelerator = type("Accelerator", (), {
            name: harmless for name in ("clip_grad_norm_", "unscale_gradients", "prepare_optimizer")
        })
        owners = {"Trainer": Trainer, "GRPOTrainer": GRPOTrainer, "Accelerator": Accelerator}
        modules = {
            "transformers.trainer": SimpleNamespace(Trainer=Trainer),
            "trl.trainer.grpo_trainer": SimpleNamespace(GRPOTrainer=GRPOTrainer),
            "accelerate.accelerator": SimpleNamespace(Accelerator=Accelerator),
        }
        patch.setattr(api, "_candidate_prerequisites", lambda: None)
        patch.setattr(api, "_check_loaded_candidate", lambda *args: None)
        patch.setattr(api, "_selected_module",
                      lambda name: (modules.get(name), b"", None))
        patch.setattr(api, "_find_code", lambda code, qualname:
                      owners[qualname.split(".")[0]].__dict__[qualname.split(".")[1]].__code__)
        patch.setattr(api, "_rewritten_loop", lambda *args: harmless.__code__)
        candidate = GRPOTrainer()
        candidate.accelerator = Accelerator()
        assert selected_codes(candidate)["get_train_dataloader"] is grpo_loader.__code__
        candidate.get_train_dataloader = trainer_loader.__get__(candidate, GRPOTrainer)
        with pytest.raises(ValueError, match="selected original code: get_train_dataloader"):
            selected_codes(candidate)


def test_11_callback_requires_real_same_parameter_update(monkeypatch, tmp_path):
    api = _implementation()
    unit = _unit_trainer(api, monkeypatch, tmp_path / "good")
    trainer = unit.trainer
    original_step = trainer.optimizer.step.__func__
    callback = _callback(api, unit)
    _event(callback, "on_train_begin", trainer)
    before = unit.parameters[0].clone()
    _update(callback, trainer)
    assert trainer.optimizer.step.__func__ is original_step, "no optimizer replacement"
    assert unit.parameters[0].values != before.values
    assert unit.parameters[1].grad.values == [0.0], "not every LoRA gradient must be nonzero"
    assert trainer.optimizer.state[unit.parameters[0]]["step"].item() == 1
    for label in (
        "allzero", "nan-gradient", "unchanged", "state-only", "displacement-only",
        "nan-parameter", "amp-skip", "foreign-parameter",
    ):
        unit = _unit_trainer(api, monkeypatch, tmp_path / label)
        trainer = unit.trainer
        callback = _callback(api, unit)
        _event(callback, "on_train_begin", trainer)

        def bad_boundary():
            if label == "allzero":
                for parameter in unit.parameters:
                    parameter.grad = TinyTensor(0.0)
            if label == "nan-gradient":
                unit.parameters[0].grad = TinyTensor(float("nan"))
            _event(callback, "on_pre_optimizer_step", trainer)
            if label == "amp-skip":
                trainer.accelerator.optimizer_step_was_skipped = True
            if label == "foreign-parameter":
                trainer.optimizer.param_groups[0]["params"] = [TinyTensor(9.0)]
                trainer.optimizer.state = {}
            else:
                trainer.optimizer.step(
                    move=label not in {"unchanged", "state-only"},
                    advance=label not in {"unchanged", "displacement-only"},
                )
            if label == "nan-parameter":
                unit.parameters[0].values[0] = float("nan")
            _event(callback, "on_optimizer_step", trainer)

        _refuses(label, bad_boundary)
    for label in (
        "approved", "raw-code", "class-step", "instance-step", "scheduler-self",
        "scheduler-func", "patch-owner", "saved-self", "closure-target",
        "extra-wrapper", "cycle", "scaler-step", "drift",
    ):
        with monkeypatch.context() as patch:
            unit = _unit_trainer(api, patch, tmp_path / f"origin-{label}")
            trainer = unit.trainer
            graph = _wrapped_optimizer_fixture(api, patch, unit)
            callback = _callback(api, unit)

            def bad(self, *args, **kwargs):
                raise AssertionError("mutated optimizer must never execute")

            bad.__name__, bad.__qualname__, bad.__module__ = (
                graph.raw.__name__, graph.raw.__qualname__, graph.raw.__module__,
            )
            bad.__wrapped__ = graph.grad
            if label == "raw-code":
                graph.raw.__code__ = bad.__code__
            elif label == "class-step":
                patch.setattr(type(graph.base), "step", bad)
            elif label == "instance-step":
                graph.base.step = bad.__get__(graph.base, type(graph.base))
            elif label == "scheduler-self":
                graph.outer.step = graph.scheduler_wrapper(type(graph.outer).step, weakref.ref(graph.base))
            elif label == "scheduler-func":
                graph.outer.step = graph.scheduler_wrapper(bad, weakref.ref(graph.outer))
            elif label == "patch-owner":
                foreign = type(graph.outer)(graph.base, graph.scale)
                graph.outer._optimizer_patched_step_method = graph.patch_optimizer_step(
                    foreign, graph.outer._optimizer_original_step_method,
                )
            elif label == "saved-self":
                foreign = type(graph.base)(unit.parameters)
                graph.outer._optimizer_original_step_method = graph.profile.__get__(foreign, type(foreign))
            elif label == "closure-target":
                graph.grad.__closure__[0].cell_contents = bad
            elif label == "extra-wrapper":
                patch.setattr(type(graph.base), "step", graph.profile_wrapper(graph.profile))
            elif label == "cycle":
                graph.grad.__closure__[0].cell_contents = graph.profile
            elif label == "scaler-step":
                patch.setattr(type(graph.scale), "step", bad)
            if label == "approved":
                patch.setattr(api, "_check_checkpoint", lambda *args: None)

                def actions():
                    _event(callback, "on_train_begin", trainer)
                    trainer._generate_and_score_completions(["original"])
                    _update(callback, trainer)
                    trainer._save_checkpoint(trainer.model)
                    _event(callback, "on_save", trainer)

                trainer._unit_action = actions
                with api._observe_calls(trainer, callback):
                    trainer.train()
                assert graph.base.steps == callback.raw_calls == callback.raw_returns == 1
                assert graph.base.step.__self__ is graph.base
                assert graph.base.step.__func__ is graph.profile
                assert graph.outer.step is graph.wrapper and not callback.hooks
            elif label == "drift":
                _event(callback, "on_train_begin", trainer)
                graph.base.step = bad.__get__(graph.base, type(graph.base))
                with pytest.raises(ValueError, match="optimizer origin"):
                    _event(callback, "on_pre_optimizer_step", trainer)
                callback.close()
                assert graph.base.steps == 0
            else:
                with pytest.raises(ValueError, match="optimizer origin"):
                    _event(callback, "on_train_begin", trainer)
                assert graph.base.steps == 0 and not graph.base.pre_hooks and not graph.base.post_hooks


def test_12_callback_requests_native_full_save_then_stop_at_one(monkeypatch, tmp_path):
    api = _implementation()
    unit = _unit_trainer(api, monkeypatch, tmp_path)
    trainer = unit.trainer
    callback = _callback(api, unit)
    checked = []

    def check(current, checkpoint, expected_step):
        assert trainer.events == ["native-save"], "on_save must follow the native full writer"
        checked.append((Path(checkpoint), expected_step))

    monkeypatch.setattr(api, "_check_checkpoint", check)
    _event(callback, "on_train_begin", trainer)
    assert not trainer.control.should_save and not trainer.control.should_training_stop
    _update(callback, trainer)
    assert trainer.state.global_step == 1 and trainer.args.max_steps == trainer.state.max_steps == 2
    assert trainer.control.should_save and trainer.control.should_training_stop
    assert trainer.args.save_only_model is False
    assert not list(tmp_path.iterdir()), "observer must not write checkpoint members"
    trainer._save_checkpoint(trainer.model)
    _event(callback, "on_save", trainer)
    assert checked == [(tmp_path / "checkpoint-1", 1)]
    assert trainer.events == ["native-save"] and not list(tmp_path.iterdir())
    unit = _unit_trainer(api, monkeypatch, tmp_path / "wrong-step")
    callback = _callback(api, unit)
    _event(callback, "on_train_begin", unit.trainer)
    unit.trainer.state.global_step = 2
    _refuses("phase1 must not first stop at2", lambda:
             _event(callback, "on_step_end", unit.trainer))


def test_13_resume_once_and_compare_every_restored_component(monkeypatch, tmp_path):
    api = _implementation()
    request = _request(api, tmp_path)
    unit = _unit_trainer(api, monkeypatch, tmp_path / "unit")
    request.output_dir.mkdir()
    checkpoint, adapter = _checkpoint(api, unit, request.output_dir)
    monkeypatch.setattr(api, "_load_adapter_state", lambda path: copy.deepcopy(adapter))
    entropy = json.loads((checkpoint / "entropy_ctrl_state.json").read_text(encoding="utf-8"))
    assert entropy == {
        "entropy_coef": unit.trainer.entropy_coef,
        "last_world_entropy": unit.trainer._last_world_entropy,
    }
    assert api._compare_restored_state(unit.trainer, checkpoint) is None
    for component in ("model", "optimizer", "scheduler", "scaler",
                      "entropy_coef", "last_world_entropy"):
        trainer = unit.trainer
        with monkeypatch.context() as patch:
            if component == "model":
                patch.setattr(unit.parameters[0], "values", [99.0])
            elif component == "optimizer":
                patch.setattr(trainer.optimizer, "state_dict", lambda: {"state": {}, "param_groups": []})
            elif component == "scheduler":
                patch.setattr(trainer.lr_scheduler, "last_epoch", 99)
            elif component == "scaler":
                patch.setattr(trainer.accelerator.scaler, "state_dict", lambda: {"scale": 1.0})
            elif component == "entropy_coef":
                patch.setattr(trainer, "entropy_coef", 99.0)
            else:
                patch.setattr(trainer, "_last_world_entropy", 99.0)
            callback = _callback(api, unit, phase=2, checkpoint=checkpoint)
            _refuses(component, lambda: _event(callback, "on_train_begin", trainer))
            assert trainer.events == [] and trainer.optimizer.steps == 1, component
    trainer = unit.trainer
    trainer.add_callback = lambda callback: None
    _assembly_spies(api, monkeypatch, request, trainer)
    monkeypatch.setattr(api, "_make_callback", lambda *args: object())
    monkeypatch.setattr(api, "_observe_calls", lambda *args: nullcontext())
    monkeypatch.setattr(api, "_check_checkpoint", lambda *args, **kwargs: None)
    api._run_phase(request, 2)
    assert trainer.train_calls == [str(checkpoint)], "exactly one ORIGINAL train(resume_from_checkpoint)"
    assert trainer.optimizer.steps == 1, "assembly spy must not perform a second update"


def test_14_trace_requires_normal_restore_and_rng_before_generation(monkeypatch, tmp_path):
    api = _implementation()
    saved_python = random.getstate()
    previous_profile, previous_trace = sys.getprofile(), sys.gettrace()
    try:
        for label in ("normal", "early", "missing", "exception", "python", "numpy", "cpu", "cuda"):
            unit = _unit_trainer(api, monkeypatch, tmp_path / label)
            trainer = unit.trainer
            checkpoint, adapter = _checkpoint(api, unit, tmp_path / label)
            monkeypatch.setattr(api, "_load_adapter_state", lambda path, adapter=adapter:
                                copy.deepcopy(adapter))
            monkeypatch.setattr(api, "_check_checkpoint", lambda *args, **kwargs: None)
            callback = _callback(api, unit, phase=2, checkpoint=checkpoint)
            trainer.restore_error = label == "exception"
            trainer.rng_mismatch = label if label in {"python", "numpy", "cpu", "cuda"} else None
            observed_exception_return = []

            def outer_profile(frame, event, arg):
                if frame.f_code is trainer._load_rng_state.__func__.__code__ and event == "return":
                    observed_exception_return.append(arg)

            def actions():
                _event(callback, "on_train_begin", trainer)
                assert trainer.events == [], "on_train_begin is not RNG-restored evidence"
                if label == "early":
                    trainer._generate_and_score_completions(["early"])
                if label != "missing":
                    try:
                        assert trainer._load_rng_state(str(checkpoint)) is None
                    except RuntimeError:
                        if label != "exception":
                            raise
                        trainer.events.append("restore-exception-caught")
                trainer._generate_and_score_completions(["first resumed generation"])
                _update(callback, trainer)
                trainer._save_checkpoint(trainer.model)
                _event(callback, "on_save", trainer)

            trainer._unit_action = actions

            def attempt():
                with api._observe_calls(trainer, callback):
                    trainer.train(resume_from_checkpoint=str(checkpoint))

            if label == "normal":
                attempt()
                assert trainer.events == ["restore-normal", "generation", "native-save"]
                assert trainer.state.global_step == 2 and trainer.optimizer.steps == 2
                assert callback.restores == 1 and callback.restored_rng is True
            else:
                if label == "exception":
                    # Independently demonstrate CPython's ambiguous None return on unwind.
                    sys.setprofile(outer_profile)
                    try:
                        with pytest.raises(RuntimeError, match="restore raised"):
                            trainer._load_rng_state(str(checkpoint))
                    finally:
                        sys.setprofile(previous_profile)
                    assert observed_exception_return == [None]
                    assert "restore-normal" not in trainer.events
                causes = {
                    "early": "preceded native normal RNG restore",
                    "missing": "preceded native normal RNG restore",
                    "exception": "unwound exceptionally",
                    "python": "Python RNG restore mismatch",
                    "numpy": "NumPy RNG restore mismatch",
                    "cpu": "CPU RNG restore mismatch",
                    "cuda": "CUDA RNG restore mismatch",
                }
                with pytest.raises(ValueError, match=causes[label]):
                    attempt()
                assert trainer.optimizer.steps == 1, f"{label}: refuse before resumed update"
                assert callback.generations == callback.restores == 0
                assert callback.restored_rng is False and not callback.hooks
                if label in {"python", "numpy", "cpu", "cuda"}:
                    assert trainer.events == ["restore-normal"]
                elif label == "exception":
                    assert trainer.events == ["restore-exception-caught"]
                else:
                    assert trainer.events == []
            assert sys.getprofile() is previous_profile, "observer must restore existing profile"
            assert sys.gettrace() is previous_trace, "observer must restore existing trace"
        unit = _unit_trainer(api, monkeypatch, tmp_path / "primary")
        checkpoint, adapter = _checkpoint(api, unit, tmp_path / "primary")
        monkeypatch.setattr(api, "_load_adapter_state", lambda path: copy.deepcopy(adapter))
        callback = _callback(api, unit, phase=2, checkpoint=checkpoint)

        class PrimarySentinel(Exception):
            pass

        primary = PrimarySentinel("phase2 comparison primary")

        def comparison(*args):
            raise primary

        monkeypatch.setattr(api, "_compare_restored_state", comparison)
        unit.trainer._unit_action = lambda: _event(callback, "on_train_begin", unit.trainer)
        with pytest.raises(PrimarySentinel) as caught:
            with api._observe_calls(unit.trainer, callback):
                unit.trainer.train(resume_from_checkpoint=str(checkpoint))
        assert caught.value is primary
        assert callback.restored_rng is False and callback.native_save_returned is False
        assert not callback.hooks and sys.getprofile() is previous_profile
    finally:
        random.setstate(saved_python)
        sys.setprofile(previous_profile)
        sys.settrace(previous_trace)


def test_15_loaded_identity_and_callback_order_fail_closed(monkeypatch, tmp_path):
    api = _implementation()
    for label in ("positive", "same-name-code", "bypassed-boundary", "extra-update", "no-restore-trace"):
        unit = _unit_trainer(api, monkeypatch, tmp_path / label)
        trainer = unit.trainer
        checkpoint, adapter = _checkpoint(api, unit, tmp_path / label)
        monkeypatch.setattr(api, "_load_adapter_state", lambda path, adapter=adapter:
                            copy.deepcopy(adapter))
        callback = _callback(api, unit, phase=2, checkpoint=checkpoint)
        assert api._compare_restored_state(trainer, checkpoint) is None
        assert api._native_adapter_state(trainer, unit.dependencies).keys() == adapter.keys()
        monkeypatch.setattr(api, "_check_checkpoint", lambda *args: None)

        def _load_rng_state(self, checkpoint):
            self.events.append("same-name-different-code")
            return None

        if label == "same-name-code":
            original = trainer._load_rng_state.__func__
            assert _load_rng_state.__name__ == original.__name__
            assert _load_rng_state.__code__ is not original.__code__
            trainer._load_rng_state = _load_rng_state.__get__(trainer, type(trainer))

        def actions():
            _event(callback, "on_train_begin", trainer)
            if label != "no-restore-trace":
                trainer._load_rng_state(str(checkpoint))
            trainer._generate_and_score_completions(["resumed"])
            if label == "bypassed-boundary":
                trainer.optimizer.step()
                _event(callback, "on_optimizer_step", trainer)
            elif label == "extra-update":
                _update(callback, trainer)
                _update(callback, trainer)
            elif label == "positive":
                _update(callback, trainer)
                trainer._save_checkpoint(trainer.model)
                _event(callback, "on_save", trainer)

        trainer._unit_action = actions

        def attempt():
            with api._observe_calls(trainer, callback):
                trainer.train(resume_from_checkpoint=str(checkpoint))

        if label == "positive":
            attempt()
            assert trainer.events == ["restore-normal", "generation", "native-save"]
        else:
            causes = {
                "same-name-code": "method identity changed",
                "bypassed-boundary": "unexpected original native Adam step call",
                "extra-update": "extra/misordered optimizer boundary",
                "no-restore-trace": "preceded native normal RNG restore",
            }
            with pytest.raises(ValueError, match=causes[label]):
                attempt()
        assert trainer.optimizer.steps <= 2, f"{label}: refuse before an extra native update"


def test_16_checkpoint_completeness_and_safe_read_policy(monkeypatch, tmp_path):
    api = _implementation()
    def forbidden_pickle(*args, **kwargs):
        raise AssertionError("checkpoint observer must not use unrestricted pickle")
    monkeypatch.setattr(pickle, "load", forbidden_pickle)
    monkeypatch.setattr(pickle, "loads", forbidden_pickle)
    for label in (
        "complete", "no-optimizer", "no-scaler", "no-entropy", "wrong-step",
        "wrong-horizon", "pending-reuse", "entropy-window", "unsafe-member",
        "symlink", "logs-only", "missing-trainable", "ambiguous-trainable", "wrong-model", "nonzip",
    ):
        root = tmp_path / label
        unit = _unit_trainer(api, monkeypatch, root)
        missing = {
            "no-optimizer": ("optimizer.pt",), "no-scaler": ("scaler.pt",),
            "no-entropy": ("entropy_ctrl_state.json",),
            "logs-only": (
                "optimizer.pt", "scheduler.pt", "scaler.pt", "entropy_ctrl_state.json",
                "rng_state.pth", "adapter_model.safetensors",
            ),
        }.get(label, ())
        checkpoint, adapter = _checkpoint(api, unit, root, omit=missing)
        trainer = unit.trainer
        if label in {"wrong-step", "wrong-horizon"}:
            (checkpoint / "trainer_state.json").write_text(json.dumps({
                "global_step": 2 if label == "wrong-step" else 1,
                "max_steps": 1 if label == "wrong-horizon" else 2,
            }), encoding="utf-8")
        elif label == "pending-reuse":
            trainer._step = 1
        elif label == "entropy-window":
            trainer._entropy_window_stats = {"unfinished": TinyTensor(1)}
        elif label == "unsafe-member":
            (checkpoint / "unapproved.pkl").write_bytes(b"not a pickle")
        elif label == "symlink":
            (checkpoint / "linked-optimizer.pt").symlink_to(checkpoint / "optimizer.pt")
        elif label == "logs-only":
            (checkpoint / "healthy.log").write_text("step1 healthy restored", encoding="utf-8")
        elif label == "missing-trainable":
            adapter.pop(next(iter(adapter)))
        elif label == "ambiguous-trainable":
            adapter["base_model.model.layer.lora_A.default.weight"] = TinyTensor(1.0)
        elif label == "wrong-model":
            adapter[next(iter(adapter))] = TinyTensor(99.0)
        elif label == "nonzip":
            (checkpoint / "optimizer.pt").write_bytes(b"NOT_A_NATIVE_ZIP")
        monkeypatch.setattr(api, "_load_adapter_state", lambda path, adapter=adapter:
                            copy.deepcopy(adapter))
        before = {path.name: os.readlink(path) if path.is_symlink() else path.read_bytes()
                  for path in checkpoint.iterdir()}
        if label == "complete":
            assert api._check_checkpoint(trainer, checkpoint, 1) is None
            assert {"optimizer.pt", "scheduler.pt", "scaler.pt", "rng_state.pth"} <= {
                name for name, _ in unit.loads
            }
            entropy = json.loads((checkpoint / "entropy_ctrl_state.json").read_text(encoding="utf-8"))
            assert entropy == {
                "entropy_coef": trainer.entropy_coef,
                "last_world_entropy": trainer._last_world_entropy,
            }
        else:
            _refuses(label, lambda: api._check_checkpoint(trainer, checkpoint, 1))
        after = {path.name: os.readlink(path) if path.is_symlink() else path.read_bytes()
                 for path in checkpoint.iterdir()}
        assert before == after, f"{label}: observer must not write checkpoint members"
        assert all(weights_only is True for _, weights_only in unit.loads)
        assert not any(name == "training_args.bin" for name, _ in unit.loads)
        assert "entropy_ctrl_state.json" not in unit.states
        assert not any(name == "entropy_ctrl_state.json" for name, _ in unit.loads)
    request = _request(api, tmp_path / "host-export")
    request.output_dir.mkdir()
    unit = _unit_trainer(api, monkeypatch, tmp_path / "host-unit")
    snapshots, adapters = {}, {}
    for step in (1, 2):
        checkpoint, adapter = _checkpoint(api, unit, request.output_dir, step=step)
        snapshots[str(checkpoint)] = copy.deepcopy(unit.states)
        adapters[str(checkpoint)] = adapter
    original_load = unit.dependencies.torch.load

    def export_load(stream, **kwargs):
        original_load(stream, **kwargs)
        path = Path(stream.name)
        return copy.deepcopy(snapshots[str(path.parent)][path.name])

    monkeypatch.setattr(unit.dependencies.torch, "load", export_load)
    monkeypatch.setattr(api, "_load_adapter_state",
                        lambda path: copy.deepcopy(adapters[str(path)]))
    result = api.OwnedJobResult(object(), request.output_dir, (0, 0))
    assert api._check_exported_artifacts(request, result) == (
        request.output_dir / "checkpoint-1", request.output_dir / "checkpoint-2",
    )
    for step in (1, 2):
        checkpoint = request.output_dir / f"checkpoint-{step}"
        with monkeypatch.context() as patch:
            original_members = api._checkpoint_members
            patch.setattr(api, "_checkpoint_members",
                          lambda path, *args, checkpoint=checkpoint:
                          original_members(path, *args) - ({"scaler.pt"} if path == checkpoint else set()))
            with pytest.raises(ValueError, match="exported native full checkpoint incomplete"):
                api._check_exported_artifacts(request, result)


def _pid_exists(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_reaped(pids, started):
    while any(_pid_exists(pid) for pid in pids) and time.monotonic() - started < 0.7:
        time.sleep(0.01)
    assert time.monotonic() - started < 0.75, "cleanup must beat1s natural expiry (and3s bound)"
    assert all(not _pid_exists(pid) for pid in pids), "owned child/group not killed and reaped"


def test_17_child_deadline_kills_and_reaps_only_owned_group(monkeypatch, tmp_path):
    api = _implementation()
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    witness = tmp_path / "owned-pids.json"
    code = (
        "import json,os,subprocess,sys,time\n"
        "from pathlib import Path\n"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(1)'])\n"
        f"Path({str(witness)!r}).write_text(json.dumps([os.getpid(),child.pid]))\n"
        "time.sleep(1)\n"
    )
    phases = []

    def harmless_argv(current, phase):
        phases.append(phase)
        return (sys.executable, "-c", code)

    monkeypatch.setattr(api, "_phase_argv", harmless_argv)
    started = time.monotonic()
    _refuses("0.1s deadline", lambda: api._run_child(
        request_file, 1, deadline=started + 0.1, output_limit=1024,
    ))
    assert witness.is_file(), "deadline test must reach the harmless real child"
    pids = json.loads(witness.read_text(encoding="utf-8"))
    assert len(pids) == 2 and len(set(pids)) == 2
    assert os.getpid() not in pids, "never probe/kill unrelated process groups"
    _wait_reaped(pids, started)
    assert phases == [1], "deadline failure permits no retry or phase2"


def test_18_child_combined_output_overflow_is_bounded_failure(monkeypatch, tmp_path, capsys):
    api = _implementation()
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    witness = tmp_path / "owned-pid.json"
    code = (
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(witness)!r}).write_text(str(os.getpid()))\n"
        "os.write(1,b'x'*32768)\nos.write(2,b'y'*32768)\ntime.sleep(1)\n"
    )
    phases = []

    def harmless_argv(current, phase):
        phases.append(phase)
        return (sys.executable, "-c", code)

    monkeypatch.setattr(api, "_phase_argv", harmless_argv)
    capsys.readouterr()
    started = time.monotonic()
    _refuses("65536 combined bytes against1024 cap", lambda: api._run_child(
        request_file, 1, deadline=started + 2, output_limit=1024,
    ))
    assert witness.is_file(), "overflow test must execute the harmless child"
    _wait_reaped([int(witness.read_text(encoding="utf-8"))], started)
    captured = capsys.readouterr()
    assert len(captured.out.encode()) + len(captured.err.encode()) <= 1024, "combined capture bound"
    retained = sum(path.stat().st_size for path in tmp_path.rglob("*")
                   if path.is_file() and path not in {request_file, witness})
    assert retained <= 1024, "retained combined child output bound"
    assert phases == [1], "overflow is failure, never retry/truncated success"


def test_19_two_fresh_sequential_children_and_one_external_launch(monkeypatch, tmp_path):
    api = _implementation()
    for label in ("zero-then-exit", "nonzero", "echild", "ambiguous", "group-remains"):
        with monkeypatch.context() as patch:
            events = []
            stream = SimpleNamespace(fileno=lambda: 123, close=lambda: events.append("close"))
            child = SimpleNamespace(pid=987654, stdout=stream, returncode=None)

            def unexpected_wait():
                raise AssertionError("portable path must not Popen.wait after reap/ambiguity")

            child.wait = unexpected_wait

            class Selector:
                def __enter__(self):
                    self.ready = True
                    return self

                def __exit__(self, *args):
                    return False

                def register(self, *args):
                    pass

                def unregister(self, *args):
                    pass

                def select(self, timeout):
                    if self.ready:
                        self.ready = False
                        return [(SimpleNamespace(fd=123, fileobj=stream), 1)]
                    return []

            waits = 0

            def waitpid(pid, options):
                nonlocal waits
                assert pid == child.pid and options == os.WNOHANG
                assert "eof" in events, "portable reaping must follow EOF"
                waits += 1
                if label == "echild":
                    raise ChildProcessError("unit external reaper")
                if label == "ambiguous":
                    return child.pid + 1, 0
                if label == "zero-then-exit" and waits == 1:
                    return 0, 0
                events.append("reaped")
                return child.pid, (7 << 8) if label == "nonzero" else 0

            def killpg(pid, sig):
                assert pid == child.pid and sig == 0, "never signal after reap or ambiguity"
                assert "reaped" in events
                events.append("group-probe")
                if label != "group-remains":
                    raise ProcessLookupError("unit group gone")

            def read(fd, size):
                assert fd == 123 and size <= 1025
                events.append("eof")
                return b""

            patch.delattr(os, "waitid", raising=False)
            patch.delattr(os, "WNOWAIT", raising=False)
            patch.setattr(api, "_owned_subreaper", nullcontext)
            patch.setattr(api, "_phase_argv", lambda *args: ("unit-protocol-only",))
            patch.setattr(api.subprocess, "Popen", lambda *args, **kwargs: child)
            patch.setattr(api.selectors, "DefaultSelector", Selector)
            patch.setattr(os, "set_blocking", lambda *args: None)
            patch.setattr(os, "read", read)
            patch.setattr(os, "waitpid", waitpid)
            patch.setattr(os, "killpg", killpg)
            action = lambda: api._run_child(
                tmp_path / "portable-protocol.json", 1,
                deadline=time.monotonic() + 1.0, output_limit=1024,
            )
            if label == "zero-then-exit":
                assert action() is None
                assert waits == 2 and child.returncode == 0
            else:
                causes = {
                    "nonzero": "native phase 1 failed", "echild": "reaped externally",
                    "ambiguous": "ambiguous PID", "group-remains": "external owner teardown",
                }
                with pytest.raises(REFUSAL, match=causes[label]):
                    action()
            expected_last = "close" if label in {"echild", "ambiguous"} else "group-probe"
            assert events[-1] == expected_last
    fixed_request = Path("/var/tmp/qualification/request.json")
    for phase in (1, 2):
        assert api._phase_argv(fixed_request, phase) == (
            "/usr/local/bin/python3.12", "-m", "train.native_qualification",
            "--_phase", str(phase), "--_request", str(fixed_request),
        )
    _refuses("invalid phase", lambda: api._phase_argv(fixed_request, 3))
    _refuses("host path is not worker path", lambda: api._phase_argv(tmp_path / "request.json", 1))
    request = _request(api, tmp_path / "host")
    request = dataclasses.replace(request, bounds=_bounds(api, lifetime_seconds=2))
    launches = []

    class ExternalController:
        def require_approved(self, current):
            launches.append(("approved-external", current))

        def run_once(self, current):
            launches.append(("one-external-launch", current))
            raise RuntimeError("owned service failure, no replacement permitted")

    with monkeypatch.context() as patch:
        patch.setattr(api, "_validate_request", lambda current: None)
        _refuses("one externally owned attempt", lambda: api.attempt_sql_qualification(
            request, controller=ExternalController(),
        ))
    assert [entry[0] for entry in launches] == ["approved-external", "one-external-launch"]
    for first_exit in (0, 7):
        directory = tmp_path / f"children-exit{first_exit}"
        directory.mkdir()
        request_file = directory / "request.json"
        request_file.write_text("{}", encoding="utf-8")
        events_file = directory / "events.jsonl"
        phases = []

        def harmless_argv(current, phase):
            phases.append(phase)
            code = (
                "import json,os,sys,time\nfrom pathlib import Path\n"
                f"p=Path({str(events_file)!r})\nphase={phase}\n"
                "prior=[json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []\n"
                "if phase==2:\n"
                " assert [x['event'] for x in prior]==['start','end']\n"
                " try: os.kill(prior[0]['pid'],0)\n"
                " except ProcessLookupError: pass\n"
                " else: raise RuntimeError('phase1 still alive, overlap or not reaped')\n"
                "with p.open('a') as f:\n"
                " f.write(json.dumps(dict(event='start',phase=phase,pid=os.getpid(),"
                "time=time.monotonic()))+'\\n')\n"
                "with p.open('a') as f:\n"
                " f.write(json.dumps(dict(event='end',phase=phase,pid=os.getpid(),"
                "time=time.monotonic()))+'\\n')\n"
                f"sys.exit({first_exit} if phase==1 else 0)\n"
            )
            return (sys.executable, "-c", code)

        with monkeypatch.context() as patch:
            patch.setattr(api, "_phase_argv", harmless_argv)
            patch.setattr(api, "_decode_worker_transport", lambda payload: {})
            patch.setattr(api, "_request_from_wire", lambda document: request)
            patch.setattr(api, "_validate_request", lambda current: None)
            started = time.monotonic()
            if first_exit:
                try:
                    result = api._worker_main(request_file)
                except RuntimeError:
                    result = 1
                assert result != 0, "phase1 exit7 cannot be worker success"
            else:
                assert api._worker_main(request_file) == 0
            assert time.monotonic() - started < 3
        events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
        assert phases == ([1] if first_exit else [1, 2]), "no retry/phase2 after exit7"
        assert [event["phase"] for event in events] == ([1, 1] if first_exit else [1, 1, 2, 2])
        assert [event["event"] for event in events] == (["start", "end"] * len(phases))
        pids = [event["pid"] for event in events if event["event"] == "start"]
        assert len(set(pids)) == len(phases), "fresh distinct interpreters"
        assert all(not _pid_exists(pid) for pid in pids), "children must be reaped before return"
        if not first_exit:
            assert events[1]["time"] <= events[2]["time"], "strict phase1-before-phase2 order"
    assert len(launches) == 2, "worker must never invoke external controller.run_once"


def test_20_default_precision_rejects_subprecision_budget_overspend(monkeypatch, tmp_path):
    from decimal import Inexact, localcontext, Rounded, ROUND_HALF_EVEN
    from train import native_model

    api = _implementation()
    request = _request(api, tmp_path)
    request = dataclasses.replace(request, bounds=_bounds(
        api, total_ceiling_usd=Decimal("25"), prior_usage_usd=Decimal("25"),
        remaining_worst_case_usd=Decimal("1E-28"),
    ))
    effects = Counter()

    def forbidden_read(*args, **kwargs):
        effects["reads"] += 1
        raise AssertionError("exact budget refusal must precede admission reads")

    class Controller:
        def require_approved(self, current):
            effects["approval"] += 1
            raise AssertionError("exact budget refusal must precede controller approval")

        def run_once(self, current):
            effects["run"] += 1
            raise AssertionError("exact budget refusal must precede controller run")

    with monkeypatch.context() as patch:
        patch.setattr(api, "_path", forbidden_read)
        patch.setattr(api, "_validate_fixture_scope", forbidden_read)
        patch.setattr(api, "_check_asset_bytes", forbidden_read)
        patch.setattr(native_model, "verify_local_model", forbidden_read)
        with localcontext() as context:
            context.prec = 28
            context.rounding = ROUND_HALF_EVEN
            context.traps[Inexact] = False
            context.traps[Rounded] = False
            with pytest.raises(
                ValueError, match=r"^prior plus remaining all-charge cost exceeds ceiling$",
            ) as caught:
                api.attempt_sql_qualification(request, controller=Controller())
            assert str(caught.value) == "prior plus remaining all-charge cost exceeds ceiling"
    assert effects["reads"] == 0
    assert effects["approval"] == 0
    assert effects["run"] == 0


def test_21_low_precision_rejects_rounded_budget_overspend(monkeypatch, tmp_path):
    from decimal import Inexact, localcontext, Rounded, ROUND_HALF_EVEN
    from train import native_model

    api = _implementation()
    request = _request(api, tmp_path)
    request = dataclasses.replace(request, bounds=_bounds(
        api, total_ceiling_usd=Decimal("25"), prior_usage_usd=Decimal("24.99"),
        remaining_worst_case_usd=Decimal("0.02"),
    ))
    effects = Counter()

    def forbidden_read(*args, **kwargs):
        effects["reads"] += 1
        raise AssertionError("exact budget refusal must precede admission reads")

    class Controller:
        def require_approved(self, current):
            effects["approval"] += 1
            raise AssertionError("exact budget refusal must precede controller approval")

        def run_once(self, current):
            effects["run"] += 1
            raise AssertionError("exact budget refusal must precede controller run")

    with monkeypatch.context() as patch:
        patch.setattr(api, "_path", forbidden_read)
        patch.setattr(api, "_validate_fixture_scope", forbidden_read)
        patch.setattr(api, "_check_asset_bytes", forbidden_read)
        patch.setattr(native_model, "verify_local_model", forbidden_read)
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_HALF_EVEN
            context.traps[Inexact] = False
            context.traps[Rounded] = False
            with pytest.raises(
                ValueError, match=r"^prior plus remaining all-charge cost exceeds ceiling$",
            ) as caught:
                api.attempt_sql_qualification(request, controller=Controller())
            assert str(caught.value) == "prior plus remaining all-charge cost exceeds ceiling"
    assert effects["reads"] == 0
    assert effects["approval"] == 0
    assert effects["run"] == 0
