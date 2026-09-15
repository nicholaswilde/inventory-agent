---
name: appliance-lookup
description: Queries and retrieves appliance specifications, troubleshooting error codes, schematic diagrams, and cataloged bills of materials (BOM) replacement parts.
---

# Appliance Lookup Skill

Fast retrieval of home appliance specifications, diagnostic error codes, parts catalogs, and exploded assembly schematics from the local `appliances/` repository.

## Script

`scripts/query_appliance.py`

## Usage

### 1. List All Cataloged Appliances
```bash
task appliance:list
# or direct script:
uv run scripts/query_appliance.py list
```

### 2. Get Appliance Specifications & Details
Look up an appliance by name, slug (`lg-dryer`), model number (`DLGX7801WE`), or Homebox ID:
```bash
task appliance:info TARGET="lg-dryer"
task appliance:info TARGET="SHXM98W75N"
# JSON format:
task appliance:info TARGET="lg-dryer" CLI_ARGS="--json"
```

### 3. Unified Search Across All Catalogs
Search across appliance names, specs, error codes, and replacement parts:
```bash
task appliance:search QUERY="compressor"
task appliance:search QUERY="drain"
```

### 4. Search Replacement Parts & Assembly Diagrams
Find part numbers, callouts, descriptions, prices, and schematic diagram references across all cataloged BOMs:
```bash
# Search all appliances
task appliance:part QUERY="valve"

# Filter to a specific appliance model
task appliance:part QUERY="valve" CLI_ARGS="--model DLGX7801WE"

# Filter with JSON output for jq processing
uv run scripts/query_appliance.py part valve --json
```

### 5. Search Diagnostic Error Codes
Search troubleshooting error codes, failure symptoms, and recommended actions:
```bash
task appliance:error QUERY="IE"
task appliance:error QUERY="unbalanced"
```

## Data Sources in `appliances/`

- **Markdown Cheat Sheets**: `appliances/<slug>.md` (specs, capacity, weight, error code tables, accessory numbers, and Homebox entity links).
- **Bills of Materials (BOM)**: `appliances/<MODEL>/bill_of_materials.md` (and `.json` / `.csv`) cataloging every assembly component, callout tag, part number, description, price, and stock status.
- **Assembly Schematics**: `appliances/<MODEL>/diagrams/` containing high-resolution exploded view diagrams referenced by callouts in the BOM.

## Guidelines for Agents

1. **Fast Lookups**: Always run `task appliance:info` or `task appliance:part` before reading large files into context.
2. **Schematic Cross-Referencing**: When locating a part, provide the user with the callout number, part number, price, and the diagram filename in `appliances/<MODEL>/diagrams/`.
3. **JSON Output**: When parsing programmatically in subagents, pass `--json` to receive structured objects without table formatting.
