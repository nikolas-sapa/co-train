"""Pure bookings for parent validation. Data only, never ownership or authority."""
from dataclasses import dataclass

NS = 1_000_000_000
MAX_NS = 2**63 - 1


def _integer(value: int, maximum: int = MAX_NS, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("bounded integer required")
    return value


@dataclass(frozen=True)
class ValidationBooking:
    end_ns: int
    latest_origin_ns: int
    worker_export_ns: int
    worker_reap_ns: int
    read_ns: int
    close_ns: int
    seal_ns: int
    phase_end_ns: int
    work_ns: int
    verify_ns: int


def minimum_remaining_ns(teardown_ns: int, arm_ns: int, *,
                         ready_pending: bool) -> int:
    _integer(teardown_ns, 20_500_000_000, 1)
    _integer(arm_ns, 5 * NS, 1)
    if type(ready_pending) is not bool:
        raise ValueError("exact startup state required")
    return teardown_ns + 167_500_000_000 + arm_ns + (2 * NS if ready_pending else 0)


def require_feasible(remaining_ns: int, teardown_ns: int, arm_ns: int, *,
                     ready_pending: bool) -> None:
    _integer(remaining_ns, 1800 * NS)
    if remaining_ns < minimum_remaining_ns(teardown_ns, arm_ns,
                                           ready_pending=ready_pending):
        raise ValueError("validation booking infeasible")


def validation_booking(end_ns: int, teardown_ns: int) -> ValidationBooking:
    _integer(end_ns, minimum=1)
    _integer(teardown_ns, 20_500_000_000, 1)
    latest = end_ns - teardown_ns - 9_500_000_000
    exported = latest - 35 * NS
    phase_end = min(end_ns, exported + 30 * NS)
    work = phase_end - 150 * NS
    _integer(work)
    return ValidationBooking(
        end_ns=end_ns, latest_origin_ns=latest,
        worker_export_ns=exported, worker_reap_ns=latest - 33 * NS,
        read_ns=latest - 3 * NS, close_ns=latest - 2 * NS,
        seal_ns=latest - NS, phase_end_ns=phase_end,
        work_ns=work, verify_ns=phase_end - 90 * NS)
