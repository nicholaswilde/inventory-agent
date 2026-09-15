import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.import_url import (
    check_duplicate,
    create_homebox_entity,
    extract_product_data,
    fetch_url_html,
    import_url,
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
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {"id": "existing-uuid-123", "name": "Moen T4111BN-3330", "modelNumber": "T4111BN-3330"}
        ]
    }
    with patch("requests.get", return_value=mock_resp):
        dup = check_duplicate(
            model_number="T4111BN-3330",
            name="Moen T4111BN-3330",
            base_url="http://127.0.0.1:7745/api/v1",
            headers={"Authorization": "Bearer fake"},
        )
        assert dup is not None
        assert dup["id"] == "existing-uuid-123"


def test_check_duplicate_asin():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {"id": "asin-uuid-456", "name": "Moen Valve Kit"}
        ]
    }
    with patch("requests.get", return_value=mock_resp):
        dup = check_duplicate(
            model_number="DIFFERENT-MODEL",
            name="Different Name",
            base_url="http://127.0.0.1:7745/api/v1",
            headers={"Authorization": "Bearer fake"},
            asin="B0042RV0CY",
        )
        assert dup is not None
        assert dup["id"] == "asin-uuid-456"



def test_check_duplicate_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    with patch("requests.get", return_value=mock_resp):
        dup = check_duplicate(
            model_number="NONEXISTENT",
            name="Brand New Item",
            base_url="http://127.0.0.1:7745/api/v1",
            headers={"Authorization": "Bearer fake"},
        )
        assert dup is None


def test_import_url_dry_run():
    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML):
        result = import_url("https://www.amazon.com/dp/B0042RV0CY", dry_run=True)
    assert result["dry_run"] is True
    assert result["entity"]["manufacturer"] == "Moen"
    assert result["entity"]["model_number"] == "T4111BN-3330"
    assert result["homebox_id"] == "dry-run-id"


def test_import_url_integration(tmp_path):
    mock_resp_create = MagicMock()
    mock_resp_create.json.return_value = {"id": "hb-imported-777", "name": "Moen T4111BN-3330"}
    mock_resp_create.raise_for_status.return_value = None

    mock_resp_update = MagicMock()
    mock_resp_update.raise_for_status.return_value = None

    mock_resp_attach = MagicMock()
    mock_resp_attach.raise_for_status.return_value = None

    mock_img_resp = MagicMock()
    mock_img_resp.status_code = 200
    mock_img_resp.content = b"fake-jpg-bytes"
    mock_img_resp.raise_for_status.return_value = None

    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML), \
         patch("scripts.import_url.check_duplicate", return_value=None), \
         patch("requests.post", side_effect=[mock_resp_create, mock_resp_attach]) as mock_post, \
         patch("requests.put", return_value=mock_resp_update) as mock_put, \
         patch("requests.get", return_value=mock_img_resp), \
         patch.dict(os.environ, {"HOMEBOX_IP": "127.0.0.1", "HOMEBOX_API_KEY": "fake-key"}):

        res = import_url("https://www.amazon.com/dp/B0042RV0CY", dry_run=False)

    assert res["homebox_id"] == "hb-imported-777"
    assert mock_post.call_count == 2
    assert mock_put.call_count == 1
