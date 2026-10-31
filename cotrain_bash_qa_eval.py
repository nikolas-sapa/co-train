"""Project-only JSON CLI for the scoped Bash QA evaluation API."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="cotrain-bash-qa-eval",
        description="Run the project Bash QA evaluator with an explicit JSON config.",
    )
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = args.config.read_bytes()
    except OSError:
        parser.error("cannot read config file")

    from pydantic import ValidationError
    from verifiers.v1.configs.cli.eval import EvalConfig

    try:
        config = EvalConfig.model_validate_json(payload)
    except ValidationError:
        parser.error("invalid EvalConfig JSON")

    from cotrain_bash_qa_env import run_bash_qa_eval

    asyncio.run(run_bash_qa_eval(config))


if __name__ == "__main__":
    main()
