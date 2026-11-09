"""One bounded file operation, never a command/training execution service.

Errors raise RPCError. A response is successful only after its body terminator,
EOF and successful process exit. Failed puts retain partial files: no racy
check-then-unlink of a name another writer could have replaced.
"""

from contextlib import contextmanager
import hashlib
import json
import os
import stat
import struct
import sys

MAX_METADATA = 1048576
CHUNK_BYTES = 65536
MAX_FILE_BYTES = 2 * 1024**3
MAX_TOTAL_BYTES = 8 * 1024**3
MAX_MEMBERS = 10000
MAX_DEPTH = 32
MAX_DIRECTORY_ENTRIES = 20000
MAX_MANIFEST_BYTES = 8 * 1024**2
MAX_KEY_BYTES = 4096
MAX_COMPONENTS = 64

_DEFAULT_ROOTS = {
    "source": "/opt/qualification/source",
    "model": "/opt/qualification/model",
    "data": "/opt/qualification/data",
    "wheels": "/opt/qualification/wheels",
    "output": "/var/tmp/qualification/output",
    "evidence": "/var/tmp/qualification/evidence",
    "request": "/var/tmp/qualification/request-input",
}
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
_FILE_FLAGS = os.O_NOFOLLOW | os.O_NONBLOCK
_EMPTY_HASH = hashlib.sha256(b"").hexdigest()


class RPCError(Exception):
    """Malformed wire input, filesystem failure, or observed mutation."""


def _read_exact(source, size):
    result = bytearray()
    while len(result) < size:
        chunk = source.read(min(CHUNK_BYTES, size - len(result)))
        if not isinstance(chunk, bytes) or not chunk:
            raise RPCError("truncated frame")
        if len(chunk) > min(CHUNK_BYTES, size - len(result)):
            raise RPCError("input returned excessive bytes")
        result.extend(chunk)
    return bytes(result)


def _length(source):
    return struct.unpack(">I", _read_exact(source, 4))[0]


def _eof(source):
    if source.read(1) != b"":
        raise RPCError("trailing bytes or incomplete EOF")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RPCError("duplicate JSON key")
        result[key] = value
    return result


def _no_constant(value):
    raise RPCError("nonfinite JSON value")


def _no_float(value):
    # The frozen request schema contains no floats (including overflow 1e999).
    raise RPCError("nonfinite or floating JSON value")


def _metadata(source):
    length = _length(source)
    if not 1 <= length <= MAX_METADATA:
        raise RPCError("metadata length outside 1..1048576")
    try:
        return json.loads(_read_exact(source, length).decode("utf-8"),
                          object_pairs_hook=_pairs,
                          parse_constant=_no_constant, parse_float=_no_float)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RPCError("invalid JSON metadata") from exc


def _key(value):
    if type(value) is not str:
        raise RPCError("key must be a string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise RPCError("key must be UTF-8") from exc
    parts = value.split("/")
    if (not encoded or len(encoded) > MAX_KEY_BYTES or
            len(parts) > MAX_COMPONENTS or
            any(part in ("", ".", "..") or "\0" in part or
                len(part.encode("utf-8")) > 255 for part in parts)):
        raise RPCError("invalid key components or byte limit")
    return parts


def _integer(request, name, cap):
    value = request[name]
    if type(value) is not int or not 0 <= value <= cap:
        raise RPCError(name + " outside bounded integer range")


def _validate(request):
    if type(request) is not dict:
        raise RPCError("request must be an object")
    if type(request.get("v")) is not int or request["v"] != 1:
        raise RPCError("invalid version")
    op = request.get("op")
    if type(op) is not str or op not in ("put", "get", "manifest"):
        raise RPCError("invalid operation")
    fields = ({"v", "op", "root", "key", "size", "sha256"} if
              op != "manifest" else
              {"v", "op", "root", "max_bytes", "max_members", "max_depth"})
    if set(request) != fields:
        raise RPCError("request fields must match exact schema")
    root = request["root"]
    if type(root) is not str or root not in _DEFAULT_ROOTS:
        raise RPCError("invalid root")
    if op == "manifest":
        if root != "output":
            raise RPCError("manifest root must be output")
        _integer(request, "max_bytes", MAX_TOTAL_BYTES)
        _integer(request, "max_members", MAX_MEMBERS)
        _integer(request, "max_depth", MAX_DEPTH)
    else:
        _key(request["key"])
        _integer(request, "size", MAX_FILE_BYTES)
        value = request["sha256"]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdefABCDEF" for c in value)):
            raise RPCError("sha256 must be exactly 64 hex digits")


def _chunks(source):
    while True:
        count = _length(source)
        if count == 0:
            _eof(source)
            return
        if False:
            raise RPCError("chunk length exceeds 65536")
        yield _read_exact(source, count)


def _empty_body(source):
    if _length(source) != 0:
        raise RPCError("get/manifest request body must be empty")
    _eof(source)


def _write_all(write, data):
    remaining = memoryview(data)
    while remaining:
        piece = remaining[:CHUNK_BYTES]
        count = write(piece)
        if type(count) is not int or not 0 < count <= len(piece):
            raise RPCError("output made no valid write progress")
        remaining = remaining[count:]


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _response(target, op, size, sha256):
    data = _json({"v": 1, "ok": True, "op": op,
                  "size": size, "sha256": sha256})
    _write_all(target.write, struct.pack(">I", len(data)))
    _write_all(target.write, data)


def _frame(target, data):
    _write_all(target.write, struct.pack(">I", len(data)))
    _write_all(target.write, data)


def _finish(target):
    _frame(target, b"")
    target.flush()


def _identity(info):
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _stamp(info):
    return (_identity(info), info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _regular(info):
    if not stat.S_ISREG(info.st_mode):
        raise RPCError("file must be regular")
    if info.st_nlink != 1:
        raise RPCError("file must be single-link")
    if not 0 <= info.st_size <= MAX_FILE_BYTES:
        raise RPCError("file size exceeds bounded ceiling")
    return info


class _Pins:
    """Retain root ancestors and active DFS/key directory chain."""

    def __init__(self):
        self.fds = []
        self.links = []

    def open_directory(self, parent, name):
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent)
        try:
            opened = os.fstat(fd)
            after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISDIR(opened.st_mode) or
                    _identity(before) != _identity(opened) or
                    _identity(after) != _identity(opened)):
                raise RPCError("directory identity changed during open")
        except BaseException:
            os.close(fd)
            raise
        self.fds.append(fd)
        self.links.append((parent, name, fd, _identity(opened)))
        return fd

    def check(self):
        for parent, name, fd, identity in self.links:
            opened = os.fstat(fd)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (_identity(opened) != identity or
                    _identity(named) != identity):
                raise RPCError("directory identity changed")

    @contextmanager
    def child(self, parent, name):
        fd = self.open_directory(parent, name)
        try:
            yield fd
            self.check()
        finally:
            self.links.pop()
            self.fds.pop()
            os.close(fd)

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()
        self.links.clear()


@contextmanager
def _root(path):
    path = os.fspath(path)
    if (type(path) is not str or not path.startswith("/") or
            len(path.encode("utf-8")) > MAX_KEY_BYTES):
        raise RPCError("root must be a bounded absolute path")
    parts = path.split("/")[1:]
    if (len(parts) > MAX_COMPONENTS or
            any(part in ("", ".", "..") or "\0" in part for part in parts)):
        raise RPCError("invalid root components")
    pins = _Pins()
    try:
        fd = os.open("/", _DIR_FLAGS)
        pins.fds.append(fd)
        for part in parts:
            fd = pins.open_directory(fd, part)
        pins.check()
        yield pins, fd
    finally:
        pins.close()


@contextmanager
def _parent(pins, root_fd, key):
    # Bounded recursive context managers retain and validate the whole chain.
    parts = _key(key)

    @contextmanager
    def descend(fd, index):
        if index == len(parts) - 1:
            yield fd, parts[-1]
        else:
            with pins.child(fd, parts[index]) as child:
                with descend(child, index + 1) as result:
                    yield result

    with descend(root_fd, 0) as result:
        yield result


def _check_file(parent, name, fd, expected):
    opened = _regular(os.fstat(fd))
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (_identity(opened) != _identity(expected) or
            _identity(named) != _identity(expected)):
        raise RPCError("file identity changed")
    _regular(named)
    if _stamp(named) != _stamp(opened):
        raise RPCError("file changed between handle and path stat")
    return opened


@contextmanager
def _existing(parent, name):
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    fd = os.open(name, os.O_RDONLY | _FILE_FLAGS, dir_fd=parent)
    try:
        opened = _regular(os.fstat(fd))
        if _stamp(before) != _stamp(opened):
            raise RPCError("file identity or content changed during open")
        _check_file(parent, name, fd, opened)
        yield fd, opened
    finally:
        os.close(fd)


def _scan(parent, name, fd, expected, size, target=None):
    """Hash actual handle bytes, bracketing the pass with stable path/fd stats."""
    before = _check_file(parent, name, fd, expected)
    if before.st_size != size:
        raise RPCError("file size differs from declaration")
    os.lseek(fd, 0, os.SEEK_SET)
    hasher = hashlib.sha256()
    count = 0
    while True:
        chunk = os.read(fd, CHUNK_BYTES)
        if not chunk:
            break
        count += len(chunk)
        if count > size:
            raise RPCError("file size changed during read")
        hasher.update(chunk)
        if target is not None:
            _frame(target, chunk)
    after = _check_file(parent, name, fd, expected)
    if count != size or _stamp(before) != _stamp(after):
        raise RPCError("file changed during read or size mismatch")
    return hasher.hexdigest(), after


def _put(request, source, target, pins, parent, name):
    fd = None
    try:
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | _FILE_FLAGS,
                     0o600, dir_fd=parent)
        opened = _regular(os.fstat(fd))
        _check_file(parent, name, fd, opened)
        pins.check()
        hasher = hashlib.sha256()
        count = 0
        for chunk in _chunks(source):
            count += len(chunk)
            if count > request["size"]:
                raise RPCError("body exceeds declared size")
            hasher.update(chunk)
            _write_all(lambda piece: os.write(fd, piece), chunk)
        if count != request["size"]:
            raise RPCError("body size differs from declaration")
        expected_hash = request["sha256"].lower()
        if hasher.hexdigest() != expected_hash:
            raise RPCError("body hash mismatch")
        # Rehash actual written inode, not merely the received stream.
        actual, baseline = _scan(parent, name, fd, opened, count)
        if actual != expected_hash:
            raise RPCError("stored file hash mismatch")
        pins.check()
        _response(target, "put", 0, _EMPTY_HASH)
        after = _check_file(parent, name, fd, opened)
        if _stamp(baseline) != _stamp(after):
            raise RPCError("stored file changed before acknowledgement")
        pins.check()
        _finish(target)
    except (OSError, RPCError) as exc:
        if fd is not None:
            raise RPCError("put failed; partial retained or namespace uncertain, "
                           "do not retry this key: "
                           + str(exc)) from exc
        raise
    finally:
        if fd is not None:
            os.close(fd)


def _get(request, target, pins, parent, name):
    with _existing(parent, name) as (fd, opened):
        size, expected_hash = request["size"], request["sha256"].lower()
        actual, baseline = _scan(parent, name, fd, opened, size)
        if actual != expected_hash:
            raise RPCError("file hash mismatch")
        pins.check()
        _response(target, "get", size, expected_hash)
        actual, after = _scan(parent, name, fd, opened, size, target)
        if actual != expected_hash or _stamp(baseline) != _stamp(after):
            raise RPCError("file changed or hash mismatch during export")
        pins.check()
        _finish(target)


def _manifest(request, pins, root_fd):
    results = []
    total_bytes = 0
    entries = 0
    encoded_members = 2  # Brackets; bound encoding before building final body.

    def visit(fd, prefix, depth):
        nonlocal total_bytes, entries, encoded_members
        before = os.fstat(fd)
        with os.scandir(fd) as iterator:
            for entry in iterator:
                entries += 1
                if entries > MAX_DIRECTORY_ENTRIES:
                    raise RPCError("manifest directory entries ceiling exceeded")
                key = prefix + entry.name
                _key(key)
                info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    if depth >= request["max_depth"]:
                        raise RPCError("manifest depth exceeded")
                    with pins.child(fd, entry.name) as child:
                        visit(child, key + "/", depth + 1)
                else:
                    _regular(info)
                    if len(results) >= request["max_members"]:
                        raise RPCError("manifest members exceeded")
                    with _existing(fd, entry.name) as (file_fd, opened):
                        if _stamp(info) != _stamp(opened):
                            raise RPCError("manifest member changed during open")
                        size = opened.st_size
                        if total_bytes + size > request["max_bytes"]:
                            raise RPCError("manifest bytes exceeded")
                        sha256, _ = _scan(fd, entry.name, file_fd, opened, size)
                    member = {"key": key, "size": size, "sha256": sha256}
                    encoded_members += len(_json(member)) + bool(results)
                    if encoded_members > MAX_MANIFEST_BYTES:
                        raise RPCError("manifest JSON bytes exceeded")
                    total_bytes += size
                    results.append(member)
        # Directory entry mutations must not silently disappear.
        after = os.fstat(fd)
        if (_identity(before) != _identity(after) or
                before.st_mtime_ns != after.st_mtime_ns or
                before.st_ctime_ns != after.st_ctime_ns):
            raise RPCError("manifest directory changed during traversal")
        pins.check()

    visit(root_fd, "", 0)
    results.sort(key=lambda item: item["key"])
    return _json(results)


def serve_file_rpc(stdin, stdout, *, roots=None):
    """Read exactly one framed operation and emit its real framed response.

    Explicit root mappings are a local unit-test seam, never a wire field or
    CLI option. Production directories must pre-exist, be owned and quiescent.
    """
    try:
        request = _metadata(stdin)
        _validate(request)
        if request["op"] != "put":
            _empty_body(stdin)
        root_map = _DEFAULT_ROOTS if roots is None else roots
        if request["root"] not in root_map:
            raise RPCError("configured root missing")
        with _root(root_map[request["root"]]) as (pins, root_fd):
            if request["op"] == "manifest":
                data = _manifest(request, pins, root_fd)
                pins.check()
                _response(stdout, "manifest", len(data),
                          hashlib.sha256(data).hexdigest())
                for offset in range(0, len(data), CHUNK_BYTES):
                    _frame(stdout, data[offset:offset + CHUNK_BYTES])
                pins.check()
                _finish(stdout)
            else:
                with _parent(pins, root_fd, request["key"]) as (parent, name):
                    if request["op"] == "put":
                        _put(request, stdin, stdout, pins, parent, name)
                    else:
                        _get(request, stdout, pins, parent, name)
    except OSError as exc:
        raise RPCError("file operation failed: " + str(exc)) from exc


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if not args.serve:
        parser.error("--serve is required")
    try:
        serve_file_rpc(sys.stdin.buffer, sys.stdout.buffer)
    except (RPCError, ValueError, TypeError):
        # Do not append an invented error schema to a potentially partial frame.
        sys.stderr.write("file RPC failed; response incomplete; "
                         "a failed put may retain a partial file\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
