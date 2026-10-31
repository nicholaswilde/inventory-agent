"""
tare_weight_manager.py — Manage kitchen container tare weights in Homebox and generate printable reference sheets.

Usage:
  uv run scripts/tare_weight_manager.py upsert "<container_name>" <weight_grams>
  uv run scripts/tare_weight_manager.py sheet
  uv run scripts/tare_weight_manager.py show
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

REQUIRED_TAGS = ["kitchen", "container", "tare-weight"]
TARE_FIELD_NAME = "Tare Weight (g)"


def get_homebox_config() -> tuple[str, str]:
    """Extract HOMEBOX_IP and HOMEBOX_API_KEY from environment or local .env file."""
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
        raise ValueError("HOMEBOX_IP and HOMEBOX_API_KEY must be set in environment or .env file")

    return ip, key


def parse_weight_grams(weight_input: str | int | float) -> int:
    """Treat input weight as grams and parse strictly as an integer."""
    if isinstance(weight_input, (int, float)):
        val = int(weight_input)
        if val <= 0:
            raise ValueError(f"Weight must be a positive integer, got: {val}")
        return val

    clean_str = re.sub(r"(?i)\s*g(rams?)?$", "", str(weight_input).strip()).strip()
    try:
        val = int(float(clean_str))
        if val <= 0:
            raise ValueError(f"Weight must be a positive integer, got: {val}")
        return val
    except Exception as exc:
        raise ValueError(f"Invalid weight in grams: '{weight_input}'") from exc


def get_tags(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Retrieve all tags from Homebox."""
    resp = requests.get(f"{base_url}/tags", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    return []


def ensure_tag_ids(base_url: str, headers: dict[str, str], tag_names: list[str]) -> list[str]:
    """Ensure required tags exist in Homebox, returning their tag IDs."""
    existing_tags = get_tags(base_url, headers)
    tag_map = {t["name"].strip().lower(): t["id"] for t in existing_tags if "name" in t and "id" in t}

    tag_ids = []
    for tag_name in tag_names:
        norm = tag_name.strip().lower()
        if norm in tag_map:
            tag_ids.append(tag_map[norm])
        else:
            resp = requests.post(f"{base_url}/tags", headers=headers, json={"name": tag_name.strip()}, timeout=15)
            resp.raise_for_status()
            new_tag = resp.json()
            new_id = new_tag.get("id")
            if new_id:
                tag_ids.append(new_id)
                tag_map[norm] = new_id

    return tag_ids


def find_container(name: str, base_url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """Find existing container item by name (case-insensitive)."""
    norm_name = name.strip().lower()
    resp = requests.get(f"{base_url}/entities", params={"q": name.strip(), "pageSize": 100}, headers=headers, timeout=15)
    if resp.status_code != 200:
        return None

    data = resp.json()
    items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    for item in items:
        item_name = item.get("name", "").strip().lower()
        if item_name == norm_name:
            return item

    return None


def upsert_container(
    name: str,
    weight: int | str | float,
    base_url: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    """
    Upsert container tare weight in Homebox:
    - If exists: update entity with PUT, applying tags and updating Tare Weight (g).
    - If not exists: create entity with POST, applying tags and Tare Weight (g).
    """
    weight_int = parse_weight_grams(weight)
    required_tag_ids = set(ensure_tag_ids(base_url, headers, REQUIRED_TAGS))
    existing = find_container(name, base_url, headers)

    if existing:
        entity_id = existing["id"]
        # Merge tags
        current_tag_ids = set(existing.get("tagIds") or [])
        for t in existing.get("tags") or []:
            if isinstance(t, dict) and "id" in t:
                current_tag_ids.add(t["id"])
        merged_tag_ids = list(current_tag_ids | required_tag_ids)

        # Merge fields
        current_fields = list(existing.get("fields") or [])
        found_field = False
        for f in current_fields:
            if f.get("name") == TARE_FIELD_NAME:
                f["value"] = weight_int
                found_field = True
                break
        if not found_field:
            current_fields.append({"name": TARE_FIELD_NAME, "type": "number", "value": weight_int})

        payload = {
            "name": existing.get("name", name.strip()),
            "tagIds": merged_tag_ids,
            "fields": current_fields,
        }
        resp = requests.put(f"{base_url}/entities/{entity_id}", headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return {"action": "updated", "id": entity_id, "name": payload["name"], "weight": weight_int}

    # Create new entity
    payload = {
        "name": name.strip(),
        "tagIds": list(required_tag_ids),
        "fields": [{"name": TARE_FIELD_NAME, "type": "number", "value": weight_int}],
    }
    resp = requests.post(f"{base_url}/entities", headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    created = resp.json()
    new_id = created.get("id", "")
    return {"action": "created", "id": new_id, "name": payload["name"], "weight": weight_int}


def fetch_tare_containers(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch all Homebox items tagged with 'tare-weight' and extract their tare weights."""
    tags = get_tags(base_url, headers)
    tare_tag_id = None
    for t in tags:
        if t.get("name", "").strip().lower() == "tare-weight":
            tare_tag_id = t.get("id")
            break

    resp = requests.get(f"{base_url}/entities", params={"pageSize": 500}, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

    containers = []
    for item in items:
        item_tag_ids = item.get("tagIds") or []
        item_tag_names = [t.get("name", "").lower() for t in (item.get("tags") or []) if isinstance(t, dict)]

        is_tare = (tare_tag_id and tare_tag_id in item_tag_ids) or ("tare-weight" in item_tag_names)
        if not is_tare:
            continue

        weight_val = None
        for f in item.get("fields") or []:
            if f.get("name") == TARE_FIELD_NAME:
                try:
                    weight_val = parse_weight_grams(f.get("value"))
                except ValueError:
                    pass
                break

        containers.append({
            "id": item.get("id"),
            "name": item.get("name", "Unknown Container"),
            "weight": weight_val,
        })

    return containers


def generate_tare_sheet(containers: list[dict[str, Any]]) -> str:
    """Generate printable Markdown table sorted alphabetically by container name."""
    sorted_containers = sorted(containers, key=lambda c: c.get("name", "").lower())
    lines = [
        "| Container / Item | Tare Weight (g) |",
        "| :--- | :--- |",
    ]
    for c in sorted_containers:
        name = c.get("name", "")
        weight = c.get("weight")
        weight_str = str(weight) if weight is not None else "-"
        lines.append(f"| {name} | {weight_str} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage container tare weights in Homebox")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    upsert_p = subparsers.add_parser("upsert", help="Upsert a container tare weight")
    upsert_p.add_argument("name", help="Container or item name")
    upsert_p.add_argument("weight", help="Tare weight in grams (e.g. 250, 250g)")

    subparsers.add_parser("sheet", aliases=["show", "table"], help="Generate printable Markdown tare weight sheet or console table")

    args = parser.parse_args(argv)

    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    if args.subcommand == "upsert":
        res = upsert_container(args.name, args.weight, base_url, headers)
        print(f"Successfully {res['action']} container '{res['name']}' with tare weight {res['weight']}g (ID: {res['id']})")
    elif args.subcommand in ("sheet", "show", "table"):
        containers = fetch_tare_containers(base_url, headers)
        sheet = generate_tare_sheet(containers)
        print(sheet)


if __name__ == "__main__":
    main()
