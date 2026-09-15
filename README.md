# Inventory Agent

[![task](https://img.shields.io/badge/Task-Enabled-brightgreen?style=for-the-badge&logo=task&logoColor=white)](https://taskfile.dev/#/)

Intelligent image and issue ingestion agent for [Homebox](https://homebox.software) inventory management.

> [!IMPORTANT]
> **Compatibility**: This repository only supports **Homebox v0.26.0+** (which uses the unified Entities API). Older versions using deprecated `/api/locations` and `/api/items` endpoints are not supported.

## :sparkles: Features

- **GitHub Issue Processing**: Ingest items from issues containing images or zip archives directly into Homebox, with OCR (`lit` + `tesseract`) and multimodal vision fallback.
- **Token-Optimized Extraction**: Streamlined issue and image extraction pipeline (`task issue:extract`) to minimize context token usage.
- **Local Image & Zip Processing**: Ingest local photos and zip files from `images/pending/` into Homebox and move them to `images/processed/`.
- **Duplicate Management**: Detect, merge, and clean up duplicate Homebox entities using fuzzy text matching.
- **Homebox API Integration**: Helper scripts and Taskfile commands for CRUD operations, search filtering, and image attachments.
- **Appliance Manual Ingestion**: Parse PDF manuals from URL or local disk, create Homebox entities with attached manuals, and generate markdown lookup cheat sheets.
- **Product URL Ingestion**: Scrape product metadata, model numbers, prices, and images from Amazon and retail URLs and create Homebox entities with deduplication.
- **Appliance Parts & Diagram Cataloging**: Download high-resolution exploded view assembly diagrams and generate complete bills of materials (parts, callout tags, descriptions, pricing, stock status) in Markdown, CSV, and JSON formats for GE, Bosch, LG, and RepairClinic portals.

## :rocket: Usage

### :inbox_tray: Local Image Ingestion

1. Place images or `.zip` archives into `images/pending/`.
2. Run the processing task:
   ```bash
   task process-vision
   ```
3. Processed files are automatically organized into `images/processed/`.

### :link: Product URL Ingestion

Import an item from an Amazon or product URL into Homebox with extracted metadata, price, and product image attachment:
```bash
task url:import URL="<product_url>"
```
Preview extracted data without writing to Homebox:
```bash
task url:import URL="<product_url>" DRY_RUN=1
```

### :page_facing_up: Appliance Manual Ingestion

Ingest a user manual (PDF path or URL) into Homebox and generate a cheat sheet in `appliances/`:
```bash
task manual:ingest FILE="<pdf_path_or_url>"
```
Preview without creating Homebox entities:
```bash
task manual:ingest FILE="<pdf_path_or_url>" DRY_RUN=1
```

### :wrench: Appliance Parts & Assembly Diagrams

Download high-resolution schematics and catalog complete bills of materials (`bill_of_materials.md`, `bill_of_materials.csv`, `bill_of_materials.json`) into `appliances/<MODEL>/`:

```bash
# GE Appliances (GE Appliance Parts portal)
task parts:download TARGET="https://www.geapplianceparts.com/store/parts/assembly/<MODEL>"

# Bosch Appliances (Bosch Home spare parts list)
task parts:bosch TARGET="https://www.bosch-home.com/us/en/spare-parts-list/<MODEL>"

# LG Appliances (LGParts exploded view assembly)
task parts:lg TARGET="https://lgparts.com/pages/exploded-view-assembly?mfg=ZEN&parentId=<ID>&assemblyId=<ID>&ariId=<ID>"

# RepairClinic Portal (interactive diagrams and parts)
task parts:repairclinic TARGET="https://www.repairclinic.com/ProductDetail/<ID>?tab=diagrams"
```

## :gear: Setup

1. Install system prerequisites (`jq`, `curl`, `tesseract-ocr`):
   ```bash
   # Debian / Ubuntu
   sudo apt-get install jq curl tesseract-ocr
   ```
2. Initialize `.env` and configure Homebox credentials and Gemini API:
   ```bash
   task init
   # Edit .env to set HOMEBOX_IP, HOMEBOX_API_KEY, and GEMINI_API_KEY
   ```
3. Install Python test dependencies (using [`uv`](https://github.com/astral-sh/uv)):
   ```bash
   uv sync
   ```

## :test_tube: Testing

Run full test suite (spins up Docker container for Homebox integration tests, verifies scripts and OCR extraction pipeline):

```bash
task test
```

Or run directly via pytest:
```bash
uv run pytest tests/
```

## :clipboard: Taskfile Commands

- `task init` — Copy `.env.example` to `.env`.
- `task encrypt` — Encrypt `.env` to `.env.enc` using SOPS.
- `task decrypt` — Decrypt `.env.enc` to `.env` using SOPS.
- `task test` — Run complete test suite (API, bash scripts, image pipeline).
- `task homebox:list` — List all Homebox entities.
- `task homebox:search QUERY='<name>'` — Search Homebox entities by name.
- `task homebox:get ID=<id>` — Get details for an entity.
- `task homebox:create DATA='<json>'` — Create a new entity.
- `task homebox:update ID=<id> DATA='<json>'` — Update an existing entity.
- `task homebox:delete ID=<id>` — Delete an entity by ID.
- `task homebox:attach ID=<id> FILE='<path>'` — Attach an image or file to an entity.
- `task homebox:dedup` — Detect and report duplicate Homebox entities.
- `task homebox:dedup-delete` — Delete duplicate entities (preview with `DRY_RUN=1`).
- `task homebox:dedup-merge` — Merge quantities and delete duplicates (preview with `DRY_RUN=1`).
- `task homebox:entity-types` — List all Homebox entity types (useful for finding Location ID).
- `task issue:extract ISSUE=<id>` — Extract issue attachments and run quiet OCR.
- `task process-vision` — Process pending local images and zip archives.
- `task manual:ingest FILE='<path_or_url>'` — Ingest appliance manual into Homebox and generate cheat sheet (preview with `DRY_RUN=1`).
- `task url:import URL='<product_url>'` — Import item from product URL into Homebox with image and price (preview with `DRY_RUN=1`).
- `task parts:download TARGET='<url_or_model>'` — Download GE appliance assembly diagrams and bill of materials.
- `task parts:bosch TARGET='<url_or_variant>'` — Download Bosch appliance spare parts assembly diagrams and bill of materials.
- `task parts:lg TARGET='<url_or_parentId>'` — Download LG appliance spare parts assembly diagrams and bill of materials.
- `task parts:repairclinic TARGET='<url_or_id>'` — Download RepairClinic appliance assembly diagrams and bill of materials.

## :balance_scale: License

[Apache License 2.0](LICENSE)

## :writing_hand: Author

This project was started in 2026 by [Nicholas Wilde](https://github.com/nicholaswilde/).