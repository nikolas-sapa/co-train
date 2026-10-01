"""A `verifiers` Harness whose only action channel is a program over a typed catalog.

Runs its loop in-process. `Harness.launch`'s contract permits that explicitly: "a
harness may run its loop in-process instead of launching a program, as long as every
model call goes through `endpoint` + `secret`" -- so there is no program to install and
no container to bring up.

The model gets exactly one tool, `run_program(code)`. The catalog lives INSIDE the
program, not alongside it as sibling tools; that is the distinction between PTC and
plain typed-tool calling, and it is the axis this project measures.

ponytail: a fixed catalog supplied by config, not MCP-derived. MCP wiring is the upgrade
path when a real task suite needs it; it is not needed to stand the arm up.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import AsyncExitStack
from typing import Any

import httpx
from pydantic import Field

from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.harness import HarnessConfig
from verifiers.v1.harness import Harness
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import TaskData
from verifiers.v1.trace import Trace

from verifiers.v1.harnesses.utils.mcp import call_mcp, connect_mcp

from ptc.runtime import TIMEOUT as runtime_timeout, Catalog, ProgramRejected, run as run_program

__all__ = ["PTCHarness"]

SYSTEM = (
    "You act by writing a Python program and submitting it with the `run_program` tool. "
    "The program may call only these catalog functions: {names}. "
    "Pass their arguments BY KEYWORD, exactly as named above: the catalog takes no "
    "positional arguments and `f(x)` is rejected where `f(id=x)` is accepted. "
    "There is no shell and no other action channel. Imports and attribute access are "
    "rejected before the program runs. Control flow, arithmetic and comprehensions are "
    "available, so prefer one program that does the whole task over many small ones. "
    "Use `print(...)` to report anything you need to see: the program's printed output "
    "is all you get back, so a program that calls a tool without printing its result "
    "tells you nothing."
)

OBSERVE = "print"
"""The program's only observation channel.

`print` is already in `runtime.SAFE_BUILTINS`, but its output would go to the harness
process's stdout, where the model cannot see it. A catalog entry shadows the builtin --
`run()` execs with the catalog as globals, so a global `print` wins name resolution --
and captures per program instead. Chosen over `contextlib.redirect_stdout` because that
mutates `sys.stdout` process-wide and programs run in a worker thread: two concurrent
rollouts would capture each other's output.
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_program",
        "description": "Execute a Python program against the typed catalog.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "The program."}},
            "required": ["code"],
        },
    },
}]


def _mcp_catalog(
    mcp_urls: dict[str, str], stack: AsyncExitStack, timeout: float
) -> Any:
    """Build catalog functions from the task's MCP servers.

    Returns a coroutine's worth of work; see `launch`. Each tool becomes an ordinary
    SYNCHRONOUS function, because that is what the paper's PTC exposes and what a
    program validated by `runtime.validate` can call -- `await` is not in ALLOWED_NODES
    and adding it would change the interface under measurement. The bridge is
    `run_coroutine_threadsafe` against the loop the harness is running on, with the
    program itself moved off that loop by `asyncio.to_thread`.

    ponytail: one blocking thread per program, and a tool call inside a program is
    serialized against the loop rather than gathered. Fine at one program per turn; if
    a task ever needs concurrent tool calls inside one program, the upgrade is an
    async catalog and an async runtime, which is a different interface and needs saying
    out loud rather than sneaking in.
    """
    async def build() -> tuple[dict[str, Any], list[str], dict[str, list[str]]]:
        config = {"mcpServers": {name: {"url": url} for name, url in mcp_urls.items()}}
        schemas, dispatch, servers = await connect_mcp(config, stack)
        loop = asyncio.get_running_loop()
        callable_names, unusable = partition_callable(dispatch)
        tools = {
            name: _bridge(name, servers, dispatch, loop, timeout)
            for name in callable_names
        }
        params = {
            name: args for name, args in schema_params(schemas).items()
            if name in tools
        }
        return tools, unusable, params

    return build()


def schema_params(schemas) -> dict[str, list[str]]:
    """Argument names per tool, read off the MCP schemas `connect_mcp` already returns.

    These were discarded for the first real run, and the prompt advertised bare names.
    `_bridge` is keyword-only on purpose, so a model given only `ledger_get` has nothing
    to guess from and guesses positionally: 26 of that run's 54 PTC tool failures were
    `takes 0 positional arguments but 1 was given`, with 8 more arriving as the same
    mistake wearing a pydantic `Field required`. Required arguments come first so the
    rendered signature reads in the order the tool actually needs.
    """
    out: dict[str, list[str]] = {}
    for schema in schemas or []:
        function = schema.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        parameters = function.get("parameters") or {}
        properties = parameters.get("properties") or {}
        required = [p for p in parameters.get("required") or [] if p in properties]
        out[name] = required + [p for p in properties if p not in required]
    return out


def render_catalog(names, params: dict[str, list[str]]) -> str:
    """The catalog as callable signatures: `ledger_get(id=...)`, not `ledger_get`.

    A name with no known arguments renders as `name(...)` rather than `name()`, because
    claiming it takes nothing is a worse error than admitting the schema is unknown --
    `name()` would invite a call that then fails on a missing required field.
    """
    parts = []
    for name in names:
        args = params.get(name)
        if args is None:
            parts.append(f"{name}(...)")
        else:
            parts.append(f"{name}({', '.join(f'{a}=...' for a in args)})")
    return ", ".join(parts)


def _callable_params(fn) -> list[str] | None:
    """Argument names of a locally-registered catalog function, or None if it hides
    them behind `**kwargs` -- which is what `_bridge` does, so a bridged tool must get
    its names from the schema instead of from here."""
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return None
    return [p.name for p in parameters
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.KEYWORD_ONLY)]


def partition_callable(names) -> tuple[list[str], list[str]]:
    """Split MCP tool names into the ones a PTC program can call and the ones it
    cannot. A program calls tools by name, so a non-identifier name (`my-tools_lookup`
    from a hyphenated server) is unreachable rather than merely ugly. The unusable ones
    are surfaced in the log instead of silently dropped: a task whose only tool is
    unreachable would otherwise read as a model failure.
    """
    ok = [n for n in names if n.isidentifier()]
    return ok, [n for n in names if not n.isidentifier()]


def _bridge(name, servers, dispatch, loop, timeout):
    """One synchronous catalog function over one async MCP tool.

    Keyword-only: MCP tool schemas name their arguments and carry no positional order,
    so accepting positional args would invent one.
    """
    def tool(**arguments: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(
            call_mcp(servers, dispatch, name, arguments), loop
        )
        return future.result(timeout=timeout)

    tool.__name__ = name
    return tool


class PTCHarnessConfig(HarnessConfig):
    max_turns: int = Field(8, gt=0)
    """Programs submitted before the loop gives up."""
    program_timeout: float = Field(runtime_timeout, gt=0)
    """Wall-clock seconds one program may run. Exceeding it is a rejection the model
    reads, not a hang: an episode that never completes never scores zero either, which
    makes a hang the cheapest accidental reward hack once Step 6 rewards the model
    (`docs/ptc-runtime-review.md`)."""


class PTCHarness(Harness[PTCHarnessConfig]):
    APPENDS_SYSTEM_PROMPT = True
    EXECUTES_CODE = True      # it runs a program, restricted or not
    NEEDS_CONTAINER = False   # nothing is installed; the loop is in-process
    SUPPORTS_MCP = True
    SUPPORTS_TOOL_INTERCEPTION = False
    SUPPORTS_RESUME = False

    def __init__(
        self,
        config: PTCHarnessConfig,
        catalog: Catalog | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        # Per-instance: a class-level `Catalog()` default would be one dict shared
        # by every arm in a run, so two tasks with different catalogs would see
        # each other's tools.
        self.catalog = catalog or Catalog()
        # Test seam. `None` is httpx's own default, so production is unchanged;
        # `test_harness.py` passes an `httpx.MockTransport` and needs no server.
        self.transport = transport

    async def launch(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
        data: TaskData,
    ) -> ProgramResult:
        system, prompt = self.resolve_prompt(data)
        messages: list[dict[str, Any]] = [
            # Rewritten below, once the catalog is known: the names cannot be listed
            # before the task's MCP servers have been asked what they offer.
            {"role": "system", "content": ""},
            {"role": "user", "content": prompt if isinstance(prompt, str) else str(prompt)},
        ]
        log: list[str] = []

        # `ctx.sampling` is deliberately not forwarded: the interception server
        # applies temperature/top_p/max_tokens as overrides onto whatever body a
        # harness sends (interception/server.py:596), so setting them here would
        # be dead at best and a silent divergence between arms at worst.
        # The program's captured output, refilled per program.
        printed: list[str] = []

        def observe(*parts: Any, sep: str = " ", end: str = "\n") -> None:
            printed.append(sep.join(str(part) for part in parts))

        async with AsyncExitStack() as stack:
            tools = dict(self.catalog.tools)
            # Locally-registered catalog functions are real functions, so their own
            # signatures are the truth; MCP tools only have schemas.
            params = {name: _callable_params(fn) for name, fn in tools.items()}
            unusable: list[str] = []
            if mcp_urls:
                discovered, unusable, discovered_params = await _mcp_catalog(
                    mcp_urls, stack, self.config.tool_timeout
                )
                tools.update(discovered)
                params.update(discovered_params)
            if unusable:
                log.append(f"unreachable tool names (not identifiers): {unusable}")
            catalog = Catalog(tools={**tools, OBSERVE: observe})
            names = sorted(tools)
            messages[0]["content"] = SYSTEM.format(
                names=render_catalog(names, params) or "(none)"
            ) + (f"\n\n{system}" if system else "")

            await self._loop(ctx, endpoint, secret, messages, catalog, printed, log)

        return ProgramResult(exit_code=0, stdout="\n".join(log), stderr="")

    async def _loop(
        self,
        ctx: ModelContext,
        endpoint: str,
        secret: str,
        messages: list[dict[str, Any]],
        catalog: Catalog,
        printed: list[str],
        log: list[str],
    ) -> None:
        # The interception endpoint already ends in `/v1` in a real run, so appending
        # `/v1/chat/completions` produced `/v1/v1/chat/completions` and a 404 that no
        # mock could have caught -- MockTransport answers any path. Found by running
        # the arm through `compare.py`.
        base = endpoint.rstrip("/")
        chat_path = "/chat/completions" if base.endswith("/v1") else "/v1/chat/completions"
        async with httpx.AsyncClient(
            transport=self.transport,
            base_url=base,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=300.0,
        ) as http:
            for _ in range(self.config.max_turns):
                r = await http.post(chat_path, json={
                    "model": ctx.model, "messages": messages,
                    "tools": TOOLS, "tool_choice": "auto", "stream": False,
                })
                r.raise_for_status()
                choice = r.json()["choices"][0]
                message = choice["message"]
                messages.append(message)
                calls = message.get("tool_calls") or []
                if not calls:
                    log.append("no tool call; loop ends")
                    break
                for call in calls:
                    args = call.get("function", {}).get("arguments") or "{}"
                    try:
                        code = json.loads(args).get("code", "")
                    except json.JSONDecodeError:
                        code = ""
                    # A rejection is DATA, not an error: the model sees why and may retry.
                    # That is what makes the restriction part of the interface rather
                    # than a crash, and it is the signal a trained model learns from.
                    printed.clear()
                    try:
                        # Off the event loop: the program is synchronous and its tool
                        # calls bridge back to this loop, so running it here would
                        # deadlock the moment a program called a tool.
                        await asyncio.to_thread(run_program, code, catalog, self.config.program_timeout)
                        content = "\n".join(printed) or "ok (the program printed nothing)"
                    except ProgramRejected as e:
                        content = f"rejected: {e}"
                    except Exception as e:  # the program itself raised
                        content = f"error: {type(e).__name__}: {e}"
                    log.append(content)
                    messages.append({
                        "role": "tool", "tool_call_id": call.get("id", "0"),
                        "name": "run_program", "content": content,
                    })
