# Timezone-Aware Origin-Time Renamer

Language: English | [Italiano](README_IT.md) | [Español](README_ES.md) | [中文](README_CN.md)

This repo provides a terminal-friendly renaming tool that prefixes each photo/video with its origin capture timestamp (`YYYYMMDD_HHMMSS_...`) using metadata from `exiftool`. It is safe to re-run (only renames new/unprocessed files), resolves filename collisions automatically, supports mixed media formats (HEIC/JPG/DNG/MOV/MP4), and handles timezone correctly by preferring embedded offsets and falling back to a run-specific timezone when metadata is missing (common in exported/edited videos).

Script: `scripts/rename_by_origin_time.py`

Renames media to:

`YYYYMMDD_HHMMSS_originalName.ext`

using origin metadata time from file content (via `exiftool`), with idempotency and collision-safe suffixes.

## Requirements

- Python 3.9+ (for `zoneinfo`)
- `exiftool` in PATH

## Install (CLI)

Recommended (uv):

```bash
brew install uv
uv tool install .
```

Then you can run:

```bash
origin-time-renamer --help
```

Developer workflow (editable install):

```bash
uv tool install --editable .
```

Install exiftool (Homebrew):

```bash
brew install exiftool
```

## Usage

Default is dry-run preview (prints what would happen, does not rename).

```bash
origin-time-renamer <path1> <path2>
```

Apply renames:

```bash
origin-time-renamer --apply /path/to/media
```

Write report CSV:

```bash
origin-time-renamer --apply --report ./rename_report.csv /path/to/media
```

Set fallback timezone (default is `Asia/Hong_Kong`):

```bash
origin-time-renamer --default-tz Asia/Hong_Kong /path/to/media
```

Specify timezone for this run (useful for a new trip folder):

```bash
origin-time-renamer \
  --default-tz Europe/Paris \
  --apply /path/to/media
```

## Time Resolution Order

1. `SubSecDateTimeOriginal`
2. `DateTimeOriginal`
3. `CreationDate`
4. `MediaCreateDate`
5. `CreateDate`

Timezone selection:

1. Offset embedded in datetime value
2. `OffsetTimeOriginal` / `OffsetTime`
3. For video files without offset: assume UTC, then convert
4. `--tz-map` path-prefix match (longest prefix)
5. `--default-tz` (default: `Asia/Hong_Kong`)

## Idempotency and Safety

- If current name already starts with computed `YYYYMMDD_HHMMSS_`, it is skipped.
- If current name already has a timestamp prefix but does not match computed timestamp, it is skipped with warning.
- Re-running the same command on the same folder only affects newly added files that are not already named by this rule.
- Name collisions in the same folder append `_2`, `_3`, ... before extension.
- Hidden files and unsupported extensions are ignored.

## Override and Troubleshooting

Common cases where you may want to specify a timezone per run:

- Mixed sources with missing timezone (often exported/edited videos): use `--default-tz <IANA_TZ>` so UTC-only timestamps convert into the desired local time for naming.
- You want one consistent timezone for a whole folder you just imported: run with `--default-tz ... --apply <folder>`; re-running later only renames newly added, un-renamed files.

Inspect why a file used a specific timezone/time source:

```bash
origin-time-renamer --report ./rename_report.csv /path/to/media
```

Check the `reason` column (e.g. `inline_offset:...`, `offset_tag`, `utc_assumed;default_tz:...`).

If a file already contains an embedded offset but it is wrong, this script will trust it (by design). In that case, fix the metadata first (via `exiftool`) or tell me and I can add a `--force-tz` mode.

## Audit Log and Undo

When running with `--apply`, the tool writes a JSONL audit log. You can provide a path with `--log`; otherwise it creates `./rename_log_YYYYMMDD_HHMMSS.jsonl` and prints the path in the summary.

Rollback from a log (dry-run by default):

```bash
origin-time-renamer undo --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

Apply rollback:

```bash
origin-time-renamer undo --apply --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

## Supported Extensions

`.heic .jpg .jpeg .png .dng .mov .mp4 .m4v .avi .mts .3gp` (case-insensitive)

## Exit Codes

- `0`: success
- `2`: `exiftool` missing/unavailable
- `3`: partial failures (e.g., rename errors, exiftool runtime failure)
