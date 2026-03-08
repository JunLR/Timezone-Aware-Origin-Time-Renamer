# Timezone-Aware Origin-Time Renamer

[English](#english) | [中文](#中文)

---

## English

Script: `scripts/rename_by_origin_time.py`

Renames media to:

`YYYYMMDD_HHMMSS_originalName.ext`

using origin metadata time from file content (via `exiftool`), with idempotency and collision-safe suffixes.

### Requirements

- Python 3.9+ (for `zoneinfo`)
- `exiftool` in PATH

Install exiftool (Homebrew):

```bash
brew install exiftool
```

### Usage

Default is dry-run preview (prints what would happen, does not rename).

```bash
python3 scripts/rename_by_origin_time.py <path1> <path2>
```

Apply renames:

```bash
python3 scripts/rename_by_origin_time.py --apply /path/to/media
```

Write report CSV:

```bash
python3 scripts/rename_by_origin_time.py --apply --report ./rename_report.csv /path/to/media
```

Set fallback timezone (default is `Asia/Hong_Kong`):

```bash
python3 scripts/rename_by_origin_time.py --default-tz Asia/Hong_Kong /path/to/media
```

Specify timezone for this run (useful for a new trip folder):

```bash
python3 scripts/rename_by_origin_time.py \
  --default-tz Europe/Paris \
  --apply /path/to/media
```

### Time Resolution Order

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

### Idempotency and Safety

- If current name already starts with computed `YYYYMMDD_HHMMSS_`, it is skipped.
- If current name already has a timestamp prefix but does not match computed timestamp, it is skipped with warning.
- Re-running the same command on the same folder only affects newly added files that are not already named by this rule.
- Name collisions in the same folder append `_2`, `_3`, ... before extension.
- Hidden files and unsupported extensions are ignored.

### Supported Extensions

`.heic .jpg .jpeg .png .dng .mov .mp4 .m4v .avi .mts .3gp` (case-insensitive)

### Exit Codes

- `0`: success
- `2`: `exiftool` missing/unavailable
- `3`: partial failures (e.g., rename errors, exiftool runtime failure)

---

## 中文

脚本：`scripts/rename_by_origin_time.py`

把照片/视频重命名为：

`YYYYMMDD_HHMMSS_原文件名.ext`

时间来自文件内容里的拍摄/创建元数据（通过 `exiftool` 读取）。脚本支持幂等（可重复运行）并且会自动处理同名冲突（追加 `_2`、`_3` 等）。

### 依赖

- Python 3.9+（使用 `zoneinfo`）
- PATH 里可用的 `exiftool`

安装 exiftool（Homebrew）：

```bash
brew install exiftool
```

### 用法

默认是 dry run（演练/预览模式）：只打印“将会怎么改名”，不实际改文件名。

```bash
python3 scripts/rename_by_origin_time.py <路径1> <路径2>
```

真正执行重命名：

```bash
python3 scripts/rename_by_origin_time.py --apply /path/to/media
```

输出 CSV 报告：

```bash
python3 scripts/rename_by_origin_time.py --apply --report ./rename_report.csv /path/to/media
```

设置兜底时区（默认 `Asia/Hong_Kong`）：

```bash
python3 scripts/rename_by_origin_time.py --default-tz Asia/Hong_Kong /path/to/media
```

每次运行统一指定时区（适合对某次旅行目录批量处理；目录里有新增文件时重复运行也只会处理新增未命名的）：

```bash
python3 scripts/rename_by_origin_time.py \
  --default-tz Europe/Paris \
  --apply /path/to/media
```

### 时间字段优先级

1. `SubSecDateTimeOriginal`
2. `DateTimeOriginal`
3. `CreationDate`
4. `MediaCreateDate`
5. `CreateDate`

时区选择顺序：

1. 时间字段本身带 offset（例如 `+01:00` / `Z`）
2. `OffsetTimeOriginal` / `OffsetTime`
3. 视频文件若缺少 offset：按 UTC 解析，再转换
4. `--tz-map` 规则（路径前缀最长匹配）
5. `--default-tz`（默认：`Asia/Hong_Kong`）

### 幂等性与安全策略

- 如果文件名已经以计算得到的 `YYYYMMDD_HHMMSS_` 开头，则跳过。
- 如果文件名已经有时间戳前缀但与计算结果不同，会警告并跳过（避免二次加前缀）。
- 同一目录重复运行同一命令，只会影响新增且未按本规则命名的文件；已按规则命名的会被跳过。
- 同目录下目标文件名冲突会自动加 `_2`、`_3` ……
- 忽略隐藏文件和不支持的扩展名。

### 支持的扩展名

`.heic .jpg .jpeg .png .dng .mov .mp4 .m4v .avi .mts .3gp`（大小写不敏感）

### 退出码

- `0`：成功
- `2`：缺少/不可用 `exiftool`
- `3`：部分失败（例如重命名失败、exiftool 运行时错误）
