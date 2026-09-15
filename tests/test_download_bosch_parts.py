import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.download_bosch_parts import (
    extract_bosch_data_from_html,
    generate_markdown_bom,
    generate_csv_bom,
)

SAMPLE_BOSCH_HTML = """
<!DOCTYPE html>
<html>
<head><title>Replacement Parts - SHXM98W75N/01 | BOSCH US</title></head>
<body>
<script>self.__next_f.push([1,"43:[\\"$\\",\\"$L11\\",null,{\\"content\\":{\\"variantId\\":\\"SHXM98W75N/01\\",\\"galleryImages\\":[{\\"id\\":\\"58300000201899_aet_000_b_01\\",\\"url\\":\\"https://media3.bsh-group.com/Documents/58300000201899_aet_000_b_01.png\\",\\"positionNumber\\":\\"01\\"},{\\"id\\":\\"58300000201899_aet_000_b_02\\",\\"url\\":\\"https://media3.bsh-group.com/Documents/58300000201899_aet_000_b_02.png\\",\\"positionNumber\\":\\"02\\"}],\\"bomRelations\\":[{\\"productId\\":\\"11019860\\",\\"positionNumber\\":\\"0101\\"},{\\"productId\\":\\"12008387\\",\\"positionNumber\\":\\"0109\\"}]}}]\n"])</script>
</body>
</html>
"""


def test_extract_bosch_data_from_html():
    images, bom = extract_bosch_data_from_html(SAMPLE_BOSCH_HTML)
    assert len(images) == 2
    assert images[0]["positionNumber"] == "01"
    assert "58300000201899_aet_000_b_01.png" in images[0]["url"]

    assert len(bom) == 2
    assert bom[0]["productId"] == "11019860"
    assert bom[0]["positionNumber"] == "0101"
    assert bom[1]["productId"] == "12008387"


def test_generate_markdown_bom():
    sections_data = [
        {
            "section_num": "01",
            "diagram_file": "01_diagram.png",
            "parts": [
                {
                    "callout": "0101",
                    "part_number": "11019860",
                    "description": "Operating module programmed",
                    "price": "148.50",
                    "status": "Available",
                }
            ],
        }
    ]
    md = generate_markdown_bom("SHXM98W75N-01", sections_data)
    assert "# Bill of Materials — Bosch SHXM98W75N-01" in md
    assert "## Diagram Section 01" in md
    assert "11019860" in md
    assert "$148.50" in md
    assert "Operating module programmed" in md


def test_generate_csv_bom():
    sections_data = [
        {
            "section_num": "01",
            "diagram_file": "01_diagram.png",
            "parts": [
                {
                    "callout": "0101",
                    "part_number": "11019860",
                    "description": "Operating module programmed",
                    "price": "148.50",
                    "status": "Available",
                }
            ],
        }
    ]
    csv_str = generate_csv_bom(sections_data)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 2
    assert "Diagram Section,Callout,Part Number,Description,Price,Status,Diagram File" in lines[0]
    assert lines[1].startswith('01,0101,11019860,"Operating module programmed",148.50,Available,01_diagram.png')


SAMPLE_APP_PARTS_PROS_HTML = """
<div id="ctl00_cphMain_rParts_ctl01_dproductitem" class="product-item-list-hold">
    <div class="product-item">
        <div class="product-item-num">101</div>
        <div class="product-item-heading">
            <h3><a href="/bosch-operating-module-pro-11019860-ap6240911.html">Dishwasher Control Module</a></h3>
        </div>
        <strong class="price text-success">$154.58</strong>
    </div>
</div>
"""


def test_parse_appliancepartspros_section():
    from scripts.download_bosch_parts import parse_appliancepartspros_section
    parts = parse_appliancepartspros_section(SAMPLE_APP_PARTS_PROS_HTML)
    assert len(parts) == 1
    assert parts[0]["callout"] == "101"
    assert parts[0]["part_number"] == "11019860"
    assert parts[0]["description"] == "Dishwasher Control Module"
    assert parts[0]["price"] == "154.58"

