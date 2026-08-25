"""Tests for homebox_dedup.py — detect, delete, and merge duplicate HomeBox entities."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from homebox_dedup import (
    STOP_WORDS,
    call_homebox,
    detect_duplicates,
    jaccard_similarity,
    merge_and_delete,
    normalize_name,
    parse_list_output,
    select_keeper,
)


class TestNormalizeName(unittest.TestCase):
    def test_lowercase_and_strip(self):
        assert normalize_name("  DHT11  ") == "dht11"

    def test_removes_stop_words(self):
        result = normalize_name("PIR Motion Sensor Module Breakout Board Kit")
        for w in STOP_WORDS:
            assert w not in result.split()

    def test_removes_punctuation(self):
        assert normalize_name("USB Type-C Breakout Board") == normalize_name("USB C Breakout Board")

    def test_version_stripped(self):
        assert "v1" not in normalize_name("Solar Charger Module V1.0")


class TestJaccardSimilarity(unittest.TestCase):
    def test_identical(self):
        assert jaccard_similarity("foo bar", "foo bar") == 1.0

    def test_disjoint(self):
        assert jaccard_similarity("alpha beta", "gamma delta") == 0.0

    def test_partial(self):
        score = jaccard_similarity("adafruit feather esp32", "adafruit huzzah esp32 feather")
        assert 0.4 < score < 1.0

    def test_empty(self):
        assert jaccard_similarity("", "") == 0.0


class TestParseListOutput(unittest.TestCase):
    def test_parses_correctly(self):
        output = "ID: abc-123 | Name: DHT11 Sensor\nID: def-456 | Name: Relay Module\n"
        items = parse_list_output(output)
        assert len(items) == 2
        assert items[0] == {"id": "abc-123", "name": "DHT11 Sensor"}
        assert items[1] == {"id": "def-456", "name": "Relay Module"}

    def test_ignores_bad_lines(self):
        assert parse_list_output("not a valid line\n") == []


class TestDetectDuplicates(unittest.TestCase):
    def _items(self):
        return [
            {"id": "1", "name": "Adafruit PowerBoost 1000 Basic"},
            {"id": "2", "name": "Adafruit PowerBoost 1000 Basic"},
            {"id": "3", "name": "USB C Breakout Board"},
            {"id": "4", "name": "USB Type-C Breakout Board"},
            {"id": "5", "name": "Totally Different Gyroscope"},
        ]

    def test_exact_duplicates(self):
        groups = detect_duplicates(self._items(), threshold=0.9)
        exact = [g for g in groups if g["type"] == "exact"]
        assert len(exact) == 1
        assert len(exact[0]["items"]) == 2

    def test_near_duplicates(self):
        groups = detect_duplicates(self._items(), threshold=0.7)
        near = [g for g in groups if g["type"] == "near"]
        assert len(near) >= 1

    def test_no_false_positives(self):
        groups = detect_duplicates(self._items(), threshold=0.9)
        for g in groups:
            for item in g["items"]:
                assert item["name"] != "Totally Different Gyroscope"


class TestSelectKeeper(unittest.TestCase):
    def test_prefers_longer_name(self):
        items = [
            {"id": "1", "name": "PIR Sensor", "quantity": 1},
            {"id": "2", "name": "HC-SR501 PIR Motion Sensor Module", "quantity": 1},
        ]
        keeper = select_keeper(items)
        assert keeper["id"] == "2"

    def test_prefers_higher_quantity(self):
        items = [
            {"id": "1", "name": "Relay Module", "quantity": 5},
            {"id": "2", "name": "Relay Module", "quantity": 1},
        ]
        keeper = select_keeper(items)
        assert keeper["id"] == "1"


class TestCallHomebox(unittest.TestCase):
    @patch("subprocess.run")
    def test_calls_correct_script(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = call_homebox("list", homebox_script="./scripts/homebox.sh")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "./scripts/homebox.sh"
        assert args[1] == "list"


class TestMergeAndDelete(unittest.TestCase):
    @patch("homebox_dedup.call_homebox")
    def test_dry_run_skips_delete(self, mock_hb):
        items = [
            {"id": "keep-1", "name": "Foo", "quantity": 2},
            {"id": "del-1", "name": "Foo", "quantity": 1},
        ]
        merge_and_delete(items, dry_run=True)
        mock_hb.assert_not_called()

    @patch("homebox_dedup.call_homebox")
    def test_deletes_non_keepers(self, mock_hb):
        mock_hb.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        items = [
            {"id": "keep-1", "name": "Foo Bar Baz", "quantity": 1},
            {"id": "del-1", "name": "Foo Bar Baz", "quantity": 1},
            {"id": "del-2", "name": "Foo Bar Baz", "quantity": 1},
        ]
        merge_and_delete(items, dry_run=False)
        deleted = [c for c in mock_hb.call_args_list if c[0][0] == "delete"]
        assert len(deleted) == 2

    @patch("homebox_dedup.call_homebox")
    def test_updates_quantity_when_merging(self, mock_hb):
        mock_hb.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        items = [
            {"id": "keep-1", "name": "Foo Bar Baz", "quantity": 2},
            {"id": "del-1", "name": "Foo Bar Baz", "quantity": 3},
        ]
        merge_and_delete(items, dry_run=False, merge=True)
        update_calls = [c for c in mock_hb.call_args_list if c[0][0] == "update"]
        assert len(update_calls) == 1
        payload = json.loads(update_calls[0][0][2])
        assert payload["quantity"] == 5


if __name__ == "__main__":
    unittest.main()
