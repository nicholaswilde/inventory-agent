---
name: homebox
description: Interacts with the Homebox API using the `hbctl` CLI to list, get, create, update, upsert, duplicate, bulk-edit, search, export, back up, inspect stats, generate labels/QR codes, look up barcodes, apply templates, manage maintenance logs and notifiers, run server actions, issue raw API requests, and attach files/links to items/entities.
---

# Homebox Skill

Use the `hbctl` CLI (`nicholaswilde/hbctl`) for all direct Homebox v0.26+ REST API interactions.

## Requirements

1. **Binary**: `hbctl` installed on `PATH` (Homebrew `nicholaswilde/homebrew-tap/hbctl`, APT `nicholaswilde/apt`, Scoop, or `cargo install --git https://github.com/nicholaswilde/hbctl`).
2. **Credentials**: Auto-loaded from local `.env` (`HOMEBOX_IP` / `HOMEBOX_URL` + `HOMEBOX_API_KEY`) or stored via `hbctl auth login`.

## CLI Usage

### List, Tree, Path & Search Entities

```bash
hbctl status
hbctl item list --all --json --select id,name,quantity
hbctl item list --include-archived --warranty-expiring 30 --output csv
hbctl item tree [--root "<location>"] [--max-depth 2]
hbctl item path <entity_id_or_asset_id>
hbctl search "<query>" --json --select id,name
hbctl search --type "Component" --parent "Workshop" --warranty-expiring 30 --with-path --limit 25 --json
hbctl search --manufacturer "Espressif" --field Voltage=3.3 --json --select id,name,fields
hbctl search --any --model "ESP32" --field "Notes=B0CJR4QZ45" --archived-only --include-archived --json
```

### Get, Move & Duplicate Entity

```bash
hbctl item get <entity_id> --with-path --json --select id,name,quantity,fields
hbctl item get 000-001 --json                                  # asset IDs like 000-001 auto-detected (or pass --asset-id)
hbctl item duplicate <entity_id> --count 2 --json
hbctl item move <entity_id_1> <entity_id_2> --to "<parent_name_or_id>"   # or 'none' to unparent
hbctl item move --tag staging --to "Warehouse" --dry-run
hbctl item list --tag unsorted -q | hbctl item move --items-from - --to "Inbox"
```

### Create & Upsert Entity

```bash
hbctl item create --name "ESP32 DevKit" --manufacturer "Espressif" --parent "Lab Bin" --field Voltage=3.3 --attach photo.jpg --optimize --json
hbctl item create --from-barcode 012345678905 --parent "Pantry" --json
hbctl item create --name "Refrigerator" --insured --warranty-expires 2028-01-15 --warranty-details "2-year replacement" --json
printf '%s' '{"name":"New Entity","manufacturer":"Acme"}' | hbctl item create --from-json - --attach-url "https://example.com/photo.jpg=product.jpg" --attach-best-effort --optimize --json
hbctl item upsert --name "ESP32 DevKit" --tag electronics --field Pins=38 --field-type number --match-by model --match-by name --match-mode contains --fill-missing
hbctl item upsert --name "Mason Jar" --tag tare-weight --field "Tare Weight (g)=250g" --field-type number
printf '%s' '{"name":"ESP32 DevKit","modelNumber":"ESP32"}' | hbctl item upsert --from-json - --match-by model --match-mode contains --on-match attach-only --attach photo.jpg --optimize --json
```

### Update Entity, Bulk Ops & Custom Fields

```bash
hbctl item update <entity_id> --quantity 5 --notes "Shelf A" --add-tag verified
hbctl item update <entity_id> --remove-tag pending --fill-missing
hbctl item update <entity_id> --sold-time 2026-06-01 --sold-to "Alice" --sold-price 15.00 --archived
hbctl item update --filter-tag temp --add-tag reviewed --dry-run
hbctl item list --tag old -q | hbctl item update --items-from - --archived
printf '%s' '{"quantity":5}' | hbctl item update <entity_id> --from-json - --fill-missing
hbctl field list <entity_id> --json
hbctl field get <entity_id> "Model Number" -q
hbctl field set <entity_id> "Model Number" "12345"
hbctl field delete <entity_id> "Obsolete Field"
```

### Delete Entity

```bash
hbctl item delete <entity_id> --yes
hbctl item delete --tag obsolete --yes --dry-run
hbctl item list --tag scrap -q | hbctl item delete --items-from - --yes
```

### Attachments

```bash
hbctl attachment upload --optimize --primary <entity_id> <file_path...> [--name <remote_name>]
hbctl attachment upload --optimize <entity_id> --attach-url "https://example.com/img.jpg=img.jpg"
printf '%s' "<bytes>" | hbctl attachment upload --name <remote_name> <entity_id> -
hbctl attachment list <entity_id> --json
hbctl attachment set-primary <entity_id> <attachment_id>
hbctl attachment update <entity_id> <attachment_id> --title "Owner Manual" --type manual --primary=false
hbctl attachment add-link <entity_id> "https://example.com/datasheet.pdf" --title "Datasheet" --type manual
hbctl attachment download <entity_id> --all --ext pdf --out ./manuals
hbctl attachment download --all-items --ext pdf --out ./manuals
hbctl attachment download --tag appliance --ext pdf --out ./manuals
hbctl attachment download --items-from ids.txt --ext pdf --out ./manuals
hbctl attachment delete <entity_id> <attachment_id>
```

### Entity Types, Tags, Profiles & Export

```bash
hbctl entity-types [list|create|delete]
hbctl tag [list|create|update|delete]
hbctl --profile <name> item list --all
hbctl item list --output csv
hbctl export --tag electronics --columns "name=Item,Manufacturer,Tare Weight (g)" --align left --empty "-" --sort purchase-price --format markdown
```

### Stats, Templates, Barcodes & Server Actions

```bash
hbctl stats                                                    # overview (defaults to overview subcommand)
hbctl stats --warranty-days 30 overview                        # NOTE: --warranty-days precedes subcommand
hbctl stats tags --output markdown                             # also: locations, entity-types, purchase-price
hbctl template [list|get|create|update|delete]
hbctl template apply <template_id> --name "USB-C Cable 2m" --location "Cable Drawer"
hbctl barcode 012345678905 --json
hbctl actions [ensure-asset-ids|create-missing-thumbnails]
```

### Labels, QR Codes, Backups, Notifiers & Config

```bash
hbctl label 000-001 --out label.png [--kind auto|item|asset|location] [--print]
hbctl qr <entity_id_or_asset_id> --out qr.png [--raw]
hbctl backup --out ./output/homebox-backup.tar.gz [--no-attachments] [--exclude-archived] [--overwrite]
hbctl notifier [list|create|update|delete|test]                # URLs redacted unless --reveal
hbctl config [show|profiles|use <name>]                        # secrets redacted as Bearer ***
```

### Maintenance Log

```bash
hbctl maintenance list [<entity_id>] [--status both|completed|scheduled] [--json]
hbctl maintenance create <entity_id> --name "<task>" [--completed-date YYYY-MM-DD] [--scheduled-date YYYY-MM-DD] [--cost 29.99] [--description "<notes>"]
hbctl maintenance update <entry_id> [--name "<task>"] [--completed-date YYYY-MM-DD] [--scheduled-date YYYY-MM-DD] [--cost 29.99] [--description "<notes>"]
hbctl maintenance delete <entry_id> --force [--dry-run]
```

### Raw API Requests

```bash
hbctl api GET status --json --select reachable,health,version
hbctl api GET groups/currency --json
hbctl api PUT groups -d '{"currency":"USD"}' --dry-run
printf '%s' '{"currency":"USD"}' | hbctl api PUT groups --from-json -
```

### Taskfile Equivalents

- `task homebox:status`
- `task homebox:api METHOD=<GET|POST|...> PATH='<path>' [DATA='<json>'] [DRY_RUN=1]`
- `task homebox:list`
- `task homebox:tree`
- `task homebox:path ID=<id>`
- `task homebox:move [ID=<id>|TAG=<tag>] PARENT='<parent>' [DRY_RUN=1]`
- `task homebox:get ID=<id> [WITH_PATH=1]`
- `task homebox:create DATA='<json>' [ATTACH='<path>']`
- `task homebox:update ID=<id> DATA='<json>' [FILL_MISSING=1]`
- `task homebox:duplicate ID=<id> [COUNT=2] [DRY_RUN=1]`
- `task homebox:delete [ID=<id>|TAG=<tag>] [DRY_RUN=1]`
- `task homebox:attach ID=<id> FILE='<path>' [PRIMARY=1]`
- `task homebox:attach-link ID=<id> URL='<url>' [TITLE='<title>'] [TYPE='<type>'] [DRY_RUN=1]`
- `task homebox:search QUERY='<query>'`
- `task homebox:entity-types`
- `task homebox:stats [VIEW=overview|tags|locations|entity-types|purchase-price] [WARRANTY_DAYS=30]`
- `task homebox:backup [OUT=output/homebox-backup.tar.gz] [NO_ATTACHMENTS=1] [EXCLUDE_ARCHIVED=1] [OVERWRITE=1] [DRY_RUN=1]`
- `task homebox:label ID=<id> [KIND=auto|item|asset|location] [OUT=label.png] [PRINT=1] [DRY_RUN=1]`
- `task homebox:qr ID=<id> [RAW=1] [OUT=qr.png] [DRY_RUN=1]`
- `task homebox:barcode CODE='<code>' [CREATE=1] [PARENT='<parent>'] [DRY_RUN=1]`
- `task homebox:template [APPLY=<template_id> NAME='<name>' LOCATION='<loc>' DRY_RUN=1]`
- `task homebox:actions ACTION=<ensure-asset-ids|create-missing-thumbnails> [DRY_RUN=1]`
- `task homebox:config`
- `task maintenance:list [TARGET='<slug|model|id>'] [STATUS=both|completed|scheduled]`
- `task maintenance:log TARGET='<slug|model|id>' NAME='<action>' [DATE=YYYY-MM] [PART='<part>'] [COST='<cost>']`
- `task maintenance:update ID='<entry_id>' [NAME='<action>'] [DATE=YYYY-MM] [COST='<cost>']`
- `task maintenance:delete ID='<entry_id>' [DRY_RUN=1]`

## Guidelines for Agents

- Always pass `--json --select id,name,...` or `-q` to keep output compact in agent context, or `--output csv|markdown` for formatted reports.
- Use native `hbctl` subcommands (`stats`, `backup`, `label`, `qr`, `template`, `barcode`, `actions`, `notifier`, `maintenance`, `config`) before falling back to `hbctl api`; `hbctl status` supports Homebox v0.27+.
- Asset IDs like `000-001` are auto-detected on `item`, `attachment`, `field`, `label`, and `qr` (or pass `--asset-id` explicitly).
- On `hbctl stats`, place `--warranty-days <N>` before the subcommand (`hbctl stats --warranty-days 30 overview`).
- Preview mutating calls with `--dry-run` (always redacts `Authorization: Bearer ***`).
- `hbctl item create` / `upsert` automatically handles Homebox's follow-up `PUT` for custom fields, `GET -> Merge -> PUT` updates, `--match-mode` (`exact|contains|fuzzy`), `--on-match` (`update|skip|attach-only`), `--attach FILE=REMOTE_NAME`, `--attach-url URL[=REMOTE_NAME]`, and `--attach-best-effort`.
- `--field-type number` accepts unit-tolerant values (e.g., `250g`, `490 grams`, `$19.99`).
- Project `.hbctl.toml` sets `auto_optimize = true` (`max_image_kb = 500`, `max_image_dimension = 1920`), so `hbctl` automatically resizes/compresses oversized images in memory on upload (or pass `--optimize` explicitly).
