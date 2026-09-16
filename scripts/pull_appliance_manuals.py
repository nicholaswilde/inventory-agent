#!/usr/bin/env python3
"""
Pull appliance reference PDF manuals from Homebox and save them locally.

Usage:
    uv run scripts/pull_appliance_manuals.py [OPTIONS]

Options:
    -o, --output-dir DIR      Destination directory (default: manuals)
    -d, --appliances-dir DIR  Directory containing appliance markdown docs (default: appliances)
    -e, --entity-id ID        Download manual for a specific Homebox entity ID
    -a, --scan-all            Scan all Homebox entities for PDF attachments, not just documented appliances
    -f, --overwrite           Overwrite existing local manual files
    --dry-run                 Show which manuals would be pulled without downloading
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests


def get_homebox_config() -> tuple[str, str]:
    """Retrieve HOMEBOX_IP and HOMEBOX_API_KEY from environment or .env file."""
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


def get_appliance_entities_from_markdown(appliances_dir: Path | str = "appliances") -> list[dict[str, Any]]:
    """Scan markdown files in appliances directory to extract documented Homebox Entity IDs."""
    app_dir = Path(appliances_dir)
    if not app_dir.is_dir():
        return []

    entities: list[dict[str, Any]] = []
    for md_file in sorted(app_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        name = md_file.stem.replace("-", " ").title()
        entity_id = None
        manual_filename = None

        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith("# "):
                name = line_str[2:].strip()
            elif "Homebox Entity ID" in line_str and "`" in line_str:
                parts = line_str.split("`")
                if len(parts) >= 2:
                    raw_id = parts[1].strip()
                    if raw_id and raw_id != "dry-run-id":
                        entity_id = raw_id
            elif "Manual Attachment" in line_str and "`" in line_str:
                parts = line_str.split("`")
                if len(parts) >= 2:
                    manual_path = parts[1].strip()
                    if manual_path.endswith(".pdf"):
                        manual_filename = Path(manual_path).name

        if entity_id:
            entities.append({
                "name": name,
                "entity_id": entity_id,
                "doc_file": str(md_file),
                "manual_filename": manual_filename,
            })

    return entities


def fetch_entity(entity_id: str, base_url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """Fetch entity details including attachment list from Homebox."""
    url = f"{base_url}/entities/{entity_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return None


def download_attachment(
    entity_id: str,
    attachment_id: str,
    dest_path: Path | str,
    base_url: str,
    headers: dict[str, str],
    chunk_size: int = 65536,
) -> Path:
    """Stream download an attachment from Homebox to local disk."""
    url = f"{base_url}/entities/{entity_id}/attachments/{attachment_id}"
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(url, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            f.write(chunk)

    return dest


def pull_appliance_manuals(
    output_dir: Path | str = "manuals",
    appliances_dir: Path | str = "appliances",
    entity_id: str | None = None,
    scan_all: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Pull appliance manual PDFs from Homebox and save them locally."""
    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    headers = {"Authorization": f"Bearer {key}"}

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    targets: list[dict[str, Any]] = []

    if entity_id:
        targets = [{"name": f"Entity_{entity_id}", "entity_id": entity_id, "manual_filename": None}]
    elif scan_all:
        resp = requests.get(f"{base_url}/entities", headers=headers, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            targets.append({
                "name": item.get("name", "Unknown"),
                "entity_id": item["id"],
                "manual_filename": None,
            })
    else:
        targets = get_appliance_entities_from_markdown(appliances_dir)

    results: list[dict[str, Any]] = []

    for target in targets:
        eid = target["entity_id"]
        entity_name = target["name"]
        entity_data = fetch_entity(eid, base_url, headers)
        if not entity_data:
            continue

        real_name = entity_data.get("name") or entity_name
        attachments = entity_data.get("attachments", [])

        # Filter for PDF attachments
        pdf_attachments = [
            a for a in attachments
            if a.get("mimeType") == "application/pdf"
            or (a.get("title") and a["title"].lower().endswith(".pdf"))
            or (a.get("name") and a["name"].lower().endswith(".pdf"))
        ]

        for att in pdf_attachments:
            aid = att["id"]
            title = att.get("title") or att.get("name")
            if not title:
                title = target.get("manual_filename")
            if not title:
                slug = re.sub(r"[^a-zA-Z0-9]+", "_", real_name).strip("_")
                title = f"{slug}_Manual.pdf"

            dest_file = out_path / title
            already_exists = dest_file.exists()

            downloaded = False
            if not already_exists or overwrite:
                if not dry_run:
                    download_attachment(eid, aid, dest_file, base_url, headers)
                downloaded = True

            results.append({
                "entity_name": real_name,
                "entity_id": eid,
                "attachment_id": aid,
                "filename": title,
                "path": str(dest_file),
                "downloaded": downloaded,
                "already_existed": already_exists,
                "dry_run": dry_run,
            })

    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Pull appliance PDF manuals from Homebox and place them locally for reference."
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="manuals",
        help="Destination directory for downloaded manuals (default: manuals)",
    )
    parser.add_argument(
        "--appliances-dir",
        "-d",
        default="appliances",
        help="Directory containing appliance markdown files (default: appliances)",
    )
    parser.add_argument(
        "--entity-id",
        "-e",
        default=None,
        help="Download manuals for a specific Homebox entity ID",
    )
    parser.add_argument(
        "--scan-all",
        "-a",
        action="store_true",
        help="Scan all Homebox entities for PDF attachments",
    )
    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        help="Overwrite existing local files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview manuals to be downloaded without writing files",
    )

    args = parser.parse_args(argv)

    try:
        results = pull_appliance_manuals(
            output_dir=args.output_dir,
            appliances_dir=args.appliances_dir,
            entity_id=args.entity_id,
            scan_all=args.scan_all,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )

        if not results:
            print("[i] No PDF manuals found to download.")
            return 0

        print(f"[*] Found {len(results)} PDF manual(s):")
        for r in results:
            is_dry_run = r.get("dry_run", False)
            is_downloaded = r.get("downloaded", False)
            dest_path = r.get("path", "")
            status = "Would download" if is_dry_run else ("Downloaded" if is_downloaded else "Already exists")
            path_str = f" ({dest_path})" if dest_path else ""
            print(f"  - [{r.get('entity_name', 'Unknown')}] {r.get('filename', 'Unknown')} -> {status}{path_str}")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
