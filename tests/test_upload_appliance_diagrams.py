"""Tests for scripts/upload_appliance_diagrams.py."""
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.upload_appliance_diagrams import (
    find_appliance_diagram_mappings,
    main,
    upload_appliance_diagrams,
)


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

    # Dry run returns DryRunRequest[] from hbctl
    dry_payload = [
        {"method": "POST", "url": "http://127.0.0.1:7745/api/v1/entities/eid-bosch/attachments", "body": {"name": "01_diagram.png", "file": str(d1)}},
        {"method": "POST", "url": "http://127.0.0.1:7745/api/v1/entities/eid-bosch/attachments", "body": {"name": "02_diagram.png", "file": str(d2)}},
    ]
    with patch("scripts.upload_appliance_diagrams.hbctl_client.upload_attachments", return_value=dry_payload) as mock_up:
        dry_results = upload_appliance_diagrams(appliances_dir=appliances_dir, dry_run=True)
        mock_up.assert_called_once_with(
            "eid-bosch",
            [d1, d2],
            overwrite=False,
            force=True,
            dry_run=True,
        )
        assert len(dry_results) == 2
        assert all(r["dry_run"] is True and r["uploaded"] is False for r in dry_results)

    # Live upload without overwrite: d1 skipped, d2 uploaded
    live_payload = [
        {"file": "01_diagram.png", "status": "skipped", "id": "a-1"},
        {"file": "02_diagram.png", "status": "uploaded", "id": "a-2"},
    ]
    with patch("scripts.upload_appliance_diagrams.hbctl_client.upload_attachments", return_value=live_payload):
        real_results = upload_appliance_diagrams(
            appliances_dir=appliances_dir,
            dry_run=False,
            overwrite=False,
        )
        d1_res = next(r for r in real_results if r["filename"] == "01_diagram.png")
        d2_res = next(r for r in real_results if r["filename"] == "02_diagram.png")
        assert d1_res["uploaded"] is False
        assert d1_res["already_existed"] is True
        assert d2_res["uploaded"] is True
        assert d2_res["already_existed"] is False

    # Live upload with overwrite: both uploaded
    overwrite_payload = [
        {"file": "01_diagram.png", "status": "uploaded", "id": "a-1-new"},
        {"file": "02_diagram.png", "status": "uploaded", "id": "a-2-new"},
    ]
    with patch("scripts.upload_appliance_diagrams.hbctl_client.upload_attachments", return_value=overwrite_payload) as mock_up:
        overwrite_results = upload_appliance_diagrams(
            appliances_dir=appliances_dir,
            dry_run=False,
            overwrite=True,
        )
        mock_up.assert_called_once_with(
            "eid-bosch",
            [d1, d2],
            overwrite=True,
            force=True,
            dry_run=False,
        )
        assert all(r["uploaded"] is True for r in overwrite_results)


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
    d2 = d_dir2 / "diag2.png"
    d2.write_bytes(b"img")

    dry_payload = [
        {"method": "POST", "url": "http://127.0.0.1:7745/api/v1/entities/eid-2/attachments", "body": {"name": "diag2.png", "file": str(d2)}},
    ]
    with patch("scripts.upload_appliance_diagrams.hbctl_client.upload_attachments", return_value=dry_payload) as mock_up:
        results = upload_appliance_diagrams(
            appliances_dir=appliances_dir,
            entity_id="eid-2",
            dry_run=True,
        )
        mock_up.assert_called_once_with("eid-2", [d2], overwrite=False, force=True, dry_run=True)
        assert len(results) == 1
        assert results[0]["entity_id"] == "eid-2"
        assert results[0]["filename"] == "diag2.png"


def test_main_cli(capsys):
    with patch("sys.argv", ["upload_appliance_diagrams.py", "--dry-run"]), \
         patch("scripts.upload_appliance_diagrams.upload_appliance_diagrams", return_value=[{"entity_name": "Dryer", "filename": "01.jpg", "uploaded": False, "dry_run": True, "path": "p"}]):
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
