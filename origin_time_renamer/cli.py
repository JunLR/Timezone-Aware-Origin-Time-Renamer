from __future__ import annotations

import argparse
import re
import sys

from .undo import undo_main
from .renamer import rename_main

TEMPLATE_CHOICES = [
    "{ts}_{city}_{device}_{orig}",
    "{ts}_{city}_{orig}",
    "{ts}_{orig}",
    "{ts}_{city}_{device}",
    "{ts}",
]

_CHOICE_RE = re.compile(r"[1-5]")


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
    rename_parser.add_argument(
        "--template",
        default=TEMPLATE_CHOICES[0],
        help="Output filename template (stem only, without extension).",
    )
    rename_parser.add_argument(
        "--interactive-template",
        action="store_true",
        help="Choose a template interactively, preview, then optionally confirm apply.",
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
        if getattr(args, "interactive_template", False):
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                print("ERROR: --interactive-template requires a TTY.", file=sys.stderr)
                return 2

            print("Select a filename template:")
            for idx, t in enumerate(TEMPLATE_CHOICES, start=1):
                default_mark = " (default)" if idx == 1 else ""
                print(f"  {idx}. {t}{default_mark}")

            chosen = None
            while chosen is None:
                raw = input("Choice [1]: ").strip()
                if raw == "":
                    chosen = 1
                    break
                # Be forgiving: accept "1", "1.", "1)" etc. (IME can add punctuation).
                m = _CHOICE_RE.search(raw)
                if m:
                    n = int(m.group(0))
                    if 1 <= n <= len(TEMPLATE_CHOICES):
                        chosen = n
                        break
                print(f"Invalid choice. Type 1-{len(TEMPLATE_CHOICES)} then press Enter.")

            chosen_template = TEMPLATE_CHOICES[chosen - 1]
            original_apply = bool(args.apply)
            original_log = getattr(args, "log", "")

            # 1) Preview pass (force dry-run, and disable audit log by default).
            preview_args = argparse.Namespace(**vars(args))
            preview_args.apply = False
            preview_args.template = chosen_template
            preview_args.log = ""
            rc = rename_main(preview_args)
            if rc != 0:
                return rc

            # 2) Optional apply pass.
            if not original_apply:
                return 0

            confirm = input("Proceed to apply? [y/N]: ").strip().lower()
            if confirm not in {"y", "yes"}:
                print("Aborted.")
                return 0

            apply_args = argparse.Namespace(**vars(args))
            apply_args.apply = True
            apply_args.template = chosen_template
            apply_args.log = original_log
            return rename_main(apply_args)

        return rename_main(args)
    if args.cmd == "undo":
        return undo_main(args)

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
