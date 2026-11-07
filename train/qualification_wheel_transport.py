"""Explicit local-public-artifact transport, never authorization or staging."""

from __future__ import annotations

from collections.abc import Callable
import http.client
import io
import math
import ssl
import time

from train.qualification_wheel_staging import WheelPin, _validate_pins


_HOST = "files.pythonhosted.org"
_ORIGIN = "https://" + _HOST
_HEADER_BYTES = 65536
_REFUSED = "wheel HTTPS response refused"


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


class _Budget:
    def __init__(self, deadline: float, clock: Callable[[], float]):
        _require(callable(clock), "wheel HTTPS clock required")
        self.clock = clock
        self.previous = clock()
        _require(_finite(self.previous) and _finite(deadline)
                 and 0 < deadline - self.previous <= 1800,
                 "wheel HTTPS deadline invalid")
        self.deadline = deadline

    def remaining(self, supplied: float | None = None) -> float:
        now = self.clock()
        _require(_finite(now) and now >= self.previous, "wheel HTTPS clock invalid")
        self.previous = now
        if supplied is not None:
            _require(_finite(supplied) and 0 < supplied <= 1800,
                     "wheel HTTPS remaining time invalid")
            self.deadline = min(self.deadline, now + supplied)
        if now >= self.deadline:
            raise TimeoutError("wheel HTTPS deadline exhausted")
        return self.deadline - now


class _Wire(io.RawIOBase):
    def __init__(self, raw, sock, budget: _Budget):
        super().__init__()
        self.raw = raw
        self.sock = sock
        self.budget = budget
        self.header_bytes = 0
        self.headers = True

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        _require(not self.closed, "wheel HTTPS response closed")
        limit = len(buffer)
        if self.headers:
            limit = min(limit, _HEADER_BYTES - self.header_bytes)
            _require(limit > 0, _REFUSED)
        else:
            _require(0 < limit <= 1048576, "wheel HTTPS read bound invalid")
        self.sock.settimeout(self.budget.remaining())
        count = self.raw.readinto(memoryview(buffer)[:limit])
        self.budget.remaining()
        _require(type(count) is int and 0 <= count <= limit, _REFUSED)
        if self.headers:
            self.header_bytes += count
        return count

    def close(self) -> None:
        if self.closed:
            return
        try:
            self.raw.close()
        finally:
            super().close()


class _ResponseSocket:
    def __init__(self, wire: _Wire):
        self.wire = wire

    def makefile(self, mode: str):
        _require(mode == "rb", _REFUSED)
        return self.wire


def _cleanup(response, wire, connection, primary: BaseException | None = None) -> None:
    first = primary
    for resource in (response, wire, connection):
        if resource is None or (resource is wire and wire.closed):
            continue
        try:
            resource.close()
        except BaseException as error:
            if first is None:
                first = error
            else:
                first.add_note("wheel HTTPS cleanup failed")
    if primary is None and first is not None:
        raise first


class _WheelResponse:
    def __init__(self, url: str, response, wire: _Wire, connection, budget: _Budget):
        self.url = url
        self.status = response.status
        self._response = response
        self._wire = wire
        self._connection = connection
        self._budget = budget
        self._closed = False

    def read(self, max_bytes: int, remaining_seconds: float) -> bytes:
        _require(not self._closed, "wheel HTTPS response closed")
        _require(type(max_bytes) is int and 0 < max_bytes <= 1048576,
                 "wheel HTTPS read bound invalid")
        self._budget.remaining(remaining_seconds)
        result = self._response.read(max_bytes)
        self._budget.remaining()
        _require(type(result) is bytes and len(result) <= max_bytes, _REFUSED)
        return result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _cleanup(self._response, self._wire, self._connection)


class PinnedWheelHTTPS:
    """Single-caller transport for an explicitly authorized stage_wheels dispatch.

    Set deadline using the same monotonic clock BEFORE entering stage_wheels.
    Parent must externally supervise that entire process against this deadline:
    DNS, OS connect/close and filesystem scheduling have no Python hard bound.
    Construction performs no TLS-context, DNS or socket acquisition.
    """

    def __init__(
        self, pins: tuple[WheelPin, ...], *, deadline: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        _require(type(pins) is tuple, "immutable pin tuple required")
        _validate_pins(pins)
        self._pins = {pin.url: pin for pin in pins}
        self._attempted: set[str] = set()
        self._budget = _Budget(deadline, clock)

    def open_once(self, url: str, remaining_seconds: float) -> _WheelResponse:
        _require(type(url) is str and len(url) <= 512 and url in self._pins,
                 "exact pinned wheel HTTPS URL required")
        _require(url not in self._attempted, "wheel HTTPS URL already attempted")
        self._budget.remaining(remaining_seconds)
        self._attempted.add(url)
        response = wire = raw = connection = None
        primary: BaseException | None = None
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            _require(context.verify_mode == ssl.CERT_REQUIRED
                     and context.check_hostname is True,
                     "wheel HTTPS verifying TLS required")
            connection = http.client.HTTPSConnection(
                _HOST, 443, timeout=self._budget.remaining(), context=context,
            )
            connection.auto_open = 0
            connection.timeout = self._budget.remaining()
            connection.connect()
            self._budget.remaining()
            sock = connection.sock
            sock.settimeout(self._budget.remaining())
            connection.putrequest(
                "GET", url[len(_ORIGIN):], skip_host=True, skip_accept_encoding=True,
            )
            connection.putheader("Host", _HOST)
            connection.putheader("Accept-Encoding", "identity")
            connection.putheader("Connection", "close")
            sock.settimeout(self._budget.remaining())
            connection.endheaders()
            self._budget.remaining()
            raw = sock.makefile("rb", buffering=0)
            wire = _Wire(raw, sock, self._budget)
            response = http.client.HTTPResponse(_ResponseSocket(wire), method="GET")
            try:
                response.begin()
            except (http.client.HTTPException, UnicodeError):
                raise ValueError(_REFUSED) from None
            self._budget.remaining()
            headers = response.headers
            _require(response.status == 200 and response.version in (10, 11)
                     and not headers.defects, _REFUSED)
            _require(headers.get_all("Content-Length", []) == [str(self._pins[url].size)]
                     and not headers.get_all("Transfer-Encoding")
                     and not headers.get_all("Content-Range")
                     and not headers.get_all("Trailer")
                     and headers.get_all("Content-Encoding", []) in ([], ["identity"]),
                     _REFUSED)
            _require(not response.chunked and response.length == self._pins[url].size,
                     _REFUSED)
            # Do not let Content-Length hide the stager's one-byte overflow probe.
            response.length = None
            response.will_close = True
            wire.headers = False
            return _WheelResponse(url, response, wire, connection, self._budget)
        except BaseException as error:
            primary = error
            raise
        finally:
            if primary is not None:
                _cleanup(response, wire if wire is not None else raw, connection, primary)
