import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.import_url import (
    _clean_text,
    _format_attach_url_spec,
    check_duplicate,
    create_homebox_entity,
    extract_product_data,
    fetch_url_html,
    import_url,
    main,
    normalize_url,
    truncate_to_bytes,
)

SAMPLE_AMAZON_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Moen T4111BN-3330 Kingsley Moentrol Valve Trim Kit with Lever Handle and Valve, Brushed Nickel - Door Levers - Amazon.com</title>
</head>
<body>
<span id="productTitle">Moen T4111BN-3330 Kingsley Moentrol Valve Trim Kit with Lever Handle and Valve, Brushed Nickel</span>
<a id="bylineInfo">Brand: Moen</a>
<span class="a-offscreen">$46.99</span>
<table>
  <tr><th>Item model number</th><td>T4111BN-3330</td></tr>
  <tr><th>Part Number</th><td>T4111BN-3330</td></tr>
</table>
<div id="feature-bullets">
  <ul>
    <li><span class="a-list-item">Includes 3330 valve</span></li>
    <li><span class="a-list-item">Brushed nickel finish provides a lightly brushed warm grey metallic look</span></li>
    <li><span class="a-list-item">Moentrol pressure-balancing valves deliver perfect water coverage</span></li>
  </ul>
</div>
<img id="landingImage" data-old-hires="https://m.media-amazon.com/images/I/41xbCEDMreL._AC_.jpg" />
</body>
</html>
"""

SAMPLE_SCHEMA_ORG_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>DEWALT 20V MAX Cordless Drill (DCD771C2)</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "DEWALT 20V MAX Cordless Drill / Driver Kit",
  "brand": {"@type": "Brand", "name": "DEWALT"},
  "model": "DCD771C2",
  "mpn": "DCD771C2",
  "description": "Compact, lightweight design fits into tight areas.",
  "image": "https://example.com/drill.jpg",
  "offers": {
    "@type": "Offer",
    "price": "99.00",
    "priceCurrency": "USD"
  }
}
</script>
</head>
<body>
<h1>DEWALT Drill</h1>
</body>
</html>
"""

SAMPLE_OPENGRAPH_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="Klein Tools 11-in-1 Screwdriver" />
<meta property="og:description" content="Multi-bit screwdriver and nut driver with cushion grip handle." />
<meta property="og:image" content="https://example.com/klein.jpg" />
<meta property="product:price:amount" content="14.97" />
<meta property="product:brand" content="Klein Tools" />
</head>
<body>
<h1>Product Page</h1>
</body>
</html>
"""


def test_extract_amazon_product():
    data = extract_product_data(SAMPLE_AMAZON_HTML, url="https://www.amazon.com/dp/B0042RV0CY")
    assert "Moen T4111BN-3330 Kingsley" in data["name"]
    assert data["manufacturer"] == "Moen"
    assert data["model_number"] == "T4111BN-3330"
    assert data["purchase_price"] == 46.99
    assert "41xbCEDMreL" in data["image_url"]
    assert "B0042RV0CY" in data["notes"]
    assert "https://www.amazon.com/dp/B0042RV0CY" in data["notes"]


def test_extract_schema_org_product():
    data = extract_product_data(SAMPLE_SCHEMA_ORG_HTML, url="https://example.com/drill")
    assert "DEWALT 20V MAX" in data["name"]
    assert data["manufacturer"] == "DEWALT"
    assert data["model_number"] == "DCD771C2"
    assert data["purchase_price"] == 99.00
    assert data["image_url"] == "https://example.com/drill.jpg"
    assert "Compact, lightweight" in data["description"]


def test_extract_opengraph_product():
    data = extract_product_data(SAMPLE_OPENGRAPH_HTML, url="https://example.com/klein")
    assert "Klein Tools 11-in-1 Screwdriver" in data["name"]
    assert data["manufacturer"] == "Klein Tools"
    assert data["purchase_price"] == 14.97
    assert data["image_url"] == "https://example.com/klein.jpg"
    assert "Multi-bit screwdriver" in data["description"]


def test_check_duplicate_found():
    items = [
        {
            "id": "existing-uuid-123",
            "name": "Moen T4111BN-3330",
            "fields": [{"name": "Model Number", "type": "text", "textValue": "T4111BN-3330"}],
        }
    ]
    with patch("scripts.import_url.hbctl_client.search_items", return_value=items) as mock_search:
        dup = check_duplicate(model_number="T4111BN-3330", name="Moen T4111BN-3330")
        assert dup is not None
        assert dup["id"] == "existing-uuid-123"
        mock_search.assert_called_once_with(
            model="T4111BN-3330",
            query="Moen T4111BN-3330",
            any_match=True,
            select="id,name,notes,modelNumber,fields",
        )


def test_check_duplicate_asin():
    items = [
        {"id": "other-uuid", "name": "Different Name", "modelNumber": "OTHER"},
        {
            "id": "asin-uuid-456",
            "name": "Moen Valve Kit",
            "fields": [{"name": "Notes", "type": "text", "textValue": "Amazon ASIN: B0042RV0CY"}],
        },
    ]
    with patch("scripts.import_url.hbctl_client.search_items", return_value=items) as mock_search:
        dup = check_duplicate(
            model_number="DIFFERENT-MODEL",
            name="Different Name",
            asin="B0042RV0CY",
        )
        assert dup is not None
        assert dup["id"] == "asin-uuid-456"
        mock_search.assert_called_once_with(
            fields=["Notes=B0042RV0CY"],
            model="DIFFERENT-MODEL",
            query="Different Name",
            any_match=True,
            select="id,name,notes,modelNumber,fields",
        )


def test_check_duplicate_asin_only():
    items = [
        {
            "id": "asin-uuid-789",
            "name": "Moen Valve Kit",
            "notes": "Amazon ASIN: B0042RV0CY",
        }
    ]
    with patch("scripts.import_url.hbctl_client.search_items", return_value=items) as mock_search:
        dup = check_duplicate(model_number=None, name="", asin="B0042RV0CY")
        assert dup is not None
        assert dup["id"] == "asin-uuid-789"
        mock_search.assert_called_once_with(
            fields=["Notes=B0042RV0CY"],
            any_match=False,
            select="id,name,notes,modelNumber,fields",
        )


def test_check_duplicate_none():
    with patch("scripts.import_url.hbctl_client.search_items", return_value=[]):
        dup = check_duplicate(model_number="NONEXISTENT", name="Brand New Item")
        assert dup is None


def test_check_duplicate_matches_name():
    items = [{"name": "Matching Name", "id": "hb-name-123"}]
    with patch("scripts.import_url.hbctl_client.search_items", return_value=items) as mock_search:
        dup = check_duplicate(model_number=None, name="Matching Name")
        assert dup is not None
        assert dup["id"] == "hb-name-123"
        mock_search.assert_called_once_with(
            query="Matching Name",
            any_match=False,
            select="id,name,notes,modelNumber,fields",
        )


def test_import_url_dry_run():
    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML):
        result = import_url("https://www.amazon.com/dp/B0042RV0CY", dry_run=True)
    assert result["dry_run"] is True
    assert result["entity"]["manufacturer"] == "Moen"
    assert result["entity"]["model_number"] == "T4111BN-3330"
    assert result["homebox_id"] == "dry-run-id"
    assert result["has_image"] is True


def test_import_url_integration():
    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML), \
         patch("scripts.import_url.check_duplicate", return_value=None), \
         patch("requests.get") as mock_get, \
         patch("scripts.import_url.hbctl_client.create_item", return_value={"id": "hb-imported-777"}) as mock_create:

        res = import_url("https://www.amazon.com/dp/B0042RV0CY", dry_run=False)

    assert res["homebox_id"] == "hb-imported-777"
    mock_get.assert_not_called()
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["attach_urls"] == [
        "https://m.media-amazon.com/images/I/41xbCEDMreL._AC_.jpg=Moen_T4111BN_3330_Kingsley_Moe.jpg"
    ]
    assert mock_create.call_args.kwargs["attach_best_effort"] is True
    assert mock_create.call_args.kwargs["optimize"] is True


def test_format_attach_url_spec():
    assert _format_attach_url_spec("https://example.com/a.jpg", "slug.jpg") == "https://example.com/a.jpg=slug.jpg"
    assert _format_attach_url_spec("https://example.com/img?size=large", "slug.jpg") == "https://example.com/img?size=large=slug.jpg"
    assert _format_attach_url_spec("https://example.com/img?raw", "slug.jpg") == "https://example.com/img?raw"
    assert _format_attach_url_spec("https://example.com/a.jpg", None) == "https://example.com/a.jpg"


def test_create_homebox_entity_truncates_notes():
    long_notes = "【Feature】" * 150
    data = {
        "name": "Test Item",
        "notes": long_notes,
        "purchase_date": "2024-01-15",
    }

    with patch("scripts.import_url.hbctl_client.create_item", return_value={"id": "hb-notes-123"}) as mock_create:
        eid = create_homebox_entity(data)
        assert eid == "hb-notes-123"
        payload = mock_create.call_args[0][0]
        assert len(payload["notes"].encode("utf-8")) <= 1000
        assert payload["purchaseDate"] == "2024-01-15"


def test_import_url_duplicate_found():
    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML), \
         patch("scripts.import_url.check_duplicate", return_value={"id": "hb-existing-999"}):
        res = import_url("https://www.amazon.com/dp/B0042RV0CY", dry_run=False)
        assert res["existing"] is True
        assert res["homebox_id"] == "hb-existing-999"


def test_import_url_main_cli(capsys):
    # 1. Existing
    with patch("sys.argv", ["import_url.py", "http://example.com/item"]), \
         patch("scripts.import_url.import_url", return_value={"existing": True, "entity": {"name": "Existing Item"}, "homebox_id": "hb-123"}):
        main()
        assert "Item already exists in Homebox" in capsys.readouterr().out

    # 2. Dry run
    with patch("sys.argv", ["import_url.py", "http://example.com/item", "--dry-run"]), \
         patch("scripts.import_url.import_url", return_value={"dry_run": True, "entity": {"name": "Dry Item"}}):
        main()
        assert "[DRY RUN]" in capsys.readouterr().out

    # 3. Normal import
    with patch("sys.argv", ["import_url.py", "http://example.com/item"]), \
         patch("scripts.import_url.import_url", return_value={"existing": False, "dry_run": False, "entity": {"name": "New Item", "manufacturer": "Acme", "model_number": "M1", "purchase_price": "10.00"}, "homebox_id": "hb-new"}):
        main()
        assert "Successfully imported New Item" in capsys.readouterr().out

    with patch("sys.argv", ["import_url.py", "http://example.com/item"]), \
         patch("scripts.import_url.import_url", side_effect=RuntimeError("scrape failed")), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_fetch_url_html():
    mock_resp = MagicMock()
    mock_resp.text = "<html>ok</html>"
    mock_resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_resp):
        assert fetch_url_html("http://example.com") == "<html>ok</html>"


def test_truncate_to_bytes_and_clean_text():
    assert truncate_to_bytes("short string", 100) == "short string"
    assert _clean_text("") == ""
    assert _clean_text("Hello &amp; world") == "Hello & world"


def test_normalize_url():
    assert normalize_url("B0CJR4QZ45") == "https://www.amazon.com/dp/B0CJR4QZ45"
    assert normalize_url("b0cjr4qz45") == "https://www.amazon.com/dp/B0CJR4QZ45"
    assert normalize_url("ASIN: B0CJR4QZ45") == "https://www.amazon.com/dp/B0CJR4QZ45"
    assert normalize_url("asin:B0CJR4QZ45") == "https://www.amazon.com/dp/B0CJR4QZ45"
    assert normalize_url("item B0CJR4QZ45") == "https://www.amazon.com/dp/B0CJR4QZ45"
    assert normalize_url("https://www.amazon.com/dp/B0CJR4QZ45") == "https://www.amazon.com/dp/B0CJR4QZ45"
    assert normalize_url("https://example.com/product/123") == "https://example.com/product/123"


def test_import_url_with_asin():
    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML):
        result = import_url("B0CJR4QZ45", dry_run=True)
        assert result["dry_run"] is True
        assert result["has_image"] is True
        assert result["entity"]["source_url"] == "https://www.amazon.com/dp/B0CJR4QZ45"
        assert result["entity"]["purchase_from"] == "Amazon"
