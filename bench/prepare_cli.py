from __future__ import annotations

import argparse
import sys

from bench import prepare


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print("prepare: invalid command arguments", file=sys.stderr)
        self.exit(2)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _add_mode_argument(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", dest="fixture", action="store_const", const=True)
    mode.add_argument("--production", dest="fixture", action="store_const", const=False)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="prepare", allow_abbrev=False)
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=_ArgumentParser,
    )

    freeze = subparsers.add_parser(
        "freeze",
        allow_abbrev=False,
    )
    freeze.add_argument("--root", required=True)
    freeze.add_argument("--output", required=True)
    freeze.add_argument("--seed", type=int, required=True)
    freeze.add_argument("--simple", type=_positive_int, required=True)
    freeze.add_argument("--moderate", type=_positive_int, required=True)
    freeze.add_argument("--challenging", type=_positive_int, required=True)
    _add_mode_argument(freeze)
    freeze.add_argument(
        "--timeout-s",
        type=float,
        default=prepare.PRODUCTION_TIMEOUT_S,
    )
    freeze.add_argument(
        "--max-rows",
        type=int,
        default=prepare.PRODUCTION_MAX_ROWS,
    )

    validate = subparsers.add_parser(
        "validate",
        allow_abbrev=False,
    )
    validate.add_argument("--root", required=True)
    validate.add_argument("--draw", required=True)
    validate.add_argument("--output", required=True)
    validate.add_argument("--expected-draw-sha256", required=True)

    check = subparsers.add_parser(
        "check",
        allow_abbrev=False,
    )
    check.add_argument("--root", required=True)
    check.add_argument("--draw", required=True)
    check.add_argument("--supplement", required=True)
    check.add_argument("--expected-draw-sha256", required=True)
    check.add_argument("--expected-supplement-sha256", required=True)
    _add_mode_argument(check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        if args.command == "freeze":
            per_tier = {
                "simple": args.simple,
                "moderate": args.moderate,
                "challenging": args.challenging,
            }
            digest = prepare.freeze_draw(
                args.root,
                args.output,
                seed=args.seed,
                per_tier=per_tier,
                fixture=args.fixture,
                timeout_s=args.timeout_s,
                max_rows=args.max_rows,
            )
            print(digest)
            return 0

        if args.command == "validate":
            digest = prepare.validate_draw(
                args.root,
                args.draw,
                args.output,
                expected_draw_sha256=args.expected_draw_sha256,
            )
            print(digest)
            return 0

        result = prepare.load_validated_draw(
            args.root,
            args.draw,
            args.supplement,
            expected_draw_sha256=args.expected_draw_sha256,
            expected_supplement_sha256=args.expected_supplement_sha256,
            fixture=args.fixture,
        )
        mode = "fixture" if result.fixture else "production"
        print(
            f"planned={len(result.planned)} "
            f"eligible={len(result.eligible)} "
            f"excluded={len(result.exclusions)} "
            f"mode={mode} measurement=false model_calls=0"
        )
        return 0
    except prepare.PublicationIndeterminateError:
        print(
            "prepare: publication indeterminate; do not auto-retry; "
            "final artifact preserved",
            file=sys.stderr,
        )
        return 3
    except (prepare.PreparationError, OSError):
        print("prepare: preparation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
