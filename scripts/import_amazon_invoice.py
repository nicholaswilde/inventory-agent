"""
Amazon Invoice Ingestion Pipeline for Homebox.
Parses Amazon PDF invoices using lit (with built-in OCR fallback),
extracts order details, line items, prices, and quantities,
checks Homebox for existing items to fill in missing details,
and creates new Homebox items if they do not exist.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
import urllib.parse

import requests

KNOWN_BRANDS = [
    "Moen", "Kohler", "Delta", "Grohe", "Pfister", "American Standard",
    "Apple", "Samsung", "Google", "Sony", "Logitech", "Anker", "Belkin",
    "DeWalt", "Milwaukee", "Bosch", "Makita", "Ryobi", "Craftsman",
    "Philips", "TP-Link", "Netgear", "Ubiquiti", "Raspberry Pi", "Arduino",
    "Adafruit", "SparkFun", "DSD TECH", "Poyiccot", "CableCreation", "UGREEN"
]


def get_homebox_config() -> tuple[str, str]:
    """Extract HOMEBOX_IP and HOMEBOX_API_KEY from environment or local .env file."""
    ip = os.getenv("HOMEBOX_IP")
    key = os.getenv("HOMEBOX_API_KEY")

    if not ip or not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "HOMEBOX_IP" and not ip:
                        ip = v
                    elif k == "HOMEBOX_API_KEY" and not key:
                        key = v

    if not ip or not key:
        raise ValueError("HOMEBOX_IP or HOMEBOX_API_KEY not set in environment or .env")

    return ip, key


def download_invoice_if_url(source: str, target_dir: Path | str = "images/pending") -> Path:
    """If source is a URL or Google Drive link, download it; otherwise return Path."""
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    if not (source.startswith("http://") or source.startswith("https://")):
        return Path(source)

    # Google Drive handling
    drive_match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", source)
    if drive_match:
        file_id = drive_match.group(1)
        download_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
        dest_file = target_path / f"amazon_invoice_{file_id}.pdf"
    else:
        parsed = urllib.parse.urlparse(source)
        file_name = Path(parsed.path).name or "amazon_invoice.pdf"
        if not file_name.lower().endswith(".pdf"):
            file_name += ".pdf"
        download_url = source
        dest_file = target_path / file_name

    resp = requests.get(download_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_file, "wb") as f:
        if hasattr(resp, "iter_content"):
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    if dest_file.stat().st_size == 0 and hasattr(resp, "content") and resp.content:
        dest_file.write_bytes(resp.content)

    return dest_file


def extract_text_from_pdf(pdf_path: Path | str) -> str:
    """Extract text from PDF using lit (--no-ocr first, built-in OCR fallback), with pdftotext fallback."""
    # 1. lit parse direct text extraction (fast, no OCR)
    try:
        proc = subprocess.run(
            ["lit", "parse", str(pdf_path), "--quiet", "--no-ocr"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 2. lit parse built-in OCR fallback
    try:
        proc = subprocess.run(
            ["lit", "parse", str(pdf_path), "--quiet"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 3. pdftotext fallback
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return ""


def _parse_order_date(raw_date_str: str) -> str | None:
    """Parse 'August 7, 2018' to '2018-08-07'."""
    try:
        dt = datetime.strptime(raw_date_str.strip(), "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def extract_invoice_data(text: str) -> dict[str, Any]:
    """Parse Amazon invoice text for order metadata and purchased line items."""
    result: dict[str, Any] = {
        "order_id": None,
        "order_date": None,
        "subtotal": 0.0,
        "grand_total": 0.0,
        "items": [],
    }

    # Order # 113-3740671-2345851
    order_id_match = re.search(r"Order\s*#\s*([0-9]{3}-[0-9]{7}-[0-9]{7})", text)
    if order_id_match:
        result["order_id"] = order_id_match.group(1)

    # Order placed August 7, 2018
    date_match = re.search(r"Order\s+placed\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if date_match:
        parsed_d = _parse_order_date(date_match.group(1))
        if parsed_d:
            result["order_date"] = parsed_d

    # Subtotal
    subtotal_match = re.search(r"Item\(s\)\s+Subtotal:\s*\$([0-9,]+\.[0-9]{2})", text)
    if subtotal_match:
        result["subtotal"] = float(subtotal_match.group(1).replace(",", ""))

    # Grand Total
    grand_match = re.search(r"Grand\s+Total:\s*\$([0-9,]+\.[0-9]{2})", text)
    if grand_match:
        result["grand_total"] = float(grand_match.group(1).replace(",", ""))

    # Parse line items
    # Typically each product block starts with item description, sold by, price, and optional quantity
    lines = [l.strip() for l in text.splitlines()]
    
    # Split content after Order Summary / Ship to section and before footer
    in_items_section = False
    current_title_lines = []
    current_price = None
    current_sold_by = None
    current_qty = 1
    found_items = []

    for i, line in enumerate(lines):
        if not line:
            continue

        # Items begin strictly after Grand Total
        if "Grand Total" in line:
            in_items_section = True
            continue

        if not in_items_section:
            continue

        if any(f in line for f in ["Back to top", "Conditions of Use", "Privacy Notice", "Order Details", "https://"]):
            # End of items
            break

        # Price pattern, optionally preceded by quantity: e.g. "$95.76" or "2  $47.29"
        price_match = re.search(r"(?:^|\s)(?:(\d+)\s+)?\$([0-9,]+\.[0-9]{2})$", line)
        if price_match:
            qty = int(price_match.group(1)) if price_match.group(1) else 1
            current_price = float(price_match.group(2).replace(",", ""))

            title = " ".join(current_title_lines).strip()
            # Clean up OCR artifacts/markers at start of title
            title = re.sub(r"^[q|{fy\d\s]+\s+", "", title).strip()

            if title and current_price is not None:
                item_obj = _build_item_object(title, current_price, qty, current_sold_by)
                found_items.append(item_obj)

            current_title_lines = []
            current_price = None
            current_sold_by = None
            continue

        if line.startswith("Sold by:"):
            current_sold_by = line.replace("Sold by:", "").strip()
            continue
        if line.startswith("Supplied by:"):
            continue

        # Filter out standalone small numbers that represent quantities already consumed
        if re.match(r"^\d+$", line) and int(line) <= 100:
            continue

        # Otherwise line is part of title
        current_title_lines.append(line)

    result["items"] = found_items
    return result


def _build_item_object(title: str, price: float, quantity: int, sold_by: str | None) -> dict[str, Any]:
    """Helper to structure an item with detected model number and brand."""
    # Detect brand
    manufacturer = ""
    for brand in KNOWN_BRANDS:
        if brand.lower() in title.lower():
            manufacturer = brand
            break
    if not manufacturer:
        words = title.split()
        if words and words[0].isalpha() and len(words[0]) > 2:
            manufacturer = words[0]

    # Detect model number
    model_number = ""
    # Model in parentheses like (7594ESRS)
    paren_match = re.search(r"\(([A-Z0-9]{3,}[A-Z0-9_-]*)\)", title)
    if paren_match:
        model_number = paren_match.group(1)
    else:
        # Search for model token like 169031 or 3942SRS
        tokens = title.split()
        for tok in tokens:
            cleaned = tok.strip("(),.-")
            if re.match(r"^(?=[A-Z0-9]*\d)[A-Z0-9]{4,12}$", cleaned, re.IGNORECASE):
                # Ensure it's not a generic word
                if cleaned.lower() not in ["2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]:
                    model_number = cleaned
                    break

    return {
        "title": title,
        "manufacturer": manufacturer,
        "model_number": model_number,
        "price": price,
        "quantity": quantity,
        "sold_by": sold_by or "Amazon.com",
    }


def search_homebox_entities(query: str, base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Query Homebox /entities with q parameter."""
    try:
        resp = requests.get(f"{base_url}/entities", params={"q": query}, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("items", [])
    except Exception:
        pass
    return []


def find_existing_item(
    model_number: str | None,
    title: str,
    base_url: str,
    headers: dict[str, str],
) -> dict[str, Any] | None:
    """Check Homebox for existing item with matching model number or title keywords."""
    queries = []
    if model_number and model_number.strip():
        queries.append(model_number.strip())

    # Key words from title
    title_words = [w for w in re.findall(r"[A-Za-z0-9]{4,}", title) if w.lower() not in ["with", "from", "other", "resist", "stainless"]]
    if len(title_words) >= 2:
        queries.append(" ".join(title_words[:3]))

    for q in queries:
        items = search_homebox_entities(q, base_url, headers)
        for item in items:
            item_model = item.get("modelNumber", "").strip().lower()
            if model_number and item_model and (model_number.lower() in item_model or item_model in model_number.lower()):
                return item

            # Strong name matching
            item_name = item.get("name", "").strip().lower()
            if model_number and model_number.lower() in item_name:
                return item
            if all(word.lower() in item_name for word in title_words[:2]):
                return item

    return None


def fill_missing_details(
    existing_item: dict[str, Any],
    item_data: dict[str, Any],
    order_id: str | None,
    order_date: str | None,
) -> dict[str, Any]:
    """Compute patch payload to fill in missing details on an existing Homebox entity."""
    patch: dict[str, Any] = {}

    if not existing_item.get("purchaseDate") and order_date:
        patch["purchaseDate"] = order_date

    if not existing_item.get("purchaseFrom"):
        patch["purchaseFrom"] = "Amazon"

    if (not existing_item.get("purchasePrice") or existing_item.get("purchasePrice") == 0) and item_data.get("price"):
        patch["purchasePrice"] = item_data["price"]

    if not existing_item.get("manufacturer") and item_data.get("manufacturer"):
        patch["manufacturer"] = item_data["manufacturer"]

    if not existing_item.get("modelNumber") and item_data.get("model_number"):
        patch["modelNumber"] = item_data["model_number"]

    # Order Number custom field
    existing_fields = existing_item.get("fields", [])
    has_order_field = any(f.get("name") == "Order Number" and f.get("textValue") for f in existing_fields)
    
    if not has_order_field and order_id:
        fields = list(existing_fields)
        fields = [f for f in fields if f.get("name") != "Order Number"]
        fields.append({"name": "Order Number", "type": "text", "textValue": order_id})
        patch["fields"] = fields

    return patch


def create_new_item_payload(
    item_data: dict[str, Any],
    order_id: str | None,
    order_date: str | None,
) -> dict[str, Any]:
    """Build payload for a new Homebox item."""
    # Clean up name: up to first comma or ~50 chars
    title = item_data["title"]
    clean_name = title.split(",")[0].strip() if "," in title else title[:60].strip()

    fields = []
    if order_id:
        fields.append({"name": "Order Number", "type": "text", "textValue": order_id})

    return {
        "name": clean_name,
        "description": title,
        "modelNumber": item_data.get("model_number", ""),
        "manufacturer": item_data.get("manufacturer", ""),
        "purchasePrice": item_data.get("price", 0.0),
        "quantity": item_data.get("quantity", 1),
        "purchaseDate": order_date or "",
        "purchaseFrom": "Amazon",
        "fields": fields,
    }


def update_homebox_entity(entity_id: str, patch_data: dict[str, Any], base_url: str, headers: dict[str, str]) -> None:
    """Fetch entity, merge patch, and PUT back to Homebox."""
    resp = requests.get(f"{base_url}/entities/{entity_id}", headers=headers, timeout=15)
    resp.raise_for_status()
    current = resp.json()
    merged = {**current, **patch_data}
    put_resp = requests.put(
        f"{base_url}/entities/{entity_id}",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(merged),
        timeout=15,
    )
    put_resp.raise_for_status()


def create_homebox_entity(data: dict[str, Any], base_url: str, headers: dict[str, str]) -> str:
    """Create entity via POST /entities."""
    resp = requests.post(
        f"{base_url}/entities",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(data),
        timeout=15,
    )
    resp.raise_for_status()
    created = resp.json()
    return created.get("id", "")


def attach_file_to_entity(entity_id: str, file_path: Path | str, base_url: str, headers: dict[str, str]) -> None:
    """Upload attachment to Homebox entity."""
    path = Path(file_path)
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "application/pdf")}
        data = {"name": path.name}
        resp = requests.post(f"{base_url}/entities/{entity_id}/attachments", headers=headers, files=files, data=data, timeout=30)
        resp.raise_for_status()


def import_amazon_invoice(
    source: str,
    dry_run: bool = False,
    attach: bool = True,
    processed_dir: Path | str = "images/processed",
) -> dict[str, Any]:
    """Execute complete Amazon invoice import pipeline."""
    # 1. Download or get file path
    pdf_path = download_invoice_if_url(source)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Invoice file not found: {pdf_path}")

    # 2. Extract text with lit
    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text.strip():
        raise ValueError(f"Failed to extract text from {pdf_path}")

    # 3. Parse invoice data
    invoice_data = extract_invoice_data(raw_text)
    order_id = invoice_data.get("order_id")
    order_date = invoice_data.get("order_date")

    # 4. Save processed copy
    processed_path = Path(processed_dir)
    processed_path.mkdir(parents=True, exist_ok=True)
    if order_id:
        final_pdf_path = processed_path / f"Amazon_Invoice_{order_id}.pdf"
    else:
        final_pdf_path = processed_path / pdf_path.name

    if str(pdf_path.resolve()) != str(final_pdf_path.resolve()):
        shutil.copyfile(pdf_path, final_pdf_path)

    # 5. Connect to Homebox
    if not dry_run:
        ip, key = get_homebox_config()
        base_url = f"http://{ip}:7745/api/v1"
        headers = {"Authorization": f"Bearer {key}"}
    else:
        base_url = ""
        headers = {}

    processed_items = []
    for item in invoice_data["items"]:
        item_summary = {
            "title": item["title"],
            "model_number": item["model_number"],
            "price": item["price"],
            "quantity": item["quantity"],
            "action": "dry_run" if dry_run else "",
            "entity_id": "",
        }

        if dry_run:
            processed_items.append(item_summary)
            continue

        # Check existing item
        existing = find_existing_item(item["model_number"], item["title"], base_url, headers)
        if existing:
            entity_id = existing["id"]
            patch = fill_missing_details(existing, item, order_id, order_date)
            if patch:
                update_homebox_entity(entity_id, patch, base_url, headers)
            item_summary["action"] = "updated"
            item_summary["entity_id"] = entity_id
        else:
            payload = create_new_item_payload(item, order_id, order_date)
            entity_id = create_homebox_entity(payload, base_url, headers)
            item_summary["action"] = "created"
            item_summary["entity_id"] = entity_id

        # Attach invoice
        if attach and entity_id and final_pdf_path.exists():
            try:
                attach_file_to_entity(entity_id, final_pdf_path, base_url, headers)
            except Exception as e:
                print(f"Warning: Failed to attach invoice to entity {entity_id}: {e}", file=sys.stderr)

        processed_items.append(item_summary)

    invoice_data["items"] = processed_items
    return invoice_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Amazon PDF invoice into Homebox.")
    parser.add_argument("source", help="Path to PDF invoice or URL (Google Drive / web)")
    parser.add_argument("--dry-run", action="store_true", help="Preview extracted data without altering Homebox")
    parser.add_argument("--no-attach", action="store_true", help="Do not attach invoice PDF to Homebox items")
    parser.add_argument("--processed-dir", default="images/processed", help="Directory to store processed invoices")

    args = parser.parse_args()

    try:
        result = import_amazon_invoice(
            source=args.source,
            dry_run=args.dry_run,
            attach=not args.no_attach,
            processed_dir=args.processed_dir,
        )
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
