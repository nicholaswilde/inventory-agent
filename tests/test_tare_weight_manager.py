import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.tare_weight_manager import (
    parse_weight_grams,
    get_homebox_config,
    get_tags,
    ensure_tag_ids,
    find_container,
    upsert_container,
    fetch_tare_containers,
    generate_tare_sheet,
    main,
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


def test_get_homebox_config_env():
    with patch.dict(os.environ, {"HOMEBOX_IP": "192.168.1.100", "HOMEBOX_API_KEY": "secret"}):
        ip, key = get_homebox_config()
        assert ip == "192.168.1.100"
        assert key == "secret"


def test_get_homebox_config_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("HOMEBOX_IP=10.0.0.5\nHOMEBOX_API_KEY=testkey\n")
    with patch.dict(os.environ, {}, clear=True), patch("scripts.tare_weight_manager.Path") as mock_path:
        mock_path.return_value = env_file
        # Also handle Path(".env")
        mock_path.side_effect = lambda *args: env_file if args == (".env",) else Path(*args)
        ip, key = get_homebox_config()
        assert ip == "10.0.0.5"
        assert key == "testkey"


def test_get_tags():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"id": "t1", "name": "kitchen"}]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        tags = get_tags("http://homebox:7745/api/v1", {"Authorization": "Bearer x"})
        assert len(tags) == 1
        assert tags[0]["name"] == "kitchen"
        mock_get.assert_called_once()


def test_ensure_tag_ids_existing_and_created():
    existing_tags = [
        {"id": "tag-1", "name": "kitchen"},
        {"id": "tag-2", "name": "container"},
    ]
    with patch("scripts.tare_weight_manager.get_tags", return_value=existing_tags):
        mock_post = MagicMock()
        mock_post.status_code = 201
        mock_post.json.return_value = {"id": "tag-3", "name": "tare-weight"}
        with patch("requests.post", return_value=mock_post) as post_call:
            tag_ids = ensure_tag_ids(
                "http://homebox:7745/api/v1",
                {"Authorization": "Bearer x"},
                ["kitchen", "container", "tare-weight"],
            )
            assert "tag-1" in tag_ids
            assert "tag-2" in tag_ids
            assert "tag-3" in tag_ids
            post_call.assert_called_once()


def test_find_container_found():
    items = [
        {"id": "item-1", "name": "Pyrex 2-Cup Glass Measuring Cup"},
        {"id": "item-2", "name": "Stainless Steel Mixing Bowl"},
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": items}

    with patch("requests.get", return_value=mock_resp):
        found = find_container(
            "stainless steel mixing bowl",
            "http://homebox:7745/api/v1",
            {"Authorization": "Bearer x"},
        )
        assert found is not None
        assert found["id"] == "item-2"


def test_find_container_not_found():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}

    with patch("requests.get", return_value=mock_resp):
        found = find_container(
            "Nonexistent Container",
            "http://homebox:7745/api/v1",
            {"Authorization": "Bearer x"},
        )
        assert found is None


def test_upsert_container_create():
    with patch("scripts.tare_weight_manager.find_container", return_value=None), \
         patch("scripts.tare_weight_manager.ensure_tag_ids", return_value=["t1", "t2", "t3"]):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "new-id", "name": "Mason Jar 16oz"}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = upsert_container(
                "Mason Jar 16oz",
                250,
                "http://homebox:7745/api/v1",
                {"Authorization": "Bearer x"},
            )
            assert result["action"] == "created"
            assert result["id"] == "new-id"
            assert result["weight"] == 250

            args, kwargs = mock_post.call_args
            payload = kwargs["json"]
            assert payload["name"] == "Mason Jar 16oz"
            assert set(payload["tagIds"]) == {"t1", "t2", "t3"}
            assert payload["fields"] == [{"name": "Tare Weight (g)", "type": "number", "value": 250}]


def test_upsert_container_update():
    existing_item = {
        "id": "existing-1",
        "name": "Pyrex 2-Cup",
        "tagIds": ["t1", "old-tag"],
        "fields": [
            {"name": "Color", "type": "text", "value": "Clear"},
            {"name": "Tare Weight (g)", "type": "number", "value": 480},
        ],
    }

    with patch("scripts.tare_weight_manager.find_container", return_value=existing_item), \
         patch("scripts.tare_weight_manager.ensure_tag_ids", return_value=["t1", "t2", "t3"]):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "existing-1", "name": "Pyrex 2-Cup"}

        with patch("requests.put", return_value=mock_resp) as mock_put:
            result = upsert_container(
                "Pyrex 2-Cup",
                490,
                "http://homebox:7745/api/v1",
                {"Authorization": "Bearer x"},
            )
            assert result["action"] == "updated"
            assert result["id"] == "existing-1"
            assert result["weight"] == 490

            args, kwargs = mock_put.call_args
            payload = kwargs["json"]
            assert set(payload["tagIds"]) == {"t1", "old-tag", "t2", "t3"}
            # Field value updated, and existing fields preserved
            tare_field = next(f for f in payload["fields"] if f["name"] == "Tare Weight (g)")
            assert tare_field["value"] == 490
            color_field = next(f for f in payload["fields"] if f["name"] == "Color")
            assert color_field["value"] == "Clear"


def test_fetch_tare_containers():
    tags = [
        {"id": "t-tare", "name": "tare-weight"},
    ]
    entities = [
        {
            "id": "c1",
            "name": "Pyrex 2-Cup",
            "tagIds": ["t-tare"],
            "fields": [{"name": "Tare Weight (g)", "value": 490}],
        },
        {
            "id": "c2",
            "name": "Other Item",
            "tagIds": ["t-other"],
            "fields": [],
        },
        {
            "id": "c3",
            "name": "Mason Jar 16oz",
            "tags": [{"name": "tare-weight"}],
            "fields": [{"name": "Tare Weight (g)", "value": 250}],
        },
    ]

    with patch("scripts.tare_weight_manager.get_tags", return_value=tags):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"items": entities}

        with patch("requests.get", return_value=mock_resp):
            containers = fetch_tare_containers("http://homebox:7745/api/v1", {"Authorization": "Bearer x"})
            assert len(containers) == 2
            names = [c["name"] for c in containers]
            assert "Pyrex 2-Cup" in names
            assert "Mason Jar 16oz" in names


def test_generate_tare_sheet():
    containers = [
        {"name": "Stainless Steel Bowl", "weight": 310},
        {"name": "Borosilicate Glass Dish", "weight": 520},
        {"name": "Pyrex 2-Cup", "weight": 490},
    ]
    sheet = generate_tare_sheet(containers)
    expected = (
        "| Container / Item | Tare Weight (g) |\n"
        "| :--- | :--- |\n"
        "| Borosilicate Glass Dish | 520 |\n"
        "| Pyrex 2-Cup | 490 |\n"
        "| Stainless Steel Bowl | 310 |"
    )
    assert sheet.strip() == expected


def test_generate_tare_sheet_empty():
    sheet = generate_tare_sheet([])
    expected = (
        "| Container / Item | Tare Weight (g) |\n"
        "| :--- | :--- |"
    )
    assert sheet.strip() == expected


def test_cli_upsert(capsys):
    with patch("scripts.tare_weight_manager.get_homebox_config", return_value=("localhost", "key")), \
         patch("scripts.tare_weight_manager.upsert_container", return_value={"action": "created", "id": "123", "name": "Jar", "weight": 200}):
        main(["upsert", "Jar", "200"])
        captured = capsys.readouterr()
        assert "created" in captured.out
        assert "Jar" in captured.out


def test_cli_sheet(capsys):
    containers = [{"name": "Jar", "weight": 200}]
    with patch("scripts.tare_weight_manager.get_homebox_config", return_value=("localhost", "key")), \
         patch("scripts.tare_weight_manager.fetch_tare_containers", return_value=containers):
        main(["sheet"])
        captured = capsys.readouterr()
        assert "| Container / Item | Tare Weight (g) |" in captured.out
        assert "| Jar | 200 |" in captured.out


def test_cli_show(capsys):
    containers = [{"name": "Jar", "weight": 200}]
    with patch("scripts.tare_weight_manager.get_homebox_config", return_value=("localhost", "key")), \
         patch("scripts.tare_weight_manager.fetch_tare_containers", return_value=containers):
        main(["show"])
        captured = capsys.readouterr()
        assert "| Container / Item | Tare Weight (g) |" in captured.out
        assert "| Jar | 200 |" in captured.out

