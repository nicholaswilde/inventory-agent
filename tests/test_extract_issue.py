import os
import subprocess
import json
import pytest
import shutil
from pathlib import Path

def test_extract_issue_script(tmp_path, monkeypatch):
    # Set up mock bin directory
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    
    # Mock gh
    gh_mock = bin_dir / "gh"
    gh_mock.write_text("""#!/bin/bash
if [ "$1" = "issue" ] && [ "$2" = "view" ] && [ "$3" = "123" ]; then
    cat <<EOF
{
  "title": "Test Issue",
  "body": "Here is an image: https://github.com/user-attachments/assets/abc-123.png\\nHere is a zip: https://github.com/user-attachments/assets/def-456.zip"
}
EOF
fi
""")
    gh_mock.chmod(0o755)

    # Mock curl
    curl_mock = bin_dir / "curl"
    curl_mock.write_text("""#!/bin/bash
# Mock curl to just create dummy files
for arg in "$@"; do
    if [[ "$arg" == "-o" ]]; then
        output_arg=1
    elif [[ "$output_arg" == "1" ]]; then
        output_file="$arg"
        output_arg=0
    elif [[ "$arg" == *"def-456.zip"* ]]; then
        # Create a dummy zip file
        echo "dummy zip content" > "$output_file"
        # We actually need a real zip so unzip doesn't fail
        # So we write a simple zip containing one image
        # In python we'll pre-create a valid zip and copy it
        cp "$MOCK_ZIP_PATH" "$output_file"
    elif [[ "$arg" == *"abc-123.png"* ]]; then
        echo "dummy png" > "$output_file"
    fi
done
""")
    curl_mock.chmod(0o755)
    
    # We need a valid zip file for the curl mock to copy
    mock_zip_path = tmp_path / "mock.zip"
    import zipfile
    with zipfile.ZipFile(mock_zip_path, 'w') as zf:
        zf.writestr("test_image.jpg", "dummy image data")
        
    # Mock unzip (optional, but system unzip is fine if we give it a real zip)
    
    # Mock lit
    lit_mock = bin_dir / "lit"
    lit_mock.write_text("""#!/bin/bash
# Mock lit to just echo something based on the file parsed
echo "Mock OCR text for $2"
""")
    lit_mock.chmod(0o755)

    # Set up environment
    env = os.environ.copy()
    # Ensure linuxbrew bin is in PATH for jq
    system_path = env.get('PATH', '')
    if "/home/linuxbrew/.linuxbrew/bin" not in system_path:
        system_path = f"/home/linuxbrew/.linuxbrew/bin:{system_path}"
    
    env["PATH"] = f"{bin_dir}:{system_path}"
    env["MOCK_ZIP_PATH"] = str(mock_zip_path)

    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "extract_issue.sh"))
    
    # Run the script with issue number 123
    result = subprocess.run([script_path, "123"], env=env, capture_output=True, text=True)
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    
    # Verify the output contains expected lines
    assert "=== Issue #123: Test Issue ===" in result.stdout
    assert "Mock OCR text for abc-123.png" in result.stdout
    assert "Mock OCR text for extracted_2/test_image.jpg" in result.stdout
    
    # Cleanup /tmp/issue_123_extract if it exists
    tmp_extract_dir = Path("/tmp/issue_123_extract")
    if tmp_extract_dir.exists():
        shutil.rmtree(tmp_extract_dir)
