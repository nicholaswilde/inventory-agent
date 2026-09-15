"""
LG Appliance Parts Assembly Diagram and Bill of Materials Downloader.
Downloads high-resolution assembly diagrams and extracts the complete
bill of materials (parts, callout numbers, prices, descriptions, availability)
from lgparts.com via ARI backend API.
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

AJAX_ENDPOINT = "https://fridgeparts.us/lgparts/admin_ajax.php"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://lgparts.com",
    "Referer": "https://lgparts.com/",
}


def fetch_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Fetch URL bytes using browser headers."""
    req = urllib.request.Request(url, headers=headers or BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def post_ajax(data: dict[str, str], headers: dict[str, str] | None = None) -> str:
    """Post form data to LG parts AJAX endpoint."""
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req_headers = dict(headers or BROWSER_HEADERS)
    req_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = urllib.request.Request(AJAX_ENDPOINT, data=encoded_data, headers=req_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_assemblies_from_ajax_response(html_str: str) -> list[dict[str, Any]]:
    """Parse list of assemblies from explodedviewassemblynew HTML snippet."""
    assemblies: list[dict[str, Any]] = []

    # Find each li block
    pattern = re.compile(
        r'<li[^>]*class=[\'"][^\'"]*explodedview-assemblyli[^\'"]*[\'"][^>]*>([\s\S]*?)</li>',
        re.IGNORECASE,
    )

    for match in pattern.finditer(html_str):
        li_html = match.group(1)
        id_m = re.search(
            r'class=[\'"][^\'"]*explodedview-assemblyId[^\'"]*[\'"][^>]*value=[\'"]([^\'"]+)[\'"]',
            li_html,
            re.IGNORECASE,
        ) or re.search(
            r'value=[\'"]([^\'"]+)[\'"][^>]*class=[\'"][^\'"]*explodedview-assemblyId[^\'"]*[\'"]',
            li_html,
            re.IGNORECASE,
        )
        name_m = re.search(
            r'class=[\'"][^\'"]*explodedview-assemblyName[^\'"]*[\'"][^>]*>([^<]+)<',
            li_html,
            re.IGNORECASE,
        )
        img_m = re.search(
            r'class=[\'"][^\'"]*explodedview-assemblyImage[^\'"]*[\'"][^>]*src=[\'"]([^\'"]+)[\'"]',
            li_html,
            re.IGNORECASE,
        ) or re.search(
            r'src=[\'"]([^\'"]+)[\'"][^>]*class=[\'"][^\'"]*explodedview-assemblyImage[^\'"]*[\'"]',
            li_html,
            re.IGNORECASE,
        )

        if id_m:
            assembly_id = id_m.group(1).strip()
            name = html.unescape(name_m.group(1).strip()) if name_m else f"Assembly {assembly_id}"
            thumb_url = img_m.group(1).strip() if img_m else ""
            assemblies.append(
                {
                    "assembly_id": assembly_id,
                    "name": name,
                    "thumb_url": thumb_url,
                }
            )

    return assemblies


def parse_assembly_details_response(json_data: dict[str, Any]) -> dict[str, Any]:
    """Parse assembly details and parts list from explodedviewassemblyselectnew response."""
    data = json_data.get("data", {})
    assembly = data.get("assembly", {})
    parts_pricing = data.get("parts", [])

    price_map: dict[str, dict[str, Any]] = {}
    for p in parts_pricing:
        sku = p.get("partNumber")
        if sku:
            price_map[sku.strip().upper()] = p

    name = assembly.get("Name", "")
    image_url = assembly.get("ImageUrl", "")
    assembly_id = str(assembly.get("AssemblyId", ""))

    raw_parts = assembly.get("Parts", [])
    parsed_parts: list[dict[str, Any]] = []

    for raw_p in raw_parts:
        callout = raw_p.get("Tag") or raw_p.get("SortTag") or ""
        sku = (raw_p.get("Sku") or "").strip()
        pricing_info = price_map.get(sku.upper(), {})

        description = (
            raw_p.get("Description")
            or pricing_info.get("description")
            or ""
        ).strip()

        price_raw = pricing_info.get("price")
        if price_raw is not None and str(price_raw).strip():
            price = str(price_raw).strip()
        else:
            price = "N/A"

        status = "Available" if price != "N/A" else "Inquire"

        parsed_parts.append(
            {
                "callout": callout,
                "part_number": sku,
                "description": description,
                "price": price,
                "status": status,
            }
        )

    return {
        "assembly_id": assembly_id,
        "name": name,
        "image_url": image_url,
        "parts": parsed_parts,
    }


def generate_markdown_bom(model_id: str, assemblies_data: list[dict[str, Any]]) -> str:
    """Generate comprehensive Markdown BOM with sections for each assembly."""
    lines = [
        f"# Bill of Materials — LG {model_id}",
        "",
        f"- **Model**: `{model_id}`",
        f"- **Total Assemblies**: {len(assemblies_data)}",
        f"- **Total Parts Cataloged**: {sum(len(a.get('parts', [])) for a in assemblies_data)}",
        "",
        "---",
        "",
    ]

    for idx, a in enumerate(assemblies_data, 1):
        name = a.get("name", f"Assembly {idx}")
        diagram_file = a.get("diagram_file", "")
        parts = a.get("parts", [])

        lines.append(f"## {name}")
        lines.append("")
        if diagram_file:
            lines.append(f"**Diagram Image**: [`{diagram_file}`](diagrams/{diagram_file})")
            lines.append("")

        lines.append("| Callout # | Part Number | Description | Price | Status |")
        lines.append("|---|---|---|---|---|")

        for p in parts:
            callout = p.get("callout", "")
            part_num = p.get("part_number", "")
            desc = p.get("description", "—")
            price = p.get("price", "N/A")
            status = p.get("status", "Available")

            if price != "N/A" and not price.startswith("$"):
                price_str = f"${price}"
            else:
                price_str = price

            lines.append(f"| {callout} | [`{part_num}`](https://lgparts.com/search?q={part_num}) | {desc} | {price_str} | {status} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_csv_bom(assemblies_data: list[dict[str, Any]]) -> str:
    """Generate CSV string from bill of materials."""
    lines = [
        "Assembly ID,Assembly Name,Callout,Part Number,Description,Price,Status,Diagram File"
    ]

    for a in assemblies_data:
        assembly_id = a.get("assembly_id", "")
        assembly_name = a.get("name", "").replace('"', '""')
        diagram_file = a.get("diagram_file", "")

        for p in a.get("parts", []):
            callout = p.get("callout", "")
            part_num = p.get("part_number", "")
            desc = p.get("description", "").replace('"', '""')
            price = p.get("price", "").lstrip("$")
            status = p.get("status", "")
            lines.append(
                f'{assembly_id},"{assembly_name}",{callout},{part_num},"{desc}",{price},{status},{diagram_file}'
            )

    return "\n".join(lines) + "\n"


def fetch_lg_assemblies(parent_id: str, mfg_code: str = "ZEN", shop: str = "lgparts.com") -> list[dict[str, Any]]:
    """Fetch assembly list from backend AJAX."""
    form_data = {
        "action": "explodedviewassemblynew",
        "shop": shop,
        "mfgCode": mfg_code,
        "parentId": parent_id,
    }
    resp_html = post_ajax(form_data)
    return parse_assemblies_from_ajax_response(resp_html)


def fetch_lg_assembly_details(
    parent_id: str, assembly_id: str, mfg_code: str = "ZEN", shop: str = "lgparts.com"
) -> dict[str, Any]:
    """Fetch assembly details (diagram + parts list + prices) from backend AJAX."""
    form_data = {
        "action": "explodedviewassemblyselectnew",
        "shop": shop,
        "mfgCode": mfg_code,
        "parentId": parent_id,
        "assemblyId": assembly_id,
        "zoomlevel": "4",
    }
    resp_text = post_ajax(form_data)
    json_data = json.loads(resp_text)
    return parse_assembly_details_response(json_data)


KNOWN_PARENT_MODELS = {
    "131154": "DLGX7801WE",
    "40660": "LRDCS2603S",
}


def resolve_model_id(parent_id: str, model_id: str | None = None) -> str:
    """Resolve model ID from parent ID or user override."""
    if model_id:
        return model_id
    return KNOWN_PARENT_MODELS.get(parent_id, f"LG_{parent_id}")


def download_lg_parts(
    url_or_parent_id: str,
    model_id: str | None = None,
    output_dir: Path | str | None = None,
    mfg_code: str = "ZEN",
    shop: str = "lgparts.com",
) -> Path:
    """Download diagrams and create BOM files for LG appliance."""
    if "parentId=" in url_or_parent_id:
        parsed_url = urllib.parse.urlparse(url_or_parent_id)
        params = urllib.parse.parse_qs(parsed_url.query)
        parent_id = params.get("parentId", [url_or_parent_id])[0]
        if "mfg" in params:
            mfg_code = params["mfg"][0]
    else:
        parent_id = url_or_parent_id

    final_model_id = resolve_model_id(parent_id, model_id)
    out_path = Path(output_dir) if output_dir else Path(f"appliances/{final_model_id}")
    diagrams_dir = out_path / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching assemblies for parentId={parent_id}, mfg={mfg_code}...")
    assemblies = fetch_lg_assemblies(parent_id, mfg_code=mfg_code, shop=shop)
    print(f"Found {len(assemblies)} assemblies.")

    assemblies_data: list[dict[str, Any]] = []

    for idx, asm in enumerate(assemblies, 1):
        asm_id = asm["assembly_id"]
        asm_name = asm["name"]
        print(f"[{idx}/{len(assemblies)}] Fetching details for assembly {asm_id}: {asm_name}...")

        details = fetch_lg_assembly_details(parent_id, asm_id, mfg_code=mfg_code, shop=shop)
        image_url = details.get("image_url", "")

        # Safe filename for diagram
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', asm_name).strip('_')
        slug = re.sub(r'_+', '_', slug)
        diagram_filename = f"{idx:02d}_{slug}.jpg"
        diagram_path = diagrams_dir / diagram_filename

        if image_url:
            print(f"  Downloading high-res diagram: {image_url}")
            img_bytes = fetch_url(image_url)
            diagram_path.write_bytes(img_bytes)
            print(f"  Saved diagram ({len(img_bytes) / 1024:.1f} KB) -> {diagram_path}")
        else:
            print(f"  Warning: No image URL for {asm_name}")

        details["diagram_file"] = diagram_filename
        details["name"] = asm_name
        assemblies_data.append(details)
        time.sleep(0.5)

    # Save JSON BOM
    json_path = out_path / "bill_of_materials.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": final_model_id,
                "parent_id": parent_id,
                "assemblies": assemblies_data,
            },
            f,
            indent=2,
        )
    print(f"Saved JSON BOM -> {json_path}")

    # Save CSV BOM
    csv_path = out_path / "bill_of_materials.csv"
    csv_content = generate_csv_bom(assemblies_data)
    csv_path.write_text(csv_content, encoding="utf-8")
    print(f"Saved CSV BOM -> {csv_path}")

    # Save Markdown BOM
    md_path = out_path / "bill_of_materials.md"
    md_content = generate_markdown_bom(final_model_id, assemblies_data)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Saved Markdown BOM -> {md_path}")

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download LG appliance parts and assembly diagrams")
    parser.add_argument("url", help="LGParts assembly URL or parentId")
    parser.add_argument("--model", default=None, help="Model ID (e.g. LRDCS2603S, DLGX7801WE)")
    parser.add_argument("--outdir", "--output-dir", "-o", default=None, help="Output directory")
    args = parser.parse_args()

    download_lg_parts(args.url, model_id=args.model, output_dir=args.outdir)


if __name__ == "__main__":
    main()
