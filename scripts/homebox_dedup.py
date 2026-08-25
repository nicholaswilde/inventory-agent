"""
homebox_dedup.py — Detect, delete, and merge duplicate HomeBox entities.

Usage:
  uv run scripts/homebox_dedup.py [--threshold 0.8] [--delete] [--merge] [--dry-run]

Options:
  --threshold FLOAT   Jaccard similarity threshold for near-duplicates (default: 0.8)
  --delete            Delete duplicate entities (keeps most descriptive entry)
  --merge             Merge quantities before deleting duplicates (implies --delete)
  --dry-run           Show what would be changed without executing
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

STOP_WORDS = {
    "module", "board", "breakout", "kit", "sensor", "shield",
    "adapter", "converter", "charger", "type", "usb",
}

VERSION_RE = re.compile(r"\bv?\d+(\.\d+)*\b", re.IGNORECASE)
PUNC_RE = re.compile(r"[^a-z0-9 ]")


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/versions/stop-words for similarity comparison."""
    s = name.lower().strip()
    s = VERSION_RE.sub("", s)
    s = PUNC_RE.sub(" ", s)
    tokens = [w for w in s.split() if w and w not in STOP_WORDS]
    return " ".join(tokens)


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity between two normalized name strings."""
    sa = set(normalize_name(a).split())
    sb = set(normalize_name(b).split())
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def parse_list_output(output: str) -> list[dict[str, str]]:
    """Parse homebox.sh list output into [{id, name}, ...]."""
    items = []
    for line in output.splitlines():
        m = re.match(r"ID:\s*([^\s|]+)\s*\|\s*Name:\s*(.+)", line)
        if m:
            items.append({"id": m.group(1).strip(), "name": m.group(2).strip()})
    return items


def call_homebox(
    subcommand: str,
    *args: str,
    homebox_script: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """Invoke scripts/homebox.sh."""
    script = str(homebox_script or Path(__file__).resolve().parent / "homebox.sh")
    return subprocess.run([script, subcommand, *args], capture_output=True, text=True)


def detect_duplicates(
    items: list[dict[str, str]],
    threshold: float = 0.8,
) -> list[dict[str, Any]]:
    """
    Group items into duplicate clusters.
    Returns list of groups, each with 'type' (exact|near) and 'items'.
    Exact duplicates are found first; near-duplicates are found among remaining pairs.
    """
    groups: list[dict[str, Any]] = []
    used: set[str] = set()

    # Pass 1: exact (case-insensitive)
    name_map: dict[str, list[dict]] = {}
    for item in items:
        key = item["name"].lower().strip()
        name_map.setdefault(key, []).append(item)
    for key, group in name_map.items():
        if len(group) > 1:
            groups.append({"type": "exact", "items": group})
            for item in group:
                used.add(item["id"])

    # Pass 2: near-duplicates among unused items
    remaining = [i for i in items if i["id"] not in used]
    merged_near: list[set] = []
    for i in range(len(remaining)):
        for j in range(i + 1, len(remaining)):
            a, b = remaining[i], remaining[j]
            if jaccard_similarity(a["name"], b["name"]) >= threshold:
                # Find or create cluster
                found = False
                for cluster in merged_near:
                    if a["id"] in cluster or b["id"] in cluster:
                        cluster.add(a["id"])
                        cluster.add(b["id"])
                        found = True
                        break
                if not found:
                    merged_near.append({a["id"], b["id"]})

    id_to_item = {i["id"]: i for i in items}
    for cluster in merged_near:
        groups.append({
            "type": "near",
            "items": [id_to_item[id_] for id_ in cluster],
        })

    return groups


def select_keeper(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Pick the item to keep from a duplicate group.
    Priority: longest name > highest quantity > first encountered.
    """
    return max(
        items,
        key=lambda x: (len(x.get("name", "")), x.get("quantity", 0)),
    )


def enrich_with_details(
    items: list[dict[str, str]],
    homebox_script: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Fetch full entity details (quantity etc.) for each item."""
    enriched = []
    for item in items:
        proc = call_homebox("get", item["id"], '{"id":.id,"name":.name,"quantity":.quantity}',
                            homebox_script=homebox_script)
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout)
                enriched.append({**item, **data})
                continue
            except json.JSONDecodeError:
                pass
        enriched.append({**item, "quantity": 1})
    return enriched


def merge_and_delete(
    items: list[dict[str, Any]],
    dry_run: bool = False,
    merge: bool = False,
    homebox_script: str | Path | None = None,
) -> None:
    """Keep the best item, optionally merge quantities, delete the rest."""
    keeper = select_keeper(items)
    to_delete = [i for i in items if i["id"] != keeper["id"]]

    if merge:
        total_qty = sum(i.get("quantity", 1) for i in items)
        if total_qty != keeper.get("quantity", 1):
            if dry_run:
                print(f"    [DRY-RUN] Would update quantity to {total_qty} on '{keeper['name']}' ({keeper['id']})")
            else:
                call_homebox(
                    "update", keeper["id"], json.dumps({"quantity": total_qty}),
                    homebox_script=homebox_script,
                )
                print(f"    Updated quantity to {total_qty} on '{keeper['name']}'")

    for dup in to_delete:
        if dry_run:
            print(f"    [DRY-RUN] Would delete '{dup['name']}' ({dup['id']})")
        else:
            call_homebox("delete", dup["id"], homebox_script=homebox_script)
            print(f"    Deleted '{dup['name']}' ({dup['id']})")


def run(
    threshold: float = 0.8,
    delete: bool = False,
    merge: bool = False,
    dry_run: bool = False,
    homebox_script: str | Path | None = None,
) -> int:
    """Main dedup logic. Returns exit code."""
    proc = call_homebox("list", homebox_script=homebox_script)
    if proc.returncode != 0:
        print(f"Error listing entities: {proc.stderr}", file=sys.stderr)
        return 1

    items = parse_list_output(proc.stdout)
    print(f"[*] Found {len(items)} total entities.")

    if delete or merge:
        items = enrich_with_details(items, homebox_script=homebox_script)

    groups = detect_duplicates(items, threshold=threshold)

    if not groups:
        print("[+] No duplicates found.")
        return 0

    exact = [g for g in groups if g["type"] == "exact"]
    near = [g for g in groups if g["type"] == "near"]

    print(f"\n[!] Exact duplicates: {len(exact)} group(s)")
    for g in exact:
        keeper = select_keeper(g["items"])
        print(f"  Group ({len(g['items'])} items) — keeping: '{keeper['name']}' ({keeper['id']})")
        for item in g["items"]:
            marker = "KEEP" if item["id"] == keeper["id"] else "DEL "
            print(f"    [{marker}] {item['id']}  qty={item.get('quantity', '?')}")
        if delete or merge:
            merge_and_delete(g["items"], dry_run=dry_run, merge=merge, homebox_script=homebox_script)

    print(f"\n[!] Near-duplicates (threshold={threshold}): {len(near)} group(s)")
    for g in near:
        keeper = select_keeper(g["items"])
        print(f"  Group ({len(g['items'])} items) — keeping: '{keeper['name']}' ({keeper['id']})")
        for item in g["items"]:
            marker = "KEEP" if item["id"] == keeper["id"] else "DEL "
            print(f"    [{marker}] '{item['name']}' ({item['id']})  qty={item.get('quantity', '?')}")
        if delete or merge:
            merge_and_delete(g["items"], dry_run=dry_run, merge=merge, homebox_script=homebox_script)

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect and remove duplicate HomeBox entities.")
    parser.add_argument("--threshold", type=float, default=0.8,
                        help="Jaccard similarity threshold for near-duplicates (default: 0.8)")
    parser.add_argument("--delete", action="store_true",
                        help="Delete duplicate entities (keep most descriptive)")
    parser.add_argument("--merge", action="store_true",
                        help="Merge quantities before deleting (implies --delete)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(
        threshold=args.threshold,
        delete=args.delete or args.merge,
        merge=args.merge,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
