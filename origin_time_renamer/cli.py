from __future__ import annotations

import argparse
import sys

from .undo import undo_main
from .renamer import rename_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="origin-time-renamer",
        description="Rename media files by origin metadata time with timezone handling.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rename_parser = sub.add_parser("rename", help="Rename files in-place")
    rename_parser.add_argument("paths", nargs="*", default=["."], help="Files/directories to process")

    rename_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames. Default is dry-run preview.",
    )
    rename_parser.add_argument("--verbose", action="store_true", help="Verbose output")
    rename_parser.add_argument("--report", default="", help="Write CSV report to this path")
    rename_parser.add_argument(
        "--log",
        default="",
        help="Write JSONL audit log to this path (default: ./rename_log_YYYYMMDD_HHMMSS.jsonl when --apply)",
    )
    rename_parser.add_argument(
        "--default-tz",
        default="Asia/Hong_Kong",
        help="Fallback timezone when metadata has no timezone and no tz-map match",
    )
    rename_parser.add_argument(
        "--tz-map",
        default="",
        help='Comma-separated mapping: "path_prefix=IANA_TZ,path2=IANA_TZ"',
    )

    undo_parser = sub.add_parser("undo", help="Rollback renames using a JSONL log")
    undo_parser.add_argument(
        "--log",
        required=True,
        help="JSONL log file previously produced by the rename command",
    )
    undo_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply rollback. Default is dry-run preview.",
    )
    undo_parser.add_argument("--verbose", action="store_true", help="Verbose output")
    undo_parser.add_argument(
        "--report",
        default="",
        help="Write CSV report to this path",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(parser.format_help())
        return 0
    if argv[0] not in {"rename", "undo"}:
        argv.insert(0, "rename")
    args = parser.parse_args(argv)

    if args.cmd == "rename":
        return rename_main(args)
    if args.cmd == "undo":
        return undo_main(args)

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
