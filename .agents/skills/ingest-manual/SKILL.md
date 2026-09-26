---
name: ingest-manual
description: Ingests appliance manuals (PDF, URL, or GitHub issue) into Homebox as inventory entities with attached manuals and generates quick-lookup markdown cheat sheets.
---

# Ingest Appliance Manual

Ingests appliance user and service manuals from local PDF files, URLs (Google Drive / web links), or GitHub issues (issues with attached PDF manuals or appliance titles), registers them in Homebox with attached PDF documents, and generates lightweight markdown cheat sheets in `appliances/` for rapid agent lookup.

## Guidelines

1. **Ingestion Trigger**:
   - Use whenever user provides a user manual, installation manual, or service guide for a home appliance (dryer, washer, oven, dishwasher, laminator, etc.) via local path, URL, or GitHub issue reference (e.g. `issue #6`).
2. **Execution**:
   - **From GitHub Issue**:
     ```bash
     # Preview extraction
     task manual:ingest-issue ISSUE="<issue_number>" DRY_RUN=1
     # Ingest and upload to Homebox
     task manual:ingest-issue ISSUE="<issue_number>"
     ```
   - **From File or URL**:
     ```bash
     # Preview extraction with dry-run
     task manual:ingest FILE="<path_or_url>" DRY_RUN=1
     # Ingest and upload to Homebox
     task manual:ingest FILE="<path_or_url>"
     ```
3. **GitHub Issue Workflow**:
   - If issue contains a PDF manual attachment (e.g. `https://github.com/user-attachments/files/.../*.pdf`), `task manual:ingest-issue ISSUE=<number>` automatically parses, downloads, extracts, and uploads the manual.
   - If issue contains only an appliance name without an attachment, search online for the official manual PDF, then run `task manual:ingest FILE="<url>"`.
   - After completing ingestion and verification, commit changes with `fixes #<issue_number>` to close the issue automatically upon push.
4. **Artifacts Produced**:
   - **Processed Manual**: Saved to `images/processed/<Slug>_Manual.pdf` (gitignored to prevent repository bloat).
   - **Homebox Entity**: Created with model, manufacturer, capacity, specs, and uploaded PDF attachment.
   - **Quick Lookup Cheat Sheet**: Saved to `appliances/<slug>.md` containing specs, error codes, part numbers, and maintenance tips.
5. **Appliance Information Lookup**:
   - For fast lookups (error codes, specs, dimensions, replacement parts), read `appliances/<slug>.md` first.
   - Only retrieve/parse the full PDF manual when deep schematic or obscure troubleshooting details are not present in the cheat sheet.
6. **Document Parsing & Text Extraction**:
   - Extract text using `lit parse -q --no-ocr <path>` first for rapid direct digital text extraction.
   - If the document is scanned, image-based, or returns empty text, fall back to `lit`'s built-in OCR with `lit parse -q <path>`.
