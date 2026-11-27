---
name: appliance-maintenance
description: Lists, logs, updates, and deletes appliance maintenance records in Homebox (via `hbctl maintenance`) and `appliances/<slug>.md` via `task maintenance:*` and `scripts/appliance_maintenance.py`.
---

# Appliance Maintenance Skill

Manage completed and scheduled appliance maintenance in both Homebox's native Maintenance Log (`hbctl maintenance`) and local `appliances/<slug>.md` (`## Maintenance History`).

## Script

`scripts/appliance_maintenance.py` wraps `hbctl maintenance` (via `scripts/hbctl_client.py`) to resolve appliance slugs/models to Homebox IDs and dual-write `appliances/<slug>.md`.

## Taskfile Usage

### 1. List Maintenance Entries
`task maintenance:list` without `TARGET` runs `hbctl maintenance list` directly; with `TARGET` it resolves local slug/model via `scripts/appliance_maintenance.py`:
```bash
task maintenance:list
task maintenance:list TARGET="ge-double-wall-oven"
task maintenance:list STATUS="completed"
```

### 2. Log Maintenance Entry
Logs to both Homebox (`hbctl maintenance create`) and `appliances/<slug>.md` in reverse-chronological order:
```bash
task maintenance:log TARGET="ge-double-wall-oven" NAME="Replaced relay daughter board" DATE="2026-11" PART="WB27X25594"
task maintenance:log TARGET="ge-double-wall-oven" NAME="Replaced cooling fan" DATE="2024-02" DISPLAY_DATE="2024-02 (approx.)" PART="WB26X35088" COST="$45.00" NOTES="Lower cooling fan motor"
# Preview without mutating Homebox or local markdown:
task maintenance:log TARGET="ge-double-wall-oven" NAME="Inspect gasket" DATE="2026-11" DRY_RUN=1
```

### 3. Update Maintenance Entry
Wraps `hbctl maintenance update` directly:
```bash
task maintenance:update ID="<entry_uuid>" NAME="Updated title" COST="$45.00" DRY_RUN=1
task maintenance:update ID="<entry_uuid>" DATE="2026-11-27" NOTES="Verified post-repair"
```

### 4. Delete Maintenance Entry
Wraps `hbctl maintenance delete` directly:
```bash
task maintenance:delete ID="<entry_uuid>" DRY_RUN=1
task maintenance:delete ID="<entry_uuid>"
```

## Direct hbctl Commands
```bash
hbctl maintenance list [<entity_id>] [--status both|completed|scheduled] [--json]
hbctl maintenance create <entity_id> --name "..." [--completed-date YYYY-MM|YYYY-MM-DD] [--scheduled-date YYYY-MM|YYYY-MM-DD] [--cost "..."] [--description "..."] [--dry-run] [--json]
hbctl maintenance update <entry_id> [--name "..."] [--completed-date YYYY-MM|YYYY-MM-DD] [--scheduled-date YYYY-MM|YYYY-MM-DD] [--cost "..."] [--description "..."] [--dry-run] [--json]
hbctl maintenance delete <entry_id> --force [--dry-run] [--json]
```

## Direct CLI Options
```bash
uv run scripts/appliance_maintenance.py list [target] [--status both|completed|scheduled] [--json]
uv run scripts/appliance_maintenance.py log <target> --name "..." [--date YYYY-MM|YYYY-MM-DD] [--scheduled YYYY-MM|YYYY-MM-DD] [--display-date "..."] [--part "..."] [--cost "..."] [--notes "..."] [--homebox-only | --local-only] [--dry-run] [--json]
uv run scripts/appliance_maintenance.py delete <entry_id> [--dry-run] [--json]
```
