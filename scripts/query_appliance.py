#!/usr/bin/env python3
"""Query and retrieve appliance information, specifications, error codes, and bill of materials."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional


def find_appliances_dir(explicit_dir: Optional[str] = None) -> Path:
    if explicit_dir:
        return Path(explicit_dir).resolve()
    # Check current directory
    cwd = Path.cwd()
    if (cwd / "appliances").is_dir():
        return cwd / "appliances"
    # Check parent directory
    if (cwd.parent / "appliances").is_dir():
        return cwd.parent / "appliances"
    # Fallback to repo root relative to this script
    script_root = Path(__file__).resolve().parent.parent / "appliances"
    return script_root


def parse_markdown_metadata(content: str) -> dict[str, Any]:
    lines = content.splitlines()
    data: dict[str, Any] = {
        "name": "",
        "homebox_id": "",
        "manufacturer": "",
        "model": "",
        "covered_models": "",
        "manual_part_number": "",
        "specs": {},
        "error_codes": [],
        "accessories": [],
        "bom_link": None,
    }

    current_section = None
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        if line_stripped.startswith("# ") and not data["name"]:
            data["name"] = line_stripped[2:].strip()
            continue

        if line_stripped.startswith("## "):
            current_section = line_stripped[3:].strip().lower()
            continue

        if current_section is None:
            # Header metadata lines
            m_id = re.match(r"-\s+\*\*Homebox Entity ID\*\*:\s*`?([^`\n]+)`?", line_stripped)
            if m_id:
                data["homebox_id"] = m_id.group(1).strip()
            m_mfg = re.match(r"-\s+\*\*Manufacturer\*\*:\s*(.+)", line_stripped)
            if m_mfg:
                data["manufacturer"] = m_mfg.group(1).strip()
            m_mod = re.match(r"-\s+\*\*Model\*\*:\s*`?([^`\n]+)`?", line_stripped)
            if m_mod:
                data["model"] = m_mod.group(1).strip()
            m_cov = re.match(r"-\s+\*\*Covered Models\*\*:\s*(.+)", line_stripped)
            if m_cov:
                data["covered_models"] = m_cov.group(1).strip()
            m_part = re.match(r"-\s+\*\*Manual Part Number\*\*:\s*(.+)", line_stripped)
            if m_part:
                data["manual_part_number"] = m_part.group(1).strip()

        elif "specification" in current_section:
            # Parse table row
            if line_stripped.startswith("|") and not line_stripped.startswith("|---"):
                cols = [c.strip() for c in line_stripped.strip("|").split("|")]
                if len(cols) >= 2 and cols[0].lower() not in ("spec", "specification"):
                    key = re.sub(r"\*\*|\*", "", cols[0]).strip()
                    val = cols[1].strip()
                    if key and val:
                        data["specs"][key] = val

        elif "error" in current_section:
            if line_stripped.startswith("|") and not line_stripped.startswith("|---"):
                cols = [c.strip() for c in line_stripped.strip("|").split("|")]
                if len(cols) >= 3 and cols[0].lower() not in ("code", "error code"):
                    code = re.sub(r"`", "", cols[0]).strip()
                    meaning = cols[1].strip()
                    action = cols[2].strip()
                    if code and code != "Code":
                        data["error_codes"].append({
                            "code": code,
                            "meaning": meaning,
                            "action": action,
                        })

        elif "part" in current_section or "accessory" in current_section:
            m_bom = re.search(r"\[([^\]]+)\]\(([^)]*bill_of_materials\.md)\)", line_stripped)
            if m_bom:
                data["bom_link"] = m_bom.group(2)
            elif line_stripped.startswith("- "):
                item_text = line_stripped[2:].strip()
                if item_text and not item_text.startswith("**Full Parts"):
                    data["accessories"].append(item_text)

    # If covered_models is empty but model is set
    if not data["covered_models"] and data["model"]:
        data["covered_models"] = data["model"]
    elif not data["model"] and data["covered_models"]:
        # Extract first clean model ID from covered models
        m = re.search(r"`?([A-Z0-9\-]+)`?", data["covered_models"])
        if m:
            data["model"] = m.group(1)

    return data


def load_bom(model_dir: Path) -> dict[str, Any]:
    json_path = model_dir / "bill_of_materials.json"
    if json_path.is_file():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Normalize structure
            assemblies = []
            raw_groups = data.get("assemblies") or data.get("sections") or data.get("diagrams") or []
            for g in raw_groups:
                g_name = g.get("name") or g.get("section_num") or "Assembly"
                diagram_file = g.get("diagram_file")
                parts = []
                for p in g.get("parts", []):
                    parts.append({
                        "callout": str(p.get("callout", "")),
                        "part_number": str(p.get("part_number") or p.get("part_no") or ""),
                        "description": str(p.get("description") or p.get("title") or ""),
                        "price": str(p.get("price", "N/A")),
                        "status": str(p.get("status", "N/A")),
                        "url": str(p.get("url") or p.get("spec_url") or ""),
                        "diagram_file": diagram_file,
                    })
                assemblies.append({
                    "name": str(g_name),
                    "diagram_file": diagram_file,
                    "parts": parts,
                })
            return {
                "model": data.get("model") or data.get("model_id") or data.get("variant_id") or model_dir.name,
                "assemblies": assemblies,
            }
        except Exception:
            pass
    return {"model": model_dir.name, "assemblies": []}


def list_appliances(appliances_dir: Path) -> list[dict[str, Any]]:
    results = []
    if not appliances_dir.is_dir():
        return results

    for md_file in sorted(appliances_dir.glob("*.md")):
        slug = md_file.stem
        content = md_file.read_text(encoding="utf-8", errors="replace")
        meta = parse_markdown_metadata(content)

        # Check BOM dir
        bom_dir = None
        if meta.get("bom_link"):
            rel_dir = Path(meta["bom_link"]).parent
            target_dir = appliances_dir / rel_dir
            if target_dir.is_dir():
                bom_dir = target_dir

        if not bom_dir:
            # Try model or covered_models
            for sub in appliances_dir.iterdir():
                if sub.is_dir() and (sub / "bill_of_materials.json").is_file():
                    if sub.name in meta.get("covered_models", "") or sub.name in meta.get("model", ""):
                        bom_dir = sub
                        break

        total_parts = 0
        total_assemblies = 0
        has_bom = False
        if bom_dir:
            has_bom = True
            bom_data = load_bom(bom_dir)
            total_assemblies = len(bom_data["assemblies"])
            total_parts = sum(len(a["parts"]) for a in bom_data["assemblies"])

        results.append({
            "slug": slug,
            "name": meta["name"],
            "manufacturer": meta["manufacturer"],
            "model": meta["model"],
            "covered_models": meta["covered_models"],
            "homebox_id": meta["homebox_id"],
            "manual_part_number": meta["manual_part_number"],
            "has_bom": has_bom,
            "total_assemblies": total_assemblies,
            "total_parts": total_parts,
            "file": str(md_file),
        })
    return results


def get_appliance_info(appliances_dir: Path, target: str) -> Optional[dict[str, Any]]:
    target_clean = target.strip().lower()
    if not appliances_dir.is_dir():
        return None

    matched_file = None
    for md_file in appliances_dir.glob("*.md"):
        slug = md_file.stem.lower()
        if slug == target_clean:
            matched_file = md_file
            break
        # Read content to check model or name
        content = md_file.read_text(encoding="utf-8", errors="replace")
        meta = parse_markdown_metadata(content)
        if (
            target_clean == meta["model"].lower()
            or target_clean in meta["covered_models"].lower()
            or target_clean in meta["name"].lower()
            or target_clean == meta["homebox_id"].lower()
        ):
            matched_file = md_file
            break

    if not matched_file:
        return None

    content = matched_file.read_text(encoding="utf-8", errors="replace")
    meta = parse_markdown_metadata(content)

    # Locate BOM directory
    bom_dir = None
    if meta.get("bom_link"):
        candidate = appliances_dir / Path(meta["bom_link"]).parent
        if candidate.is_dir():
            bom_dir = candidate

    if not bom_dir:
        for sub in appliances_dir.iterdir():
            if sub.is_dir() and (sub / "bill_of_materials.json").is_file():
                if sub.name in meta.get("covered_models", "") or sub.name in meta.get("model", ""):
                    bom_dir = sub
                    break

    bom_assemblies = []
    if bom_dir:
        bom_data = load_bom(bom_dir)
        bom_assemblies = bom_data.get("assemblies", [])

    return {
        "slug": matched_file.stem,
        "name": meta["name"],
        "manufacturer": meta["manufacturer"],
        "model": meta["model"],
        "covered_models": meta["covered_models"],
        "homebox_id": meta["homebox_id"],
        "manual_part_number": meta["manual_part_number"],
        "specs": meta["specs"],
        "error_codes": meta["error_codes"],
        "accessories": meta["accessories"],
        "has_bom": bool(bom_dir),
        "bom_dir": str(bom_dir) if bom_dir else None,
        "assemblies": bom_assemblies,
    }


def search_parts(appliances_dir: Path, query: str, model: Optional[str] = None) -> list[dict[str, Any]]:
    query_lower = query.strip().lower()
    model_filter = model.strip().lower() if model else None
    results = []

    if not appliances_dir.is_dir():
        return results

    for sub in appliances_dir.iterdir():
        if not sub.is_dir():
            continue
        bom_json = sub / "bill_of_materials.json"
        if not bom_json.is_file():
            continue

        bom_data = load_bom(sub)
        app_model = bom_data.get("model", sub.name)

        if model_filter and model_filter not in app_model.lower() and model_filter not in sub.name.lower():
            continue

        for assembly in bom_data.get("assemblies", []):
            assembly_name = assembly.get("name", "")
            diagram_file = assembly.get("diagram_file")
            for part in assembly.get("parts", []):
                part_no = part.get("part_number", "")
                desc = part.get("description", "")
                callout = part.get("callout", "")

                if (
                    query_lower in part_no.lower()
                    or query_lower in desc.lower()
                    or query_lower == callout.lower()
                    or query_lower in assembly_name.lower()
                ):
                    results.append({
                        "model": app_model,
                        "model_dir": sub.name,
                        "assembly": assembly_name,
                        "callout": callout,
                        "part_number": part_no,
                        "description": desc,
                        "price": part.get("price", "N/A"),
                        "status": part.get("status", "N/A"),
                        "url": part.get("url", ""),
                        "diagram_file": diagram_file or part.get("diagram_file"),
                    })
    return results


def search_error_codes(appliances_dir: Path, query: str) -> list[dict[str, Any]]:
    query_lower = query.strip().lower()
    results = []

    if not appliances_dir.is_dir():
        return results

    for md_file in sorted(appliances_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8", errors="replace")
        meta = parse_markdown_metadata(content)
        app_name = meta["name"]
        model = meta["model"] or meta["covered_models"]

        for ec in meta.get("error_codes", []):
            code = ec.get("code", "")
            meaning = ec.get("meaning", "")
            action = ec.get("action", "")

            if (
                query_lower in code.lower()
                or query_lower in meaning.lower()
                or query_lower in action.lower()
                or query_lower in app_name.lower()
            ):
                results.append({
                    "appliance": app_name,
                    "model": model,
                    "slug": md_file.stem,
                    "code": code,
                    "meaning": meaning,
                    "action": action,
                })
    return results


def search_appliances(appliances_dir: Path, query: str) -> dict[str, Any]:
    query_lower = query.strip().lower()
    apps_list = list_appliances(appliances_dir)
    matched_apps = [
        a for a in apps_list
        if query_lower in a["name"].lower()
        or query_lower in a["model"].lower()
        or query_lower in a["covered_models"].lower()
        or query_lower in a["manufacturer"].lower()
        or query_lower in a["slug"].lower()
    ]
    parts = search_parts(appliances_dir, query)
    error_codes = search_error_codes(appliances_dir, query)

    return {
        "query": query,
        "appliances": matched_apps,
        "parts": parts,
        "error_codes": error_codes,
    }


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "(no results)"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    header_line = " | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * widths[i] for i in range(len(headers)))
    data_lines = [
        " | ".join(f"{str(cell):<{widths[i]}}" for i, cell in enumerate(r))
        for r in rows
    ]
    return "\n".join([header_line, sep_line] + data_lines)


def main(argv: Optional[list[str]] = None) -> int:
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("--dir", default=argparse.SUPPRESS, help="Path to appliances directory")
    base_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output results in JSON format")

    parser = argparse.ArgumentParser(
        description="Query and retrieve appliance information and parts BOM.",
        parents=[base_parser],
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list
    subparsers.add_parser("list", parents=[base_parser], help="List all cataloged appliances")

    # info
    info_parser = subparsers.add_parser("info", parents=[base_parser], help="Get detailed info for an appliance")
    info_parser.add_argument("target", help="Appliance slug, model, or name")

    # search
    search_parser = subparsers.add_parser("search", parents=[base_parser], help="Search appliances, specs, error codes, and parts")
    search_parser.add_argument("query", help="Search query keyword or pattern")

    # part
    part_parser = subparsers.add_parser("part", parents=[base_parser], help="Search replacement parts across BOMs")
    part_parser.add_argument("query", help="Part number or description keyword")
    part_parser.add_argument("--model", default=None, help="Filter to specific model ID")

    # error
    error_parser = subparsers.add_parser("error", parents=[base_parser], help="Search error codes and troubleshooting diagnostics")
    error_parser.add_argument("query", help="Error code or symptom keyword")

    args = parser.parse_args(argv)
    appliances_dir = find_appliances_dir(getattr(args, "dir", None))
    output_json = getattr(args, "json", False)

    if not args.command or args.command == "list":
        apps = list_appliances(appliances_dir)
        if output_json:
            print(json.dumps(apps, indent=2))
            return 0
        rows = [
            [
                a["name"],
                a["model"] or a["covered_models"] or "N/A",
                a["manufacturer"] or "N/A",
                "Yes" if a["has_bom"] else "No",
                str(a["total_parts"]),
                a["slug"],
            ]
            for a in apps
        ]
        headers = ["Name", "Model", "Manufacturer", "BOM?", "Parts", "Slug"]
        print(format_table(headers, rows))
        return 0

    if args.command == "info":
        info = get_appliance_info(appliances_dir, args.target)
        if not info:
            print(f"Appliance not found matching '{args.target}'", file=sys.stderr)
            return 1
        if output_json:
            print(json.dumps(info, indent=2))
            return 0

        print(f"=== {info['name']} ===")
        print(f"Slug:         {info['slug']}")
        print(f"Manufacturer: {info['manufacturer']}")
        print(f"Model(s):     {info['covered_models'] or info['model']}")
        print(f"Homebox ID:   {info['homebox_id'] or 'N/A'}")
        if info['manual_part_number']:
            print(f"Manual Part:  {info['manual_part_number']}")

        if info['specs']:
            print("\n--- Specifications ---")
            for k, v in info['specs'].items():
                print(f"  {k}: {v}")

        if info['error_codes']:
            print("\n--- Error Codes ---")
            ec_rows = [[e['code'], e['meaning'], e['action']] for e in info['error_codes']]
            print(format_table(["Code", "Meaning", "Action"], ec_rows))

        if info['assemblies']:
            print(f"\n--- Bill of Materials ({len(info['assemblies'])} assemblies) ---")
            total_p = sum(len(a['parts']) for a in info['assemblies'])
            print(f"Total parts cataloged: {total_p}")
            for a in info['assemblies']:
                diag = f" (Diagram: {a['diagram_file']})" if a.get('diagram_file') else ""
                print(f"  - {a['name']}: {len(a['parts'])} parts{diag}")
        return 0

    if args.command == "part":
        parts = search_parts(appliances_dir, args.query, model=args.model)
        if output_json:
            print(json.dumps(parts, indent=2))
            return 0
        if not parts:
            print(f"No parts found matching '{args.query}'" + (f" for model '{args.model}'" if args.model else ""))
            return 0
        rows = [
            [
                p["model"],
                p["callout"],
                p["part_number"],
                p["description"][:45],
                p["price"],
                p["status"],
                p.get("diagram_file") or "N/A",
            ]
            for p in parts
        ]
        headers = ["Model", "Callout", "Part #", "Description", "Price", "Status", "Diagram"]
        print(format_table(headers, rows))
        print(f"\nTotal matches: {len(parts)}")
        return 0

    if args.command == "error":
        errors = search_error_codes(appliances_dir, args.query)
        if output_json:
            print(json.dumps(errors, indent=2))
            return 0
        if not errors:
            print(f"No error codes found matching '{args.query}'")
            return 0
        rows = [
            [e["appliance"], e["code"], e["meaning"][:40], e["action"][:40]]
            for e in errors
        ]
        headers = ["Appliance", "Code", "Meaning", "Action"]
        print(format_table(headers, rows))
        print(f"\nTotal matches: {len(errors)}")
        return 0

    if args.command == "search":
        res = search_appliances(appliances_dir, args.query)
        if output_json:
            print(json.dumps(res, indent=2))
            return 0

        print(f"=== Search results for '{args.query}' ===")
        if res["appliances"]:
            print("\nMatched Appliances:")
            for a in res["appliances"]:
                print(f"  - {a['name']} ({a['model'] or a['covered_models']}) [slug: {a['slug']}]")
        if res["error_codes"]:
            print(f"\nMatched Error Codes ({len(res['error_codes'])}):")
            for e in res["error_codes"][:5]:
                print(f"  - [{e['appliance']}] {e['code']}: {e['meaning']} -> {e['action']}")
            if len(res["error_codes"]) > 5:
                print(f"    ... and {len(res['error_codes']) - 5} more")
        if res["parts"]:
            print(f"\nMatched BOM Parts ({len(res['parts'])}):")
            for p in res["parts"][:10]:
                print(f"  - [{p['model']}] #{p['part_number']} ({p['callout']}): {p['description']} (${p['price']})")
            if len(res["parts"]) > 10:
                print(f"    ... and {len(res['parts']) - 10} more")

        if not res["appliances"] and not res["error_codes"] and not res["parts"]:
            print("No matches found.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
