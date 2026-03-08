# Timezone-Aware Origin-Time Renamer

语言： [English](README.md) | 中文

脚本：`scripts/rename_by_origin_time.py`

把照片/视频重命名为：

`YYYYMMDD_HHMMSS_原文件名.ext`

时间来自文件内容里的拍摄/创建元数据（通过 `exiftool` 读取）。脚本支持幂等（可重复运行）并且会自动处理同名冲突（追加 `_2`、`_3` 等）。

## 依赖

- Python 3.9+（使用 `zoneinfo`）
- PATH 里可用的 `exiftool`

## 安装（CLI）

在仓库根目录执行：

```bash
python3 -m pip install -e .
```

然后可以直接运行：

```bash
origin-time-renamer --help
```

安装 exiftool（Homebrew）：

```bash
brew install exiftool
```

## 用法

默认是 dry run（演练/预览模式）：只打印“将会怎么改名”，不实际改文件名。

```bash
origin-time-renamer <路径1> <路径2>
```

真正执行重命名：

```bash
origin-time-renamer --apply /path/to/media
```

输出 CSV 报告：

```bash
origin-time-renamer --apply --report ./rename_report.csv /path/to/media
```

设置兜底时区（默认 `Asia/Hong_Kong`）：

```bash
origin-time-renamer --default-tz Asia/Hong_Kong /path/to/media
```

每次运行统一指定时区（适合对某次旅行目录批量处理；目录里有新增文件时重复运行也只会处理新增未命名的）：

```bash
origin-time-renamer \
  --default-tz Europe/Paris \
  --apply /path/to/media
```

## 时间字段优先级

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

## 幂等性与安全策略

- 如果文件名已经以计算得到的 `YYYYMMDD_HHMMSS_` 开头，则跳过。
- 如果文件名已经有时间戳前缀但与计算结果不同，会警告并跳过（避免二次加前缀）。
- 同一目录重复运行同一命令，只会影响新增且未按本规则命名的文件；已按规则命名的会被跳过。
- 同目录下目标文件名冲突会自动加 `_2`、`_3` ……
- 忽略隐藏文件和不支持的扩展名。

## 覆盖与排查

一些需要“每次运行统一指定时区”的常见场景：

- 混合来源且部分文件没有时区信息（常见于导出/编辑后的视频）：用 `--default-tz <IANA_TZ>`，把按 UTC 解析到的时间转换成你希望的本地时间再命名。
- 你希望某次导入的整个目录都用同一个时区：直接 `--default-tz ... --apply <目录>`；之后重复运行只会处理新增且未命名的文件。

想看每个文件到底用了哪个字段/时区来命名：

```bash
origin-time-renamer --report ./rename_report.csv /path/to/media
```

看 `reason` 列（例如 `inline_offset:...`、`offset_tag`、`utc_assumed;default_tz:...`）。

如果文件元数据里已经带了 offset 但这个 offset 是错的，脚本会按元数据来（这是设计选择）。这种情况建议先用 `exiftool` 修正元数据，或者告诉我我可以加一个 `--force-tz` 覆盖模式。

## 审计日志与回滚

当使用 `--apply` 执行重命名时，工具会写入 JSONL 审计日志。你可以用 `--log` 指定路径；否则会自动生成 `./rename_log_YYYYMMDD_HHMMSS.jsonl`，并在 summary 中打印路径。

通过日志回滚（默认 dry-run）：

```bash
origin-time-renamer undo --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

真正执行回滚：

```bash
origin-time-renamer undo --apply --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

## 支持的扩展名

`.heic .jpg .jpeg .png .dng .mov .mp4 .m4v .avi .mts .3gp`（大小写不敏感）

## 退出码

- `0`：成功
- `2`：缺少/不可用 `exiftool`
- `3`：部分失败（例如重命名失败、exiftool 运行时错误）
