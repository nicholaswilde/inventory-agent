from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.optimize_image import (
    get_image_dimensions,
    optimize_image,
    optimize_directory,
    main,
    SUPPORTED_EXTENSIONS,
)


@pytest.fixture
def sample_large_image(tmp_path: Path) -> Path:
    """Create a high-resolution, noisy image using ImageMagick."""
    img_path = tmp_path / "large_photo.jpg"
    # Create 2000x1200 image with fractal noise to ensure high file size
    subprocess.run(
        ["magick", "-size", "2000x1200", "plasma:fractal", str(img_path)],
        check=True,
    )
    return img_path


@pytest.fixture
def sample_small_image(tmp_path: Path) -> Path:
    """Create a small 200x200 low-size image."""
    img_path = tmp_path / "small_icon.png"
    subprocess.run(
        ["magick", "-size", "200x200", "xc:blue", str(img_path)],
        check=True,
    )
    return img_path


def test_get_image_dimensions(sample_large_image: Path):
    w, h = get_image_dimensions(sample_large_image)
    assert w == 2000
    assert h == 1200


def test_optimize_image_resizes_and_compresses(sample_large_image: Path):
    original_size = sample_large_image.stat().st_size
    assert original_size > 500 * 1024  # ensure starting > 500KB

    res = optimize_image(
        sample_large_image,
        max_size_kb=500,
        max_dimension="1920x1080",
        quality=85,
    )

    assert res["modified"] is True
    assert res["original_size"] == original_size
    assert res["optimized_size"] <= 500 * 1024
    assert res["optimized_size"] < original_size
    assert res["savings_bytes"] > 0
    assert res["savings_percent"] > 0

    w, h = get_image_dimensions(sample_large_image)
    assert w <= 1920
    assert h <= 1080


def test_optimize_image_dry_run(sample_large_image: Path):
    original_size = sample_large_image.stat().st_size
    res = optimize_image(
        sample_large_image,
        max_size_kb=500,
        max_dimension="1920x1080",
        dry_run=True,
    )

    assert res["dry_run"] is True
    # File on disk should remain untouched
    assert sample_large_image.stat().st_size == original_size
    assert res["optimized_size"] <= 500 * 1024


def test_optimize_image_to_separate_output_path(sample_large_image: Path, tmp_path: Path):
    dest = tmp_path / "output_optimized.jpg"
    res = optimize_image(
        sample_large_image,
        output_path=dest,
        max_size_kb=500,
        max_dimension="1920x1080",
    )

    assert dest.exists()
    assert dest.stat().st_size <= 500 * 1024
    assert sample_large_image.stat().st_size > dest.stat().st_size


def test_optimize_image_already_optimal(sample_small_image: Path):
    original_size = sample_small_image.stat().st_size
    res = optimize_image(
        sample_small_image,
        max_size_kb=500,
        max_dimension="1920x1080",
    )
    # Small image below 500KB and within 1920x1080
    assert sample_small_image.stat().st_size <= 500 * 1024
    w, h = get_image_dimensions(sample_small_image)
    assert w <= 1920
    assert h <= 1080


def test_optimize_directory(tmp_path: Path):
    img_dir = tmp_path / "batch_images"
    img_dir.mkdir()

    # Create two images and one non-image
    img1 = img_dir / "img1.jpg"
    img2 = img_dir / "img2.png"
    txt = img_dir / "readme.txt"
    txt.write_text("not an image")

    subprocess.run(["magick", "-size", "2000x1200", "plasma:fractal", str(img1)], check=True)
    subprocess.run(["magick", "-size", "150x150", "xc:red", str(img2)], check=True)

    results = optimize_directory(img_dir, max_size_kb=500, max_dimension="1920x1080")
    assert len(results) == 2
    assert any(r["path"] == str(img1) for r in results)
    assert any(r["path"] == str(img2) for r in results)


def test_optimize_directory_non_existent():
    results = optimize_directory(Path("/non/existent/directory"))
    assert results == []


def test_cli_execution(tmp_path: Path):
    test_dir = tmp_path / "cli_test"
    test_dir.mkdir()
    img = test_dir / "test.jpg"
    subprocess.run(["magick", "-size", "2000x1200", "plasma:fractal", str(img)], check=True)

    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent.parent / "scripts" / "optimize_image.py"),
        str(test_dir),
        "--max-size-kb", "400",
        "--max-dimension", "1600x900",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Optimized" in proc.stdout or "Summary" in proc.stdout
    assert img.stat().st_size <= 400 * 1024
