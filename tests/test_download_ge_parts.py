import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.download_ge_parts import (
    extract_assemblies_from_model_html,
    parse_section_parts,
    generate_markdown_bom,
    generate_csv_bom,
)

SAMPLE_MODEL_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Model Search | JT5500SF1SS</title></head>
<body>
<ul>
  <li>
    <a href="/store/parts/ModelSectionParts/JT5500SF1SS/1/0/0/0/CONTROL_PANEL">
      <img src="https://assets.geappliances.io/parts/00100000/00118700/480/00118767.p01_480.jpg" alt="Control Panel" />
      <span>CONTROL PANEL</span>
    </a>
  </li>
  <li>
    <a href="/store/parts/ModelSectionParts/JT5500SF1SS/2/0/0/0/UPPER_OVEN">
      <img src="https://assets.geappliances.io/parts/00100000/00118700/480/00118767.p02_480.jpg" alt="Upper Oven" />
      <span>UPPER OVEN</span>
    </a>
  </li>
</ul>
</body>
</html>
"""

SAMPLE_SECTION_HTML = """
<div class="assembly-parts">
  <div class="part-item">
    <strong>1</strong> &mdash; Diagram Number
    <div class="row">
      <a class="gotham-bold" href="/store/parts/spec/WB07T10769">Double Wall oven Control panel with glass touch STAINLESS</a>
      <p>WB07T10769</p>
      <span class="bold-price"><sup>$</sup>418.39</span>
    </div>
  </div>
  <div class="part-item">
    <strong>7</strong> &mdash; Diagram Number
    <div class="row">
      <a class="gotham-bold" href="/store/parts/spec/WB07T10740">Wall oven Control mounting bracket</a>
      <p>WB07T10740</p>
      <p class="not-available">No longer available</p>
    </div>
  </div>
</div>
"""


def test_extract_assemblies_from_model_html():
    assemblies = extract_assemblies_from_model_html(SAMPLE_MODEL_PAGE_HTML)
    assert len(assemblies) == 2
    
    assert assemblies[0]["section_num"] == 1
    assert assemblies[0]["name"] == "CONTROL_PANEL"
    assert "/store/parts/ModelSectionParts/JT5500SF1SS/1/0/0/0/CONTROL_PANEL" in assemblies[0]["url"]
    assert "00118767.p01_2325.jpg" in assemblies[0]["diagram_highres_url"]
    assert "00118767.p01_480.jpg" in assemblies[0]["diagram_thumb_url"]

    assert assemblies[1]["section_num"] == 2
    assert assemblies[1]["name"] == "UPPER_OVEN"
    assert "00118767.p02_2325.jpg" in assemblies[1]["diagram_highres_url"]


def test_parse_section_parts():
    parts = parse_section_parts(SAMPLE_SECTION_HTML)
    assert len(parts) == 2

    assert parts[0]["callout"] == "1"
    assert parts[0]["part_number"] == "WB07T10769"
    assert "Control panel" in parts[0]["description"]
    assert parts[0]["price"] == "418.39"
    assert parts[0]["status"] == "Available"

    assert parts[1]["callout"] == "7"
    assert parts[1]["part_number"] == "WB07T10740"
    assert parts[1]["status"] == "No longer available"
    assert parts[1]["price"] == "N/A"


def test_generate_markdown_bom():
    assemblies_data = [
        {
            "name": "CONTROL_PANEL",
            "section_num": 1,
            "diagram_file": "01_CONTROL_PANEL.jpg",
            "parts": [
                {
                    "callout": "1",
                    "part_number": "WB07T10769",
                    "description": "Control panel",
                    "price": "418.39",
                    "status": "Available",
                }
            ],
        }
    ]
    md = generate_markdown_bom("JT5500SF1SS", assemblies_data)
    assert "# Bill of Materials — GE JT5500SF1SS" in md
    assert "## 1. Control Panel" in md
    assert "WB07T10769" in md
    assert "$418.39" in md


def test_generate_csv_bom():
    assemblies_data = [
        {
            "name": "CONTROL_PANEL",
            "section_num": 1,
            "diagram_file": "01_CONTROL_PANEL.jpg",
            "parts": [
                {
                    "callout": "1",
                    "part_number": "WB07T10769",
                    "description": "Control panel",
                    "price": "418.39",
                    "status": "Available",
                }
            ],
        }
    ]
    csv_str = generate_csv_bom(assemblies_data)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 2
    assert "Section Number,Section Name,Callout,Part Number,Description,Price,Status,Diagram File" in lines[0]
    assert lines[1].startswith('1,CONTROL_PANEL,1,WB07T10769,"Control panel",418.39,Available,01_CONTROL_PANEL.jpg')


def test_download_ge_parts_orchestration(tmp_path):
    from scripts.download_ge_parts import download_ge_parts

    out_dir = tmp_path / "appliances" / "JT5500SF1SS"

    def mock_fetch(url):
        if "assembly/" in url:
            return SAMPLE_MODEL_PAGE_HTML.encode("utf-8")
        if "ModelSectionParts" in url:
            return SAMPLE_SECTION_HTML.encode("utf-8")
        return b"fake-jpeg-bytes"

    with patch("scripts.download_ge_parts.fetch_url", side_effect=mock_fetch):
        res = download_ge_parts("JT5500SF1SS", output_dir=out_dir, delay=0)
        assert res["model_id"] == "JT5500SF1SS"
        assert (out_dir / "bill_of_materials.json").exists()
        assert (out_dir / "bill_of_materials.csv").exists()
        assert (out_dir / "bill_of_materials.md").exists()
        assert (out_dir / "diagrams" / "01_CONTROL_PANEL.jpg").exists()


def test_download_ge_parts_main(tmp_path):
    from scripts.download_ge_parts import main

    with patch("sys.argv", ["download_ge_parts.py", "JT5500SF1SS", "-o", str(tmp_path)]), \
         patch("scripts.download_ge_parts.download_ge_parts") as mock_dl:
        main()
        mock_dl.assert_called_once_with(model_id="JT5500SF1SS", output_dir=str(tmp_path))

    with patch("sys.argv", ["download_ge_parts.py", "https://www.geapplianceparts.com/store/parts/assembly/JT5500SF1SS"]), \
         patch("scripts.download_ge_parts.download_ge_parts") as mock_dl:
        main()
        assert mock_dl.call_args[1]["model_id"] == "JT5500SF1SS"

    with patch("sys.argv", ["download_ge_parts.py", "error"]), \
         patch("scripts.download_ge_parts.download_ge_parts", side_effect=RuntimeError("boom")), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
