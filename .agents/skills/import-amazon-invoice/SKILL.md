---
name: import-amazon-invoice
description: Imports products and purchase details from Amazon PDF invoices into Homebox, checking for existing items to fill in missing details and creating new items if not found.
---

# Import Amazon Invoice Skill

Ingests Amazon PDF invoices from local files or URLs (e.g. Google Drive / web downloads), extracts purchase details and product line items using `lit` (with built-in OCR fallback), checks Homebox for existing items to fill in missing purchase metadata, creates any missing items, and attaches the invoice PDF to all relevant entities.

## Guidelines

1. **Trigger**:
   - Use whenever the user provides an Amazon invoice PDF, receipt, or order summary (via local path, URL, or Google Drive link) and requests adding or updating items in Homebox.

2. **Execution**:
   - **Dry Run (Preview Extraction & Changes)**:
     ```bash
     task invoice:import FILE="<path_or_url>" DRY_RUN=1
     ```
   - **Import into Homebox**:
     ```bash
     task invoice:import FILE="<path_or_url>"
     ```
   - **Skip Attachment**:
     ```bash
     task invoice:import FILE="<path_or_url>" NO_ATTACH=1
     ```

3. **Workflow & Field Handling**:
   - **Document Parsing**:
     - Extracts text using `lit parse -q --no-ocr <file>` first for rapid digital text extraction.
     - Falls back to `lit parse -q <file>` (built-in OCR) if the document is scanned, image-only, or no text is extracted.
   - **Extracted Order Metadata**:
     - `order_id`: Amazon order number (e.g. `113-3740671-2345851`).
     - `order_date`: Formatted to `YYYY-MM-DD`.
     - `subtotal` & `grand_total`.
   - **Extracted Product Line Items**:
     - `name`: Clean product title.
     - `description`: Full item description.
     - `modelNumber`: Extracted model / part number.
     - `manufacturer`: Recognized brand or vendor.
     - `purchasePrice`: Unit price.
     - `quantity`: Quantity purchased.
     - `purchaseDate`: Order date.
     - `purchaseFrom`: `Amazon`.
     - `fields`: Custom field `Order Number` with order ID.
   - **Existing Item Check (Fill Missing Details)**:
     - Checks Homebox first for matching item via model number or name keywords.
     - If the item **already exists**:
       - Fills in missing `purchaseDate`, `purchaseFrom`, `purchasePrice`, `modelNumber`, `manufacturer`, and `Order Number` custom field.
       - Preserves all existing non-empty fields and notes.
       - Updates the existing entity via Homebox API.
     - If the item **does not exist**:
       - Creates a new item in Homebox with the extracted details.
   - **Attachment**:
     - Copies the invoice PDF to `images/processed/Amazon_Invoice_<order_id>.pdf`.
     - Attaches the PDF invoice to each corresponding item entity in Homebox.
