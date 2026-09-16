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


def test_create_homebox_entity_truncates_notes():
    mock_resp_create = MagicMock()
    mock_resp_create.json.return_value = {"id": "hb-notes-123"}
    mock_resp_create.raise_for_status.return_value = None

    mock_resp_update = MagicMock()
    mock_resp_update.raise_for_status.return_value = None

    # Multi-byte characters (each 3 bytes in UTF-8)
    long_notes = "【Feature】" * 150
    data = {
        "name": "Test Item",
        "notes": long_notes,
    }

    with patch("requests.post", return_value=mock_resp_create) as mock_post, \
         patch("requests.put", return_value=mock_resp_update) as mock_put, \
         patch.dict(os.environ, {"HOMEBOX_IP": "127.0.0.1", "HOMEBOX_API_KEY": "fake-key"}):
        eid = create_homebox_entity(data)
        assert eid == "hb-notes-123"
        post_payload = mock_post.call_args[1]["json"]
        put_payload = mock_put.call_args[1]["json"]
        assert len(post_payload["notes"].encode("utf-8")) <= 1000
        assert len(put_payload["notes"].encode("utf-8")) <= 1000


def test_import_url_duplicate_found():
    with patch("scripts.import_url.fetch_url_html", return_value=SAMPLE_AMAZON_HTML), \
         patch("scripts.import_url.check_duplicate", return_value={"id": "hb-existing-999"}), \
         patch.dict(os.environ, {"HOMEBOX_IP": "127.0.0.1", "HOMEBOX_API_KEY": "fake-key"}):
        res = import_url("https://www.amazon.com/dp/B0042RV0CY", dry_run=False)
        assert res["existing"] is True
        assert res["homebox_id"] == "hb-existing-999"


def test_import_url_main_cli(capsys):
    from scripts.import_url import main

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


def test_get_homebox_config(tmp_path, monkeypatch):
    from scripts.import_url import get_homebox_config
    monkeypatch.delenv("HOMEBOX_IP", raising=False)
    monkeypatch.delenv("HOMEBOX_API_KEY", raising=False)

    fake_env = tmp_path / ".env"
    fake_env.write_text("HOMEBOX_IP=192.168.1.50\nHOMEBOX_API_KEY=secret-token\n# comment\n")
    with patch("scripts.import_url.Path.exists", return_value=True), \
         patch("scripts.import_url.Path.read_text", return_value=fake_env.read_text()):
        ip, key = get_homebox_config()
        assert ip == "192.168.1.50"
        assert key == "secret-token"

    with patch("scripts.import_url.Path.exists", return_value=False), \
         pytest.raises(ValueError) as exc:
        get_homebox_config()
    assert "HOMEBOX_IP or HOMEBOX_API_KEY not set" in str(exc.value)


def test_fetch_url_html():
    from scripts.import_url import fetch_url_html
    mock_resp = MagicMock()
    mock_resp.text = "<html>ok</html>"
    mock_resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_resp):
        assert fetch_url_html("http://example.com") == "<html>ok</html>"


def test_check_duplicate_matches_name():
    from scripts.import_url import check_duplicate
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [{"name": "Matching Name", "id": "hb-name-123"}]}
    with patch("requests.get", return_value=mock_resp):
        dup = check_duplicate(base_url="http://127.0.0.1:7745", headers={}, name="Matching Name", model_number=None)
        assert dup["id"] == "hb-name-123"


def test_truncate_to_bytes_and_clean_text():
    from scripts.import_url import truncate_to_bytes, _clean_text
    assert truncate_to_bytes("short string", 100) == "short string"
    assert _clean_text("") == ""
    assert _clean_text("Hello &amp; world") == "Hello & world"

