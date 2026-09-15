"""
RepairClinic Parts and Assembly Diagram Downloader.
Extracts assembly diagrams and bill of materials from RepairClinic / BAPG schematics API.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BAPG_API_BASE = "https://bapg.azure-api.net/bapg-repair-intelligence-schematics"

API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://diagrams.bapgparts.com",
    "Referer": "https://diagrams.bapgparts.com/",
}


def fetch_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Fetch URL bytes using headers."""
    req = urllib.request.Request(url, headers=headers or API_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_api_json(path: str) -> dict[str, Any]:
    """Fetch JSON from BAPG API endpoint."""
    url = f"{BAPG_API_BASE}{path}"
    raw_bytes = fetch_url(url)
    return json.loads(raw_bytes.decode("utf-8"))


def extract_model_id_from_target(target: str) -> str:
    """Extract numeric model/product ID from URL or raw string."""
    m = re.search(r'ProductDetail/(\d+)', target, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'models?/(\d+)', target, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'^\d+$', target.strip())
    if m:
        return m.group(0)
    raise ValueError(f"Could not extract numeric model ID from target: {target}")


def parse_diagram_details(raw_diagram: dict[str, Any]) -> dict[str, Any]:
    """Normalize diagram and parts structure from BAPG API."""
    diagram_id = raw_diagram.get("diagram_id")
    name = raw_diagram.get("name", f"Diagram {diagram_id}")
    large_image_url = (
        raw_diagram.get("large_image_url")
        or raw_diagram.get("image_url")
        or ""
    )

    parts: list[dict[str, Any]] = []
    for p in raw_diagram.get("parts", []):
        callout = p.get("order_tag") or ""
        part_num = p.get("oem_number") or p.get("bapg_part_number") or ""
        title = p.get("title") or ""
        description = p.get("description") or ""

        price_val = p.get("price")
        if isinstance(price_val, (int, float)):
            price = f"{price_val:.2f}"
        elif price_val is not None and str(price_val).strip():
            price = str(price_val).strip().lstrip("$")
        else:
            price = "N/A"

        if p.get("in_stock"):
            status = "In Stock"
        elif p.get("is_nla"):
            status = "NLA"
        else:
            status = "Out of Stock"

        parts.append(
            {
                "callout": callout,
                "part_number": part_num,
                "title": title,
                "description": description,
                "price": price,
                "status": status,
                "part_id": p.get("part_id"),
            }
        )

    return {
        "diagram_id": diagram_id,
        "name": name,
        "large_image_url": large_image_url,
        "parts": parts,
    }


def generate_markdown_bom(model_name: str, diagrams_data: list[dict[str, Any]]) -> str:
    """Generate markdown bill of materials."""
    lines = [
        f"# Bill of Materials — LG {model_name}",
        "",
        f"- **Model**: `{model_name}`",
        f"- **Total Assemblies / Diagrams**: {len(diagrams_data)}",
        f"- **Total Parts Cataloged**: {sum(len(d.get('parts', [])) for d in diagrams_data)}",
        "",
        "---",
        "",
    ]

    for idx, d in enumerate(diagrams_data, 1):
        name = d.get("name", f"Diagram {idx}")
        diagram_file = d.get("diagram_file", "")
        parts = d.get("parts", [])

        lines.append(f"## {name}")
        lines.append("")
        if diagram_file:
            lines.append(f"**Diagram Image**: [`{diagram_file}`](diagrams/{diagram_file})")
            lines.append("")

        lines.append("| Callout # | Part Number | Title | Description | Price | Status |")
        lines.append("|---|---|---|---|---|---|")

        for p in parts:
            callout = p.get("callout", "")
            part_num = p.get("part_number", "")
            title = p.get("title", "")
            desc = p.get("description", "—")
            price = p.get("price", "N/A")
            status = p.get("status", "Available")

            if price != "N/A" and not price.startswith("$"):
                price_str = f"${price}"
            else:
                price_str = price

            link_str = (
                f"[`{part_num}`](https://www.repairclinic.com/Shop-For-Parts?query={part_num})"
                if part_num
                else "—"
            )
            lines.append(
                f"| {callout} | {link_str} | {title} | {desc} | {price_str} | {status} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_csv_bom(diagrams_data: list[dict[str, Any]]) -> str:
    """Generate CSV string for bill of materials."""
    lines = [
        "Diagram ID,Diagram Name,Callout,Part Number,Title,Description,Price,Status,Diagram File"
    ]

    for d in diagrams_data:
        diagram_id = d.get("diagram_id", "")
        diagram_name = d.get("name", "").replace('"', '""')
        diagram_file = d.get("diagram_file", "")

        for p in d.get("parts", []):
            callout = p.get("callout", "")
            part_num = p.get("part_number", "")
            title = p.get("title", "").replace('"', '""')
            desc = p.get("description", "").replace('"', '""')
            price = p.get("price", "").lstrip("$")
            status = p.get("status", "")

            lines.append(
                f'{diagram_id},"{diagram_name}",{callout},{part_num},"{title}","{desc}",{price},{status},{diagram_file}'
            )

    return "\n".join(lines) + "\n"


def download_repairclinic_parts(
    target: str,
    output_dir: Path | str | None = None,
    model_name: str | None = None,
) -> Path:
    """Download diagrams and parts from RepairClinic."""
    model_id = extract_model_id_from_target(target)

    # 1. Fetch model info
    print(f"Fetching model info for ID {model_id}...")
    model_info = fetch_api_json(f"/model/{model_id}?api-version=v1")
    resolved_model = model_name or model_info.get("name") or f"Model_{model_id}"

    # Standard clean directory name (e.g. WT7800CW/00 -> WT7800CW)
    clean_slug = re.sub(r'/00$', '', resolved_model)
    clean_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_slug)
    out_path = Path(output_dir) if output_dir else Path(f"appliances/{clean_slug}")
    diagrams_dir = out_path / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    # 2. Fetch diagrams list
    print(f"Fetching diagrams list for model {resolved_model} (ID: {model_id})...")
    diagrams_list_resp = fetch_api_json(f"/models/{model_id}/diagrams?api-version=v1")
    diagrams_list = diagrams_list_resp.get("diagrams", [])
    print(f"Found {len(diagrams_list)} diagrams.")

    # Sort diagrams by page number if found in large_image_url
    def page_sorter(d: dict[str, Any]) -> tuple[int, int]:
        url = d.get("large_image_url", "")
        m = re.search(r'page_(\d+)', url)
        page_num = int(m.group(1)) if m else 999
        return (page_num, d.get("diagram_id", 0))

    sorted_diagrams = sorted(diagrams_list, key=page_sorter)

    diagrams_data: list[dict[str, Any]] = []

    for idx, d_stub in enumerate(sorted_diagrams, 1):
        d_id = d_stub["diagram_id"]
        print(f"[{idx}/{len(sorted_diagrams)}] Fetching details for diagram {d_id}...")
        raw_details = fetch_api_json(f"/diagrams/{d_id}?api-version=v1")
        details = parse_diagram_details(raw_details)

        name = details["name"]
        large_url = details["large_image_url"]

        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', name).strip('_')
        slug = re.sub(r'_+', '_', slug)
        diagram_filename = f"{idx:02d}_{slug}.jpg"
        diagram_path = diagrams_dir / diagram_filename

        if large_url:
            print(f"  Downloading diagram: {large_url}")
            img_bytes = fetch_url(large_url)
            diagram_path.write_bytes(img_bytes)
            print(f"  Saved diagram ({len(img_bytes) / 1024:.1f} KB) -> {diagram_path}")
        else:
            print(f"  Warning: No image URL for {name}")

        details["diagram_file"] = diagram_filename
        diagrams_data.append(details)
        time.sleep(0.5)

    # Save JSON BOM
    json_path = out_path / "bill_of_materials.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": resolved_model,
                "model_id": model_id,
                "diagrams": diagrams_data,
            },
            f,
            indent=2,
        )
    print(f"Saved JSON BOM -> {json_path}")

    # Save CSV BOM
    csv_path = out_path / "bill_of_materials.csv"
    csv_content = generate_csv_bom(diagrams_data)
    csv_path.write_text(csv_content, encoding="utf-8")
    print(f"Saved CSV BOM -> {csv_path}")

    # Save Markdown BOM
    md_path = out_path / "bill_of_materials.md"
    md_content = generate_markdown_bom(resolved_model, diagrams_data)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Saved Markdown BOM -> {md_path}")

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download RepairClinic appliance assembly diagrams and bill of materials"
    )
    parser.add_argument(
        "target", help="RepairClinic URL or numeric model ID (e.g. 2453006)"
    )
    parser.add_argument("--model", default=None, help="Model name override")
    parser.add_argument(
        "--outdir", "--output-dir", "-o", default=None, help="Output directory"
    )
    args = parser.parse_args()

    download_repairclinic_parts(args.target, output_dir=args.outdir, model_name=args.model)


if __name__ == "__main__":
    main()
