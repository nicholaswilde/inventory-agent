import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.download_repairclinic_parts import (
    extract_model_id_from_target,
    parse_diagram_details,
    generate_markdown_bom,
    generate_csv_bom,
)

SAMPLE_DIAGRAM_JSON = {
    "diagram_id": 1129403,
    "name": "EXPLODED VIEW OF TOP COVER ASSEMBLY",
    "image_url": "https://bapgpartsprod.blob.core.windows.net/diagrams/20153051211818_10000_EV_page_1__md_1000x.jpg",
    "large_image_url": "https://bapgpartsprod.blob.core.windows.net/diagrams/20153051211818_10000_EV_page_1__lg_1500x.jpg",
    "thumbnail_url": "https://bapgpartsprod.blob.core.windows.net/diagrams/20153051211818_10000_EV_page_1__thumb_315x.jpg",
    "parts": [
        {
            "part_id": 4951629,
            "price": 180.84,
            "image_url": "/static/images/icons/defaultShopPart.svg",
            "oem_number": "ABJ75767801",
            "is_nla": False,
            "skill_level": None,
            "description": "Cabinet assembly",
            "in_stock": True,
            "title": "Housing Panel",
            "order_tag": "F000",
            "original_oem_number": None,
            "bapg_part_number": "LG-ABJ75767801",
        }
    ],
    "models": [],
}


def test_extract_model_id_from_target():
    assert extract_model_id_from_target("https://www.repairclinic.com/ProductDetail/2453006?tab=diagrams") == "2453006"
    assert extract_model_id_from_target("https://www.repairclinic.com/ProductDetail/2453006") == "2453006"
    assert extract_model_id_from_target("2453006") == "2453006"


def test_parse_diagram_details():
    parsed = parse_diagram_details(SAMPLE_DIAGRAM_JSON)
    assert parsed["diagram_id"] == 1129403
    assert parsed["name"] == "EXPLODED VIEW OF TOP COVER ASSEMBLY"
    assert "large_image_url" in parsed
    assert len(parsed["parts"]) == 1
    part = parsed["parts"][0]
    assert part["callout"] == "F000"
    assert part["part_number"] == "ABJ75767801"
    assert part["title"] == "Housing Panel"
    assert part["description"] == "Cabinet assembly"
    assert part["price"] == "180.84"
    assert part["status"] == "In Stock"


def test_generate_markdown_bom():
    diagrams_data = [
        {
            "diagram_id": 1129403,
            "name": "EXPLODED VIEW OF TOP COVER ASSEMBLY",
            "diagram_file": "01_EXPLODED_VIEW_OF_TOP_COVER_ASSEMBLY.jpg",
            "parts": [
                {
                    "callout": "F000",
                    "part_number": "ABJ75767801",
                    "title": "Housing Panel",
                    "description": "Cabinet assembly",
                    "price": "180.84",
                    "status": "In Stock",
                }
            ],
        }
    ]
    md = generate_markdown_bom("WT7800CW/00", diagrams_data)
    assert "# Bill of Materials — LG WT7800CW/00" in md
    assert "EXPLODED VIEW OF TOP COVER ASSEMBLY" in md
    assert "ABJ75767801" in md
    assert "$180.84" in md


def test_generate_csv_bom():
    diagrams_data = [
        {
            "diagram_id": 1129403,
            "name": "EXPLODED VIEW OF TOP COVER ASSEMBLY",
            "diagram_file": "01_EXPLODED_VIEW_OF_TOP_COVER_ASSEMBLY.jpg",
            "parts": [
                {
                    "callout": "F000",
                    "part_number": "ABJ75767801",
                    "title": "Housing Panel",
                    "description": "Cabinet assembly",
                    "price": "180.84",
                    "status": "In Stock",
                }
            ],
        }
    ]
    csv_str = generate_csv_bom(diagrams_data)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 2
    assert "Diagram ID,Diagram Name,Callout,Part Number,Title,Description,Price,Status,Diagram File" in lines[0]
    assert lines[1].startswith('1129403,"EXPLODED VIEW OF TOP COVER ASSEMBLY",F000,ABJ75767801,"Housing Panel","Cabinet assembly",180.84,In Stock,01_EXPLODED_VIEW_OF_TOP_COVER_ASSEMBLY.jpg')


def test_download_repairclinic_parts_orchestration(tmp_path):
    from unittest.mock import patch
    from scripts.download_repairclinic_parts import download_repairclinic_parts

    out_dir = tmp_path / "appliances" / "WT7800CW"

    def mock_api(endpoint):
        if "/model/" in endpoint and "diagrams" not in endpoint:
            return {"name": "WT7800CW/00"}
        if "/diagrams?" in endpoint:
            return {"diagrams": [{"diagram_id": 1129403, "large_image_url": "http://example.com/page_1.jpg"}]}
        if "/diagrams/1129403" in endpoint:
            return SAMPLE_DIAGRAM_JSON
        return {}

    with patch("scripts.download_repairclinic_parts.fetch_api_json", side_effect=mock_api), \
         patch("scripts.download_repairclinic_parts.fetch_url", return_value=b"fake-image"), \
         patch("time.sleep", return_value=None):
        res = download_repairclinic_parts("2453006", output_dir=out_dir)
        assert res == out_dir
        assert (out_dir / "bill_of_materials.json").exists()
        assert (out_dir / "bill_of_materials.csv").exists()
        assert (out_dir / "bill_of_materials.md").exists()
        assert (out_dir / "diagrams" / "01_EXPLODED_VIEW_OF_TOP_COVER_ASSEMBLY.jpg").exists()


def test_download_repairclinic_parts_main(tmp_path):
    from unittest.mock import patch
    from scripts.download_repairclinic_parts import main

    with patch("sys.argv", ["download_repairclinic_parts.py", "2453006", "-o", str(tmp_path)]), \
         patch("scripts.download_repairclinic_parts.download_repairclinic_parts") as mock_dl:
        main()
        mock_dl.assert_called_once_with("2453006", model_name=None, output_dir=str(tmp_path))
