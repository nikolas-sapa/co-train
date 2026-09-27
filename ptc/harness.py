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

import json
from typing import Any

import httpx
from pydantic import Field

from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.harness import HarnessConfig
from verifiers.v1.harness import Harness
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import TaskData
from verifiers.v1.trace import Trace

from ptc.runtime import Catalog, ProgramRejected, run as run_program

__all__ = ["PTCHarness"]

SYSTEM = (
    "You act by writing a Python program and submitting it with the `run_program` tool. "
    "The program may call only these catalog functions: {names}. "
    "There is no shell and no other action channel. Imports and attribute access are "
    "rejected before the program runs. Control flow, arithmetic and comprehensions are "
    "available, so prefer one program that does the whole task over many small ones."
)

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


class PTCHarnessConfig(HarnessConfig):
    max_turns: int = Field(8, gt=0)
    """Programs submitted before the loop gives up."""


class PTCHarness(Harness[PTCHarnessConfig]):
    APPENDS_SYSTEM_PROMPT = True
    EXECUTES_CODE = True      # it runs a program, restricted or not
    NEEDS_CONTAINER = False   # nothing is installed; the loop is in-process
    SUPPORTS_MCP = False
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
        names = sorted(self.catalog.names())
        system, prompt = self.resolve_prompt(data)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM.format(names=", ".join(names) or "(none)")
             + (f"\n\n{system}" if system else "")},
            {"role": "user", "content": prompt if isinstance(prompt, str) else str(prompt)},
        ]
        log: list[str] = []

        # `ctx.sampling` is deliberately not forwarded: the interception server
        # applies temperature/top_p/max_tokens as overrides onto whatever body a
        # harness sends (interception/server.py:596), so setting them here would
        # be dead at best and a silent divergence between arms at worst.
        async with httpx.AsyncClient(
            transport=self.transport,
            base_url=endpoint.rstrip("/"),
            headers={"Authorization": f"Bearer {secret}"},
            timeout=300.0,
        ) as http:
            for _ in range(self.config.max_turns):
                r = await http.post("/v1/chat/completions", json={
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
                    try:
                        ns = run_program(code, self.catalog)
                        content = f"ok; names now: {sorted(ns)}"
                    except ProgramRejected as e:
                        content = f"rejected: {e}"
                    except Exception as e:  # the program itself raised
                        content = f"error: {type(e).__name__}: {e}"
                    log.append(content)
                    messages.append({
                        "role": "tool", "tool_call_id": call.get("id", "0"),
                        "name": "run_program", "content": content,
                    })

        return ProgramResult(exit_code=0, stdout="\n".join(log), stderr="")
