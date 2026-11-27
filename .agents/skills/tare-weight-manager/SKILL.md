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
  - Run `task tare:upsert NAME="<container>" WEIGHT="<grams>"` (or directly `hbctl item upsert --name "<container>" --tag kitchen --tag container --tag tare-weight --field "Tare Weight (g)=<grams>" --field-type number`).
  - **Behavior:** Checks existing inventory via `hbctl item upsert`; if found, updates it, else creates it. Applies tags `kitchen`, `container`, and `tare-weight`, and stores custom field `Tare Weight (g)` via unit-tolerant `--field-type number` (accepts `250` or `250g`).

2. **Generate the Reference Sheet / Console Table:**
  - Run `task tare:sheet` (aliases `task tare:show`, `task tare:table`) — executes `hbctl export --tag tare-weight --format markdown --columns "name=Container / Item,Tare Weight (g)" --align left --empty "-" --sort name` directly.
  - Queries all Homebox items tagged `tare-weight`, formats an alphabetically sorted Markdown table with columns `Container / Item` and `Tare Weight (g)`, and prints without conversational filler.

3. **Generate Printable PDF & LAN Preview:**
  - Run `task tare:pdf` (supports `PAPER=card`, `FONT_SIZE=6pt`) to render `output/tare_weights.pdf` (or `output/tare_weights_card.pdf`).
  - Run `task tare:serve` to generate the PDF and serve it on the LAN.
