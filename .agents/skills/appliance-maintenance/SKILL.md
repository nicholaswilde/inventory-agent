---
name: appliance-maintenance
description: Lists, logs, and deletes appliance maintenance records in Homebox and `appliances/<slug>.md` via `task maintenance:*` and `scripts/appliance_maintenance.py`.
---

# Appliance Maintenance Skill

Manage completed and scheduled appliance maintenance in both Homebox's native Maintenance Log (`/api/v1/entities/{id}/maintenance`, `/api/v1/maintenance`) and local `appliances/<slug>.md` (`## Maintenance History`).

## Script

`scripts/appliance_maintenance.py`

## Taskfile Usage

### 1. List Maintenance Entries
```bash
task maintenance:list
task maintenance:list TARGET="ge-double-wall-oven"
task maintenance:list STATUS="completed"
```

### 2. Log Maintenance Entry
Logs to both Homebox and `appliances/<slug>.md` in reverse-chronological order:
```bash
task maintenance:log TARGET="ge-double-wall-oven" NAME="Replaced relay daughter board" DATE="2026-11" PART="WB27X25594"
task maintenance:log TARGET="ge-double-wall-oven" NAME="Replaced cooling fan" DATE="2024-02" DISPLAY_DATE="2024-02 (approx.)" PART="WB26X35088" COST="$45.00" NOTES="Lower cooling fan motor"
# Preview without mutating Homebox or local markdown:
task maintenance:log TARGET="ge-double-wall-oven" NAME="Inspect gasket" DATE="2026-11" DRY_RUN=1
```

### 3. Delete Maintenance Entry
```bash
task maintenance:delete ID="<entry_uuid>" DRY_RUN=1
task maintenance:delete ID="<entry_uuid>"
```

## Direct CLI Options
```bash
uv run scripts/appliance_maintenance.py list [target] [--status both|completed|scheduled] [--json]
uv run scripts/appliance_maintenance.py log <target> --name "..." [--date YYYY-MM|YYYY-MM-DD] [--scheduled YYYY-MM|YYYY-MM-DD] [--display-date "..."] [--part "..."] [--cost "..."] [--notes "..."] [--homebox-only | --local-only] [--dry-run] [--json]
uv run scripts/appliance_maintenance.py delete <entry_id> [--dry-run] [--json]
```
