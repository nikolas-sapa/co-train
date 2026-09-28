"""The `ledger` tool server: a small deterministic record store, offline.

Three tools, deliberately low-level. The comparison is between action CHANNELS
(shell + typed tools vs a program over a typed catalog), so the catalog has to be
identical for both arms and must not do the task for either one. A `ledger_total(kind)`
tool would collapse every aggregation task into one call and measure nothing.

`docs/pre-registration.md` §5 requires action-space altitude held comparable across
arms or the asymmetry declared. Here it is held by construction: both arms receive the
same three MCP tools, and only the channel differs.
"""

import json
from pathlib import Path

import verifiers.v1 as vf

RECORDS: dict[str, dict] = json.loads((Path(__file__).parent / "records.json").read_text())


class LedgerToolset(vf.Toolset[vf.ToolsetConfig]):
    TOOL_PREFIX = "ledger"

    @vf.tool
    def ids(self) -> str:
        """List every record id in the ledger, space separated."""
        return " ".join(sorted(RECORDS))

    @vf.tool
    def get(self, id: str) -> str:
        """Return one record as JSON: id, kind, amount, owner, link (or null)."""
        record = RECORDS.get(id.strip().lower())
        return json.dumps(record) if record else "no such record"

    @vf.tool
    def links_to(self, id: str) -> str:
        """List the ids of records whose `link` points at this record."""
        target = id.strip().lower()
        return " ".join(sorted(r["id"] for r in RECORDS.values() if r["link"] == target)) or "none"


if __name__ == "__main__":
    LedgerToolset.run()
