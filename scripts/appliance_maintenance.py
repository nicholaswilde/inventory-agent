#!/usr/bin/env python3
"""List, log, and delete appliance maintenance entries in Homebox and local docs."""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from scripts import hbctl_client, query_appliance
except ImportError:
    import hbctl_client  # type: ignore[no-redef]
    import query_appliance  # type: ignore[no-redef]


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DATE_PREFIX_RE = re.compile(r"^\|\s*(\d{4}-\d{2}(?:-\d{2})?)")


def normalize_api_date(raw: str) -> str:
    """Validate and normalize YYYY-MM or YYYY-MM-DD to YYYY-MM-DD."""
    cleaned = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}", cleaned):
        cleaned = f"{cleaned}-01"
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        raise ValueError(f"Invalid date '{raw}': expected YYYY-MM or YYYY-MM-DD")
    datetime.date.fromisoformat(cleaned)
    return cleaned


def normalize_api_cost(raw: str | None) -> str | None:
    """Normalize a cost string like '$29.99' into a numeric string or None."""
    if raw is None:
        return None
    cleaned = raw.strip().lstrip("$").replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    float(cleaned)
    return cleaned


def resolve_target(appliances_dir: Path, target: str) -> dict[str, Any]:
    """Resolve an appliance slug, model, name, or UUID to metadata and markdown path."""
    info = query_appliance.get_appliance_info(appliances_dir, target)
    if info:
        md_path = appliances_dir / f"{info['slug']}.md"
        return {
            "slug": info["slug"],
            "name": info["name"],
            "homebox_id": info.get("homebox_id", ""),
            "md_path": md_path if md_path.is_file() else None,
        }
    cleaned = target.strip()
    if _UUID_RE.match(cleaned):
        return {
            "slug": None,
            "name": cleaned,
            "homebox_id": cleaned,
            "md_path": None,
        }
    raise ValueError(f"Appliance not found matching '{target}'")


def _sanitize_cell(value: str | None, *, default: str = "-") -> str:
    if value is None:
        return default
    cleaned = " ".join(value.replace("|", "/").splitlines()).strip()
    return cleaned or default


def insert_maintenance_row(
    content: str,
    *,
    date: str,
    action: str,
    parts: str = "-",
    cost: str = "-",
    notes: str = "-",
) -> str:
    """Insert a maintenance row into `## Maintenance History` in reverse-chronological order."""
    date_cell = _sanitize_cell(date)
    action_cell = _sanitize_cell(action)
    parts_cell = _sanitize_cell(parts)
    if parts_cell != "-" and "`" not in parts_cell:
        parts_cell = f"`{parts_cell}`"
    cost_cell = _sanitize_cell(cost)
    notes_cell = _sanitize_cell(notes)
    new_row = f"| {date_cell} | {action_cell} | {parts_cell} | {cost_cell} | {notes_cell} |"

    lines = content.splitlines()
    heading_idx: Optional[int] = None
    for idx, line in enumerate(lines):
        if line.strip().lower() in ("## maintenance history", "## maintenance log"):
            heading_idx = idx
            break

    if heading_idx is None:
        base = content.rstrip("\n")
        section = (
            "\n\n---\n\n"
            "## Maintenance History\n\n"
            "| Date | Action | Part(s) | Cost | Notes |\n"
            "|---|---|---|---|---|\n"
            f"{new_row}\n"
        )
        return f"{base}{section}"

    table_start: Optional[int] = None
    sep_idx: Optional[int] = None
    for idx in range(heading_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("|") and table_start is None:
            table_start = idx
        elif table_start is not None and stripped.startswith("|---"):
            sep_idx = idx
            break

    if table_start is None or sep_idx is None:
        insert_at = heading_idx + 1
        block = [
            "",
            "| Date | Action | Part(s) | Cost | Notes |",
            "|---|---|---|---|---|",
            new_row,
        ]
        updated_lines = lines[:insert_at] + block + lines[insert_at:]
        return "\n".join(updated_lines) + "\n"

    row_end = sep_idx + 1
    while row_end < len(lines) and lines[row_end].strip().startswith("|"):
        row_end += 1

    existing_rows = lines[sep_idx + 1 : row_end]
    combined = [new_row, *existing_rows]

    def _sort_key(row_line: str) -> str:
        match = _DATE_PREFIX_RE.match(row_line.strip())
        return match.group(1) if match else ""

    sorted_rows = sorted(combined, key=_sort_key, reverse=True)
    updated_lines = lines[: sep_idx + 1] + sorted_rows + lines[row_end:]
    return "\n".join(updated_lines) + "\n"


def _format_entries_table(entries: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for entry in entries:
        completed = str(entry.get("completedDate") or "")
        scheduled = str(entry.get("scheduledDate") or "")
        status_label = "completed" if completed else ("scheduled" if scheduled else "-")
        date_val = completed or scheduled or "-"
        rows.append([
            date_val,
            status_label,
            str(entry.get("itemName") or entry.get("itemID") or "-"),
            str(entry.get("name") or "-"),
            str(entry.get("cost") or "0"),
            str(entry.get("id") or "-"),
        ])
    return query_appliance.format_table(["Date", "Status", "Item", "Name", "Cost", "ID"], rows)


def main(argv: Optional[list[str]] = None) -> int:
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--dir", default=argparse.SUPPRESS, help="Path to appliances directory")
    base_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output JSON")
    base_parser.add_argument(
        "--dry-run", action="store_true", default=argparse.SUPPRESS, help="Preview without mutating"
    )

    parser = argparse.ArgumentParser(
        description="Manage appliance maintenance entries in Homebox and local docs.",
        parents=[base_parser],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_p = subparsers.add_parser("list", parents=[base_parser], help="List maintenance entries")
    list_p.add_argument("target", nargs="?", default=None, help="Optional appliance slug, model, or ID")
    list_p.add_argument(
        "--status",
        choices=("both", "completed", "scheduled"),
        default="both",
        help="Filter global list by status (default: both)",
    )

    log_p = subparsers.add_parser("log", parents=[base_parser], help="Log a maintenance entry")
    log_p.add_argument("target", help="Appliance slug, model, name, or Homebox UUID")
    log_p.add_argument("--name", required=True, help="Short maintenance action title")
    log_p.add_argument("--date", default=None, help="Completed date (YYYY-MM or YYYY-MM-DD)")
    log_p.add_argument("--scheduled", default=None, help="Scheduled date (YYYY-MM or YYYY-MM-DD)")
    log_p.add_argument("--display-date", default=None, help="Display date for local markdown table")
    log_p.add_argument("--part", default="", help="Part number(s) used")
    log_p.add_argument("--cost", default="", help="Cost (e.g. 29.99 or $29.99)")
    log_p.add_argument("--notes", default="", help="Additional notes or description")
    log_p.add_argument("--homebox-only", action="store_true", help="Only log to Homebox")
    log_p.add_argument("--local-only", action="store_true", help="Only update local markdown")

    del_p = subparsers.add_parser("delete", parents=[base_parser], help="Delete a maintenance entry")
    del_p.add_argument("entry_id", help="Maintenance entry UUID")

    args = parser.parse_args(argv)
    appliances_dir = query_appliance.find_appliances_dir(getattr(args, "dir", None))
    output_json = getattr(args, "json", False)
    dry_run = getattr(args, "dry_run", False)

    if args.command == "list":
        entity_id = None
        if args.target:
            resolved = resolve_target(appliances_dir, args.target)
            entity_id = resolved["homebox_id"]
            if not entity_id:
                print(f"No Homebox Entity ID found for '{args.target}'", file=sys.stderr)
                return 1
        entries = hbctl_client.list_maintenance(entity_id=entity_id, status=args.status)
        if output_json:
            print(json.dumps(entries, indent=2))
        else:
            print(_format_entries_table(entries))
        return 0

    if args.command == "log":
        if args.homebox_only and args.local_only:
            print("Cannot specify both --homebox-only and --local-only", file=sys.stderr)
            return 1

        resolved = resolve_target(appliances_dir, args.target)
        raw_completed = args.date
        raw_scheduled = args.scheduled
        if raw_completed is None and raw_scheduled is None:
            raw_completed = datetime.date.today().isoformat()

        api_completed = normalize_api_date(raw_completed) if raw_completed else None
        api_scheduled = normalize_api_date(raw_scheduled) if raw_scheduled else None
        api_cost = normalize_api_cost(args.cost)

        desc_parts = [args.notes.strip()] if args.notes.strip() else []
        if args.part.strip() and args.part.strip() not in args.notes:
            desc_parts.append(f"Part: {args.part.strip()}")
        description = " ".join(desc_parts)

        payload: dict[str, Any] = {"name": args.name.strip()}
        if description:
            payload["description"] = description
        if api_completed:
            payload["completedDate"] = api_completed
        if api_scheduled:
            payload["scheduledDate"] = api_scheduled
        if api_cost is not None:
            payload["cost"] = api_cost

        display_date = (
            args.display_date
            or raw_completed
            or (f"scheduled {raw_scheduled}" if raw_scheduled else datetime.date.today().isoformat())
        )
        display_cost = args.cost.strip() if args.cost.strip() else "-"
        display_part = args.part.strip() if args.part.strip() else "-"
        display_notes = args.notes.strip() if args.notes.strip() else "Logged in Homebox maintenance."

        if dry_run:
            preview = {
                "dry_run": True,
                "target": {
                    "name": resolved["name"],
                    "homebox_id": resolved["homebox_id"],
                    "md_path": str(resolved["md_path"]) if resolved["md_path"] else None,
                },
                "homebox_payload": None if args.local_only else payload,
                "local_row": None
                if (args.homebox_only or resolved["md_path"] is None)
                else {
                    "date": display_date,
                    "action": args.name.strip(),
                    "parts": display_part,
                    "cost": display_cost,
                    "notes": display_notes,
                },
            }
            if output_json:
                print(json.dumps(preview, indent=2))
            else:
                print(f"[DRY RUN] Target: {resolved['name']} ({resolved['homebox_id']})")
                if not args.local_only:
                    print(f"[DRY RUN] Homebox POST payload: {json.dumps(payload)}")
                if not args.homebox_only and resolved["md_path"] is not None:
                    print(
                        f"[DRY RUN] Markdown ({resolved['md_path']}): "
                        f"| {display_date} | {args.name.strip()} | {display_part} | {display_cost} | {display_notes} |"
                    )
            return 0

        hb_result = None
        if not args.local_only:
            entity_id = resolved["homebox_id"]
            if not entity_id or entity_id == "dry-run-id":
                print(f"No valid Homebox Entity ID for '{args.target}'", file=sys.stderr)
                return 1
            hb_result = hbctl_client.create_maintenance(
                entity_id,
                args.name.strip(),
                completed_date=api_completed,
                scheduled_date=api_scheduled,
                cost=api_cost,
                description=description or None,
            )

        md_updated: str | None = None
        if not args.homebox_only and resolved["md_path"] is not None:
            md_path = Path(resolved["md_path"])
            updated_content = insert_maintenance_row(
                md_path.read_text(encoding="utf-8"),
                date=display_date,
                action=args.name.strip(),
                parts=display_part,
                cost=display_cost,
                notes=display_notes,
            )
            md_path.write_text(updated_content, encoding="utf-8")
            md_updated = str(md_path)

        if output_json:
            print(json.dumps({"homebox": hb_result, "markdown": md_updated}, indent=2))
        else:
            if hb_result is not None:
                print(f"Logged in Homebox: {hb_result.get('id')} ({hb_result.get('name')})")
            if md_updated is not None:
                print(f"Updated local doc: {md_updated}")
        return 0

    if args.command == "delete":
        if dry_run:
            if output_json:
                print(json.dumps({"dry_run": True, "delete_entry_id": args.entry_id}, indent=2))
            else:
                print(f"[DRY RUN] Would DELETE /api/v1/maintenance/{args.entry_id}")
            return 0
        hbctl_client.delete_maintenance(args.entry_id, force=True)
        if output_json:
            print(json.dumps({"deleted": args.entry_id}, indent=2))
        else:
            print(f"Deleted maintenance entry: {args.entry_id}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
