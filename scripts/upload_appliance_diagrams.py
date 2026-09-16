#!/usr/bin/env python3
"""Upload appliance assembly and schematic diagrams to Homebox entities."""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

DIAGRAM_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def get_homebox_config() -> tuple[str, str]:
    """Retrieve Homebox IP and API Key from environment or .env file."""
    ip = os.getenv("HOMEBOX_IP")
    api_key = os.getenv("HOMEBOX_API_KEY")

    if not ip or not api_key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "HOMEBOX_IP" and not ip:
                        ip = v
                    elif k == "HOMEBOX_API_KEY" and not api_key:
                        api_key = v

    if not ip or not api_key:
        raise ValueError("HOMEBOX_IP or HOMEBOX_API_KEY not set in environment or .env")

    return ip, api_key


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


def get_entity_attachments(entity_id: str, base_url: str, headers: dict[str, str]) -> set[str]:
    """Retrieve existing attachment titles / filenames for a given entity."""
    url = f"{base_url}/entities/{entity_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            existing: set[str] = set()
            for a in data.get("attachments", []):
                t = a.get("title") or a.get("name")
                if t:
                    existing.add(t)
            return existing
    except requests.RequestException:
        pass
    return set()


def upload_diagram(
    entity_id: str,
    file_path: Path,
    base_url: str,
    headers: dict[str, str],
) -> bool:
    """Upload a diagram file to a Homebox entity as an attachment."""
    url = f"{base_url}/entities/{entity_id}/attachments"
    filename = file_path.name
    suffix = file_path.suffix.lower()

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    mime_type = mime_types.get(suffix, "application/octet-stream")

    with open(file_path, "rb") as f:
        files = {"file": (filename, f, mime_type)}
        data = {"name": filename}
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        resp.raise_for_status()

    return True


def upload_appliance_diagrams(
    appliances_dir: Path | str = "appliances",
    entity_id: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Upload diagrams for cataloged appliances to Homebox."""
    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    headers = {"Authorization": f"Bearer {key}"}

    all_mappings = find_appliance_diagram_mappings(appliances_dir)

    if entity_id:
        all_mappings = [m for m in all_mappings if m["entity_id"] == entity_id]

    results: list[dict[str, Any]] = []

    for mapping in all_mappings:
        eid = mapping["entity_id"]
        ename = mapping["name"]
        existing_attachments = get_entity_attachments(eid, base_url, headers)

        for diag in mapping["diagrams"]:
            fname = diag.name
            already_exists = fname in existing_attachments
            uploaded = False

            if not already_exists or overwrite:
                if not dry_run:
                    upload_diagram(eid, diag, base_url, headers)
                    uploaded = True

            results.append({
                "entity_name": ename,
                "entity_id": eid,
                "filename": fname,
                "path": str(diag),
                "uploaded": uploaded,
                "already_existed": already_exists,
                "dry_run": dry_run,
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
