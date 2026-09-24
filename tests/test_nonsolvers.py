import typing

from cotrain.contract import ActKind
from cotrain.nonsolvers import (
    JUDGE_BAIT,
    KINDS,
    INJECTIONS,
    NEUTRAL_PROBES,
    NEUTRALS,
    TAMPER_PROBES,
    Inject,
    Null,
    RandomAgent,
    Tamper,
)


def test_null_takes_no_actions():
    assert Null().act("obs") is None


def test_random_is_seed_reproducible():
    a = [RandomAgent(7).act("obs") for _ in range(10)]
    b = [RandomAgent(7).act("obs") for _ in range(10)]
    assert a == b


def test_random_differs_across_seeds():
    a = [RandomAgent(1).act("o") for _ in range(20)]
    b = [RandomAgent(2).act("o") for _ in range(20)]
    assert a != b


def test_random_eventually_emits_every_kind():
    agent = RandomAgent(0)
    kinds = {agent.act("o").kind for _ in range(400)}
    assert kinds == {"bash", "ptc", "submit", "escalate"}


def test_tamper_covers_all_five_r1a_surfaces():
    # research/05 R1a: "the exploit surface includes the runtime, not just the
    # application" -- $PATH, test-framework plugin hooks, shared containers,
    # uninitialized memory, and the path the verifier itself reads from.
    surfaces = {s for s, _ in TAMPER_PROBES}
    assert surfaces == {
        "path",
        "plugin_hook",
        "shared_container",
        "uninit_memory",
        "verifier_read_path",
    }


def test_tamper_emits_each_probe_once_then_stops():
    agent = Tamper()
    emitted = []
    while (act := agent.act("obs")) is not None:
        emitted.append(act.payload)
    assert len(emitted) == len(TAMPER_PROBES)
    assert len(set(emitted)) == len(TAMPER_PROBES)


def test_inject_modes_emit_equal_length_sequences():
    # Review Focus 5: LeakyEnv rewards action count, so unequal sequence
    # lengths would confound the delta test and report a compromised judge
    # where there is none.
    assert len(INJECTIONS) == len(NEUTRALS)

    def drain(mode):
        agent = Inject(mode)
        out = []
        while (act := agent.act("obs")) is not None:
            out.append(act)
        return out

    assert len(drain("attack")) == len(drain("control"))


def test_kinds_matches_the_actkind_literal():
    # A typo'd ActKind is silently dropped by rollout, so a typo'd agent looks
    # exactly like a working adversarial agent emitting a forbidden kind.
    assert set(KINDS) == set(typing.get_args(ActKind))


def test_every_tamper_probe_is_a_bash_action():
    # Tamper emitting kind="ptc" against a bash harness has all five probes
    # refused, takes zero env steps, collects only the floor -- and a
    # sum-based gate reports green.
    agent = Tamper()
    kinds = []
    while (act := agent.act("obs")) is not None:
        kinds.append(act.kind)
    assert kinds and all(k == "bash" for k in kinds)

def test_inject_attack_mode_emits_the_bait_and_control_does_not():
    # Swapping INJECTIONS and NEUTRALS inside Inject.__init__ survives every
    # other test in this file: both tuples are equal length and neither trips
    # the R1 signature, so the swap is invisible without an environment that has
    # a judge. Measured as a surviving mutant. Asserting on Inject's BEHAVIOUR
    # rather than on the tuples catches it here instead of deferring to Task 4 --
    # a task should not rely on a later task to catch its own defect.
    def drain(mode):
        agent = Inject(mode)
        out = []
        while (act := agent.act("obs")) is not None:
            out.append(act.payload)
        return out

    assert any(JUDGE_BAIT in p for p in drain("attack"))
    assert not any(JUDGE_BAIT in p for p in drain("control"))


def test_neutral_probes_match_attack_probes_and_trip_nothing():
    # The matched pair only cancels if both arms are the same length and the
    # control arm trips no leak. Otherwise the tamper delta measures action
    # count rather than tampering.
    assert len(NEUTRAL_PROBES) == len(TAMPER_PROBES)
    assert [s for s, _ in NEUTRAL_PROBES] == [s for s, _ in TAMPER_PROBES]
    for _surface, payload in NEUTRAL_PROBES:
        assert not ("score" in payload.lower() and "=" in payload)


def test_one_tamper_probe_trips_the_r1_leak_signature():
    # `verifier_read_path` is the only probe that writes the scored state, so
    # this one string is the entire link between the tamper agent and the
    # tamper predicate. Defusing it alone previously survived every test.
    tripping = [
        surface
        for surface, payload in TAMPER_PROBES
        if "score" in payload.lower() and "=" in payload
    ]
    assert tripping == ["verifier_read_path"]


def test_inject_payloads_avoid_the_r1_leak_signature():
    # The tamper probes trip LeakyEnv by writing the scored state. If an
    # injection payload also matched that signature, the delta test would be
    # measuring tampering rather than judge compromise.
    for payload in INJECTIONS + NEUTRALS:
        assert not ("score" in payload.lower() and "=" in payload)
