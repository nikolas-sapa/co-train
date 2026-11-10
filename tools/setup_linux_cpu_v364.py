"""Install immutable CPU test tools into a new private prefix, without sudo."""
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
    parser.add_argument("--requirements", required=True)
    args = parser.parse_args()
    require(sys.platform == "linux" and platform.machine() == "x86_64",
            "requires Linux x86_64")
    require(sys.version_info >= (3, 12) and os.getuid() != 0,
            "requires nonroot modern bootstrap Python")
    parent = Path(args.parent)
    require(parent.is_absolute() and parent.resolve(strict=True) == parent,
            "noncanonical setup parent")
    root = Path(tempfile.mkdtemp(prefix="cpu-v364-tools-", dir=parent))
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

    def run(command):
        subprocess.run(command, env=clean, stdin=subprocess.DEVNULL,
                       stdout=sys.stderr, stderr=sys.stderr,
                       timeout=120, check=True)

    run([str(binary), "-I", "-B", "-c",
         "import sys; assert sys.version_info[:3] == (3,12,13)"])
    venv = root / "venv"
    run([str(binary), "-I", "-B", "-m", "venv", str(venv)])
    python = venv / "bin" / "python"
    pip = [str(python), "-I", "-B", "-m", "pip", "--isolated",
           "--disable-pip-version-check", "--no-cache-dir"]
    run(pip + ["index", "versions", "pytest", "--index-url",
               "https://pypi.org/simple", "--retries", "0", "--timeout", "20"])
    requirements = Path(args.requirements)
    require(requirements.is_absolute()
            and requirements.resolve(strict=True) == requirements,
            "requirements path")
    run(pip + ["install", "--require-hashes", "--no-deps",
               "--only-binary=:all:", "--no-compile", "--retries", "0",
               "--timeout", "20", "--index-url", "https://pypi.org/simple",
               "-r", str(requirements)])
    run([str(python), "-I", "-B", "-c",
         "import sys,pytest; assert sys.version_info[:3]==(3,12,13);"
         "assert pytest.__version__=='8.4.2'"])
    print(json.dumps({"python": str(python), "library_dir": libraries,
                      "archive_sha256": ARCHIVE_SHA256,
                      "python_version": "3.12.13", "pytest_version": "8.4.2"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
