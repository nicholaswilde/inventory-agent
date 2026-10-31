import os
import subprocess
from pathlib import Path
import pytest

SCRIPT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts", "print_to_brother.sh")
)


def test_print_to_brother_no_args():
    result = subprocess.run([SCRIPT_PATH], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Error: No text provided to print." in (result.stdout + result.stderr)


def test_print_to_brother_empty_arg():
    result = subprocess.run([SCRIPT_PATH, ""], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Error: No text provided to print." in (result.stdout + result.stderr)


def test_print_to_brother_success(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_file = tmp_path / "calls.log"
    tracked_files = tmp_path / "tracked_files.txt"

    # Mock pandoc
    pandoc_mock = bin_dir / "pandoc"
    pandoc_mock.write_text(f"""#!/bin/bash
echo "pandoc called with: $@" >> "{log_file}"
echo "$1" >> "{tracked_files}"
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    out_file="$2"
    echo "$out_file" >> "{tracked_files}"
    shift 2
  else
    shift
  fi
done
if [ -n "$out_file" ]; then
  echo "%PDF-1.4 dummy pdf" > "$out_file"
fi
""")
    pandoc_mock.chmod(0o755)

    # Mock lp
    lp_mock = bin_dir / "lp"
    lp_mock.write_text(f"""#!/bin/bash
echo "lp called with: $@" >> "{log_file}"
pdf_file="${{@: -1}}"
if [ -f "$pdf_file" ]; then
  echo "pdf exists: $pdf_file" >> "{log_file}"
fi
""")
    lp_mock.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    markdown_input = "# Test Title\\n\\n| Column | Value |\\n|---|---|\\n| A | 1 |"
    result = subprocess.run(
        [SCRIPT_PATH, markdown_input], env=env, capture_output=True, text=True
    )

    assert result.returncode == 0, f"Script failed: {result.stderr}"

    logs = log_file.read_text()
    assert "pandoc called with:" in logs
    assert "--pdf-engine=xelatex" in logs
    assert "lp called with: -d BrotherPrinter" in logs
    assert "pdf exists:" in logs

    # Check temp files deleted
    created_files = [
        line.strip() for line in tracked_files.read_text().splitlines() if line.strip()
    ]
    assert len(created_files) == 2
    for file_path in created_files:
        assert not os.path.exists(file_path), (
            f"Temporary file {file_path} was not cleaned up"
        )
