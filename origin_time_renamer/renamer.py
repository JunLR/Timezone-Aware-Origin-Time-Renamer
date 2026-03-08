"""Rename media files to YYYYMMDD_HHMMSS_originalName.ext using metadata origin time.

Priority tags:
1) SubSecDateTimeOriginal
2) DateTimeOriginal
3) CreationDate
4) MediaCreateDate
5) CreateDate

Timezone resolution:
- Datetime offset in tag value
- OffsetTimeOriginal / OffsetTime tags
- --tz-map path-prefix match (longest prefix)
- --default-tz (Asia/Hong_Kong)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

SUPPORTED_EXTS = {
    ".heic",
    ".jpg",
    ".jpeg",
    ".png",
    ".dng",
    ".mov",
    ".mp4",
    ".m4v",
    ".avi",
    ".mts",
    ".3gp",
}

VIDEO_EXTS = {
    ".mov",
    ".mp4",
    ".m4v",
    ".avi",
    ".mts",
    ".3gp",
}

TIME_TAGS_PRIORITY = [
    "SubSecDateTimeOriginal",
    "DateTimeOriginal",
    "CreationDate",
    "MediaCreateDate",
    "CreateDate",
]

TS_PREFIX_RE = re.compile(r"^(\d{8}_\d{6})(?:_|$)")
ILLEGAL_FILENAME_CHARS_RE = re.compile(r'[\\/:"*?<>|]+')
WS_RE = re.compile(r"\s+")
MULTI_UNDERSCORE_RE = re.compile(r"_+")
MULTI_DASH_RE = re.compile(r"-+")

_CITY_CACHE: Dict[Tuple[float, float], str] = {}
_REVERSE_GEOCODER_IMPORT_ERROR: Optional[str] = None


@dataclass
class Action:
    status: str
    source: str
    target: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename media by metadata origin time (idempotent and collision-safe)."
    )
    parser.add_argument("paths", nargs="*", default=["."], help="Files/directories to process")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames. Default is dry-run preview.",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--report",
        default="",
        help="Write CSV report to this path",
    )
    parser.add_argument(
        "--default-tz",
        default="Asia/Hong_Kong",
        help="Fallback timezone when metadata has no timezone and no tz-map match",
    )
    parser.add_argument(
        "--tz-map",
        default="",
        help='Comma-separated mapping: "path_prefix=IANA_TZ,path2=IANA_TZ"',
    )
    return parser.parse_args()


def ensure_exiftool() -> None:
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: exiftool is required but not installed.", file=sys.stderr)
        raise SystemExit(2)

    if result.returncode != 0:
        print("ERROR: exiftool is required but unavailable.", file=sys.stderr)
        raise SystemExit(2)


def validate_timezones(default_tz: str, tz_map: Dict[str, str]) -> None:
    try:
        ZoneInfo(default_tz)
    except Exception as exc:
        print(f"ERROR: Invalid --default-tz '{default_tz}': {exc}", file=sys.stderr)
        raise SystemExit(1)

    for prefix, tz_name in tz_map.items():
        try:
            ZoneInfo(tz_name)
        except Exception as exc:
            print(f"ERROR: Invalid timezone '{tz_name}' for prefix '{prefix}': {exc}", file=sys.stderr)
            raise SystemExit(1)


def parse_tz_map(raw: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not raw.strip():
        return mapping

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid --tz-map entry '{item}'. Expected 'path_prefix=IANA_TZ'.")
        prefix, tz_name = item.split("=", 1)
        prefix = prefix.strip()
        tz_name = tz_name.strip()
        if not prefix or not tz_name:
            raise ValueError(f"Invalid --tz-map entry '{item}'.")
        mapping[prefix] = tz_name

    return mapping


def is_hidden_name(name: str) -> bool:
    return name.startswith(".")


def discover_media_files(paths: Sequence[str]) -> List[str]:
    found: List[str] = []

    for p in paths:
        path = Path(p).expanduser().resolve()
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTS and not is_hidden_name(path.name):
                found.append(str(path))
            continue

        for root, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not is_hidden_name(d)]
            for name in filenames:
                if is_hidden_name(name):
                    continue
                ext = Path(name).suffix.lower()
                if ext in SUPPORTED_EXTS:
                    found.append(str(Path(root) / name))

    # Keep deterministic order
    return sorted(dict.fromkeys(found))


def batch_iter(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def read_metadata(files: Sequence[str]) -> Dict[str, Dict[str, object]]:
    metadata: Dict[str, Dict[str, object]] = {}
    if not files:
        return metadata

    base_cmd = [
        "exiftool",
        "-j",
        "-m",
        "-n",
        "-SubSecDateTimeOriginal",
        "-DateTimeOriginal",
        "-CreationDate",
        "-MediaCreateDate",
        "-CreateDate",
        "-OffsetTimeOriginal",
        "-OffsetTime",
        "-GPSLatitude",
        "-GPSLongitude",
        "-City",
        "-Location",
        "-Country",
        "-Make",
        "-Model",
        "-DeviceModelName",
    ]

    for batch in batch_iter(files, 400):
        cmd = base_cmd + list(batch)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                records = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Failed to parse exiftool JSON: {exc}") from exc

            for rec in records:
                src = rec.get("SourceFile")
                if isinstance(src, str):
                    metadata[str(Path(src).resolve())] = rec
            continue

        # If one bad file breaks a batch, fallback to per-file collection.
        for one in batch:
            single_cmd = base_cmd + [one]
            one_result = subprocess.run(
                single_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if one_result.returncode != 0:
                metadata[one] = {"SourceFile": one, "__error__": one_result.stderr.strip()}
                continue
            try:
                one_records = json.loads(one_result.stdout)
            except json.JSONDecodeError:
                metadata[one] = {"SourceFile": one, "__error__": "json_decode_failed"}
                continue
            if not one_records:
                metadata[one] = {"SourceFile": one, "__error__": "no_record"}
                continue
            rec = one_records[0]
            src = rec.get("SourceFile")
            if isinstance(src, str):
                metadata[str(Path(src).resolve())] = rec
            else:
                metadata[one] = {"SourceFile": one, "__error__": "missing_source_file"}

    return metadata


def parse_offset_string(raw: str) -> timezone:
    text = raw.strip()
    if text == "Z":
        return timezone.utc
    if not re.match(r"^[+-]\d{2}:\d{2}$", text):
        raise ValueError(f"Unsupported offset format '{raw}'")
    sign = 1 if text[0] == "+" else -1
    hh = int(text[1:3])
    mm = int(text[4:6])
    return timezone(timedelta(seconds=sign * (hh * 3600 + mm * 60)))


def parse_exif_datetime(value: str) -> Tuple[datetime, Optional[timezone]]:
    # Typical forms:
    # YYYY:MM:DD HH:MM:SS
    # YYYY:MM:DD HH:MM:SS.sss
    # YYYY:MM:DD HH:MM:SS+01:00
    # YYYY:MM:DD HH:MM:SS.sss+01:00
    # YYYY:MM:DD HH:MM:SSZ
    text = value.strip()
    match = re.match(
        r"^(\d{4}:\d{2}:\d{2})\s+(\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?\s*(Z|[+-]\d{2}:\d{2})?$",
        text,
    )
    if not match:
        raise ValueError(f"Unsupported datetime format '{value}'")

    date_part, time_part, frac_part, offset_part = match.groups()
    dt = datetime.strptime(f"{date_part} {time_part}", "%Y:%m:%d %H:%M:%S")

    if frac_part:
        micros = int(frac_part.ljust(6, "0")[:6])
        dt = dt.replace(microsecond=micros)

    tzinfo: Optional[timezone] = None
    if offset_part:
        tzinfo = parse_offset_string(offset_part)

    return dt, tzinfo


def choose_tz_from_map(abs_path: str, tz_map: Dict[str, str], cwd: str) -> Optional[str]:
    if not tz_map:
        return None

    abs_norm = abs_path
    rel_norm = os.path.relpath(abs_path, cwd)
    rel_posix = rel_norm.replace(os.sep, "/")

    best_match_len = -1
    best_tz: Optional[str] = None

    for raw_prefix, tz_name in tz_map.items():
        prefix = raw_prefix.strip()
        if os.path.isabs(prefix):
            candidate = str(Path(prefix).expanduser().resolve())
            if abs_norm == candidate or abs_norm.startswith(candidate + os.sep):
                score = len(candidate)
            else:
                continue
        else:
            p = prefix.strip("/")
            if rel_posix == p or rel_posix.startswith(p + "/"):
                score = len(p)
            else:
                continue

        if score > best_match_len:
            best_match_len = score
            best_tz = tz_name

    return best_tz


def resolve_datetime(
    meta: Dict[str, object],
    abs_path: str,
    default_tz: str,
    tz_map: Dict[str, str],
    cwd: str,
) -> Tuple[Optional[datetime], str]:
    error_detail = meta.get("__error__")
    if isinstance(error_detail, str) and error_detail:
        return None, f"metadata_error:{error_detail}"

    source_tag: Optional[str] = None
    raw_value: Optional[str] = None

    for tag in TIME_TAGS_PRIORITY:
        value = meta.get(tag)
        if isinstance(value, str) and value.strip():
            source_tag = tag
            raw_value = value
            break

    if raw_value is None:
        return None, "no_time_tag"

    try:
        base_dt, inline_tz = parse_exif_datetime(raw_value)
    except ValueError:
        return None, f"invalid_datetime:{source_tag}"

    tz_source = ""
    tzinfo = inline_tz
    used_offset_tag = False

    if tzinfo is not None:
        tz_source = f"inline_offset:{source_tag}"
    else:
        offset_value = None
        for offset_tag in ("OffsetTimeOriginal", "OffsetTime"):
            ov = meta.get(offset_tag)
            if isinstance(ov, str) and ov.strip():
                offset_value = ov.strip()
                break
        if offset_value:
            try:
                tzinfo = parse_offset_string(offset_value)
                tz_source = "offset_tag"
                used_offset_tag = True
            except ValueError:
                tzinfo = None

    # Video metadata (QuickTime/MP4) often encodes times as UTC without an explicit offset.
    # In that case, treat the base datetime as UTC and convert into the selected timezone.
    ext = Path(abs_path).suffix.lower()
    base_is_utc = (
        ext in VIDEO_EXTS
        and source_tag in ("CreationDate", "MediaCreateDate", "CreateDate")
        and inline_tz is None
        and not used_offset_tag
    )

    if tzinfo is None:
        mapped_tz = choose_tz_from_map(abs_path, tz_map, cwd)
        if mapped_tz:
            tzinfo = ZoneInfo(mapped_tz)
            tz_source = f"tz_map:{mapped_tz}"
        else:
            tzinfo = ZoneInfo(default_tz)
            tz_source = f"default_tz:{default_tz}"

    if base_is_utc:
        aware_dt = base_dt.replace(tzinfo=timezone.utc).astimezone(tzinfo)
        return aware_dt, f"utc_assumed;{tz_source}"

    aware_dt = base_dt.replace(tzinfo=tzinfo)
    return aware_dt, tz_source


def extract_existing_ts(stem: str) -> Optional[str]:
    m = TS_PREFIX_RE.match(stem)
    if not m:
        return None
    return m.group(1)


def sanitize_component(text: str) -> str:
    s = text.strip()
    if not s:
        return ""
    s = WS_RE.sub("-", s)
    s = ILLEGAL_FILENAME_CHARS_RE.sub("", s)
    s = s.replace("_", "-")
    s = MULTI_DASH_RE.sub("-", s)
    return s.strip("-")


def collapse_underscores(text: str) -> str:
    s = MULTI_UNDERSCORE_RE.sub("_", text)
    return s.strip("_")


def template_uses(template: str, field: str) -> bool:
    return "{" + field + "}" in template


def build_device(meta: Dict[str, object]) -> str:
    device_model_name = meta.get("DeviceModelName")
    if isinstance(device_model_name, str) and device_model_name.strip():
        return sanitize_component(device_model_name)

    make = meta.get("Make")
    model = meta.get("Model")
    make_s = make.strip() if isinstance(make, str) else ""
    model_s = model.strip() if isinstance(model, str) else ""

    combo = "-".join([p for p in [make_s, model_s] if p])
    return sanitize_component(combo)


def build_city(meta: Dict[str, object]) -> str:
    city = meta.get("City")
    if isinstance(city, str) and city.strip():
        return sanitize_component(city)
    loc = meta.get("Location")
    if isinstance(loc, str) and loc.strip():
        return sanitize_component(loc)
    return ""


def reverse_geocode_city(lat: float, lon: float) -> str:
    global _REVERSE_GEOCODER_IMPORT_ERROR  # noqa: PLW0603
    key = (round(lat, 3), round(lon, 3))
    if key in _CITY_CACHE:
        return _CITY_CACHE[key]

    if _REVERSE_GEOCODER_IMPORT_ERROR is not None:
        return ""

    try:
        import reverse_geocoder as rg  # type: ignore
    except Exception as exc:  # noqa: BLE001
        _REVERSE_GEOCODER_IMPORT_ERROR = str(exc)
        print(
            "WARNING: reverse_geocoder is not available; {city} will be omitted. "
            "Install dependencies (e.g. `uv tool install .`) to enable offline city lookup.",
            file=sys.stderr,
        )
        return ""

    try:
        result = rg.search([(lat, lon)], mode=1)
        name = ""
        if result and isinstance(result, list) and isinstance(result[0], dict):
            v = result[0].get("name")
            if isinstance(v, str):
                name = v
        city = sanitize_component(name)
    except Exception:  # noqa: BLE001
        city = ""

    _CITY_CACHE[key] = city
    return city


def build_stem_from_template(
    template: str,
    ts: str,
    city: str,
    device: str,
    orig: str,
) -> str:
    formatted = template.format(ts=ts, city=city, device=device, orig=orig)
    formatted = collapse_underscores(formatted)
    return formatted


def choose_available_target(target: Path) -> Path:
    if not target.exists():
        return target

    stem = target.stem
    ext = target.suffix
    parent = target.parent
    idx = 2
    while True:
        candidate = parent / f"{stem}_{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1


def write_report(report_path: str, actions: Sequence[Action]) -> None:
    if not report_path:
        return

    report_file = Path(report_path).expanduser().resolve()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with report_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["status", "source", "target", "reason"])
        for a in actions:
            writer.writerow([a.status, a.source, a.target, a.reason])

def _default_log_path() -> str:
    # Per-run log file by default, so undo is unambiguous.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"./rename_log_{ts}.jsonl"

def rename_main(args: argparse.Namespace) -> int:

    try:
        tz_map = parse_tz_map(args.tz_map)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    validate_timezones(args.default_tz, tz_map)
    ensure_exiftool()

    files = discover_media_files(args.paths)
    if not files:
        print("No supported media files found.")
        return 0

    try:
        metadata = read_metadata(files)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    cwd = str(Path(".").resolve())
    dry_run = not args.apply
    log_path = (args.log or "").strip()
    if not log_path and args.apply:
        log_path = _default_log_path()

    log_file = None
    if log_path:
        log_file = Path(log_path).expanduser().resolve()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_file.open("a", encoding="utf-8")
    else:
        log_fp = None

    def log_event(event: dict) -> None:
        if log_fp is None:
            return
        log_fp.write(json.dumps(event, sort_keys=True) + "\n")
        log_fp.flush()

    actions: List[Action] = []
    counts = {
        "would_rename": 0,
        "renamed": 0,
        "already_renamed": 0,
        "skipped_prefixed_mismatch": 0,
        "skipped_no_metadata": 0,
        "error": 0,
    }

    for path in files:
        p = Path(path)
        meta = metadata.get(path, {})

        dt, tz_reason = resolve_datetime(meta, path, args.default_tz, tz_map, cwd)
        if dt is None:
            status = "skipped_no_metadata"
            reason = tz_reason
            actions.append(Action(status, path, path, reason))
            log_event(
                {
                    "status": status,
                    "source": path,
                    "target": path,
                    "reason": reason,
                    "mode": "dry-run" if dry_run else "apply",
                }
            )
            counts[status] += 1
            if args.verbose:
                print(f"[{status}] {path} ({reason})")
            continue

        ts = dt.strftime("%Y%m%d_%H%M%S")

        existing_ts = extract_existing_ts(p.stem)
        if existing_ts is not None:
            if existing_ts == ts and (p.stem == ts or p.stem.startswith(ts + "_")):
                status = "already_renamed"
                actions.append(Action(status, path, path, "timestamp_prefix_matches"))
                log_event(
                    {
                        "status": status,
                        "source": path,
                        "target": path,
                        "reason": "timestamp_prefix_matches",
                        "mode": "dry-run" if dry_run else "apply",
                    }
                )
                counts[status] += 1
                if args.verbose:
                    print(f"[{status}] {path}")
                continue

            status = "skipped_prefixed_mismatch"
            actions.append(
                Action(
                    status,
                    path,
                    path,
                    f"existing_prefix:{existing_ts};computed:{ts}",
                )
            )
            log_event(
                {
                    "status": status,
                    "source": path,
                    "target": path,
                    "reason": f"existing_prefix:{existing_ts};computed:{ts}",
                    "mode": "dry-run" if dry_run else "apply",
                }
            )
            counts[status] += 1
            print(f"[{status}] {path} (computed {ts}, keeping existing prefix)")
            continue

        template = getattr(args, "template", "{ts}_{orig}")
        orig = p.stem
        device = build_device(meta) if template_uses(template, "device") else ""

        city = ""
        if template_uses(template, "city"):
            lat = meta.get("GPSLatitude")
            lon = meta.get("GPSLongitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                city = reverse_geocode_city(float(lat), float(lon))
                if not city:
                    city = build_city(meta)
            else:
                city = build_city(meta)

        desired_stem = build_stem_from_template(template, ts=ts, city=city, device=device, orig=orig)
        if not desired_stem:
            desired_stem = f"{ts}_{orig}"

        desired_name = f"{desired_stem}{p.suffix}"
        desired_target = p.with_name(desired_name)

        final_target = choose_available_target(desired_target)
        if final_target != desired_target:
            collision_reason = "collision_suffix"
        else:
            collision_reason = ""

        if dry_run:
            status = "would_rename"
            counts[status] += 1
            reason = collision_reason or tz_reason
            actions.append(Action(status, path, str(final_target), reason))
            log_event(
                {
                    "status": status,
                    "source": path,
                    "target": str(final_target),
                    "reason": reason,
                    "mode": "dry-run",
                }
            )
            print(f"[{status}] {path} -> {final_target}")
            continue

        try:
            p.rename(final_target)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            counts[status] += 1
            actions.append(Action(status, path, str(final_target), f"rename_failed:{exc}"))
            log_event(
                {
                    "status": status,
                    "source": path,
                    "target": str(final_target),
                    "reason": f"rename_failed:{exc}",
                    "mode": "apply",
                }
            )
            print(f"[{status}] {path} -> {final_target} ({exc})", file=sys.stderr)
            continue

        status = "renamed"
        counts[status] += 1
        reason = collision_reason or tz_reason
        actions.append(Action(status, path, str(final_target), reason))
        log_event(
            {
                "status": status,
                "source": path,
                "target": str(final_target),
                "reason": reason,
                "mode": "apply",
            }
        )
        print(f"[{status}] {path} -> {final_target}")

    write_report(args.report, actions)
    if log_fp is not None:
        log_fp.close()

    print("\nSummary:")
    print(f"  mode: {'dry-run' if dry_run else 'apply'}")
    print(f"  total_files: {len(files)}")
    for key in (
        "would_rename",
        "renamed",
        "already_renamed",
        "skipped_prefixed_mismatch",
        "skipped_no_metadata",
        "error",
    ):
        print(f"  {key}: {counts[key]}")
    if args.report:
        print(f"  report: {Path(args.report).expanduser().resolve()}")
    if log_path:
        print(f"  log: {Path(log_path).expanduser().resolve()}")

    return 3 if counts["error"] > 0 else 0
