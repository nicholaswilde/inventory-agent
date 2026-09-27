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


def test_ingest_manual_generic_pdf_renaming_and_model_overrides(tmp_path):
    from scripts.ingest_manual import ingest_manual

    input_pdf = tmp_path / "manual.pdf"
    input_pdf.write_bytes(b"%PDF-1.4 fake")

    out_dir = tmp_path / "appliances"
    proc_dir = tmp_path / "processed"

    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_MICROWAVE_TEXT):
        res = ingest_manual(
            source=str(input_pdf),
            output_dir=out_dir,
            processed_dir=proc_dir,
            dry_run=True,
            model_override="NN-SD745S",
        )
        assert res["dry_run"] is True
        assert res["entity"]["capacity"] == "1.6 cu. ft."
        assert Path(res["entity"]["manual_path"]).name.endswith("_Manual.pdf")

    # Test WT7800 model override
    input_pdf2 = tmp_path / "washer.pdf"
    input_pdf2.write_bytes(b"%PDF-1.4 fake")
    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_WASHER_TEXT):
        res = ingest_manual(
            source=str(input_pdf2),
            output_dir=out_dir,
            processed_dir=proc_dir,
            dry_run=True,
            model_override="WT7800CW",
        )
        assert res["entity"]["capacity"] == "5.5 cu. ft. (Mega Capacity)"

    # Test 2603 model override
    input_pdf3 = tmp_path / "fridge.pdf"
    input_pdf3.write_bytes(b"%PDF-1.4 fake")
    with patch("scripts.ingest_manual.run_pdf_extraction", return_value=SAMPLE_REFRIGERATOR_TEXT):
        res = ingest_manual(
            source=str(input_pdf3),
            output_dir=out_dir,
            processed_dir=proc_dir,
            dry_run=True,
            model_override="LRDCS2603S",
        )
        assert res["entity"]["capacity"] == "25.5 cu. ft. (26 cu. ft. class)"


def test_ingest_manual_main_cli(capsys):
    from scripts.ingest_manual import main

    with patch("sys.argv", ["ingest_manual.py", "http://example.com/manual.pdf", "--dry-run"]), \
         patch("scripts.ingest_manual.ingest_manual", return_value={"entity": {"name": "Microwave"}, "homebox_id": "dry-run", "cheat_sheet": "appliances/microwave.md"}):
        main()
        out = capsys.readouterr().out
        assert "Successfully ingested Microwave" in out

    with patch("sys.argv", ["ingest_manual.py", "http://example.com/manual.pdf"]), \
         patch("scripts.ingest_manual.ingest_manual", side_effect=ValueError("invalid source")), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_download_or_copy_manual_url_and_missing(tmp_path):
    from scripts.ingest_manual import download_or_copy_manual
    proc_dir = tmp_path / "proc"

    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
    mock_resp.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_resp):
        out_file = download_or_copy_manual("https://example.com/docs/appliance_manual.pdf", proc_dir)
        assert out_file.name == "appliance_manual.pdf"
        assert out_file.read_bytes() == b"chunk1chunk2"

    with pytest.raises(FileNotFoundError):
        download_or_copy_manual(str(tmp_path / "does_not_exist.pdf"), proc_dir)


def test_run_pdf_extraction_lit_and_pdftotext(tmp_path):
    from scripts.ingest_manual import run_pdf_extraction
    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"dummy")

    # 1. lit --no-ocr direct text succeeds
    def mock_subp_lit_no_ocr(cmd, *args, **kwargs):
        if cmd[0] == "lit" and "--no-ocr" in cmd:
            return MagicMock(returncode=0, stdout="lit direct text")
        return MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_subp_lit_no_ocr):
        assert run_pdf_extraction(pdf) == "lit direct text"

    # 2. lit --no-ocr returns empty, falls back to lit built-in OCR
    def mock_subp_lit_ocr(cmd, *args, **kwargs):
        if cmd[0] == "lit" and "--no-ocr" in cmd:
            return MagicMock(returncode=0, stdout="")
        if cmd[0] == "lit" and "--no-ocr" not in cmd:
            return MagicMock(returncode=0, stdout="lit ocr fallback text")
        return MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_subp_lit_ocr):
        assert run_pdf_extraction(pdf) == "lit ocr fallback text"

    # 3. lit fails entirely, pdftotext succeeds
    def mock_subp_pdftotext(cmd, *args, **kwargs):
        if cmd[0] == "lit":
            return MagicMock(returncode=1, stdout="")
        if cmd[0] == "pdftotext":
            return MagicMock(returncode=0, stdout="pdftotext extracted text")
        return MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_subp_pdftotext):
        assert run_pdf_extraction(pdf) == "pdftotext extracted text"

    # 4. Both fail
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
        assert run_pdf_extraction(pdf) == ""


def test_compress_pdf_if_large_gs_error(tmp_path):
    from scripts.ingest_manual import compress_pdf_if_large
    large_pdf = tmp_path / "large.pdf"
    large_pdf.write_bytes(b"A" * 100)

    with patch("subprocess.run", side_effect=FileNotFoundError):
        res = compress_pdf_if_large(large_pdf, max_bytes=50)
        assert res == large_pdf


def test_extract_scotch_thermal_laminator():
    sample = """
User Manual of Product 1:
Scotch Thermal Laminator, 2 Roller System for a Professional Finish (TL901X)
Thermal Laminator TL901X USER MANUAL

SPECIFICATIONS
Laminating Speed   13.5 in/min
Nominal Weight Poids nominal 2.4 lb.
Number of Rollers  2
Entry Width        9.5 in.
Power Requirements 120 VAC / 60Hz / 300W / 2.5A
Maximum Thickness  0.015 in.
Ready Time         3-4 min
34-8724-4757-7
"""
    data = extract_appliance_data(sample)
    assert data["manufacturer"] == "Scotch"
    assert data["appliance_type"] == "Thermal Laminator"
    assert "TL901X" in data["model_number"]
    assert "Scotch Thermal Laminator" in data["name"]
    assert "9.5" in data["capacity"] or "9.5" in data["dimensions"]
    assert data["weight"] == "2.4 lb."
    assert data["manual_number"] == "34-8724-4757-7"


def test_resolve_issue_source_success():
    from scripts.ingest_manual import resolve_issue_source
    mock_issue = {
        "number": 6,
        "title": "[appliance] Weber SmokeFire",
        "body": "![Smokefire-EX4-EX6-Owners-Guide.pdf](https://github.com/user-attachments/files/32426804/Smokefire-EX4-EX6-Owners-Guide.pdf)\n\n",
        "comments": [],
    }
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=json.dumps(mock_issue))):
        pdf_url, title, issue_num = resolve_issue_source("#6")
        assert pdf_url == "https://github.com/user-attachments/files/32426804/Smokefire-EX4-EX6-Owners-Guide.pdf"
        assert title == "Weber SmokeFire"
        assert issue_num == 6


def test_resolve_issue_source_no_pdf():
    from scripts.ingest_manual import resolve_issue_source
    mock_issue = {
        "number": 7,
        "title": "[appliance] Scotch thermal laminator",
        "body": "",
        "comments": [],
    }
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=json.dumps(mock_issue))):
        with pytest.raises(ValueError, match="No PDF manual URL found in GitHub issue #7"):
            resolve_issue_source("7")


def test_resolve_issue_source_invalid_ref():
    from scripts.ingest_manual import resolve_issue_source
    with pytest.raises(ValueError, match="Invalid GitHub issue reference"):
        resolve_issue_source("no-numbers-here")


def test_resolve_issue_source_gh_error():
    from scripts.ingest_manual import resolve_issue_source
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="Not found")):
        with pytest.raises(RuntimeError, match="Failed to fetch issue #99"):
            resolve_issue_source(99)


def test_ingest_manual_from_issue_ref(tmp_path):
    mock_issue = {
        "number": 6,
        "title": "[appliance] Weber SmokeFire",
        "body": "![Smokefire.pdf](https://example.com/Smokefire.pdf)",
        "comments": [],
    }
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=json.dumps(mock_issue))), \
         patch("scripts.ingest_manual.download_or_copy_manual") as mock_dl, \
         patch("scripts.ingest_manual.run_pdf_extraction", return_value="WEBER SMOKEFIRE GRILL"), \
         patch("scripts.ingest_manual.extract_appliance_data", return_value={"name": "Weber SmokeFire", "model_number": "EX4", "error_codes": [], "accessories": []}):

        mock_pdf = tmp_path / "Smokefire_Manual.pdf"
        mock_pdf.write_bytes(b"%PDF dummy")
        mock_dl.return_value = mock_pdf

        res = ingest_manual(
            source="#6",
            output_dir=tmp_path / "appliances",
            processed_dir=tmp_path / "processed",
            dry_run=True,
        )
        assert res["entity"]["name"] == "Weber SmokeFire"
        assert Path(res["cheat_sheet"]).exists()


def test_extract_weber_smokefire():
    sample = """
Weber SmokeFire
EX4
Wood Pellet Barbecue EX6
OWNER’S MANUAL
53524

Large Hopper
The large capacity hopper holds an entire 9kg (20 pound) bag of pellets.

Error Code  Cause                     Solution
E1        Auger Jam              Auger jam has been detected.
E2        Fan Error              Fan error detected.
E3        Barbecue Flame is Out  Flame out procedure.
E4        Communication Failure  Communication error.
E5        Barbecue is too Hot    Over temperature.
E6        Start Up Failure       Glow plug issue.
E7        Motor Failure          Drive motor failure.
E8        Thermocouple Error     Temperature probe.
E9        Low Fuel Detection     Low fuel error.
"""
    data = extract_appliance_data(sample)
    assert data["manufacturer"] == "Weber"
    assert "Grill" in data["appliance_type"] or "Barbecue" in data["appliance_type"]
    assert "EX4" in data["model_number"] and "EX6" in data["model_number"]
    assert "20" in data["capacity"] or "9kg" in data["capacity"]
    assert any("E1" in err["code"] for err in data["error_codes"])
    assert any("E6" in err["code"] for err in data["error_codes"])
    assert data["manual_number"] == "53524"


def test_extract_roborock():
    sample = """
Roborock Q7 Max+
Robotic Vacuum Cleaner User Manual
Read this user manual with diagrams carefully before using
this product and store it properly for future reference.

Errors
Error 1: LiDAR turret or laser blocked. Check for obstruction and retry.
Error 2: Bumper stuck. Clean it and lightly tap to release it.
Error 3: Wheels suspended. Move robot and restart.
Error 5: Main brush jammed. Clean main brush and bearings.
Error 18: Fan error. Reset robot.
"""
    data = extract_appliance_data(sample)
    assert data["manufacturer"] == "Roborock"
    assert "Vacuum" in data["appliance_type"]
    assert "Q7 Max+" in data["model_number"]
    assert any("Error 1" in err["code"] or "1" in err["code"] for err in data["error_codes"])
    assert any("Error 5" in err["code"] or "5" in err["code"] for err in data["error_codes"])


def test_extract_dyson_v10():
    sample = """
User manual
The D y son cordles s vacuum drops into the wall-mounte d charging dock.
Motorbar™ cleaner head
Fluffy™ cleaner head brush bar
Hair screw tool
S V12 J N.0 0 0 0 0 P N.0 0 0 0 0 0 - 0 0 - 0 0
B at ter y LEDs
B at ter y fault. One flashing re d LED.
Charger fault. One light flashing alter-
Clearing blockages
Washing filter
"""
    data = extract_appliance_data(sample)
    assert data["manufacturer"] == "Dyson"
    assert "Vacuum" in data["appliance_type"]
    assert "SV12" in data["model_number"]
    assert any("Battery Fault" in err["code"] or "Battery" in err["code"] for err in data["error_codes"])


def test_extract_broan_pm390():
    sample = """
BROAN PM390
Owner's Manual
PM390 SERIES
POWER MODULE
Range Hood
Grease Filter
Non-Ducted Filter Kit B08999040
Blower Assembly B06002125
Light Switch B03295081
40 Watt Max Candelabra Bulbs
"""
    data = extract_appliance_data(sample)
    assert data["manufacturer"] == "Broan"
    assert "Range Hood" in data["appliance_type"]
    assert "PM390" in data["model_number"]
    assert any("B08999040" in acc or "Grease Filter" in acc for acc in data["accessories"])
    assert any("Candelabra" in acc or "Blower" in acc for acc in data["accessories"])


def test_extract_schlage_encode_plus():
    sample = """
Schlage deadbolt
Start here! Visit alle.co/encodeplus
Touchscreen
Communication Icon
Low Battery Icon
Lock Button and “X” Icon
Apple HomeKit
47360452 Rev. 07/21-b
BE499WB
"""
    data = extract_appliance_data(sample)
    assert data["manufacturer"] == "Schlage"
    assert "Deadbolt" in data["appliance_type"] or "Lock" in data["appliance_type"]
    assert "BE499WB" in data["model_number"]
    assert "47360452" in data["manual_number"]
    assert any("Low Battery" in err["code"] or "Battery" in err["code"] for err in data["error_codes"])
    assert any("AA" in acc or "Battery" in acc or "Key" in acc for acc in data["accessories"])


def test_create_homebox_entity_matches_partial_model(tmp_path):
    from scripts.ingest_manual import create_homebox_entity

    dummy_pdf = tmp_path / "manual.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 test")

    data = {
        "name": "Schlage Smart Deadbolt Lock",
        "model_number": "BE499WB",
        "manufacturer": "Schlage",
    }

    mock_entities = [
        {
            "id": "eeac5cf2-dadd-4ce5-b94c-137c9a01fd8d",
            "name": "Schlage Encode Plus Smart WiFi Deadbolt Lock, Tap to Unlock, Aged Bronze",
            "modelNumber": "BE499WB CAM 716",
        }
    ]

    with patch("scripts.ingest_manual.get_homebox_config", return_value=("127.0.0.1", "test-key")), \
         patch("requests.get") as mock_get, \
         patch("requests.post") as mock_post:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_entities
        mock_post.return_value.status_code = 200

        entity_id = create_homebox_entity(data, dummy_pdf)
        assert entity_id == "eeac5cf2-dadd-4ce5-b94c-137c9a01fd8d"
        # Should not create new entity
        assert not any(call[0][0].endswith("/entities") and "json" in call[1] for call in mock_post.call_args_list)
