#!/usr/bin/env python3
"""Upload appliance assembly and schematic diagrams to Homebox entities."""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import hbctl_client
except ImportError:
    import hbctl_client  # type: ignore[no-redef]

DIAGRAM_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def find_appliance_diagram_mappings(appliances_dir: Path | str = "appliances") -> list[dict[str, Any]]:
    """Inspect appliance markdown cheat sheets and map entity IDs to diagram images."""
    app_dir = Path(appliances_dir)
    mappings: list[dict[str, Any]] = []

    if not app_dir.is_dir():
        return mappings

    for md_file in sorted(app_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        name = md_file.stem.replace("-", " ").title()
        entity_id = None
        bom_link = None

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
            elif "bill_of_materials.md" in line_str:
                m_bom = re.search(r"\[([^\]]+)\]\(([^)]*bill_of_materials\.md)\)", line_str)
                if m_bom:
                    bom_link = m_bom.group(2)

        if not entity_id:
            continue

        diagram_dir: Path | None = None

        # 1. Check relative link to bill_of_materials.md
        if bom_link:
            rel_path = Path(bom_link).parent
            cand = app_dir / rel_path / "diagrams"
            if cand.is_dir():
                diagram_dir = cand

        # 2. Check model folder name mentioned in markdown
        if not diagram_dir:
            for sub in sorted(app_dir.iterdir()):
                if sub.is_dir() and (sub / "diagrams").is_dir():
                    if sub.name in text:
                        diagram_dir = sub / "diagrams"
                        break

        if diagram_dir and diagram_dir.is_dir():
            diagram_files = sorted(
                f for f in diagram_dir.iterdir()
                if f.is_file() and f.suffix.lower() in DIAGRAM_EXTENSIONS
            )
            if diagram_files:
                mappings.append({
                    "name": name,
                    "entity_id": entity_id,
                    "doc_file": str(md_file),
                    "diagram_dir": str(diagram_dir),
                    "diagrams": diagram_files,
                })

    return mappings


def upload_appliance_diagrams(
    appliances_dir: Path | str = "appliances",
    entity_id: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Upload diagrams for cataloged appliances to Homebox via `hbctl attachment upload`."""
    all_mappings = find_appliance_diagram_mappings(appliances_dir)

    if entity_id:
        all_mappings = [m for m in all_mappings if m["entity_id"] == entity_id]

    results: list[dict[str, Any]] = []

    for mapping in all_mappings:
        eid = mapping["entity_id"]
        ename = mapping["name"]
        diagrams: list[Path] = mapping["diagrams"]
        diag_by_name = {d.name: d for d in diagrams}

        hb_results = hbctl_client.upload_attachments(
            eid,
            diagrams,
            overwrite=overwrite,
            force=True,
            dry_run=dry_run,
        )

        if dry_run:
            for idx, entry in enumerate(hb_results):
                body = entry.get("body") or {}
                fname = body.get("name") or (diagrams[idx].name if idx < len(diagrams) else "unknown")
                fpath = body.get("file") or str(diag_by_name.get(fname, ""))
                results.append({
                    "entity_name": ename,
                    "entity_id": eid,
                    "filename": fname,
                    "path": fpath,
                    "uploaded": False,
                    "already_existed": False,
                    "dry_run": True,
                })
            continue

        for entry in hb_results:
            fname = entry.get("file", "")
            status = entry.get("status", "")
            results.append({
                "entity_name": ename,
                "entity_id": eid,
                "filename": fname,
                "path": str(diag_by_name.get(fname, "")),
                "uploaded": status == "uploaded",
                "already_existed": status == "skipped",
                "dry_run": False,
            })

    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Upload appliance assembly diagrams from appliances/ into Homebox entities."
    )
    parser.add_argument(
        "--appliances-dir",
        "-d",
        default="appliances",
        help="Directory containing appliance markdown docs and diagram subfolders (default: appliances)",
    )
    parser.add_argument(
        "--entity-id",
        "-e",
        default=None,
        help="Upload diagrams for a specific Homebox entity ID only",
    )
    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        help="Upload even if an attachment with the same filename already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview diagrams to be uploaded without sending files to Homebox",
    )

    args = parser.parse_args(argv)

    try:
        results = upload_appliance_diagrams(
            appliances_dir=args.appliances_dir,
            entity_id=args.entity_id,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )

        if not results:
            print("[i] No diagrams found to upload.")
            return 0

        print(f"[*] Found {len(results)} diagram(s):")
        for r in results:
            is_dry = r.get("dry_run", False)
            is_up = r.get("uploaded", False)
            dest_path = r.get("path", "")
            if is_dry:
                status = "Would upload" if (not r.get("already_existed") or args.overwrite) else "Already exists"
            else:
                status = "Uploaded" if is_up else "Already exists"
            path_str = f" ({dest_path})" if dest_path else ""
            print(f"  - [{r.get('entity_name', 'Unknown')}] {r.get('filename', 'Unknown')} -> {status}{path_str}")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
