import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.appliance_maintenance import (
    create_maintenance,
    delete_maintenance,
    insert_maintenance_row,
    list_maintenance,
    load_homebox_config,
    main,
    normalize_api_cost,
    normalize_api_date,
    resolve_target,
)


@pytest.fixture
def sample_appliances_dir(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()

    washer_md = appliances_dir / "sample-washer.md"
    washer_md.write_text(
        """# Sample Washer

- **Homebox Entity ID**: `test-uuid-1234`
- **Manufacturer**: Acme
- **Covered Models**: `WT100` (`WT100A / WT100B`)
- **Manual Part Number**: M12345

---

## Specifications

| Spec | Value |
|---|---|
| **Capacity** | 5.0 cu.ft. |
""",
        encoding="utf-8",
    )

    oven_md = appliances_dir / "sample-oven.md"
    oven_md.write_text(
        """# Sample Oven

- **Homebox Entity ID**: `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`
- **Manufacturer**: GE
- **Model**: `JT5500`

---

## Maintenance History

| Date | Action | Part(s) | Cost | Notes |
|---|---|---|---|---|
| 2026-11 | Replaced relay board | `WB27X25594` | - | November swap |
| 2024-02 (approx.) | Replaced cooling fan | `WB26X35088` | - | Fan replacement |
""",
        encoding="utf-8",
    )
    return appliances_dir


def test_normalize_api_date():
    assert normalize_api_date("2026-03-15") == "2026-03-15"
    assert normalize_api_date("2026-03") == "2026-03-01"
    for bad in ("March 2026", "2026-13-01", "2026-02-30", ""):
        with pytest.raises(ValueError):
            normalize_api_date(bad)


def test_normalize_api_cost():
    assert normalize_api_cost("$29.99") == "29.99"
    assert normalize_api_cost(" 1,245.50 ") == "1245.50"
    assert normalize_api_cost("45") == "45"
    assert normalize_api_cost("") is None
    assert normalize_api_cost("-") is None
    assert normalize_api_cost(None) is None
    with pytest.raises(ValueError):
        normalize_api_cost("abc")


def test_load_homebox_config(tmp_path, monkeypatch):
    monkeypatch.delenv("HOMEBOX_URL", raising=False)
    monkeypatch.delenv("HOMEBOX_IP", raising=False)
    monkeypatch.delenv("HOMEBOX_API_KEY", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        '# comment\nHOMEBOX_IP="192.168.1.50"\nHOMEBOX_API_KEY=\'secret-key-123\'\n',
        encoding="utf-8",
    )
    url, key = load_homebox_config(env_file)
    assert url == "http://192.168.1.50:7745"
    assert key == "secret-key-123"

    # Env vars override .env file, HOMEBOX_URL overrides HOMEBOX_IP
    monkeypatch.setenv("HOMEBOX_URL", "https://hb.example.com/")
    monkeypatch.setenv("HOMEBOX_API_KEY", "env-key")
    url2, key2 = load_homebox_config(env_file)
    assert url2 == "https://hb.example.com"
    assert key2 == "env-key"

    # Missing config raises RuntimeError
    monkeypatch.delenv("HOMEBOX_URL", raising=False)
    monkeypatch.delenv("HOMEBOX_API_KEY", raising=False)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("HOMEBOX_IP=127.0.0.1\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_homebox_config(empty_env)


def test_resolve_target(sample_appliances_dir):
    by_slug = resolve_target(sample_appliances_dir, "sample-washer")
    assert by_slug["homebox_id"] == "test-uuid-1234"
    assert by_slug["md_path"] == sample_appliances_dir / "sample-washer.md"

    by_model = resolve_target(sample_appliances_dir, "WT100")
    assert by_model["slug"] == "sample-washer"

    by_uuid_doc = resolve_target(sample_appliances_dir, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert by_uuid_doc["slug"] == "sample-oven"

    raw_uuid = "11111111-2222-3333-4444-555555555555"
    raw_res = resolve_target(sample_appliances_dir, raw_uuid)
    assert raw_res["homebox_id"] == raw_uuid
    assert raw_res["md_path"] is None

    with pytest.raises(ValueError):
        resolve_target(sample_appliances_dir, "nonexistent-appliance")


def test_insert_maintenance_row_creates_section(sample_appliances_dir):
    washer_path = sample_appliances_dir / "sample-washer.md"
    updated = insert_maintenance_row(
        washer_path.read_text(encoding="utf-8"),
        date="2026-05-10",
        action="Cleaned drain | pump",
        parts="P10002",
        cost="$12.50",
        notes="Line 1\nLine 2",
    )
    assert "## Maintenance History" in updated
    assert "| 2026-05-10 | Cleaned drain / pump | `P10002` | $12.50 | Line 1 Line 2 |" in updated


def test_insert_maintenance_row_reverse_chronological(sample_appliances_dir):
    oven_path = sample_appliances_dir / "sample-oven.md"
    updated = insert_maintenance_row(
        oven_path.read_text(encoding="utf-8"),
        date="2026-03",
        action="Replaced relay board",
        parts="WB27X25594",
        cost="-",
        notes="March swap",
    )
    lines = [ln for ln in updated.splitlines() if ln.startswith("| 20")]
    assert len(lines) == 3
    assert lines[0].startswith("| 2026-11 ")
    assert lines[1].startswith("| 2026-03 ")
    assert lines[2].startswith("| 2024-02 (approx.) ")


def test_http_helpers():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"id": "m1", "name": "Test"}]

    with patch("scripts.appliance_maintenance.requests.request", return_value=mock_resp) as req:
        items = list_maintenance("http://hb:7745", "tok", entity_id="e1", status="completed")
        assert items == [{"id": "m1", "name": "Test"}]
        req.assert_called_once()
        assert req.call_args.args[:2] == ("GET", "http://hb:7745/api/v1/entities/e1/maintenance")

    with patch("scripts.appliance_maintenance.requests.request", return_value=mock_resp) as req:
        list_maintenance("http://hb:7745", "tok")
        assert req.call_args.args[:2] == ("GET", "http://hb:7745/api/v1/maintenance")
        assert req.call_args.kwargs["params"] == {"status": "both"}

    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"id": "m2"}
    with patch("scripts.appliance_maintenance.requests.request", return_value=mock_post) as req:
        created = create_maintenance("http://hb:7745", "tok", "e1", {"name": "Fix"})
        assert created["id"] == "m2"
        assert req.call_args.args[:2] == ("POST", "http://hb:7745/api/v1/entities/e1/maintenance")

    mock_del = MagicMock()
    mock_del.status_code = 204
    with patch("scripts.appliance_maintenance.requests.request", return_value=mock_del) as req:
        delete_maintenance("http://hb:7745", "tok", "m2")
        assert req.call_args.args[:2] == ("DELETE", "http://hb:7745/api/v1/maintenance/m2")


def test_cli_list(sample_appliances_dir, capsys, monkeypatch):
    monkeypatch.setenv("HOMEBOX_URL", "http://hb:7745")
    monkeypatch.setenv("HOMEBOX_API_KEY", "tok")
    entries = [
        {
            "id": "entry-1",
            "name": "Replaced fan",
            "completedDate": "2024-02-01",
            "scheduledDate": "",
            "cost": "0",
            "itemName": "Sample Oven",
            "itemID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        }
    ]

    with patch("scripts.appliance_maintenance.list_maintenance", return_value=entries) as mock_list:
        rc = main(["--dir", str(sample_appliances_dir), "list", "sample-oven"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Replaced fan" in out
        assert "entry-1" in out
        mock_list.assert_called_once_with(
            "http://hb:7745", "tok", entity_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", status="both"
        )

    with patch("scripts.appliance_maintenance.list_maintenance", return_value=entries):
        rc = main(["--dir", str(sample_appliances_dir), "--json", "list"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["id"] == "entry-1"


def test_cli_log_modes(sample_appliances_dir, capsys, monkeypatch):
    monkeypatch.setenv("HOMEBOX_URL", "http://hb:7745")
    monkeypatch.setenv("HOMEBOX_API_KEY", "tok")
    washer_path = sample_appliances_dir / "sample-washer.md"
    original_md = washer_path.read_text(encoding="utf-8")

    # 1. --dry-run makes no HTTP call and leaves file untouched
    with patch("scripts.appliance_maintenance.create_maintenance") as mock_create:
        rc = main([
            "--dir", str(sample_appliances_dir), "--dry-run",
            "log", "sample-washer", "--name", "Clean filter", "--date", "2026-06", "--part", "P10002",
        ])
        assert rc == 0
        mock_create.assert_not_called()
        assert washer_path.read_text(encoding="utf-8") == original_md
        assert "DRY RUN" in capsys.readouterr().out

    # 2. --local-only skips HTTP, writes markdown
    with patch("scripts.appliance_maintenance.create_maintenance") as mock_create:
        rc = main([
            "--dir", str(sample_appliances_dir),
            "log", "sample-washer", "--name", "Clean filter", "--date", "2026-06", "--local-only",
        ])
        assert rc == 0
        mock_create.assert_not_called()
        assert "| 2026-06 | Clean filter |" in washer_path.read_text(encoding="utf-8")
        capsys.readouterr()

    # Reset markdown
    washer_path.write_text(original_md, encoding="utf-8")

    # 3. --homebox-only skips markdown, calls HTTP
    with patch("scripts.appliance_maintenance.create_maintenance", return_value={"id": "hb-1"}) as mock_create:
        rc = main([
            "--dir", str(sample_appliances_dir),
            "log", "sample-washer", "--name", "Inspect hose", "--scheduled", "2026-12", "--homebox-only",
        ])
        assert rc == 0
        mock_create.assert_called_once()
        payload = mock_create.call_args.args[3]
        assert payload["scheduledDate"] == "2026-12-01"
        assert "completedDate" not in payload
        assert washer_path.read_text(encoding="utf-8") == original_md
        capsys.readouterr()

    # 4. Full log updates both Homebox and markdown
    with patch("scripts.appliance_maintenance.create_maintenance", return_value={"id": "hb-2"}) as mock_create:
        rc = main([
            "--dir", str(sample_appliances_dir), "--json",
            "log", "sample-washer",
            "--name", "Replaced drain pump",
            "--date", "2026-07-04",
            "--display-date", "2026-07-04",
            "--part", "P10002",
            "--cost", "$29.99",
            "--notes", "Routine swap",
        ])
        assert rc == 0
        mock_create.assert_called_once()
        payload = mock_create.call_args.args[3]
        assert payload["completedDate"] == "2026-07-04"
        assert payload["cost"] == "29.99"
        assert "P10002" in payload["description"]
        res = json.loads(capsys.readouterr().out)
        assert res["homebox"]["id"] == "hb-2"
        assert "| 2026-07-04 | Replaced drain pump | `P10002` | $29.99 | Routine swap |" in washer_path.read_text(encoding="utf-8")


def test_cli_delete(sample_appliances_dir, capsys, monkeypatch):
    monkeypatch.setenv("HOMEBOX_URL", "http://hb:7745")
    monkeypatch.setenv("HOMEBOX_API_KEY", "tok")

    with patch("scripts.appliance_maintenance.delete_maintenance") as mock_del:
        rc = main(["--dir", str(sample_appliances_dir), "--dry-run", "delete", "entry-99"])
        assert rc == 0
        mock_del.assert_not_called()
        assert "DRY RUN" in capsys.readouterr().out

    with patch("scripts.appliance_maintenance.delete_maintenance") as mock_del:
        rc = main(["--dir", str(sample_appliances_dir), "delete", "entry-99"])
        assert rc == 0
        mock_del.assert_called_once_with("http://hb:7745", "tok", "entry-99")
