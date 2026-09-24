import dataclasses

import pytest
from cotrain.contract import Act, permits, rollout


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
    def act(self, obs):
        return Act("ptc", "print(1)")


def test_rollout_stops_at_max_steps():
    # Review Focus 2: a non-terminating policy must not hang.
    policy = _AlwaysActs()
    rollout(_NeverDone(), policy, max_steps=5)
    assert policy.calls == 5


def test_forbidden_kind_is_dropped_not_stepped():
    # Review Focus 1: a forbidden kind is dropped and never reaches step().
    env = _CountsSteps()
    rollout(env, _EmitsForbidden(), max_steps=5)
    assert env.steps == 0


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
