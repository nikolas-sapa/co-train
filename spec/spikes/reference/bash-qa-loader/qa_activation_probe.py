"""Construction-only reference spike. Never run a policy with this harness."""
from typing import Literal

from ptc.bash_qa import QaBashHarness, QaBashHarnessConfig
from verifiers.v1.harness import Harness

__all__ = ["ProbeHarness"]


class ProbeConfig(QaBashHarnessConfig):
    # SHORTCUT: throwaway flat ID, not the production activation plugin.
    id: Literal["qa_activation_probe"] = "qa_activation_probe"


class ProbeHarness(QaBashHarness, Harness[ProbeConfig]):
    # PROVES: SDK config discovery honors this explicit generic specialization.
    # MISSING: fail-closed unbound setup/launch and the paired runner.
    # This disabled construction-only prototype is NOT an activation solution.
    pass
