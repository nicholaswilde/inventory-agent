"""
Product URL Ingestion Pipeline for Homebox.
Fetches product pages (Amazon, retail, generic), extracts metadata (name, brand,
model number, price, description, product image), and creates Homebox inventory items.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


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


def fetch_url_html(url: str, timeout: int = 30) -> str:
    """Fetch raw HTML for product page."""
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _clean_text(text: str) -> str:
    """Unescape HTML entities and normalize whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_product_data(raw_html: str, url: str) -> dict[str, Any]:
    """Parse product metadata from Amazon, Schema.org LD+JSON, or OpenGraph meta tags."""
    data: dict[str, Any] = {
        "name": "",
        "manufacturer": "",
        "model_number": "",
        "purchase_price": None,
        "description": "",
        "image_url": "",
        "notes": "",
        "source_url": url,
    }

    bullets: list[str] = []
    asin = ""
    # Check for Amazon ASIN
    asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    if asin_match:
        asin = asin_match.group(1)

    # 1. Check for Schema.org JSON-LD scripts
    json_ld_matches = re.findall(
        r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>',
        raw_html,
        re.DOTALL | re.IGNORECASE,
    )
    for block in json_ld_matches:
        try:
            ld = json.loads(block.strip())
            # Sometimes JSON-LD is a list or wrapped in @graph
            items = ld if isinstance(ld, list) else ld.get("@graph", [ld])
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("@type") in ["Product", "IndividualProduct"]:
                    if not data["name"] and item.get("name"):
                        data["name"] = _clean_text(item["name"])
                    if not data["manufacturer"]:
                        brand = item.get("brand")
                        if isinstance(brand, dict):
                            data["manufacturer"] = _clean_text(brand.get("name", ""))
                        elif isinstance(brand, str):
                            data["manufacturer"] = _clean_text(brand)
                    if not data["model_number"]:
                        model = item.get("model") or item.get("mpn") or item.get("sku")
                        if isinstance(model, dict):
                            data["model_number"] = _clean_text(model.get("name", ""))
                        elif isinstance(model, str):
                            data["model_number"] = _clean_text(model)
                    if not data["description"] and item.get("description"):
                        data["description"] = _clean_text(item["description"])
                    if not data["image_url"] and item.get("image"):
                        img = item["image"]
                        if isinstance(img, list) and img:
                            data["image_url"] = img[0] if isinstance(img[0], str) else img[0].get("url", "")
                        elif isinstance(img, dict):
                            data["image_url"] = img.get("url", "")
                        elif isinstance(img, str):
                            data["image_url"] = img
                    if data["purchase_price"] is None and item.get("offers"):
                        offers = item["offers"]
                        offer = offers[0] if isinstance(offers, list) and offers else offers
                        if isinstance(offer, dict) and offer.get("price"):
                            try:
                                data["purchase_price"] = float(str(offer["price"]).replace(",", ""))
                            except (ValueError, TypeError):
                                pass
        except (json.JSONDecodeError, TypeError):
            continue

    # 2. Amazon specific patterns
    # Title
    amz_title = re.search(r'id=[\'"]productTitle[\'"][^>]*>\s*([^<]+)\s*<', raw_html)
    if amz_title:
        data["name"] = _clean_text(amz_title.group(1))

    # Brand
    amz_brand = re.search(r'id=[\'"]bylineInfo[\'"][^>]*>\s*([^<]+)\s*<', raw_html)
    if amz_brand and _clean_text(amz_brand.group(1)):
        raw_b = _clean_text(amz_brand.group(1))
        raw_b = re.sub(r"^(?:Brand:\s*|Visit the\s*)", "", raw_b, flags=re.IGNORECASE)
        raw_b = re.sub(r"\s*Store$", "", raw_b, flags=re.IGNORECASE)
        data["manufacturer"] = raw_b.strip()
    if not data["manufacturer"]:
        store_match = re.search(r'>\s*(?:Visit the\s+([A-Za-z0-9\s&.-]+?)\s+Store|Brand:\s*([A-Za-z0-9\s&.-]+?))\s*<', raw_html, re.IGNORECASE)
        if store_match:
            data["manufacturer"] = _clean_text(store_match.group(1) or store_match.group(2))

    # Price
    if data["purchase_price"] is None:
        price_match = re.search(r'class=[\'"]a-offscreen[\'"]>\s*\$([0-9,.]+)\s*<', raw_html)
        if price_match:
            try:
                data["purchase_price"] = float(price_match.group(1).replace(",", ""))
            except ValueError:
                pass

    # Model / Part number from tables
    if not data["model_number"]:
        mod_row = re.search(
            r"(?:Item model number|Part Number)[^<]*</(?:th|span)>\s*<(?:td|span)[^>]*>\s*([^<]+)\s*<",
            raw_html,
            re.IGNORECASE,
        )
        if mod_row:
            data["model_number"] = _clean_text(mod_row.group(1))

    # Amazon feature bullets
    bullet_matches = re.findall(
        r'<span class=[\'"]a-list-item[\'"]>\s*([^<]+)\s*</span>',
        raw_html,
        re.IGNORECASE,
    )
    for b in bullet_matches:
        cleaned = _clean_text(b)
        if len(cleaned) > 15 and not any(skip in cleaned.lower() for skip in ["shipping", "sign in", "prime"]):
            if cleaned not in bullets:
                bullets.append(cleaned)

    # Amazon image
    if not data["image_url"]:
        img_match = re.search(r'data-old-hires=[\'"]([^\'"]+)[\'"]', raw_html) or re.search(
            r'[\'"]large[\'"]:[\'"](https://m\.media-amazon\.com/[^\'"]+)[\'"]', raw_html
        )
        if img_match:
            data["image_url"] = img_match.group(1)

    # 3. OpenGraph fallback
    if not data["name"]:
        og_title = re.search(r'<meta[^>]*property=[\'"]og:title[\'"][^>]*content=[\'"]([^\'"]+)[\'"]', raw_html, re.IGNORECASE)
        if og_title:
            data["name"] = _clean_text(og_title.group(1))
    if not data["name"]:
        t_tag = re.search(r"<title>([^<]+)</title>", raw_html, re.IGNORECASE)
        if t_tag:
            t_clean = _clean_text(t_tag.group(1))
            t_clean = re.sub(r"\s*-\s*Amazon\.com.*$", "", t_clean, flags=re.IGNORECASE)
            data["name"] = t_clean

    if not data["manufacturer"]:
        og_brand = re.search(r'<meta[^>]*property=[\'"](?:product:brand|og:brand)[\'"][^>]*content=[\'"]([^\'"]+)[\'"]', raw_html, re.IGNORECASE)
        if og_brand:
            data["manufacturer"] = _clean_text(og_brand.group(1))

    if data["purchase_price"] is None:
        og_price = re.search(r'<meta[^>]*property=[\'"]product:price:amount[\'"][^>]*content=[\'"]([0-9,.]+)[\'"]', raw_html, re.IGNORECASE)
        if og_price:
            try:
                data["purchase_price"] = float(og_price.group(1).replace(",", ""))
            except ValueError:
                pass

    if not data["image_url"]:
        og_img = re.search(r'<meta[^>]*property=[\'"]og:image[\'"][^>]*content=[\'"]([^\'"]+)[\'"]', raw_html, re.IGNORECASE)
        if og_img:
            data["image_url"] = og_img.group(1)

    if not data["description"]:
        og_desc = re.search(r'<meta[^>]*property=[\'"](?:og:description|description)[\'"][^>]*content=[\'"]([^\'"]+)[\'"]', raw_html, re.IGNORECASE)
        if og_desc:
            data["description"] = _clean_text(og_desc.group(1))

    # Notes generation
    note_parts = [f"Source URL: {url}"]
    if asin:
        note_parts.append(f"Amazon ASIN: {asin}")
        data["asin"] = asin
    if bullets:
        note_parts.append("Features:")
        for b in bullets[:6]:
            note_parts.append(f"- {b}")
    data["notes"] = "\n".join(note_parts)

    return data


def check_duplicate(
    model_number: str | None,
    name: str,
    base_url: str,
    headers: dict[str, str],
    asin: str | None = None,
) -> dict[str, Any] | None:
    """Check Homebox for existing item with matching model number, name, or ASIN."""
    queries = []
    if asin:
        queries.append(asin.strip())
    if model_number:
        queries.append(model_number.strip())
    if name:
        queries.append(name.strip())

    for q in queries:
        try:
            resp = requests.get(f"{base_url}/entities", params={"q": q}, headers=headers, timeout=15)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if asin and q == asin.strip() and items:
                    return items[0]
                for item in items:
                    if model_number and item.get("modelNumber", "").strip().lower() == model_number.strip().lower():
                        return item
                    if item.get("name", "").strip().lower() == name.strip().lower():
                        return item
        except Exception:
            pass

    return None


def create_homebox_entity(
    data: dict[str, Any],
    image_bytes: bytes | None = None,
    image_filename: str = "product.jpg",
) -> str:
    """Create item in Homebox and upload product image."""
    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    payload: dict[str, Any] = {
        "name": data["name"],
        "description": data.get("description", ""),
        "manufacturer": data.get("manufacturer", ""),
        "modelNumber": data.get("model_number", ""),
        "quantity": 1,
        "notes": data.get("notes", ""),
    }
    if data.get("purchase_price") is not None:
        payload["purchasePrice"] = data["purchase_price"]

    create_resp = requests.post(f"{base_url}/entities", json=payload, headers=headers, timeout=30)
    create_resp.raise_for_status()
    entity_id = create_resp.json().get("id")

    # Update top-level fields (Homebox v0.26+ schema)
    update_resp = requests.put(f"{base_url}/entities/{entity_id}", json=payload, headers=headers, timeout=30)
    update_resp.raise_for_status()

    # Upload attachment image if available
    if image_bytes:
        files = {"file": (image_filename, image_bytes, "image/jpeg")}
        data_fields = {"name": image_filename}
        att_headers = {"Authorization": f"Bearer {key}"}
        att_resp = requests.post(
            f"{base_url}/entities/{entity_id}/attachments",
            headers=att_headers,
            files=files,
            data=data_fields,
            timeout=30,
        )
        att_resp.raise_for_status()

    return entity_id


def import_url(
    url: str,
    dry_run: bool = False,
    name_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Main importer orchestrator."""
    raw_html = fetch_url_html(url)
    product_data = extract_product_data(raw_html, url)

    if name_override:
        product_data["name"] = name_override
    if model_override:
        product_data["model_number"] = model_override

    # Fetch product image bytes
    image_bytes = None
    image_filename = "product.jpg"
    if product_data.get("image_url"):
        try:
            img_resp = requests.get(product_data["image_url"], headers=HTTP_HEADERS, timeout=15)
            if img_resp.status_code == 200:
                image_bytes = img_resp.content
                parsed_path = urllib.parse.urlparse(product_data["image_url"]).path
                ext = Path(parsed_path).suffix or ".jpg"
                slug = re.sub(r"[^a-zA-Z0-9]+", "_", product_data["name"][:30]).strip("_")
                image_filename = f"{slug}{ext}"
        except Exception:
            pass

    if dry_run:
        return {
            "entity": product_data,
            "homebox_id": "dry-run-id",
            "dry_run": True,
            "image_filename": image_filename,
            "has_image": image_bytes is not None,
        }

    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    headers = {"Authorization": f"Bearer {key}"}

    # Duplicate check
    dup = check_duplicate(
        model_number=product_data.get("model_number"),
        name=product_data["name"],
        base_url=base_url,
        headers=headers,
        asin=product_data.get("asin"),
    )
    if dup:
        return {
            "entity": product_data,
            "homebox_id": dup["id"],
            "existing": True,
            "dry_run": False,
        }

    entity_id = create_homebox_entity(product_data, image_bytes=image_bytes, image_filename=image_filename)
    return {
        "entity": product_data,
        "homebox_id": entity_id,
        "existing": False,
        "dry_run": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Import an item into Homebox from a product URL.")
    parser.add_argument("url", help="Product URL (Amazon, retail, or product page)")
    parser.add_argument("--dry-run", action="store_true", help="Preview extracted data without writing to Homebox")
    parser.add_argument("--name", help="Override item name")
    parser.add_argument("--model", help="Override item model number")

    args = parser.parse_args()

    try:
        res = import_url(
            url=args.url,
            dry_run=args.dry_run,
            name_override=args.name,
            model_override=args.model,
        )
        if res.get("existing"):
            print(f"Item already exists in Homebox: {res['entity']['name']}")
            print(f"Existing Homebox ID: {res['homebox_id']}")
        elif res.get("dry_run"):
            print("[DRY RUN] Extracted product data:")
            print(json.dumps(res["entity"], indent=2))
        else:
            print(f"Successfully imported {res['entity']['name']}")
            print(f"Homebox Entity ID: {res['homebox_id']}")
            print(f"Manufacturer: {res['entity'].get('manufacturer', 'N/A')}")
            print(f"Model Number: {res['entity'].get('model_number', 'N/A')}")
            print(f"Purchase Price: ${res['entity'].get('purchase_price', 'N/A')}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
