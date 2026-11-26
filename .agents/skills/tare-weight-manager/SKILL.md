---
name: tare-weight-manager
description: Upserts kitchen container weights into Homebox and generates a printable markdown reference sheet.
---

# Skill: Homebox Tare Weight Manager

## Description
Upserts kitchen container weights into Homebox and generates a printable markdown reference sheet.

## Instructions
When I feed you a container name and its weight via `agy`:

1. **Upsert the Item:**
  - Run `task tare:upsert NAME="<container>" WEIGHT="<grams>"` (or `uv run scripts/tare_weight_manager.py upsert "<container>" <grams>`).
  - **Behavior:** Checks existing inventory via Homebox API; if found, updates it, else creates it. Applies labels `kitchen`, `container`, and `tare-weight`, and stores custom field `Tare Weight (g)` strictly as an integer in grams.

2. **Generate the Reference Sheet / Console Table:**
  - Run `task tare:sheet` (aliases `task tare:show`, `task tare:table`) — executes `hbctl export --tag tare-weight --format markdown --columns "name=Container / Item,Tare Weight (g)" --align left --empty "-" --sort name` directly (or `uv run scripts/tare_weight_manager.py sheet`).
  - Queries all Homebox items tagged `tare-weight`, formats an alphabetically sorted Markdown table with columns `Container / Item` and `Tare Weight (g)`, and prints without conversational filler.

3. **Generate Printable PDF & LAN Preview:**
  - Run `task tare:pdf` (supports `PAPER=card`, `FONT_SIZE=6pt`) to render `output/tare_weights.pdf` (or `output/tare_weights_card.pdf`).
  - Run `task tare:serve` to generate the PDF and serve it on the LAN.
