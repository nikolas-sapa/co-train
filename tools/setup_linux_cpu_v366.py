"""Set up only the immutable Python runtime in a new private prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


URL = (
    "https://github.com/actions/python-versions/releases/download/"
    "3.12.13-27650778726/python-3.12.13-linux-24.04-x64.tar.gz"
)
ARCHIVE_BYTES = 94990593
ARCHIVE_SHA256 = "ce7d511228f095b5ea1ad5568543388870f5964688303f9ddc24ba06c336bfba"


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", required=True)
    args = parser.parse_args()
    require(sys.platform == "linux" and platform.machine() == "x86_64",
            "requires Linux x86_64")
    require(sys.version_info >= (3, 12) and os.getuid() != 0,
            "requires nonroot modern bootstrap Python")
    parent = Path(args.parent)
    require(parent.is_absolute() and parent.resolve(strict=True) == parent,
            "noncanonical setup parent")
    root = Path(tempfile.mkdtemp(prefix="cpu-v366-runtime-", dir=parent))
    require(stat.S_IMODE(root.stat().st_mode) == 0o700, "private setup root")
    home, tmp = root / "home", root / "tmp"
    home.mkdir(mode=0o700)
    tmp.mkdir(mode=0o700)
    archive = root / "python.tar.gz"
    digest = hashlib.sha256()
    size = 0
    # No inherited proxy, credential, or alternate-index environment is used.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL, timeout=30) as response, archive.open("xb") as output:
        while block := response.read(1024 * 1024):
            size += len(block)
            require(size <= ARCHIVE_BYTES, "Python archive grew")
            digest.update(block)
            output.write(block)
    require(size == ARCHIVE_BYTES and digest.hexdigest() == ARCHIVE_SHA256,
            "Python archive integrity")
    prefix = root / "python"
    prefix.mkdir(mode=0o700)
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        require(len(members) <= 100000
                and sum(member.size for member in members) <= 2 * 1024**3,
                "Python unpacking bound")
        require(all(not Path(member.name).is_absolute()
                    and ".." not in Path(member.name).parts
                    and (member.isfile() or member.isdir()
                         or member.issym() or member.islnk())
                    for member in members), "Python archive member")
        package.extractall(prefix, members=members, filter="data")
    # Never run vendor setup.sh (cache deletion and unpinned pip upgrade).
    binary = prefix / "bin" / "python3.12"
    require(binary.is_file() and not binary.is_symlink(), "Python executable")
    mode = binary.stat().st_mode
    require(not mode & (stat.S_ISUID | stat.S_ISGID), "privileged Python")
    libraries = str(prefix / "lib")
    clean = {"HOME": str(home), "TMPDIR": str(tmp),
             "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
             "LD_LIBRARY_PATH": libraries}

    result = subprocess.run(
        [str(binary), "-I", "-B", "-c",
         "import sys; assert sys.version_info[:3] == (3,12,13)"],
        env=clean, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=10)
    require(result.returncode == 0 and result.stdout == b"", "runtime version check")
    print(json.dumps({"python": str(binary), "library_dir": libraries,
                      "archive_sha256": ARCHIVE_SHA256, "python_version": "3.12.13",
                      "packages_installed": 0}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(json.dumps({"status": "SETUP_NONPASS", "error_type": type(error).__name__},
                         sort_keys=True), flush=True)
        raise SystemExit(1)
