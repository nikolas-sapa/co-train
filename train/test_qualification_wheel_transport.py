from __future__ import annotations

from dataclasses import replace
import hashlib
import http.client
import io
from pathlib import Path
import ssl
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from train import qualification_wheel_staging as staging
from train import qualification_wheel_transport as api


_ORIGINAL_HTTPS_CONNECTION = http.client.HTTPSConnection
_ORIGINAL_HTTP_RESPONSE = http.client.HTTPResponse
_ORIGINAL_HTTP_METHODS = {
    name: getattr(_ORIGINAL_HTTPS_CONNECTION, name)
    for name in (
        "__init__", "request", "_send_request", "putrequest", "putheader",
        "endheaders", "_send_output", "send", "close",
    )
}


class SyntheticFile(io.BytesIO):
    def __init__(self, wire, owner):
        super().__init__(wire)
        self.owner = owner
        self.header_end = wire.find(b"\r\n\r\n") + 4
        self.reads = []
        self.body_reads = []
        self.closes = 0
        self.close_error = None
        self.read_error = None
        self.slow_header = False
        self.slow_body = False

    def readinto(self, buffer):
        position = self.tell()
        self.reads.append((position, len(buffer)))
        body = position >= self.header_end
        if body:
            self.body_reads.append(len(buffer))
            if self.read_error is not None and len(self.body_reads) == 2:
                raise self.read_error
        count = super().readinto(buffer)
        if (body and self.slow_body) or (not body and self.slow_header):
            self.owner.now += 11
        return count

    def close(self):
        self.closes += 1
        super().close()
        if self.close_error is not None:
            raise self.close_error


class SyntheticSocket:
    def __init__(self, wire, owner):
        self.file = SyntheticFile(wire, owner)
        self.timeouts = []
        self.makefiles = []
        self.closes = 0
        self.close_error = None
        self.sent = []
        self.send_error = None

    def sendall(self, data):
        self.sent.append(bytes(data))
        if self.send_error is not None:
            raise self.send_error

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def makefile(self, mode, buffering=None):
        self.makefiles.append((mode, buffering))
        return self.file

    def close(self):
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


class SyntheticConnection:
    def __init__(self, sock):
        self.synthetic_socket = sock
        self.sock = None
        self.auto_open = 1
        self.timeout = None
        self.connects = 0
        self.requests = []
        self.headers = []
        self.ends = 0
        self.closes = 0
        self.connect_error = None
        self.request_error = None

    def connect(self):
        self.connects += 1
        if self.connect_error is not None:
            raise self.connect_error
        self.sock = self.synthetic_socket

    def putrequest(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        self.ends += 1
        if self.request_error is not None:
            raise self.request_error

    def close(self):
        self.closes += 1
        sock, self.sock = self.sock, None
        if sock is not None:
            sock.close()


class Fixture(unittest.TestCase):
    use_stdlib_connection = False

    def setUp(self):
        self.now = 0.0
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.root = self.parent / "staged"
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context_factory = self.enterContext(patch.object(
            api.ssl, "create_default_context", return_value=self.context,
        ))
        self.connections = []
        self.wires = []
        if not self.use_stdlib_connection:
            self.factory = self.enterContext(patch.object(
                api.http.client, "HTTPSConnection", side_effect=self.connection,
            ))
        self.enterContext(patch(
            "socket.create_connection", side_effect=AssertionError("no network"),
        ))
        self.bounds = staging.StagingBounds(8, 8, 3, 10)
        self.authorization = Mock(return_value=None)

    def pin(self, name="a", data=b"abc"):
        filename = f"{name}-1-py3-none-any.whl"
        return staging.WheelPin(
            name, "1", filename, len(data), hashlib.sha256(data).hexdigest(),
            f"https://files.pythonhosted.org/packages/aa/bb/{'c' * 60}/{filename}",
        )

    def wire(self, body=b"abc", *, status=200, headers=None):
        if headers is None:
            headers = b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        return b"HTTP/1.1 " + str(status).encode() + b" synthetic\r\n" + headers + b"\r\n" + body

    def connection(self, *args, **kwargs):
        wire = self.wires.pop(0) if self.wires else self.wire()
        result = SyntheticConnection(SyntheticSocket(wire, self))
        self.connections.append(result)
        return result

    def transport(self, pins=None, deadline=10):
        return api.PinnedWheelHTTPS(
            pins if pins is not None else (self.pin(),),
            deadline=deadline, clock=lambda: self.now,
        )

    def open(self, *, wire=None, pin=None):
        pin = pin if pin is not None else self.pin()
        if wire is not None:
            self.wires.append(wire)
        transport = self.transport((pin,))
        response = transport.open_once(pin.url, 10)
        self.addCleanup(response.close)
        return response

    def stage(self, pins=None, *, bounds=None, transport=None):
        pins = pins if pins is not None else (self.pin(),)
        return staging.stage_wheels(
            pins, self.root, bounds=bounds if bounds is not None else self.bounds,
            authorize=self.authorization,
            transport=transport if transport is not None else self.transport(pins),
            clock=lambda: self.now,
        )

    def assert_closed(self, connection, *, file=True, socket=True):
        self.assertEqual(connection.closes, 1)
        self.assertEqual(connection.synthetic_socket.closes, int(socket))
        self.assertEqual(connection.synthetic_socket.file.closes, int(file))


class StdlibRequestTests(Fixture):
    use_stdlib_connection = True

    def setUp(self):
        super().setUp()
        self.connection_targets = []
        self.send_error = None
        self.socket_close_error = None

        def connect(connection):
            self.connection_targets.append((connection.host, connection.port))
            wire = self.wires.pop(0) if self.wires else self.wire()
            sock = SyntheticSocket(wire, self)
            sock.send_error = self.send_error
            sock.close_error = self.socket_close_error
            connection.sock = sock
            connection.synthetic_socket = sock
            self.connections.append(connection)

        self.enterContext(patch.object(
            _ORIGINAL_HTTPS_CONNECTION, "connect", new=connect,
        ))

    def assert_stdlib(self, connection):
        self.assertIs(api.http.client.HTTPSConnection, _ORIGINAL_HTTPS_CONNECTION)
        self.assertIs(type(connection), _ORIGINAL_HTTPS_CONNECTION)
        self.assertIs(api.http.client.HTTPResponse, _ORIGINAL_HTTP_RESPONSE)
        for name, original in _ORIGINAL_HTTP_METHODS.items():
            self.assertIs(getattr(type(connection), name), original)
        self.assertEqual(connection.auto_open, 0)
        self.assertEqual(self.connection_targets, [("files.pythonhosted.org", 443)])
        self.assertEqual(len(self.connections), 1)

    def assert_serialized_get(self, sock):
        path = self.pin().url.removeprefix("https://files.pythonhosted.org")
        expected = (
            f"GET {path} HTTP/1.1\r\n"
            "Host: files.pythonhosted.org\r\n"
            "Accept-Encoding: identity\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        self.assertEqual(sock.sent, [expected])

    def test_stdlib_serialized_get(self):
        response = self.open()
        connection = self.connections[0]
        sock = connection.synthetic_socket
        self.assert_stdlib(connection)
        self.assert_serialized_get(sock)
        self.assertIs(type(response._response), _ORIGINAL_HTTP_RESPONSE)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.url, self.pin().url)
        self.assertEqual(response.read(3, 10), b"abc")
        self.assertEqual(response.read(1, 10), b"")
        self.assertEqual(sock.makefiles, [("rb", 0)])
        response.close()
        self.assertEqual(sock.closes, 1)
        self.assertEqual(sock.file.closes, 1)
        self.assertIsNone(connection.sock)

    def test_stdlib_closed_socket_no_reconnect(self):
        response = self.open()
        connection = self.connections[0]
        sock = connection.synthetic_socket
        response.close()
        self.assertIsNone(connection.sock)
        path = self.pin().url.removeprefix("https://files.pythonhosted.org")
        with self.assertRaises(http.client.NotConnected):
            connection.request("GET", path)
        self.assert_stdlib(connection)
        self.assert_serialized_get(sock)
        self.assertEqual(sock.closes, 1)
        self.assertEqual(sock.file.closes, 1)

    def test_stdlib_sendall_failure_primary_cleanup(self):
        for cleanup_fails in (False, True):
            with self.subTest(cleanup_fails=cleanup_fails):
                self.connections.clear()
                self.connection_targets.clear()
                primary = OSError("synthetic sendall")
                self.send_error = primary
                self.socket_close_error = (
                    OSError("private-cleanup-marker") if cleanup_fails else None
                )
                transport = self.transport()
                with self.assertRaises(OSError) as caught:
                    transport.open_once(self.pin().url, 10)
                self.assertIs(caught.exception, primary)
                connection = self.connections[0]
                sock = connection.synthetic_socket
                self.assertIsNone(connection.sock)
                self.assertEqual(sock.closes, 1)
                self.assertEqual(sock.makefiles, [])
                self.assertEqual(sock.file.body_reads, [])
                self.assertEqual(sock.file.closes, 0)
                self.assertEqual(
                    getattr(primary, "__notes__", []),
                    ["wheel HTTPS cleanup failed"] if cleanup_fails else [],
                )
                with self.assertRaises(ValueError):
                    transport.open_once(self.pin().url, 10)
                path = self.pin().url.removeprefix("https://files.pythonhosted.org")
                with self.assertRaises(http.client.NotConnected):
                    connection.request("GET", path)
                self.assert_stdlib(connection)
                self.assert_serialized_get(sock)
                self.assertEqual(sock.closes, 1)


class WireTests(Fixture):
    def test_original_parser_raw_wire(self):
        response = self.open()
        self.assertIs(type(response._response), http.client.HTTPResponse)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.url, self.pin().url)
        self.assertEqual(response.read(3, 10), b"abc")
        self.assertEqual(response.read(1, 10), b"")
        response.close()
        self.assertEqual(self.connections[0].synthetic_socket.makefiles, [("rb", 0)])
        self.assert_closed(self.connections[0])

    def test_fixed_request(self):
        self.open()
        connection = self.connections[0]
        path = self.pin().url.removeprefix("https://files.pythonhosted.org")
        self.assertEqual(connection.requests, [
            ("GET", path, dict(skip_host=True, skip_accept_encoding=True)),
        ])
        self.assertEqual(connection.headers, [
            ("Host", "files.pythonhosted.org"),
            ("Accept-Encoding", "identity"),
            ("Connection", "close"),
        ])
        self.assertEqual(connection.auto_open, 0)
        self.assertEqual(connection.connects, 1)
        self.assertEqual(connection.ends, 1)
        self.assertTrue(all(0 < timeout <= 10
                            for timeout in connection.synthetic_socket.timeouts))

    def test_non200_no_follow(self):
        for status in (301, 302, 307, 404, 206, 500):
            self.wires.append(self.wire(status=status))
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.transport().open_once(self.pin().url, 10)
            connection = self.connections[-1]
            self.assertEqual(connection.ends, 1)
            self.assertEqual(len(connection.requests), 1)
            self.assertEqual(connection.synthetic_socket.file.body_reads, [])
            self.assert_closed(connection)
        self.assertEqual(self.factory.call_count, 6)

    def test_header_semantics(self):
        cases = (
            b"", b"Content-Length: 2\r\n",
            b"Content-Length: -3\r\n", b"Content-Length: 03\r\n",
            b"Content-Length: 3\r\nContent-Length: 3\r\n",
            b"Content-Length: 3, 3\r\n",
            b"Content-Length: 3\r\nTransfer-Encoding: chunked\r\n",
            b"Content-Length: 3\r\nContent-Encoding: gzip\r\n",
            b"Content-Length: 3\r\nContent-Range: bytes 0-2/3\r\n",
            b"Content-Length: 3\r\nTrailer: Digest\r\n",
        )
        for headers in cases:
            self.wires.append(self.wire(headers=headers))
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                self.transport().open_once(self.pin().url, 10)
            self.assertEqual(self.connections[-1].synthetic_socket.file.body_reads, [])
            self.assert_closed(self.connections[-1])

    def test_aggregate_raw_headers(self):
        prefix = b"HTTP/1.1 200 synthetic\r\nContent-Length: 3\r\n"
        suffix = b"\r\n"
        lines = b"".join(b"X-Pad: " + b"x" * 990 + b"\r\n" for _ in range(64))
        remaining = 65536 - len(prefix) - len(lines) - len(suffix)
        final = b"X-End: " + b"x" * (remaining - 9) + b"\r\n"
        head = prefix + lines + final + suffix
        self.assertEqual(len(head), 65536)
        response = self.open(wire=head + b"abc")
        response.close()
        self.assert_closed(self.connections[-1])
        self.wires.append(prefix + lines + final[:-2] + b"x\r\n" + suffix + b"abc")
        with self.assertRaises(ValueError):
            self.transport().open_once(self.pin().url, 10)
        self.assertEqual(self.connections[-1].synthetic_socket.file.body_reads, [])
        self.assert_closed(self.connections[-1])

    def test_slow_header_deadline(self):
        original = self.connection
        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            result.synthetic_socket.file.slow_header = True
            return result
        self.factory.side_effect = slow
        with self.assertRaises(TimeoutError):
            self.transport().open_once(self.pin().url, 10)
        connection = self.connections[0]
        self.assertEqual(len(connection.synthetic_socket.file.reads), 1)
        self.assertEqual(connection.synthetic_socket.file.body_reads, [])
        self.assert_closed(connection)

    def test_slow_body_deadline(self):
        response = self.open()
        self.connections[0].synthetic_socket.file.slow_body = True
        with self.assertRaises(TimeoutError):
            response.read(1, 10)
        response.close()
        self.assert_closed(self.connections[0])

    def test_body_read_limits(self):
        pin = self.pin(data=b"abcdef")
        response = self.open(pin=pin, wire=self.wire(b"abcdef"))
        self.assertEqual(response.read(1, 2), b"a")
        self.now = 0.5
        self.assertEqual(response.read(2, 10), b"bc")
        self.assertEqual(response.read(3, 10), b"def")
        self.assertEqual(response.read(1, 10), b"")
        self.assertEqual(self.connections[0].synthetic_socket.file.body_reads, [1, 2, 3, 1])
        self.assertEqual(self.connections[0].synthetic_socket.timeouts[-1], 1.5)

    def test_invalid_read_limits(self):
        response = self.open()
        for limit in (0, -1, 1048577, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                response.read(limit, 10)
        self.assertEqual(self.connections[0].synthetic_socket.file.body_reads, [])

    def test_parser_diagnostics(self):
        for wire in (
            b"private-server-marker\r\n\r\n",
            b"HTTP/1.1 xyz private-server-marker\r\n\r\n",
            b"HTTP/1.1 200 synthetic\r\nbroken-private-server-marker\r\n\r\n",
        ):
            self.wires.append(wire)
            with self.assertRaises(ValueError) as caught:
                self.transport().open_once(self.pin().url, 10)
            self.assertEqual(str(caught.exception), "wheel HTTPS response refused")
            self.assertNotIn("private-server-marker", str(caught.exception))
            self.assert_closed(self.connections[-1])


class AdmissionTests(Fixture):
    def test_constructor_inert(self):
        self.transport()
        self.factory.assert_not_called()
        self.context_factory.assert_not_called()

    def test_authorization_before_dispatch(self):
        def deny(*args):
            raise PermissionError("synthetic denial")
        for authorize in (None, True, deny, lambda *args: True):
            transport = self.transport()
            with self.subTest(authorize=authorize):
                with patch.object(transport, "open_once", wraps=transport.open_once) as opened:
                    with self.assertRaises((ValueError, PermissionError)):
                        staging.stage_wheels(
                            (self.pin(),), self.root, bounds=self.bounds,
                            authorize=authorize, transport=transport, clock=lambda: self.now,
                        )
                    opened.assert_not_called()
                self.assertFalse(self.root.exists())
        self.factory.assert_not_called()

    def test_invalid_urls_zero_get(self):
        pin = self.pin()
        invalid = (
            pin.url.replace("https:", "http:"),
            pin.url.replace("files.pythonhosted.org", "evil.example"),
            pin.url.replace("files.pythonhosted.org", "files.pythonhosted.org.evil"),
            pin.url.replace("files.pythonhosted.org", "user@files.pythonhosted.org"),
            pin.url.replace("files.pythonhosted.org", "files.pythonhosted.org:443"),
            pin.url.replace("files.pythonhosted.org", "files.pythonhosted.org:444"),
            pin.url + "#fragment", pin.url + "?query=1",
            pin.url.replace("/packages/", "/packages/../"),
            pin.url.replace(pin.filename, "%2e%2e.whl"),
            pin.url.replace("files.pythonhosted.org", "FILES.PYTHONHOSTED.ORG"),
            pin.url + "\r\nHost: private-marker",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.transport().open_once(url, 10)
        self.factory.assert_not_called()

    def test_unpinned_url_zero_get(self):
        with self.assertRaises(ValueError):
            self.transport().open_once(self.pin("b").url, 10)
        self.factory.assert_not_called()

    def test_duplicate_url_no_retry(self):
        transport = self.transport()
        response = transport.open_once(self.pin().url, 10)
        response.close()
        with self.assertRaises(ValueError):
            transport.open_once(self.pin().url, 10)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.connections[0].ends, 1)
        self.assert_closed(self.connections[0])

    def test_failed_open_no_retry(self):
        original = self.connection
        def fail(*args, **kwargs):
            result = original(*args, **kwargs)
            result.request_error = OSError("synthetic request")
            return result
        self.factory.side_effect = fail
        transport = self.transport()
        with self.assertRaises(OSError):
            transport.open_once(self.pin().url, 10)
        with self.assertRaises(ValueError):
            transport.open_once(self.pin().url, 10)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.connections[0].ends, 1)
        self.assert_closed(self.connections[0], file=False)

    def test_tls_verification(self):
        self.open()
        args, kwargs = self.factory.call_args
        self.assertEqual(args, ("files.pythonhosted.org", 443))
        self.assertIs(kwargs["context"], self.context)
        self.assertEqual(self.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertIs(self.context.check_hostname, True)
        self.context_factory.assert_called_once_with(ssl.Purpose.SERVER_AUTH)

    def test_insecure_context_zero_get(self):
        self.context.check_hostname = False
        for mode in (ssl.CERT_REQUIRED, ssl.CERT_NONE):
            self.context.verify_mode = mode
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.transport().open_once(self.pin().url, 10)
        self.factory.assert_not_called()

    def test_invalid_deadlines_zero_get(self):
        for deadline in (0, -1, 1801, float("inf"), float("nan"), True):
            with self.subTest(deadline=deadline), self.assertRaises(ValueError):
                self.transport(deadline=deadline)
        for remaining in (0, float("nan")):
            with self.subTest(remaining=remaining), self.assertRaises(ValueError):
                self.transport().open_once(self.pin().url, remaining)
        self.factory.assert_not_called()

    def test_manifest_api_unchanged(self):
        rows = []
        for index in range(220):
            pin = self.pin(f"p{index}")
            rows.append(dict(
                name=pin.name, version=pin.version, filename=pin.filename,
                size=4400067018 - 219 if index == 0 else 1,
                sha256=pin.sha256, url=pin.url,
            ))
        left = dict(selected=rows, selected_count=220,
                    total_declared_wheel_bytes=4400067018)
        right = dict(selected=[dict(row) for row in rows], expected_count=220)
        pins = staging.pins_from_manifests(left, right)
        self.assertEqual(len(pins), 220)
        self.assertEqual(sum(pin.size for pin in pins), 4400067018)
        self.transport(pins)
        right["selected"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            staging.pins_from_manifests(left, right)
        self.factory.assert_not_called()


class LifecycleTests(Fixture):
    def test_stage_exact_caps(self):
        pins = (self.pin(), self.pin("b", b"defg"))
        self.wires.extend((self.wire(), self.wire(b"defg")))
        bounds = replace(self.bounds, max_chunks=5)
        paths = self.stage(pins, bounds=bounds)
        self.assertEqual(tuple(path.read_bytes() for path in paths), (b"abc", b"defg"))
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(self.factory.call_count, 2)
        self.authorization.assert_called_once_with(pins, self.root, bounds)
        reads = []
        for path, connection in zip(paths, self.connections):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assert_closed(connection)
            reads.extend(connection.synthetic_socket.file.body_reads)
        self.assertEqual(reads, [3, 1, 3, 2, 1])

    def test_overflow_probe_retains_partial(self):
        self.wires.append(self.wire(b"abcd", headers=b"Content-Length: 3\r\n"))
        with self.assertRaisesRegex(ValueError, "received byte overflow"):
            self.stage(bounds=replace(self.bounds, max_bytes=4))
        self.assertEqual((self.root / self.pin().filename).read_bytes(), b"abc")
        self.assertEqual(self.connections[0].synthetic_socket.file.body_reads, [3, 1])
        self.assertEqual(self.factory.call_count, 1)
        self.assert_closed(self.connections[0])

    def test_length_hash_retains_actual_partial(self):
        for index, body in enumerate((b"ab", b"xyz")):
            self.root = self.parent / f"mismatch-{index}"
            self.wires.append(self.wire(body, headers=b"Content-Length: 3\r\n"))
            with self.assertRaisesRegex(ValueError, "wheel size/hash mismatch"):
                self.stage()
            self.assertEqual((self.root / self.pin().filename).read_bytes(), body)
            self.assert_closed(self.connections[-1])
        self.assertEqual(self.factory.call_count, 2)

    def test_chunk_budget(self):
        with self.assertRaisesRegex(ValueError, "total chunk/read budget exhausted"):
            self.stage(bounds=replace(self.bounds, max_chunks=1))
        self.assertEqual((self.root / self.pin().filename).read_bytes(), b"abc")
        self.assertEqual(self.connections[0].synthetic_socket.file.body_reads, [3])
        self.assert_closed(self.connections[0])

    def test_cumulative_admission(self):
        for bounds in (
            replace(self.bounds, max_bytes=3),
            replace(self.bounds, max_bytes=4400067020),
            replace(self.bounds, max_chunks=1000001),
            replace(self.bounds, chunk_bytes=1048577),
            replace(self.bounds, deadline_seconds=1801),
        ):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                self.stage(bounds=bounds)
        self.factory.assert_not_called()
        self.authorization.assert_not_called()
        self.assertFalse(self.root.exists())

    def check_primary(self, primary):
        original = self.connection
        cleanup = OSError("private-cleanup-marker")
        def failing(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.synthetic_socket.file.read_error = primary
            connection.synthetic_socket.file.close_error = cleanup
            connection.synthetic_socket.close_error = SystemExit("private-close-marker")
            return connection
        self.factory.side_effect = failing
        pin = self.pin(data=b"abcdef")
        self.wires.append(self.wire(b"abcdef"))
        with self.assertRaises(type(primary)) as caught:
            self.stage((pin,), bounds=replace(self.bounds, chunk_bytes=2))
        self.assertIs(caught.exception, primary)
        self.assertEqual((self.root / pin.filename).read_bytes(), b"ab")
        self.assertEqual(self.connections[-1].synthetic_socket.file.body_reads, [2, 2])
        self.assert_closed(self.connections[-1])
        for note in getattr(primary, "__notes__", []):
            self.assertIn(note, ("wheel HTTPS cleanup failed", "wheel response cleanup failed"))
            self.assertNotIn("private", note)
        self.assertEqual(self.connections[-1].ends, 1)

    def test_read_failure_primary_identity(self):
        self.check_primary(OSError("synthetic read"))
        self.assertEqual(self.factory.call_count, 1)

    def test_cancel_primary_identity(self):
        for index, primary in enumerate((KeyboardInterrupt("cancelled"), SystemExit(7))):
            self.root = self.parent / f"cancel-{index}"
            with self.subTest(primary=type(primary).__name__):
                self.check_primary(primary)
        self.assertEqual(self.factory.call_count, 2)

    def test_close_failure_primary_identity(self):
        response = self.open()
        connection = self.connections[0]
        cleanup = KeyboardInterrupt("synthetic close")
        connection.synthetic_socket.file.close_error = cleanup
        connection.synthetic_socket.close_error = OSError("private-cleanup-marker")
        with patch.object(response._response, "close", wraps=response._response.close) as close:
            with self.assertRaises(KeyboardInterrupt) as caught:
                response.close()
            self.assertIs(caught.exception, cleanup)
            response.close()
            self.assertEqual(close.call_count, 1)
        self.assert_closed(connection)
        self.assertEqual(getattr(cleanup, "__notes__", []), ["wheel HTTPS cleanup failed"])

    def test_acquisition_cleanup(self):
        original = self.connection
        for phase in ("connect", "request", "parser"):
            def failing(*args, **kwargs):
                connection = original(*args, **kwargs)
                if phase == "connect":
                    connection.connect_error = OSError("synthetic connect")
                elif phase == "request":
                    connection.request_error = KeyboardInterrupt("synthetic request")
                return connection
            self.factory.side_effect = failing
            if phase == "parser":
                self.wires.append(b"private-server-marker\r\n\r\n")
            with self.subTest(phase=phase), self.assertRaises(
                (OSError, KeyboardInterrupt, ValueError),
            ):
                self.transport().open_once(self.pin().url, 10)
            self.assert_closed(self.connections[-1], file=phase == "parser",
                               socket=phase != "connect")
        self.assertEqual(self.factory.call_count, 3)

    def test_removable_guard(self):
        # Parent negative control: change only this synthetic body to b"abd".
        response = self.open(wire=self.wire(b"abc"))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(3, 10), b"abc")
        response.close()
        self.assert_closed(self.connections[0])
