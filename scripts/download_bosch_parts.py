"""
Bosch Home Appliances Spare Parts and Assembly Diagram Downloader.
Extracts assembly diagram images and complete bill of materials with callout numbers,
part numbers, descriptions, prices, and availability from Bosch's spare-parts portal.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Upgrade-Insecure-Requests": "1",
}


def fetch_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Fetch URL bytes using browser headers."""
    req = urllib.request.Request(url, headers=headers or BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def extract_bosch_data_from_html(raw_html: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract gallery images and bomRelations from Bosch spare parts HTML."""
    gallery_images: list[dict[str, Any]] = []
    bom_relations: list[dict[str, Any]] = []

    # Look through all <script> blocks for bomRelations
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', raw_html, re.DOTALL):
        s = m.group(1)
        if "bomRelations" in s:
            push_m = re.search(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', s, re.DOTALL)
            if push_m:
                try:
                    unescaped = json.loads(f'"{push_m.group(1)}"', strict=False)
                    brace_idx = unescaped.find('{"variantId"')
                    if brace_idx != -1:
                        decoder = json.JSONDecoder()
                        obj, _ = decoder.raw_decode(unescaped[brace_idx:])
                        gallery_images = obj.get("galleryImages", [])
                        bom_relations = obj.get("bomRelations", [])
                        if gallery_images and bom_relations:
                            break
                except Exception:
                    continue

    return gallery_images, bom_relations


def parse_appliancepartspros_section(section_html: str) -> list[dict[str, Any]]:
    """Extract parts from an AppliancePartsPros section page."""
    parts: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<div class="product-item-num">(\d+)</div>[\s\S]*?'
        r'<div class="product-item-heading">\s*<h3><a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</a>[\s\S]*?'
        r'(?:<strong class="price[^"]*">\s*([$0-9,.]+)\s*</strong>|Out of Stock|Not available)',
        re.IGNORECASE,
    )
    for m in pattern.finditer(section_html):
        callout, link, title, price = m.groups()
        part_m = re.search(r'/bosch-[a-z0-9-]+-(\d+)-ap\d+\.html', link)
        raw_pid = part_m.group(1) if part_m else ""
        pid = raw_pid.zfill(8) if raw_pid else ""
        parts.append({
            "callout": callout,
            "part_number": pid,
            "description": title.strip(),
            "price": price.replace("$", "").strip() if price else "N/A",
            "url": f"https://www.appliancepartspros.com{link}",
            "status": "Available" if price else "Out of Stock / Inquire",
        })
    return parts


def fetch_appliancepartspros_catalog(model_id: str) -> dict[str, dict[str, Any]]:
    """Fetch all sections from AppliancePartsPros for model to enrich BOM descriptions and prices."""
    model_slug = model_id.lower().replace("/", "-")
    index_url = f"https://www.appliancepartspros.com/parts-for-bosch-{model_slug}.html"
    print(f"Fetching parts catalog from {index_url}...")
    try:
        index_html = fetch_url(index_url).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Warning: Could not fetch catalog index: {e}")
        return {}

    # Find section URLs
    section_links = re.findall(
        rf'href=[\'"]([^\'"]*\-parts\-for\-bosch\-{model_slug}\.html)[\'"]',
        index_html,
        re.IGNORECASE,
    )
    section_urls = list(set(urllib.parse.urljoin("https://www.appliancepartspros.com", href) for href in section_links))
    print(f"Found {len(section_urls)} catalog sections on AppliancePartsPros.")

    catalog: dict[str, dict[str, Any]] = {}
    for url in section_urls:
        try:
            sec_html = fetch_url(url).decode("utf-8", errors="ignore")
            sec_parts = parse_appliancepartspros_section(sec_html)
            for p in sec_parts:
                pid = p["part_number"]
                if pid and pid not in catalog:
                    catalog[pid] = p
            time.sleep(0.5)
        except Exception as e:
            print(f"Warning fetching section {url}: {e}")

    print(f"Enriched catalog with {len(catalog)} part descriptions and prices.")
    return catalog


def generate_markdown_bom(variant_id: str, sections_data: list[dict[str, Any]]) -> str:
    """Format bill of materials into human-readable Markdown with diagram links."""
    total_parts = sum(len(s.get("parts", [])) for s in sections_data)
    lines = [
        f"# Bill of Materials — Bosch {variant_id}",
        "",
        f"- **Model / Variant**: `{variant_id}`",
        f"- **Source**: [Bosch Spare Parts List](https://www.bosch-home.com/us/en/spare-parts-list/{variant_id.replace('/', '-')})",
        f"- **Total Diagram Sections**: {len(sections_data)}",
        f"- **Total Parts Cataloged**: {total_parts}",
        "",
        "---",
        "",
    ]

    for s in sections_data:
        sec_num = s["section_num"]
        diagram_file = s.get("diagram_file", "")
        lines.extend([
            f"## Diagram Section {sec_num}",
            "",
            f"**Diagram Image**: [`{diagram_file}`](diagrams/{diagram_file})",
            "",
            "| Callout # | Part Number | Description | Price | Status |",
            "|---|---|---|---|---|",
        ])

        parts = s.get("parts", [])
        if not parts:
            lines.append("| — | — | No parts listed | — | — |")
        else:
            for p in parts:
                p_num = f"[`{p['part_number']}`]({p['url']})" if p.get("url") else f"`{p['part_number']}`"
                desc = p["description"].replace("|", "\\|") if p["description"] else "—"
                price_str = f"${p['price']}" if p["price"] != "N/A" else "N/A"
                lines.append(f"| {p['callout']} | {p_num} | {desc} | {price_str} | {p['status']} |")

        lines.extend(["", "---", ""])

    return "\n".join(lines)


def generate_csv_bom(sections_data: list[dict[str, Any]]) -> str:
    """Format bill of materials into CSV."""
    output = []
    output.append(
        "Diagram Section,Callout,Part Number,Description,Price,Status,Diagram File"
    )
    for s in sections_data:
        sec_num = s["section_num"]
        diagram_file = s.get("diagram_file", "")
        for p in s.get("parts", []):
            callout = p["callout"]
            p_num = p["part_number"]
            desc = p["description"].replace('"', '""')
            price = p["price"]
            status = p["status"]
            output.append(
                f'{sec_num},{callout},{p_num},"{desc}",{price},{status},{diagram_file}'
            )
    return "\n".join(output) + "\n"


def download_bosch_parts(
    variant_id: str = "SHXM98W75N-01",
    output_dir: Path | str = "appliances/SHXM98W75N-01",
) -> dict[str, Any]:
    """Orchestrate downloading diagrams and cataloging BOM from Bosch."""
    out_path = Path(output_dir)
    diagrams_dir = out_path / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    url_variant = variant_id.replace("/", "-")
    url = f"https://www.bosch-home.com/us/en/spare-parts-list/{url_variant}"
    print(f"Fetching Bosch spare parts page: {url}...")
    cache_file = Path(f"/tmp/bosch_{variant_id.replace('/', '_').replace('-', '_')}.html")
    if cache_file.exists():
        print(f"Using cached page from {cache_file}...")
        html_content = cache_file.read_text(encoding="utf-8", errors="ignore")
    else:
        try:
            html_content = fetch_url(url).decode("utf-8", errors="ignore")
        except Exception as e:
            if cache_file.exists():
                print(f"Fetch failed ({e}), falling back to cached {cache_file}...")
                html_content = cache_file.read_text(encoding="utf-8", errors="ignore")
            else:
                raise

    gallery_images, bom_relations = extract_bosch_data_from_html(html_content)
    if not gallery_images or not bom_relations:
        raise ValueError(f"Failed to extract gallery images or bomRelations from {url}")

    print(f"Found {len(gallery_images)} diagram images and {len(bom_relations)} BOM relations.")

    # 1. Download diagram images
    diagram_files: dict[str, str] = {}
    for img in gallery_images:
        pos = img.get("positionNumber", "01")
        img_url = img.get("url", "")
        filename = f"{pos}_diagram.png"
        file_path = diagrams_dir / filename
        diagram_files[pos] = filename
        if not file_path.exists() and img_url:
            print(f"Downloading diagram {pos}: {img_url}...")
            img_bytes = fetch_url(img_url)
            file_path.write_bytes(img_bytes)
            print(f"Saved {filename} ({len(img_bytes)} bytes)")
        else:
            print(f"Diagram {pos} exists: {filename}")

    # 2. Enrich parts metadata from catalog
    catalog = fetch_appliancepartspros_catalog(variant_id)

    # 3. Group by diagram section
    sections_map: dict[str, list[dict[str, Any]]] = {}
    for img in gallery_images:
        sections_map[img.get("positionNumber", "01")] = []

    for r in bom_relations:
        pos = r.get("positionNumber", "0100")
        sec_num = pos[:2]
        pid = r.get("productId", "")
        cat_info = catalog.get(pid, {})
        desc = cat_info.get("description", "")
        price = cat_info.get("price", "N/A")
        status = cat_info.get("status", "Available")
        url_link = cat_info.get("url", "")

        part_entry = {
            "callout": pos,
            "part_number": pid,
            "description": desc,
            "price": price,
            "status": status,
            "url": url_link,
        }
        if sec_num not in sections_map:
            sections_map[sec_num] = []
        sections_map[sec_num].append(part_entry)

    # Sort parts within sections by callout number
    sections_data = []
    for sec_num in sorted(sections_map.keys()):
        parts = sorted(sections_map[sec_num], key=lambda x: x["callout"])
        sections_data.append({
            "section_num": sec_num,
            "diagram_file": diagram_files.get(sec_num, f"{sec_num}_diagram.png"),
            "parts": parts,
        })

    # 4. Save JSON BOM
    json_path = out_path / "bill_of_materials.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "variant_id": variant_id,
                "source_url": url,
                "sections": sections_data,
            },
            f,
            indent=2,
        )
    print(f"\nSaved JSON BOM: {json_path}")

    # 5. Save CSV BOM
    csv_path = out_path / "bill_of_materials.csv"
    csv_path.write_text(generate_csv_bom(sections_data), encoding="utf-8")
    print(f"Saved CSV BOM: {csv_path}")

    # 6. Save Markdown BOM
    md_path = out_path / "bill_of_materials.md"
    md_path.write_text(generate_markdown_bom(variant_id, sections_data), encoding="utf-8")
    print(f"Saved Markdown BOM: {md_path}")

    return {
        "variant_id": variant_id,
        "sections": sections_data,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "md_path": str(md_path),
        "diagrams_dir": str(diagrams_dir),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Download Bosch spare parts diagrams and Bill of Materials."
    )
    parser.add_argument(
        "target",
        help="Bosch Variant ID (e.g. SHXM98W75N-01 or SHXM98W75N/01) or full URL",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="Destination directory (default: appliances/<VARIANT_ID>)",
    )

    args = parser.parse_args()

    target = args.target.strip()
    if "spare-parts-list/" in target:
        variant_id = target.split("spare-parts-list/")[-1].strip("/").split("?")[0]
    else:
        variant_id = target.split("/")[-1].strip()

    output_dir = args.output_dir or f"appliances/{variant_id.replace('/', '-')}"

    try:
        download_bosch_parts(variant_id=variant_id, output_dir=output_dir)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
