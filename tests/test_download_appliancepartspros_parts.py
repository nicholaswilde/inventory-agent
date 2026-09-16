import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.download_appliancepartspros_parts import (
    extract_model_from_url,
    parse_sections_from_index_html,
    parse_section_page,
    generate_markdown_bom,
    generate_csv_bom,
)

SAMPLE_INDEX_HTML = """
<section class="diagram-section part-diagrams bg-secondary" id="part-diagrams">
  <div class="diagram-parts-list">
    <div class="diagram-part-box bg-white border border-secondary radius">
      <a href="/control-panel-parts-for-panasonic-nn-sd997s.html">
        <div class="img-hold">
          <img src="https://t-esb6c0d2a5gwexgk.z03.azurefd.net/diagram/0031288113_6.gif" />
        </div>
        <div class="txt-hold">
          <strong class="title">Control Panel Parts</strong>
        </div>
      </a>
    </div>
    <div class="diagram-part-box bg-white border border-secondary radius">
      <a href="/door-assembly-parts-for-panasonic-nn-sd997s.html">
        <div class="img-hold">
          <img src="https://t-esb6c0d2a5gwexgk.z03.azurefd.net/diagram/0031288114_6.gif" />
        </div>
        <div class="txt-hold">
          <strong class="title">Door Assy Parts</strong>
        </div>
      </a>
    </div>
  </div>
</section>
"""

SAMPLE_SECTION_HTML = """
<img id="ctl00_cphMain_iDiagramFull2" src="https://t-esb6c0d2a5gwexgk.z03.azurefd.net/diagram/0031288113_8.gif" />
<script>
window.dataLayer = window.dataLayer || [];
function addtocart_g_7059014() {
window.dataLayer.push({
'event': 'add_to_cart',
 'ecommerce': {
 'currency': 'USD',
 'add': {
 'items': [
    {
        'item_id': 'AP7059014',
        'item_name': 'Cable',
        'price': 4.95
    }
 ]
 }
 }
});
}
</script>
<div class="product-item">
  <div class="product-item-num">E4</div>
  <div class="product-item-heading">
    <h3><a href="/panasonic-cable-f66167d00ap-ap7059014.html">Cable</a></h3>
  </div>
  <div class="ships-info-box">
    <div id="ctl00_cphMain_rParts_ctl00_ShipsInfoRow" class="ships-info-row" data-pid="7059014">
      <span class="in-stock">In Stock</span>
    </div>
  </div>
</div>
<div class="product-item">
  <div class="product-item-num">E1</div>
  <div class="product-item-heading">
    <h3><a href="/panasonic-pc-board-f603l8p00ap-ap7087591.html">Electronic Pc Board</a></h3>
  </div>
  <div class="ships-info-box">
    <div id="ctl00_cphMain_rParts_ctl01_ShipsInfoRow" class="ships-info-row na" data-pid="7087591">
      <span class="in-stock not-available">Out of Stock</span>
    </div>
  </div>
</div>
"""


def test_extract_model_from_url():
    url = "https://www.appliancepartspros.com/parts-for-panasonic-nn-sd997s.html?gad_source=1"
    assert extract_model_from_url(url) == "NN-SD997S"


def test_parse_sections_from_index_html():
    sections = parse_sections_from_index_html(SAMPLE_INDEX_HTML)
    assert len(sections) == 2
    assert sections[0]["name"] == "Control Panel Parts"
    assert sections[0]["url"] == "https://www.appliancepartspros.com/control-panel-parts-for-panasonic-nn-sd997s.html"
    assert "0031288113" in sections[0]["thumb_url"]


def test_parse_section_page():
    data = parse_section_page(SAMPLE_SECTION_HTML)
    assert data["diagram_url"] == "https://t-esb6c0d2a5gwexgk.z03.azurefd.net/diagram/0031288113_8.gif"
    assert len(data["parts"]) == 2

    p0 = data["parts"][0]
    assert p0["callout"] == "E4"
    assert p0["part_number"] == "F66167D00AP"
    assert p0["ap_id"] == "AP7059014"
    assert p0["title"] == "Cable"
    assert p0["price"] == "4.95"
    assert p0["status"] == "In Stock"

    p1 = data["parts"][1]
    assert p1["callout"] == "E1"
    assert p1["part_number"] == "F603L8P00AP"
    assert p1["price"] == "N/A"
    assert p1["status"] == "Not Available"


def test_generate_markdown_bom():
    sections_data = [
        {
            "name": "Control Panel Parts",
            "diagram_file": "01_Control_Panel_Parts.gif",
            "parts": [
                {
                    "callout": "E4",
                    "part_number": "F66167D00AP",
                    "ap_id": "AP7059014",
                    "title": "Cable",
                    "price": "4.95",
                    "status": "In Stock",
                }
            ],
        }
    ]
    md = generate_markdown_bom("NN-SD945S", sections_data)
    assert "# Bill of Materials — Panasonic NN-SD945S" in md
    assert "Control Panel Parts" in md
    assert "F66167D00AP" in md
    assert "$4.95" in md


def test_generate_csv_bom():
    sections_data = [
        {
            "name": "Control Panel Parts",
            "diagram_file": "01_Control_Panel_Parts.gif",
            "parts": [
                {
                    "callout": "E4",
                    "part_number": "F66167D00AP",
                    "ap_id": "AP7059014",
                    "title": "Cable",
                    "price": "4.95",
                    "status": "In Stock",
                }
            ],
        }
    ]
    csv_str = generate_csv_bom(sections_data)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 2
    assert "Section Name,Callout,Part Number,AP Part Number,Title,Price,Status,Diagram File" in lines[0]
    assert lines[1].startswith('"Control Panel Parts",E4,F66167D00AP,AP7059014,"Cable",4.95,In Stock,01_Control_Panel_Parts.gif')


def test_download_appliancepartspros_parts_orchestration(tmp_path):
    from unittest.mock import patch
    from scripts.download_appliancepartspros_parts import download_appliancepartspros_parts

    out_dir = tmp_path / "appliances" / "NN-SD945S"

    def mock_fetch(url):
        if "parts-for-panasonic" in url:
            return SAMPLE_INDEX_HTML.encode("utf-8")
        if "control-panel-parts" in url or "door-assembly" in url:
            return SAMPLE_SECTION_HTML.encode("utf-8")
        return b"fake-gif-bytes"

    with patch("scripts.download_appliancepartspros_parts.fetch_url", side_effect=mock_fetch), \
         patch("time.sleep", return_value=None):
        res = download_appliancepartspros_parts(
            "https://www.appliancepartspros.com/parts-for-panasonic-nn-sd997s.html",
            output_dir=out_dir,
            model_name="NN-SD945S",
        )
        assert res == out_dir
        assert (out_dir / "bill_of_materials.json").exists()
        assert (out_dir / "bill_of_materials.csv").exists()
        assert (out_dir / "bill_of_materials.md").exists()


def test_download_appliancepartspros_parts_main(tmp_path):
    from unittest.mock import patch
    from scripts.download_appliancepartspros_parts import main

    with patch("sys.argv", ["download_appliancepartspros_parts.py", "https://www.appliancepartspros.com/parts-for-panasonic-nn-sd997s.html", "-o", str(tmp_path), "--model", "NN-SD945S"]), \
         patch("scripts.download_appliancepartspros_parts.download_appliancepartspros_parts") as mock_dl:
        main()
        mock_dl.assert_called_once_with(
            "https://www.appliancepartspros.com/parts-for-panasonic-nn-sd997s.html",
            output_dir=str(tmp_path),
            model_name="NN-SD945S",
        )
