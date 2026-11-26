---
name: homebox
description: Interacts with the Homebox API using the `hbctl` CLI to list, get, create, update, upsert, search, export, and attach files to items/entities.
---

# Homebox Skill

Use the `hbctl` CLI (`nicholaswilde/hbctl`) for all direct Homebox v0.26+ REST API interactions.

## Requirements

1. **Binary**: `hbctl` installed on `PATH` (Homebrew `nicholaswilde/homebrew-tap/hbctl`, APT `nicholaswilde/apt`, Scoop, or `cargo install --git https://github.com/nicholaswilde/hbctl`).
2. **Credentials**: Auto-loaded from local `.env` (`HOMEBOX_IP` / `HOMEBOX_URL` + `HOMEBOX_API_KEY`) or stored via `hbctl auth login`.

## CLI Usage

### List, Tree & Search Entities

```bash
hbctl status
hbctl item list --all --json --select id,name,quantity
hbctl item tree [--root "<location>"] [--max-depth 2]
hbctl search "<query>" --json --select id,name
hbctl search --manufacturer "Espressif" --field Voltage=3.3 --json --select id,name,fields
```

### Get & Move Entity

```bash
hbctl item get <entity_id> --json --select id,name,quantity,fields
hbctl item move <entity_id> "<parent_name_or_id>"   # or 'none' to unparent
```

### Create & Upsert Entity

```bash
hbctl item create --name "ESP32 DevKit" --manufacturer "Espressif" --parent "Lab Bin" --field Voltage=3.3 --attach photo.jpg --json
printf '%s' '{"name":"New Entity","manufacturer":"Acme"}' | hbctl item create --from-json - --attach photo.jpg --json
hbctl item upsert --name "ESP32 DevKit" --tag electronics --field Pins=38 --field-type number --match-by model --match-by name --fill-missing
printf '%s' '{"name":"ESP32 DevKit","modelNumber":"ESP32"}' | hbctl item upsert --from-json - --match-by model --fill-missing --attach photo.jpg --json
```

### Update Entity & Custom Fields

```bash
hbctl item update <entity_id> --quantity 5 --notes "Shelf A" --add-tag verified
hbctl item update <entity_id> --remove-tag pending --fill-missing
printf '%s' '{"quantity":5}' | hbctl item update <entity_id> --from-json - --fill-missing
hbctl field list <entity_id> --json
hbctl field get <entity_id> "Model Number" -q
hbctl field set <entity_id> "Model Number" "12345"
hbctl field delete <entity_id> "Obsolete Field"
```

### Delete Entity

```bash
hbctl item delete <entity_id> --force
```

### Attachments

```bash
hbctl attachment upload <entity_id> <file_path...> [--name <remote_name>]
printf '%s' "<bytes>" | hbctl attachment upload --name <remote_name> <entity_id> -
hbctl attachment list <entity_id> --json
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
hbctl export --tag electronics --columns "name=Item,Manufacturer,Tare Weight (g)" --align left --empty "-" --format markdown
```

### Taskfile Equivalents

- `task homebox:status`
- `task homebox:list`
- `task homebox:tree`
- `task homebox:move ID=<id> PARENT='<parent>'`
- `task homebox:get ID=<id>`
- `task homebox:create DATA='<json>' [ATTACH='<path>']`
- `task homebox:update ID=<id> DATA='<json>' [FILL_MISSING=1]`
- `task homebox:delete ID=<id>`
- `task homebox:attach ID=<id> FILE='<path>'`
- `task homebox:search QUERY='<query>'`
- `task homebox:entity-types`

## Guidelines for Agents

- Always pass `--json --select id,name,...` or `-q` to keep output compact in agent context.
- Preview mutating calls with `--dry-run` (always redacts `Authorization: Bearer ***`).
- `hbctl item create` / `upsert` automatically handles Homebox's follow-up `PUT` for custom fields and `GET -> Merge -> PUT` updates.
- Optimize local photos with `task image:optimize TARGET="<path>"` (< 500KB, max 1920x1080) before `hbctl attachment upload`.
