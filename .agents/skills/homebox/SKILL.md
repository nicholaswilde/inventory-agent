---
name: homebox
description: Interacts with the Homebox API using the `hbx` CLI to list, get, create, update, upsert, search, export, and attach files to items/entities.
---

# Homebox Skill

Use the `hbx` CLI (`nicholaswilde/hbx`) for all direct Homebox v0.26+ REST API interactions.

## Requirements

1. **Binary**: `hbx` installed on `PATH` (Homebrew `nicholaswilde/homebrew-tap/hbx`, APT `nicholaswilde/apt`, Scoop, or `cargo install --git https://github.com/nicholaswilde/hbx`).
2. **Credentials**: Auto-loaded from local `.env` (`HOMEBOX_IP` / `HOMEBOX_URL` + `HOMEBOX_API_KEY`) or stored via `hbx auth login`.

## CLI Usage

### List & Search Entities

```bash
hbx item list --all --json --select id,name,quantity
hbx search "<query>" --json --select id,name
hbx search --manufacturer "Espressif" --json --select id,name,fields
```

### Get Entity

```bash
hbx item get <entity_id> --json --select id,name,quantity,fields
```

### Create & Upsert Entity

```bash
hbx item create --name "ESP32 DevKit" --manufacturer "Espressif" --field Voltage=3.3 --json
printf '%s' '{"name":"New Entity","manufacturer":"Acme"}' | hbx item create --from-json - --json
hbx item upsert --name "ESP32 DevKit" --tag electronics --field Pins=38 --field-type number
```

### Update Entity & Custom Fields

```bash
hbx item update <entity_id> --quantity 5 --notes "Shelf A"
printf '%s' '{"quantity":5}' | hbx item update <entity_id> --from-json -
hbx field get <entity_id> "Model Number" -q
hbx field set <entity_id> "Model Number" "12345"
```

### Delete Entity

```bash
hbx item delete <entity_id> --force
```

### Attachments

```bash
hbx attachment upload <entity_id> <file_path...>
hbx attachment list <entity_id> --json
hbx attachment download <entity_id> --all --ext pdf --out ./manuals
hbx attachment delete <entity_id> <attachment_id>
```

### Entity Types, Tags & Export

```bash
hbx entity-types
hbx tag list
hbx export --tag electronics --field Manufacturer --format markdown
```

## Guidelines for Agents

- Always pass `--json --select id,name,...` or `-q` to keep output compact in agent context.
- Preview mutating calls with `--dry-run` (always redacts `Authorization: Bearer ***`).
- `hbx item create` / `upsert` automatically handles Homebox's follow-up `PUT` for custom fields and `GET -> Merge -> PUT` updates.
