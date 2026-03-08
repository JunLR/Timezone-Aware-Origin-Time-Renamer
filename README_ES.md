# Timezone-Aware Origin-Time Renamer

Idioma: [English](README.md) | [Italiano](README_IT.md) | Español | [中文](README_CN.md)

Este repositorio ofrece una herramienta pensada para terminal que renombra fotos y videos anteponiendo su marca de tiempo de captura/origen (`YYYYMMDD_HHMMSS_...`) usando metadatos leídos con `exiftool`. Es segura para re-ejecutar (solo renombra archivos nuevos/no procesados), resuelve automáticamente colisiones de nombres, soporta formatos mixtos (HEIC/JPG/DNG/MOV/MP4) y maneja correctamente las zonas horarias priorizando offsets embebidos y usando una zona horaria indicada en la ejecución cuando faltan en los metadatos (común en videos exportados/editados).

Script: `scripts/rename_by_origin_time.py`

Renombra los archivos a:

Default: `{ts}_{city}_{device}_{orig}.ext`

usando el tiempo de origen desde los metadatos (vía `exiftool`), con idempotencia y sufijos seguros ante colisiones.

## Requisitos

- Python 3.9+ (para `zoneinfo`)
- `exiftool` disponible en el PATH

## Instalación (CLI)

Recomendado (uv):

```bash
brew install uv
uv tool install .
```

Luego puedes ejecutar:

```bash
origin-time-renamer --help
```

Flujo para desarrolladores (instalación editable):

```bash
uv tool install --editable .
```

Instala exiftool (Homebrew):

```bash
brew install exiftool
```

## Uso

Por defecto es un dry-run (muestra qué haría, no renombra).

```bash
origin-time-renamer <path1> <path2>
```

Elegir un template de nombre (ejemplos):

```bash
origin-time-renamer --template "{ts}_{city}_{device}_{orig}" /path/to/media
origin-time-renamer --template "{ts}_{city}_{orig}" /path/to/media
origin-time-renamer --template "{ts}_{orig}" /path/to/media
origin-time-renamer --template "{ts}_{city}_{device}" /path/to/media
origin-time-renamer --template "{ts}" /path/to/media
```

Selector interactivo (elige -> preview -> confirma apply):

```bash
origin-time-renamer --interactive-template /path/to/media
origin-time-renamer --apply --interactive-template /path/to/media
```

Aplicar renombrados:

```bash
origin-time-renamer --apply /path/to/media
```

Escribir reporte CSV:

```bash
origin-time-renamer --apply --report ./rename_report.csv /path/to/media
```

Configurar zona horaria de fallback (por defecto `Asia/Hong_Kong`):

```bash
origin-time-renamer --default-tz Asia/Hong_Kong /path/to/media
```

Especificar zona horaria para esta ejecución (útil para una carpeta de viaje nueva):

```bash
origin-time-renamer \
  --default-tz Europe/Madrid \
  --apply /path/to/media
```

## Prioridad de Campos de Tiempo

1. `SubSecDateTimeOriginal`
2. `DateTimeOriginal`
3. `CreationDate`
4. `MediaCreateDate`
5. `CreateDate`

Selección de zona horaria:

1. Offset embebido en el valor datetime
2. `OffsetTimeOriginal` / `OffsetTime`
3. Para videos sin offset: asumir UTC y convertir
4. `--tz-map` (coincidencia por prefijo de ruta, gana el más largo)
5. `--default-tz` (por defecto: `Asia/Hong_Kong`)

## Idempotencia y Seguridad

- Si el nombre ya empieza con el `YYYYMMDD_HHMMSS_` calculado, se omite.
- Si el nombre ya tiene un prefijo timestamp pero no coincide, se omite con advertencia.
- Re-ejecutar el mismo comando en la misma carpeta solo afecta archivos nuevos aún no renombrados con esta regla.
- Colisiones en la misma carpeta: añade `_2`, `_3`, ... antes de la extensión.
- Archivos ocultos y extensiones no soportadas se ignoran.

## Override y Troubleshooting

Casos comunes donde conviene especificar una zona horaria por ejecución:

- Fuentes mixtas sin zona horaria (frecuente en videos exportados/editados): usa `--default-tz <IANA_TZ>` para convertir timestamps solo-UTC a la hora local deseada.
- Quieres una zona horaria consistente para toda una carpeta importada: ejecuta `--default-tz ... --apply <carpeta>`; al re-ejecutar luego solo se procesan archivos nuevos.

Para ver por qué un archivo usó un campo/zona horaria específica:

```bash
origin-time-renamer --report ./rename_report.csv /path/to/media
```

Revisa la columna `reason` (p. ej. `inline_offset:...`, `offset_tag`, `utc_assumed;default_tz:...`).

Si un archivo ya contiene un offset embebido pero es incorrecto, la herramienta lo usará (por diseño). En ese caso, corrige primero los metadatos (vía `exiftool`) o puedo agregar un modo `--force-tz`.

## Campos Ciudad y Dispositivo

- `{city}` se obtiene offline a partir de GPS (nearest-city best-effort) y se omite si no hay GPS.
- `{device}` se obtiene de make/model y se omite si no esta disponible.
- La busqueda de `{city}` requiere la dependencia `reverse_geocoder`, instalada automaticamente al instalar esta herramienta (p. ej. `uv tool install .`). Si solo ejecutas el script wrapper sin dependencias, `{city}` puede omitirse con un warning.

## Log de Auditoría y Undo

Al ejecutar con `--apply`, la herramienta escribe un log de auditoría en JSONL. Puedes indicar la ruta con `--log`; de lo contrario crea `./rename_log_YYYYMMDD_HHMMSS.jsonl` e imprime la ruta en el resumen.

Rollback desde un log (dry-run por defecto):

```bash
origin-time-renamer undo --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

Aplicar rollback:

```bash
origin-time-renamer undo --apply --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

## Extensiones Soportadas

`.heic .jpg .jpeg .png .dng .mov .mp4 .m4v .avi .mts .3gp` (no distingue mayúsculas/minúsculas)

## Códigos de Salida

- `0`: éxito
- `2`: `exiftool` faltante/no disponible
- `3`: fallos parciales (p. ej. errores de rename, error en tiempo de ejecución de exiftool)
