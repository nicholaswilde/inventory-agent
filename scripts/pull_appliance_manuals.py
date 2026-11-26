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
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import hbctl_client
except ImportError:
    import hbctl_client  # type: ignore[no-redef]


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


def pull_appliance_manuals(
    output_dir: Path | str = "manuals",
    appliances_dir: Path | str = "appliances",
    entity_id: str | None = None,
    scan_all: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Pull appliance manual PDFs from Homebox via `hbctl attachment download`."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    name_by_id: dict[str, str] = {}
    if entity_id:
        dl_results = hbctl_client.download_attachments(
            entity_id,
            out_path,
            ext="pdf",
            overwrite=overwrite,
            dry_run=dry_run,
        )
    elif scan_all:
        dl_results = hbctl_client.download_attachments(
            out_dir=out_path,
            all_items=True,
            ext="pdf",
            overwrite=overwrite,
            dry_run=dry_run,
        )
    else:
        targets = get_appliance_entities_from_markdown(appliances_dir)
        if not targets:
            return []
        name_by_id = {t["entity_id"]: t["name"] for t in targets}
        dl_results = hbctl_client.download_attachments(
            out_dir=out_path,
            items_from=[t["entity_id"] for t in targets],
            ext="pdf",
            overwrite=overwrite,
            dry_run=dry_run,
        )

    results: list[dict[str, Any]] = []
    for entry in dl_results:
        if dry_run:
            body = entry.get("body") or {}
            dest_str = body.get("out", "")
            eid = body.get("entityId") or entity_id or ""
            entity_name = body.get("entityName") or name_by_id.get(eid) or (f"Entity_{eid}" if eid else "Unknown")
            att_id = str(entry.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
            dest_file = Path(dest_str) if dest_str else out_path
            already_exists = dest_file.exists() if dest_str else False
            downloaded = not already_exists or overwrite
        else:
            dest_str = entry.get("path", "")
            eid = entry.get("entityId") or entity_id or ""
            entity_name = entry.get("entityName") or name_by_id.get(eid) or (f"Entity_{eid}" if eid else "Unknown")
            att_id = entry.get("id", "")
            dest_file = Path(dest_str) if dest_str else out_path
            status = entry.get("status", "")
            downloaded = status == "downloaded"
            already_exists = status == "skipped"

        results.append({
            "entity_name": entity_name,
            "entity_id": eid,
            "attachment_id": att_id,
            "filename": dest_file.name if dest_str else "",
            "path": dest_str,
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
