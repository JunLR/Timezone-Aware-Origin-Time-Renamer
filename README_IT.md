# Timezone-Aware Origin-Time Renamer

Lingua: [English](README.md) | Italiano | [Español](README_ES.md) | [中文](README_CN.md)

Questo repository fornisce uno strumento da terminale che rinomina foto/video anteponendo il timestamp di acquisizione originale (`YYYYMMDD_HHMMSS_...`) usando i metadati letti da `exiftool`. È sicuro da rieseguire (rinomina solo i file nuovi/non elaborati), risolve automaticamente i conflitti di nome, supporta formati misti (HEIC/JPG/DNG/MOV/MP4) e gestisce correttamente i fusi orari preferendo gli offset incorporati e usando un fuso orario specificato a runtime quando i metadati non lo includono (tipico dei video esportati/modificati).

Script: `scripts/rename_by_origin_time.py`

Rinomina i file in:

Default: `{ts}_{city}_{device}_{orig}.ext`

usando l'orario di origine dai metadati (via `exiftool`), con idempotenza e suffissi sicuri in caso di collisione.

## Requisiti

- Python 3.9+ (per `zoneinfo`)
- `exiftool` disponibile nel PATH

## Installazione (CLI)

Consigliato (uv):

```bash
brew install uv
uv tool install .
```

Poi puoi eseguire:

```bash
origin-time-renamer --help
```

Workflow da sviluppatore (installazione editable):

```bash
uv tool install --editable .
```

Installa exiftool (Homebrew):

```bash
brew install exiftool
```

## Uso

Di default è un dry-run (mostra cosa farebbe, non rinomina).

```bash
origin-time-renamer <path1> <path2>
```

Scegli un template di naming (esempi):

```bash
origin-time-renamer --template "{ts}_{city}_{device}_{orig}" /path/to/media
origin-time-renamer --template "{ts}_{city}_{orig}" /path/to/media
origin-time-renamer --template "{ts}_{orig}" /path/to/media
origin-time-renamer --template "{ts}_{city}_{device}" /path/to/media
origin-time-renamer --template "{ts}" /path/to/media
```

Selettore interattivo (scegli -> preview -> conferma apply):

```bash
origin-time-renamer --interactive-template /path/to/media
origin-time-renamer --apply --interactive-template /path/to/media
```

Applica le rinomine:

```bash
origin-time-renamer --apply /path/to/media
```

Scrivi report CSV:

```bash
origin-time-renamer --apply --report ./rename_report.csv /path/to/media
```

Imposta il fuso orario di fallback (default `Asia/Hong_Kong`):

```bash
origin-time-renamer --default-tz Asia/Hong_Kong /path/to/media
```

Specifica il fuso orario per questa esecuzione (utile per una nuova cartella di viaggio):

```bash
origin-time-renamer \
  --default-tz Europe/Rome \
  --apply /path/to/media
```

## Priorità dei Campi Tempo

1. `SubSecDateTimeOriginal`
2. `DateTimeOriginal`
3. `CreationDate`
4. `MediaCreateDate`
5. `CreateDate`

Selezione del fuso orario:

1. Offset incorporato nel valore datetime
2. `OffsetTimeOriginal` / `OffsetTime`
3. Per i video senza offset: assumere UTC e convertire
4. `--tz-map` (match per prefisso di percorso, più lungo vince)
5. `--default-tz` (default: `Asia/Hong_Kong`)

## Idempotenza e Sicurezza

- Se il nome inizia già con `YYYYMMDD_HHMMSS_` calcolato, viene saltato.
- Se il nome ha già un prefisso timestamp ma non coincide, viene saltato con avviso.
- Rieseguire lo stesso comando sulla stessa cartella agisce solo sui file aggiunti di recente non ancora rinominati.
- Collisioni nello stesso folder: aggiunge `_2`, `_3`, ... prima dell'estensione.
- File nascosti ed estensioni non supportate vengono ignorati.

## Override e Troubleshooting

Casi comuni in cui vuoi specificare un fuso orario per esecuzione:

- Fonti miste con fuso orario mancante (spesso video esportati/modificati): usa `--default-tz <IANA_TZ>` per convertire i timestamp solo-UTC nel locale desiderato.
- Vuoi un fuso orario coerente per un'intera cartella importata: esegui con `--default-tz ... --apply <cartella>`; rieseguendo in seguito rinomini solo i file nuovi.

Per capire perché un file ha scelto un certo campo/fuso:

```bash
origin-time-renamer --report ./rename_report.csv /path/to/media
```

Controlla la colonna `reason` (es. `inline_offset:...`, `offset_tag`, `utc_assumed;default_tz:...`).

Se un file contiene un offset incorporato ma errato, lo strumento lo userà (per design). In tal caso correggi prima i metadati (via `exiftool`) oppure posso aggiungere una modalità `--force-tz`.

## Campi Citta e Dispositivo

- `{city}` deriva offline dalle coordinate GPS (nearest-city best-effort) ed e omesso se manca il GPS.
- `{device}` deriva dai campi make/model ed e omesso se non disponibile.
- La ricerca di `{city}` richiede la dipendenza `reverse_geocoder`, installata automaticamente quando installi questo tool (es. `uv tool install .`). Se esegui solo lo script wrapper senza dipendenze, `{city}` puo essere omesso con un warning.

## Log di Audit e Undo

Con `--apply`, lo strumento scrive un log di audit in JSONL. Puoi specificare il percorso con `--log`; altrimenti crea `./rename_log_YYYYMMDD_HHMMSS.jsonl` e stampa il percorso nel riepilogo.

Rollback da un log (dry-run di default):

```bash
origin-time-renamer undo --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

Applica il rollback:

```bash
origin-time-renamer undo --apply --log ./rename_log_YYYYMMDD_HHMMSS.jsonl
```

## Estensioni Supportate

`.heic .jpg .jpeg .png .dng .mov .mp4 .m4v .avi .mts .3gp` (case-insensitive)

## Exit Codes

- `0`: successo
- `2`: `exiftool` mancante/non disponibile
- `3`: fallimenti parziali (es. errori di rename, errore runtime di exiftool)
