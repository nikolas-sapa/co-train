"""The SQL arm's stdlib boundary must not require the benchmark package."""

import shutil
import subprocess
import sys
from pathlib import Path


def test_sql_arm_modules_import_without_bench_or_frameworks(tmp_path):
    isolated = tmp_path / "isolated"
    shutil.copytree(
        Path(__file__).resolve().parent, isolated / "ptc",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    code = "\n".join([
        "import sys",
        "sys.path.insert(0, sys.argv[1])",
        "blocked = {'bench', 'torch', 'trl', 'unsloth', 'transformers', 'verifiers', 'vllm'}",
        "class BlockDependencies:",
        "    def find_spec(self, fullname, path=None, target=None):",
        "        if fullname.split('.')[0] in blocked:",
        "            raise ModuleNotFoundError('standalone dependency forbidden: ' + fullname)",
        "sys.meta_path.insert(0, BlockDependencies())",
        "import ptc.sql_arms, ptc.sql_diff",
        "assert ptc.sql_arms.__file__.startswith(sys.argv[1])",
        "assert ptc.sql_diff.__file__.startswith(sys.argv[1])",
        "assert not (blocked & {name.split('.')[0] for name in sys.modules})",
    ])
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(isolated)],
        cwd=tmp_path, capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
