---
name: tare-weight-manager
description: Upserts kitchen container weights into Homebox and generates a printable markdown reference sheet.
---

# Skill: Homebox Tare Weight Manager

## Description
Upserts kitchen container weights into Homebox and generates a printable markdown reference sheet.

## Instructions
When I feed you a container name and its weight via `agy`:

1. **Check Existing Inventory:**
  - Query the Homebox MCP server by item name to see if the container already exists in the database.
  
2. **Upsert the Item:**
  - **If it exists:** Trigger an update. Ensure the labels `kitchen`, `container`, and `tare-weight` are applied. Update or create the custom field `Tare Weight (g)` with the provided weight.
  - **If it doesn't exist:** Trigger a creation payload. Set the name, apply the labels `kitchen`, `container`, and `tare-weight`, and add the custom field `Tare Weight (g)`.
  - **Units:** Always treat the input weight as grams and store it strictly as an integer in the custom field.

3. **Generate the Reference Sheet:**
  - When I ask for the tare weight list or sheet, query Homebox to fetch all items tagged with the `tare-weight` label.
  - Format the output strictly as a Markdown table with the columns `Container / Item` and `Tare Weight (g)`.
  - Sort the table alphabetically by container name so it is easy to quickly scan on the fridge.
  - Output only the Markdown table without any conversational filler so I can pipe or copy it directly into a file.
