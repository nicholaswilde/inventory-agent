import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.batch_import import (
    parse_items_list,
    parse_amazon_orders_csv,
    filter_csv_candidates,
    batch_import,
)

SAMPLE_CSV = """\ufeffASIN,Product Name,Department,Order Date,Order ID,Original Quantity,Unit Price,Order Status
B086383HC7,"Lenovo Chromebook Flex 5 13\" Laptop",Personal Computers,2020-12-08T02:25:09Z,111-1234567-1111111,1,433.70,Closed
B087D5T3QT,"Intel NUC Mini PC",Personal Computers,2021-06-14T05:37:42Z,111-2222222-2222222,1,607.00,Closed
B087D5T3QT,"Intel NUC Mini PC",Personal Computers,2021-08-12T19:33:11Z,111-3333333-3333333,1,607.00,Closed
B000000000,"Organic Green Tea 100 Bags",Grocery,2022-01-01T00:00:00Z,111-4444444-4444444,1,12.99,Closed
B099999999,"Cancelled Item",Electronics,2023-01-01T00:00:00Z,111-5555555-5555555,1,99.99,Cancelled
"""


def test_parse_items_list(tmp_path):
    file_content = """
    # Comments should be ignored
    B086383HC7
    https://www.amazon.com/dp/B08G8WMRRP

    B0916F5DTM
    """
    item_file = tmp_path / "items.txt"
    item_file.write_text(file_content)

    items = parse_items_list(
        direct_items=["B0CGJGZZ1L", "https://example.com/gadget"],
        file_path=str(item_file)
    )
    assert items == [
        "B0CGJGZZ1L",
        "https://example.com/gadget",
        "B086383HC7",
        "https://www.amazon.com/dp/B08G8WMRRP",
        "B0916F5DTM"
    ]


def test_parse_amazon_orders_csv(tmp_path):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(SAMPLE_CSV)

    orders = parse_amazon_orders_csv(str(csv_file))
    assert "B086383HC7" in orders
    assert orders["B086383HC7"]["count"] == 1
    assert orders["B086383HC7"]["unit_price"] == 433.70
    assert orders["B086383HC7"]["latest_date"] == "2020-12-08"

    assert "B087D5T3QT" in orders
    assert orders["B087D5T3QT"]["count"] == 2
    assert orders["B087D5T3QT"]["unit_price"] == 607.00
    assert orders["B087D5T3QT"]["latest_date"] == "2021-08-12"
    assert len(orders["B087D5T3QT"]["orders"]) == 2

    # Cancelled order should be excluded
    assert "B099999999" not in orders


def test_filter_csv_candidates(tmp_path):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(SAMPLE_CSV)

    orders = parse_amazon_orders_csv(str(csv_file))
    candidates = filter_csv_candidates(orders, min_price=50.0)

    asins = [c["asin"] for c in candidates]
    assert "B086383HC7" in asins
    assert "B087D5T3QT" in asins
    # Tea should be excluded by keyword/dept filter
    assert "B000000000" not in asins


def test_batch_import_dry_run(tmp_path):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(SAMPLE_CSV)

    results = batch_import(
        items=["B086383HC7", "B087D5T3QT"],
        csv_path=str(csv_file),
        dry_run=True,
    )
    assert len(results) == 2
    assert results[0]["asin"] == "B086383HC7"
    assert results[0]["dry_run"] is True
    assert results[0]["quantity"] == 1
    assert results[0]["purchase_price"] == 433.70

    assert results[1]["asin"] == "B087D5T3QT"
    assert results[1]["dry_run"] is True
    assert results[1]["quantity"] == 2
    assert results[1]["purchase_price"] == 607.00


@patch("scripts.batch_import.fetch_url_html")
@patch("scripts.batch_import.create_homebox_entity")
@patch("scripts.batch_import.hbctl_client.list_items", return_value=[])
@patch("scripts.batch_import.hbctl_client.update_item")
def test_batch_import_execution(
    mock_update, mock_list, mock_create_entity, mock_fetch_html, tmp_path
):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(SAMPLE_CSV)

    mock_fetch_html.return_value = """
    <html>
      <span id="productTitle">Lenovo Chromebook Flex 5 13" Laptop</span>
    </html>
    """
    mock_create_entity.return_value = "entity-12345"
    mock_update.return_value = {"id": "entity-12345"}

    results = batch_import(
        items=["B086383HC7"],
        csv_path=str(csv_file),
        dry_run=False,
    )

    assert len(results) == 1
    assert results[0]["asin"] == "B086383HC7"
    assert results[0]["entity_id"] == "entity-12345"
    assert results[0]["quantity"] == 1
    assert results[0]["purchase_price"] == 433.70

    mock_list.assert_called_once()
    mock_create_entity.assert_called_once()
    assert mock_create_entity.call_args[0][0]["purchase_date"] == "2020-12-08"
    mock_update.assert_not_called()


@patch("scripts.batch_import.fetch_url_html", side_effect=Exception("404 Not Found"))
@patch("scripts.batch_import.create_homebox_entity")
@patch("scripts.batch_import.hbctl_client.list_items", return_value=[])
@patch("scripts.batch_import.hbctl_client.update_item")
def test_batch_import_fallback_on_404(
    mock_update, mock_list, mock_create_entity, mock_fetch_html, tmp_path
):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(SAMPLE_CSV)

    mock_create_entity.return_value = "nuc-id"
    mock_update.return_value = {"id": "nuc-id"}

    results = batch_import(
        items=["B087D5T3QT"],
        csv_path=str(csv_file),
        dry_run=False,
    )

    assert len(results) == 1
    assert results[0]["asin"] == "B087D5T3QT"
    assert results[0]["entity_id"] == "nuc-id"
    assert results[0]["quantity"] == 2
    assert results[0]["fallback"] is True
    assert mock_create_entity.call_args[0][0]["purchase_date"] == "2021-08-12"
    mock_update.assert_not_called()


@patch("scripts.batch_import.hbctl_client.list_items")
@patch("scripts.batch_import.hbctl_client.update_item")
def test_batch_import_update_existing(mock_update, mock_list, tmp_path):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(SAMPLE_CSV)

    mock_list.return_value = [
        {"id": "nuc-existing", "name": "Intel NUC Mini PC", "notes": "ASIN: B087D5T3QT"}
    ]
    mock_update.return_value = {"id": "nuc-existing"}

    results = batch_import(
        items=["B087D5T3QT"],
        csv_path=str(csv_file),
        dry_run=False,
        update_existing=True,
    )

    assert len(results) == 1
    assert results[0]["status"] == "updated"
    mock_update.assert_called_once_with(
        "nuc-existing",
        {
            "purchaseFrom": "Amazon",
            "purchasePrice": 607.00,
            "purchaseDate": "2021-08-12",
            "quantity": 2,
        },
    )


def test_find_existing_item():
    from scripts.batch_import import find_existing_item

    cached = [
        {"id": "item-1", "name": "Moen Kitchen Faucet", "modelNumber": "7594EWSRS", "notes": ""},
        {
            "id": "item-2",
            "name": "Moen Valve Trim",
            "fields": [
                {"name": "Model Number", "type": "text", "textValue": "T4111BN-3330"},
                {"name": "Notes", "type": "text", "textValue": "ASIN: B0042RV0CY"},
            ],
        },
    ]

    # Match by ASIN in custom Notes field
    match = find_existing_item("B0042RV0CY", "", "", cached)
    assert match is not None
    assert match["id"] == "item-2"

    # Match by model number inside name
    match = find_existing_item("", "Moen Arbor Motionsense Kitchen Faucet (7594EWSRS)", "", cached)
    assert match is not None
    assert match["id"] == "item-1"

    # Match by model number direct
    match = find_existing_item("", "", "7594EWSRS", cached)
    assert match is not None
    assert match["id"] == "item-1"

