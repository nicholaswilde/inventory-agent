---
name: batch-import
description: Batch imports multiple items into Homebox from product URLs, Amazon ASINs, text files, or Amazon order history CSVs with live metadata extraction and image attachments.
---

# Batch Import Skill

Performs batch imports of multiple items into Homebox from a list of URLs/ASINs, a text file, or an Amazon Order History CSV. Fetches product specs, models, brands, and photos from live product pages, synchronizes purchase dates, quantities, and prices from order histories, gracefully falls back to CSV metadata for delisted/404 products, and avoids duplicate entries.

## Guidelines

1. **Trigger**:
   - Use whenever the user asks to import multiple products, a batch or list of ASINs/URLs, an items text file, or items from an Amazon order history CSV into Homebox.

2. **Execution**:
   - **From List of Items (ASINs or URLs)**:
     ```bash
     # Dry Run:
     task batch:import ITEMS="B005EXOK0Y B00IG46NL2 B09RS3W7M5" DRY_RUN=1

     # Import:
     task batch:import ITEMS="B005EXOK0Y B00IG46NL2 B09RS3W7M5"
     ```

   - **From Items Text File (one URL/ASIN per line)**:
     ```bash
     # Dry Run:
     task batch:import FILE="items.txt" DRY_RUN=1

     # Import:
     task batch:import FILE="items.txt"
     ```

   - **From Amazon Order History CSV (Specific ASINs)**:
     ```bash
     # Enriches live product fetch with actual order date, purchase price paid, and quantity
     task batch:import ITEMS="B005EXOK0Y B00IG46NL2" CSV="orders.csv" DRY_RUN=1
     task batch:import ITEMS="B005EXOK0Y B00IG46NL2" CSV="orders.csv"
     ```

   - **From Amazon Order History CSV (Category & Price Filter)**:
     ```bash
     # Categories: computing, smarthome, tools, appliances, all
     task batch:import CSV="orders.csv" CATEGORY="tools" MIN_PRICE=50 DRY_RUN=1
     task batch:import CSV="orders.csv" CATEGORY="smarthome" MIN_PRICE=30
     ```

   - **Update Existing Entities**:
     ```bash
     # Updates existing Homebox items with order dates, purchase price, and quantities
     task batch:import CSV="orders.csv" ITEMS="B086383HC7" UPDATE=1
     ```

3. **Key Features & Resiliency**:
   - **Live Web Enrichment**: Scrapes product specifications, bullet points, manufacturer, and high-resolution primary product images.
   - **Delisted Product Fallback**: Automatically falls back to CSV order name, price, date, and order ID if a product URL returns HTTP 404 or is delisted.
   - **Deduplication**: Checks Homebox for matching ASINs, model numbers, or titles before creating items to prevent duplicate records.
   - **Rate Limiting**: Includes a configurable inter-request delay (`--delay 0.5`) to prevent throttling from retailer websites.
   - **Image Attachments**: Downloads and attaches product photos directly to created Homebox items (can be skipped with `NO_ATTACH=1`).
