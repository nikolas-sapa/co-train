"""SHORTCUT: one synthetic seed. No corpus, toolsets or model dependency."""
from typing import Literal

from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from ptc.bash_qa import BashQaTaskMixin

__all__ = ["ProbeTaskset"]


class SeedTask(Task):
    def build_bash_qa_task(self, binding):
        # PROVES: explicit paired subclass keeps exact seed data/config.
        return PairedTask(self.data, self.config, qa_binding=binding)


class PairedTask(BashQaTaskMixin, SeedTask):
    pass


class ProbeTasksetConfig(TasksetConfig):
    id: Literal["qa_eval_execution_taskset"] = "qa_eval_execution_taskset"


class ProbeTaskset(Taskset[SeedTask, ProbeTasksetConfig]):
    def load(self):
        yield SeedTask(TaskData(prompt="Synthetic probe."), self.config.task)
