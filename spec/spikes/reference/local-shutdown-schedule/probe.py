"""SOURCEONLY UNRUN: own schedule model, NOT original binding or runtime."""
from time import monotonic_ns
HARNESS_START = monotonic_ns()
from dataclasses import dataclass
import json

S = 1_000_000_000
RESERVE, REAP = 30*S, S//2
NAMES = ("cooperate", "worker", "trigger", "command",
         "reap", "gate", "controller", "release")
EXPECTED = (1889500000000, 1891500000000, 1892500000000,
            1894500000000, 1895000000000, 1897000000000,
            1899000000000, 1900000000000)
EARLY = (501000000000, 503000000000, 504000000000,
         506000000000, 506500000000, 508500000000,
         510500000000, 511500000000)


def require(ok, code):
    if not ok:
        raise ValueError(code)


def refuses(fn, code):
    try:
        fn()
    except ValueError as exc:
        require(str(exc) == code, "wrong_refusal")
    else:
        raise ValueError("missing_refusal:" + code)


@dataclass(frozen=True)
class Schedule:
    start: int
    end: int
    latest: int
    costs: tuple
    cuts: tuple


def schedule(rpc=S, teardown=2*S, arm=S, duration=1800*S,
             capacity_guard=True):
    for value, cap in ((rpc, 30*S), (teardown, 30*S),
                       (arm, 5*S), (duration, 1800*S)):
        require(type(value) is int and 0 < value <= cap, "range")
    require(rpc <= teardown, "rpc_envelope")
    require(duration > RESERVE + arm + REAP, "window")
    costs = (S, 2*S, S, teardown, REAP, 2*S, 2*S, S)
    need = sum(costs)
    if capacity_guard:
        require(need <= RESERVE, "capacity")
    start, end = 100*S, 100*S + duration
    latest = end - need
    cuts, cursor = [], latest
    for cost in costs:
        cursor += cost
        cuts.append(cursor)
    return Schedule(start, end, latest, costs, tuple(cuts))


def admit(effects, **values):
    result = schedule(**values)
    effects["claim"] += 1
    effects["spawn"] += 1
    return result


class OwnerModel:
    def __init__(self, s, roles=("worker", "controller", "gate")):
        self.s, self.roles = s, frozenset(roles)
        self.cuts = None
        self.stops = self.creates = 0
        self.ack = False
        self.unknown = False
        self.observed, self.waits = set(), []

    def stop(self, now, cancellation_guard=True):
        self.unknown = True
        if self.cuts is not None and cancellation_guard:
            return
        self.stops += 1
        origin = now if now < self.s.latest else self.s.latest
        shift = self.s.latest - origin
        self.cuts = tuple(cut - shift for cut in self.s.cuts)

    def failure(self, role, now):
        require(role in self.roles, "role")
        self.ack = False
        self.stop(now)

    def create(self, ack_guard=True):
        require(self.stops == 0 and self.creates == 0, "one_create")
        if ack_guard:
            require(self.ack, "not_armed")
        self.creates += 1

    def wait(self, stage, now, expiry_guard=True, renew=False):
        require(self.cuts is not None, "not_stopping")
        index = NAMES.index(stage)
        cutoff = self.cuts[index]
        if renew:
            cutoff = now + self.s.costs[index]
        left = cutoff - now
        if expiry_guard:
            require(left > 0, "expired")
        record = (stage, cutoff, left if left > 0 else 1)
        self.waits.append(record)
        return record

    def release(self, join_guard=True):
        if join_guard:
            require(self.observed == self.roles, "unjoined")
        return True


def exact_cutoffs():
    s = schedule()
    require((s.end, s.latest) == (1900000000000, 1888500000000), "ends")
    require(s.cuts == EXPECTED and sum(s.costs) == 11500000000, "cuts")


def preclaim_refusal():
    for values, code in (
        (dict(rpc=30*S, teardown=30*S), "capacity"),
        (dict(rpc=30*S, teardown=S), "rpc_envelope"),
        (dict(duration=1800*S+1), "range"),
        (dict(rpc=True), "range"),
        (dict(arm=5*S+1), "range"),
        (dict(duration=30*S), "window"),
    ):
        effects = dict(claim=0, spawn=0)
        refuses(lambda: admit(effects, **values), code)
        require(effects == dict(claim=0, spawn=0), "preclaim_effect")


def boundary_fit():
    require(schedule(teardown=20500000000).latest == 1870000000000, "fit")
    refuses(lambda: schedule(teardown=20500000001), "capacity")


def expired_and_late():
    for stage, cutoff in zip(NAMES, EXPECTED):
        for now in (cutoff, cutoff+1):
            o = OwnerModel(schedule()); o.stop(1888500000000)
            refuses(lambda: o.wait(stage, now), "expired")
            require(o.waits == [], "expired_wait")
    o = OwnerModel(schedule()); o.stop(1888500000000)
    require(o.wait("worker", 1890000000000) ==
            ("worker", 1891500000000, 1500000000), "remaining")


def cancellation_and_early():
    o = OwnerModel(schedule())
    for now in (500*S, 501*S, 502*S):
        o.stop(now)
    require(o.stops == 1 and o.cuts == EARLY, "cancel_renewal")


def failures_and_partial_state():
    for role in ("worker", "controller", "gate"):
        o = OwnerModel(schedule()); o.ack = True
        o.failure(role, 500*S)
        refuses(o.create, "one_create")
        refuses(o.release, "unjoined")
        o.observed.update(o.roles)
        require(o.release() and o.unknown, "failure_outcome")
    for event in ("partial_arm", "lost_arm_ack"):
        o = OwnerModel(schedule())
        refuses(o.create, "not_armed")
        o.stop(500*S)
        require(o.creates == 0 and o.unknown, event)
    o = OwnerModel(schedule()); o.ack = True; o.create(); o.stop(500*S)
    refuses(o.create, "one_create")
    require(o.creates == 1 and o.unknown, "lost_create_ack")
    o = OwnerModel(schedule(), ("worker",)); o.stop(500*S)
    refuses(o.release, "unjoined")
    o.observed.add("worker")
    require(o.release(), "partial_release")


def guard_pairs():
    def reserve_oracle(s):
        require(s.latest >= 1870000000000, "reserve_oracle")
    refuses(lambda: schedule(rpc=30*S, teardown=30*S), "capacity")
    bad = schedule(rpc=30*S, teardown=30*S, capacity_guard=False)
    refuses(lambda: reserve_oracle(bad), "reserve_oracle")
    refuses(lambda: schedule(rpc=30*S, teardown=30*S), "capacity")
    for loss in (False, True, False):
        o = OwnerModel(schedule()); o.stop(1888500000000)
        if loss:
            row = o.wait("worker", 1891500000000, expiry_guard=False)
            refuses(lambda: require(row[2] <= 0, "expiry_oracle"), "expiry_oracle")
        else:
            refuses(lambda: o.wait("worker", 1891500000000), "expired")
        o = OwnerModel(schedule()); o.stop(1888500000000)
        row = o.wait("worker", 1890000000000, renew=loss)
        oracle = lambda: require(row[1:] == (1891500000000, 1500000000),
                                 "lease_oracle")
        if loss:
            refuses(oracle, "lease_oracle")
        else:
            oracle()
        o = OwnerModel(schedule())
        if loss:
            o.create(ack_guard=False)
            refuses(lambda: require(o.creates == 0, "ack_oracle"), "ack_oracle")
        else:
            refuses(o.create, "not_armed")
        o = OwnerModel(schedule())
        for now in (500*S, 501*S, 502*S):
            o.stop(now, cancellation_guard=not loss)
        oracle = lambda: require(o.stops == 1 and o.cuts == EARLY, "cancel_oracle")
        if loss:
            refuses(oracle, "cancel_oracle")
        else:
            oracle()
        o = OwnerModel(schedule()); o.stop(500*S)
        if loss:
            released = o.release(join_guard=False)
            refuses(lambda: require(not released, "release_oracle"), "release_oracle")
        else:
            refuses(o.release, "unjoined")


def main():
    cases = []
    for case in (exact_cutoffs, preclaim_refusal, boundary_fit,
                 expired_and_late, cancellation_and_early,
                 failures_and_partial_state, guard_pairs):
        started = monotonic_ns()
        case()
        elapsed = monotonic_ns() - started
        require(elapsed <= 2500000000, "case_time")
        cases.append({"name": case.__name__, "elapsed_ns": elapsed})
    result = {"status": "PROTOTYPE_PASS", "scope": "OWN_ARITHMETIC_MODEL_ONLY",
              "cases": cases, "original_binding_and_runtime_verified": False}
    total = monotonic_ns() - HARNESS_START
    require(total < 8000000000, "shared_time")
    result["total_ns"] = total
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
