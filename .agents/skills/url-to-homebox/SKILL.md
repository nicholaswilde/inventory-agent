---
name: url-to-homebox
description: Imports a product from a URL (Amazon, retail, product web pages) into Homebox with extracted metadata, specs, price, and product image attachment.
---

# URL to Homebox Skill

Imports an item into Homebox from a product URL (Amazon, e-commerce stores, brand/product pages). Fetches page metadata (Schema.org JSON-LD, OpenGraph, HTML product markup), checks for existing duplicates in Homebox, creates the entity, and attaches the primary product image.

## Guidelines

1. **Trigger**:
   - Use whenever the user asks to import or add an item into Homebox from a web link / URL (e.g. `https://www.amazon.com/dp/...` or retail product pages).

2. **Execution**:
   - **Dry Run (Preview)**:
     ```bash
     task url:import URL="<url>" DRY_RUN=1
     ```
   - **Import into Homebox**:
     ```bash
     task url:import URL="<url>"
     ```
   - **With Overrides**:
     ```bash
     task url:import URL="<url>" -- --name "<Custom Name>" --model "<Model Number>"
     ```

3. **Artifacts & Data Extracted**:
   - **Name**: Product title / model name.
   - **Manufacturer / Brand**: Extracted from Schema.org brand, meta tags, or byline.
   - **Model Number / SKU / MPN**: Extracted from specifications, tables, or product identifiers.
   - **Purchase Price**: Extracted from offer/price metadata and saved to `purchasePrice`.
   - **Product Image**: Primary product image downloaded and uploaded as an attachment to the entity.
   - **Notes & Description**: Source URL, ASIN / SKU, bullet points, and key product features.
   - **Deduplication**: Automatically checks Homebox for matching model number or item name before creating to prevent duplicate entries.
