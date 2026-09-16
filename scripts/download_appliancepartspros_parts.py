"""
AppliancePartsPros Parts and Assembly Diagram Downloader.
Downloads high-resolution assembly diagrams and extracts complete bill of materials
(parts, callout tags, part numbers, titles, pricing, availability) from AppliancePartsPros.
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


def extract_model_from_url(url: str) -> str:
    """Extract model ID from AppliancePartsPros URL."""
    clean_url = url.split("?")[0]
    m = re.search(r'parts-for-(?:[a-z]+-)?([a-z0-9-]+)\.html', clean_url, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    raise ValueError(f"Could not extract model from URL: {url}")


def parse_sections_from_index_html(index_html: str) -> list[dict[str, Any]]:
    """Extract diagram section links and names from main parts index HTML."""
    sections: list[dict[str, Any]] = []

    pattern = re.compile(
        r'<div class=[\'"]diagram-part-box[^\'\"]*[\'"]>[\s\S]*?'
        r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>[\s\S]*?'
        r'<img[^>]+src=[\'"]([^\'"]+)[\'"][^>]*>[\s\S]*?'
        r'<strong class=[\'"]title[\'"]>\s*([^<]+)</strong>',
        re.IGNORECASE,
    )

    for m in pattern.finditer(index_html):
        href, thumb_url, title = m.groups()
        full_url = urllib.parse.urljoin("https://www.appliancepartspros.com", href)
        sections.append(
            {
                "name": html.unescape(title.strip()),
                "url": full_url,
                "thumb_url": thumb_url.strip(),
            }
        )

    return sections


def parse_section_page(section_html: str) -> dict[str, Any]:
    """Parse diagram URL and parts list from a diagram section page."""
    # 1. Diagram image URL (prefer _8.gif high-res)
    diag_m = re.search(
        r'id=[\'"][^\'"]*iDiagramFull2[^\'"]*[\'"][^>]+src=[\'"]([^\'"]+)[\'"]',
        section_html,
        re.IGNORECASE,
    ) or re.search(
        r'src=[\'"]([^\'"]+)[\'"][^>]+id=[\'"][^\'"]*iDiagramFull2[^\'"]*[\'"]',
        section_html,
        re.IGNORECASE,
    ) or re.search(
        r'https?://[^\s\"\'<>]+(?:diagram/00\d+_8\.gif)',
        section_html,
        re.IGNORECASE,
    )

    if diag_m:
        diagram_url = diag_m.group(1) if hasattr(diag_m, "group") and diag_m.lastindex else diag_m.group(0)
    else:
        # Fallback to iDiagramFull or any diagram and upgrade to _8.gif
        fallback_m = re.search(r'https?://[^\s\"\'<>]+(?:diagram/00\d+_\d+\.gif)', section_html, re.IGNORECASE)
        if fallback_m:
            diagram_url = re.sub(r'_\d+\.gif', '_8.gif', fallback_m.group(0))
        else:
            diagram_url = ""

    # 2. Extract pricing map from dataLayer
    pricing: dict[str, str] = {}
    for m in re.finditer(
        r'items\':\s*\[\s*\{\s*\'item_id\':\s*\'([^\']+)\'[\s\S]*?\'price\':\s*([0-9.]+)',
        section_html,
    ):
        pid, pr = m.groups()
        pricing[pid.strip().upper()] = pr.strip()

    # 3. Extract parts
    parts: list[dict[str, Any]] = []
    part_blocks = re.finditer(
        r'<div class=[\'"]product-item[\'"]>([\s\S]*?)</div>\s*</div>\s*</div>',
        section_html,
    )

    for block_match in part_blocks:
        block = block_match.group(1)
        num_m = re.search(r'<div class=[\'"]product-item-num[\'"]>([^<]+)</div>', block)
        callout = num_m.group(1).strip() if num_m else ""

        link_m = re.search(
            r'<a[^>]+href=[\'"]([^\'"]+-[a-z0-9]+-(ap\d+)\.html)[\'\"][^>]*>([^<]+)</a>',
            block,
            re.IGNORECASE,
        )
        if not link_m:
            continue

        link, ap_id, title = link_m.groups()
        ap_id_upper = ap_id.upper()

        # Extract MPN / OEM part number from link
        mpn_m = re.search(r'-([a-z0-9]+)-ap\d+\.html', link, re.IGNORECASE)
        part_number = mpn_m.group(1).upper() if mpn_m else ""

        price = pricing.get(ap_id_upper, "N/A")
        if price != "N/A":
            status = "In Stock"
        elif "not-available" in block or 'class="ships-info-row na"' in block:
            status = "Not Available"
        else:
            status = "Inquire"

        parts.append(
            {
                "callout": callout,
                "part_number": part_number,
                "ap_id": ap_id_upper,
                "title": html.unescape(title.strip()),
                "price": price,
                "status": status,
                "url": urllib.parse.urljoin("https://www.appliancepartspros.com", link),
            }
        )

    return {
        "diagram_url": diagram_url,
        "parts": parts,
    }


def generate_markdown_bom(model_name: str, sections_data: list[dict[str, Any]]) -> str:
    """Generate comprehensive markdown bill of materials."""
    lines = [
        f"# Bill of Materials — Panasonic {model_name}",
        "",
        f"- **Model**: `{model_name}`",
        f"- **Total Assemblies / Diagrams**: {len(sections_data)}",
        f"- **Total Parts Cataloged**: {sum(len(s.get('parts', [])) for s in sections_data)}",
        "",
        "---",
        "",
    ]

    for idx, s in enumerate(sections_data, 1):
        name = s.get("name", f"Section {idx}")
        diagram_file = s.get("diagram_file", "")
        parts = s.get("parts", [])

        lines.append(f"## {name}")
        lines.append("")
        if diagram_file:
            lines.append(f"**Diagram Image**: [`{diagram_file}`](diagrams/{diagram_file})")
            lines.append("")

        lines.append("| Callout # | Part Number | AP Part # | Title | Price | Status |")
        lines.append("|---|---|---|---|---|---|")

        for p in parts:
            callout = p.get("callout", "")
            part_num = p.get("part_number", "")
            ap_id = p.get("ap_id", "")
            title = p.get("title", "—")
            price = p.get("price", "N/A")
            status = p.get("status", "Available")
            url = p.get("url", "")

            if price != "N/A" and not price.startswith("$"):
                price_str = f"${price}"
            else:
                price_str = price

            link_str = f"[`{part_num}`]({url})" if url and part_num else part_num

            lines.append(
                f"| {callout} | {link_str} | `{ap_id}` | {title} | {price_str} | {status} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_csv_bom(sections_data: list[dict[str, Any]]) -> str:
    """Generate CSV string from bill of materials."""
    lines = [
        "Section Name,Callout,Part Number,AP Part Number,Title,Price,Status,Diagram File"
    ]

    for s in sections_data:
        sec_name = s.get("name", "").replace('"', '""')
        diagram_file = s.get("diagram_file", "")

        for p in s.get("parts", []):
            callout = p.get("callout", "")
            part_num = p.get("part_number", "")
            ap_id = p.get("ap_id", "")
            title = p.get("title", "").replace('"', '""')
            price = p.get("price", "").lstrip("$")
            status = p.get("status", "")

            lines.append(
                f'"{sec_name}",{callout},{part_num},{ap_id},"{title}",{price},{status},{diagram_file}'
            )

    return "\n".join(lines) + "\n"


def download_appliancepartspros_parts(
    target_url: str,
    output_dir: Path | str | None = None,
    model_name: str | None = None,
) -> Path:
    """Download diagrams and parts from AppliancePartsPros."""
    clean_target = target_url.split("?")[0]
    extracted_model = extract_model_from_url(clean_target)
    resolved_model = model_name or extracted_model

    out_path = Path(output_dir) if output_dir else Path(f"appliances/{resolved_model}")
    diagrams_dir = out_path / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching parts index from {clean_target}...")
    index_html = fetch_url(clean_target).decode("utf-8", errors="ignore")
    sections = parse_sections_from_index_html(index_html)
    print(f"Found {len(sections)} diagram sections.")

    sections_data: list[dict[str, Any]] = []

    for idx, sec in enumerate(sections, 1):
        sec_name = sec["name"]
        sec_url = sec["url"]
        print(f"[{idx}/{len(sections)}] Fetching details for section: {sec_name} ({sec_url})...")

        sec_html = fetch_url(sec_url).decode("utf-8", errors="ignore")
        parsed = parse_section_page(sec_html)

        diagram_url = parsed["diagram_url"]
        ext = ".gif"
        if diagram_url:
            ext_m = re.search(r'\.(gif|jpg|jpeg|png)', diagram_url, re.I)
            if ext_m:
                ext = f".{ext_m.group(1).lower()}"

        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', sec_name).strip('_')
        slug = re.sub(r'_+', '_', slug)
        diagram_filename = f"{idx:02d}_{slug}{ext}"
        diagram_path = diagrams_dir / diagram_filename

        if diagram_url:
            print(f"  Downloading high-res diagram: {diagram_url}")
            img_bytes = fetch_url(diagram_url)
            diagram_path.write_bytes(img_bytes)
            print(f"  Saved diagram ({len(img_bytes) / 1024:.1f} KB) -> {diagram_path}")
        else:
            print(f"  Warning: No diagram URL found for {sec_name}")

        sec_entry = {
            "name": sec_name,
            "url": sec_url,
            "diagram_url": diagram_url,
            "diagram_file": diagram_filename,
            "parts": parsed["parts"],
        }
        sections_data.append(sec_entry)
        time.sleep(0.5)

    # Save JSON BOM
    json_path = out_path / "bill_of_materials.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": resolved_model,
                "source_model": extracted_model,
                "source_url": clean_target,
                "sections": sections_data,
            },
            f,
            indent=2,
        )
    print(f"Saved JSON BOM -> {json_path}")

    # Save CSV BOM
    csv_path = out_path / "bill_of_materials.csv"
    csv_content = generate_csv_bom(sections_data)
    csv_path.write_text(csv_content, encoding="utf-8")
    print(f"Saved CSV BOM -> {csv_path}")

    # Save Markdown BOM
    md_path = out_path / "bill_of_materials.md"
    md_content = generate_markdown_bom(resolved_model, sections_data)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Saved Markdown BOM -> {md_path}")

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download AppliancePartsPros assembly diagrams and bill of materials"
    )
    parser.add_argument("url", help="AppliancePartsPros parts index URL")
    parser.add_argument("--model", default=None, help="Model name override (e.g. NN-SD945S)")
    parser.add_argument(
        "--outdir", "--output-dir", "-o", default=None, help="Output directory"
    )
    args = parser.parse_args()

    download_appliancepartspros_parts(args.url, output_dir=args.outdir, model_name=args.model)


if __name__ == "__main__":
    main()
