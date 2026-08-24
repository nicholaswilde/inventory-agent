# Inventory Agent

[![task](https://img.shields.io/badge/Task-Enabled-brightgreen?style=for-the-badge&logo=task&logoColor=white)](https://taskfile.dev/#/)

Intelligent image and issue ingestion agent for Homebox inventory management.

## Features

- **GitHub Issue Processing**: Ingest items from issues containing images or zip archives directly into Homebox, with OCR (`lit` + `tesseract`) and multimodal vision fallback.
- **Local Image & Zip Processing**: Ingest local photos and zip files from `images/pending/` into Homebox and move them to `images/processed/`.
- **Homebox API Integration**: Helper scripts and Taskfile commands for CRUD operations and image attachments.

## Usage

### Local Image Ingestion

1. Place images or `.zip` archives into `images/pending/`.
2. Run the processing task:
   ```bash
   task process-images
   ```
3. Processed files are automatically organized into `images/processed/`.

### Taskfile Commands

- `task homebox:list` — List all Homebox entities.
- `task homebox:get ID=<id>` — Get details for an entity.
- `task homebox:create DATA='<json>'` — Create a new entity.
- `task homebox:update ID=<id> DATA='<json>'` — Update an existing entity.
- `task homebox:attach ID=<id> FILE='<path>'` — Attach an image or file to an entity.
- `task process-images` — Process pending local images and zip archives.

## :balance_scale: License

[Apache License 2.0](LICENSE)

## :writing_hand: Author

This project was started in 2026 by [Nicholas Wilde](https://github.com/nicholaswilde/).