"""Explicit native SQL trainer construction, behind unchanged closed gates.

No training, saving, publishing or dependency/model download is initiated here.
Constructor success would establish wiring only, not generation, gradients,
runtime compatibility or checkpoint restoration. The scoped native policy does
not establish the unresolved runtime/isolation authority, so admission is closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import copy
import os
import pathlib
import re
import sys
from types import SimpleNamespace
from typing import Any

from bench.task import SqlTask
from train import dead_group_probe, grpo_ptc, guards, native_model, sql_bridge


def _load_runtime() -> SimpleNamespace:
    """Import the actual native classes, only in a fresh Unsloth-first process.

    Private seam for labelled constructor tests, never a public admission API.
    Framework imports themselves can have side effects. Do not try to repair
    order by unloading/reimporting modules in an already contaminated process.
    """
    patched_roots = {
        "unsloth", "unsloth_zoo", "torch", "transformers", "trl", "peft",
        "vllm", "accelerate", "bitsandbytes", "datasets",
    }
    present = sorted({name.split(".")[0] for name in sys.modules} & patched_roots)
    if present:
        raise RuntimeError(
            "native training requires a fresh Unsloth-first process; already "
            f"imported framework modules: {', '.join(present)}"
        )

    from unsloth import FastLanguageModel  # noqa: PLC0415

    import torch  # noqa: PLC0415
    from datasets import Dataset  # noqa: PLC0415
    from trl import GRPOConfig, GRPOTrainer  # noqa: PLC0415
    from transformers.utils.chat_template_utils import get_json_schema  # noqa: PLC0415

    return SimpleNamespace(
        FastLanguageModel=FastLanguageModel, torch=torch, Dataset=Dataset,
        GRPOConfig=GRPOConfig, GRPOTrainer=GRPOTrainer,
        get_json_schema=get_json_schema,
    )


def _positive_integer(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _admit_output(output_dir: str | os.PathLike[str]) -> pathlib.Path:
    """Observe a fresh/empty destination; never create, clear or overwrite it.

    Refuse symlinks before resolving, including ancestor links. This is an
    admission check on caller-owned paths, not a race-proof filesystem lease.
    """
    output = pathlib.Path(os.path.abspath(os.fspath(output_dir)))
    for component in (output, *output.parents):
        if component.is_symlink():
            raise ValueError(f"output directory must not traverse a symlink: {component}")
    if output.exists():
        if not output.is_dir():
            raise ValueError(f"output destination is not a directory: {output}")
        if next(output.iterdir(), None) is not None:
            raise ValueError(f"output directory must be fresh or empty: {output}")
    return output


def _native_attribute(trainer: Any, name: str) -> Any:
    try:
        return getattr(trainer, name)
    except AttributeError as exc:
        raise RuntimeError(f"native trainer is missing required attribute {name}") from exc


def _validate_native_view(
    trainer: Any,
    rows: list[dict[str, Any]],
    runtime: SimpleNamespace,
    *,
    max_seq_length: int,
    completion_cap: int,
    chat_template_kwargs: Mapping[str, Any],
) -> None:
    """Check the actual discovered tool and selected native rendering.

    The native suffix method performs its own token-prefix equality check. It
    renders a synthetic tool boundary only; it does not execute a program or
    sample a model. Never replace a rejected template identity in this layer.
    """
    processing_class = _native_attribute(trainer, "processing_class")
    template = _native_attribute(trainer, "chat_template")
    kwargs = _native_attribute(trainer, "chat_template_kwargs")
    environments = _native_attribute(trainer, "_env_tools")
    suffix_method = _native_attribute(trainer, "_get_tool_suffix_ids")
    if not callable(getattr(processing_class, "apply_chat_template", None)):
        raise RuntimeError("native processing_class must support apply_chat_template")
    if template is not None and (not isinstance(template, str) or not template):
        raise RuntimeError("native chat_template must be a template string or None")
    if not isinstance(kwargs, Mapping) or dict(kwargs) != dict(chat_template_kwargs):
        raise RuntimeError("native chat_template_kwargs differ from the unchanged configuration")
    if not isinstance(environments, Mapping) or set(environments) != {None}:
        raise RuntimeError("native _env_tools must contain exactly the unnamed None environment")
    tools = environments[None]
    if not isinstance(tools, (list, tuple)):
        raise RuntimeError("native environment tools must be a sequence")
    guards.assert_one_tool(tools)
    if not callable(tools[0]):
        raise RuntimeError("native run_program tool must be the discovered callable")
    if runtime.get_json_schema(tools[0]) != grpo_ptc.THE_TOOL_SCHEMA:
        raise RuntimeError("native discovered tool schema differs from canonical run_program")
    if not callable(suffix_method):
        raise RuntimeError("native _get_tool_suffix_ids must be callable")

    suffix_ids = suffix_method([{
        "role": "tool", "name": guards.THE_TOOL, "content": "native prefix boundary probe",
    }])
    if (
        not isinstance(suffix_ids, list) or not suffix_ids
        or any(isinstance(token, bool) or not isinstance(token, int) or token < 0
               for token in suffix_ids)
    ):
        raise RuntimeError("native _get_tool_suffix_ids returned invalid prefix boundary tokens")

    for row in rows:
        # A present native None means the actual Trainer chose no override.
        # A missing attribute never falls back to the tokenizer's stock view.
        ids = processing_class.apply_chat_template(
            copy.deepcopy(row["prompt"]),
            tools=tools,
            chat_template=template,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=False,
            **kwargs,
        )
        if (
            not isinstance(ids, list) or not ids
            or any(isinstance(token, bool) or not isinstance(token, int) or token < 0
                   for token in ids)
        ):
            raise RuntimeError("native prompt tokenization must return a nonempty token ID list")
        needed = len(ids) + completion_cap
        if needed > max_seq_length:
            raise ValueError(
                f"task {row['task_id']!r} native prompt length {len(ids)} plus "
                f"completion cap {completion_cap} needs context {needed}, "
                f"above caller max_seq_length {max_seq_length}"
            )


def build_sql_trainer(
    tasks: Iterable[SqlTask],
    db_root: str | pathlib.Path,
    *,
    output_dir: str | os.PathLike[str],
    model_dir: str | os.PathLike[str],
    model_revision: str,
    max_seq_length: int,
    steps: int = 200,
    root: pathlib.Path = guards.REPO_ROOT,
) -> Any:
    """Construct an explicit-task native Trainer; never start training.

    Only caller input/path admission precedes the real preflight. Both real
    gates must pass before artifact reads, schema preparation or framework loading.
    The revision selects a source-pinned inventory, never a mutable repository
    reference passed to vLLM. Byte admission is not source isolation. Partial
    constructor failures may leave allocated runtime resources; no cleanup is claimed.
    """
    if (
        not isinstance(model_revision, str)
        or re.fullmatch(r"[0-9a-fA-F]{40}", model_revision) is None
    ):
        raise ValueError("model_revision must be a full 40-hex revision")
    _positive_integer(max_seq_length, "max_seq_length")
    _positive_integer(steps, "steps")
    output = _admit_output(output_dir)
    model_path = pathlib.Path(model_dir)
    if not model_path.is_absolute() or ".." in model_path.parts:
        raise ValueError("model_dir must be an absolute canonical directory")

    config = dict(grpo_ptc.native_sql_preflight(root=root, steps=steps))
    if max_seq_length <= config["max_completion_length"]:
        raise ValueError("max_seq_length must leave prompt context beyond the completion cap")
    source = native_model.verify_local_model(model_path, model_revision=model_revision)
    prepared = sql_bridge.prepare_sql_training(tasks, db_root, root=root)
    runtime = _load_runtime()
    dataset = runtime.Dataset.from_list(prepared.dataset_rows)
    per_device, accumulation = dead_group_probe.batch_for(dead_group_probe.NUM_GENERATIONS)
    config.update(
        output_dir=str(output),
        remove_unused_columns=False,
        per_device_train_batch_size=per_device,
        gradient_accumulation_steps=accumulation,
        max_tool_calling_iterations=prepared.max_tool_calling_iterations,
        save_strategy="steps",
        save_steps=steps,
        save_only_model=False,
        push_to_hub=False,
    )
    model, tokenizer = runtime.FastLanguageModel.from_pretrained(
        model_name=source.path,
        use_exact_model_name=True,
        local_files_only=True,
        dtype=runtime.torch.float16,
        max_seq_length=max_seq_length,
        load_in_4bit=False,
        fast_inference=True,
        max_lora_rank=dead_group_probe.LORA_RANK,
        gpu_memory_utilization=dead_group_probe.GPU_MEMORY_UTILIZATION,
    )
    model = runtime.FastLanguageModel.get_peft_model(
        model, r=dead_group_probe.LORA_RANK, lora_alpha=dead_group_probe.LORA_RANK,
    )
    trainer = runtime.GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=[prepared.reward],
        args=runtime.GRPOConfig(**config),
        train_dataset=dataset,
        environment_factory=prepared.environment_factory,
    )
    _validate_native_view(
        trainer, prepared.dataset_rows, runtime,
        max_seq_length=max_seq_length,
        completion_cap=config["max_completion_length"],
        chat_template_kwargs=config["chat_template_kwargs"],
    )
    return trainer
