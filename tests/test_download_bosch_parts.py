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


def test_fetch_appliancepartspros_catalog():
    from scripts.download_bosch_parts import fetch_appliancepartspros_catalog

    index_html = '<a href="/test-parts-for-bosch-shxm98w75n-01.html">Section</a>'
    section_html = SAMPLE_APP_PARTS_PROS_HTML

    def mock_fetch(url):
        if "parts-for-bosch" in url and "test-" not in url:
            return index_html.encode("utf-8")
        return section_html.encode("utf-8")

    with patch("scripts.download_bosch_parts.fetch_url", side_effect=mock_fetch):
        cat = fetch_appliancepartspros_catalog("SHXM98W75N-01")
        assert "11019860" in cat
        assert cat["11019860"]["description"] == "Dishwasher Control Module"


def test_fetch_appliancepartspros_catalog_error():
    from scripts.download_bosch_parts import fetch_appliancepartspros_catalog

    with patch("scripts.download_bosch_parts.fetch_url", side_effect=Exception("network down")):
        cat = fetch_appliancepartspros_catalog("SHXM98W75N-01")
        assert cat == {}


def test_download_bosch_parts_orchestration(tmp_path):
    from scripts.download_bosch_parts import download_bosch_parts

    out_dir = tmp_path / "appliances" / "SHXM98W75N-01"

    def mock_fetch(url):
        if "media3.bsh-group.com" in url:
            return b"fake-png-bytes"
        if "appliancepartspros.com" in url:
            return b""
        return SAMPLE_BOSCH_HTML.encode("utf-8")

    with patch("scripts.download_bosch_parts.fetch_url", side_effect=mock_fetch), \
         patch("scripts.download_bosch_parts.fetch_appliancepartspros_catalog", return_value={"11019860": {"description": "Module", "price": "100.00", "status": "Available", "url": "http://example.com"}}):
        res = download_bosch_parts("SHXM98W75N/01", output_dir=out_dir)
        assert res["variant_id"] == "SHXM98W75N/01"
        assert (out_dir / "bill_of_materials.json").exists()
        assert (out_dir / "bill_of_materials.csv").exists()
        assert (out_dir / "bill_of_materials.md").exists()
        assert (out_dir / "diagrams" / "01_diagram.png").exists()


def test_download_bosch_parts_main(tmp_path):
    from scripts.download_bosch_parts import main

    with patch("sys.argv", ["download_bosch_parts.py", "SHXM98W75N-01", "--output-dir", str(tmp_path)]), \
         patch("scripts.download_bosch_parts.download_bosch_parts") as mock_dl:
        main()
        mock_dl.assert_called_once_with(variant_id="SHXM98W75N-01", output_dir=str(tmp_path))

    with patch("sys.argv", ["download_bosch_parts.py", "https://www.bosch-home.com/us/en/spare-parts-list/SHXM98W75N-01"]), \
         patch("scripts.download_bosch_parts.download_bosch_parts") as mock_dl:
        main()
        assert mock_dl.call_args[1]["variant_id"] == "SHXM98W75N-01"

    with patch("sys.argv", ["download_bosch_parts.py", "fail"]), \
         patch("scripts.download_bosch_parts.download_bosch_parts", side_effect=ValueError("bad variant")), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

