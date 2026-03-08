from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass
class UndoAction:
    status: str
    source: str
    target: str
    reason: str


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_report(report_path: str, actions: Sequence[UndoAction]) -> None:
    if not report_path:
        return
    report_file = Path(report_path).expanduser().resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with report_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["status", "source", "target", "reason"])
        for a in actions:
            writer.writerow([a.status, a.source, a.target, a.reason])


def undo_main(args) -> int:
    log_path = Path(args.log).expanduser().resolve()
    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")

    dry_run = not args.apply
    entries = list(iter_jsonl(log_path))

    # Only rollback entries that actually renamed.
    renamed = [e for e in entries if e.get("status") == "renamed"]

    actions: list[UndoAction] = []
    # Reverse order to safely rollback chains.
    for e in reversed(renamed):
        src = e.get("source")
        dst = e.get("target")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue

        src_path = Path(src)
        dst_path = Path(dst)

        if not dst_path.exists():
            actions.append(UndoAction("skipped_missing_target", dst, src, "target_missing"))
            continue

        if src_path.exists():
            actions.append(UndoAction("skipped_source_exists", dst, src, "source_exists"))
            continue

        if dry_run:
            actions.append(UndoAction("would_undo", dst, src, ""))
            print(f"[would_undo] {dst_path} -> {src_path}")
            continue

        try:
            dst_path.rename(src_path)
        except Exception as exc:  # noqa: BLE001
            actions.append(UndoAction("error", dst, src, f"rename_failed:{exc}"))
            print(f"[error] {dst_path} -> {src_path} ({exc})")
            continue

        actions.append(UndoAction("undone", dst, src, ""))
        print(f"[undone] {dst_path} -> {src_path}")

    write_report(args.report, actions)

    print("\nSummary:")
    print(f"  mode: {'dry-run' if dry_run else 'apply'}")
    print(f"  log: {log_path}")
    print(f"  entries_total: {len(entries)}")
    print(f"  entries_renamed: {len(renamed)}")
    print(f"  actions: {len(actions)}")
    if args.report:
        print(f"  report: {Path(args.report).expanduser().resolve()}")

    return 0

