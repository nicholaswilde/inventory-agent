import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.import_amazon_invoice import (
    extract_invoice_data,
    extract_text_from_pdf,
    create_new_item_payload,
    import_amazon_invoice,
    download_invoice_if_url,
)

SAMPLE_AMAZON_INVOICE_TEXT = """
Order Summary
Order placed August 7, 2018  Order # 113-3740671-2345851
Ship to
Jane Doe
123 Test St
Springfield, IL 62701
United States
Payment method
Visa •••• 0000
View related transactions
Order Summary
Item(s) Subtotal: $562.61
Shipping & Handling: $0.00
Total before tax: $562.61
Estimated tax to be collected: $43.59
Grand Total: $606.20

Moen 169031 AC Adapter Service Kit for Moen Kitchen Faucets with MotionSense
Sold by: Amazon.com
Supplied by: Other
$95.76

Moen Arbor Motionsense Two-Sensor Touchless One-Handle High Arc Pulldown
Kitchen Faucet Featuring Reflex, Spot Resist Stainless (7594ESRS)
Sold by: Amazon.com
Supplied by: Other
$372.27
2

Moen 3942SRS Kitchen Soap and Lotion Dispenser, Spot Resist Stainless
Sold by: Amazon.com
Supplied by: Other
2  $47.29

Back to top
"""


def test_extract_invoice_data():
    data = extract_invoice_data(SAMPLE_AMAZON_INVOICE_TEXT)
    assert data["order_id"] == "113-3740671-2345851"
    assert data["order_date"] == "2018-08-07"
    assert data["subtotal"] == 562.61
    assert data["grand_total"] == 606.20

    items = data["items"]
    assert len(items) == 3

    # Item 1: Adapter
    assert items[0]["manufacturer"] == "Moen"
    assert items[0]["model_number"] == "169031"
    assert items[0]["price"] == 95.76
    assert items[0]["quantity"] == 1
    assert "AC Adapter Service Kit" in items[0]["title"]

    # Item 2: Faucet
    assert items[1]["manufacturer"] == "Moen"
    assert items[1]["model_number"] == "7594ESRS"
    assert items[1]["price"] == 372.27
    assert items[1]["quantity"] == 1
    assert "Arbor Motionsense" in items[1]["title"]

    # Item 3: Soap dispenser
    assert items[2]["manufacturer"] == "Moen"
    assert items[2]["model_number"] == "3942SRS"
    assert items[2]["price"] == 47.29
    assert items[2]["quantity"] == 2
    assert "Soap and Lotion Dispenser" in items[2]["title"]


def test_extract_text_from_pdf(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")

    # 1. Direct text extraction via lit --no-ocr succeeds
    def mock_lit_no_ocr(cmd, *args, **kwargs):
        if cmd[0] == "lit" and "--no-ocr" in cmd:
            return MagicMock(returncode=0, stdout="Invoice text direct")
        return MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_lit_no_ocr):
        assert extract_text_from_pdf(pdf) == "Invoice text direct"

    # 2. Direct text extraction is empty, falls back to lit built-in OCR
    def mock_lit_ocr(cmd, *args, **kwargs):
        if cmd[0] == "lit" and "--no-ocr" in cmd:
            return MagicMock(returncode=0, stdout="")
        if cmd[0] == "lit" and "--no-ocr" not in cmd:
            return MagicMock(returncode=0, stdout="Invoice text via built-in OCR")
        return MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_lit_ocr):
        assert extract_text_from_pdf(pdf) == "Invoice text via built-in OCR"

    # 3. lit fails, falls back to pdftotext
    def mock_pdftotext(cmd, *args, **kwargs):
        if cmd[0] == "lit":
            return MagicMock(returncode=1, stdout="")
        if cmd[0] == "pdftotext":
            return MagicMock(returncode=0, stdout="Invoice text via pdftotext")
        return MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", side_effect=mock_pdftotext):
        assert extract_text_from_pdf(pdf) == "Invoice text via pdftotext"


def test_create_new_item_payload():
    item_data = {
        "title": "Moen 3942SRS Kitchen Soap and Lotion Dispenser, Spot Resist Stainless",
        "model_number": "3942SRS",
        "manufacturer": "Moen",
        "price": 47.29,
        "quantity": 2,
    }

    payload = create_new_item_payload(
        item_data=item_data,
        order_id="113-3740671-2345851",
        order_date="2018-08-07",
    )

    assert payload["name"] == "Moen 3942SRS Kitchen Soap and Lotion Dispenser"
    assert payload["modelNumber"] == "3942SRS"
    assert payload["manufacturer"] == "Moen"
    assert payload["purchasePrice"] == 47.29
    assert payload["quantity"] == 2
    assert payload["purchaseDate"] == "2018-08-07"
    assert payload["purchaseFrom"] == "Amazon"
    order_fields = [f for f in payload["fields"] if f["name"] == "Order Number"]
    assert len(order_fields) == 1
    assert order_fields[0]["textValue"] == "113-3740671-2345851"


def test_download_invoice_if_url(tmp_path):
    # Local path returns directly
    local_file = tmp_path / "local_invoice.pdf"
    local_file.write_bytes(b"%PDF-1.4")
    assert download_invoice_if_url(str(local_file)) == local_file

    # Google Drive / HTTP URL downloads via requests
    url = "https://drive.google.com/file/d/16vcfO46EGt9O7GIrSbVOsbzgM8LDwPMd/view?usp=sharing"
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"%PDF-1.4 downloaded content"
        res_path = download_invoice_if_url(url, target_dir=tmp_path)
        assert res_path.exists()
        assert res_path.read_bytes() == b"%PDF-1.4 downloaded content"


def test_import_amazon_invoice_pipeline(tmp_path, capsys):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    processed_dir = tmp_path / "processed"

    upsert_responses = [
        {"id": "hb-adapter-123", "action": "updated"},
        {"id": "hb-faucet-456", "action": "updated", "attachmentErrors": ["upload timeout"]},
        {"id": "hb-new-item-789", "action": "created"},
    ]

    with patch("scripts.import_amazon_invoice.extract_text_from_pdf", return_value=SAMPLE_AMAZON_INVOICE_TEXT), \
         patch("scripts.import_amazon_invoice.hbctl_client.upsert_item", side_effect=upsert_responses) as mock_upsert:

        results = import_amazon_invoice(
            source=str(pdf),
            dry_run=False,
            attach=True,
            processed_dir=processed_dir,
        )

    assert results["order_id"] == "113-3740671-2345851"
    assert len(results["items"]) == 3
    assert results["items"][0]["action"] == "updated"
    assert results["items"][0]["entity_id"] == "hb-adapter-123"
    assert results["items"][2]["action"] == "created"
    assert results["items"][2]["entity_id"] == "hb-new-item-789"

    assert mock_upsert.call_count == 3
    expected_pdf = processed_dir / "Amazon_Invoice_113-3740671-2345851.pdf"
    first_kwargs = mock_upsert.call_args_list[0].kwargs
    assert first_kwargs["match_by"] == ["model", "name"]
    assert first_kwargs["match_mode"] == "contains"
    assert first_kwargs["fill_missing"] is True
    assert first_kwargs["attach"] == [expected_pdf]
    assert first_kwargs["attach_best_effort"] is True

    captured = capsys.readouterr()
    assert "upload timeout" in captured.err
