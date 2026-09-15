import json
import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.query_appliance import (
    list_appliances,
    get_appliance_info,
    search_parts,
    search_error_codes,
    search_appliances,
    main,
)


@pytest.fixture
def sample_appliances_dir(tmp_path):
    appliances_dir = tmp_path / "appliances"
    appliances_dir.mkdir()

    # Markdown cheat sheet
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
| **Weight** | 100 lb |

---

## Part & Accessory Numbers

- **Full Parts List & Assembly Diagrams**: [WT100 Bill of Materials](WT100/bill_of_materials.md)
- Water Hose Kit (Part # WH123)

---

## Error Codes & Diagnostics

| Code | Meaning | Action |
|---|---|---|
| `IE` | Water Inlet Error | Check supply valves |
| `UE` | Unbalanced Load | Redistribute laundry |
"""
    )

    # Model directory with BOM
    model_dir = appliances_dir / "WT100"
    model_dir.mkdir()
    diagrams_dir = model_dir / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "01_drum.jpg").write_bytes(b"dummy image")

    bom_json = model_dir / "bill_of_materials.json"
    bom_data = {
        "model": "WT100",
        "assemblies": [
            {
                "name": "Drum and Motor Assembly",
                "diagram_file": "01_drum.jpg",
                "parts": [
                    {
                        "callout": "D01",
                        "part_number": "P10001",
                        "description": "Washer Drive Motor",
                        "price": "149.99",
                        "status": "Available",
                        "url": "https://example.com/parts/P10001",
                    },
                    {
                        "callout": "D02",
                        "part_number": "P10002",
                        "description": "Drain Pump Filter",
                        "price": "29.99",
                        "status": "Available",
                        "url": "https://example.com/parts/P10002",
                    },
                ],
            }
        ],
    }
    bom_json.write_text(json.dumps(bom_data))

    return appliances_dir


def test_list_appliances(sample_appliances_dir):
    appliances = list_appliances(sample_appliances_dir)
    assert len(appliances) == 1
    app = appliances[0]
    assert app["slug"] == "sample-washer"
    assert app["name"] == "Sample Washer"
    assert app["manufacturer"] == "Acme"
    assert "WT100" in app["covered_models"]
    assert app["homebox_id"] == "test-uuid-1234"
    assert app["has_bom"] is True
    assert app["total_parts"] == 2


def test_get_appliance_info(sample_appliances_dir):
    info = get_appliance_info(sample_appliances_dir, "sample-washer")
    assert info is not None
    assert info["name"] == "Sample Washer"
    assert info["specs"]["Capacity"] == "5.0 cu.ft."
    assert len(info["error_codes"]) == 2
    assert info["error_codes"][0]["code"] == "IE"
    assert info["error_codes"][0]["meaning"] == "Water Inlet Error"
    assert len(info["assemblies"]) == 1
    assert info["assemblies"][0]["name"] == "Drum and Motor Assembly"


def test_get_appliance_info_by_model(sample_appliances_dir):
    info = get_appliance_info(sample_appliances_dir, "WT100")
    assert info is not None
    assert info["slug"] == "sample-washer"


def test_search_parts(sample_appliances_dir):
    # Search by part number
    results = search_parts(sample_appliances_dir, "P10001")
    assert len(results) == 1
    assert results[0]["part_number"] == "P10001"
    assert results[0]["description"] == "Washer Drive Motor"
    assert results[0]["callout"] == "D01"
    assert results[0]["price"] == "149.99"

    # Search by keyword in description
    results = search_parts(sample_appliances_dir, "pump")
    assert len(results) == 1
    assert results[0]["part_number"] == "P10002"
    assert "Drain Pump" in results[0]["description"]

    # Filter by model
    results = search_parts(sample_appliances_dir, "pump", model="WT100")
    assert len(results) == 1

    # Filter by nonexistent model
    results = search_parts(sample_appliances_dir, "pump", model="NONEXISTENT")
    assert len(results) == 0


def test_search_error_codes(sample_appliances_dir):
    results = search_error_codes(sample_appliances_dir, "IE")
    assert len(results) == 1
    assert results[0]["code"] == "IE"
    assert results[0]["meaning"] == "Water Inlet Error"

    # Search by action / meaning text
    results = search_error_codes(sample_appliances_dir, "unbalanced")
    assert len(results) == 1
    assert results[0]["code"] == "UE"


def test_search_appliances_unified(sample_appliances_dir):
    results = search_appliances(sample_appliances_dir, "washer")
    assert len(results["appliances"]) >= 1
    assert len(results["parts"]) >= 1


def test_cli_list(sample_appliances_dir, capsys):
    ret = main(["--dir", str(sample_appliances_dir), "list"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Sample Washer" in captured.out
    assert "WT100" in captured.out


def test_cli_search_json(sample_appliances_dir, capsys):
    ret = main(["--dir", str(sample_appliances_dir), "search", "pump", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data["parts"]) == 1
    assert data["parts"][0]["part_number"] == "P10002"
