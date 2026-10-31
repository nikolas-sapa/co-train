"""SHORTCUT: synthetic taskset. No corpus, toolsets or policy calls."""
from typing import Literal

from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset

from ptc.bash_qa import BashQaTaskMixin

__all__ = ["ProbeTaskset"]


class SeedTask(Task):
    def build_bash_qa_task(self, binding):
        # PROVES: explicit paired subclass construction, not arbitrary wrapping.
        return PairedTask(self.data, self.config, qa_binding=binding)


class PairedTask(BashQaTaskMixin, SeedTask):
    pass


class ProbeTasksetConfig(TasksetConfig):
    id: Literal["qa_eval_probe_taskset"] = "qa_eval_probe_taskset"


class ProbeTaskset(Taskset[SeedTask, ProbeTasksetConfig]):
    def load(self):
        yield SeedTask(TaskData(prompt="Synthetic probe."), self.config.task)
