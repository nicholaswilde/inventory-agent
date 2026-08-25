"""
Electronic Component Vision Automation Pipeline.
Processes pending component images using local OCR and Gemini Vision fallback,
integrating with HomeBox inventory.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

ELECTRONIC_KEYWORDS = {
    "sensor", "module", "controller", "regulator", "display", "transceiver",
    "relay", "driver", "opamp", "board", "voltage", "converter", "microcontroller",
    "timer", "breakout", "uart", "i2c", "spi", "shield", "arduino", "esp32", "esp8266",
    "charger", "lipo", "humidity", "temp", "temperature", "ftdi", "serial", "ttl",
    "step-down", "step-up", "buck", "boost", "featherwing", "adafruit", "sensirion", "ky", "hw"
}

PART_NUMBER_PATTERN = re.compile(
    r"\b(?=[A-Z0-9_.-]*[A-Z])(?=[A-Z0-9_.-]*\d)(?:(?:[A-Z0-9]+[-_.])+[A-Z0-9]+|[A-Z]{2,}\d{2,}[A-Z0-9]*|(?:ESP|DHT|SHT|STM32|ATmega|CH340|AMS1117|NE555|TP4056|LM\d+|MAX\d+|HW|KY)[A-Z0-9_.-]*)\b",
    re.IGNORECASE,
)


def scan_image_queue(pending_dir: Path | str) -> list[Path]:
    """Scan directory for valid image files, ignoring dotfiles, non-images, and subdirectories."""
    pending_path = Path(pending_dir)
    if not pending_path.is_dir():
        return []

    images = []
    for entry in pending_path.iterdir():
        if entry.is_file() and not entry.name.startswith("."):
            if entry.suffix.lower() in VALID_IMAGE_EXTENSIONS:
                images.append(entry)

    return sorted(images, key=lambda p: p.name)


def run_local_ocr(image_path: Path | str) -> str:
    """Execute local OCR using lit and extract meaningful text lines, with tesseract fallback."""
    # 1. Attempt lit parse
    try:
        proc = subprocess.run(
            ["lit", "parse", str(image_path), "--quiet"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            lines = []
            for line in proc.stdout.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("--- Page") or line_str.startswith("[liteparse]"):
                    continue
                lines.append(line_str)
            extracted = "\n".join(lines).strip()
            if extracted:
                return extracted
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 2. Fallback to tesseract standard
    try:
        proc = subprocess.run(
            ["tesseract", str(image_path), "stdout"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            lines = []
            for line in proc.stdout.splitlines():
                line_str = line.strip()
                if not line_str or line_str.startswith("--- Page") or line_str.startswith("[liteparse]"):
                    continue
                lines.append(line_str)
            extracted = "\n".join(lines).strip()
            if extracted:
                return extracted
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 3. Fallback to tesseract sparse/macro text (psm 11)
    try:
        proc = subprocess.run(
            ["tesseract", str(image_path), "stdout", "--psm", "11"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            lines = []
            for line in proc.stdout.splitlines():
                line_str = line.strip()
                if not line_str or line_str.startswith("--- Page") or line_str.startswith("[liteparse]"):
                    continue
                lines.append(line_str)
            extracted = "\n".join(lines).strip()
            if extracted:
                return extracted
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return ""



ocr_image = run_local_ocr


def is_ocr_meaningful(ocr_text: str) -> bool:
    """Heuristic analyzer determining if extracted OCR text is valid electronic component metadata."""
    if not ocr_text or not ocr_text.strip():
        return False

    cleaned = ocr_text.strip()
    # Strip metadata markers
    cleaned_lines = [
        line for line in cleaned.splitlines()
        if not line.startswith("--- Page") and not line.startswith("[liteparse]")
    ]
    cleaned = "\n".join(cleaned_lines).strip()
    if not cleaned:
        return False

    # Stage 1: Length check
    alnum_chars = [c for c in cleaned if c.isalnum()]
    if len(alnum_chars) < 6:
        return False

    # Stage 2: Noise Ratio check
    non_ws_chars = [c for c in cleaned if not c.isspace()]
    if not non_ws_chars:
        return False
    non_alnum_chars = [c for c in non_ws_chars if not c.isalnum() and c not in "-_."]
    noise_ratio = len(non_alnum_chars) / len(non_ws_chars)
    if noise_ratio > 0.40:
        return False

    # Stage 3: Token length check
    words = re.findall(r"[A-Za-z0-9_-]+", cleaned)
    valid_tokens = [w for w in words if len(re.sub(r"[^A-Za-z0-9]", "", w)) >= 3]
    if not valid_tokens:
        return False

    # Stage 4: Domain matching
    cleaned_lower = cleaned.lower()
    has_keyword = any(
        re.search(rf"\b{re.escape(kw)}\b", cleaned_lower) for kw in ELECTRONIC_KEYWORDS
    )
    has_part_number = bool(PART_NUMBER_PATTERN.search(cleaned))

    return has_keyword or has_part_number


def load_gemini_api_key(api_key: str | None = None) -> str | None:
    """Load GEMINI_API_KEY from parameter, environment, or .env file."""
    if api_key:
        return api_key
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]

    search_paths = [
        Path(".env"),
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for env_path in search_paths:
        if env_path.is_file():
            try:
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("#") or not line or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k == "GEMINI_API_KEY" and v:
                        os.environ["GEMINI_API_KEY"] = v
                        return v
            except OSError:
                pass
    return None


GEMINI_MODELS = ["models/gemini-3.5-flash", "models/gemini-3.1-flash-lite", "models/gemini-2.5-flash"]


def query_gemini_vision(
    image_path: Path | str,
    api_key: str | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    models: list[str] | None = None,
) -> dict[str, Any]:
    """Identify electronic component using Google Gemini Vision API with fallback models."""
    key = load_gemini_api_key(api_key)
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in environment or arguments.")

    img_path = Path(image_path)
    if not img_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image_bytes = img_path.read_bytes()
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    mime_type = "image/jpeg"
    if img_path.suffix.lower() == ".png":
        mime_type = "image/png"

    prompt = (
        "Identify the electronic component or module in this image. "
        "Return a JSON object with keys: "
        "'name' (string, required), 'manufacturer' (string, optional), "
        "'modelNumber' (string, optional), 'description' (string, required), "
        "'quantity' (integer, default 1), 'notes' (string, optional), 'tags' (list of strings, optional)."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data,
                        }
                    },
                ]
            }
        ]
    }

    model_list = models or GEMINI_MODELS
    last_error: Exception | None = None

    for model_name in model_list:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={key}"
        for attempt in range(max_retries):
            resp: requests.Response | None = None
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 429:
                    if attempt < max_retries - 1:
                        sleep_time = retry_delay * (2 ** attempt)
                        time.sleep(sleep_time)
                        continue
                    resp.raise_for_status()
                elif resp.status_code in (400, 403, 404) and len(model_list) > 1:
                    # Model not available/supported, fall back to next model
                    break
                elif resp.status_code >= 500:
                    if attempt < max_retries - 1:
                        sleep_time = retry_delay * (2 ** attempt)
                        time.sleep(sleep_time)
                        continue
                    resp.raise_for_status()
                else:
                    resp.raise_for_status()

                data = resp.json()
                if "promptFeedback" in data and data["promptFeedback"].get("blockReason"):
                    raise RuntimeError(f"Prompt blocked by Gemini: {data['promptFeedback']['blockReason']}")

                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError("No candidates returned from Gemini Vision API")

                part_text = candidates[0]["content"]["parts"][0]["text"]
                # Clean markdown code fences if present
                cleaned_text = part_text.strip()
                if cleaned_text.startswith("```"):
                    cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
                    cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

                parsed = json.loads(cleaned_text.strip())
                if not isinstance(parsed, dict) or "name" not in parsed:
                    raise ValueError(f"Invalid component schema from Gemini: {parsed}")
                return parsed

            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                else:
                    break

    if last_error:
        raise last_error
    raise RuntimeError("Failed to query Gemini Vision API across all models")


call_gemini_vision = query_gemini_vision


def call_homebox(
    subcommand: str,
    *args: str,
    homebox_script: Path | str | None = None,
) -> subprocess.CompletedProcess:
    """Invoke ./scripts/homebox.sh subprocess wrapper."""
    if homebox_script is None:
        script_path = Path(__file__).resolve().parent / "homebox.sh"
        if not script_path.exists():
            script_path = Path("./scripts/homebox.sh")
    else:
        script_path = Path(homebox_script)

    cmd = [str(script_path), subcommand, *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def search_entity(query: str, homebox_script: Path | str | None = None) -> str | None:
    """Search HomeBox for entity matching query. Returns entity UUID if found, else None."""
    if not query:
        return None
    q = query.strip()
    if len(q) < 3 or not any(c.isalpha() for c in q):
        return None

    proc = call_homebox("search", q, homebox_script=homebox_script)
    if proc.returncode != 0 or not proc.stdout:
        return None

    for line in proc.stdout.splitlines():
        match = re.search(r"ID:\s*([^\s|]+)", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def create_entity(
    component_data: dict[str, Any],
    homebox_script: Path | str | None = None,
) -> str:
    """Create new entity in HomeBox. Returns entity UUID on success, raises RuntimeError on failure."""
    sanitized = dict(component_data)
    if "description" in sanitized and isinstance(sanitized["description"], str):
        sanitized["description"] = sanitized["description"][:250].strip()
    if "name" in sanitized and isinstance(sanitized["name"], str):
        sanitized["name"] = sanitized["name"][:100].strip()
    json_payload = json.dumps(sanitized)
    proc = call_homebox("create", json_payload, homebox_script=homebox_script)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to create HomeBox entity: {proc.stderr or proc.stdout}")

    try:
        resp = json.loads(proc.stdout)
        entity_id = resp.get("id")
        if not entity_id:
            raise ValueError(f"No id field in create response: {proc.stdout}")
        return str(entity_id)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON response from homebox create: {proc.stdout}") from e


def attach_image(
    entity_id: str,
    image_path: Path | str,
    homebox_script: Path | str | None = None,
) -> bool:
    """Attach image file to HomeBox entity."""
    proc = call_homebox("attach", entity_id, str(image_path), homebox_script=homebox_script)
    return proc.returncode == 0


def move_to_processed(image_path: Path | str, processed_dir: Path | str) -> Path:
    """Move image atomically to processed directory."""
    src = Path(image_path)
    dest_dir = Path(processed_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / src.name
    shutil.move(str(src), str(dest_file))
    return dest_file


def identify_component(
    image_path: Path | str,
    api_key: str | None = None,
) -> dict[str, Any] | None:
    """Identify component via Gemini Vision API first, falling back to local OCR."""
    # Always try Gemini Vision first — macro photos of electronics are too noisy for OCR alone
    try:
        gemini_res = query_gemini_vision(image_path, api_key=api_key)
        if gemini_res:
            return gemini_res
    except Exception:
        pass

    # Fallback: local OCR if Gemini is unavailable or fails
    ocr_text = run_local_ocr(image_path)
    stem = Path(image_path).stem

    if is_ocr_meaningful(ocr_text):
        best_line = None
        best_score = -1

        for line in ocr_text.splitlines():
            line_str = re.sub(r"[|\\~^_©®«»“”\[\]{}<>*?`]+", " ", line)
            line_str = re.sub(r"\s+", " ", line_str).strip()
            if line_str.startswith("--- Page") or line_str.startswith("[liteparse]"):
                continue
            if len(line_str) < 4:
                continue

            has_pn = bool(PART_NUMBER_PATTERN.search(line_str))
            has_kw = bool(
                any(
                    re.search(rf"\b{re.escape(kw)}\b", line_str.lower())
                    for kw in ELECTRONIC_KEYWORDS
                )
            )

            score = 0
            if has_pn and has_kw:
                score = 3
            elif has_pn or has_kw:
                score = 2

            if score > best_score:
                best_score = score
                best_line = line_str

        if best_line and best_score >= 2:
            component: dict[str, Any] = {
                "name": best_line,
                "description": ocr_text,
                "quantity": 1,
            }
            pn_match = PART_NUMBER_PATTERN.search(best_line) or PART_NUMBER_PATTERN.search(ocr_text)
            if pn_match:
                component["modelNumber"] = pn_match.group(0)
            return component

    # Last resort: filename-based fallback
    clean_lines = [
        re.sub(r"[|\\~^_©®«»“”\[\]{}<>*?`]+", " ", line).strip()
        for line in ocr_text.splitlines()
        if not line.startswith("---") and not line.startswith("[lite")
    ]
    meaningful_lines = [l for l in clean_lines if len(l) >= 4 and any(c.isalnum() for c in l)]
    name = meaningful_lines[0] if meaningful_lines else f"Electronic Component ({stem})"

    comp: dict[str, Any] = {
        "name": name,
        "description": ocr_text.strip() or f"Electronic component from {stem}",
        "quantity": 1,
    }
    pn_match = PART_NUMBER_PATTERN.search(name) or PART_NUMBER_PATTERN.search(ocr_text)
    if pn_match:
        comp["modelNumber"] = pn_match.group(0)
    return comp


def process_single_image(
    image_path: Path | str,
    processed_dir: Path | str,
    dry_run: bool = False,
    homebox_script: Path | str | None = None,
    api_key: str | None = None,
) -> bool:
    """Process a single image through identification, duplicate check, creation, attachment, and moving."""
    img_path = Path(image_path)
    if not img_path.is_file():
        print(f"[-] Image not found: {image_path}")
        return False

    print(f"[*] Processing {img_path.name}...")
    comp = identify_component(img_path, api_key=api_key)
    if not comp:
        print(f"  [-] Failed to identify component for {img_path.name}")
        return False

    name = comp.get("name", "Unknown")
    model = comp.get("modelNumber", "")
    print(f"  [+] Identified: {name} (Model: {model})")

    search_query = comp.get("modelNumber") or comp.get("name") or img_path.stem
    entity_id = search_entity(search_query, homebox_script=homebox_script)

    if entity_id:
        print(f"  [i] Found existing HomeBox entity: {entity_id} for query '{search_query}'")
        # Duplicate found: attach and move
        if not dry_run:
            if not attach_image(entity_id, img_path, homebox_script=homebox_script):
                print(f"  [-] Failed to attach {img_path.name} to entity {entity_id}")
                return False
            move_to_processed(img_path, processed_dir)
            print(f"  [+] Attached {img_path.name} to {entity_id} and moved to {processed_dir}")
        else:
            print(f"  [DRY-RUN] Would attach {img_path.name} to {entity_id} and move to {processed_dir}")
        return True
    else:
        print(f"  [i] No existing entity found. Creating new entity: {name}")
        # New entity
        if not dry_run:
            try:
                entity_id = create_entity(comp, homebox_script=homebox_script)
                print(f"  [+] Created entity with ID: {entity_id}")
            except Exception as e:
                print(f"  [-] Failed to create entity: {e}")
                return False
            if not attach_image(entity_id, img_path, homebox_script=homebox_script):
                print(f"  [-] Failed to attach image to new entity {entity_id}")
                return False
            move_to_processed(img_path, processed_dir)
            print(f"  [+] Attached {img_path.name} and moved to {processed_dir}")
        else:
            print(f"  [DRY-RUN] Would create entity '{name}', attach {img_path.name}, and move to {processed_dir}")
        return True


def process_all_images(
    pending_dir: Path | str = "images/pending",
    processed_dir: Path | str = "images/processed",
    dry_run: bool = False,
    homebox_script: Path | str | None = None,
    api_key: str | None = None,
) -> dict[str, int]:
    """Scan and process all pending images in batch."""
    pending_images = scan_image_queue(pending_dir)
    total = len(pending_images)
    print(f"[*] Found {total} image(s) in {pending_dir} (dry_run={dry_run})")

    succeeded = 0
    failed = 0

    for idx, img in enumerate(pending_images, 1):
        print(f"--- [{idx}/{total}] ---")
        ok = process_single_image(
            img,
            processed_dir=processed_dir,
            dry_run=dry_run,
            homebox_script=homebox_script,
            api_key=api_key,
        )
        if ok:
            succeeded += 1
        else:
            failed += 1

    print(f"[*] Batch summary: {succeeded} succeeded, {failed} failed out of {total} total.")
    return {"total": total, "succeeded": succeeded, "failed": failed}


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Process electronic component images.")
    parser.add_argument(
        "--pending-dir",
        type=str,
        default="images/pending",
        help="Directory containing pending images (default: images/pending)",
    )
    parser.add_argument(
        "--processed-dir",
        type=str,
        default="images/processed",
        help="Directory to move processed images to (default: images/processed)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform scanning and identification without mutating HomeBox or moving files",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Gemini API Key (optional, defaults to GEMINI_API_KEY environment variable)",
    )
    return parser.parse_args(args)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    args = parse_args(argv)
    res = process_all_images(
        pending_dir=args.pending_dir,
        processed_dir=args.processed_dir,
        dry_run=args.dry_run,
        api_key=args.api_key,
    )
    if res["failed"] > 0 and res["succeeded"] == 0 and res["total"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
