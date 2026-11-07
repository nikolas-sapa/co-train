from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class Response:
    def __init__(self, url, chunks, *, status=200, before_read=None, close_error=None):
        self.url = url
        self.status = status
        self.chunks = iter(chunks)
        self.before_read = before_read
        self.reads = []
        self.closed = 0
        self.close_error = close_error

    def read(self, limit, timeout):
        self.reads.append((limit, timeout))
        if self.before_read:
            self.before_read()
        value = next(self.chunks, b"")
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class Transport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def open_once(self, url, timeout):
        self.calls.append((url, timeout))
        return next(self.responses)


class WheelStagingTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("train.qualification_wheel_staging")
        except ModuleNotFoundError as error:
            self.fail(f"wheel staging API missing: {error}")
        for name in ("WheelPin", "StagingBounds", "pins_from_manifests", "stage_wheels"):
            self.assertTrue(hasattr(self.api, name), f"missing intended API: {name}")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.root = self.parent / "staged"
        self.bounds = self.api.StagingBounds(
            max_bytes=8, max_chunks=8, chunk_bytes=3, deadline_seconds=10,
        )
        self.now = 0.0
        self.auth_calls = []

    def pin(self, name="a", data=b"abc"):
        filename = f"{name}-1-py3-none-any.whl"
        return self.api.WheelPin(
            name, "1", filename, len(data), hashlib.sha256(data).hexdigest(),
            f"https://files.pythonhosted.org/packages/aa/bb/{'c' * 60}/{filename}",
        )

    def authorize(self, pins, destination, bounds):
        self.auth_calls.append((pins, destination, bounds))

    def stage(self, pins, responses, **kwargs):
        transport = Transport(responses)
        options = dict(
            bounds=self.bounds, authorize=self.authorize, transport=transport,
            clock=lambda: self.now,
        )
        options.update(kwargs)
        result = self.api.stage_wheels(pins, self.root, **options)
        return result, transport

    def test_manifest_closure(self):
        rows = []
        total = 4400067018
        for index in range(220):
            pin = self.pin(f"p{index}")
            rows.append(dict(
                name=pin.name, version=pin.version, filename=pin.filename,
                size=total - 219 if index == 0 else 1,
                sha256=pin.sha256, url=pin.url,
            ))
        v4 = {"selected": rows, "selected_count": 220,
              "total_declared_wheel_bytes": total}
        v2 = {"selected": [dict(row) for row in rows], "expected_count": 220}
        pins = self.api.pins_from_manifests(v4, v2)
        self.assertEqual(len(pins), 220)
        self.assertEqual(sum(pin.size for pin in pins), total)
        v2["selected"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.api.pins_from_manifests(v4, v2)
        v2["selected"] = [dict(row) for row in rows]
        v2["selected"][1] = dict(v2["selected"][0])
        with self.assertRaises(ValueError):
            self.api.pins_from_manifests(v4, v2)

    def test_authorization_zero_network(self):
        def deny(*args):
            raise PermissionError("not admitted")

        for authorization in (None, True, deny, lambda *args: True):
            transport = Transport([])
            with self.subTest(authorization=authorization):
                with self.assertRaises((ValueError, PermissionError)):
                    self.api.stage_wheels(
                        (self.pin(),), self.root, bounds=self.bounds,
                        transport=transport, authorize=authorization,
                    )
                self.assertEqual(transport.calls, [])
                self.assertFalse(self.root.exists())

    def test_exact_bytes(self):
        pins = (self.pin(), self.pin("b", b"defg"))
        responses = [
            Response(pins[0].url, [b"ab", b"c", b""]),
            Response(pins[1].url, [b"def", b"g", b""]),
        ]
        paths, transport = self.stage(pins, responses)
        self.assertEqual(tuple(path.read_bytes() for path in paths), (b"abc", b"defg"))
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(self.auth_calls), 1)
        for path, response in zip(paths, responses):
            metadata = path.lstat()
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
            self.assertEqual(metadata.st_nlink, 1)
            self.assertEqual(metadata.st_uid, os.getuid())
            self.assertEqual(response.closed, 1)
            self.assertTrue(all(0 < limit <= 3 and timeout > 0
                                for limit, timeout in response.reads))

    def test_hash_mismatch(self):
        pin = replace(self.pin(), sha256="0" * 64)
        response = Response(pin.url, [b"abc", b""])
        with self.assertRaises(ValueError):
            self.stage((pin,), [response])
        self.assertEqual((self.root / pin.filename).read_bytes(), b"abc")
        self.assertEqual(response.closed, 1)

    def test_size_mismatch(self):
        pin = self.pin()
        with self.assertRaises(ValueError):
            self.stage((pin,), [Response(pin.url, [b"ab", b""])])
        self.assertEqual((self.root / pin.filename).read_bytes(), b"ab")

    def test_invalid_urls(self):
        pin = self.pin()
        invalid = (
            pin.url.replace("https:", "http:"),
            pin.url.replace("files.pythonhosted.org", "evil.example"),
            pin.url.replace("files.pythonhosted.org", "files.pythonhosted.org.evil"),
            pin.url.replace("files.pythonhosted.org", "user@files.pythonhosted.org"),
            pin.url + "?download=1", pin.url + "#fragment",
            pin.url.replace("/packages/", "/packages/../"),
            pin.url.replace(pin.filename, "%2e%2e.whl"),
        )
        for url in invalid:
            transport = Transport([])
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.api.stage_wheels(
                    (replace(pin, url=url),), self.root, bounds=self.bounds,
                    authorize=self.authorize, transport=transport,
                )
            self.assertEqual(transport.calls, [])
        self.assertEqual(self.auth_calls, [])

    def test_redirect_refusal(self):
        pin = self.pin()
        for status, url in ((302, pin.url), (200, pin.url.replace("/aa/", "/ab/"))):
            root = self.parent / f"redirect-{status}"
            response = Response(url, [], status=status)
            with self.assertRaises(ValueError):
                self.api.stage_wheels(
                    (pin,), root, bounds=self.bounds, authorize=self.authorize,
                    transport=Transport([response]),
                )
            self.assertEqual(response.reads, [])
            self.assertEqual(response.closed, 1)

    def test_duplicates(self):
        pin = self.pin()
        with self.assertRaises(ValueError):
            self.stage((pin, pin), [])
        self.assertEqual(self.auth_calls, [])
        self.assertFalse(self.root.exists())

    def test_overflow(self):
        pin = self.pin()
        cases = (
            (replace(self.bounds, max_bytes=2), [b"abc"], False),
            (replace(self.bounds, max_chunks=1), [b"a", b"bc"], True),
            (self.bounds, [b"abcd"], True),
        )
        for index, (bounds, chunks, created) in enumerate(cases):
            root = self.parent / f"overflow-{index}"
            transport = Transport([Response(pin.url, chunks)])
            with self.assertRaises(ValueError):
                self.api.stage_wheels(
                    (pin,), root, bounds=bounds, authorize=self.authorize,
                    transport=transport,
                )
            self.assertEqual(root.exists(), created)
            if created:
                self.assertLessEqual((root / pin.filename).stat().st_size, 1)
        with self.assertRaises(ValueError):
            self.stage(tuple(self.pin(f"p{i}", b"x") for i in range(221)), [])

    def test_deadline(self):
        pin = self.pin()
        response = Response(pin.url, [b"abc"], before_read=lambda: setattr(self, "now", 11))
        with self.assertRaises(TimeoutError):
            self.stage((pin,), [response])
        self.assertEqual((self.root / pin.filename).stat().st_size, 0)
        self.assertEqual(response.closed, 1)

    def test_path_and_symlink(self):
        pin = self.pin()
        self.root.mkdir()
        sentinel = self.root / pin.filename
        sentinel.write_bytes(b"untouched")
        with self.assertRaises(OSError):
            self.stage((pin,), [])
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        link = self.parent / "link"
        link.symlink_to(self.root, target_is_directory=True)
        for root in (link, link / "child"):
            transport = Transport([])
            with self.assertRaises(OSError):
                self.api.stage_wheels(
                    (pin,), root, bounds=self.bounds, authorize=self.authorize,
                    transport=transport,
                )
            self.assertEqual(transport.calls, [])
        with self.assertRaises(ValueError):
            self.stage((replace(pin, filename="../escape.whl"),), [])

    def test_hardlink_mutation(self):
        pin = self.pin()
        def mutate():
            os.link(self.root / pin.filename, self.root / "retained-link")
        with self.assertRaises(ValueError):
            self.stage((pin,), [Response(pin.url, [b"abc"], before_read=mutate)])
        self.assertEqual((self.root / pin.filename).stat().st_size, 0)

    def test_owner_and_path_mutation(self):
        pin = self.pin()
        original_fstat = os.fstat
        mutated = False
        def fstat(fd):
            result = original_fstat(fd)
            if mutated and stat.S_ISREG(result.st_mode):
                fields = {name: getattr(result, name) for name in
                          ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_size")}
                fields["st_uid"] += 1
                return SimpleNamespace(**fields)
            return result
        def change_owner():
            nonlocal mutated
            mutated = True
        with patch.object(self.api.os, "fstat", side_effect=fstat):
            with self.assertRaises(ValueError):
                self.stage((pin,), [Response(pin.url, [b"abc"], before_read=change_owner)])
        self.assertEqual((self.root / pin.filename).stat().st_size, 0)
        for kind in ("file", "root"):
            root = self.parent / kind
            def replace_path():
                target = root / pin.filename if kind == "file" else root
                target.rename(target.with_name(target.name + ".retained"))
                if kind == "file":
                    target.write_bytes(b"replacement")
                else:
                    target.mkdir()
            with self.assertRaises(ValueError):
                self.api.stage_wheels(
                    (pin,), root, bounds=self.bounds, authorize=self.authorize,
                    transport=Transport([Response(pin.url, [b"abc"], before_read=replace_path)]),
                )
            retained = (root / (pin.filename + ".retained") if kind == "file"
                        else root.with_name(root.name + ".retained") / pin.filename)
            self.assertEqual(retained.stat().st_size, 0)

    def test_partial_retention_no_retry(self):
        pin = self.pin()
        response = Response(pin.url, [b"ab", OSError("transport interrupted")])
        transport = Transport([response])
        with self.assertRaises(OSError):
            self.api.stage_wheels(
                (pin,), self.root, bounds=self.bounds, authorize=self.authorize,
                transport=transport,
            )
        self.assertEqual((self.root / pin.filename).read_bytes(), b"ab")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(response.closed, 1)

    def assert_cleanup_notes(self, error, count):
        notes = getattr(error, "__notes__", [])
        self.assertEqual(len(notes), count)
        for note in notes:
            self.assertIn(note, (
                "wheel response cleanup failed",
                "wheel descriptor cleanup failed",
            ))
            self.assertNotIn("private-cleanup-marker", note)
            self.assertNotIn(str(self.root), note)
            self.assertNotIn(self.pin().url, note)

    def test_transfer_failure_with_response_close_failure(self):
        pin = self.pin()
        primary = OSError("synthetic transfer interrupted")
        response = Response(
            pin.url, [b"ab", primary],
            close_error=OSError("private-cleanup-marker"),
        )
        transport = Transport([response])
        with self.assertRaises(OSError) as caught:
            self.api.stage_wheels(
                (pin,), self.root, bounds=self.bounds, authorize=self.authorize,
                transport=transport,
            )
        self.assertIs(caught.exception, primary)
        self.assert_cleanup_notes(primary, 1)
        self.assertEqual((self.root / pin.filename).read_bytes(), b"ab")
        self.assertEqual(len(response.reads), 2)
        self.assertEqual(response.closed, 1)
        self.assertEqual(len(transport.calls), 1)

    def test_cancellation_with_response_close_failure(self):
        pin = self.pin()
        for index, primary in enumerate((KeyboardInterrupt("cancelled"), SystemExit(7))):
            with self.subTest(cancellation=type(primary).__name__):
                self.root = self.parent / f"cancellation-{index}"
                response = Response(
                    pin.url, [b"ab", primary],
                    close_error=OSError("private-cleanup-marker"),
                )
                transport = Transport([response])
                with self.assertRaises(type(primary)) as caught:
                    self.api.stage_wheels(
                        (pin,), self.root, bounds=self.bounds, authorize=self.authorize,
                        transport=transport,
                    )
                self.assertIs(caught.exception, primary)
                self.assert_cleanup_notes(primary, 1)
                self.assertEqual((self.root / pin.filename).read_bytes(), b"ab")
                self.assertEqual(len(response.reads), 2)
                self.assertEqual(response.closed, 1)
                self.assertEqual(len(transport.calls), 1)

    def test_response_close_failure_without_primary(self):
        pin = self.pin()
        cleanup = OSError("private-cleanup-marker")
        response = Response(pin.url, [b"abc", b""], close_error=cleanup)
        try:
            raise ValueError("unrelated caller exception")
        except ValueError:
            with self.assertRaises(OSError) as caught:
                self.stage((pin,), [response])
        self.assertIs(caught.exception, cleanup)
        self.assertEqual((self.root / pin.filename).read_bytes(), b"abc")
        self.assertEqual(response.closed, 1)

    def check_descriptor_close_failures(self, primary):
        pin = self.pin()
        chunks = [b"ab", primary] if primary is not None else [b"abc", b""]
        response = Response(
            pin.url, chunks,
            close_error=OSError("private-cleanup-marker response")
            if primary is not None else None,
        )
        transport = Transport([response])
        original_open, original_close = os.open, os.close
        opened, attempts = [], []
        owned = set()
        failures = [
            OSError("private-cleanup-marker descriptor 1"),
            OSError("private-cleanup-marker descriptor 2"),
        ]

        def open_fd(*args, **kwargs):
            fd = original_open(*args, **kwargs)
            opened.append(fd)
            owned.add(fd)
            return fd

        def close_fd(fd):
            self.assertIn(fd, owned)
            attempts.append(fd)
            if len(attempts) <= len(failures):
                raise failures[len(attempts) - 1]
            original_close(fd)
            owned.remove(fd)

        try:
            with patch.object(self.api.os, "open", side_effect=open_fd):
                with patch.object(self.api.os, "close", side_effect=close_fd):
                    with self.assertRaises(BaseException) as caught:
                        self.api.stage_wheels(
                            (pin,), self.root, bounds=self.bounds,
                            authorize=self.authorize, transport=transport,
                        )
            self.assertGreaterEqual(len(opened), 3)
            self.assertCountEqual(attempts, opened)
            self.assertEqual(len(attempts), len(set(attempts)))
            self.assertEqual(len(owned), 2)
            expected = primary if primary is not None else failures[0]
            self.assertIs(caught.exception, expected)
            self.assert_cleanup_notes(expected, 3 if primary is not None else 1)
            expected_bytes = b"ab" if primary is not None else b"abc"
            self.assertEqual((self.root / pin.filename).read_bytes(), expected_bytes)
            self.assertEqual(len(response.reads), 2)
            self.assertEqual(response.closed, 1)
            self.assertEqual(len(transport.calls), 1)
        finally:
            # Fault injection leaves genuine descriptors open, including on RED.
            for fd in tuple(owned):
                original_close(fd)
                owned.remove(fd)
        self.assertEqual(owned, set())

    def test_descriptor_close_failures_preserve_primary(self):
        for index, primary in enumerate((
            OSError("synthetic transfer interrupted"), KeyboardInterrupt("cancelled"),
        )):
            with self.subTest(primary=type(primary).__name__):
                self.root = self.parent / f"descriptor-{index}"
                self.check_descriptor_close_failures(primary)

    def test_descriptor_close_failures_without_primary(self):
        self.check_descriptor_close_failures(None)
