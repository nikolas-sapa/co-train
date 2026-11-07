"""Shared-composition seam, deliberately not a runnable product plugin."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
import stat
from typing import TYPE_CHECKING

from verifiers.v1.runtimes import Runtime
from verifiers.v1.runtimes.docker import DockerConfig

from ptc.bash_owned_runtime import BashOwnedDockerRuntime, BridgeLimits
from ptc.bird_sql_broker import TaskSqlBrokerConfig
from ptc.sql_owned_bash import BashSqlBinding, BashSqlError, public_bash_prompt

if TYPE_CHECKING:
    from train.sql_live_reuse import SqlLiveInput

__all__ = [
    "BashTaskResources", "bind_bash_sql_leaf", "public_bash_prompt",
    "require_production_bash_runtime",
]


@dataclass(frozen=True)
class BashTaskResources:
    input: "SqlLiveInput"
    runtime_config: DockerConfig
    broker_config: TaskSqlBrokerConfig
    db_size_bytes: int
    interpreter: str
    scratch: Path
    engine_binary: str
    limits: BridgeLimits
    source_pins: tuple[tuple[str, str], ...]

    def check(self):
        if (type(self.runtime_config) is not DockerConfig
                or type(self.broker_config) is not TaskSqlBrokerConfig
                or type(self.limits) is not BridgeLimits
                or type(self.db_size_bytes) is not int or self.db_size_bytes <= 0
                or not isinstance(self.scratch, Path) or not self.scratch.is_absolute()
                or any(type(value) is not str or not Path(value).is_absolute()
                       or str(Path(value)) != value
                       for value in (self.interpreter, self.engine_binary))
                or type(self.source_pins) is not tuple or not self.source_pins):
            raise BashSqlError("explicit original Bash resources required")
        scratch = self.scratch.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(scratch.st_mode) or scratch.st_uid != os.geteuid()
                or stat.S_IMODE(scratch.st_mode) != 0o700
                or str(self.scratch.resolve(strict=True)) != str(self.scratch)
                or type(self.runtime_config.workdir) is not str
                or not Path(self.runtime_config.workdir).is_absolute()):
            raise BashSqlError("explicit private Bash scratch and workdir required")
        paths = []
        for path, digest in self.source_pins:
            if (type(path) is not str or not Path(path).is_absolute()
                    or path in paths or type(digest) is not str
                    or len(digest) != 64
                    or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest):
                raise BashSqlError("approved Bash source binding differs")
            paths.append(path)
        self.broker_config.__post_init__()
        self.limits.__post_init__()


@dataclass(frozen=True)
class _BoundBashResources:
    spec: BashTaskResources
    task: object
    agent: object
    harness: object
    binding: BashSqlBinding
    owner: BashOwnedDockerRuntime


def _bind_resources(association, spec):
    spec.check()
    binding = bind_bash_sql_leaf(
        task=association.task, sql_task=association.row.task,
        instrument=association.instrument, harness=association.harness,
        broker_config=spec.broker_config, db_sha256=association.row.db_sha256,
        db_size_bytes=spec.db_size_bytes, schema=association.row.schema,
        host_authority=association.host_authority)
    owner = BashOwnedDockerRuntime(
        spec.runtime_config, harness=association.harness, binding=binding,
        interpreter=spec.interpreter, scratch=spec.scratch,
        engine_binary=spec.engine_binary, limits=spec.limits, mcp_urls={})
    return _BoundBashResources(
        spec, association.task, association.agent, association.harness, binding, owner)


def bind_bash_sql_leaf(*, schema: str, **binding) -> BashSqlBinding:
    return BashSqlBinding(schema=schema, **binding)


def require_production_bash_runtime(runtime: Runtime | None) -> None:
    # No existing concrete runtime owns and qualifies the complete Bash path.
    # Accepting an interface, flag or profile digest would invent that authority.
    raise BashSqlError(
        "externally qualified full-shell runtime and shared Env hook required; "
        "SQL-only diagnostics are not the original Bash baseline")
