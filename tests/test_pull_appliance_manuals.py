"""Tests for scripts/pull_appliance_manuals.py."""
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.pull_appliance_manuals import (
    get_appliance_entities_from_markdown,
    main,
    pull_appliance_manuals,
)


def test_get_appliance_entities_from_markdown(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()

    md1 = appliances_dir / "dishwasher.md"
    md1.write_text(
        "# Bosch Dishwasher\n\n"
        "- **Homebox Entity ID**: `f6d4bac9-27dd-498e-8ba4-ad03374c905b`\n"
        "- **Manufacturer**: Bosch\n"
        "- **Manual Attachment**: Stored in Homebox entity and locally at `images/processed/Bosch_Dishwasher_Manual.pdf`\n"
    )

    md2 = appliances_dir / "dryer.md"
    md2.write_text(
        "# LG Dryer\n\n"
        "- **Homebox Entity ID**: `d4ba571f-ef19-4787-9926-ec40a177015d`\n"
    )

    md_ignored = appliances_dir / "no_id.md"
    md_ignored.write_text("# Unknown Appliance\n\nNo ID here.\n")

    entities = get_appliance_entities_from_markdown(appliances_dir)
    assert len(entities) == 2

    e0 = next(e for e in entities if e["name"] == "Bosch Dishwasher")
    assert e0["entity_id"] == "f6d4bac9-27dd-498e-8ba4-ad03374c905b"
    assert e0["manual_filename"] == "Bosch_Dishwasher_Manual.pdf"

    e1 = next(e for e in entities if e["name"] == "LG Dryer")
    assert e1["entity_id"] == "d4ba571f-ef19-4787-9926-ec40a177015d"
    assert e1["manual_filename"] is None


def test_pull_appliance_manuals_orchestration(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()
    out_dir = tmp_path / "manuals"

    (appliances_dir / "dishwasher.md").write_text(
        "# Bosch Dishwasher\n\n"
        "- **Homebox Entity ID**: `eid-bosch`\n"
    )

    dest_file = out_dir / "Bosch_Dishwasher_Manual.pdf"
    dl_payload = [
        {
            "entityId": "eid-bosch",
            "entityName": "Bosch Dishwasher",
            "id": "aid-bosch-1",
            "path": str(dest_file),
            "status": "downloaded",
            "bytes": 128,
        }
    ]
    skip_payload = [
        {
            "entityId": "eid-bosch",
            "entityName": "Bosch Dishwasher",
            "id": "aid-bosch-1",
            "path": str(dest_file),
            "status": "skipped",
            "bytes": 0,
        }
    ]

    with patch("scripts.pull_appliance_manuals.hbctl_client.download_attachments", return_value=dl_payload) as mock_dl:
        res = pull_appliance_manuals(
            output_dir=out_dir,
            appliances_dir=appliances_dir,
            overwrite=False,
        )
        mock_dl.assert_called_once_with(
            out_dir=out_dir,
            items_from=["eid-bosch"],
            ext="pdf",
            overwrite=False,
            dry_run=False,
        )

    assert len(res) == 1
    assert res[0]["entity_name"] == "Bosch Dishwasher"
    assert res[0]["filename"] == "Bosch_Dishwasher_Manual.pdf"
    assert res[0]["downloaded"] is True
    assert res[0]["already_existed"] is False

    with patch("scripts.pull_appliance_manuals.hbctl_client.download_attachments", return_value=skip_payload):
        res_skip = pull_appliance_manuals(
            output_dir=out_dir,
            appliances_dir=appliances_dir,
            overwrite=False,
        )
    assert len(res_skip) == 1
    assert res_skip[0]["downloaded"] is False
    assert res_skip[0]["already_existed"] is True


def test_pull_appliance_manuals_single_entity(tmp_path):
    out_dir = tmp_path / "manuals"
    dest_file = out_dir / "Manual.pdf"
    dl_payload = [
        {
            "entityId": "eid-1",
            "entityName": "Test Appliance",
            "id": "aid-1",
            "path": str(dest_file),
            "status": "downloaded",
            "bytes": 64,
        }
    ]
    with patch("scripts.pull_appliance_manuals.hbctl_client.download_attachments", return_value=dl_payload) as mock_dl:
        res = pull_appliance_manuals(output_dir=out_dir, entity_id="eid-1")
        mock_dl.assert_called_once_with("eid-1", out_dir, ext="pdf", overwrite=False, dry_run=False)
    assert len(res) == 1
    assert res[0]["entity_id"] == "eid-1"
    assert res[0]["entity_name"] == "Test Appliance"


def test_pull_appliance_manuals_dry_run_and_scan_all(tmp_path):
    out_dir = tmp_path / "manuals"
    dry_payload = [
        {
            "method": "GET",
            "url": "http://127.0.0.1:7745/api/v1/entities/eid-dryer/attachments/aid-dryer",
            "body": {
                "entityId": "eid-dryer",
                "entityName": "LG Dryer",
                "out": str(out_dir / "LG_Dryer_Manual.pdf"),
            },
        }
    ]

    with patch("scripts.pull_appliance_manuals.hbctl_client.download_attachments", return_value=dry_payload) as mock_dl:
        res = pull_appliance_manuals(
            output_dir=out_dir,
            scan_all=True,
            dry_run=True,
        )

    mock_dl.assert_called_once_with(
        out_dir=out_dir,
        all_items=True,
        ext="pdf",
        overwrite=False,
        dry_run=True,
    )
    assert len(res) == 1
    assert res[0]["entity_name"] == "LG Dryer"
    assert res[0]["entity_id"] == "eid-dryer"
    assert res[0]["attachment_id"] == "aid-dryer"
    assert res[0]["filename"] == "LG_Dryer_Manual.pdf"
    assert res[0]["downloaded"] is True
    assert res[0]["dry_run"] is True


def test_main_cli(tmp_path, capsys):
    with patch("sys.argv", ["pull_appliance_manuals.py", "-o", str(tmp_path), "--dry-run"]), \
         patch("scripts.pull_appliance_manuals.pull_appliance_manuals", return_value=[{"entity_name": "Dryer", "filename": "dryer.pdf", "downloaded": True}]):
        code = main()
        assert code == 0
        out = capsys.readouterr().out
        assert "Downloaded" in out
        assert "Dryer" in out

    with patch("sys.argv", ["pull_appliance_manuals.py", "-o", str(tmp_path)]), \
         patch("scripts.pull_appliance_manuals.pull_appliance_manuals", side_effect=RuntimeError("connection error")):
        code = main()
        assert code == 1
