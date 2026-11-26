"""
tare_weight_manager.py — Manage kitchen container tare weights in Homebox and generate printable reference sheets.

Usage:
  uv run scripts/tare_weight_manager.py upsert "<container_name>" <weight_grams>
  uv run scripts/tare_weight_manager.py sheet
  uv run scripts/tare_weight_manager.py show
"""
from __future__ import annotations

import argparse
import re
from typing import Any

try:
    from scripts import hbctl_client
except ImportError:
    import hbctl_client  # type: ignore[no-redef]

REQUIRED_TAGS = ["kitchen", "container", "tare-weight"]
TARE_FIELD_NAME = "Tare Weight (g)"


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


def upsert_container(name: str, weight: int | str | float) -> dict[str, Any]:
    """Upsert container tare weight in Homebox via `hbctl item upsert`."""
    weight_int = parse_weight_grams(weight)
    clean_name = name.strip()
    res = hbctl_client.upsert_item(
        clean_name,
        tags=REQUIRED_TAGS,
        fields=[(TARE_FIELD_NAME, weight_int)],
        field_type="number",
    )
    action = str(res.get("action") or "upserted")
    return {
        "action": action,
        "id": res.get("id", ""),
        "name": res.get("name", clean_name),
        "weight": weight_int,
    }


def render_tare_sheet() -> str:
    """Render printable Markdown tare weight table via `hbctl export`."""
    return hbctl_client.export_markdown(
        tag="tare-weight",
        columns=["name=Container / Item", TARE_FIELD_NAME],
        align="left",
        empty="-",
        sort="name",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage container tare weights in Homebox")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    upsert_p = subparsers.add_parser("upsert", help="Upsert a container tare weight")
    upsert_p.add_argument("name", help="Container or item name")
    upsert_p.add_argument("weight", help="Tare weight in grams (e.g. 250, 250g)")

    subparsers.add_parser("sheet", aliases=["show", "table"], help="Generate printable Markdown tare weight sheet or console table")

    args = parser.parse_args(argv)

    if args.subcommand == "upsert":
        res = upsert_container(args.name, args.weight)
        print(f"Successfully {res['action']} container '{res['name']}' with tare weight {res['weight']}g (ID: {res['id']})")
    elif args.subcommand in ("sheet", "show", "table"):
        print(render_tare_sheet())


if __name__ == "__main__":
    main()
