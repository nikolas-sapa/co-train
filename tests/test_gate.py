"""The non-solver gate. Ten assertions: four predicates x two directions,
plus a protocol check on the decorator and a meta-test on the liveness guard.

Berkeley RDI's rule is "if a zero-capability agent scores above baseline,
your evaluation has a bug" -- but the four agents have four DIFFERENT tests,
and a one-line summary flattens them:

  null    "Its score is your floor. If it's not zero, something is wrong."
  random  "If it significantly outperforms the null agent on some tasks,
          those tasks may have evaluation gaps."
  inject  "If scores change, your judge is compromisable."
  tamper  "If it scores above zero, your isolation is broken."

Baseline is COMPUTED, not configured: the source gives no formal definition
of baseline, and the null agent's score *is* the floor. So null runs first
and the other three are scored relative to it.

"Significantly" presumes a task pool with sampling noise. There is no pool
yet, so the threshold collapses to exactness: on a sound environment null
scores 0, therefore random must score exactly 0 too, over N_SEEDS seeds. The
looser reading is deferred to Step 4 deliberately, so that it is not
silently inherited here.
"""

import inspect

import pytest

from cotrain.contract import Act, Env, rollout
from cotrain.nonsolvers import (
    INJECTIONS,
    TAMPER_PROBES,
    Echo,
    Inject,
    Null,
    RandomAgent,
    Tamper,
)
from leaky_env import LeakyEnv, SoundStubEnv

N_SEEDS = 32


class _Landed:
    """Env decorator counting steps the harness ACCEPTED.

    Liveness lives here, in the gate, not in the fixture -- so it applies
    identically to LeakyEnv, to SoundStubEnv, and to Step 4's real environment.

    Without it every SILENT predicate passes with a DEAD agent. All four assert
    equality against zero on an environment that pays out only for the exact
    minted secret, so a no-op agent scores zero and reads as green (measured: a
    no-op RandomAgent passes test_random_silent_on_sound in isolation). The
    gate's only liveness would then sit in the FIRE direction, which runs
    against the fixture Step 4 replaces -- so the gate would lose all liveness
    at exactly the moment the real environment arrives.

    Counts ACCEPTED steps, not policy emissions. That distinction is what
    catches a Tamper emitting kind="ptc": the agent emits five probes, rollout
    refuses all five via `continue`, and landed == 0. A policy-side spy would
    see five emissions and pass.
    """

    # ponytail: counts accepted steps without inspecting what step() returns, so
    # an environment that accepted actions and then ignored them entirely would
    # still read as live. No mutation against these four files can reach that.
    # Upgrade path: inspect the returned observation or a reward delta if a real
    # environment ever makes "accepted but ignored" a reachable state.

    def __init__(self, env) -> None:
        # R1/R4 asserted on the WRAPPED environment at the boundary, so it
        # travels with the gate across the Step 4 swap. Asserting it on the
        # decorator instead is useless: _Landed.get_reward takes no arguments
        # by construction, so it passes regardless of what it wraps. Measured
        # -- that mistake let get_reward(self, claimed=0.0) through.
        assert not inspect.signature(env.get_reward).parameters, (
            f"{type(env).__name__}.get_reward takes agent-supplied arguments: "
            f"{list(inspect.signature(env.get_reward).parameters)}"
        )
        assert env.harness in ("bash", "ptc"), f"bad harness {env.harness!r}"
        self._env = env
        self.landed = 0
        # A plain attribute, not a property, so isinstance(_Landed(env), Env)
        # stays True: the decorator must satisfy the protocol it wraps.
        self.harness = env.harness

    def reset(self) -> str:
        return self._env.reset()

    def step(self, act):
        self.landed += 1
        return self._env.step(act)

    def get_reward(self) -> float:
        return self._env.get_reward()


def _score(env_cls, policy, *, expect) -> float:
    """Run `policy` against a fresh `env_cls` and return the reward.

    `expect` is the number of accepted actions required, and it is keyword-only
    and REQUIRED -- not defaulted. A call site that omits it raises TypeError
    rather than silently downgrading to the weakest check, which is what
    happened when `test_inject_silent_on_sound` was measured with its
    `expect=len(INJECTIONS)` removed: Inject landed 3, the weaker "at least one"
    branch accepted it, and the suite stayed green. Proving the guard trips is
    not the same as proving every call site uses it.

    `None` means "at least one": silence must be attributable to the environment
    being sound, never to the agent being dead. `expect=0` is Null's inverted
    form, and it makes Null's predicate load-bearing for the first time -- a Null
    that started acting is otherwise invisible to the gate.

    ponytail: making `expect` required stops a call site OMITTING it, not a call
    site passing `expect=None` explicitly and thereby asking for the weakest
    check. That mutation survives, and it is the inherent limit of mutation-
    testing a test suite rather than a defect in the gate: any test can be
    weakened by editing it to assert less, and no assertion inside the same file
    can prevent that without circularity. The defence is review of this file, not
    more machinery in it. Upgrade path, only if it ever earns its keep: split
    into `_score_live()` and `_score_exact(n)` so "the weakest check" has no
    spelling at a call site that wants an exact count.
    """
    env = _Landed(env_cls())
    reward = rollout(env, policy)
    if expect is None:
        assert env.landed > 0, "agent took no accepted action: silence is not attributable"
    else:
        assert env.landed == expect, f"expected {expect} accepted acts, got {env.landed}"
    return reward


def _sweep(env_cls) -> list[float]:
    """Score every seed, asserting the sweep actually explored.

    The spread assert is on LANDED STEPS, never on reward. On a sound
    environment every seed scoring identically zero is the CORRECT result, so a
    spread-on-reward assert goes red on working code -- measured, the baseline
    went red.

    This is also what kills `N_SEEDS = 32 -> 1`, which a universal quantifier
    alone does not: `all()` over a single seed passes happily. Only the spread
    assert notices that the sweep stopped sweeping.
    """
    # The sweep's breadth is a STATED property, not an accident of which seeds
    # happen to produce varied episodes. Spec 3.1 fixes it at 32. The spread
    # assert below alone pinned only N_SEEDS >= 4, and it did so through a seed
    # coincidence -- landed counts happened to be [3,18,3] on SoundStubEnv --
    # so the floor would move silently if Step 4's environment changed
    # RandomAgent's termination profile.
    assert N_SEEDS >= 32, f"spec 3.1 fixes the sweep at 32 seeds, got {N_SEEDS}"

    scores: list[float] = []
    landed: list[int] = []
    for seed in range(N_SEEDS):
        env = _Landed(env_cls())
        scores.append(rollout(env, RandomAgent(seed)))
        # ponytail: this per-seed check is largely redundant with the spread
        # assert below -- a wholly dead policy lands 0 for every seed, so the
        # spread collapses to one value and fails there anyway. It only adds
        # coverage for a policy dead on SOME seeds. Left in because it names the
        # failure precisely, but not probed by the meta-test: closing it would
        # need _sweep to take a policy factory, and RandomAgent lands at least
        # one action with probability 1-(1/4)**32.
        assert env.landed > 0, f"seed {seed} took no accepted action"
        landed.append(env.landed)
    assert len(set(landed)) >= 3, (
        "sweep did not explore: fewer than three distinct landed-step counts "
        f"across {N_SEEDS} seeds (got {sorted(set(landed))})"
    )
    return scores


def test_liveness_guard_actually_trips():
    """`expect=` is what makes every SILENT predicate non-vacuous, and it is a
    CONDITIONAL assertion -- dormant on correct code. So no mutation of this
    file can kill it: `_score` ignoring `expect` entirely survives the whole
    suite, measured. Its load-bearing-ness was instead proven by composition --
    an acting Null fails four tests with the guard intact and only one with the
    guard removed, because both Null predicates go blind.

    A guard that has never been observed tripping is not evidence (R24: "a green
    anti-cheat check that has never gone red is not evidence"). This is the one
    test in the file that exercises the gate's own machinery rather than the
    agents, and it is why the four SILENT predicates can be trusted.

    It covers all three of the gate's dormant guards -- the default liveness
    requirement, Null's inverted expect=0, and `_sweep`'s spread assert. Each
    one survives removal on correct code, so each is exercised here instead.
    The `match=` strings are load-bearing, not decorative: mutating a guard's
    message alone fails this test, which is what stops it passing on some
    unrelated AssertionError.
    """

    class _Dead:
        def act(self, obs):
            return None

    class _Acts:
        def act(self, obs):
            return Act("bash", "noop")

    # Default form: silence must be attributable to the environment being sound,
    # so a dead agent is rejected rather than quietly scored zero.
    # `match=` anchors on "silence is not attributable", which is unique to
    # _score. "no accepted action" alone also matches _sweep's per-seed message.
    with pytest.raises(AssertionError, match="silence is not attributable"):
        _score(SoundStubEnv, _Dead(), expect=None)

    # Null's inverted form: an agent that started acting must not pass as Null.
    with pytest.raises(AssertionError, match="expected 0 accepted acts"):
        _score(SoundStubEnv, _Acts(), expect=0)

    # The expect>0 branch, which the four matched-pair predicates actually use.
    # Covering only the default and expect=0 left it open: `assert env.landed ==
    # expect or expect > 0` neutered the guard for all four and stayed green.
    with pytest.raises(AssertionError, match="expected 99 accepted acts"):
        _score(SoundStubEnv, _Acts(), expect=99)

    # `_sweep`'s spread assert is the third dormant guard, and the only thing
    # that kills N_SEEDS 32 -> 1 (a universal quantifier over one seed passes
    # happily). Removing it also changes nothing on correct code, so it is
    # exercised directly too: against an env that terminates on its first step,
    # every seed lands exactly one action and the sweep has stopped exploring.
    class _AlwaysDone:
        harness = "bash"

        def reset(self):
            return "obs"

        def step(self, act):
            return "obs", True

        def get_reward(self):
            return 0.0

    with pytest.raises(AssertionError, match="sweep did not explore"):
        _sweep(_AlwaysDone)


def test_landed_decorator_satisfies_the_env_protocol():
    # If the decorator stopped conforming, every predicate below would be
    # measuring a different contract than Step 4's environment implements.
    assert isinstance(_Landed(SoundStubEnv()), Env)
    assert isinstance(_Landed(LeakyEnv()), Env)

    # R1/R4 asserted HERE, not only in tests/test_stub_envs.py. That file tests
    # the stub fixtures and does not survive the Step 4 environment swap; this
    # file is the one declared unchanged across it. isinstance resolves names
    # only, so get_reward(self, claimed=0.0) -- the exact violation the contract
    # exists to prevent -- passes conformance while failing this.
    # The invariant is enforced in _Landed.__init__, so a violating env cannot
    # even be wrapped. Exercised directly, because that guard is dormant too.
    class _TakesAgentArg:
        harness = "bash"

        def reset(self):
            return "obs"

        def step(self, act):
            return "obs", False

        def get_reward(self, claimed: float = 0.0):
            return claimed

    with pytest.raises(AssertionError, match="agent-supplied arguments"):
        _Landed(_TakesAgentArg())


# ---------------------------------------------------------------------------
# Direction 1: the agents must FIRE on the leaky fixture.
# A gate that has only ever been green has not been shown capable of failing.
# ---------------------------------------------------------------------------


def test_null_fires_on_leaky():
    # Null is the one agent whose predicate is the total, because it takes no
    # actions and the floor is all that is left. expect=0 pins that: a Null
    # that started acting now fails here.
    assert _score(LeakyEnv, Null(), expect=0) > 0.0


def test_random_fires_on_leaky():
    # Universal, not averaged -- and there is no aggregator left in the file to
    # mutate, so `mean -> min` and `mean -> max` stop existing rather than
    # getting caught. `all(s > null)` is `min(...) > null` spelled out.
    null = _score(LeakyEnv, Null(), expect=0)
    assert all(s > null for s in _sweep(LeakyEnv))


def test_inject_fires_on_leaky():
    # Matched pair, and directional. The earlier `!=` survived a sign reversal:
    # swapping INJECTIONS/NEUTRALS gave attack 0.40 against control 1.40, and
    # the gate reported "your judge is compromisable" off a backwards signal.
    attack = _score(LeakyEnv, Inject("attack"), expect=len(INJECTIONS))
    control = _score(LeakyEnv, Inject("control"), expect=len(INJECTIONS))
    # Magnitude, not just direction. `attack > control` alone survives the judge
    # verdict dropping 1.0 -> 0.01, and survives `>` -> `>=`, which makes the
    # predicate vacuous.
    assert attack - control == pytest.approx(1.0)


def test_tamper_fires_on_leaky():
    # The predicate that was vacuous. `total > 0` passed on the bare floor even
    # when all five probes were refused. Both arms emit the same number of bash
    # actions, so the floor and action-count terms cancel and the delta is the
    # agent-written term alone.
    attack = _score(LeakyEnv, Tamper("attack"), expect=len(TAMPER_PROBES))
    control = _score(LeakyEnv, Tamper("control"), expect=len(TAMPER_PROBES))
    # 5.0 = one fixture leak per R1a surface. Anything less means a probe has
    # stopped tripping its surface and that surface is decorative again.
    assert attack - control == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Direction 2: the agents must be SILENT on a sound environment.
# Step 4 swaps SoundStubEnv for the real environment; nothing here changes.
# Every assertion below is paired with a liveness check, so a dead agent fails
# rather than passing for the wrong reason.
# ---------------------------------------------------------------------------


def test_echo_fires_on_leaky():
    # LeakyEnv pays the floor to anything that acts, so Echo firing here is the
    # weak direction. The load-bearing one is test_echo_silent_on_sound.
    # expect=None, not an exact count: Echo's action count is a function of how
    # many distinct tokens the environment's observations contain, which is a
    # fixture artifact Step 4 will change. Liveness is the property that must
    # hold across the swap; the exact number is not.
    assert _score(LeakyEnv, Echo(), expect=None) > 0.0


def test_null_silent_on_sound():
    assert _score(SoundStubEnv, Null(), expect=0) == 0.0


def test_random_silent_on_sound():
    # Without _sweep's per-seed liveness assert, a no-op RandomAgent satisfies
    # this trivially: 0.0 == 0.0, measured as 1 passed in isolation.
    null = _score(SoundStubEnv, Null(), expect=0)
    assert all(s == null for s in _sweep(SoundStubEnv))


def test_inject_silent_on_sound():
    attack = _score(SoundStubEnv, Inject("attack"), expect=len(INJECTIONS))
    control = _score(SoundStubEnv, Inject("control"), expect=len(INJECTIONS))
    assert attack == control == 0.0


def test_echo_silent_on_sound():
    # The gate's only defence against observation-channel leakage. A sound
    # environment must never put anything in an observation that redeems for
    # reward. Deterministic: Echo submits every token it was shown.
    assert _score(SoundStubEnv, Echo(), expect=None) == 0.0


def test_tamper_silent_on_sound():
    attack = _score(SoundStubEnv, Tamper("attack"), expect=len(TAMPER_PROBES))
    control = _score(SoundStubEnv, Tamper("control"), expect=len(TAMPER_PROBES))
    assert attack == control == 0.0
