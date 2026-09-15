import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.ingest_manual import (
    compress_pdf_if_large,
    download_or_copy_manual,
    extract_appliance_data,
    format_cheat_sheet,
    ingest_manual,
    resolve_download_url,
)

SAMPLE_MANUAL_TEXT = """
OWNER'S MANUAL
DRYER
ENGLISH
DL*X780**E / DL*X788**E / DE*X790**E
MFL70442689 www.lg.com
Copyright © 2024 LG Electronics Inc.

SPECIFICATIONS
Model: DL*X780**E / DL*X788**E / DE*X790**E
Dimensions (Width X Depth X Height): 27'' X 29 1/2'' X 44 1/2''
Capacity: 7.3 cu.ft.
Net Weight: Gas : 129.8 lb / Electric : 124.8 lb

Accessories:
a Drying Rack (No. 3750EL001C)
b Side vent kit (Kit No. 383EEL9001B)

TROUBLESHOOTING
Error Messages
tE1 through tE7: Temperature sensor failure. Turn off and call service.
PS: Power cord is connected incorrectly.
d80, d90, d95: Exhaust system is too long or has too many turns/restrictions.
bIGf: More Time button was pressed for big item.
"""


def test_resolve_download_url():
    gdrive_sharing = "https://drive.google.com/file/d/1aH0KA3Ohw2L1Tu2YpIxv8KTJpDz02sFV/view?usp=sharing"
    direct = resolve_download_url(gdrive_sharing)
    assert "id=1aH0KA3Ohw2L1Tu2YpIxv8KTJpDz02sFV" in direct
    assert "export=download" in direct

    normal_url = "https://example.com/manual.pdf"
    assert resolve_download_url(normal_url) == normal_url


def test_extract_appliance_data():
    data = extract_appliance_data(SAMPLE_MANUAL_TEXT)
    assert data["manufacturer"].upper() == "LG"
    assert "DRYER" in data["appliance_type"].upper()
    assert "DL*X780**E" in data["model_number"]
    assert data["manual_number"] == "MFL70442689"
    assert "7.3" in data["capacity"]
    assert "27''" in data["dimensions"]
    assert len(data["error_codes"]) >= 3
    assert any("d80" in err["code"] for err in data["error_codes"])
    assert any("3750EL001C" in acc for acc in data["accessories"])


def test_format_cheat_sheet():
    data = {
        "manufacturer": "LG",
        "appliance_type": "Dryer",
        "name": "LG Dryer",
        "model_number": "DL*X780**E",
        "manual_number": "MFL70442689",
        "capacity": "7.3 cu. ft.",
        "dimensions": "27\" W x 29.5\" D x 44.5\" H",
        "accessories": ["Drying Rack (No. 3750EL001C)"],
        "error_codes": [
            {"code": "tE1", "meaning": "Temp sensor failure", "action": "Call service"},
            {"code": "d80", "meaning": "Vent blocked 80%", "action": "Clean duct"},
        ],
        "homebox_id": "mock-12345",
        "manual_path": "images/processed/test.pdf",
    }
    markdown = format_cheat_sheet(data)
    assert "# LG Dryer" in markdown
    assert "mock-12345" in markdown
    assert "3750EL001C" in markdown
    assert "d80" in markdown


def test_download_or_copy_manual_local(tmp_path):
    src_file = tmp_path / "sample.pdf"
    src_file.write_bytes(b"%PDF-1.6 dummy")
    dest_dir = tmp_path / "processed"

    dest_file = download_or_copy_manual(str(src_file), dest_dir=dest_dir)
    assert dest_file.exists()
    assert dest_file.read_bytes() == b"%PDF-1.6 dummy"
    assert dest_file.parent == dest_dir


def test_ingest_manual_dry_run(tmp_path):
    pdf_path = tmp_path / "test_manual.pdf"
    pdf_path.write_bytes(b"%PDF-1.6 dummy")

    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_MANUAL_TEXT):
        result = ingest_manual(
            source=str(pdf_path),
            output_dir=tmp_path / "appliances",
            processed_dir=tmp_path / "processed",
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["entity"]["manufacturer"] == "LG"
    cheat_sheet = tmp_path / "appliances" / "lg-dryer.md"
    assert cheat_sheet.exists()
    assert "d80" in cheat_sheet.read_text()


def test_ingest_manual_model_override(tmp_path):
    pdf_path = tmp_path / "test_manual.pdf"
    pdf_path.write_bytes(b"%PDF-1.6 dummy")

    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_MANUAL_TEXT):
        result = ingest_manual(
            source=str(pdf_path),
            output_dir=tmp_path / "appliances",
            processed_dir=tmp_path / "processed",
            dry_run=True,
            model_override="JT5500SF5SS",
            name_override="GE Double Wall Oven",
        )

    assert result["entity"]["model_number"] == "JT5500SF5SS"
    assert result["entity"]["name"] == "GE Double Wall Oven"
    cheat_sheet = tmp_path / "appliances" / "ge-double-wall-oven.md"
    assert cheat_sheet.exists()
    assert "JT5500SF5SS" in cheat_sheet.read_text()

    # Test washer model override
    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_WASHER_TEXT):
        res_washer = ingest_manual(
            source=str(pdf_path),
            output_dir=tmp_path / "appliances",
            processed_dir=tmp_path / "processed",
            dry_run=True,
            model_override="WT7800CW",
        )
    assert res_washer["entity"]["model_number"] == "WT7800CW"
    assert "5.5 cu. ft." in res_washer["entity"]["capacity"]
    assert "132.3 lb" in res_washer["entity"]["weight"]


def test_ingest_manual_homebox_integration(tmp_path):
    pdf_path = tmp_path / "test_manual.pdf"
    pdf_path.write_bytes(b"%PDF-1.6 dummy")

    mock_resp_create = MagicMock()
    mock_resp_create.json.return_value = {"id": "hb-entity-999", "name": "LG Dryer"}
    mock_resp_create.raise_for_status.return_value = None

    mock_resp_update = MagicMock()
    mock_resp_update.raise_for_status.return_value = None

    mock_resp_attach = MagicMock()
    mock_resp_attach.json.return_value = {"id": "attach-111"}
    mock_resp_attach.raise_for_status.return_value = None

    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_MANUAL_TEXT), \
         patch("requests.post", side_effect=[mock_resp_create, mock_resp_attach]) as mock_post, \
         patch("requests.put", return_value=mock_resp_update) as mock_put, \
         patch.dict(os.environ, {"HOMEBOX_IP": "127.0.0.1", "HOMEBOX_API_KEY": "fake-key"}):
        
        result = ingest_manual(
            source=str(pdf_path),
            output_dir=tmp_path / "appliances",
            processed_dir=tmp_path / "processed",
            dry_run=False,
        )

    assert result["homebox_id"] == "hb-entity-999"
    assert mock_post.call_count == 2
    assert mock_put.call_count == 1
    # Verify first call was create entity
    assert "/api/v1/entities" in mock_post.call_args_list[0][0][0]
    # Verify second call was attach
    assert "/attachments" in mock_post.call_args_list[1][0][0]


SAMPLE_REFRIGERATOR_TEXT = """
OWNER'S MANUAL
REFRIGERATOR
LRDCS2603*
MFL67851408 www.lg.com

Product Specifications
*The appearance and specifications listed in this manual may vary due to constant product improvements.
Electrical requirements: 115 V, 60 Hz
Min. / Max. water pressure: 20 - 120 psi (138 - 827 kPa)
                  Model LRDCS2603*
Description   Standard-depth, bottom freezer
Net weight    226 lb (102.5 kg)

Dimensions and Clearances
- Dimension/Clearance model
A Depth without Handle 34” (864 mm)
B Width 32 4/5” (833 mm)
C Height to Top of Case 68 1/2” (1740 mm)
D Height to Top of Hinge 69 4/5” (1774 mm)
G Depth with Handle 35” (889 mm)

Water Filter
Use replacement cartridge: LT1000P, LT1000PC or LT1000PCS
Model: LT1000P, LT1000PC, LT1000PCS
NSF System Trade Name Code: MDJ64844601

Display Mode (For Store Use Only)
When activated, OFF is displayed on the control panel.

TROUBLESHOOTING
1-800-243-0000 U.S.A.
1-888-542-2623 CANADA
800-980-2973. You must include in the opt out e-mail or provide by telephone: (a) your name and address;
2,4-D 210.0 ug/L
"""


def test_extract_refrigerator_data():
    data = extract_appliance_data(SAMPLE_REFRIGERATOR_TEXT)
    assert data["manufacturer"] == "LG"
    assert "Refrigerator" in data["appliance_type"]
    assert "226 lb" in data["weight"]
    assert "32 4/5" in data["dimensions"] or "833 mm" in data["dimensions"]
    assert "69 4/5" in data["dimensions"] or "1774 mm" in data["dimensions"]
    assert any("LT1000P" in acc for acc in data["accessories"])
    assert not any("800-" in err["code"] for err in data["error_codes"])
    assert not any("2,4" in err["code"] for err in data["error_codes"])
    assert any("OFF" in err["code"] for err in data["error_codes"])


SAMPLE_WASHER_TEXT = """
OWNER'S MANUAL
WASHING MACHINE
WT7800C* / WT7880H*A / WT7900H*A
MFL68267065 www.lg.com

Product Specifications
Model    WT7800C* / WT7880H*A / WT7900H*A
Electrical Requirements  120 V~, 60 Hz
Dimensions (Width X Depth X Height) 27" X 28 3/8" X 44 1/2" (68.6 cm X 72.1 cm X 113 cm)
Maximum Depth with Lid Open  57 1/4” (145.3 cm)
Net Weight  132.3 lb (60 kg)
Maximum Spin Speed  950 RPM

Error Messages
UE  UNBALANCE ERROR
IE  INLET ERROR
OE  WATER OUTLET ERROR
dE  LID ERROR
tcL TUB CLEAN ALARM
"""


def test_extract_washer_data():
    data = extract_appliance_data(SAMPLE_WASHER_TEXT)
    assert data["manufacturer"] == "LG"
    assert "Washer" in data["appliance_type"] or "Washing Machine" in data["appliance_type"]
    assert "27\"" in data["dimensions"] or "68.6" in data["dimensions"]
    assert "132.3 lb" in data["weight"]
    assert "5.5 cu. ft." in data["capacity"]
    assert any("UE" in err["code"] for err in data["error_codes"])
    assert any("IE" in err["code"] for err in data["error_codes"])
    assert any("OE" in err["code"] for err in data["error_codes"])
    assert not any("LOCKED" in err["code"] for err in data["error_codes"])


def test_compress_pdf_if_large(tmp_path):
    small_file = tmp_path / "small.pdf"
    small_file.write_bytes(b"%PDF-1.4 dummy content")
    result = compress_pdf_if_large(small_file, max_bytes=1000)
    assert result == small_file

    # Mock large file
    large_file = tmp_path / "large.pdf"
    large_file.write_bytes(b"%PDF-1.4 large content " * 100)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        compressed_target = tmp_path / "large_compressed.pdf"
        compressed_target.write_bytes(b"%PDF-1.4 compressed")
        res_large = compress_pdf_if_large(large_file, max_bytes=10)
        assert res_large == compressed_target


SAMPLE_MICROWAVE_TEXT = """
Operating Instructions
Microwave Oven
Household Use Only
Model No. NN-SD945S / NN-SD975S / NN-SD745S
Panasonic

Specifications
Power Source: 120 V, 60 Hz
Cooking Power: 1,250 W
Outside Dimensions (W x H x D): 23 7⁄8” x 14” x 19 15⁄16”
Net Weight: Approx. 36.8 lbs (16.7 kg)

Trim Kit Information
27" Trim Kit: NN-TK922S
30" Trim Kit: NN-TK932S

Troubleshooting
The word “LOCK” appears in the display: The CHILD SAFETY LOCK was activated.
The oven stops cooking and “H00“, “H97” or “H98” appears: The oven's power supply has failed.
“DEMO MODE PRESS ANY KEY” or “D” appears in the display: Demo mode was selected On.
"""


def test_extract_microwave_data():
    data = extract_appliance_data(SAMPLE_MICROWAVE_TEXT)
    assert data["manufacturer"] == "Panasonic"
    assert "Microwave" in data["appliance_type"]
    assert "23 7⁄8" in data["dimensions"] or "14”" in data["dimensions"] or "14\"" in data["dimensions"]
    assert "36.8 lbs" in data["weight"] or "16.7 kg" in data["weight"]
    assert any("LOCK" in err["code"] for err in data["error_codes"])
    assert any("H97" in err["code"] or "H00" in err["code"] for err in data["error_codes"])
    assert any("DEMO" in err["code"] for err in data["error_codes"])
    assert not any("OFF (Display / Demo Mode)" in err["code"] for err in data["error_codes"])
    assert any("NN-TK922S" in acc for acc in data["accessories"])




