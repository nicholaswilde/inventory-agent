import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.download_lg_parts import (
    parse_assemblies_from_ajax_response,
    parse_assembly_details_response,
    generate_markdown_bom,
    generate_csv_bom,
    resolve_model_id,
)

SAMPLE_AJAX_ASSEMBLIES_HTML = """
<ul class="explodedview-assemblyul">
  <li class="explodedview-assemblyli">
    <a href="https://lgparts.com/pages/exploded-view-assembly?mfg=ZEN&parentId=131154&assemblyId=131157&ariId=131154">
      <input type="hidden" class="explodedview-assemblyId" value="131157">
      <img class="explodedview-assemblyImage" src="https://cdn.datamanager.arinet.com/image/ZEN/f600bd4d-8279-4860-a1ac-4d1febd047e7/Small">
      <span class="explodedview-assemblyName">Cabinet and Door Assembly: Gas Type</span>
    </a>
  </li>
  <li class="explodedview-assemblyli">
    <a href="https://lgparts.com/pages/exploded-view-assembly?mfg=ZEN&parentId=131154&assemblyId=131156&ariId=131154">
      <input type="hidden" class="explodedview-assemblyId" value="131156">
      <img class="explodedview-assemblyImage" src="https://cdn.datamanager.arinet.com/image/ZEN/7528db7c-9022-4f85-b354-6fbdda54e97d/Small">
      <span class="explodedview-assemblyName">Control Panel and Plate Assembly</span>
    </a>
  </li>
</ul>
"""

SAMPLE_AJAX_DETAILS_JSON = {
    "status": True,
    "data": {
        "assembly": {
            "AssemblyId": "131157",
            "Name": "Cabinet and Door Assembly: Gas Type",
            "ParentName": "ABWEEUS",
            "ImageUrl": "https://cdn.datamanager.arinet.com/image/ZEN/f600bd4d-8279-4860-a1ac-4d1febd047e7/ExtraLarge?ariz=4",
            "Parts": [
                {
                    "Tag": "K730",
                    "Sku": "AJU73432602",
                    "Description": "DRYER WATER INLET VALVE",
                }
            ],
        },
        "parts": [
            {
                "partNumber": "AJU73432602",
                "price": "103.95",
                "description": "Water Inlet Valve",
            }
        ],
    },
}


def test_parse_assemblies_from_ajax_response():
    assemblies = parse_assemblies_from_ajax_response(SAMPLE_AJAX_ASSEMBLIES_HTML)
    assert len(assemblies) == 2
    assert assemblies[0]["assembly_id"] == "131157"
    assert assemblies[0]["name"] == "Cabinet and Door Assembly: Gas Type"
    assert "f600bd4d" in assemblies[0]["thumb_url"]

    assert assemblies[1]["assembly_id"] == "131156"
    assert assemblies[1]["name"] == "Control Panel and Plate Assembly"


def test_parse_assembly_details_response():
    data = parse_assembly_details_response(SAMPLE_AJAX_DETAILS_JSON)
    assert data["name"] == "Cabinet and Door Assembly: Gas Type"
    assert "ExtraLarge" in data["image_url"]
    assert len(data["parts"]) == 1
    assert data["parts"][0]["callout"] == "K730"
    assert data["parts"][0]["part_number"] == "AJU73432602"
    assert data["parts"][0]["price"] == "103.95"
    assert "WATER INLET VALVE" in data["parts"][0]["description"].upper()


def test_generate_markdown_bom():
    assemblies_data = [
        {
            "assembly_id": "131157",
            "name": "Cabinet and Door Assembly: Gas Type",
            "diagram_file": "01_Cabinet_and_Door_Assembly.jpg",
            "parts": [
                {
                    "callout": "K730",
                    "part_number": "AJU73432602",
                    "description": "Water Inlet Valve",
                    "price": "103.95",
                    "status": "Available",
                }
            ],
        }
    ]
    md = generate_markdown_bom("DLGX7801WE", assemblies_data)
    assert "# Bill of Materials — LG DLGX7801WE" in md
    assert "Cabinet and Door Assembly: Gas Type" in md
    assert "AJU73432602" in md
    assert "$103.95" in md


def test_generate_csv_bom():
    assemblies_data = [
        {
            "assembly_id": "131157",
            "name": "Cabinet and Door Assembly: Gas Type",
            "diagram_file": "01_Cabinet_and_Door_Assembly.jpg",
            "parts": [
                {
                    "callout": "K730",
                    "part_number": "AJU73432602",
                    "description": "Water Inlet Valve",
                    "price": "103.95",
                    "status": "Available",
                }
            ],
        }
    ]
    csv_str = generate_csv_bom(assemblies_data)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 2
    assert "Assembly ID,Assembly Name,Callout,Part Number,Description,Price,Status,Diagram File" in lines[0]
    assert lines[1].startswith('131157,"Cabinet and Door Assembly: Gas Type",K730,AJU73432602,"Water Inlet Valve",103.95,Available,01_Cabinet_and_Door_Assembly.jpg')


def test_resolve_model_id():
    assert resolve_model_id("40660") == "LRDCS2603S"
    assert resolve_model_id("131154") == "DLGX7801WE"
    assert resolve_model_id("40660", "CUSTOM_MODEL") == "CUSTOM_MODEL"
    assert resolve_model_id("999999") == "LG_999999"


def test_download_lg_parts_orchestration(tmp_path):
    from unittest.mock import patch
    from scripts.download_lg_parts import download_lg_parts

    out_dir = tmp_path / "appliances" / "DLGX7801WE"

    def mock_fetch_details(parent_id, asm_id, **kwargs):
        return {
            "name": "Cabinet Assembly",
            "image_url": "http://example.com/lg.jpg",
            "parts": [
                {
                    "callout": "K730",
                    "part_number": "AJU73432602",
                    "description": "Water Valve",
                    "price": "100.00",
                    "status": "Available",
                }
            ],
        }

    with patch("scripts.download_lg_parts.fetch_lg_assemblies", return_value=[{"assembly_id": "131157", "name": "Cabinet Assembly"}]), \
         patch("scripts.download_lg_parts.fetch_lg_assembly_details", side_effect=mock_fetch_details), \
         patch("scripts.download_lg_parts.fetch_url", return_value=b"fake-image"), \
         patch("time.sleep", return_value=None):
        res = download_lg_parts("https://lgparts.com/pages/exploded-view-assembly?mfg=ZEN&parentId=131154", output_dir=out_dir)
        assert res == out_dir
        assert (out_dir / "bill_of_materials.json").exists()
        assert (out_dir / "bill_of_materials.csv").exists()
        assert (out_dir / "bill_of_materials.md").exists()
        assert (out_dir / "diagrams" / "01_Cabinet_Assembly.jpg").exists()


def test_download_lg_parts_main(tmp_path):
    from unittest.mock import patch
    from scripts.download_lg_parts import main

    with patch("sys.argv", ["download_lg_parts.py", "131154", "-o", str(tmp_path)]), \
         patch("scripts.download_lg_parts.download_lg_parts") as mock_dl:
        main()
        mock_dl.assert_called_once_with("131154", model_id=None, output_dir=str(tmp_path))

