# Homebox & Ingestion Pipeline Rules

## Homebox API Connection
- **Credentials**: Source `HOMEBOX_IP` and `HOMEBOX_API_KEY` from local `.env`. Never commit `.env` or log keys.
- **Port**: 7745 (`http://$HOMEBOX_IP:7745`).
- **Auth Header**: Bearer token: `-H "Authorization: Bearer $HOMEBOX_API_KEY"`.
- **JSON Filtering**: Always filter Homebox API responses with `jq` to specific fields. Keep raw uncompressed payloads out of model context.

## Image Optimization & Compression
- **Limit**: Web-friendly images (< 500KB, max 1920x1080 resolution) before uploading/attaching to Homebox entities.
- **Task**: Run `task image:optimize` (or `task image:optimize TARGET="<path>"`). Preview with `DRY_RUN=1`.
- **Metadata**: Strips EXIF to protect location privacy and prevent database bloat.

## Document & Image OCR Workflow
1. **Documents (PDF, DOCX, XLSX)**: Extract text with `lit parse -q --no-ocr <file>` first. Fall back to `lit parse -q <file>` if scanned. Fall back to `pdftotext` for digital PDFs.
2. **Images**: Run `lit parse -q <image>`, fall back to `tesseract`.
3. **Multimodal Fallback**: Inspect component visually with vision capabilities when OCR text is insufficient.

## Appliance Manual Ingestion
1. **Trigger**: Process issues/manuals via `task manual:ingest-issue ISSUE=<number>` or `task manual:ingest FILE="<path_or_url>"`.
2. **Artifacts**:
   - Cheat sheet in `appliances/<slug>.md`.
   - Processed manual in `images/processed/<Slug>_Manual.pdf`.
   - Homebox entity with specs, model, error codes, and manual attachment.
3. **Lookup**: Query `appliances/<slug>.md` first before reading full PDF manual.

## Script TDD Workflow
- Always create a test first when adding a new script (`tests/test_<name>.py`).
- Always modify corresponding test first before editing an existing script.
- Verify tests pass with `uv run pytest`.
