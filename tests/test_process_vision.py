"""
Comprehensive Test Suite for Electronic Component Vision Automation Pipeline.

Verifies:
- Image queue scanning & filtering
- Local OCR invocation (lit / tesseract) & error handling
- OCR quality heuristic evaluation (meaningful component vs noise)
- Gemini Vision API fallback (payload formatting, parsing, auth, retries, safety blocks)
- HomeBox shell subprocess wrapper (search, create, attach)
- Atomic processed image movement and failure retention
- CLI parsing & dry-run execution
- End-to-end mocked pipeline flows (new item, duplicate item, partial error recovery)
"""
import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import requests

from scripts.process_vision import (
    attach_image,
    call_homebox,
    create_entity,
    identify_component,
    is_ocr_meaningful,
    main,
    move_to_processed,
    parse_args,
    process_all_images,
    process_single_image,
    query_gemini_vision,
    run_local_ocr,
    scan_image_queue,
    search_entity,
)


# ============================================================================
# 1. Image Queue Scanner Tests
# ============================================================================

class TestImageQueueScanner:
    """Tests for scanning and filtering the pending images directory."""

    def test_scan_finds_all_valid_image_extensions(self, tmp_path):
        """Verify .jpg, .jpeg, .png in mixed cases are scanned in sorted order."""
        pending = tmp_path / "pending"
        pending.mkdir()

        valid_files = ["alpha.jpg", "beta.jpeg", "gamma.png", "delta.JPG", "epsilon.PNG"]
        for f in valid_files:
            (pending / f).write_bytes(b"dummy image data")

        result = scan_image_queue(pending)
        result_names = [p.name for p in result]
        assert result_names == sorted(valid_files)

    def test_scan_skips_non_images_and_hidden_files(self, tmp_path):
        """Verify .gitkeep, text files, archives, dotfiles, and subdirectories are ignored."""
        pending = tmp_path / "pending"
        pending.mkdir()

        (pending / "valid1.jpg").write_bytes(b"data")
        (pending / "valid2.png").write_bytes(b"data")

        # Non-images & metadata files
        (pending / ".gitkeep").touch()
        (pending / ".DS_Store").touch()
        (pending / ".hidden.jpg").write_bytes(b"hidden")
        (pending / "notes.txt").write_text("component list")
        (pending / "data.csv").write_text("a,b,c")
        (pending / "archive.zip").write_bytes(b"zip")

        # Subdirectory with nested image
        sub = pending / "nested_dir"
        sub.mkdir()
        (sub / "nested.jpg").write_bytes(b"nested")

        result = scan_image_queue(pending)
        result_names = [p.name for p in result]
        assert result_names == ["valid1.jpg", "valid2.png"]

    def test_scan_empty_directory_returns_empty_list(self, tmp_path):
        """Verify empty directory or directory with only .gitkeep returns empty list."""
        pending = tmp_path / "pending"
        pending.mkdir()
        assert scan_image_queue(pending) == []

        (pending / ".gitkeep").touch()
        assert scan_image_queue(pending) == []

    def test_scan_nonexistent_directory_returns_empty_list(self, tmp_path):
        """Verify non-existent directory returns empty list without crashing."""
        non_existent = tmp_path / "does_not_exist"
        assert scan_image_queue(non_existent) == []

    def test_scan_preserves_special_characters_in_filenames(self, tmp_path):
        """Verify filenames with macro focus symbols like ~, (), and spaces are preserved."""
        pending = tmp_path / "pending"
        pending.mkdir()

        special_files = [
            "PXL_20260822_211521439.MACRO_FOCUS~2.jpg",
            "PXL_20260822_214703084.MACRO_FOCUS(1).jpg",
            "PXL component with spaces.png",
        ]
        for f in special_files:
            (pending / f).write_bytes(b"data")

        result = scan_image_queue(pending)
        assert len(result) == len(special_files)
        assert {p.name for p in result} == set(special_files)


# ============================================================================
# 2. Local OCR Analyzer Tests
# ============================================================================

class TestLocalOCRAnalyzer:
    """Tests for local OCR execution via lit/tesseract and error handling."""

    def test_run_local_ocr_clean_output(self):
        """Verify successful lit invocation and stripping of page/tool metadata headers."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["lit", "parse", "sample.jpg", "--quiet"],
                returncode=0,
                stdout="--- Page 1 ---\nESP32-WROOM-32D\nEspressif Systems\n[liteparse] done\n",
                stderr="",
            )
            result = run_local_ocr("sample.jpg")
            assert result == "ESP32-WROOM-32D\nEspressif Systems"
            mock_run.assert_called_once_with(
                ["lit", "parse", "sample.jpg", "--quiet"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

    def test_run_local_ocr_empty_output(self):
        """Verify OCR returning empty text or only headers returns empty string."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["lit", "parse"],
                returncode=0,
                stdout="--- Page 1 ---\n\n   \n[liteparse] done\n",
                stderr="",
            )
            assert run_local_ocr("sample.jpg") == ""

    def test_run_local_ocr_tool_failure(self):
        """Verify non-zero returncode is handled gracefully without crashing."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["lit", "parse"],
                returncode=1,
                stdout="",
                stderr="Error: corrupt image file",
            )
            assert run_local_ocr("sample.jpg") == ""

    def test_run_local_ocr_binary_not_found(self):
        """Verify missing lit/tesseract binary returns empty string."""
        with patch("subprocess.run", side_effect=FileNotFoundError("lit not found")):
            assert run_local_ocr("sample.jpg") == ""

    def test_run_local_ocr_timeout(self):
        """Verify timeout during OCR execution returns empty string."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="lit", timeout=15)):
            assert run_local_ocr("sample.jpg") == ""


# ============================================================================
# 3. OCR Quality Evaluator Tests
# ============================================================================

class TestOCRQualityEvaluator:
    """Tests for heuristic evaluation of OCR text quality."""

    @pytest.mark.parametrize(
        "valid_part_text",
        [
            "ESP32-WROOM-32D Wi-Fi & Bluetooth Module",
            "DHT11 Temperature and Humidity Sensor Module",
            "Texas Instruments NE555P Precision Timer DIP-8",
            "AMS1117-3.3 Linear Voltage Regulator SOT-223",
            "CH340G USB to Serial UART Interface",
            "STM32F103C8T6 ARM Cortex-M3 Minimal System",
            "ATmega328P-PU 8-bit Microcontroller",
            "TP4056 1A Li-Ion Battery Charging Board",
        ],
    )
    def test_ocr_meaningful_valid_part_numbers(self, valid_part_text):
        """Valid electronic part numbers and IC identifiers must be recognized as meaningful."""
        assert is_ocr_meaningful(valid_part_text) is True

    @pytest.mark.parametrize(
        "valid_keyword_text",
        [
            "5V Dual Channel Relay Module for Arduino",
            "OLED Display I2C 128x64 0.96 inch",
            "Buck Converter Step Down Power Supply Board",
            "Microcontroller Development Board 3.3V",
            "Optocoupler Transceiver Interface Shield",
        ],
    )
    def test_ocr_meaningful_valid_keywords(self, valid_keyword_text):
        """Descriptions with standard electronic component keywords must be recognized."""
        assert is_ocr_meaningful(valid_keyword_text) is True

    @pytest.mark.parametrize(
        "noise_text",
        [
            "a . Fy . el EL : 2 4 RE 3 > ¥",
            "ow\n +h\n a=\n Paes\n EN\n J > = vi »",
            "pes an : 1 0 A 3 5 ny Poh dl wf i evo val pe",
            "\\ EA \\ + TOW | WT r rs 4 EB \n _ er \\ nr > :",
            "©, | A 4 : a |g bear 2 - Ve - Ria, > Ji] > (HG | LE | ni)",
            "",
            "   \n\t  ",
            "OK",
            "123",
            "--- Page 1 ---\n[liteparse]\n",
            "The quick brown fox jumps over the lazy dog.",
            "Receipt No 94829 Total 45.99 Thank You",
            "!@#$% ^&*() ___ +++ === ~~~ {} [] | \\ < >",
        ],
    )
    def test_ocr_meaningful_rejects_noise_and_non_electronic_text(self, noise_text):
        """Noise fragments, sparse punctuation, empty strings, and non-electronic text must return False."""
        assert is_ocr_meaningful(noise_text) is False

    @pytest.mark.parametrize(
        "substring_false_positives",
        [
            "hi-speed transmission line",
            "gas pis control valve",
            "conspicuous error report",
            "hospital medical unit",
        ],
    )
    def test_ocr_meaningful_rejects_keyword_substring_false_positives(self, substring_false_positives):
        """Keywords like 'spi' in 'hi-speed' or 'gas pis' must not trigger false positive domain match."""
        assert is_ocr_meaningful(substring_false_positives) is False

    @pytest.mark.parametrize(
        "word_boundary_keywords",
        [
            "SPI Interface Bus Module",
            "I2C-SPI Protocol Adapter",
            "Dual Relay Board 5V",
            "Microcontroller Core Board",
        ],
    )
    def test_ocr_meaningful_word_boundary_keywords(self, word_boundary_keywords):
        """Keywords matched with proper word boundaries must be recognized as meaningful."""
        assert is_ocr_meaningful(word_boundary_keywords) is True


# ============================================================================
# 3b. Component Identification & Line Extraction Tests
# ============================================================================

class TestComponentIdentification:
    """Tests for identify_component: local OCR vs Gemini Vision fallback, line sanitization, and model extraction."""

    def test_identify_component_leading_noise_lines_sanitized(self, tmp_path):
        """Verify leading noise characters (., a, |, 4) are skipped to find best descriptive line."""
        img = tmp_path / "relay.jpg"
        img.write_bytes(b"dummy")

        ocr_with_noise = (
            ".\n"
            "a\n"
            "|\n"
            "Non-Latching Relay FeatherWing\n"
            "Adafruit Industries\n"
        )
        with patch("scripts.process_vision.run_local_ocr", return_value=ocr_with_noise), \
             patch("scripts.process_vision.query_gemini_vision") as mock_gemini:
            comp = identify_component(img)
            assert comp is not None
            assert comp["name"] == "Non-Latching Relay FeatherWing"
            assert comp["description"] == ocr_with_noise
            assert mock_gemini.call_count == 0

    def test_identify_component_part_number_populates_model_number(self, tmp_path):
        """Verify part number is extracted into modelNumber field."""
        img = tmp_path / "esp32.jpg"
        img.write_bytes(b"dummy")

        ocr_text = "4\nESP32-WROOM-32D Wi-Fi & Bluetooth Module\nEspressif Systems\n"
        with patch("scripts.process_vision.run_local_ocr", return_value=ocr_text), \
             patch("scripts.process_vision.query_gemini_vision") as mock_gemini:
            comp = identify_component(img)
            assert comp is not None
            assert comp["name"] == "ESP32-WROOM-32D Wi-Fi & Bluetooth Module"
            assert comp["modelNumber"] == "ESP32-WROOM-32D"
            assert mock_gemini.call_count == 0

    def test_identify_component_falls_back_to_gemini_when_ocr_has_no_valid_line(self, tmp_path):
        """Verify fallback to Gemini Vision when OCR produces only short noise lines."""
        img = tmp_path / "chip.jpg"
        img.write_bytes(b"dummy")

        ocr_short_noise = ".\n4\nx\ny\nz\n1\n"
        with patch("scripts.process_vision.run_local_ocr", return_value=ocr_short_noise), \
             patch("scripts.process_vision.query_gemini_vision") as mock_gemini:
            mock_gemini.return_value = {
                "name": "LM7805 Voltage Regulator",
                "modelNumber": "LM7805",
                "description": "5V Linear Regulator",
            }
            comp = identify_component(img, api_key="test-key")
            assert comp is not None
            assert comp["name"] == "LM7805 Voltage Regulator"
            assert mock_gemini.call_count == 1


# ============================================================================
# 4. Gemini Vision Fallback Tests
# ============================================================================

class TestGeminiVisionFallback:
    """Tests for multimodal Gemini Vision API integration."""

    def test_gemini_missing_api_key_raises_value_error(self, monkeypatch, tmp_path):
        """Verify ValueError raised when GEMINI_API_KEY is not set."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"dummy image bytes")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            query_gemini_vision(img, api_key=None)

    def test_gemini_nonexistent_image_raises_file_not_found(self, tmp_path):
        """Verify FileNotFoundError raised when image does not exist on disk."""
        non_existent = tmp_path / "missing.jpg"
        with pytest.raises(FileNotFoundError):
            query_gemini_vision(non_existent, api_key="fake-key")

    def test_gemini_successful_response_parsing(self, tmp_path):
        """Verify Gemini JSON response is parsed into component schema."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"image_content_bytes")

        expected_component = {
            "name": "DHT11 Sensor Module",
            "manufacturer": "Aosong",
            "modelNumber": "DHT11",
            "description": "Digital temperature and humidity sensor module with 3-pin breakout.",
            "quantity": 1,
            "notes": "Blue casing PCB",
            "tags": ["Sensor", "Temperature", "Humidity"],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(expected_component)}]
                    }
                }
            ]
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = query_gemini_vision(img, api_key="test-api-key")
            assert result["name"] == "DHT11 Sensor Module"
            assert result["modelNumber"] == "DHT11"
            assert result["manufacturer"] == "Aosong"
            assert result["description"] == expected_component["description"]
            assert mock_post.call_count == 1

            # Verify request URL and base64 payload
            url_called = mock_post.call_args[0][0]
            assert "key=test-api-key" in url_called
            req_json = mock_post.call_args.kwargs["json"]
            parts = req_json["contents"][0]["parts"]
            inline_part = next(p for p in parts if "inline_data" in p)
            expected_b64 = base64.b64encode(b"image_content_bytes").decode("utf-8")
            assert inline_part["inline_data"]["data"] == expected_b64
            assert inline_part["inline_data"]["mime_type"] == "image/jpeg"

    def test_gemini_png_mime_type_handling(self, tmp_path):
        """Verify image/png mime type used for .png files."""
        img = tmp_path / "chip.png"
        img.write_bytes(b"png_bytes")

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"name": "ESP32", "description": "MCU"})}]}}]
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            query_gemini_vision(img, api_key="test-api-key")
            req_json = mock_post.call_args.kwargs["json"]
            parts = req_json["contents"][0]["parts"]
            inline_part = next(p for p in parts if "inline_data" in p)
            assert inline_part["inline_data"]["mime_type"] == "image/png"

    def test_gemini_markdown_fenced_json_cleaning(self, tmp_path):
        """Verify markdown code fences (```json ... ```) are cleanly parsed."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        fenced_text = "```json\n{\n  \"name\": \"ESP32-WROOM-32\",\n  \"description\": \"WiFi & BT MCU\"\n}\n```"
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": fenced_text}]}}]
        }

        with patch("requests.post", return_value=mock_resp):
            result = query_gemini_vision(img, api_key="test-key")
            assert result["name"] == "ESP32-WROOM-32"
            assert result["description"] == "WiFi & BT MCU"

    def test_gemini_malformed_json_raises_error(self, tmp_path):
        """Verify invalid or unparseable JSON text raises error."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Not valid JSON: {name: unquoted"}]}}]
        }

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises((ValueError, json.JSONDecodeError)):
                query_gemini_vision(img, api_key="test-key")

    def test_gemini_rate_limit_429_retry_success(self, tmp_path):
        """Verify HTTP 429 triggers exponential backoff retries and succeeds on retry."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        resp_429_1 = MagicMock(status_code=429)
        resp_429_2 = MagicMock(status_code=429)
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps({"name": "NE555 Timer", "description": "Timer IC"})}]
                    }
                }
            ]
        }

        with patch("requests.post", side_effect=[resp_429_1, resp_429_2, resp_200]) as mock_post, \
             patch("time.sleep") as mock_sleep:
            result = query_gemini_vision(img, api_key="test-key", max_retries=3, retry_delay=0.1)
            assert result["name"] == "NE555 Timer"
            assert mock_post.call_count == 3
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(0.1)
            mock_sleep.assert_any_call(0.2)

    def test_gemini_rate_limit_429_exhausted_single_model(self, tmp_path):
        """Verify repeated HTTP 429 raises error when max retries are exhausted on a single model."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        resp_429 = MagicMock(status_code=429)
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError("429 Too Many Requests")

        with patch("requests.post", return_value=resp_429) as mock_post, \
             patch("time.sleep") as mock_sleep:
            with pytest.raises((requests.exceptions.HTTPError, RuntimeError)):
                query_gemini_vision(img, api_key="test-key", max_retries=3, retry_delay=0.1, models=["gemini-2.5-flash"])
            assert mock_post.call_count == 3
            assert mock_sleep.call_count == 2

    def test_gemini_rate_limit_429_exhausted_all_models(self, tmp_path):
        """Verify repeated HTTP 429 across multiple models raises error after exhausting all retries."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        resp_429 = MagicMock(status_code=429)
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError("429 Too Many Requests")

        with patch("requests.post", return_value=resp_429) as mock_post, \
             patch("time.sleep") as mock_sleep:
            with pytest.raises((requests.exceptions.HTTPError, RuntimeError)):
                query_gemini_vision(img, api_key="test-key", max_retries=3, retry_delay=0.1, models=["model-a", "model-b"])
            assert mock_post.call_count == 6
            assert mock_sleep.call_count == 4

    def test_gemini_429_fallback_to_next_model_succeeds(self, tmp_path):
        """Verify when first model encounters 429 on all retries, the loop falls back to next model and succeeds."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        resp_429 = MagicMock(status_code=429)
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError("429 Too Many Requests")

        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps({"name": "Fallback Sensor", "description": "From 2nd model"})}]
                    }
                }
            ]
        }

        with patch("requests.post", side_effect=[resp_429, resp_429, resp_429, resp_200]) as mock_post, \
             patch("time.sleep") as mock_sleep:
            result = query_gemini_vision(
                img,
                api_key="test-key",
                max_retries=3,
                retry_delay=0.1,
                models=["gemini-2.5-flash", "gemini-2.0-flash"],
            )
            assert result["name"] == "Fallback Sensor"
            assert mock_post.call_count == 4
            assert mock_sleep.call_count == 2

    def test_gemini_safety_blocked_response(self, tmp_path):
        """Verify prompt blocked for safety raises RuntimeError."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"bytes")

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [],
            "promptFeedback": {"blockReason": "SAFETY"},
        }

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="SAFETY"):
                query_gemini_vision(img, api_key="test-key")


# ============================================================================
# 5. HomeBox Subprocess Wrapper Tests
# ============================================================================

class TestHomeboxSubprocess:
    """Tests for ./scripts/homebox.sh subprocess execution (search, create, attach)."""

    def test_search_entity_match_found(self):
        """Verify search returns UUID when matching item is found."""
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "search", "DHT11"],
                returncode=0,
                stdout="ID: 12edefc5-6bf3-492d-b340-1c73a85be0b8 | Name: DHT11 Sensor Module\n",
                stderr="",
            )
            entity_id = search_entity("DHT11")
            assert entity_id == "12edefc5-6bf3-492d-b340-1c73a85be0b8"
            mock_hb.assert_called_once_with("search", "DHT11", homebox_script=None)

    def test_search_entity_no_match(self):
        """Verify search returns None when 0 items match."""
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "search", "NonExistent"],
                returncode=0,
                stdout="",
                stderr="",
            )
            assert search_entity("NonExistent") is None

    def test_search_entity_subprocess_error(self):
        """Verify search returns None on non-zero exit code."""
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "search", "ErrorItem"],
                returncode=1,
                stdout="",
                stderr="Connection refused",
            )
            assert search_entity("ErrorItem") is None

    @pytest.mark.parametrize(
        "invalid_query",
        [
            "",
            "   ",
            ".",
            "4",
            "12",
            "..",
            "123",
            "---",
            "@#$",
        ],
    )
    def test_search_entity_rejects_short_and_non_alpha_queries(self, invalid_query):
        """Verify search_entity returns None without invoking subprocess for queries < 3 chars or lacking letters."""
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            result = search_entity(invalid_query)
            assert result is None
            assert mock_hb.call_count == 0

    def test_create_entity_success(self):
        """Verify create passes JSON and parses returned entity UUID."""
        comp = {
            "name": "CH340G Module",
            "modelNumber": "CH340G",
            "description": "USB TTL IC",
        }
        created_json = json.dumps({"id": "created-uuid-999", "name": "CH340G Module"})

        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "create", json.dumps(comp)],
                returncode=0,
                stdout=created_json,
                stderr="",
            )
            entity_id = create_entity(comp)
            assert entity_id == "created-uuid-999"
            mock_hb.assert_called_once_with("create", json.dumps(comp), homebox_script=None)

    def test_create_entity_failure_raises_runtime_error(self):
        """Verify create failure raises RuntimeError."""
        comp = {"name": "Bad Item"}
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "create"],
                returncode=1,
                stdout="",
                stderr="Server 500 Error",
            )
            with pytest.raises(RuntimeError, match="Failed to create HomeBox entity"):
                create_entity(comp)

    def test_create_entity_invalid_json_response_raises_runtime_error(self):
        """Verify malformed JSON from create subprocess raises RuntimeError."""
        comp = {"name": "Bad Response Item"}
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "create"],
                returncode=0,
                stdout="<html>502 Bad Gateway</html>",
                stderr="",
            )
            with pytest.raises(RuntimeError, match="Invalid JSON response"):
                create_entity(comp)

    def test_attach_image_success(self):
        """Verify attach passes entity ID and image path returning True."""
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "attach", "uuid-123", "image.jpg"],
                returncode=0,
                stdout='{"id": "att-1", "name": "image.jpg"}',
                stderr="",
            )
            result = attach_image("uuid-123", "image.jpg")
            assert result is True
            mock_hb.assert_called_once_with("attach", "uuid-123", "image.jpg", homebox_script=None)

    def test_attach_image_failure(self):
        """Verify attach returns False on non-zero exit code."""
        with patch("scripts.process_vision.call_homebox") as mock_hb:
            mock_hb.return_value = subprocess.CompletedProcess(
                args=["./scripts/homebox.sh", "attach", "uuid-123", "image.jpg"],
                returncode=1,
                stdout="",
                stderr="File upload failed",
            )
            assert attach_image("uuid-123", "image.jpg") is False


# ============================================================================
# 6. Processed Image Mover Tests
# ============================================================================

class TestProcessedImageMover:
    """Tests for moving processed images to target directory."""

    def test_move_to_processed_atomic(self, tmp_path):
        """Verify image is moved to processed directory and removed from pending."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        img = pending / "item.jpg"
        img.write_bytes(b"content")

        dest = move_to_processed(img, processed)
        assert not img.exists()
        assert dest.exists()
        assert dest == processed / "item.jpg"
        assert dest.read_bytes() == b"content"

    def test_move_to_processed_auto_creates_directory(self, tmp_path):
        """Verify processed directory is created automatically if it does not exist."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        # processed directory intentionally not created

        img = pending / "item.jpg"
        img.write_bytes(b"content")

        dest = move_to_processed(img, processed)
        assert processed.exists()
        assert dest.exists()


# ============================================================================
# 7. CLI & Dry Run Tests
# ============================================================================

class TestCLIAndDryRun:
    """Tests for CLI arguments, default values, and dry-run execution."""

    def test_parse_args_defaults(self):
        """Verify default CLI arguments."""
        args = parse_args([])
        assert args.pending_dir == "images/pending"
        assert args.processed_dir == "images/processed"
        assert args.dry_run is False
        assert args.api_key is None

    def test_parse_args_custom(self):
        """Verify custom CLI flags."""
        args = parse_args([
            "--pending-dir", "/tmp/in",
            "--processed-dir", "/tmp/out",
            "--dry-run",
            "--api-key", "custom-key",
        ])
        assert args.pending_dir == "/tmp/in"
        assert args.processed_dir == "/tmp/out"
        assert args.dry_run is True
        assert args.api_key == "custom-key"

    def test_cli_dry_run_skips_mutating_calls(self, tmp_path):
        """Verify dry-run mode identifies items but executes NO creates, attaches, or file moves."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        img = pending / "test_item.jpg"
        img.write_bytes(b"image_data")

        with patch("scripts.process_vision.identify_component") as mock_id, \
             patch("scripts.process_vision.call_homebox") as mock_hb:

            mock_id.return_value = {
                "name": "Dry Run Component",
                "modelNumber": "DRY-01",
                "description": "Test Component",
            }
            # Search returns no match
            mock_hb.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="")

            result = process_single_image(img, processed, dry_run=True)
            assert result is True

            # Assert only search was called, no create or attach
            assert mock_hb.call_count == 1
            assert mock_hb.call_args[0][0] == "search"

            # Assert file did NOT move
            assert img.exists()
            assert not (processed / "test_item.jpg").exists()

    def test_main_cli_entrypoint(self, tmp_path):
        """Verify main() entrypoint returns 0 on success."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        (pending / "test.jpg").write_bytes(b"data")

        with patch("scripts.process_vision.identify_component", return_value={"name": "Item", "description": "Desc"}), \
             patch("scripts.process_vision.call_homebox") as mock_hb:

            mock_hb.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout=""),  # search
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"id": "new-1"}'),  # create
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"status": "ok"}'),  # attach
            ]

            exit_code = main(["--pending-dir", str(pending), "--processed-dir", str(processed)])
            assert exit_code == 0
            assert not (pending / "test.jpg").exists()
    def test_cli_help_flag(self):
        """Verify --help / -h flag displays help and raises SystemExit(0)."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_main_cli_failure_exit_code(self, tmp_path):
        """Verify main() returns 1 when all processing attempts fail."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        (pending / "fail.jpg").write_bytes(b"data")

        with patch("scripts.process_vision.identify_component", return_value=None):
            exit_code = main(["--pending-dir", str(pending), "--processed-dir", str(processed)])
            assert exit_code == 1
            assert (pending / "fail.jpg").exists()


# ============================================================================
# 8. End-to-End Mocked Pipeline Integration Tests
# ============================================================================

class TestFullPipelineE2EMock:
    """Tests for full pipeline workflows across batches with mocked external dependencies."""

    def test_e2e_new_item_creation_flow(self, tmp_path):
        """Verify new item workflow: OCR fails -> Gemini succeeds -> create -> attach -> move."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        img = pending / "new_sensor.jpg"
        img.write_bytes(b"data")

        with patch("scripts.process_vision.run_local_ocr", return_value="?? noise %%"), \
             patch("scripts.process_vision.query_gemini_vision") as mock_gemini, \
             patch("scripts.process_vision.call_homebox") as mock_hb:

            mock_gemini.return_value = {
                "name": "BME280 Pressure Sensor",
                "modelNumber": "BME280",
                "manufacturer": "Bosch",
                "description": "Digital pressure and humidity sensor.",
            }

            mock_hb.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout=""),  # search -> not found
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"id": "bme280-uuid"}'),  # create
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"status": "attached"}'),  # attach
            ]

            success = process_single_image(img, processed_dir=processed, api_key="test-key")
            assert success is True
            assert not img.exists()
            assert (processed / "new_sensor.jpg").exists()

            # Verify call sequence
            hb_calls = mock_hb.call_args_list
            assert len(hb_calls) == 3
            assert hb_calls[0][0][0] == "search"
            assert hb_calls[1][0][0] == "create"
            assert hb_calls[2][0][0] == "attach"
            assert hb_calls[2][0][1] == "bme280-uuid"

    def test_e2e_duplicate_item_attach_flow(self, tmp_path):
        """Verify duplicate item workflow: Gemini succeeds -> duplicate found -> attach to existing -> move."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        img = pending / "dht11_angle2.jpg"
        img.write_bytes(b"data")

        with patch("scripts.process_vision.run_local_ocr", return_value=""), \
             patch("scripts.process_vision.query_gemini_vision") as mock_gemini, \
             patch("scripts.process_vision.call_homebox") as mock_hb:

            mock_gemini.return_value = {
                "name": "DHT11 Sensor Module",
                "modelNumber": "DHT11",
                "description": "Temperature and humidity sensor.",
            }

            mock_hb.side_effect = [
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="ID: existing-dht11-uuid | Name: DHT11 Sensor Module\n",
                ),  # search -> match
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"status": "attached"}'),  # attach
            ]

            success = process_single_image(img, processed_dir=processed, api_key="test-key")
            assert success is True
            assert not img.exists()
            assert (processed / "dht11_angle2.jpg").exists()

            # Assert create was NEVER called
            hb_calls = mock_hb.call_args_list
            assert len(hb_calls) == 2
            assert hb_calls[0][0][0] == "search"
            assert hb_calls[1][0][0] == "attach"
            assert hb_calls[1][0][1] == "existing-dht11-uuid"

    def test_e2e_meaningful_ocr_bypasses_gemini(self, tmp_path):
        """Verify high quality local OCR creates item directly without calling Gemini Vision API."""
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        img = pending / "esp32.jpg"
        img.write_bytes(b"data")

        with patch("scripts.process_vision.run_local_ocr", return_value="ESP32-WROOM-32D Wi-Fi & Bluetooth Module"), \
             patch("scripts.process_vision.query_gemini_vision") as mock_gemini, \
             patch("scripts.process_vision.call_homebox") as mock_hb:

            mock_hb.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout=""),  # search -> not found
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"id": "esp32-uuid"}'),  # create
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"status": "attached"}'),  # attach
            ]

            success = process_single_image(img, processed_dir=processed)
            assert success is True
            assert not img.exists()
            assert (processed / "esp32.jpg").exists()

            # Gemini must NOT be called
            assert mock_gemini.call_count == 0

    def test_e2e_mixed_batch_with_partial_failure_recovery(self, tmp_path):
        """
        Verify batch processing over mixed directory:
        - Image 1: Duplicate found -> attached to existing -> moved
        - Image 2: New item -> created -> attached -> moved
        - Image 3: Create fails -> file remains in pending
        - Non-image files (.gitkeep, notes.txt) remain in pending untouched
        """
        pending = tmp_path / "pending"
        processed = tmp_path / "processed"
        pending.mkdir()
        processed.mkdir()

        (pending / ".gitkeep").touch()
        (pending / "notes.txt").write_text("todo list")
        (pending / "img1_dup.jpg").write_bytes(b"dup")
        (pending / "img2_new.png").write_bytes(b"new")
        (pending / "img3_fail.jpg").write_bytes(b"fail")

        def ocr_dispatch(path):
            if "img1_dup" in str(path):
                return "DHT11 Temperature Sensor Module"
            return "?? %$"

        def gemini_dispatch(path, **kwargs):
            if "img2_new" in str(path):
                return {"name": "CH340G USB Interface", "modelNumber": "CH340G", "description": "USB IC"}
            return {"name": "Relay Module 5V", "modelNumber": "RELAY", "description": "5V Relay"}

        with patch("scripts.process_vision.run_local_ocr", side_effect=ocr_dispatch), \
             patch("scripts.process_vision.query_gemini_vision", side_effect=gemini_dispatch) as mock_gemini, \
             patch("scripts.process_vision.call_homebox") as mock_hb:

            mock_hb.side_effect = [
                # img1_dup: search match -> attach
                subprocess.CompletedProcess(args=[], returncode=0, stdout="ID: dup-uuid | Name: DHT11\n"),
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"status": "ok"}'),
                # img2_new: search none -> create -> attach
                subprocess.CompletedProcess(args=[], returncode=0, stdout=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"id": "new-uuid"}'),
                subprocess.CompletedProcess(args=[], returncode=0, stdout='{"status": "ok"}'),
                # img3_fail: search none -> create fails (returncode 1)
                subprocess.CompletedProcess(args=[], returncode=0, stdout=""),
                subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="500 Internal Error"),
            ]

            summary = process_all_images(pending_dir=pending, processed_dir=processed, api_key="key")

            assert summary == {"total": 3, "succeeded": 2, "failed": 1}

            # Moved files
            assert (processed / "img1_dup.jpg").exists()
            assert (processed / "img2_new.png").exists()
            assert not (pending / "img1_dup.jpg").exists()
            assert not (pending / "img2_new.png").exists()

            # Failed file remains in pending
            assert (pending / "img3_fail.jpg").exists()
            assert not (processed / "img3_fail.jpg").exists()

            # Non-image files preserved
            assert (pending / ".gitkeep").exists()
            assert (pending / "notes.txt").exists()

            # Gemini only called for img2_new and img3_fail
            assert mock_gemini.call_count == 2
