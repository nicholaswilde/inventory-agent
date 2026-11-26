import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.tare_weight_manager import (
    REQUIRED_TAGS,
    TARE_FIELD_NAME,
    main,
    parse_weight_grams,
    render_tare_sheet,
    upsert_container,
)


def test_parse_weight_grams():
    assert parse_weight_grams(250) == 250
    assert parse_weight_grams("250") == 250
    assert parse_weight_grams("250g") == 250
    assert parse_weight_grams("250 G") == 250
    assert parse_weight_grams("250.0") == 250
    assert parse_weight_grams(" 490 g ") == 490

    with pytest.raises(ValueError):
        parse_weight_grams("invalid")
    with pytest.raises(ValueError):
        parse_weight_grams(-10)


def test_upsert_container_calls_hbctl():
    with patch(
        "scripts.tare_weight_manager.hbctl_client.upsert_item",
        return_value={"id": "new-id", "name": "Mason Jar 16oz", "action": "created"},
    ) as mock_upsert:
        result = upsert_container(" Mason Jar 16oz ", "250g")
        assert result == {
            "action": "created",
            "id": "new-id",
            "name": "Mason Jar 16oz",
            "weight": 250,
        }
        mock_upsert.assert_called_once_with(
            "Mason Jar 16oz",
            tags=REQUIRED_TAGS,
            fields=[(TARE_FIELD_NAME, 250)],
            field_type="number",
        )

    with patch(
        "scripts.tare_weight_manager.hbctl_client.upsert_item",
        return_value={"id": "existing-id", "name": "Mason Jar 16oz"},
    ):
        result_fallback = upsert_container("Mason Jar 16oz", 250)
        assert result_fallback["action"] == "upserted"


def test_render_tare_sheet_uses_hbctl_export():
    table = (
        "| Container / Item | Tare Weight (g) |\n"
        "| :--- | :--- |\n"
        "| Borosilicate Glass Dish | 520 |\n"
        "| Pyrex 2-Cup | 490 |\n"
        "| Unweighed Jar | - |"
    )
    with patch("scripts.tare_weight_manager.hbctl_client.export_markdown", return_value=table) as mock_export:
        sheet = render_tare_sheet()
        mock_export.assert_called_once_with(
            tag="tare-weight",
            columns=["name=Container / Item", TARE_FIELD_NAME],
            align="left",
            empty="-",
            sort="name",
        )
        assert sheet == table


def test_cli_upsert(capsys):
    with patch(
        "scripts.tare_weight_manager.upsert_container",
        return_value={"action": "created", "id": "123", "name": "Jar", "weight": 200},
    ):
        main(["upsert", "Jar", "200"])
        captured = capsys.readouterr()
        assert "created" in captured.out
        assert "Jar" in captured.out


def test_cli_sheet(capsys):
    table = "| Container / Item | Tare Weight (g) |\n| :--- | :--- |\n| Jar | 200 |"
    with patch("scripts.tare_weight_manager.render_tare_sheet", return_value=table):
        main(["sheet"])
        captured = capsys.readouterr()
        assert "| Container / Item | Tare Weight (g) |" in captured.out
        assert "| Jar | 200 |" in captured.out


def test_cli_show(capsys):
    table = "| Container / Item | Tare Weight (g) |\n| :--- | :--- |\n| Jar | 200 |"
    with patch("scripts.tare_weight_manager.render_tare_sheet", return_value=table):
        main(["show"])
        captured = capsys.readouterr()
        assert "| Container / Item | Tare Weight (g) |" in captured.out
        assert "| Jar | 200 |" in captured.out
