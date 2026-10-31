---
name: show-tare-weights
description: Shows a table in the console of kitchen containers and their tare weights from Homebox.
---

# Skill: Show Tare Weights Table

## Description
Displays an alphabetically sorted table of all tracked kitchen containers and their tare weights in the console.

## Instructions
When the user asks to view, show, list, or display kitchen containers, tare weights, or the container weight table in the console:

1. **Query and Generate Table:**
  - Execute `task tare:show` (or `task tare:sheet` / `uv run scripts/tare_weight_manager.py show`), or query Homebox items tagged with `tare-weight`.
  - Format the table with columns `Container / Item` and `Tare Weight (g)`.
  - Ensure items are sorted alphabetically by container name.

2. **Display in Console:**
  - Print the clean Markdown table directly into the console output.
  - Do not wrap in unnecessary chatter; keep the focus on the container weights for quick reference.
