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
    create_item,
    download_attachments,
    export_items,
    export_markdown,
    get_field_value,
    get_item,
    hbctl_json,
    list_items,
    run_hbctl,
    search_items,
    update_item,
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
        assert list_items(tag="electronics", has_field="Voltage", select="id,name") == [
            {"id": "e1", "name": "ESP32"}
        ]
        assert mock_json.call_args[0][0] == [
            "item",
            "list",
            "--all",
            "--tag",
            "electronics",
            "--has-field",
            "Voltage",
            "--select",
            "id,name",
        ]

        mock_json.return_value = [{"id": "e2"}]
        assert search_items(
            "ESP32",
            tag="mcu",
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
