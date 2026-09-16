---
name: upload-appliance-diagrams
description: Uploads appliance assembly schematics and exploded diagram images to Homebox entities.
---

# Upload Appliance Diagrams Skill

Uploads appliance exploded diagrams and assembly schematics cataloged in `appliances/<MODEL>/diagrams/` to their corresponding Homebox entities as attachments.

## Script

`scripts/upload_appliance_diagrams.py`

## Guidelines

1. **Trigger**:
   - Use whenever user asks to upload, sync, or attach appliance schematics/diagrams to Homebox.
2. **Execution**:
   - Upload all cataloged diagrams to matching Homebox entities:
     ```bash
     task diagrams:upload
     # or direct script:
     uv run scripts/upload_appliance_diagrams.py
     ```
   - Preview uploads without modifying Homebox (dry run):
     ```bash
     task diagrams:upload -- --dry-run
     ```
   - Upload for a specific Homebox entity ID:
     ```bash
     uv run scripts/upload_appliance_diagrams.py --entity-id <ENTITY_ID>
     ```
   - Force re-upload / overwrite existing attachments with identical filenames:
     ```bash
     task diagrams:upload -- --overwrite
     ```
3. **Entity Resolution**:
   - Resolves entity IDs from `appliances/*.md` cheat sheets.
   - Maps to diagrams via `[...](<MODEL>/bill_of_materials.md)` or folder name matching in the cheat sheet text.
