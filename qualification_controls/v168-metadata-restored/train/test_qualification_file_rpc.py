"""Source-only public-wire tests. UNRUN by author; parent owns execution."""

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from train import qualification_file_rpc as rpc


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def frame(data):
    return struct.pack(">I", len(data)) + data


def body(data):
    return b"".join(frame(data[i:i + 65536])
                    for i in range(0, len(data), 65536)) + frame(b"")


class BoundedInput(io.BytesIO):
    def __init__(self, data, short=False):
        super().__init__(data)
        self.short = short
        self.requests = []

    def read(self, n=-1):
        if n < 0 or n > 65536:
            raise AssertionError("unbounded input read")
        self.requests.append(n)
        return super().read(min(n, 7) if self.short else n)


class ShortOutput(io.BytesIO):
    def write(self, data):
        if len(data) > 65536:
            raise AssertionError("unbounded output write")
        return super().write(data[:3])


class FileRPCTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Darwin's /var and /tmp can themselves be symlinks.
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "output"
        self.root.mkdir()
        self.roots = {"output": str(self.root)}

    def request(self, op="put", data=b"", key="x", **updates):
        value = {"v": 1, "op": op, "root": "output", "key": key,
                 "size": len(data), "sha256": digest(data)}
        value.update(updates)
        return value

    def manifest(self, **updates):
        value = {"v": 1, "op": "manifest", "root": "output",
                 "max_bytes": 1000000, "max_members": 100, "max_depth": 8}
        value.update(updates)
        return value

    def call(self, request, payload=b"", raw_body=None, raw_metadata=None,
             source=None, target=None, roots=None):
        wire = frame(canonical(request) if raw_metadata is None
                     else raw_metadata)
        wire += body(payload) if raw_body is None else raw_body
        source = BoundedInput(wire) if source is None else source
        target = io.BytesIO() if target is None else target
        rpc.serve_file_rpc(source, target,
                           roots=self.roots if roots is None else roots)
        return target.getvalue()

    def decode(self, wire, op):
        source = io.BytesIO(wire)
        prefix = source.read(4)
        self.assertEqual(len(prefix), 4)
        length = struct.unpack(">I", prefix)[0]
        metadata = json.loads(source.read(length))
        self.assertEqual(set(metadata), {"v", "ok", "op", "size", "sha256"})
        self.assertIs(type(metadata["v"]), int)
        self.assertEqual(metadata["v"], 1)
        self.assertIs(metadata["ok"], True)
        self.assertEqual(metadata["op"], op)
        self.assertIs(type(metadata["size"]), int)
        chunks = []
        while True:
            prefix = source.read(4)
            self.assertEqual(len(prefix), 4, "missing success terminator")
            count = struct.unpack(">I", prefix)[0]
            if count == 0:
                break
            self.assertLessEqual(count, 65536)
            chunk = source.read(count)
            self.assertEqual(len(chunk), count)
            chunks.append(chunk)
        self.assertEqual(source.read(), b"")
        data = b"".join(chunks)
        self.assertEqual(metadata["size"], len(data))
        self.assertEqual(metadata["sha256"], digest(data))
        return data

    def reject(self, request, message, **kwargs):
        with self.assertRaisesRegex(rpc.RPCError, message):
            self.call(request, **kwargs)

    def test_put_roundtrip(self):
        data = b"actual bytes"
        self.assertEqual(self.decode(self.call(self.request(data=data),
                                               payload=data), "put"), b"")
        self.assertEqual((self.root / "x").read_bytes(), data)

    def test_get_roundtrip(self):
        data = b"a" * 65536 + b"last"
        (self.root / "x").write_bytes(data)
        self.assertEqual(self.decode(self.call(self.request("get", data)),
                                     "get"), data)

    def test_manifest_roundtrip_canonical(self):
        (self.root / "b").write_bytes(b"two")
        (self.root / "a").write_bytes(b"one")
        expected = [{"key": key, "size": 3, "sha256": digest(data)}
                    for key, data in (("a", b"one"), ("b", b"two"))]
        self.assertEqual(self.decode(self.call(self.manifest()), "manifest"),
                         canonical(expected))

    def test_empty_manifest_zero_limits(self):
        wire = self.call(self.manifest(max_bytes=0, max_members=0, max_depth=0))
        self.assertEqual(self.decode(wire, "manifest"), b"[]")

    def test_metadata_exact_1048576_whitespace(self):
        request = self.request()
        raw = canonical(request)
        raw += b" " * (1048576 - len(raw))
        self.assertEqual(len(raw), 1048576)
        self.assertEqual(self.decode(self.call(request, raw_metadata=raw),
                                     "put"), b"")
        self.assertEqual((self.root / "x").read_bytes(), b"")

    def test_metadata_1048577_before_payload_read(self):
        source = BoundedInput(struct.pack(">I", 1048577))
        self.reject(self.request(), "metadata length", source=source)
        self.assertEqual(source.tell(), 4)
        self.assertEqual(source.requests, [4])

    def test_chunk_65536(self):
        data = b"x" * 65536
        self.decode(self.call(self.request(data=data), payload=data), "put")
        self.assertEqual((self.root / "x").read_bytes(), data)

    def test_chunk_65537_before_payload_read(self):
        request = self.request(size=65537)
        wire = frame(canonical(request)) + struct.pack(">I", 65537)
        source = BoundedInput(wire)
        self.reject(request, "chunk length", source=source)
        self.assertEqual(source.tell(), len(wire))

    def test_missing_metadata_prefix(self):
        self.reject(self.request(), "truncated", source=BoundedInput(b""))

    def test_zero_metadata(self):
        self.reject(self.request(), "metadata length",
                    source=BoundedInput(frame(b"")))

    def test_truncated_metadata(self):
        self.reject(self.request(), "truncated",
                    source=BoundedInput(struct.pack(">I", 20) + b"{}"))

    def test_missing_body(self):
        self.reject(self.request(), "truncated", raw_body=b"")

    def test_truncated_chunk_prefix(self):
        self.reject(self.request(), "truncated", raw_body=b"\0\0")

    def test_truncated_chunk_payload(self):
        self.reject(self.request(data=b"abc"), "truncated",
                    raw_body=struct.pack(">I", 3) + b"a")

    def test_missing_terminator(self):
        self.reject(self.request(data=b"x"), "truncated", raw_body=frame(b"x"))

    def test_trailing_body(self):
        self.reject(self.request(), "trailing", raw_body=frame(b"") + b"x")

    def test_put_wrong_hash_retains_explicit_partial(self):
        self.reject(self.request(data=b"x", sha256="0" * 64),
                    "partial retained.*hash", payload=b"x")
        self.assertEqual((self.root / "x").read_bytes(), b"x")

    def test_put_short_size(self):
        self.reject(self.request(size=1), "size", payload=b"")

    def test_put_oversize(self):
        self.reject(self.request(), "size", payload=b"x")

    def test_get_wrong_hash_before_response(self):
        (self.root / "x").write_bytes(b"x")
        target = io.BytesIO()
        self.reject(self.request("get", b"x", sha256="0" * 64), "hash",
                    target=target)
        self.assertEqual(target.getvalue(), b"")

    def test_get_wrong_size(self):
        (self.root / "x").write_bytes(b"x")
        self.reject(self.request("get"), "size")

    def test_get_requires_empty_terminated_body(self):
        (self.root / "x").write_bytes(b"")
        self.reject(self.request("get"), "empty", raw_body=body(b"x"))

    def test_get_requires_eof(self):
        (self.root / "x").write_bytes(b"")
        self.reject(self.request("get"), "trailing", raw_body=frame(b"") + b"x")

    def test_manifest_requires_terminator(self):
        self.reject(self.manifest(), "truncated", raw_body=b"")

    def test_manifest_rejects_nonempty_body(self):
        self.reject(self.manifest(), "empty", raw_body=body(b"x"))

    def test_manifest_requires_eof(self):
        self.reject(self.manifest(), "trailing", raw_body=frame(b"") + b"x")

    def test_duplicate_json(self):
        raw = canonical(self.request()).replace(b'"v":1', b'"v":1,"v":1')
        self.reject(self.request(), "duplicate", raw_metadata=raw)

    def test_nonfinite_json(self):
        raw = canonical(self.request()).replace(b'"size":0', b'"size":NaN')
        self.reject(self.request(), "nonfinite", raw_metadata=raw)

    def test_exact_schema_extra(self):
        self.reject(self.request(extra=0), "fields")

    def test_exact_schema_missing(self):
        request = self.request()
        del request["sha256"]
        self.reject(request, "fields")

    def test_bool_size(self):
        self.reject(self.request(size=False), "size")

    def test_bool_version(self):
        self.reject(self.request(v=True), "version")

    def test_bool_manifest_limit(self):
        self.reject(self.manifest(max_members=True), "max_members")

    def test_invalid_hash(self):
        self.reject(self.request(sha256="z" * 64), "sha256")

    def test_unknown_root(self):
        self.reject(self.request(root="unknown"), "root")

    def test_manifest_only_output_root(self):
        self.reject(self.manifest(root="source"), "root")

    def test_absolute_path(self):
        self.reject(self.request(key="/x"), "key")

    def test_parent_path(self):
        self.reject(self.request(key="../x"), "key")

    def test_empty_component(self):
        self.reject(self.request(key="a//x"), "key")

    def test_component_count(self):
        self.reject(self.request(key="/".join(["a"] * 65)), "key")

    def test_overwrite_preserves_original(self):
        (self.root / "x").write_bytes(b"old")
        self.reject(self.request(data=b"new"), "file operation", payload=b"new")
        self.assertEqual((self.root / "x").read_bytes(), b"old")

    def test_leaf_symlink(self):
        (self.base / "outside").write_bytes(b"")
        (self.root / "x").symlink_to(self.base / "outside")
        self.reject(self.request("get"), "file operation")

    def test_intermediate_symlink(self):
        (self.base / "outside").mkdir()
        (self.base / "outside" / "x").write_bytes(b"")
        (self.root / "link").symlink_to(self.base / "outside",
                                       target_is_directory=True)
        self.reject(self.request("get", key="link/x"), "file operation")

    def test_root_symlink(self):
        link = self.base / "link"
        link.symlink_to(self.root, target_is_directory=True)
        self.reject(self.manifest(), "file operation",
                    roots={"output": str(link)})

    def test_root_ancestor_symlink(self):
        link = self.base / "link"
        link.symlink_to(self.base, target_is_directory=True)
        self.reject(self.manifest(), "file operation",
                    roots={"output": str(link / "output")})

    def test_hardlink_get(self):
        (self.root / "x").write_bytes(b"")
        os.link(self.root / "x", self.base / "alias")
        self.reject(self.request("get"), "single-link")

    def test_directory_get(self):
        (self.root / "x").mkdir()
        self.reject(self.request("get"), "regular")

    def test_fifo_nonblocking_get(self):
        os.mkfifo(self.root / "x")
        real_open = os.open
        observed = []

        def checked_open(path, flags, mode=0o777, *, dir_fd=None):
            if path == "x":
                self.assertTrue(flags & os.O_NONBLOCK,
                                "refuse blocking FIFO open before syscall")
                observed.append(path)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with patch.object(rpc.os, "open", checked_open):
            self.reject(self.request("get"), "regular")
        self.assertEqual(observed, ["x"])

    def test_missing_file(self):
        self.reject(self.request("get"), "file operation")

    def test_manifest_inclusive_limits(self):
        (self.root / "dir").mkdir()
        (self.root / "dir" / "x").write_bytes(b"x")
        wire = self.call(self.manifest(max_bytes=1, max_members=1, max_depth=1))
        self.assertEqual(json.loads(self.decode(wire, "manifest")),
                         [{"key": "dir/x", "size": 1, "sha256": digest(b"x")}])

    def test_manifest_bytes_one_over(self):
        (self.root / "x").write_bytes(b"xx")
        self.reject(self.manifest(max_bytes=1), "bytes")

    def test_manifest_members_one_over(self):
        (self.root / "a").write_bytes(b"")
        (self.root / "b").write_bytes(b"")
        self.reject(self.manifest(max_members=1), "members")

    def test_manifest_depth_one_over_empty_directory(self):
        (self.root / "dir").mkdir()
        self.reject(self.manifest(max_depth=0), "depth")

    def test_manifest_symlink_not_omitted(self):
        (self.root / "link").symlink_to(self.base)
        self.reject(self.manifest(), "regular")

    def test_manifest_hardlink_not_omitted(self):
        (self.root / "x").write_bytes(b"")
        os.link(self.root / "x", self.base / "alias")
        self.reject(self.manifest(), "single-link")

    def test_manifest_directory_work_bound(self):
        (self.root / "a").mkdir()
        with patch.object(rpc, "MAX_DIRECTORY_ENTRIES", 1):
            self.assertEqual(self.decode(self.call(self.manifest()), "manifest"),
                             b"[]")
            (self.root / "b").mkdir()
            self.reject(self.manifest(), "directory entries")

    def test_manifest_json_byte_ceiling(self):
        (self.root / "x").write_bytes(b"")
        expected = canonical([{"key": "x", "size": 0, "sha256": digest(b"")}])
        with patch.object(rpc, "MAX_MANIFEST_BYTES", len(expected)):
            self.assertEqual(self.decode(self.call(self.manifest()), "manifest"),
                             expected)
        with patch.object(rpc, "MAX_MANIFEST_BYTES", len(expected) - 1):
            self.reject(self.manifest(), "JSON bytes")

    def test_model_size_reaches_body_without_gigabyte_allocation(self):
        self.reject(self.request(size=1192135096), "truncated", raw_body=b"")
        self.assertEqual((self.root / "x").stat().st_size, 0)

    def test_file_cap_plus_one_metadata_rejection(self):
        self.reject(self.request(size=2147483649), "size")
        self.assertFalse((self.root / "x").exists())

    def test_file_cap_exact_reaches_body(self):
        self.reject(self.request(size=2147483648), "truncated", raw_body=b"")
        self.assertEqual((self.root / "x").stat().st_size, 0)

    def test_short_input_file_and_output_writes(self):
        data = b"abc" * 30000
        request = self.request(data=data)
        source = BoundedInput(frame(canonical(request)) + body(data), short=True)
        real_write = os.write

        def short_write(fd, chunk):
            return real_write(fd, chunk[:5])

        with patch.object(rpc.os, "write", short_write):
            self.decode(self.call(request, source=source,
                                  target=ShortOutput()), "put")
        self.assertEqual((self.root / "x").read_bytes(), data)
        self.assertEqual(self.decode(self.call(self.request("get", data),
                                              target=ShortOutput()), "get"),
                         data)

    def test_put_replacement_retains_unknown_inode(self):
        real_write = os.write
        fired = []

        def replace_after_write(fd, chunk):
            count = real_write(fd, chunk)
            if not fired:
                fired.append(True)
                (self.root / "x").rename(self.root / "owned-partial")
                (self.root / "x").write_bytes(b"unknown")
            return count

        with patch.object(rpc.os, "write", replace_after_write):
            self.reject(self.request(data=b"x"), "partial retained.*identity",
                        payload=b"x")
        self.assertEqual((self.root / "x").read_bytes(), b"unknown")
        self.assertEqual((self.root / "owned-partial").read_bytes(), b"x")

    def test_put_rehashes_written_inode(self):
        real_write = os.write

        def corrupt_write(fd, chunk):
            return real_write(fd, b"!" * len(chunk))

        with patch.object(rpc.os, "write", corrupt_write):
            self.reject(self.request(data=b"x"), "stored file hash",
                        payload=b"x")
        self.assertEqual((self.root / "x").read_bytes(), b"!")

    def test_put_replacement_during_ack_has_no_terminator(self):
        root = self.root

        class ReplacingOutput(io.BytesIO):
            changed = False

            def write(self, chunk):
                if b'"ok":true' in bytes(chunk) and not self.changed:
                    self.changed = True
                    (root / "x").rename(root / "owned-partial")
                    (root / "x").write_bytes(b"unknown")
                return super().write(chunk)

        target = ReplacingOutput()
        self.reject(self.request(data=b"x"), "partial retained.*identity",
                    payload=b"x", target=target)
        self.assertTrue(target.changed)
        self.assertEqual((self.root / "x").read_bytes(), b"unknown")
        with self.assertRaises(AssertionError):
            self.decode(target.getvalue(), "put")

    def test_zero_progress_file_write_fails(self):
        with patch.object(rpc.os, "write", return_value=0):
            self.reject(self.request(data=b"x"), "write progress", payload=b"x")
        self.assertEqual((self.root / "x").read_bytes(), b"")

    def test_zero_progress_output_write_fails(self):
        class NoProgress(io.BytesIO):
            def write(self, chunk):
                return 0

        self.reject(self.request(), "write progress", target=NoProgress())
        self.assertEqual((self.root / "x").read_bytes(), b"")

    def test_get_replacement_before_response(self):
        (self.root / "x").write_bytes(b"x")
        real_read = os.read
        fired = []

        def replace_after_read(fd, n):
            data = real_read(fd, n)
            if data and not fired:
                fired.append(True)
                (self.root / "x").rename(self.root / "old")
                (self.root / "x").write_bytes(b"x")
            return data

        target = io.BytesIO()
        with patch.object(rpc.os, "read", replace_after_read):
            self.reject(self.request("get", b"x"), "identity", target=target)
        self.assertEqual(target.getvalue(), b"")

    def test_get_same_inode_mutation_during_send_no_terminator(self):
        data = b"a" * 65536 + b"b"
        (self.root / "x").write_bytes(data)
        root = self.root

        class MutatingOutput(io.BytesIO):
            changed = False

            def write(self, chunk):
                if len(chunk) == 65536 and not self.changed:
                    self.changed = True
                    with (root / "x").open("r+b") as changed:
                        changed.seek(65536)
                        changed.write(b"c")
                return super().write(chunk)

        target = MutatingOutput()
        self.reject(self.request("get", data), "changed|hash", target=target)
        self.assertTrue(target.changed)
        with self.assertRaises(AssertionError):
            self.decode(target.getvalue(), "get")

    def test_root_directory_replacement_during_put(self):
        real_write = os.write
        fired = []

        def replace_root(fd, chunk):
            count = real_write(fd, chunk)
            if not fired:
                fired.append(True)
                self.root.rename(self.base / "old-output")
                self.root.mkdir()
                (self.root / "x").write_bytes(b"unknown")
            return count

        with patch.object(rpc.os, "write", replace_root):
            self.reject(self.request(data=b"x"), "partial retained.*identity",
                        payload=b"x")
        self.assertEqual((self.root / "x").read_bytes(), b"unknown")

    def test_manifest_file_mutation_is_not_a_valid_manifest(self):
        (self.root / "x").write_bytes(b"x")
        real_read = os.read
        fired = []

        def mutate(fd, n):
            data = real_read(fd, n)
            if data and not fired:
                fired.append(True)
                (self.root / "x").write_bytes(b"changed-size")
            return data

        with patch.object(rpc.os, "read", mutate):
            self.reject(self.manifest(), "changed|size")

    def test_manifest_directory_mutation_fails(self):
        (self.root / "x").write_bytes(b"x")
        real_read = os.read
        fired = []
        original = self.root.stat()

        def mutate(fd, n):
            data = real_read(fd, n)
            if data and not fired:
                fired.append(True)
                os.utime(self.root, ns=(original.st_atime_ns,
                                       original.st_mtime_ns + 1000000000))
            return data

        with patch.object(rpc.os, "read", mutate):
            self.reject(self.manifest(), "directory changed")
        self.assertEqual(fired, [True])

    def test_manifest_unreadable_member_is_not_omitted(self):
        (self.root / "x").write_bytes(b"x")
        real_stat = os.stat

        def refuse(path, *args, **kwargs):
            if path == "x":
                raise PermissionError("injected unreadable member")
            return real_stat(path, *args, **kwargs)

        target = io.BytesIO()
        with patch.object(rpc.os, "stat", refuse):
            self.reject(self.manifest(), "file operation", target=target)
        self.assertEqual(target.getvalue(), b"")

    def test_all_open_fds_closed_success_and_failure(self):
        real_open, real_close = os.open, os.close
        active = set()
        opened = []

        def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
            fd = real_open(path, flags, mode, dir_fd=dir_fd)
            active.add(fd)
            opened.append(fd)
            return fd

        def tracked_close(fd):
            result = real_close(fd)
            active.discard(fd)
            return result

        (self.root / "dir").mkdir()
        (self.root / "dir" / "x").write_bytes(b"x")
        with patch.object(rpc.os, "open", tracked_open), \
                patch.object(rpc.os, "close", tracked_close):
            self.decode(self.call(self.manifest()), "manifest")
            self.assertEqual(active, set())
            self.reject(self.manifest(max_bytes=0), "bytes")
            self.assertEqual(active, set())
            self.reject(self.request(key="bad", data=b"x",
                                     sha256="0" * 64), "hash", payload=b"x")
            self.assertEqual(active, set())
            self.reject(self.request("get", key="missing/x"), "file operation")
            self.assertEqual(active, set())
        self.assertGreater(len(opened), 6)
        for fd in set(opened):
            with self.assertRaises(OSError):
                os.fstat(fd)


if __name__ == "__main__":
    unittest.main()
