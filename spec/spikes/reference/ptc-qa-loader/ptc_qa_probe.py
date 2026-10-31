"""SHORTCUT: proof-only loader subclass, no production admission guards."""
from typing import Literal
from verifiers.v1.harness import Harness
from ptc.harness import PTCHarness, PTCHarnessConfig

__all__ = ["ProbeHarness"]


class ProbeConfig(PTCHarnessConfig):
    id: Literal["ptc_qa_probe"] = "ptc_qa_probe"


class ProbeHarness(PTCHarness, Harness[ProbeConfig]):
    pass
