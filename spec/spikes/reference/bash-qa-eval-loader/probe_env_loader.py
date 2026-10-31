"""PROVES actual EvalConfig JSON -> Env -> taskset/harness construction only.

Run using the already-installed qualified interpreter and -B. Opens no listener,
does not run evaluation, and writes no output. MISSING: lifecycle/persistence.
"""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(ROOT)]

from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.utils.loaders import load_environment
from cotrain_bash_qa import ReportingBashConfig, ReportingBashHarness
from qa_eval_probe import ProbeEnv, ProbeEnvConfig
from qa_eval_probe_taskset import ProbeTaskset

raw = {
    "model": "fixture-model",
    "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
    "env": {
        "id": "qa_eval_probe",
        "taskset": {"id": "qa_eval_probe_taskset"},
        "agent": {
            "harness": {"id": "cotrain_bash_qa", "edit": False, "search": False},
            "runtime": {"type": "subprocess"},
            "max_turns": 3,
            "retries": {"max_retries": 0},
        },
        "retries": {"max_retries": 0},
    },
    "num_tasks": 1,
    "num_rollouts": 1,
    "max_concurrent": 1,
    "push": False,
    "rich": None,
    # SHORTCUT: unused during construction, not a product export path.
    "output_dir": str(HERE / "construction-output"),
    "run": {"dir": "probe"},
    "clean": False,
}
config = EvalConfig.model_validate_json(json.dumps(raw))
restored = EvalConfig.model_validate_json(config.model_dump_json())
assert type(restored.env) is ProbeEnvConfig
assert type(restored.env.agent.harness) is ReportingBashConfig
assert restored.model_dump(mode="json") == config.model_dump(mode="json")
env = load_environment(restored.env)
assert type(env) is ProbeEnv
assert env.config is restored.env
assert type(env.taskset) is ProbeTaskset
# SHORTCUT: loader diagnostic only, not a product dependency on private caches.
assert type(env._harnesses["agent"]) is ReportingBashHarness
seed, = list(env.taskset)
print("GREEN: EvalConfig JSON -> flat custom Env + taskset + canonical harness")
print("Execution disabled; zero policy/tool actions/listeners.")
