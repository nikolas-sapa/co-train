"""The `ledger` tool server: a small deterministic record store, offline.

Three tools, deliberately low-level. The comparison is between action CHANNELS
(shell + typed tools vs a program over a typed catalog), so the catalog has to be
identical for both arms and must not do the task for either one. A `ledger_total(kind)`
tool would collapse every aggregation task into one call and measure nothing.

`docs/pre-registration.md` §5 requires action-space altitude held comparable across
arms or the asymmetry declared. Identical tools are necessary but were not sufficient:
these three used to return human-readable text -- a space-separated id list and a JSON
string -- which the bash arm reads with its own attention and a PTC program cannot read
at all, the sandbox having no `import json`, no `.split` and no `ord`. Same tools, one
arm able to use them. Every return is now JSON, so one decode rule in `ptc/harness.py`
hands a program real data and both arms receive the same bytes (defect 5,
`docs/deviations.md`).
"""

import json
from pathlib import Path

import verifiers.v1 as vf

RECORDS: dict[str, dict] = json.loads((Path(__file__).parent / "records.json").read_text())


class LedgerToolset(vf.Toolset[vf.ToolsetConfig]):
    TOOL_PREFIX = "ledger"

    @vf.tool
    def ids(self) -> str:
        """Return every record id in the ledger as a JSON array of strings."""
        return json.dumps(sorted(RECORDS))

    @vf.tool
    def get(self, id: str) -> str:
        """Return one record as a JSON object: id, kind, amount, owner, link (or null).
        Returns JSON null if there is no such record."""
        return json.dumps(RECORDS.get(id.strip().lower()))

    @vf.tool
    def links_to(self, id: str) -> str:
        """Return the ids of records whose `link` points at this record, as a JSON
        array of strings. Empty array if none do."""
        target = id.strip().lower()
        return json.dumps(sorted(r["id"] for r in RECORDS.values() if r["link"] == target))


if __name__ == "__main__":
    LedgerToolset.run()
