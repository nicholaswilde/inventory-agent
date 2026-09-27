"""
Batch Import Pipeline for Homebox.
Imports multiple items from a list of URLs/ASINs, a text file, or an Amazon Order History CSV.
Extracts product specs, order metadata, dates, prices, and attaches product images.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from scripts.import_url import (
    HTTP_HEADERS,
    create_homebox_entity,
    extract_product_data,
    fetch_url_html,
    get_homebox_config,
    normalize_url,
)

EXCLUDE_PATTERNS = [
    r"\bvitamin\b", r"\bsupplement\b", r"\bshampoo\b", r"\bsoap\b", r"\blotion\b", r"\btoothpaste\b",
    r"\btea\b", r"\bcoffee\b", r"\bcandy\b", r"\bsnack\b", r"\bchocolate\b", r"\bsauce\b", r"\borganic\b",
    r"\bcapsule\b", r"\btablet\b", r"\bwipes\b", r"\btowel\b", r"\bcleaner\b", r"\bdetergent\b",
    r"\bsponge\b", r"\bfilter replacement\b", r"\bbeans\b", r"\bscented\b", r"\bpaper\b", r"\bbags\b",
    r"\btape\b", r"\bglue\b", r"\bepoxy\b", r"\bsandpaper\b", r"\bscrews\b", r"\bbolts\b", r"\bzip ties\b",
    r"\bshirt\b", r"\bsocks\b", r"\bgloves\b", r"\bpants\b", r"\bunderwear\b", r"\bshoes\b", r"\bsandals\b",
    r"\bslippers\b", r"\bmask\b", r"\bbook\b", r"\bpaperback\b", r"\bhardcover\b", r"\bkindle\b",
    r"\baudiobook\b", r"\bcups\b", r"\bmug\b", r"\bbottle\b", r"\bcase for\b", r"\bcover for\b",
    r"\bsleeve\b", r"\bstrap\b", r"\bmat\b", r"\bpillow\b", r"\bsheet\b", r"\bcurtain\b", r"\btoy\b",
    r"\bcostume\b", r"\bbaby wipes\b", r"\bdiaper\b", r"\bpacifier\b", r"\bbaby carrier\b"
]

EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "computing": [
        r"\bintel nuc\b", r"\bmini pc\b", r"\blaptop\b", r"\bdesktop\b", r"\bmonitor\b",
        r"\bunifi\b", r"\bubiquiti\b", r"\bswitch\b", r"\brouter\b", r"\bmodem\b", r"\bdock\b",
        r"\bthunderbolt\b", r"\bnas\b", r"\bsynology\b", r"\bhard drive\b", r"\bssd\b", r"\bnvme\b",
        r"\baccess point\b", r"\bheadphone\b", r"\bdac\b", r"\bamplifier\b"
    ],
    "smarthome": [
        r"\besp32\b", r"\besp8266\b", r"\brasaspberry pi\b", r"\barduino\b", r"\bzigbee\b",
        r"\bz-wave\b", r"\bsonoff\b", r"\bshelly\b", r"\bsmart plug\b", r"\bsmart lock\b",
        r"\bdeadbolt\b", r"\baqara\b", r"\bthermostat\b", r"\bsmart fan\b", r"\bdimmer\b",
        r"\blora\b", r"\bnest learning\b", r"\bcamera\b"
    ],
    "tools": [
        r"\bknipex\b", r"\bmitutoyo\b", r"\bcaliper\b", r"\bmultimeter\b", r"\bsoldering\b",
        r"\boscilloscope\b", r"\bdrill\b", r"\bsaw\b", r"\bcrimper\b", r"\bstud finder\b",
        r"\bdremel\b", r"\bheat gun\b", r"\bpower supply\b", r"\bwrench\b", r"\bpliers\b",
        r"\bscrews driver\b", r"\btorque\b", r"\bvise\b", r"\bclamp\b", r"\bwelder\b"
    ],
    "appliances": [
        r"\brobot vacuum\b", r"\bvacuum\b", r"\bair fryer\b", r"\bfood processor\b",
        r"\bhand blender\b", r"\bmicrowave\b", r"\brange hood\b", r"\bblender\b",
        r"\bdishwasher\b", r"\brefrigerator\b", r"\bwater heater\b", r"\bfaucet\b",
        r"\bshowerhead\b", r"\bsink\b", r"\bpatio heater\b", r"\bmixer\b", r"\bdehydrator\b"
    ]
}


def parse_items_list(
    direct_items: list[str] | None = None,
    file_path: str | None = None
) -> list[str]:
    """Parse list of items (ASINs/URLs) from arguments and/or a text file."""
    items: list[str] = []
    if direct_items:
        for it in direct_items:
            clean = it.strip()
            if clean:
                items.append(clean)

    if file_path:
        p = Path(file_path)
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    items.append(line)
    return items


def parse_amazon_orders_csv(csv_path: str) -> dict[str, dict[str, Any]]:
    """Parse Amazon orders CSV into an ASIN-indexed dictionary of order details."""
    orders_by_asin: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "orders": [], "name": "", "dept": "", "latest_date": "", "unit_price": 0.0}
    )

    with open(csv_path, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = (row.get("\ufeffASIN") or row.get("ASIN") or "").strip()
            if not asin or row.get("Order Status") == "Cancelled":
                continue

            name = (row.get("Product Name") or "").strip()
            dept = (row.get("Department") or "").strip()
            qty_val = row.get("Original Quantity") or 1
            try:
                qty = int(qty_val)
            except ValueError:
                qty = 1

            price_str = (row.get("Unit Price") or "0").replace("$", "").replace(",", "").strip()
            try:
                price = float(price_str)
            except ValueError:
                price = 0.0

            order_date = (row.get("Order Date") or "")[:10]
            order_id = (row.get("Order ID") or "").strip()

            entry = orders_by_asin[asin]
            entry["count"] += qty
            entry["name"] = name or entry["name"]
            entry["dept"] = dept or entry["dept"]
            entry["orders"].append({
                "date": order_date,
                "qty": qty,
                "unit_price": price,
                "order_id": order_id
            })

            if not entry["latest_date"] or order_date > entry["latest_date"]:
                entry["latest_date"] = order_date
                entry["unit_price"] = price

    return dict(orders_by_asin)


def filter_csv_candidates(
    orders: dict[str, dict[str, Any]],
    category: str | None = None,
    min_price: float = 0.0
) -> list[dict[str, Any]]:
    """Filter durable candidates from parsed CSV orders based on price and category."""
    candidates = []
    cat_lower = category.lower() if category else None

    for asin, info in orders.items():
        name = info["name"]
        price = info["unit_price"]

        if price < min_price:
            continue
        if EXCLUDE_RE.search(name):
            continue

        matched_cat = None
        for cname, patterns in CATEGORY_PATTERNS.items():
            if any(re.search(p, name, re.IGNORECASE) for p in patterns):
                matched_cat = cname
                break

        if cat_lower and cat_lower != "all":
            if matched_cat != cat_lower:
                continue

        candidates.append({
            "asin": asin,
            "name": name,
            "category": matched_cat or "other",
            "unit_price": price,
            "quantity": info["count"],
            "latest_date": info["latest_date"],
            "orders": info["orders"],
        })

    candidates.sort(key=lambda x: -x["unit_price"])
    return candidates


def fetch_existing_homebox_items(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Retrieve existing items from Homebox API."""
    try:
        resp = requests.get(f"{base_url}/items", headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("items", []) if isinstance(data, dict) else data
    except Exception:
        pass
    return []


def find_existing_item(
    asin: str,
    name: str,
    model: str,
    existing_items: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find matching item in Homebox cache by ASIN, model number, or title."""
    for it in existing_items:
        notes = it.get("notes") or ""
        it_name = (it.get("name") or "").lower()
        it_model = (it.get("modelNumber") or "").lower()

        if asin and asin in notes:
            return it
        if model and it_model and model.lower() == it_model:
            return it
        if len(name) > 15 and (name.lower() in it_name or it_name in name.lower()):
            return it
    return None


def batch_import(
    items: list[str] | None = None,
    csv_path: str | None = None,
    category: str | None = None,
    min_price: float = 0.0,
    dry_run: bool = False,
    delay: float = 0.5,
    attach_images: bool = True,
    update_existing: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute batch import from list of items and/or Amazon order history CSV.
    """
    # 1. Parse CSV orders if provided
    csv_orders: dict[str, dict[str, Any]] = {}
    if csv_path:
        csv_orders = parse_amazon_orders_csv(csv_path)

    # 2. Determine target items to import
    targets: list[str] = []
    if items:
        targets.extend(items)
    elif csv_path and (category or min_price > 0):
        candidates = filter_csv_candidates(csv_orders, category=category, min_price=min_price)
        targets.extend([c["asin"] for c in candidates])

    if not targets:
        return []

    # 3. If dry-run, output planned imports without contacting Homebox
    if dry_run:
        results = []
        for it in targets:
            url = normalize_url(it)
            asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
            asin = asin_match.group(1) if asin_match else it
            csv_info = csv_orders.get(asin, {})
            results.append({
                "asin": asin,
                "url": url,
                "name": csv_info.get("name", ""),
                "quantity": csv_info.get("count", 1),
                "purchase_price": csv_info.get("unit_price", 0.0),
                "purchase_date": csv_info.get("latest_date", ""),
                "dry_run": True,
            })
        return results

    # 4. Live execution: setup Homebox API connection
    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    auth_header = {"Authorization": f"Bearer {key}"}
    json_headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    existing_items = fetch_existing_homebox_items(base_url, auth_header)
    results = []

    for i, it in enumerate(targets):
        if i > 0 and delay > 0:
            time.sleep(delay)

        url = normalize_url(it)
        asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        asin = asin_match.group(1) if asin_match else it
        csv_info = csv_orders.get(asin, {})

        name_hint = csv_info.get("name", "")
        existing = find_existing_item(asin, name_hint, "", existing_items)

        fallback = False
        entity_id = None

        if existing and not update_existing:
            results.append({
                "asin": asin,
                "name": existing.get("name", name_hint),
                "entity_id": existing.get("id"),
                "status": "skipped_exists",
                "quantity": existing.get("quantity", 1),
                "purchase_price": existing.get("purchasePrice", 0.0),
            })
            continue

        if existing and update_existing:
            entity_id = existing.get("id")
        else:
            # Try fetching product page from live web
            raw_html = None
            try:
                raw_html = fetch_url_html(url)
            except Exception:
                fallback = True

            if raw_html:
                product_data = extract_product_data(raw_html, url)
                image_bytes = None
                image_filename = f"{asin}.jpg"

                if attach_images and product_data.get("image_url"):
                    try:
                        img_resp = requests.get(product_data["image_url"], headers=HTTP_HEADERS, timeout=15)
                        if img_resp.status_code == 200:
                            image_bytes = img_resp.content
                    except Exception:
                        pass

                # Append order history to notes
                notes_lines = [product_data.get("notes", "")]
                if csv_info.get("orders"):
                    notes_lines.append("\nOrder History:")
                    for o in csv_info["orders"]:
                        notes_lines.append(f"- {o['date']}: {o['qty']}x @ ${o['unit_price']:.2f} (Order #{o['order_id']})")
                product_data["notes"] = "\n".join(notes_lines).strip()

                if csv_info.get("unit_price"):
                    product_data["purchase_price"] = csv_info["unit_price"]
                product_data["purchase_from"] = "Amazon"
                if csv_info.get("count"):
                    product_data["quantity"] = csv_info["count"]

                entity_id = create_homebox_entity(product_data, image_bytes=image_bytes, image_filename=image_filename)
            else:
                # Fallback on CSV metadata (e.g. delisted / 404 products)
                fallback = True
                notes_lines = [f"Source: Amazon CSV\nASIN: {asin}\n"]
                if csv_info.get("orders"):
                    notes_lines.append("Order History:")
                    for o in csv_info["orders"]:
                        notes_lines.append(f"- {o['date']}: {o['qty']}x @ ${o['unit_price']:.2f} (Order #{o['order_id']})")

                product_data = {
                    "name": csv_info.get("name") or it,
                    "manufacturer": "Intel" if "intel" in name_hint.lower() else "",
                    "model_number": "",
                    "description": csv_info.get("name", ""),
                    "purchase_price": csv_info.get("unit_price", 0.0),
                    "purchase_from": "Amazon",
                    "notes": "\n".join(notes_lines).strip(),
                    "quantity": csv_info.get("count", 1)
                }
                entity_id = create_homebox_entity(product_data)

        # Update entity fields to ensure purchaseDate, purchasePrice, and quantity are synchronized
        if entity_id:
            try:
                curr_resp = requests.get(f"{base_url}/entities/{entity_id}", headers=auth_header, timeout=10)
                if curr_resp.status_code == 200:
                    ent_data = curr_resp.json()
                    if csv_info.get("unit_price"):
                        ent_data["purchasePrice"] = csv_info["unit_price"]
                    if csv_info.get("latest_date"):
                        ent_data["purchaseDate"] = csv_info["latest_date"]
                    if csv_info.get("count"):
                        ent_data["quantity"] = csv_info["count"]
                    ent_data["purchaseFrom"] = "Amazon"

                    requests.put(f"{base_url}/entities/{entity_id}", json=ent_data, headers=json_headers, timeout=10)
            except Exception:
                pass

        results.append({
            "asin": asin,
            "name": name_hint or it,
            "entity_id": entity_id,
            "quantity": csv_info.get("count", 1),
            "purchase_price": csv_info.get("unit_price", 0.0),
            "fallback": fallback,
            "status": "imported" if not existing else "updated"
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch import items into Homebox from URLs, ASINs, or Amazon CSV.")
    parser.add_argument("items", nargs="*", help="ASINs or product URLs to import")
    parser.add_argument("--file", help="Path to text file containing ASINs/URLs (one per line)")
    parser.add_argument("--csv", help="Path to Amazon order history CSV")
    parser.add_argument("--category", choices=["computing", "smarthome", "tools", "appliances", "all"], help="Filter CSV by category")
    parser.add_argument("--min-price", type=float, default=0.0, help="Minimum purchase price filter for CSV candidates")
    parser.add_argument("--dry-run", action="store_true", help="Preview items without importing into Homebox")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between web requests in seconds")
    parser.add_argument("--no-attach", action="store_true", help="Do not download/attach product images")
    parser.add_argument("--update-existing", action="store_true", help="Update existing Homebox items with order details")

    args = parser.parse_args()

    items = parse_items_list(direct_items=args.items, file_path=args.file)

    if not items and not (args.csv and (args.category or args.min_price > 0)):
        parser.error("No items specified. Provide ASINs/URLs, a --file, or --csv with --category/--min-price.")

    results = batch_import(
        items=items if items else None,
        csv_path=args.csv,
        category=args.category,
        min_price=args.min_price,
        dry_run=args.dry_run,
        delay=args.delay,
        attach_images=not args.no_attach,
        update_existing=args.update_existing,
    )

    if args.dry_run:
        print(f"[DRY RUN] Planned {len(results)} imports:")
        for r in results:
            print(f"- [{r['asin']}] {r['name'][:60]} | Qty: {r['quantity']} | Price: ${r['purchase_price']:.2f}")
    else:
        print(f"Batch import completed: {len(results)} items processed.")
        for r in results:
            status = r.get("status", "ok")
            print(f"[{r['asin']}] {r['name'][:50]} -> ID: {r.get('entity_id')} ({status})")


if __name__ == "__main__":
    main()
