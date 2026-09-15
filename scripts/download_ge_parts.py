"""
GE Appliance Parts Assembly Diagram and Bill of Materials Downloader.
Downloads high-resolution assembly diagrams and extracts the complete
bill of materials (parts, callout numbers, prices, descriptions, substitutes).
"""
from __future__ import annotations

import argparse
import csv
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
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Fetch URL bytes using browser headers."""
    req = urllib.request.Request(url, headers=headers or BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def extract_assemblies_from_model_html(model_html: str) -> list[dict[str, Any]]:
    """Extract assembly sections and diagram image URLs from GE model assembly page."""
    assemblies: list[dict[str, Any]] = []

    # Pattern for assembly cards/links
    # Matches href="/store/parts/ModelSectionParts/<MODEL>/<NUM>/.../<NAME>"
    pattern = re.compile(
        r'<a[^>]+href=[\'"]([^\'"]*ModelSectionParts/[^/]+/(\d+)/[^/]+/[^/]+/[^/]+/([^/\'"]+))[\'"][^>]*>([\s\S]*?)</a>',
        re.IGNORECASE,
    )

    seen_sections: set[int] = set()

    for match in pattern.finditer(model_html):
        rel_url, section_num_str, section_name, inner_content = match.groups()
        section_num = int(section_num_str)
        if section_num in seen_sections:
            continue
        seen_sections.add(section_num)

        # Full section URL
        full_url = urllib.parse.urljoin("https://www.geapplianceparts.com", rel_url)

        # Look for thumbnail image
        img_match = re.search(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', inner_content)
        thumb_url = img_match.group(1) if img_match else ""
        if thumb_url and not thumb_url.startswith("http"):
            thumb_url = urllib.parse.urljoin("https://assets.geappliances.io", thumb_url)

        # Construct high-res diagram URL (replace _480.jpg or _96.jpg with _2325.jpg)
        highres_url = ""
        if thumb_url:
            highres_url = re.sub(r"_\d+\.jpg$", "_2325.jpg", thumb_url)
            # If thumb URL had /480/ or /96/ directory, remove size folder for high-res
            highres_url = re.sub(r"/(?:480|96|300)/", "/", highres_url)

        assemblies.append(
            {
                "section_num": section_num,
                "name": section_name,
                "url": full_url,
                "diagram_thumb_url": thumb_url,
                "diagram_highres_url": highres_url,
            }
        )

    assemblies.sort(key=lambda x: x["section_num"])
    return assemblies


def parse_section_parts(section_html: str) -> list[dict[str, Any]]:
    """Extract all part entries from a GE assembly section HTML page."""
    parts: list[dict[str, Any]] = []

    # Split by diagram number blocks: <strong>X</strong> &mdash; Diagram Number
    blocks = re.findall(
        r"<strong>\s*(\d+)\s*</strong>\s*(?:&mdash;|—|-)\s*Diagram Number([\s\S]*?)(?=<strong>\s*\d+\s*</strong>\s*(?:&mdash;|—|-)\s*Diagram Number|$)",
        section_html,
        re.IGNORECASE,
    )

    for callout, block in blocks:
        # Part link & description
        part_link = re.search(
            r'href=[\'"]/store/parts/spec/([^\'"]+)[\'"][^>]*>([\s\S]*?)</a>',
            block,
            re.IGNORECASE,
        )
        part_num = part_link.group(1).strip() if part_link else ""
        desc_raw = part_link.group(2).strip() if part_link else ""
        desc = html.unescape(re.sub(r"<[^>]+>", " ", desc_raw)).strip()
        desc = " ".join(desc.split())

        # Fallback part number from <p> if not in link
        if not part_num:
            p_num = re.search(r"<p[^>]*>\s*([A-Z0-9]{5,15})\s*</p>", block)
            if p_num:
                part_num = p_num.group(1).strip()

        # Price
        price_m = re.search(
            r'class=[\'"]bold-price[\'"][^>]*>.*?\$?([0-9,.]+)',
            block,
            re.IGNORECASE,
        )
        price = price_m.group(1).replace(",", "") if price_m else "N/A"

        # Status / Availability
        status = "Available"
        if "no longer available" in block.lower():
            status = "No longer available"
        elif "substituted by" in block.lower() or "replaces" in block.lower():
            status = "Substituted"
        elif price == "N/A" and "backorder" in block.lower():
            status = "Backordered"
        elif price == "N/A":
            status = "Unavailable / Inquire"

        parts.append(
            {
                "callout": callout,
                "part_number": part_num,
                "description": desc,
                "price": price,
                "status": status,
                "spec_url": f"https://www.geapplianceparts.com/store/parts/spec/{part_num}"
                if part_num
                else "",
            }
        )

    return parts


def generate_markdown_bom(model_id: str, assemblies_data: list[dict[str, Any]]) -> str:
    """Format bill of materials into human-readable Markdown with diagram links."""
    lines = [
        f"# Bill of Materials — GE {model_id}",
        "",
        f"- **Model**: `{model_id}`",
        f"- **Source**: [GE Appliance Parts Assembly](https://www.geapplianceparts.com/store/parts/assembly/{model_id})",
        f"- **Total Assembly Sections**: {len(assemblies_data)}",
        f"- **Total Parts Cataloged**: {sum(len(a.get('parts', [])) for a in assemblies_data)}",
        "",
        "---",
        "",
    ]

    for a in assemblies_data:
        sec_num = a["section_num"]
        sec_name = a["name"].replace("_", " ").title()
        diagram_file = a.get("diagram_file", "")

        lines.extend([
            f"## {sec_num}. {sec_name}",
            "",
            f"**Diagram**: [`{diagram_file}`](diagrams/{diagram_file})",
            "",
            "| Callout # | Part Number | Description | Price | Status |",
            "|---|---|---|---|---|",
        ])

        parts = a.get("parts", [])
        if not parts:
            lines.append("| — | — | No parts listed | — | — |")
        else:
            for p in parts:
                p_num = f"[`{p['part_number']}`]({p['spec_url']})" if p.get("spec_url") else f"`{p['part_number']}`"
                desc = p["description"].replace("|", "\\|")
                price_str = f"${p['price']}" if p["price"] != "N/A" else "N/A"
                lines.append(f"| {p['callout']} | {p_num} | {desc} | {price_str} | {p['status']} |")

        lines.extend(["", "---", ""])

    return "\n".join(lines)


def generate_csv_bom(assemblies_data: list[dict[str, Any]]) -> str:
    """Format bill of materials into CSV format."""
    output = []
    output.append(
        "Section Number,Section Name,Callout,Part Number,Description,Price,Status,Diagram File,Spec URL"
    )
    for a in assemblies_data:
        sec_num = str(a["section_num"])
        sec_name = a["name"]
        diagram_file = a.get("diagram_file", "")
        for p in a.get("parts", []):
            callout = p["callout"]
            p_num = p["part_number"]
            desc = p["description"].replace('"', '""')
            price = p["price"]
            status = p["status"]
            spec_url = p.get("spec_url", "")
            output.append(
                f'{sec_num},{sec_name},{callout},{p_num},"{desc}",{price},{status},{diagram_file},{spec_url}'
            )
    return "\n".join(output) + "\n"


def download_ge_parts(
    model_id: str,
    output_dir: Path | str = "appliances/JT5500SF1SS",
    delay: float = 1.0,
) -> dict[str, Any]:
    """Orchestrate downloading diagrams and extracting complete BOM."""
    out_path = Path(output_dir)
    diagrams_dir = out_path / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch model page
    model_url = f"https://www.geapplianceparts.com/store/parts/assembly/{model_id}"
    print(f"Fetching model assembly index: {model_url}...")
    model_html = fetch_url(model_url).decode("utf-8", errors="ignore")

    assemblies = extract_assemblies_from_model_html(model_html)
    print(f"Found {len(assemblies)} assembly sections.")

    assemblies_data = []

    # 2. Iterate each assembly
    for idx, a in enumerate(assemblies, 1):
        sec_num = a["section_num"]
        sec_name = a["name"]
        slug = f"{sec_num:02d}_{sec_name}.jpg"
        diagram_path = diagrams_dir / slug

        print(f"\n[{idx}/{len(assemblies)}] Section {sec_num}: {sec_name}")

        # Download high-res diagram
        if not diagram_path.exists():
            img_url = a["diagram_highres_url"] or a["diagram_thumb_url"]
            print(f"  Downloading diagram: {img_url}...")
            try:
                img_bytes = fetch_url(img_url)
                diagram_path.write_bytes(img_bytes)
                print(f"  Saved {slug} ({len(img_bytes)} bytes)")
            except Exception as e:
                print(f"  High-res failed ({e}), trying thumbnail fallback...")
                if a["diagram_thumb_url"]:
                    img_bytes = fetch_url(a["diagram_thumb_url"])
                    diagram_path.write_bytes(img_bytes)
                    print(f"  Saved thumbnail {slug} ({len(img_bytes)} bytes)")
        else:
            print(f"  Diagram already exists: {slug}")

        a["diagram_file"] = slug

        # Fetch section parts HTML
        print(f"  Fetching parts from: {a['url']}...")
        section_html = fetch_url(a["url"]).decode("utf-8", errors="ignore")
        parts = parse_section_parts(section_html)
        print(f"  Extracted {len(parts)} parts.")
        a["parts"] = parts
        assemblies_data.append(a)

        time.sleep(delay)

    # 3. Save JSON BOM
    json_path = out_path / "bill_of_materials.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model_id": model_id,
                "source_url": model_url,
                "assemblies": assemblies_data,
            },
            f,
            indent=2,
        )
    print(f"\nSaved structured JSON BOM: {json_path}")

    # 4. Save CSV BOM
    csv_path = out_path / "bill_of_materials.csv"
    csv_path.write_text(generate_csv_bom(assemblies_data), encoding="utf-8")
    print(f"Saved CSV BOM: {csv_path}")

    # 5. Save Markdown BOM
    md_path = out_path / "bill_of_materials.md"
    md_path.write_text(generate_markdown_bom(model_id, assemblies_data), encoding="utf-8")
    print(f"Saved Markdown BOM: {md_path}")

    return {
        "model_id": model_id,
        "assemblies": assemblies_data,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "md_path": str(md_path),
        "diagrams_dir": str(diagrams_dir),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Download GE Appliance Parts diagrams and Bill of Materials."
    )
    parser.add_argument(
        "target",
        help="GE Model number (e.g. JT5500SF1SS) or full assembly URL",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="Destination directory (default: appliances/<MODEL_ID>)",
    )

    args = parser.parse_args()

    # Extract model id from target if full URL was provided
    target = args.target.strip()
    if "assembly/" in target:
        model_id = target.split("assembly/")[-1].strip("/").split("?")[0]
    else:
        model_id = target.split("/")[-1].strip()

    output_dir = args.output_dir or f"appliances/{model_id}"

    try:
        download_ge_parts(model_id=model_id, output_dir=output_dir)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
