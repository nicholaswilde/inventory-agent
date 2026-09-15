---
name: ingest-manual
description: Ingests appliance manuals (PDF or URL) into Homebox as inventory entities with attached manuals and generates quick-lookup markdown cheat sheets.
---

# Ingest Appliance Manual

Ingests appliance user and service manuals from local PDF files or URLs (Google Drive / web links), registers them in Homebox with attached PDF documents, and generates lightweight markdown cheat sheets in `appliances/` for rapid agent lookup.

## Guidelines

1. **Ingestion Trigger**:
   - Use whenever user provides a user manual, installation manual, or service guide for a home appliance (dryer, washer, oven, dishwasher, etc.) via local path or URL.
2. **Execution**:
   - Preview extraction with dry-run:
     ```bash
     task manual:ingest FILE="<path_or_url>" DRY_RUN=1
     ```
   - Ingest and upload to Homebox:
     ```bash
     task manual:ingest FILE="<path_or_url>"
     ```
3. **Artifacts Produced**:
   - **Processed Manual**: Saved to `images/processed/<Slug>_Manual.pdf` (gitignored to prevent repository bloat).
   - **Homebox Entity**: Created with model, manufacturer, capacity, specs, and uploaded PDF attachment.
   - **Quick Lookup Cheat Sheet**: Saved to `appliances/<slug>.md` containing specs, error codes, part numbers, and maintenance tips.
4. **Appliance Information Lookup**:
   - For fast lookups (error codes, specs, dimensions, replacement parts), read `appliances/<slug>.md` first.
   - Only retrieve/parse the full PDF manual when deep schematic or obscure troubleshooting details are not present in the cheat sheet.
