"""Optional monitored SQL trainer construction, behind the original closed gates."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import os
import pathlib
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from train.sql_capture import SqlCapture
    from train.sql_episodes import EpisodeIds
    from train.sql_reporting import ReportingConfig

from bench.task import SqlTask
from train import native_training
from train.run_monitor import RunMonitor


class MonitoredSqlTrainer(NamedTuple):
    trainer: Any
    monitor: RunMonitor


def _make_callback(monitor: RunMonitor):
    from transformers.trainer_callback import TrainerCallback

    class _MonitoredSqlCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs is not None:
                monitor.observe(logs)
            if monitor.aborted is not None:
                control.should_training_stop = True
            return control

    return _MonitoredSqlCallback()


def build_monitored_sql_trainer(
    tasks: Iterable[SqlTask],
    db_root: str | pathlib.Path,
    *,
    output_dir: str | os.PathLike[str],
    model_dir: str | os.PathLike[str],
    model_revision: str,
    max_seq_length: int,
    steps: int = 200,
    root: pathlib.Path = native_training.guards.REPO_ROOT,
    reporting: ReportingConfig | None = None,
    capture_ids: Callable[[str], EpisodeIds] | None = None,
    capture_sink: Callable[[SqlCapture], None] | None = None,
) -> MonitoredSqlTrainer:
    """Attach one callback after successful original construction; never train."""
    trainer = native_training.build_sql_trainer(
        tasks,
        db_root,
        output_dir=output_dir,
        model_dir=model_dir,
        model_revision=model_revision,
        max_seq_length=max_seq_length,
        steps=steps,
        root=root,
        **({"reporting": reporting} if reporting is not None else {}),
        **({"capture_ids": capture_ids, "capture_sink": capture_sink}
           if capture_ids is not None or capture_sink is not None else {}),
    )
    monitor = RunMonitor()
    callback = _make_callback(monitor)
    trainer.add_callback(callback)
    return MonitoredSqlTrainer(trainer=trainer, monitor=monitor)
