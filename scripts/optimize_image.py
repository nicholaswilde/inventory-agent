"""
Image Optimization & Compression Pipeline.
Resizes and compresses images in-place or into a specified output directory using ImageMagick,
ensuring assets are web-friendly (< 500KB and max 1920x1080 resolution) before attachment.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".heic"}


def get_magick_command() -> list[str]:
    """Find available ImageMagick CLI binary."""
    if shutil.which("magick"):
        return ["magick"]
    if shutil.which("convert"):
        return ["convert"]
    raise FileNotFoundError("ImageMagick ('magick' or 'convert') is not installed or not in PATH.")


def get_image_dimensions(image_path: Path | str) -> tuple[int, int]:
    """Return (width, height) of an image using ImageMagick identify."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    magick = get_magick_command()
    cmd = magick + ["identify", "-format", "%w %h", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    parts = proc.stdout.strip().split()
    if len(parts) >= 2:
        return int(parts[0]), int(parts[1])
    raise ValueError(f"Could not parse dimensions from output: {proc.stdout}")


def parse_max_dimensions(dim_str: str) -> tuple[int, int]:
    """Parse '1920x1080' string into (1920, 1080)."""
    parts = dim_str.lower().split("x")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    if len(parts) == 1 and parts[0].isdigit():
        return int(parts[0]), int(parts[0])
    return 1920, 1080


def optimize_image(
    input_path: Path | str,
    output_path: Path | str | None = None,
    max_size_kb: int = 500,
    max_dimension: str = "1920x1080",
    quality: int = 85,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Optimize and compress a single image.
    If output_path is None, modifies in-place.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Image file not found: {src}")

    if src.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {src.suffix}")

    dest = Path(output_path) if output_path else src
    original_size = src.stat().st_size
    max_bytes = max_size_kb * 1024
    max_w, max_h = parse_max_dimensions(max_dimension)

    w, h = get_image_dimensions(src)
    already_optimal = (original_size <= max_bytes) and (w <= max_w) and (h <= max_h)

    # Use a temporary destination to build the optimized version
    temp_dest = dest.parent / f".tmp_{src.stem}_{os.getpid()}{src.suffix}"
    temp_dest.parent.mkdir(parents=True, exist_ok=True)

    magick = get_magick_command()
    cmd = [
        *magick,
        str(src),
        "-strip",
        "-resize", f"{max_dimension}>",
        "-quality", str(quality),
    ]

    if src.suffix.lower() in {".jpg", ".jpeg"}:
        cmd.extend(["-define", f"jpeg:extent={max_size_kb}KB"])

    cmd.append(str(temp_dest))

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        optimized_size = temp_dest.stat().st_size

        if optimized_size >= original_size and already_optimal:
            optimized_size = original_size
            modified = False
        else:
            modified = True

        savings_bytes = max(0, original_size - optimized_size)
        savings_percent = round((savings_bytes / original_size) * 100, 2) if original_size > 0 else 0.0

        if not dry_run and modified:
            shutil.move(temp_dest, dest)
        elif not dry_run and not modified and dest != src:
            shutil.copy2(src, dest)

        return {
            "path": str(dest),
            "original_size": original_size,
            "optimized_size": optimized_size,
            "savings_bytes": savings_bytes,
            "savings_percent": savings_percent,
            "modified": modified,
            "dry_run": dry_run,
        }
    finally:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)


def optimize_directory(
    dir_path: Path | str,
    max_size_kb: int = 500,
    max_dimension: str = "1920x1080",
    quality: int = 85,
    recursive: bool = True,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Scan directory and optimize all supported images."""
    p = Path(dir_path)
    if not p.is_dir():
        return []

    pattern = "**/*" if recursive else "*"
    images = [
        f for f in p.glob(pattern)
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    results = []
    for img in sorted(images):
        try:
            res = optimize_image(
                img,
                max_size_kb=max_size_kb,
                max_dimension=max_dimension,
                quality=quality,
                dry_run=dry_run,
            )
            results.append(res)
        except Exception as e:
            print(f"Error optimizing {img}: {e}", file=sys.stderr)

    return results


def format_bytes(b: int) -> str:
    """Format bytes into readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024 or unit == "GB":
            return f"{b:.1f} {unit}" if unit != "B" else f"{b} B"
        b /= 1024
    return f"{b:.1f} GB"


def main():
    parser = argparse.ArgumentParser(
        description="Optimize and compress images for HomeBox (< 500KB, max 1920x1080)."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["images/pending", "images/processed"],
        help="Directories or image files to optimize (default: images/pending and images/processed)",
    )
    parser.add_argument(
        "--max-size-kb", "-s",
        type=int,
        default=500,
        help="Maximum file size in KB (default: 500)",
    )
    parser.add_argument(
        "--max-dimension", "-d",
        default="1920x1080",
        help="Maximum width x height bounding box (default: 1920x1080)",
    )
    parser.add_argument(
        "--quality", "-q",
        type=int,
        default=85,
        help="Target JPEG quality (default: 85)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview savings without altering files on disk",
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Optional destination directory for optimized files (default: in-place)",
    )

    args = parser.parse_args()

    all_results: list[dict[str, Any]] = []

    for target_str in args.targets:
        target = Path(target_str)
        if not target.exists():
            continue

        if target.is_dir():
            res = optimize_directory(
                target,
                max_size_kb=args.max_size_kb,
                max_dimension=args.max_dimension,
                quality=args.quality,
                dry_run=args.dry_run,
            )
            all_results.extend(res)
        elif target.is_file() and target.suffix.lower() in SUPPORTED_EXTENSIONS:
            out = None
            if args.output_dir:
                out = Path(args.output_dir) / target.name
            try:
                res = optimize_image(
                    target,
                    output_path=out,
                    max_size_kb=args.max_size_kb,
                    max_dimension=args.max_dimension,
                    quality=args.quality,
                    dry_run=args.dry_run,
                )
                all_results.append(res)
            except Exception as e:
                print(f"Error optimizing {target}: {e}", file=sys.stderr)

    if not all_results:
        print("No images found to optimize.")
        return

    total_orig = sum(r["original_size"] for r in all_results)
    total_opt = sum(r["optimized_size"] for r in all_results)
    total_saved = max(0, total_orig - total_opt)
    percent_saved = round((total_saved / total_orig) * 100, 2) if total_orig > 0 else 0.0
    modified_count = sum(1 for r in all_results if r["modified"])

    action_label = "[DRY RUN] Would optimize" if args.dry_run else "Optimized"
    print(f"\n{action_label} {len(all_results)} images ({modified_count} modified):")
    for r in all_results:
        status = "modified" if r["modified"] else "optimal"
        print(
            f"  - {Path(r['path']).name}: {format_bytes(r['original_size'])} -> "
            f"{format_bytes(r['optimized_size'])} (-{r['savings_percent']}%) [{status}]"
        )

    print("\nSummary:")
    print(f"  Total Original:  {format_bytes(total_orig)}")
    print(f"  Total Optimized: {format_bytes(total_opt)}")
    print(f"  Total Saved:     {format_bytes(total_saved)} ({percent_saved}%)")


if __name__ == "__main__":
    main()
