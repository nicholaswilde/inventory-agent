---
name: pull-appliance-manuals
description: Pulls appliance PDF manuals from Homebox and stores them in the local manuals/ directory.
---

# Pull Appliance Manuals Skill

Pulls appliance user manuals, installation guides, and service documents from Homebox entities and stores them locally in `manuals/` for offline inspection and deep troubleshooting.

## Script

`scripts/pull_appliance_manuals.py`

## Guidelines

1. **Trigger**:
   - Use whenever user asks to download, pull, sync, or fetch appliance manuals locally from Homebox.
2. **Execution**:
   - Download all manuals cataloged in `appliances/*.md`:
     ```bash
     task manuals:pull
     # or direct script:
     uv run scripts/pull_appliance_manuals.py
     ```
   - Preview download without saving files (dry run):
     ```bash
     task manuals:pull -- --dry-run
     ```
   - Download for a specific Homebox entity ID:
     ```bash
     uv run scripts/pull_appliance_manuals.py --entity-id <ENTITY_ID>
     ```
   - Scan all entities in Homebox for PDF attachments (not just appliances cataloged in `appliances/`):
     ```bash
     uv run scripts/pull_appliance_manuals.py --scan-all
     ```
   - Force re-download / overwrite existing local files:
     ```bash
     task manuals:pull -- --overwrite
     ```
3. **Storage & Repository Hygiene**:
   - PDFs are saved to `manuals/<Filename>.pdf`.
   - `manuals/*.pdf` is gitignored to avoid repository bloat. `manuals/.gitkeep` maintains directory presence.
