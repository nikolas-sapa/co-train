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

import pytest

from cotrain.contract import Act, Env, rollout
from cotrain.nonsolvers import (
    INJECTIONS,
    TAMPER_PROBES,
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

    def __init__(self, env) -> None:
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


def _score(env_cls, policy, expect=None) -> float:
    """Run `policy` against a fresh `env_cls` and return the reward.

    `expect` is the number of accepted actions required. None means "at least
    one": silence must be attributable to the environment being sound, never to
    the agent being dead. expect=0 is Null's inverted form, and it makes Null's
    predicate load-bearing for the first time -- a Null that started acting is
    otherwise invisible to the gate.
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
    scores: list[float] = []
    landed: list[int] = []
    for seed in range(N_SEEDS):
        env = _Landed(env_cls())
        scores.append(rollout(env, RandomAgent(seed)))
        assert env.landed > 0, f"seed {seed} took no accepted action"
        landed.append(env.landed)
    assert len(set(landed)) > 1, (
        "sweep did not explore: every seed landed the same number of actions"
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
    with pytest.raises(AssertionError, match="no accepted action"):
        _score(SoundStubEnv, _Dead())

    # Null's inverted form: an agent that started acting must not pass as Null.
    with pytest.raises(AssertionError, match="expected 0 accepted acts"):
        _score(SoundStubEnv, _Acts(), expect=0)

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
    assert attack > control


def test_tamper_fires_on_leaky():
    # The predicate that was vacuous. `total > 0` passed on the bare floor even
    # when all five probes were refused. Both arms emit the same number of bash
    # actions, so the floor and action-count terms cancel and the delta is the
    # agent-written term alone.
    attack = _score(LeakyEnv, Tamper("attack"), expect=len(TAMPER_PROBES))
    control = _score(LeakyEnv, Tamper("control"), expect=len(TAMPER_PROBES))
    assert attack > control


# ---------------------------------------------------------------------------
# Direction 2: the agents must be SILENT on a sound environment.
# Step 4 swaps SoundStubEnv for the real environment; nothing here changes.
# Every assertion below is paired with a liveness check, so a dead agent fails
# rather than passing for the wrong reason.
# ---------------------------------------------------------------------------


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


def test_tamper_silent_on_sound():
    attack = _score(SoundStubEnv, Tamper("attack"), expect=len(TAMPER_PROBES))
    control = _score(SoundStubEnv, Tamper("control"), expect=len(TAMPER_PROBES))
    assert attack == control == 0.0
