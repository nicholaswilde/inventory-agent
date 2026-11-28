"""Tests for scripts/hbctl_client.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hbctl_client import (
    HbctlError,
    api_request,
    create_item,
    create_maintenance,
    delete_maintenance,
    download_attachments,
    export_items,
    export_markdown,
    get_field_value,
    get_item,
    hbctl_json,
    list_items,
    list_maintenance,
    run_hbctl,
    search_items,
    update_item,
    update_maintenance,
    upload_attachments,
    upsert_item,
)


def test_run_hbctl_success_and_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["hbctl", "item", "list"], returncode=0, stdout="[]\n", stderr=""
        )
        proc = run_hbctl(["item", "list"])
        assert proc.stdout == "[]\n"
        mock_run.assert_called_once_with(
            ["hbctl", "item", "list"], input=None, capture_output=True, text=True
        )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["hbctl", "item", "get", "bad"],
            returncode=1,
            stdout="",
            stderr="not found",
        )
        with pytest.raises(HbctlError, match="not found"):
            run_hbctl(["item", "get", "bad"])


def test_hbctl_json_parses_and_handles_empty():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"id": "1"}\n', stderr=""
        )
        assert hbctl_json(["item", "get", "1"]) == {"id": "1"}
        assert mock_run.call_args[0][0] == ["hbctl", "--json", "item", "get", "1"]

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="   \n", stderr=""
        )
        assert hbctl_json(["item", "list"]) is None


def test_get_field_value_custom_and_top_level():
    item = {
        "name": "Faucet",
        "modelNumber": "TOP-1",
        "fields": [
            {"name": "Model Number", "type": "text", "textValue": "CF-123"},
            {"name": "Tare Weight (g)", "type": "number", "numberValue": 490},
            {"name": "Enabled", "type": "boolean", "booleanValue": True},
        ],
    }
    assert get_field_value(item, "model number", "modelNumber") == "CF-123"
    assert get_field_value(item, "Tare Weight (g)") == "490"
    assert get_field_value(item, "Enabled") == "True"
    assert get_field_value({"modelNumber": "TOP-1"}, "Model Number", "modelNumber") == "TOP-1"
    assert get_field_value({}, "Missing", "missing") == ""


def test_list_search_get_create_update_items():
    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = [{"id": "e1", "name": "ESP32"}]
        assert list_items(
            tag="electronics",
            entity_type="Component",
            parent="Lab",
            has_field="Voltage",
            include_archived=True,
            archived_only=True,
            warranty_expiring=30,
            select="id,name",
        ) == [
            {"id": "e1", "name": "ESP32"}
        ]
        assert mock_json.call_args[0][0] == [
            "item",
            "list",
            "--all",
            "--tag",
            "electronics",
            "--type",
            "Component",
            "--parent",
            "Lab",
            "--has-field",
            "Voltage",
            "--include-archived",
            "--archived-only",
            "--warranty-expiring",
            "30",
            "--select",
            "id,name",
        ]

        mock_json.return_value = [{"id": "e2"}]
        assert search_items(
            "ESP32",
            tag="mcu",
            entity_type="Appliance",
            parent="Kitchen",
            limit=10,
            include_archived=True,
            archived_only=True,
            warranty_expiring=30,
            with_path=True,
            model="S3",
            serial="SN1",
            manufacturer="Espressif",
            fields=["Notes=B001"],
            any_match=True,
            select="id",
        ) == [{"id": "e2"}]
        assert mock_json.call_args[0][0] == [
            "search",
            "--tag",
            "mcu",
            "--type",
            "Appliance",
            "--parent",
            "Kitchen",
            "--limit",
            "10",
            "--include-archived",
            "--archived-only",
            "--warranty-expiring",
            "30",
            "--with-path",
            "--model",
            "S3",
            "--serial",
            "SN1",
            "--manufacturer",
            "Espressif",
            "--field",
            "Notes=B001",
            "--any",
            "--select",
            "id",
            "ESP32",
        ]

        mock_json.return_value = {"id": "e1"}
        assert get_item("e1") == {"id": "e1"}
        assert mock_json.call_args[0][0] == ["item", "get", "e1"]
        assert get_item("000-001", with_path=True, asset_id=True) == {"id": "e1"}
        assert mock_json.call_args[0][0] == ["item", "get", "--with-path", "--asset-id", "000-001"]

        payload = {"name": "ESP32", "quantity": 2}
        assert create_item(
            payload,
            attach=["/tmp/c.pdf=Manual.pdf"],
            attach_urls=["https://img.example/a.jpg=a.jpg"],
            attach_best_effort=True,
            optimize=True,
            force=True,
            dry_run=True,
            hbctl_bin="/custom/hbctl",
        ) == {"id": "e1"}
        assert mock_json.call_args[0][0] == [
            "item",
            "create",
            "--from-json",
            "-",
            "--attach",
            "/tmp/c.pdf=Manual.pdf",
            "--attach-url",
            "https://img.example/a.jpg=a.jpg",
            "--attach-best-effort",
            "--optimize",
            "--force",
            "--dry-run",
        ]
        assert json.loads(mock_json.call_args[1]["stdin_data"]) == payload
        assert mock_json.call_args[1]["hbctl_bin"] == "/custom/hbctl"

        assert create_item(None, from_barcode="012345678905", dry_run=True) == {"id": "e1"}
        assert mock_json.call_args[0][0] == [
            "item",
            "create",
            "--from-barcode",
            "012345678905",
            "--dry-run",
        ]
        assert mock_json.call_args[1]["stdin_data"] is None
        with pytest.raises(ValueError, match="payload or from_barcode"):
            create_item(None)

        patch_data = {"quantity": 5}
        assert update_item("e1", patch_data, fill_missing=True) == {"id": "e1"}
        assert mock_json.call_args[0][0] == [
            "item",
            "update",
            "e1",
            "--from-json",
            "-",
            "--fill-missing",
        ]
        assert json.loads(mock_json.call_args[1]["stdin_data"]) == patch_data


def test_upsert_and_export_items():
    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = {"id": "jar-1", "name": "Mason Jar", "action": "created"}
        res = upsert_item(
            "Mason Jar",
            tags=["kitchen", "tare-weight"],
            fields=[("Tare Weight (g)", "250g")],
            field_type="number",
        )
        assert res["id"] == "jar-1"
        assert res["action"] == "created"
        assert mock_json.call_args[0][0] == [
            "item",
            "upsert",
            "--name",
            "Mason Jar",
            "--tag",
            "kitchen",
            "--tag",
            "tare-weight",
            "--field",
            "Tare Weight (g)=250g",
            "--field-type",
            "number",
        ]

        mock_json.return_value = {"id": "jar-1", "action": "attached"}
        res2 = upsert_item(
            from_json={"name": "Mason Jar", "modelNumber": "MJ-16"},
            match_by=["model", "name"],
            match_mode="contains",
            on_match="attach-only",
            fill_missing=True,
            attach=[Path("a.pdf")],
            attach_urls=["https://img.example/jar.jpg=jar.jpg"],
            attach_best_effort=True,
            optimize=True,
            force=True,
            dry_run=True,
            hbctl_bin="/opt/hbctl",
        )
        assert res2["action"] == "attached"
        assert mock_json.call_args[0][0] == [
            "item",
            "upsert",
            "--from-json",
            "-",
            "--match-by",
            "model",
            "--match-by",
            "name",
            "--match-mode",
            "contains",
            "--on-match",
            "attach-only",
            "--fill-missing",
            "--attach",
            "a.pdf",
            "--attach-url",
            "https://img.example/jar.jpg=jar.jpg",
            "--attach-best-effort",
            "--optimize",
            "--force",
            "--dry-run",
        ]
        assert json.loads(mock_json.call_args[1]["stdin_data"]) == {
            "name": "Mason Jar",
            "modelNumber": "MJ-16",
        }
        assert mock_json.call_args[1]["hbctl_bin"] == "/opt/hbctl"

        mock_json.return_value = [{"id": "jar-1", "name": "Mason Jar", "Tare Weight (g)": "250"}]
        exported = export_items(tag="tare-weight", fields=["Tare Weight (g)"], sort="name")
        assert len(exported) == 1
        assert mock_json.call_args[0][0] == [
            "export",
            "--format",
            "json",
            "--tag",
            "tare-weight",
            "--field",
            "Tare Weight (g)",
            "--sort",
            "name",
        ]

    with patch("scripts.hbctl_client.run_hbctl") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="| Container / Item | Tare Weight (g) |\n| :--- | :--- |\n| Mason Jar | 250 |\n",
            stderr="",
        )
        md = export_markdown(
            tag="tare-weight",
            columns=["name=Container / Item", "Tare Weight (g)"],
            align="left",
            empty="-",
            sort="name",
        )
        assert "| Mason Jar | 250 |" in md
        assert mock_run.call_args[0][0] == [
            "export",
            "--format",
            "markdown",
            "--tag",
            "tare-weight",
            "--columns",
            "name=Container / Item",
            "--columns",
            "Tare Weight (g)",
            "--align",
            "left",
            "--empty",
            "-",
            "--sort",
            "name",
        ]


def test_upload_attachments_flags_and_remote_name(tmp_path):
    src = tmp_path / "compressed_temp.pdf"
    src.write_bytes(b"%PDF-1.4 data")

    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = [{"file": "LG_Manual.pdf", "status": "uploaded", "id": "att-1"}]
        res = upload_attachments(
            "ent-1",
            [src],
            attach_urls=["https://img.example/diag.png=diag.png"],
            overwrite=True,
            optimize=True,
            force=True,
            dry_run=True,
            primary=True,
            remote_name="LG_Manual.pdf",
            hbctl_bin="/custom/hbctl",
        )

    assert len(res) == 1
    assert mock_json.call_args[0][0] == [
        "attachment",
        "upload",
        "--overwrite",
        "--optimize",
        "--force",
        "--dry-run",
        "--primary",
        "--name",
        "LG_Manual.pdf",
        "--attach-url",
        "https://img.example/diag.png=diag.png",
        "ent-1",
        str(src),
    ]
    assert mock_json.call_args[1]["hbctl_bin"] == "/custom/hbctl"

    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        assert upload_attachments("ent-1", []) == []
        mock_json.assert_not_called()

    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = [{"file": "diag.png", "status": "uploaded", "id": "att-url"}]
        res_url = upload_attachments("ent-1", [], attach_urls=["https://img.example/diag.png"])
        assert len(res_url) == 1
        assert mock_json.call_args[0][0] == [
            "attachment",
            "upload",
            "--attach-url",
            "https://img.example/diag.png",
            "ent-1",
        ]


def test_download_attachments(tmp_path):
    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = [{"id": "att-1", "path": str(tmp_path / "m.pdf"), "status": "downloaded", "bytes": 100}]
        dl = download_attachments("ent-2", tmp_path, ext="pdf", overwrite=True, dry_run=True)
        assert len(dl) == 1
        assert mock_json.call_args[0][0] == [
            "attachment",
            "download",
            "ent-2",
            "--all",
            "--out",
            str(tmp_path),
            "--ext",
            "pdf",
            "--overwrite",
            "--dry-run",
        ]

        dl_all = download_attachments(out_dir=tmp_path, all_items=True, ext="pdf")
        assert len(dl_all) == 1
        assert mock_json.call_args[0][0] == [
            "attachment",
            "download",
            "--all-items",
            "--out",
            str(tmp_path),
            "--ext",
            "pdf",
        ]

        dl_from = download_attachments(out_dir=tmp_path, items_from=["e1", "e2"], ext="pdf")
        assert len(dl_from) == 1
        assert mock_json.call_args[0][0] == [
            "attachment",
            "download",
            "--items-from",
            "-",
            "--out",
            str(tmp_path),
            "--ext",
            "pdf",
        ]
        assert mock_json.call_args[1]["stdin_data"] == "e1\ne2\n"

    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        assert download_attachments(out_dir=tmp_path, items_from=[]) == []
        mock_json.assert_not_called()


def test_api_request():
    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = [{"method": "POST", "url": "http://hb:7745/api/v1/groups"}]
        res = api_request(
            "POST",
            "groups",
            data={"name": "Lab"},
            query=[("limit", "10")],
            select="id,name",
            dry_run=True,
            hbctl_bin="/custom/hbctl",
        )
        assert isinstance(res, list)
        assert mock_json.call_args[0][0] == [
            "api",
            "POST",
            "groups",
            "--from-json",
            "-",
            "--query",
            "limit=10",
            "--select",
            "id,name",
            "--dry-run",
        ]
        assert json.loads(mock_json.call_args[1]["stdin_data"]) == {"name": "Lab"}
        assert mock_json.call_args[1]["hbctl_bin"] == "/custom/hbctl"

        mock_json.return_value = {"version": "0.27.1"}
        res_get = api_request("GET", "status")
        assert res_get == {"version": "0.27.1"}
        assert mock_json.call_args[0][0] == ["api", "GET", "status"]
        assert mock_json.call_args[1]["stdin_data"] is None


def test_maintenance_helpers():
    with patch("scripts.hbctl_client.hbctl_json") as mock_json:
        mock_json.return_value = [{"id": "m1", "name": "Test"}]
        assert list_maintenance() == [{"id": "m1", "name": "Test"}]
        assert mock_json.call_args[0][0] == ["maintenance", "list"]

        list_maintenance("e1", status="completed", select="id,name", dry_run=True)
        assert mock_json.call_args[0][0] == [
            "maintenance",
            "list",
            "--status",
            "completed",
            "--select",
            "id,name",
            "--dry-run",
            "e1",
        ]

        mock_json.return_value = {"id": "m2", "name": "Replaced valve"}
        created = create_maintenance(
            "e1",
            "Replaced valve",
            completed_date="2026-11-27",
            scheduled_date="2026-11-20",
            cost="29.99",
            description="Part: 00628334",
        )
        assert created["id"] == "m2"
        assert mock_json.call_args[0][0] == [
            "maintenance",
            "create",
            "--name",
            "Replaced valve",
            "--completed-date",
            "2026-11-27",
            "--scheduled-date",
            "2026-11-20",
            "--cost",
            "29.99",
            "--description",
            "Part: 00628334",
            "e1",
        ]

        mock_json.return_value = [{"method": "POST", "url": "http://hb:7745/api/v1/entities/e1/maintenance"}]
        dry_created = create_maintenance("e1", "Replaced valve", dry_run=True)
        assert isinstance(dry_created, dict)
        assert dry_created["method"] == "POST"

        mock_json.return_value = [{"method": "PUT", "url": "http://hb:7745/api/v1/maintenance/m1"}]
        updated = update_maintenance(
            "m1",
            name="Updated",
            completed_date="2026-11-28",
            cost="10.00",
            description="Note",
            dry_run=True,
        )
        assert isinstance(updated, dict)
        assert updated["method"] == "PUT"
        assert mock_json.call_args[0][0] == [
            "maintenance",
            "update",
            "--name",
            "Updated",
            "--completed-date",
            "2026-11-28",
            "--cost",
            "10.00",
            "--description",
            "Note",
            "--dry-run",
            "m1",
        ]

        mock_json.return_value = {"id": "m1", "deleted": True}
        deleted = delete_maintenance("m1")
        assert deleted == {"id": "m1", "deleted": True}
        assert mock_json.call_args[0][0] == ["maintenance", "delete", "--force", "m1"]

        mock_json.return_value = [{"method": "DELETE", "url": "http://hb:7745/api/v1/maintenance/m1"}]
        dry_deleted = delete_maintenance("m1", force=False, dry_run=True)
        assert isinstance(dry_deleted, dict)
        assert dry_deleted["method"] == "DELETE"
        assert mock_json.call_args[0][0] == ["maintenance", "delete", "--dry-run", "m1"]
