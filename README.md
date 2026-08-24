# Inventory Agent

[![task](https://img.shields.io/badge/Task-Enabled-brightgreen?style=for-the-badge&logo=task&logoColor=white)](https://taskfile.dev/#/)

Intelligent image and issue ingestion agent for [Homebox](https://homebox.software) inventory management.

> [!IMPORTANT]
> **Compatibility**: This repository only supports **Homebox v0.26.0+** (which uses the unified Entities API). Older versions using deprecated `/api/locations` and `/api/items` endpoints are not supported.

## :sparkles: Features

- **GitHub Issue Processing**: Ingest items from issues containing images or zip archives directly into Homebox, with OCR (`lit` + `tesseract`) and multimodal vision fallback.
- **Token-Optimized Extraction**: Streamlined issue and image extraction pipeline (`task issue:extract`) to minimize context token usage.
- **Local Image & Zip Processing**: Ingest local photos and zip files from `images/pending/` into Homebox and move them to `images/processed/`.
- **Homebox API Integration**: Helper scripts and Taskfile commands for CRUD operations, search filtering, and image attachments.

## :rocket: Usage

### :inbox_tray: Local Image Ingestion

1. Place images or `.zip` archives into `images/pending/`.
2. Run the processing task:
   ```bash
   task process-images
   ```
3. Processed files are automatically organized into `images/processed/`.

## :gear: Setup

1. Copy the example environment file and configure Homebox credentials:
   ```bash
   cp .env.example .env
   ```
2. Install Python test dependencies (using [`uv`](https://github.com/astral-sh/uv)):
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
sudo .venv/bin/pytest tests/
```

## :clipboard: Taskfile Commands

- `task test` — Run complete test suite (API, bash scripts, image pipeline).
- `task homebox:list` — List all Homebox entities.
- `task homebox:search QUERY='<name>'` — Search Homebox entities by name.
- `task homebox:get ID=<id>` — Get details for an entity.
- `task homebox:create DATA='<json>'` — Create a new entity.
- `task homebox:update ID=<id> DATA='<json>'` — Update an existing entity.
- `task homebox:delete ID=<id>` — Delete an entity by ID.
- `task homebox:attach ID=<id> FILE='<path>'` — Attach an image or file to an entity.
- `task homebox:entity-types` — List all Homebox entity types (useful for finding Location ID).
- `task issue:extract ISSUE=<id>` — Extract issue attachments and run quiet OCR.
- `task process-images` — Process pending local images and zip archives.

## :balance_scale: License

[Apache License 2.0](LICENSE)

## :writing_hand: Author

This project was started in 2026 by [Nicholas Wilde](https://github.com/nicholaswilde/).