import dataclasses
import inspect

import pytest
from cotrain.contract import Act, Env, permits, rollout


def test_bash_harness_forbids_ptc():
    assert permits("bash", "bash")
    assert permits("bash", "submit")
    assert permits("bash", "escalate")
    assert not permits("bash", "ptc")


def test_ptc_harness_forbids_bash():
    assert permits("ptc", "ptc")
    assert not permits("ptc", "bash")


def test_unknown_harness_raises():
    # Review Focus 4: fail loudly at the boundary, never silently permit.
    with pytest.raises(KeyError):
        permits("bash+tool", "bash")


class _AlwaysActs:
    """Never returns None; paired with an env that never sets done."""

    def __init__(self):
        self.calls = 0

    def act(self, obs):
        self.calls += 1
        return Act("bash", "echo hi")


class _NeverDone:
    harness = "bash"

    def reset(self):
        return "obs"

    def step(self, act):
        return "obs", False

    def get_reward(self):
        return 0.0


class _CountsSteps:
    harness = "bash"

    def __init__(self):
        self.steps = 0

    def reset(self):
        return "obs"

    def step(self, act):
        self.steps += 1
        return "obs", False

    def get_reward(self):
        return 0.0


class _EmitsForbidden:
    def __init__(self):
        self.calls = 0

    def act(self, obs):
        self.calls += 1
        return Act("ptc", "print(1)")


class _RewardsFixed:
    """Returns a distinctive reward so rollout's return value is pinned."""

    harness = "bash"

    def reset(self):
        return "obs"

    def step(self, act):
        return "obs", False

    def get_reward(self):
        return 0.75


class _DoneFirstStep:
    """Terminates immediately -- the single-shot PTC harness shape."""

    harness = "bash"

    def __init__(self):
        self.steps = 0

    def reset(self):
        return "obs"

    def step(self, act):
        self.steps += 1
        return "obs", True

    def get_reward(self):
        return 0.0


class _EchoesStepCount:
    """Observation changes every step, so obs threading is observable."""

    harness = "bash"

    def __init__(self):
        self.n = 0

    def reset(self):
        return "obs-0"

    def step(self, act):
        self.n += 1
        return f"obs-{self.n}", False

    def get_reward(self):
        return 0.0


class _RecordsObs:
    def __init__(self):
        self.seen = []

    def act(self, obs):
        self.seen.append(obs)
        return Act("bash", "noop")


def test_rollout_stops_at_max_steps():
    # Review Focus 2: a non-terminating policy must not hang.
    policy = _AlwaysActs()
    rollout(_NeverDone(), policy, max_steps=5)
    assert policy.calls == 5


def test_forbidden_kind_is_dropped_not_stepped():
    # Review Focus 1: a forbidden kind is dropped and never reaches step().
    env = _CountsSteps()
    policy = _EmitsForbidden()
    rollout(env, policy, max_steps=5)
    assert env.steps == 0
    # `steps == 0` alone also holds if a refusal ABORTS the rollout. Pinning the
    # call count distinguishes `continue` from `break`, which is the exact
    # iteration accounting the random agent and the gate depend on.
    assert policy.calls == 5


def test_rollout_returns_the_env_reward():
    # Without this, `return 0.0` from rollout survives the whole suite, and the
    # gate reads its reward out of rollout.
    assert rollout(_RewardsFixed(), _AlwaysActs(), max_steps=3) == 0.75


def test_done_terminates_the_rollout_after_one_step():
    # The single-shot harness branch. Deleting `if done: break` otherwise
    # survives, because no other double ever terminates.
    env = _DoneFirstStep()
    policy = _AlwaysActs()
    rollout(env, policy, max_steps=5)
    assert env.steps == 1
    assert policy.calls == 1


def test_observation_is_threaded_from_env_to_policy():
    # `obs, done = env.step(act)` -> `_, done = env.step(act)` otherwise
    # survives, because every other double returns a constant observation.
    policy = _RecordsObs()
    rollout(_EchoesStepCount(), policy, max_steps=3)
    assert policy.seen == ["obs-0", "obs-1", "obs-2"]


def test_env_protocol_is_runtime_checkable():
    # Removing @runtime_checkable from Env otherwise survives Task 1 entirely
    # and breaks Task 3's isinstance check with a TypeError.
    assert isinstance(_NeverDone(), Env)


def test_get_reward_accepts_no_agent_supplied_argument():
    # R1/R4 as an enforced invariant rather than a naming convention.
    # isinstance() resolves names only: an env whose get_reward(self, token)
    # took an agent-supplied token would still pass isinstance(env, Env).
    for env_cls in (_NeverDone, _CountsSteps, _RewardsFixed, _DoneFirstStep):
        params = inspect.signature(env_cls().get_reward).parameters
        assert not params, f"{env_cls.__name__}.get_reward takes {list(params)}"


def test_null_policy_returning_none_ends_rollout_immediately():
    env = _CountsSteps()

    class _Null:
        def act(self, obs):
            return None

    rollout(env, _Null(), max_steps=5)
    assert env.steps == 0


def test_act_is_frozen():
    a = Act("bash", "ls")
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.payload = "mutated"
