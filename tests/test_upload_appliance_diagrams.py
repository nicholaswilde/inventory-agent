"""Tests for scripts/upload_appliance_diagrams.py."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.upload_appliance_diagrams import (
    get_homebox_config,
    find_appliance_diagram_mappings,
    get_entity_attachments,
    upload_diagram,
    upload_appliance_diagrams,
    main,
)


def test_get_homebox_config_from_env(monkeypatch):
    monkeypatch.setenv("HOMEBOX_IP", "10.0.0.8")
    monkeypatch.setenv("HOMEBOX_API_KEY", "upload-token-abc")
    ip, key = get_homebox_config()
    assert ip == "10.0.0.8"
    assert key == "upload-token-abc"


def test_get_homebox_config_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HOMEBOX_IP", raising=False)
    monkeypatch.delenv("HOMEBOX_API_KEY", raising=False)

    fake_env = tmp_path / ".env"
    fake_env.write_text("HOMEBOX_IP=192.168.1.115\nHOMEBOX_API_KEY=hb_token123\n")

    with patch("scripts.upload_appliance_diagrams.Path.exists", return_value=True), \
         patch("scripts.upload_appliance_diagrams.Path.read_text", return_value=fake_env.read_text()):
        ip, key = get_homebox_config()
        assert ip == "192.168.1.115"
        assert key == "hb_token123"

    with patch("scripts.upload_appliance_diagrams.Path.exists", return_value=False), \
         pytest.raises(ValueError) as exc:
        get_homebox_config()
    assert "HOMEBOX_IP or HOMEBOX_API_KEY not set" in str(exc.value)


def test_find_appliance_diagram_mappings(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()

    # Model 1 with direct BOM link
    md1 = appliances_dir / "bosch-dishwasher.md"
    md1.write_text(
        "# Bosch Dishwasher\n\n"
        "- **Homebox Entity ID**: `f6d4bac9-27dd-498e-8ba4-ad03374c905b`\n"
        "- **Full Parts List & Assembly Diagrams**: [SHXM98W75N-01 Bill of Materials](SHXM98W75N-01/bill_of_materials.md)\n"
    )

    bosch_model_dir = appliances_dir / "SHXM98W75N-01" / "diagrams"
    bosch_model_dir.mkdir(parents=True)
    d1 = bosch_model_dir / "01_diagram.png"
    d1.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    d2 = bosch_model_dir / "02_diagram.png"
    d2.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    # Model 2 matching folder name mentioned in markdown
    md2 = appliances_dir / "lg-dryer.md"
    md2.write_text(
        "# LG Dryer\n\n"
        "- **Homebox Entity ID**: `d4ba571f-ef19-4787-9926-ec40a177015d`\n"
        "- **Covered Models**: `DLGX7801WE`\n"
    )

    lg_model_dir = appliances_dir / "DLGX7801WE" / "diagrams"
    lg_model_dir.mkdir(parents=True)
    lg1 = lg_model_dir / "01_Cabinet.jpg"
    lg1.write_bytes(b"\xff\xd8\xfffake")

    # Model 3 with dry-run ID (should be ignored)
    md3 = appliances_dir / "ge-oven.md"
    md3.write_text(
        "# GE Oven\n\n"
        "- **Homebox Entity ID**: `dry-run-id`\n"
    )

    # Model 4 with no diagrams
    md4 = appliances_dir / "faucet.md"
    md4.write_text(
        "# Faucet\n\n"
        "- **Homebox Entity ID**: `faucet-eid`\n"
    )

    mappings = find_appliance_diagram_mappings(appliances_dir)

    assert len(mappings) == 2
    names = [m["name"] for m in mappings]
    assert "Bosch Dishwasher" in names
    assert "LG Dryer" in names

    bosch_map = next(m for m in mappings if m["name"] == "Bosch Dishwasher")
    assert bosch_map["entity_id"] == "f6d4bac9-27dd-498e-8ba4-ad03374c905b"
    assert len(bosch_map["diagrams"]) == 2

    lg_map = next(m for m in mappings if m["name"] == "LG Dryer")
    assert lg_map["entity_id"] == "d4ba571f-ef19-4787-9926-ec40a177015d"
    assert len(lg_map["diagrams"]) == 1


def test_get_entity_attachments():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "eid-1",
        "attachments": [
            {"id": "att-1", "title": "01_diagram.png", "mimeType": "image/png"},
            {"id": "att-2", "title": "manual.pdf", "mimeType": "application/pdf"},
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        atts = get_entity_attachments("eid-1", "http://127.0.0.1:7745/api/v1", {})
        assert "01_diagram.png" in atts
        assert "manual.pdf" in atts


def test_upload_diagram(tmp_path):
    img_file = tmp_path / "01_diagram.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp) as mock_post:
        res = upload_diagram("eid-1", img_file, "http://127.0.0.1:7745/api/v1", {})
        assert res is True
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert "files" in call_kwargs
        assert "data" in call_kwargs
        assert call_kwargs["data"]["name"] == "01_diagram.png"


def test_upload_appliance_diagrams_orchestration(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()

    md = appliances_dir / "bosch-dishwasher.md"
    md.write_text(
        "# Bosch Dishwasher\n\n"
        "- **Homebox Entity ID**: `eid-bosch`\n"
        "- **Full Parts List & Assembly Diagrams**: [SHXM98W75N-01 Bill of Materials](SHXM98W75N-01/bill_of_materials.md)\n"
    )

    diagrams_dir = appliances_dir / "SHXM98W75N-01" / "diagrams"
    diagrams_dir.mkdir(parents=True)
    d1 = diagrams_dir / "01_diagram.png"
    d1.write_bytes(b"\x89PNG fake")
    d2 = diagrams_dir / "02_diagram.png"
    d2.write_bytes(b"\x89PNG fake")

    # Mock config
    with patch("scripts.upload_appliance_diagrams.get_homebox_config", return_value=("127.0.0.1", "test-key")):
        # Mock get attachments: 01_diagram.png already exists, 02_diagram.png does not
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {
            "id": "eid-bosch",
            "name": "Bosch Dishwasher",
            "attachments": [
                {"id": "a-1", "title": "01_diagram.png", "mimeType": "image/png"}
            ],
        }

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.raise_for_status.return_value = None

        with patch("requests.get", return_value=mock_get), \
             patch("requests.post", return_value=mock_post):
            
            # Dry run
            dry_results = upload_appliance_diagrams(
                appliances_dir=appliances_dir,
                dry_run=True,
            )
            assert len(dry_results) == 2
            d1_res = next(r for r in dry_results if r["filename"] == "01_diagram.png")
            d2_res = next(r for r in dry_results if r["filename"] == "02_diagram.png")
            assert d1_res["already_existed"] is True
            assert d2_res["already_existed"] is False
            assert d2_res["uploaded"] is False
            assert d2_res["dry_run"] is True

            # Real upload without overwrite: uploads d2, skips d1
            real_results = upload_appliance_diagrams(
                appliances_dir=appliances_dir,
                dry_run=False,
                overwrite=False,
            )
            d1_res = next(r for r in real_results if r["filename"] == "01_diagram.png")
            d2_res = next(r for r in real_results if r["filename"] == "02_diagram.png")
            assert d1_res["uploaded"] is False
            assert d2_res["uploaded"] is True

            # Real upload with overwrite: uploads both d1 and d2
            overwrite_results = upload_appliance_diagrams(
                appliances_dir=appliances_dir,
                dry_run=False,
                overwrite=True,
            )
            d1_res = next(r for r in overwrite_results if r["filename"] == "01_diagram.png")
            d2_res = next(r for r in overwrite_results if r["filename"] == "02_diagram.png")
            assert d1_res["uploaded"] is True
            assert d2_res["uploaded"] is True


def test_upload_appliance_diagrams_filter_entity(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()

    md1 = appliances_dir / "app1.md"
    md1.write_text("# App 1\n\n- **Homebox Entity ID**: `eid-1`\n- **Covered Models**: `MOD1`\n")
    d_dir1 = appliances_dir / "MOD1" / "diagrams"
    d_dir1.mkdir(parents=True)
    (d_dir1 / "diag1.png").write_bytes(b"img")

    md2 = appliances_dir / "app2.md"
    md2.write_text("# App 2\n\n- **Homebox Entity ID**: `eid-2`\n- **Covered Models**: `MOD2`\n")
    d_dir2 = appliances_dir / "MOD2" / "diagrams"
    d_dir2.mkdir(parents=True)
    (d_dir2 / "diag2.png").write_bytes(b"img")

    with patch("scripts.upload_appliance_diagrams.get_homebox_config", return_value=("127.0.0.1", "test-key")), \
         patch("scripts.upload_appliance_diagrams.get_entity_attachments", return_value=set()):
        results = upload_appliance_diagrams(
            appliances_dir=appliances_dir,
            entity_id="eid-2",
            dry_run=True,
        )
        assert len(results) == 1
        assert results[0]["entity_id"] == "eid-2"
        assert results[0]["filename"] == "diag2.png"


def test_main_cli(capsys):
    with patch("sys.argv", ["upload_appliance_diagrams.py", "--dry-run"]), \
         patch("scripts.upload_appliance_diagrams.upload_appliance_diagrams", return_value=[{"entity_name": "Dryer", "filename": "01.jpg", "uploaded": True, "dry_run": True, "path": "p"}]):
        code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Would upload" in out
        assert "Dryer" in out

    with patch("sys.argv", ["upload_appliance_diagrams.py"]), \
         patch("scripts.upload_appliance_diagrams.upload_appliance_diagrams", return_value=[]):
        code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "No diagrams found" in out

    with patch("sys.argv", ["upload_appliance_diagrams.py"]), \
         patch("scripts.upload_appliance_diagrams.upload_appliance_diagrams", side_effect=RuntimeError("fail")):
        code = main()
        assert code == 1
