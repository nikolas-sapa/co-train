"""The bash arm's defect-report channel, delivered mid-run by request interception.

The PTC arm files allegations through its program catalog (`ptc/harness.py`). A
bash program has no catalog -- its only action is a shell command -- so the
channel reaches it through a different composition of the same pieces:

* The caller mixes `BashQaTaskMixin` BEFORE its Task class, creates ONE
  `BashQaBinding` shared by task and harness, supplies `qa_factory` plus a
  `QaBashHarnessConfig`, and runs the agent through `run_bash_qa` -- the only
  entry point. Every other route (bare `agent.run`, `agent.interaction`,
  resume, a reconstructed harness) refuses before the first action.
* At launch the paired `QaBashHarness` claims a fresh `QaChannel` atomically
  (the channel's existing one-shot `_claim_launch`), installs the existing
  `report_defect` shim into a unique owned directory under the subprocess
  runtime's workdir, prepends it to the program PATH for exactly that launch,
  and appends `REPORT_PROMPT + BASH_REPORT` to a launch-local TaskData copy.
* The shim prints the public `COTRAIN_QA_REPORT` marker on stdout; the bash
  tool result carrying it is rewritten by the task-side `@intercept` BEFORE
  the next model request -- never a post-hoc scan -- so the model reads the
  fixed receipt in-band. Provenance stays `agent_output`: a marker in shell
  output attests to the bytes, not to who produced them (the frame remains
  forgeable, by design).
* The framework pins every rewrite to its conversation prefix + call id, so a
  replayed history re-imposes the receipt-bearing result; a private
  occurrence cache keyed on (issuing assistant position, call id) deduplicates
  pre-commit replays so no result is consumed twice and none is scanned
  twice.

Bounds: at most 64 uncommitted rewrites per registration (a 65th raises
`TaskError` before any collector mutation), `consume_output`'s own appended
feedback caps at 8 lines plus one cap notice, and the framework's 20 KB
head/tail rebounding runs after the rewrite -- a receipt lands in the kept
tail. Every refusal is fail-closed: a real tool result reaching a missing,
unready or closed registration raises `TaskError`; unsupported shapes
(non-subprocess runtime, borrowed box, resume, compaction, edit/search, MCP
toolsets, skills, non-string prompt, unbounded turns, retries) refuse before
any policy or tool action. The disabled path is byte-for-byte the baseline:
`ptc.sql_qa` is only imported inside the enabled launch, and no tracking
state, wrapper, PATH or prompt change exists without a factory.

Marker lines remain forgeable -- this enforces launch ownership and delivery,
not authenticity. Reports are data for a reviewer, never authority.
"""

from __future__ import annotations

import os
import shutil
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import PrivateAttr

from verifiers.v1.agent import Agent
from verifiers.v1.clients import ModelContext
from verifiers.v1.errors import TaskError
from verifiers.v1.graph import message_hash, message_prefix_len
from verifiers.v1.harnesses.bash.harness import BashHarness, BashHarnessConfig
from verifiers.v1.runtimes import ProgramResult, Runtime, SubprocessConfig
from verifiers.v1.runtimes.subprocess import SubprocessRuntime
from verifiers.v1.task import Task, TaskData
from verifiers.v1.trace import Trace
from verifiers.v1.types import AssistantMessage, Request, ToolCall, ToolMessage
from verifiers.v1.utils.decorators import intercept

__all__ = [
    "QaBashHarnessConfig",
    "BashQaBinding",
    "BashQaTaskMixin",
    "QaBashHarness",
    "run_bash_qa",
    "MAX_PENDING_OCCURRENCES",
]

MAX_PENDING_OCCURRENCES = 64
"""Rewrites cached for tool results the graph has not committed yet. One
allegation flood is bounded by the collector's own arm quotas; this bound
keeps a pathological history from growing routing state without it. The 65th
uncommitted occurrence raises `TaskError` before the collector is touched."""


class _Permit:
    """The entry point's capability: this exact task on this exact harness
    through this exact binding, valid for one `run_bash_qa` call. Held on a
    ContextVar so `task.setup` can demand it before doing any work -- a direct
    `agent.run` finds nothing and refuses."""

    __slots__ = ("task", "harness", "binding")

    def __init__(self, task: Task, harness: "QaBashHarness",
                 binding: "BashQaBinding") -> None:
        self.task = task
        self.harness = harness
        self.binding = binding


_permit: ContextVar[_Permit | None] = ContextVar(
    "ptc_bash_qa_permit", default=None)


@dataclass(frozen=True)
class _Occurrence:
    """One rewritten tool-result occurrence, keyed (assistant position, call
    id): the issuing message's fingerprint, the result's absolute position
    (for committed-prefix pruning), and the original -> rewritten contents."""

    fingerprint: str
    tool_pos: int
    original: str
    rewritten: str


class _Route:
    """One trace's registration on its binding. Retains the Trace strongly so
    `id(trace)` cannot be recycled while registered; dropped on cleanup."""

    __slots__ = (
        "permit", "trace", "task_data", "state", "channel", "launched",
        "cache",
    )

    def __init__(self, permit: _Permit, trace: Trace,
                 task_data: TaskData) -> None:
        self.permit = permit
        self.trace = trace
        self.task_data = task_data
        self.state = "setup"  # setup -> ready -> active -> closed
        self.channel = None
        self.launched = False
        self.cache: dict[tuple[int, str], _Occurrence] = {}


class BashQaBinding:
    """The routing table shared by the paired task mixin and harness.

    Keyed on `id(trace)` with the Trace object retained -- never on task,
    task data, or "the current channel" -- so two overlapping launches route
    by identity and a completed registration leaves no history behind. Plain
    dict, no locks: every use is synchronous on the event loop.
    """

    def __init__(self) -> None:
        self._routes: dict[int, _Route] = {}

    def _register(self, permit: _Permit, trace: Trace,
                  task_data: TaskData) -> _Route:
        if id(trace) in self._routes:
            raise TaskError("this trace is already registered")
        route = _Route(permit, trace, task_data)
        self._routes[id(trace)] = route
        return route

    def _lookup(self, trace: Trace) -> _Route | None:
        route = self._routes.get(id(trace))
        return route if route is not None and route.trace is trace else None

    def _remove(self, trace: Trace) -> None:
        route = self._routes.get(id(trace))
        if route is not None and route.trace is trace:
            del self._routes[id(trace)]

    def _clear_permit(self, permit: _Permit) -> None:
        """Drop every registration this entry-point call owns -- the cleanup
        for an aborted setup the framework never finalizes."""
        for key, route in list(self._routes.items()):
            if route.permit is not permit:
                continue
            route.state = "closed"
            del self._routes[key]


class QaBashHarnessConfig(BashHarnessConfig):
    """A `BashHarnessConfig` carrying the reporting intent marker privately:
    `_qa_required` survives `model_copy` (the skills-clone the framework
    performs on its own) but is absent from every dump and schema, so a
    config that arrived without the factory and binding it was created with
    cannot silently run unreported -- the constructor refuses it."""

    _qa_required: bool = PrivateAttr(default=False)


class BashQaTaskMixin:
    """Mix BEFORE the caller's existing Task class: `class T(BashQaTaskMixin, T0)`.

    Owns the launch half the harness cannot see: registration is keyed on the
    rollout's Trace at `setup`, invalidated before `finalize`, and dropped at
    either. `setup`/`finalize` are ordinary overrides -- the only decorated
    method is the request interceptor, because request interceptors are
    discovered on the TASK, never on a harness.
    """

    def __init__(self, *args: Any, qa_binding: BashQaBinding,
                 **kwargs: Any) -> None:
        if not isinstance(qa_binding, BashQaBinding):
            raise TypeError(
                "qa_binding must be a BashQaBinding, got "
                f"{type(qa_binding).__name__}"
            )
        self._qa_binding = qa_binding
        super().__init__(*args, **kwargs)

    async def setup(self, trace: Trace, runtime: Runtime) -> None:
        permit = _permit.get()
        if (permit is None or permit.task is not self
                or permit.binding is not self._qa_binding):
            raise TaskError(
                "qa reporting requires the run_bash_qa entry point: this "
                "task may not launch through a bare agent.run"
            )
        route = self._qa_binding._register(permit, trace, self.data)
        try:
            await super().setup(trace, runtime)
        except BaseException:
            self._qa_binding._remove(trace)
            raise
        route.state = "ready"

    async def finalize(self, trace: Trace, runtime: Runtime) -> None:
        route = self._qa_binding._lookup(trace)
        if route is not None:
            # Invalidate first: no interception still in flight may consume
            # into the channel after this point.
            route.state = "closed"
        try:
            await super().finalize(trace, runtime)
        finally:
            self._qa_binding._remove(trace)

    @intercept
    def _qa_rewrite(self, request: Request, trace: Trace) -> Request | None:
        """Rewrite the uncommitted tail bash ToolMessage through the channel.

        Sync, on purpose: look-up, consume and cache update happen in one
        stretch with no intervening await, so a consumed line can never be
        scanned by a second handler or submitted twice. Returns a replacement
        Request only when the tail's content changed; None leaves it alone.
        The framework calls hooks once per uncommitted tail boundary and pins
        each rewrite to its conversation prefix + call id.
        """
        messages = request.messages
        tail = messages[-1] if messages else None
        if (not isinstance(tail, ToolMessage)
                or not isinstance(tail.content, str) or not tail.content):
            # Non-tool tails (user turns), multimodal results, and the empty
            # synthetic tool-result probes the /tool gate synthesizes are all
            # not ours: no consume, and no cache entry either.
            return None
        route = self._qa_binding._lookup(trace)
        if (route is None or route.state != "active"
                or route.channel is None):
            raise TaskError(
                "qa reporting received a tool result with no active launch: "
                "refusing to drop or recreate the channel"
            )
        # Evict occurrences the graph has already committed: they can never
        # arrive at the tail again, so their cache slots are spent.
        prefix_len = message_prefix_len(trace, messages)
        cache = route.cache
        for key, entry in list(cache.items()):
            if entry.tool_pos < prefix_len:
                del cache[key]
        position, call = _issuing_call(messages, tail)
        if call is None:
            raise TaskError(
                f"tool result {tail.tool_call_id!r} has no issuing call"
            )
        if call.name != "bash":
            return None
        fingerprint = message_hash(messages[position])
        key = (position, call.id)
        entry = cache.get(key)
        if entry is not None:
            if entry.fingerprint != fingerprint:
                raise TaskError(
                    "qa occurrence fingerprint mismatch: refusing to reuse "
                    "a rewrite across different issuing messages"
                )
            if tail.content == entry.rewritten:
                return None  # the pinned form came back: already ours
            if tail.content != entry.original:
                raise TaskError(
                    "qa occurrence content drifted between requests"
                )
            rewritten = entry.rewritten  # replay: no resubmission
        else:
            if len(cache) >= MAX_PENDING_OCCURRENCES:
                raise TaskError(
                    f"over {MAX_PENDING_OCCURRENCES} uncommitted report "
                    "rewrites; refusing before collector mutation"
                )
            rewritten = route.channel.consume_output("bash", tail.content)
            if rewritten == tail.content:
                return None
            cache[key] = _Occurrence(
                fingerprint, len(messages) - 1, tail.content, rewritten)
        updated = list(messages)
        updated[-1] = tail.model_copy(update={"content": rewritten})
        return request.model_copy(update={"messages": updated})


_QA_OWNER_ATTR = "_cotrain_qa_owner"


def _claim_runtime(runtime: Runtime) -> object:
    """Take exclusive ownership of this runtime object for one launch.

    Synchronous, and it lives ON the runtime, so the same physical box is
    refused to a second launch no matter which task/harness/binding tries it.
    Returns the unique owner identity the launch must hand back to release.
    """
    owner = object()
    if getattr(runtime, _QA_OWNER_ATTR, None) is not None:
        raise ValueError("this runtime already hosts an in-flight qa launch")
    setattr(runtime, _QA_OWNER_ATTR, owner)
    return owner


def _release_runtime(runtime: Runtime, owner: object) -> None:
    """Release the claim only while this launch still owns it."""
    if getattr(runtime, _QA_OWNER_ATTR, None) is owner:
        delattr(runtime, _QA_OWNER_ATTR)


def _issuing_call(messages: list, tail: ToolMessage
                  ) -> tuple[int | None, ToolCall | None]:
    """The (position, ToolCall) whose id the tail result answers, scanning
    back from the tail. A result without an issuer is malformed input."""
    for position in range(len(messages) - 2, -1, -1):
        message = messages[position]
        if not isinstance(message, AssistantMessage):
            continue
        for call in message.tool_calls or []:
            if call.id == tail.tool_call_id:
                return position, call
    return None, None


class QaBashHarness(BashHarness):
    """A `BashHarness` that launches with a claimed `QaChannel` and the
    `report_defect` shim on the program's PATH for exactly that launch.

    Disabled (`qa_factory`/`qa_binding` both None, config unmarked) is a pure
    delegate: nothing here runs, imports or allocates. An enabled harness
    copies the supplied config and stamps `_qa_required` on its own copy --
    the private marker the skills-clone path cannot lose.
    """

    SUPPORTS_RESUME = False

    def __init__(
        self,
        config: QaBashHarnessConfig,
        *,
        qa_factory: Any = None,
        qa_binding: BashQaBinding | None = None,
    ) -> None:
        marked = getattr(config, "_qa_required", False)
        if qa_factory is None or qa_binding is None:
            if marked:
                raise ValueError(
                    "a marked QaBashHarnessConfig requires qa_factory and "
                    "qa_binding; a reconstruction without them cannot run"
                )
            if qa_factory is not None or qa_binding is not None:
                raise ValueError(
                    "qa_factory and qa_binding must be supplied together"
                )
            super().__init__(config)
            self._qa_factory = None
            self._qa_binding = None
            return
        if not isinstance(config, QaBashHarnessConfig):
            raise TypeError(
                "qa reporting requires a QaBashHarnessConfig, got "
                f"{type(config).__name__}"
            )
        if not callable(qa_factory):
            raise TypeError(
                f"qa_factory must be callable, got {type(qa_factory).__name__}"
            )
        if not isinstance(qa_binding, BashQaBinding):
            raise TypeError(
                "qa_binding must be a BashQaBinding, got "
                f"{type(qa_binding).__name__}"
            )
        if config.skills:
            raise ValueError("qa reporting does not support skills")
        if config.compaction is not None:
            raise ValueError("qa reporting does not support compaction")
        # Copy, then mark our OWN copy: the caller's config stays unmarked.
        marked_config = config.model_copy()
        marked_config._qa_required = True
        super().__init__(marked_config)
        self._qa_factory = qa_factory
        self._qa_binding = qa_binding

    async def launch(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
        data: TaskData,
        tool_interception_url: str | None = None,
    ) -> ProgramResult:
        if self._qa_binding is None:
            return await super().launch(
                ctx, trace, runtime, endpoint, secret, mcp_urls, data,
                tool_interception_url=tool_interception_url,
            )
        # The only ptc.sql_qa import site in this module: disabled launches
        # never touch it.
        from ptc.sql_qa import (
            BASH_REPORT,
            REPORT_PROMPT,
            QaChannel,
            install_report_wrapper,
        )
        binding = self._qa_binding
        route = binding._lookup(trace)
        if route is None or route.state != "ready" or route.launched:
            raise ValueError(
                "qa launch requires a ready registration on an unlaunched "
                "trace; the run_bash_qa entry point creates one per run"
            )
        route.launched = True
        if not isinstance(runtime, SubprocessRuntime) or runtime.workdir is None:
            raise TypeError(
                "qa reporting supports only a started subprocess runtime, "
                f"got {type(runtime).__name__}"
            )
        if not tool_interception_url:
            raise ValueError(
                "qa reporting requires the tool-interception gate; a task "
                "without a discovered interceptor cannot launch reported"
            )
        if "PATH" in self.config.resolved_env:
            raise ValueError(
                "an enabled qa harness refuses a config PATH override; the "
                "launch prepends its own owned directory"
            )
        # The original TaskData object captured at task.setup, not the
        # (possibly rewritten) launch-time harness data.
        channel = self._qa_factory(route.task_data)
        if type(channel) is not QaChannel:
            raise TypeError(
                "qa_factory must return a QaChannel, got "
                f"{type(channel).__name__}"
            )
        channel._claim_launch()  # atomic one-shot; stays spent on any failure
        # Exclusive ownership lives on the runtime object itself: the same
        # physical box is refused across ANY binding, not only this one.
        bindir = Path(runtime.workdir) / f".qa-report-{uuid.uuid4().hex}"
        had_path = "PATH" in runtime.env
        previous_path = runtime.env.get("PATH")
        owner = _claim_runtime(runtime)
        try:
            # Wrapper first, PATH only after the shim is in place: the program
            # never sees a half-provisioned channel.
            install_report_wrapper(bindir)
            # Presence, not truthiness: an explicit "" PATH stays "".
            effective = (
                previous_path
                if had_path
                else os.environ.get("PATH", os.defpath)
            )
            runtime.env["PATH"] = f"{bindir}{os.pathsep}{effective}"
            route.channel = channel
            route.state = "active"
            qa_data = data.model_copy(update={
                "system_prompt": "\n\n".join(
                    p for p in (data.system_prompt, REPORT_PROMPT + BASH_REPORT)
                    if p
                ),
            })
            return await super().launch(
                ctx, trace, runtime, endpoint, secret, mcp_urls, qa_data,
                tool_interception_url=tool_interception_url,
            )
        finally:
            # Invalidate synchronously, restore exact PATH presence/value,
            # remove only the owned directory, release runtime ownership. A
            # cleanup failure surfaces; the channel stays spent.
            route.state = "closed"
            try:
                if had_path:
                    runtime.env["PATH"] = previous_path
                else:
                    runtime.env.pop("PATH", None)
                if bindir.exists():
                    shutil.rmtree(bindir)
            finally:
                _release_runtime(runtime, owner)


async def run_bash_qa(agent: Agent, task: Task) -> Trace:
    """The only supported entry point for a reporting Bash rollout.

    Validates the pairing and every unsupported setting BEFORE `agent.run`,
    then holds a ContextVar permit for the run's duration so `task.setup` can
    prove it was reached through here. Refuses rather than silently modifies:
    a borrowed or non-subprocess runtime, a non-string or absent prompt,
    skills, compaction, edit/search tools, MCP toolsets, unbounded turns and
    retries all fail here with zero actions taken.
    """
    if not isinstance(agent, Agent):
        raise TypeError(
            f"agent must be a verifiers Agent, got {type(agent).__name__}")
    if not isinstance(task, BashQaTaskMixin):
        raise TypeError(
            "run_bash_qa requires a task mixing in BashQaTaskMixin, got "
            f"{type(task).__name__}"
        )
    harness = agent.harness
    if not isinstance(harness, QaBashHarness):
        raise TypeError(
            "run_bash_qa requires the agent's harness to be a QaBashHarness, "
            f"got {type(harness).__name__}"
        )
    binding = task._qa_binding
    if harness._qa_binding is not binding or not callable(harness._qa_factory):
        raise ValueError(
            "task and harness must share one BashQaBinding with an enabled "
            "qa_factory"
        )
    if not getattr(harness.config, "_qa_required", False):
        raise ValueError(
            "the harness config carries no qa intent marker; an unpaired "
            "composition cannot launch reported"
        )
    config = harness.config
    if not isinstance(agent.runtime_config, SubprocessConfig):
        raise TypeError(
            "qa reporting supports only the subprocess runtime config, got "
            f"{type(agent.runtime_config).__name__}"
        )
    if not isinstance(task.data.prompt, str):
        raise ValueError(
            "qa reporting requires a string opening prompt (no replay, no "
            "user-opened exchange)"
        )
    if task.data.skills or config.skills:
        raise ValueError("qa reporting does not support skills")
    if config.compaction is not None:
        raise ValueError("qa reporting does not support compaction")
    if config.edit:
        raise ValueError("qa reporting requires edit=False")
    if config.search:
        raise ValueError("qa reporting requires search=False")
    if task.toolsets(task.config):
        raise ValueError("qa reporting does not support MCP toolsets")
    if (not isinstance(agent.limits.max_turns, int)
            or agent.limits.max_turns <= 0):
        raise ValueError(
            "qa reporting requires a finite positive max_turns limit"
        )
    if agent.config.retries.max_retries != 0:
        raise ValueError("qa reporting does not support rollout retries")
    permit = _Permit(task=task, harness=harness, binding=binding)
    token = _permit.set(permit)
    try:
        return await agent.run(task)
    finally:
        _permit.reset(token)
        binding._clear_permit(permit)
