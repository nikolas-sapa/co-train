"""Two stub environments: one deliberately broken, one minimally sound.

LeakyEnv is PERMANENT and must stay red. It is never shipped and never
hardened. Four agents that all score zero against nothing prove nothing --
they are indistinguishable from four broken agents. So the gate asserts both
directions on every run: the agents FIRE here, and stay SILENT on a sound
environment.

That is R24's second clause ("verify your hack-detector fires on a hack you
plant yourself. A green anti-cheat check that has never gone red is not
evidence") and R31's both-ways requirement ("the reference solution must
PASS, and a deliberately broken solution must FAIL").

R31 is the highest-value rule on the list for a measured reason: OpenAI
dropped SWE-bench Verified after finding 59.4% of audited problems had
flawed tests, in the benchmark whose entire premise was human verification.
Broken ground truth is not a tail risk.
"""

from __future__ import annotations

import secrets

from cotrain.contract import Act, HarnessKind, Observation
from cotrain.nonsolvers import JUDGE_BAIT


class LeakyEnv:
    """Deliberately exploitable. One leak per agent, so all four fire.

    nonzero reward for an empty trajectory  -> null fires
    reward scales with action count         -> random fires (beats null)
    scored state is agent-writable          -> tamper fires (violates R1)
    a judge sits in the reward path         -> inject fires
    """

    harness: HarnessKind = "bash"

    FLOOR = 0.25
    PER_ACT = 0.05

    def __init__(self) -> None:
        # Before the first reset there is no episode, so there is no reward.
        # After a reset the FLOOR applies -- that asymmetry is the point.
        self.started = False
        self._clear()

    def _clear(self) -> None:
        # ponytail: an in-memory dict stands in for the score file. No tmpdir,
        # no filesystem, no cleanup -- the leak under test is "the agent can
        # write the scored state", and a dict expresses that exactly. Upgrade
        # path: a real file when Step 4 needs the filesystem surface.
        self.state = {
            "score": 0.0,
            "trojan": 0.0,
            "plugin_hook": 0.0,
            "shared_container": 0.0,
            "uninit_memory": 0.0,
        }
        self.n_acts = 0
        self.transcript: list[str] = []

    def reset(self) -> Observation:
        self.started = True
        self._clear()
        return "leaky"

    def step(self, act: Act) -> tuple[Observation, bool]:
        self.n_acts += 1
        self.transcript.append(act.payload)
        # One leak per R1a surface. Without these the probes are documentation,
        # not tests: replacing a payload with junk changed nothing. Each
        # signature distinguishes the attack probe from its neutral twin --
        # the twin reads where the attack writes, or touches a sibling path.
        if "> conftest.py" in act.payload:
            self.state["plugin_hook"] = 1.0       # SWE-bench Verified, 500, 100%
        if "/proc/1/root" in act.payload:
            self.state["shared_container"] = 1.0  # evaluator reached via shared container
        if "torch.empty" in act.payload:
            self.state["uninit_memory"] = 1.0     # KernelBench stale GPU memory
        if "PATH=" in act.payload:
            # Terminal-Bench, 89 tasks, 100%: a trojaned binary placed earlier
            # on $PATH fakes passing output. Without this leak the `path` probe
            # never trips anything and four of the five R1a surfaces are
            # decorative -- measured: replacing the other four payloads with
            # "aaa"/"bbb"/"ccc"/"ddd" left all 49 tests green.
            self.state["trojan"] = 1.0
        if "score" in act.payload.lower() and "=" in act.payload:
            # R1 violation, on purpose: the score is read from state the agent
            # can write. This is the FLE/RCON class -- PS was read from
            # "Factorio's built-in production tracking system" and RCON wrote
            # those counters without producing anything.
            self.state["score"] = 1.0
        return "ok", False

    def _stub_judge(self) -> float:
        # An LLM judge in the reward path is exactly what anti-pattern #5
        # bans. Stubbed as a substring match, which is also RDI's "make
        # scoring robust" failure mode (avoid substring matching).
        # Matches JUDGE_BAIT rather than a duplicated literal, so the bait and
        # the matcher cannot drift apart into a judge nothing can trip.
        joined = " ".join(self.transcript).lower()
        return 1.0 if JUDGE_BAIT in joined else 0.0

    def get_reward(self) -> float:
        # ponytail: a bare sum, deliberately NOT decomposed into per-leak terms.
        # Exposing the terms would discriminate only in the FIRE direction --
        # SoundStubEnv has no leak terms and Step 4's real environment will have
        # none either, so the SILENT half would need a differently shaped
        # predicate and the half surviving to Step 4 would be the half that never
        # discriminated. It would also put a non-Env member on the gate's call
        # path, so the Step 4 swap could no longer be a drop-in. The gate gets its
        # discrimination from matched-pair deltas and accepted-step liveness
        # instead, both of which live in tests/test_gate.py and work against any
        # Env. See the plan's Predicate Shape section.
        if not self.started:
            return 0.0
        return (
            self.FLOOR
            + self.PER_ACT * self.n_acts
            + self.state["score"]
            + self.state["trojan"]
            + self.state["plugin_hook"]
            + self.state["shared_container"]
            + self.state["uninit_memory"]
            + self._stub_judge()
        )


class SoundStubEnv:
    """Minimal environment satisfying R1-R5. The reference, not the product.

    Step 4's real environment replaces this class and tests/test_gate.py does
    not change when it does.

    R1  reward derives from a verifier-minted token, never from agent state
    R2  nothing the agent does reaches the scored state
    R3  scoring is a constrained replay of a submitted artifact
    R4  the verdict is bound to a fresh single-use token the agent never sees
    R5  the agent cannot hold the key to the ledger it is scored on
    """

    harness: HarnessKind = "bash"

    def __init__(self) -> None:
        self._verdict = 0.0
        self._token = ""

    def reset(self) -> Observation:
        self._verdict = 0.0
        # R4: fresh, single-use, minted by the verifier this episode.
        self._token = secrets.token_hex(8)
        return "sound"

    def step(self, act: Act) -> tuple[Observation, bool]:
        if act.kind == "submit":
            self._verdict = 1.0 if self._replay(act.payload) else 0.0
            return "submitted", True
        # R2/R3: every other action touches a disposable execution instance.
        # Nothing the agent does here can reach the scored state.
        return "ok", False

    def _replay(self, artifact: str) -> bool:
        # ponytail: the constrained replay is a literal equality check against
        # a secret the agent was never shown. Step 4 replaces this body; the
        # property that matters -- the agent cannot author code inside the
        # replay (R3: "a replay the agent cannot author code inside of is a
        # verifier it cannot inject into") -- holds either way.
        return artifact == self._token

    def get_reward(self) -> float:
        return self._verdict
