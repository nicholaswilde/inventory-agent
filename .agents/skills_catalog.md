# Agent Skills Catalog

Catalog of custom Antigravity agent skills available in `inventory-agent`.

| Skill | Description | Task / Command |
|---|---|---|
| [`appliance-lookup`](skills/appliance-lookup/SKILL.md) | Query appliance specs, error codes, schematics, and BOM parts | `task appliance:info TARGET="<model>"` |
| [`batch-import`](skills/batch-import/SKILL.md) | Batch import items from URLs, ASINs, text files, or Amazon CSVs | `task batch:import ITEMS="..."` |
| [`homebox`](skills/homebox/SKILL.md) | Direct Homebox API client script interactions | `./scripts/homebox.sh <subcommand>` |
| [`homebox-dedup`](skills/homebox-dedup/SKILL.md) | Detect, delete, or merge duplicate Homebox entities | `task homebox:dedup` |
| [`import-amazon-invoice`](skills/import-amazon-invoice/SKILL.md) | Import products and order dates from Amazon PDF invoices | `task invoice:import FILE="<path>"` |
| [`ingest-manual`](skills/ingest-manual/SKILL.md) | Ingest appliance manuals (PDF/URL/Issue) and generate cheat sheets | `task manual:ingest FILE="<path>"` |
| [`issue-to-homebox`](skills/issue-to-homebox/SKILL.md) | Ingest components from GitHub issues with images/zips | `/issue-to-homebox <number>` |
| [`optimize-images`](skills/optimize-images/SKILL.md) | Resize and compress images (< 500KB, max 1920x1080) | `task image:optimize` |
| [`print-local`](skills/print-local/SKILL.md) | Print markdown lists or PDFs to local Brother printer | `task print:brother TEXT="..."` |
| [`process-local-images`](skills/process-local-images/SKILL.md) | Process images and zips from `images/pending/` | `task process-vision` |
| [`pull-appliance-manuals`](skills/pull-appliance-manuals/SKILL.md) | Pull appliance PDF manuals from Homebox to `manuals/` | `task manuals:pull` |
| [`show-tare-weights`](skills/show-tare-weights/SKILL.md) | Display console table of kitchen container tare weights | `task tare:show` |
| [`tare-weight-manager`](skills/tare-weight-manager/SKILL.md) | Manage kitchen container tare weights and PDF sheet | `task tare:sheet` / `task tare:pdf` |
| [`upload-appliance-diagrams`](skills/upload-appliance-diagrams/SKILL.md) | Upload exploded diagrams to Homebox entities | `task diagrams:upload` |
| [`url-to-homebox`](skills/url-to-homebox/SKILL.md) | Import items from product URLs or Amazon ASINs | `task url:import URL="<url>"` |
