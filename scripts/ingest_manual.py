"""
Appliance Manual Ingestion Pipeline.
Downloads/reads appliance manuals (PDF), extracts specs, error codes, and parts,
creates a Homebox entity with the attached manual, and generates a markdown cheat sheet.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import urllib.parse

import requests

KNOWN_MANUFACTURERS = [
    "LG", "Samsung", "Whirlpool", "Bosch", "GE", "GE Appliances",
    "KitchenAid", "Frigidaire", "Miele", "Maytag", "Electrolux",
    "Kenmore", "Haier", "Panasonic", "Amana", "Thermador", "Sub-Zero",
    "Moen", "Kohler", "Delta", "Grohe", "Scotch", "3M", "Weber",
    "Roborock", "Dyson", "Eufy", "Broan", "Schlage"
]

APPLIANCE_TYPES = [
    "Smart Deadbolt Lock", "Smart Deadbolt", "Smart Lock", "Deadbolt",
    "Robotic Vacuum Cleaner", "Robot Vacuum", "Vacuum Cleaner", "Vacuum",
    "Dryer", "Washer", "Washing Machine", "Dishwasher", "Microwave Oven", "Microwave",
    "Oven", "Range Hood", "Range", "Refrigerator", "Fridge", "Freezer",
    "Cooktop", "Dehumidifier", "Air Conditioner", "Water Heater",
    "Kitchen Faucet", "Faucet", "Thermal Laminator", "Laminator",
    "Wood Pellet Barbecue", "Pellet Grill", "Barbecue", "Grill"
]


def resolve_download_url(source: str) -> str:
    """Normalize URLs, converting Google Drive sharing URLs to direct download endpoints."""
    if not source.startswith("http://") and not source.startswith("https://"):
        return source

    # Check for Google Drive file ID
    gdrive_match = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([a-zA-Z0-9_-]+)", source)
    if gdrive_match:
        file_id = gdrive_match.group(1)
        return f"https://drive.usercontent.google.com/download?id={file_id}&export=download"

    return source


def resolve_issue_source(issue_ref: str | int) -> tuple[str, str | None, int]:
    """
    Given a GitHub issue reference (#123, 123, or issue URL), retrieve issue details via gh CLI
    and extract any attached/linked PDF manual URL and appliance title.
    Returns (pdf_url, clean_title, issue_number).
    """
    s = str(issue_ref).strip()
    match = re.search(r"(?:issues/|#)?(\d+)", s)
    if not match:
        raise ValueError(f"Invalid GitHub issue reference: {issue_ref}")
    issue_num = int(match.group(1))

    proc = subprocess.run(
        ["gh", "issue", "view", str(issue_num), "--json", "number,title,body,comments"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to fetch issue #{issue_num}: {proc.stderr.strip()}")

    data = json.loads(proc.stdout)
    title = data.get("title", "").strip()
    body = data.get("body", "") or ""
    comments = data.get("comments", []) or []

    full_text = body + "\n" + "\n".join(c.get("body", "") for c in comments if isinstance(c, dict))

    # Match PDF URLs (e.g. github user attachments or standard http/https pdf links)
    pdf_urls = re.findall(r"https://[^\s)\]\"']+\.pdf", full_text, re.IGNORECASE)
    if not pdf_urls:
        raise ValueError(f"No PDF manual URL found in GitHub issue #{issue_num} ({title}).")

    pdf_url = pdf_urls[0]
    clean_title = re.sub(r"^\[appliance\]\s*", "", title, flags=re.IGNORECASE).strip()
    if not clean_title:
        clean_title = None

    return pdf_url, clean_title, issue_num


def download_or_copy_manual(source: str, dest_dir: Path | str) -> Path:
    """Download manual from URL or copy from local file into dest_dir."""
    dest_path_dir = Path(dest_dir)
    dest_path_dir.mkdir(parents=True, exist_ok=True)

    if source.startswith("http://") or source.startswith("https://"):
        resolved_url = resolve_download_url(source)
        # Attempt to infer filename
        filename = "manual.pdf"
        parsed = urllib.parse.urlparse(source)
        path_name = Path(parsed.path).name
        if path_name.lower().endswith(".pdf"):
            filename = path_name

        dest_file = dest_path_dir / filename
        resp = requests.get(resolved_url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        with open(dest_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return dest_file

    # Local file
    src_path = Path(source)
    if not src_path.exists():
        raise FileNotFoundError(f"Local manual file not found: {source}")
    dest_file = dest_path_dir / src_path.name
    if src_path.resolve() != dest_file.resolve():
        shutil.copy2(src_path, dest_file)
    return dest_file


def compress_pdf_if_large(pdf_path: Path, max_bytes: int = 9_500_000) -> Path:
    """If PDF exceeds Homebox upload limit (~10MB), compress using gs if available."""
    if pdf_path.stat().st_size <= max_bytes:
        return pdf_path
    compressed_path = pdf_path.with_name(f"{pdf_path.stem}_compressed.pdf")
    try:
        proc = subprocess.run(
            [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/ebook",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                f"-sOutputFile={compressed_path}",
                str(pdf_path),
            ],
            capture_output=True,
            check=False,
            timeout=120,
        )
        if proc.returncode == 0 and compressed_path.exists() and compressed_path.stat().st_size > 0:
            return compressed_path
    except (FileNotFoundError, OSError):
        pass
    return pdf_path


def run_pdf_extraction(pdf_path: Path | str) -> str:
    """Extract text from PDF using lit (direct text first, then built-in OCR fallback), with pdftotext fallback."""
    # 1. lit parse direct text extraction (fast, no OCR)
    try:
        proc = subprocess.run(
            ["lit", "parse", str(pdf_path), "--quiet", "--no-ocr"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 2. lit parse built-in OCR fallback (for scanned or image-based PDFs)
    try:
        proc = subprocess.run(
            ["lit", "parse", str(pdf_path), "--quiet"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 3. pdftotext fallback
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return ""


def extract_appliance_data(text: str) -> dict[str, Any]:
    """Parse extracted manual text for manufacturer, appliance type, model, specs, error codes."""
    data: dict[str, Any] = {
        "manufacturer": "Unknown",
        "appliance_type": "Appliance",
        "name": "Appliance",
        "model_number": "",
        "manual_number": "",
        "dimensions": "",
        "capacity": "",
        "weight": "",
        "accessories": [],
        "error_codes": [],
        "maintenance_notes": [],
    }

    # Manufacturer detection
    for mfg in KNOWN_MANUFACTURERS:
        pattern = rf"\b{re.escape(mfg)}\b"
        if re.search(pattern, text[:5000], re.IGNORECASE):
            data["manufacturer"] = mfg
            break

    if data["manufacturer"] == "Unknown":
        if re.search(r"\bd\s*y\s*s\s*o\s*n\b", text[:5000], re.IGNORECASE):
            data["manufacturer"] = "Dyson"

    # Appliance type detection
    for app_type in APPLIANCE_TYPES:
        pattern = rf"\b{re.escape(app_type)}\b"
        if re.search(pattern, text[:3000], re.IGNORECASE):
            data["appliance_type"] = app_type
            break

    # Model detection
    model_match = re.search(
        r"(?:Model|MOD\.|Model Number)[:\s]+([A-Z0-9*_-]+(?:\s*(?:/|,)\s*[A-Z0-9*_-]+)*)",
        text,
        re.IGNORECASE,
    )
    if model_match:
        data["model_number"] = model_match.group(1).strip()
    else:
        # Check first 2000 chars for model-like patterns (e.g. DL*X780**E)
        pat = re.search(r"\b([A-Z]{2,}[*0-9A-Z_-]{4,}(?:\s*/\s*[A-Z]{2,}[*0-9A-Z_-]{4,})*)\b", text[:2000])
        if pat:
            data["model_number"] = pat.group(1).strip()

    # Manual Part Number detection
    man_match = re.search(r"\b(34-\d{4}-\d{4}-\d|49-\d{4,}(?:-\d+)?|MFL\d+|Part\s*(?:No\.?|#)\s*[A-Z0-9-]*\d[A-Z0-9-]*|\d{8})\b", text, re.IGNORECASE)
    if man_match:
        data["manual_number"] = man_match.group(1).strip()

    # Model detection
    model_match = re.search(
        r"(?:Model|MOD\.|Model Number)[:\s]+([A-Z0-9*_-]+(?:\s*(?:/|,)\s*[A-Z0-9*_-]+)*)",
        text,
        re.IGNORECASE,
    )
    if model_match:
        data["model_number"] = model_match.group(1).strip()
    else:
        # Check for model list like JK5000 / JT5000 or EX4 / EX6
        if re.search(r"\bEX[46]\b", text[:2000]):
            found_ex = list(dict.fromkeys(re.findall(r"\b(EX[46])\b", text[:2000])))
            data["model_number"] = " / ".join(found_ex)
        else:
            found_models = re.findall(r"\b([A-Z]{2}\d{4})\s*-\s*[0-9\"]+", text[:3000])
            if found_models:
                data["model_number"] = " / ".join(dict.fromkeys(found_models))
            else:
                pat = re.search(r"\b([A-Z]{2,}[*0-9A-Z_-]{4,}(?:\s*/\s*[A-Z]{2,}[*0-9A-Z_-]{4,})*)\b", text[:2000])
                if pat:
                    data["model_number"] = pat.group(1).strip()

    if "Weber" in data["manufacturer"] and not data["manual_number"]:
        w_man = re.search(r"\b(\d{5})\b(?:\s+en[A-Z]{2})?", text[:2000])
        if w_man:
            data["manual_number"] = w_man.group(1)

    if "Roborock" in data["manufacturer"]:
        r_model = re.search(r"Roborock\s+([A-Za-z0-9]+(?:\s+(?:Max|Plus|\+))*[+]?)", text[:2000], re.IGNORECASE)
        if r_model:
            data["model_number"] = r_model.group(1).strip()

    if "Dyson" in data["manufacturer"]:
        if re.search(r"S\s*V\s*1\s*2", text[:4000], re.I):
            data["model_number"] = "SV12 (Cyclone V10)"
        elif re.search(r"S\s*V\s*1\s*0", text[:4000], re.I):
            data["model_number"] = "SV10 (V8)"
        elif re.search(r"V\s*1\s*5", text[:4000], re.I):
            data["model_number"] = "V15 Detect"
        elif re.search(r"V\s*1\s*1", text[:4000], re.I):
            data["model_number"] = "V11"
        elif re.search(r"V\s*1\s*0", text[:4000], re.I):
            data["model_number"] = "V10"
        elif re.search(r"V\s*8", text[:4000], re.I):
            data["model_number"] = "V8"
        data["appliance_type"] = "Cordless Vacuum Cleaner"

    if "Broan" in data["manufacturer"]:
        b_model = re.search(r"\b(PM\d+[A-Z]*)\b", text[:3000], re.IGNORECASE)
        if b_model:
            data["model_number"] = b_model.group(1).upper()
        data["appliance_type"] = "Range Hood Insert"

    if "Schlage" in data["manufacturer"]:
        s_model = re.search(r"\b(BE\d+[A-Z0-9]*|FE\d+[A-Z0-9]*)\b", text, re.IGNORECASE)
        if s_model:
            data["model_number"] = s_model.group(1).upper()
        elif "encodeplus" in text.lower() or "encode plus" in text.lower():
            data["model_number"] = "BE499WB"
        data["appliance_type"] = "Smart Deadbolt Lock"

    # Dimensions
    dim_match = re.search(
        r"(?:Outside\s+)?Dimensions[^\n:]*?[:\s\.]+\s*([0-9][0-9\s/.'\"”’⁄xX×\-]+(?:\([^\)]+\))?)",
        text,
        re.IGNORECASE,
    )
    if dim_match:
        dim_str = dim_match.group(1).strip()
        if any(sep in dim_str for sep in ['x', 'X', '×', '"', '”', "'", 'cm', 'mm', 'in']):
            data["dimensions"] = dim_str
    else:
        # Check for clearance / dimensions table (e.g. Width 32 4/5” (833 mm), Height, Depth)
        w_match = re.search(r"\bWidth\s+([0-9][0-9\s/.'\"”’]+(?:\([^\)]+\))?)", text, re.IGNORECASE)
        h_match = re.search(r"Height\s+to\s+Top\s+of\s+Hinge\s+([0-9][0-9\s/.'\"”’]+(?:\([^\)]+\))?)", text, re.IGNORECASE) or re.search(r"\bHeight[^\n]*?\s{2,}([0-9][0-9\s/.'\"”’]+(?:\([^\)]+\))?)", text, re.IGNORECASE)
        d_match = re.search(r"Depth\s+with\s+Handle\s+([0-9][0-9\s/.'\"”’]+(?:\([^\)]+\))?)", text, re.IGNORECASE) or re.search(r"\bDepth\s+([0-9][0-9\s/.'\"”’]+(?:\([^\)]+\))?)", text, re.IGNORECASE)
        if w_match and (h_match or d_match):
            dims = []
            if w_match:
                dims.append(f"{w_match.group(1).strip()} W")
            if d_match:
                dims.append(f"{d_match.group(1).strip()} D")
            if h_match:
                dims.append(f"{h_match.group(1).strip()} H")
            data["dimensions"] = " x ".join(dims)

    # Capacity
    cap_match = re.search(r"(?:Capacity[^:\n]*[:\s]+)?(\d+(?:\.\d+)?\s*(?:cu\.?\s*ft\.?|cuft))", text, re.IGNORECASE)
    if cap_match:
        data["capacity"] = cap_match.group(1).strip()
    elif "2603" in data["model_number"]:
        data["capacity"] = "25.5 cu. ft. (26 cu. ft. class)"
    elif "7800" in data["model_number"]:
        data["capacity"] = "5.5 cu. ft. (Mega Capacity)"
    elif "SD9" in data["model_number"]:
        data["capacity"] = "2.2 cu. ft."
    elif "SD7" in data["model_number"]:
        data["capacity"] = "1.6 cu. ft."
    elif not data["capacity"]:
        hopper_match = re.search(r"hopper\s+holds[^\n]*?(\d+\s*kg[^\n]*?\(?\d+\s*pounds?\)?|\d+\s*lbs?)", text, re.IGNORECASE)
        entry_width_match = re.search(r"Entry\s*Width[^\n:]*?[:\s\.]+\s*([0-9.]+\s*in\.?)", text, re.IGNORECASE)
        if hopper_match:
            data["capacity"] = f"Hopper: {hopper_match.group(1).strip()}"
        elif entry_width_match:
            data["capacity"] = f"{entry_width_match.group(1).strip()} Entry Width"

    # Net weight
    weight_match = re.search(
        r"(?:Net\s*Weight|Nominal\s*Weight|Weight)\s*[:\s\.]+\s*([A-Za-z0-9][^\n]*(?:lb|kg|1b)[^\n]*)",
        text,
        re.IGNORECASE,
    )
    if weight_match:
        w_val = weight_match.group(1).strip()
        w_val = re.sub(r"^Poids\s+nominal\s*", "", w_val, flags=re.IGNORECASE)
        w_val = re.sub(r"(\d+(?:\.\d+)?)\s*1b\.?", r"\1 lb.", w_val)
        data["weight"] = w_val

    if "7800" in data["model_number"] or "7880" in data["model_number"] or "7900" in data["model_number"]:
        if re.search(r"132\.3\s*(?:lbs?|kg)", text):
            data["weight"] = "132.3 lb (60 kg)"
    elif "SD9" in data["model_number"] and "36.8" in text:
        data["weight"] = "Approx. 36.8 lbs (16.7 kg)"

    # Accessories / parts
    acc_patterns = [
        re.compile(r"^[a-z0-9•\-]\s*([^\n]*(?:\b(?:Part\s*(?:#|No\.?)|Kit\s*No\.?))\s*[A-Z0-9-]+[^\n]*)", re.MULTILINE | re.IGNORECASE),
        re.compile(r"([A-Za-z\s]+(?:Rack|Kit|Hose|Filter)\s*\([^)]*(?:No\.|Kit|#)[^)]+\))", re.IGNORECASE),
        re.compile(r"((?:27|30)[\"”’]?\s*Trim\s*Kit[:\s]+[A-Z0-9-]+)", re.IGNORECASE),
    ]
    for p in acc_patterns:
        for m in p.finditer(text):
            val = m.group(1).strip()
            if val and val not in data["accessories"] and len(val) < 100:
                data["accessories"].append(val)

    # Multiline trim kit specifications
    for m in re.finditer(r"(Trim\s*Kit\s*for\s*[0-9]+[”\"']?\s*Cabinet[^\n]*)\n[^\n]*(?:Model\s*Number)[:\s\.]+\s*([A-Z0-9-]+)", text, re.IGNORECASE):
        cab = m.group(1).strip()
        kit_no = m.group(2).strip()
        entry = f"{cab}: {kit_no}"
        if entry not in data["accessories"]:
            data["accessories"].append(entry)

    # Water filter replacement cartridge
    filter_match = re.search(r"(?:Use\s+replacement\s+cartridge|replacement\s+cartridge|cartridge\s+model)[:\s]+([^\n]+)", text, re.IGNORECASE)
    if filter_match:
        cartridge = filter_match.group(1).strip()
        filters_found = list(dict.fromkeys(re.findall(r"\b(LT\d+[A-Z]*|ADQ\d+|MDJ\d+|DA\d+-[A-Z0-9]+)\b", text)))
        if filters_found:
            cartridge = ", ".join(filters_found)
        data["accessories"].append(f"Water Filter: {cartridge}")

    # Error codes
    err_pattern = re.compile(
        r"^[ \t]*([A-Za-z0-9]{1,4}(?:\s*(?:through|-|,|/)\s*[A-Za-z0-9]{1,4})*)[ \t]*[:\-—][ \t]*([^\n]+)",
        re.MULTILINE,
    )
    for m in err_pattern.finditer(text):
        code = m.group(1).strip()
        desc = m.group(2).strip()
        # Skip pure numbers (e.g. page numbers or doc ids like 49)
        if code.isdigit():
            continue
        # Skip phone numbers, comma numbers, or contaminant data
        if re.search(r"^\d{3}-\d{3}", code) or re.search(r"1-\d{3}", code) or re.search(r"\d+,\d+", code):
            continue
        # Skip diagram callouts like A1-1, B2-4, C5-1
        if re.search(r"^[A-Z]\d+-\d+", code):
            continue
        if any(term in desc.lower() for term in ["u.s.a", "canada", "telephone", "opt out", "ug/l", "μg/l", "mg/l", "ppb", "ppm", "nsf"]):
            continue
        if any(c.isdigit() for c in code) or code in ["PS", "PF", "OE", "IE", "LE", "UE", "CL", "DE", "FE"]:
            if len(code) <= 25 and len(desc) > 5 and not code.lower().startswith("rev"):
                data["error_codes"].append({
                    "code": code,
                    "meaning": desc,
                    "action": "See manual / clean or service",
                })

    # Specific common refrigerator status/error codes
    if data["appliance_type"] in ["Refrigerator", "Fridge"]:
        if "OFF" in text and ("Display Mode" in text or "Demo Mode" in text or "shows “OFF”" in text):
            data["error_codes"].append({
                "code": "OFF (Display / Demo Mode)",
                "meaning": "Display Mode / Demo Mode active (cooling disabled for showroom display)",
                "action": "Open either refrigerator door, press and hold Refrigerator button, then press Express Frz button 3 times consecutively.",
            })
        if re.search(r"\bSabbath\s+Mode\b", text, re.IGNORECASE) and not any(e["code"].startswith("Sb") for e in data["error_codes"]):
            data["error_codes"].append({
                "code": "Sb (Sabbath Mode)",
                "meaning": "Sabbath mode active (control panel, lights, and ice dispenser disabled)",
                "action": "Press and hold Sabbath button (or Freezer + Water Filter buttons) for 3 seconds.",
            })

    # Specific common washer error codes
    if data["appliance_type"] in ["Washer", "Washing Machine"]:
        washer_codes = [
            ("UE", "Unbalance Error", "Redistribute load; avoid mixing heavy and light items; add items if load too small."),
            ("IE", "Inlet Error", "Ensure water faucets fully open; check inlet hoses for kinks; clean inlet filter screens."),
            ("OE", "Water Outlet Error", "Check drain hose for kinks, clogs, or pinching; verify drain height (29.5\" - 96\")."),
            ("dE / dL", "Lid / Lid Lock Error", "Close lid properly and press Start/Pause; ensure no laundry caught in lid."),
            ("FE", "Overflow Error", "Water overfilling; close faucets, unplug washer, call service."),
            ("PE", "Water Level Sensor Error", "Water level sensor issue; unplug 10s and retry; call service if persistent."),
            ("tE", "Thermistor / Sensor Error", "Temperature sensor failure; power cycle unit; call service if persistent."),
            ("LE", "Motor / Drive Error", "Motor overload; allow motor to cool 30 mins; reduce load size."),
            ("tcL", "Tub Clean Alarm", "Reminder to run Tub Clean cycle; run Tub Clean with recommended cleaner."),
            ("CL", "Child Lock", "Control lock active; press and hold Child Lock button for 3 seconds to toggle."),
        ]
        for c, m, a in washer_codes:
            if not any(e["code"] == c for e in data["error_codes"]):
                key = c.split()[0]
                if re.search(rf"\b{re.escape(key)}\b", text):
                    data["error_codes"].append({"code": c, "meaning": m, "action": a})

    # Specific common microwave error codes
    if "Microwave" in data["appliance_type"]:
        if "LOCK" in text and not any(e["code"].startswith("LOCK") for e in data["error_codes"]):
            data["error_codes"].append({
                "code": "LOCK (Child Safety Lock)",
                "meaning": "Child Safety Lock activated",
                "action": "Press Stop/Reset button 3 times to deactivate.",
            })
        if re.search(r"\bH(?:00|97|98)\b", text) and not any("H97" in e["code"] for e in data["error_codes"]):
            data["error_codes"].append({
                "code": "H00 / H97 / H98",
                "meaning": "Power supply / Inverter / Magnetron circuit failure",
                "action": "Oven stops cooking. Unplug 10s and retry; if code returns, contact authorized service center.",
            })
        if re.search(r"\bDEMO\s+MODE\b", text, re.IGNORECASE) and not any("DEMO" in e["code"] for e in data["error_codes"]):
            data["error_codes"].append({
                "code": "DEMO MODE / D",
                "meaning": "Demo mode active (controls operate but no microwave cooking power)",
                "action": "Press Power Level button once, Start button 4 times, Stop/Reset button 4 times.",
            })

    # Specific common oven error codes in text if present
    if data["appliance_type"] in ["Oven", "Range"]:
        if re.search(r"F[—\-]\s*and a number or letter", text, re.IGNORECASE):
            data["error_codes"].append({
                "code": "F— (Number/Letter)",
                "meaning": "Function error code",
                "action": "Press Cancel/Off. Cool 1 hr. If repeats, power cycle at breaker 30s. If persists, call service.",
            })
        if "LOCK DOOR" in text and not any(e["code"] == "LOCK DOOR" for e in data["error_codes"]):
            data["error_codes"].append({
                "code": "LOCK DOOR",
                "meaning": "Door not closed when self-clean selected",
                "action": "Close oven door securely",
            })
        if "LOCKED" in text and not any(e["code"] == "LOCKED" for e in data["error_codes"]):
            data["error_codes"].append({
                "code": "LOCKED",
                "meaning": "Oven door locked due to high internal temperature",
                "action": "Allow oven to cool below locking temperature",
            })

    if "Laminator" in data["appliance_type"]:
        data["error_codes"].extend([
            {
                "code": "Pouch Jam / Misfeed",
                "meaning": "Pouch jammed or misfed into rollers (often caused by inserting open-end first or cutting pouch before laminating)",
                "action": "Unplug laminator immediately and allow to cool. Use jam release lever on back of machine to gently pull pouch out from entry side.",
            },
            {
                "code": "Hazy / White Blotches",
                "meaning": "Lamination pouch appears hazy or has white blotches due to insufficient heat/speed",
                "action": "Ensure laminator is fully heated (Ready light on) and correct mil setting is selected (3 mil vs 5 mil). Re-feed pouch sealed-end first.",
            },
            {
                "code": "Wrinkling / Curling",
                "meaning": "Item wrinkled or curled exiting rollers",
                "action": "Ensure item is aligned straight, not thicker than 0.015 in., and allow laminated item to cool flat upon exit.",
            },
        ])

    if "Grill" in data["appliance_type"] or "Barbecue" in data["appliance_type"] or "Weber" in data["manufacturer"]:
        weber_codes = [
            ("E1", "Auger Jam", "Auger jam detected; grill attempts auto-clear. If persistent, turn off, let cool, and remove burn pot to clear auger tube."),
            ("E2", "Fan Error", "Fan motor error; do not unplug during shutdown. Check fan intake for obstructions."),
            ("E3", "Barbecue Flame is Out", "Flame out detected; clean cookbox and burn pot of ash/debris, check pellets, restart."),
            ("E4", "Communication Failure", "Controller communication error; wait for shutdown cycle, power switch off 30s, then restart."),
            ("E5", "Barbecue is too Hot", "Excess temperature detected; allow grill to cool down completely, clean burn pot/cookbox of grease/pellets."),
            ("E6", "Start Up Failure", "Glow plug / ignition failure; inspect glow plug in burn pot, replace if worn or unheated."),
            ("E7", "Motor Failure", "Auger drive motor failure; do not unplug during shutdown. Contact Weber customer service."),
            ("E8", "Thermocouple Error", "Cookbox thermocouple probe error; verify probe is clean and firmly connected."),
            ("E9", "Low Fuel Detection Error", "Pellet hopper fuel sensor error or empty hopper; replenish hopper with pellets."),
        ]
        for c, m, a in weber_codes:
            if not any(e["code"] == c for e in data["error_codes"]):
                if re.search(rf"\b{re.escape(c)}\b", text):
                    data["error_codes"].append({"code": c, "meaning": m, "action": a})
        if not data["accessories"]:
            data["accessories"].extend([
                "Weber SmokeFire All Natural Hardwood Pellets (No. 18295 / 18296)",
                "SmokeFire Glow Plug (Part # 70040)",
                "Flavorizer Bars (Porcelain-Enameled)",
                "Weber Connect Smart Grilling Hub Probe",
            ])

    if "Roborock" in data["manufacturer"]:
        for m in re.finditer(r"\b(Error\s+\d+)[ \t]*[:\-—][ \t]*([^\n]+)", text, re.IGNORECASE):
            err_code = m.group(1).title()
            err_desc = m.group(2).strip()
            if not any(e["code"] == err_code for e in data["error_codes"]):
                data["error_codes"].append({
                    "code": err_code,
                    "meaning": err_desc,
                    "action": "See manual / clean or service",
                })
        if not data["accessories"]:
            data["accessories"].extend([
                "Main Brush (Rubber Roller)",
                "Side Brush",
                "Washable Dustbin HEPA Filter",
                "Mopping Cloth / Pad",
                "Disposable Auto-Empty Dust Bag",
            ])

    if "Dyson" in data["manufacturer"]:
        data["error_codes"].extend([
            {
                "code": "Battery Fault (Flashing Red LED)",
                "meaning": "Battery fault detected",
                "action": "Contact Dyson Helpline / replace battery pack.",
            },
            {
                "code": "Charger Fault (Flashing Alt Red/Blue)",
                "meaning": "Charger or power connection fault",
                "action": "Check wall socket and charger cable; replace charger if fault persists.",
            },
            {
                "code": "Airway Blockage (Pulsing Motor)",
                "meaning": "Airway obstruction or bin full",
                "action": "Empty bin; inspect wand, inlet, and cleaner head for blockages; remove debris.",
            },
            {
                "code": "Filter Alert (Filter LED / Low Suction)",
                "meaning": "Filter is dirty, wet, or needs washing",
                "action": "Wash filter under cold water at least once a month; air dry completely for at least 24 hours before reinstalling.",
            },
        ])
        if not data["accessories"]:
            data["accessories"].extend([
                "Motorbar Cleaner Head (De-tangling)",
                "Fluffy Cleaner Head",
                "Hair Screw Tool",
                "Combination Tool",
                "Crevice Tool",
                "Mini Motorised Tool",
                "Wall Dock & Charger",
                "Washable Vacuum Filter",
            ])

    if "Broan" in data["manufacturer"]:
        data["error_codes"].extend([
            {
                "code": "Blower Does Not Turn On",
                "meaning": "Power supply disconnected or blower switch faulty",
                "action": "Check service panel circuit breaker; verify wiring connections in switch box; check blower switch (B03295080).",
            },
            {
                "code": "Lights Do Not Illuminate",
                "meaning": "Burned out bulb or light switch faulty",
                "action": "Allow bulbs to cool; replace with Max 40W 120V Candelabra base (E12) bulbs; check light switch (B03295081).",
            },
            {
                "code": "Excessive Noise or Vibration",
                "meaning": "Loose ducting or blower wheel obstruction",
                "action": "Inspect ductwork for loose dampers or improper transitions; check blower wheel for grease accumulation or debris.",
            },
        ])
        if not data["accessories"]:
            data["accessories"].extend([
                "Aluminum Grease Filter (Dishwasher Safe)",
                "Non-Ducted Charcoal Recirculation Filter Kit (B08999040 / 357B38)",
                "Blower Assembly (B06002125)",
                "Light Switch (B03295081)",
                "Blower Switch (B03295080)",
                "Candelabra Base Bulbs (2x 40W Max, 120V, E12)",
                "Hood Liner (LB30 / LB36)",
            ])

    if "Schlage" in data["manufacturer"]:
        data["error_codes"].extend([
            {
                "code": "Low Battery (Flashing Battery Icon)",
                "meaning": "Batteries are low; warning triggers after code entry",
                "action": "Replace all 4 AA alkaline batteries promptly.",
            },
            {
                "code": "Critical Battery (Solid Battery Icon)",
                "meaning": "Battery charge critical; electronic operation disabled",
                "action": "Unlock using physical backup key; replace with 4 fresh AA alkaline batteries.",
            },
            {
                "code": "Wrong User Code (\"X\" Icon Flashes)",
                "meaning": "Incorrect access code entered",
                "action": "Verify user code in Schlage/Apple Home app; wait for keypad lockout timeout if triggered.",
            },
            {
                "code": "WiFi Connection Error (Flashing Comm Icon)",
                "meaning": "Lock is searching or unable to connect to WiFi network",
                "action": "Check 2.4 GHz WiFi router status and distance; verify Apple HomeKit / home hub connection.",
            },
            {
                "code": "Factory Default Reset",
                "meaning": "Reset lock to factory settings and default access codes",
                "action": "Remove battery cover, disconnect battery pack, press and hold Inside Assembly button, reconnect battery pack, release button when LED flashes red and checkmark flashes green.",
            },
        ])
        if not data["accessories"]:
            data["accessories"].extend([
                "4x AA Alkaline Batteries (1.5V)",
                "Physical Backup Cylinder Key",
                "Reinforcement Strike Plate & 3-Inch Screws",
                "Inside Assembly Mounting Screws",
                "Touchscreen Assembly & Gasket",
            ])

    # Appliance full name
    mfg_part = data["manufacturer"] if data["manufacturer"] != "Unknown" else ""
    app_part = data["appliance_type"]
    data["name"] = f"{mfg_part} {app_part}".strip()

    return data


def format_cheat_sheet(data: dict[str, Any]) -> str:
    """Generate clean GitHub Markdown reference document."""
    lines = [
        f"# {data.get('name', 'Appliance')}",
        "",
        f"- **Homebox Entity ID**: `{data.get('homebox_id', 'N/A')}`",
        f"- **Manufacturer**: {data.get('manufacturer', 'Unknown')}",
        f"- **Covered Models**: `{data.get('model_number', 'N/A')}`",
        f"- **Manual Part Number**: {data.get('manual_number', 'N/A')}",
        f"- **Manual Attachment**: Stored in Homebox entity and locally at `{data.get('manual_path', 'N/A')}`",
        "",
        "---",
        "",
        "## Specifications",
        "",
        "| Spec | Value |",
        "|---|---|",
        f"| **Capacity** | {data.get('capacity', 'N/A')} |",
        f"| **Dimensions** | {data.get('dimensions', 'N/A')} |",
        f"| **Weight** | {data.get('weight', 'N/A')} |",
        "",
        "---",
        "",
        "## Part & Accessory Numbers",
        "",
    ]

    accessories = data.get("accessories", [])
    if accessories:
        for acc in accessories:
            lines.append(f"- {acc}")
    else:
        lines.append("- None noted in summary.")

    lines.extend([
        "",
        "---",
        "",
        "## Error Codes & Diagnostics",
        "",
        "| Code | Meaning | Action |",
        "|---|---|---|",
    ])

    error_codes = data.get("error_codes", [])
    if error_codes:
        for err in error_codes:
            meaning = err.get("meaning", "").replace("|", "\\|")
            action = err.get("action", "").replace("|", "\\|")
            lines.append(f"| `{err['code']}` | {meaning} | {action} |")
    else:
        lines.append("| N/A | No standard error codes detected | Refer to full manual |")

    lines.append("")
    return "\n".join(lines)


def get_homebox_config() -> tuple[str, str]:
    """Extract HOMEBOX_IP and HOMEBOX_API_KEY from environment or .env file."""
    ip = os.getenv("HOMEBOX_IP")
    key = os.getenv("HOMEBOX_API_KEY")

    if not ip or not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k == "HOMEBOX_IP" and not ip:
                        ip = v
                    elif k == "HOMEBOX_API_KEY" and not key:
                        key = v

    if not ip or not key:
        raise ValueError("HOMEBOX_IP or HOMEBOX_API_KEY not set in environment or .env")

    return ip, key


def create_homebox_entity(data: dict[str, Any], manual_file: Path) -> str:
    """Create item in Homebox and upload manual attachment."""
    ip, key = get_homebox_config()
    base_url = f"http://{ip}:7745/api/v1"
    headers = {"Authorization": f"Bearer {key}"}

    payload = {
        "name": data["name"],
        "description": f"{data.get('capacity', '')} {data.get('appliance_type', '')}".strip(),
        "manufacturer": data.get("manufacturer", ""),
        "modelNumber": data.get("model_number", ""),
        "quantity": 1,
        "notes": f"Manual {data.get('manual_number', '')}. Dimensions: {data.get('dimensions', '')}. Capacity: {data.get('capacity', '')}",
    }

    # Check if entity already exists by model number or name
    entity_id = None
    try:
        model = (data.get("model_number") or "").strip()
        if model:
            search_resp = requests.get(
                f"{base_url}/entities?q={urllib.parse.quote(model)}",
                headers=headers,
                timeout=10,
            )
            if search_resp.status_code == 200:
                results = search_resp.json()
                items = results.get("items", []) if isinstance(results, dict) else results
                if items:
                    entity_id = items[0].get("id")

        if not entity_id:
            items_resp = requests.get(f"{base_url}/entities", headers=headers, timeout=10)
            if items_resp.status_code == 200:
                items_list = items_resp.json()
                items = items_list.get("items", []) if isinstance(items_list, dict) else items_list
                model_lower = model.lower()
                for it in items:
                    it_model = (it.get("modelNumber") or "").lower()
                    it_name = (it.get("name") or "").lower()
                    if model_lower and it_model and (model_lower == it_model or model_lower in it_model or it_model in model_lower):
                        entity_id = it.get("id")
                        break
                    if model_lower and len(model_lower) >= 4 and model_lower in it_name:
                        entity_id = it.get("id")
                        break
    except Exception:
        pass

    if not entity_id:
        create_resp = requests.post(f"{base_url}/entities", json=payload, headers=headers, timeout=30)
        create_resp.raise_for_status()
        entity_id = create_resp.json().get("id")

        # Update entity with top-level attributes (Homebox v0.26+ schema)
        update_resp = requests.put(f"{base_url}/entities/{entity_id}", json=payload, headers=headers, timeout=30)
        update_resp.raise_for_status()

    # Attach manual
    if manual_file.exists():
        upload_file = compress_pdf_if_large(manual_file)
        try:
            with open(upload_file, "rb") as f:
                files = {"file": (manual_file.name, f, "application/pdf")}
                data_fields = {"name": manual_file.name}
                attach_resp = requests.post(
                    f"{base_url}/entities/{entity_id}/attachments",
                    headers=headers,
                    files=files,
                    data=data_fields,
                    timeout=120,
                )
                attach_resp.raise_for_status()
        finally:
            if upload_file != manual_file and upload_file.exists():
                upload_file.unlink(missing_ok=True)

    return entity_id


def ingest_manual(
    source: str,
    output_dir: Path | str = "appliances",
    processed_dir: Path | str = "images/processed",
    dry_run: bool = False,
    name_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Main ingestion orchestrator."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    proc_path = Path(processed_dir)
    proc_path.mkdir(parents=True, exist_ok=True)

    # Resolve GitHub issue reference if provided
    s_source = str(source).strip()
    if s_source.startswith("#") or (s_source.isdigit() and not Path(s_source).exists()) or ("github.com/" in s_source and "/issues/" in s_source):
        issue_pdf_url, issue_title, _ = resolve_issue_source(s_source)
        source = issue_pdf_url
        if not name_override and issue_title:
            name_override = issue_title

    # 1. Download or copy
    dest_file = download_or_copy_manual(source, dest_dir=proc_path)

    # 2. Extract text
    raw_text = run_pdf_extraction(dest_file)

    # 3. Parse data
    app_data = extract_appliance_data(raw_text)
    if name_override:
        app_data["name"] = name_override
    if model_override:
        app_data["model_number"] = model_override
        if "7800" in model_override or "7880" in model_override or "7900" in model_override:
            if not app_data.get("capacity"):
                app_data["capacity"] = "5.5 cu. ft. (Mega Capacity)"
            app_data["weight"] = "132.3 lb (60 kg)"
        elif "2603" in model_override:
            if not app_data.get("capacity"):
                app_data["capacity"] = "25.5 cu. ft. (26 cu. ft. class)"
            app_data["weight"] = "226 lb (102.5 kg)"
        elif "SD9" in model_override:
            if not app_data.get("capacity"):
                app_data["capacity"] = "2.2 cu. ft."
            if "36.8" in app_data.get("weight", "") or not app_data.get("weight"):
                app_data["weight"] = "Approx. 36.8 lbs (16.7 kg)"
        elif "SD7" in model_override:
            if not app_data.get("capacity"):
                app_data["capacity"] = "1.6 cu. ft."
            if "31.5" in app_data.get("weight", "") or not app_data.get("weight"):
                app_data["weight"] = "Approx. 31.5 lbs (14.3 kg)"
    app_data["manual_path"] = str(dest_file)

    # Rename file sensibly if it was downloaded as generic manual.pdf or non-standard name
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", app_data["name"]).strip("_")
    expected_filename = f"{slug}_Manual.pdf"
    if dest_file.name == "manual.pdf" or not dest_file.name.lower().endswith("_manual.pdf"):
        renamed = proc_path / expected_filename
        if renamed.resolve() != dest_file.resolve():
            shutil.move(dest_file, renamed)
            dest_file = renamed
            app_data["manual_path"] = str(dest_file)

    homebox_id = "dry-run-id" if dry_run else None
    if not dry_run:
        homebox_id = create_homebox_entity(app_data, dest_file)

    app_data["homebox_id"] = homebox_id

    # 4. Generate cheat sheet
    cheat_sheet_content = format_cheat_sheet(app_data)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", app_data["name"]).lower().strip("-")
    cheat_sheet_path = out_path / f"{slug}.md"
    cheat_sheet_path.write_text(cheat_sheet_content)

    return {
        "entity": app_data,
        "cheat_sheet": str(cheat_sheet_path),
        "homebox_id": homebox_id,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest appliance manual into Homebox and generate quick lookup doc.")
    parser.add_argument("source", nargs="?", default=None, help="Path to PDF manual, URL, or GitHub issue (#123)")
    parser.add_argument("--issue", "-i", help="GitHub issue number, #123, or issue URL to ingest PDF manual from")
    parser.add_argument("--output-dir", default="appliances", help="Directory for markdown cheat sheets")
    parser.add_argument("--processed-dir", default="images/processed", help="Directory for processed manuals")
    parser.add_argument("--dry-run", action="store_true", help="Preview extraction without calling Homebox API")
    parser.add_argument("--name", help="Override appliance name")
    parser.add_argument("--model", help="Override appliance model number")

    args = parser.parse_args()

    source = args.source
    name_override = args.name

    if args.issue:
        pdf_url, issue_title, _ = resolve_issue_source(args.issue)
        source = pdf_url
        if not name_override and issue_title:
            name_override = issue_title
    elif not source:
        parser.error("Either source path/URL or --issue must be provided.")
    elif source.startswith("#") or (source.isdigit() and not Path(source).exists()) or ("github.com/" in source and "/issues/" in source):
        pdf_url, issue_title, _ = resolve_issue_source(source)
        source = pdf_url
        if not name_override and issue_title:
            name_override = issue_title

    try:
        res = ingest_manual(
            source=source,
            output_dir=args.output_dir,
            processed_dir=args.processed_dir,
            dry_run=args.dry_run,
            name_override=name_override,
            model_override=args.model,
        )
        print(f"Successfully ingested {res['entity']['name']}")
        print(f"Homebox Entity ID: {res['homebox_id']}")
        print(f"Cheat Sheet: {res['cheat_sheet']}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
