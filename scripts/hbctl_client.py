"""Thin subprocess wrapper around the `hbctl` CLI for inventory-agent scripts."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence


class HbctlError(RuntimeError):
    """Raised when an `hbctl` CLI invocation fails or returns invalid output."""


def run_hbctl(
    args: Sequence[str],
    *,
    stdin_data: str | None = None,
    stdin_bytes: bytes | None = None,
    hbctl_bin: str = "hbctl",
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute `hbctl` with the given arguments and optional stdin payload."""
    cmd = [hbctl_bin, *args]
    if stdin_bytes is not None:
        raw_proc = subprocess.run(cmd, input=stdin_bytes, capture_output=True, text=False)
        proc = subprocess.CompletedProcess(
            args=raw_proc.args,
            returncode=raw_proc.returncode,
            stdout=(raw_proc.stdout or b"").decode("utf-8", errors="replace"),
            stderr=(raw_proc.stderr or b"").decode("utf-8", errors="replace"),
        )
    else:
        proc = subprocess.run(cmd, input=stdin_data, capture_output=True, text=True)
    if check and proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip()
        raise HbctlError(f"hbctl {' '.join(args)} failed: {msg}")
    return proc


def hbctl_json(
    args: Sequence[str],
    *,
    stdin_data: str | None = None,
    stdin_bytes: bytes | None = None,
    hbctl_bin: str = "hbctl",
) -> Any:
    """Execute `hbctl --json` and parse the JSON stdout payload."""
    proc = run_hbctl(
        ["--json", *args],
        stdin_data=stdin_data,
        stdin_bytes=stdin_bytes,
        hbctl_bin=hbctl_bin,
    )
    stripped = proc.stdout.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise HbctlError(f"Invalid JSON from hbctl {' '.join(args)}: {stripped}") from exc


def get_field_value(
    item: dict[str, Any],
    field_name: str,
    top_level_key: str | None = None,
) -> str:
    """Return a custom field value (case-insensitive), falling back to a top-level key."""
    needle = field_name.strip().lower()
    for field in item.get("fields") or []:
        if isinstance(field, dict) and str(field.get("name", "")).strip().lower() == needle:
            for key in ("textValue", "numberValue", "booleanValue", "value"):
                val = field.get(key)
                if val is not None and str(val).strip() != "":
                    return str(val).strip()
    if top_level_key:
        val = item.get(top_level_key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return ""


def list_items(
    *,
    tag: str | None = None,
    has_field: str | None = None,
    select: str | None = None,
) -> list[dict[str, Any]]:
    """List all Homebox items via `hbctl item list --all`."""
    args = ["item", "list", "--all"]
    if tag:
        args.extend(["--tag", tag])
    if has_field:
        args.extend(["--has-field", has_field])
    if select:
        args.extend(["--select", select])
    data = hbctl_json(args)
    return data if isinstance(data, list) else []


def search_items(
    query: str | None = None,
    *,
    tag: str | None = None,
    model: str | None = None,
    serial: str | None = None,
    manufacturer: str | None = None,
    fields: Sequence[str] = (),
    select: str | None = None,
) -> list[dict[str, Any]]:
    """Search Homebox items via `hbctl search`."""
    args = ["search"]
    if tag:
        args.extend(["--tag", tag])
    if model:
        args.extend(["--model", model])
    if serial:
        args.extend(["--serial", serial])
    if manufacturer:
        args.extend(["--manufacturer", manufacturer])
    for field in fields:
        args.extend(["--field", field])
    if select:
        args.extend(["--select", select])
    if query:
        args.append(query)
    data = hbctl_json(args)
    return data if isinstance(data, list) else []


def get_item(entity_id: str) -> dict[str, Any]:
    """Fetch a single item by ID via `hbctl item get`."""
    data = hbctl_json(["item", "get", entity_id])
    return data if isinstance(data, dict) else {}


def create_item(
    payload: dict[str, Any],
    *,
    attach: Sequence[Path | str] = (),
    force: bool = False,
) -> dict[str, Any]:
    """Create an item from a JSON payload via `hbctl item create --from-json -`."""
    args = ["item", "create", "--from-json", "-"]
    for path in attach:
        args.extend(["--attach", str(path)])
    if force:
        args.append("--force")
    data = hbctl_json(args, stdin_data=json.dumps(payload))
    return data if isinstance(data, dict) else {}


def update_item(
    entity_id: str,
    patch: dict[str, Any],
    *,
    fill_missing: bool = False,
) -> dict[str, Any]:
    """Update an item from a JSON patch via `hbctl item update --from-json -`."""
    args = ["item", "update", entity_id, "--from-json", "-"]
    if fill_missing:
        args.append("--fill-missing")
    data = hbctl_json(args, stdin_data=json.dumps(patch))
    return data if isinstance(data, dict) else {}


def upsert_item(
    name: str | None = None,
    *,
    from_json: dict[str, Any] | None = None,
    description: str | None = None,
    quantity: int | None = None,
    tags: Sequence[str] = (),
    fields: Sequence[tuple[str, Any]] = (),
    field_type: str = "text",
    purchase_price: float | None = None,
    purchase_date: str | None = None,
    purchase_from: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
    match_by: Sequence[str] = (),
    fill_missing: bool = False,
    attach: Sequence[Path | str] = (),
    force: bool = False,
) -> dict[str, Any]:
    """Create or update an item matched by key via `hbctl item upsert`."""
    args = ["item", "upsert"]
    if name is not None:
        args.extend(["--name", name])
    if from_json is not None:
        args.extend(["--from-json", "-"])
    if description is not None:
        args.extend(["--description", description])
    if quantity is not None:
        args.extend(["--quantity", str(quantity)])
    for tag in tags:
        args.extend(["--tag", tag])
    if manufacturer is not None:
        args.extend(["--manufacturer", manufacturer])
    if model is not None:
        args.extend(["--model", model])
    if notes is not None:
        args.extend(["--notes", notes])
    if purchase_price is not None:
        args.extend(["--purchase-price", str(purchase_price)])
    if purchase_date is not None:
        args.extend(["--purchase-date", purchase_date])
    if purchase_from is not None:
        args.extend(["--purchase-from", purchase_from])
    for key, val in fields:
        args.extend(["--field", f"{key}={val}"])
    if fields:
        args.extend(["--field-type", field_type])
    for key in match_by:
        args.extend(["--match-by", key])
    if fill_missing:
        args.append("--fill-missing")
    for path in attach:
        args.extend(["--attach", str(path)])
    if force:
        args.append("--force")
    stdin_data = json.dumps(from_json) if from_json is not None else None
    data = hbctl_json(args, stdin_data=stdin_data)
    return data if isinstance(data, dict) else {}


def export_items(
    *,
    tag: str | None = None,
    fields: Sequence[str] = (),
    has_field: str | None = None,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    """Export filtered items as JSON via `hbctl export --format json`."""
    args = ["export", "--format", "json"]
    if tag:
        args.extend(["--tag", tag])
    for field in fields:
        args.extend(["--field", field])
    if has_field:
        args.extend(["--has-field", has_field])
    if sort:
        args.extend(["--sort", sort])
    data = hbctl_json(args)
    return data if isinstance(data, list) else []


def export_markdown(
    *,
    tag: str | None = None,
    columns: Sequence[str] = (),
    has_field: str | None = None,
    align: str = "left",
    empty: str = "-",
    sort: str = "name",
) -> str:
    """Export filtered items as a formatted Markdown table via `hbctl export --format markdown`."""
    args = ["export", "--format", "markdown"]
    if tag:
        args.extend(["--tag", tag])
    for col in columns:
        args.extend(["--columns", col])
    if has_field:
        args.extend(["--has-field", has_field])
    if align:
        args.extend(["--align", align])
    if empty is not None:
        args.extend(["--empty", empty])
    if sort:
        args.extend(["--sort", sort])
    return run_hbctl(args).stdout.rstrip("\n")


def upload_attachments(
    entity_id: str,
    files: Sequence[Path | str],
    *,
    overwrite: bool = False,
    force: bool = False,
    dry_run: bool = False,
    remote_name: str | None = None,
) -> list[dict[str, Any]]:
    """Upload one or more files as item attachments via `hbctl attachment upload`."""
    if not files:
        return []

    args = ["attachment", "upload"]
    if overwrite:
        args.append("--overwrite")
    if force:
        args.append("--force")
    if dry_run:
        args.append("--dry-run")
    if remote_name:
        args.extend(["--name", remote_name])
    args.append(entity_id)
    args.extend(str(Path(f)) for f in files)

    data = hbctl_json(args)
    return data if isinstance(data, list) else []


def upload_attachment_bytes(
    entity_id: str,
    content: bytes,
    filename: str,
    *,
    overwrite: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Upload raw bytes as a named attachment via `hbctl attachment upload --name ... -`."""
    args = ["attachment", "upload"]
    if overwrite:
        args.append("--overwrite")
    if force:
        args.append("--force")
    if dry_run:
        args.append("--dry-run")
    args.extend(["--name", filename, entity_id, "-"])
    data = hbctl_json(args, stdin_bytes=content)
    return data if isinstance(data, list) else []


def download_attachments(
    entity_id: str | None = None,
    out_dir: Path | str = ".",
    *,
    all_items: bool = False,
    tag: str | None = None,
    items_from: Sequence[str] | None = None,
    ext: str | None = None,
    mime: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Download matching attachments for one or many items via `hbctl attachment download`."""
    args = ["attachment", "download"]
    stdin_data: str | None = None

    if items_from is not None:
        item_ids = [eid.strip() for eid in items_from if eid and eid.strip()]
        if not item_ids:
            return []
        args.extend(["--items-from", "-"])
        stdin_data = "\n".join(item_ids) + "\n"
    elif all_items:
        args.append("--all-items")
    elif tag:
        args.extend(["--tag", tag])
    elif entity_id:
        args.extend([entity_id, "--all"])
    else:
        raise ValueError("One of entity_id, all_items, tag, or items_from must be provided")

    args.extend(["--out", str(out_dir)])
    if ext:
        args.extend(["--ext", ext])
    if mime:
        args.extend(["--mime", mime])
    if overwrite:
        args.append("--overwrite")
    if dry_run:
        args.append("--dry-run")
    data = hbctl_json(args, stdin_data=stdin_data)
    return data if isinstance(data, list) else []
