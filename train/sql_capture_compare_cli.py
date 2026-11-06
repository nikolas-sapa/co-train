"""Operator command for read-only caller-declared capture comparison."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from train.sql_capture_comparison import compare_capture_files, format_comparison


def _paths(parser, declarations):
    paths = {}
    for case_id, path in declarations:
        if case_id in paths:
            parser.error("duplicate arm declaration")
        paths[case_id] = Path(path)
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare explicit caller-declared capture files read-only.",
        allow_abbrev=False,
    )
    parser.add_argument("--case", action="append", default=[], metavar="ID")
    parser.add_argument(
        "--baseline", action="append", nargs=2, default=[],
        metavar=("CASE", "ABS_PATH"),
    )
    parser.add_argument(
        "--treatment", action="append", nargs=2, default=[],
        metavar=("CASE", "ABS_PATH"),
    )
    args = parser.parse_args(argv)
    planned_case_ids = tuple(args.case)
    if len(set(planned_case_ids)) != len(planned_case_ids):
        parser.error("duplicate case declaration")
    baseline_paths = _paths(parser, args.baseline)
    treatment_paths = _paths(parser, args.treatment)
    try:
        comparison = compare_capture_files(
            planned_case_ids, baseline_paths, treatment_paths,
        )
    except ValueError:
        print("Capture comparison refused: invalid comparison arguments.", file=sys.stderr)
        return 1
    print(format_comparison(comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
