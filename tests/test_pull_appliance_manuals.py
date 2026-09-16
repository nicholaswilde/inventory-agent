"""Tests for scripts/pull_appliance_manuals.py."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.pull_appliance_manuals import (
    get_homebox_config,
    get_appliance_entities_from_markdown,
    fetch_entity,
    download_attachment,
    pull_appliance_manuals,
    main,
)


def test_get_homebox_config_from_env(monkeypatch):
    monkeypatch.setenv("HOMEBOX_IP", "10.0.0.5")
    monkeypatch.setenv("HOMEBOX_API_KEY", "secret-test-key")
    ip, key = get_homebox_config()
    assert ip == "10.0.0.5"
    assert key == "secret-test-key"


def test_get_homebox_config_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HOMEBOX_IP", raising=False)
    monkeypatch.delenv("HOMEBOX_API_KEY", raising=False)

    fake_env = tmp_path / ".env"
    fake_env.write_text("HOMEBOX_IP=192.168.1.115\nHOMEBOX_API_KEY=hb_token123\n# comment\n")

    with patch("scripts.pull_appliance_manuals.Path.exists", return_value=True), \
         patch("scripts.pull_appliance_manuals.Path.read_text", return_value=fake_env.read_text()):
        ip, key = get_homebox_config()
        assert ip == "192.168.1.115"
        assert key == "hb_token123"

    with patch("scripts.pull_appliance_manuals.Path.exists", return_value=False), \
         pytest.raises(ValueError) as exc:
        get_homebox_config()
    assert "HOMEBOX_IP or HOMEBOX_API_KEY not set" in str(exc.value)


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


def test_fetch_entity():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "hb-123", "name": "Dishwasher"}

    with patch("requests.get", return_value=mock_resp):
        entity = fetch_entity("hb-123", "http://127.0.0.1:7745/api/v1", {})
        assert entity["id"] == "hb-123"

    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404
    with patch("requests.get", return_value=mock_resp_404):
        assert fetch_entity("hb-missing", "http://127.0.0.1:7745/api/v1", {}) is None


def test_download_attachment(tmp_path):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_content.return_value = [b"%PDF-1.6\n", b"content_bytes\n"]
    mock_resp.raise_for_status.return_value = None

    dest = tmp_path / "manuals" / "test_manual.pdf"
    with patch("requests.get", return_value=mock_resp):
        res = download_attachment("eid-1", "aid-1", dest, "http://127.0.0.1:7745/api/v1", {})
        assert res == dest
        assert dest.exists()
        assert dest.read_bytes() == b"%PDF-1.6\ncontent_bytes\n"


def test_pull_appliance_manuals_orchestration(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()
    out_dir = tmp_path / "manuals"

    (appliances_dir / "dishwasher.md").write_text(
        "# Bosch Dishwasher\n\n"
        "- **Homebox Entity ID**: `eid-bosch`\n"
    )

    mock_entity_data = {
        "id": "eid-bosch",
        "name": "Bosch Dishwasher",
        "attachments": [
            {
                "id": "aid-bosch-1",
                "title": "Bosch_Dishwasher_Manual.pdf",
                "mimeType": "application/pdf",
            }
        ],
    }

    mock_resp_get = MagicMock()
    mock_resp_get.status_code = 200
    mock_resp_get.json.return_value = mock_entity_data

    mock_resp_att = MagicMock()
    mock_resp_att.status_code = 200
    mock_resp_att.iter_content.return_value = [b"%PDF-1.6 fake-manual"]
    mock_resp_att.raise_for_status.return_value = None

    def mock_requests(url, **kwargs):
        if "attachments/aid-bosch-1" in url:
            return mock_resp_att
        return mock_resp_get

    with patch("scripts.pull_appliance_manuals.get_homebox_config", return_value=("127.0.0.1", "test-key")), \
         patch("requests.get", side_effect=mock_requests):
        res = pull_appliance_manuals(
            output_dir=out_dir,
            appliances_dir=appliances_dir,
            overwrite=False,
        )

    assert len(res) == 1
    assert res[0]["entity_name"] == "Bosch Dishwasher"
    assert res[0]["downloaded"] is True
    saved_file = out_dir / "Bosch_Dishwasher_Manual.pdf"
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"%PDF-1.6 fake-manual"

    # Running again without overwrite should skip re-download
    with patch("scripts.pull_appliance_manuals.get_homebox_config", return_value=("127.0.0.1", "test-key")), \
         patch("requests.get", side_effect=mock_requests):
        res_skip = pull_appliance_manuals(
            output_dir=out_dir,
            appliances_dir=appliances_dir,
            overwrite=False,
        )
    assert len(res_skip) == 1
    assert res_skip[0]["downloaded"] is False


def test_pull_appliance_manuals_scan_all(tmp_path):
    out_dir = tmp_path / "manuals"

    mock_list_resp = MagicMock()
    mock_list_resp.status_code = 200
    mock_list_resp.json.return_value = {
        "items": [
            {"id": "eid-dryer", "name": "LG Dryer"},
            {"id": "eid-faucet", "name": "Moen Kitchen Faucet"},
        ]
    }

    def mock_requests(url, **kwargs):
        if url.endswith("/entities"):
            return mock_list_resp
        if "eid-dryer" in url and "attachments/" not in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "id": "eid-dryer",
                "name": "LG Dryer",
                "attachments": [
                    {"id": "aid-dryer", "title": "LG_Dryer_Manual.pdf", "mimeType": "application/pdf"}
                ],
            }
            return m
        if "eid-faucet" in url and "attachments/" not in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {"id": "eid-faucet", "name": "Moen Kitchen Faucet", "attachments": []}
            return m
        if "attachments/aid-dryer" in url:
            m = MagicMock(status_code=200)
            m.iter_content.return_value = [b"%PDF dryer-manual"]
            m.raise_for_status.return_value = None
            return m
        return MagicMock(status_code=404)

    with patch("scripts.pull_appliance_manuals.get_homebox_config", return_value=("127.0.0.1", "test-key")), \
         patch("requests.get", side_effect=mock_requests):
        res = pull_appliance_manuals(
            output_dir=out_dir,
            scan_all=True,
        )

    assert len(res) == 1
    assert res[0]["entity_name"] == "LG Dryer"
    assert (out_dir / "LG_Dryer_Manual.pdf").exists()


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
