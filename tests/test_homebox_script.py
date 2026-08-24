import os
import subprocess
import json
import pytest

def test_homebox_script_search(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    
    # Mock curl
    curl_mock = bin_dir / "curl"
    curl_mock.write_text("""#!/bin/bash
    cat <<EOF
{
  "items": [
    {"id": "1", "name": "Test Laptop"},
    {"id": "2", "name": "Keyboard"}
  ]
}
EOF
""")
    curl_mock.chmod(0o755)

    # Note: We rely on the system jq for parsing the output
    
    env = os.environ.copy()
    
    system_path = env.get('PATH', '')
    if "/home/linuxbrew/.linuxbrew/bin" not in system_path:
        system_path = f"/home/linuxbrew/.linuxbrew/bin:{system_path}"
        
    env["PATH"] = f"{bin_dir}:{system_path}"
    env["HOMEBOX_IP"] = "127.0.0.1"
    env["HOMEBOX_API_KEY"] = "fake-key"
    
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "homebox.sh"))
    
    # Run the script with 'search laptop'
    result = subprocess.run([script_path, "search", "laptop"], env=env, capture_output=True, text=True)
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "ID: 1 | Name: Test Laptop" in result.stdout
    assert "Keyboard" not in result.stdout

def test_homebox_script_entity_types(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    
    curl_mock = bin_dir / "curl"
    curl_mock.write_text("""#!/bin/bash
    cat <<EOF
[
  {"id": "loc-123", "name": "Location", "isLocation": true}
]
EOF
""")
    curl_mock.chmod(0o755)
    
    env = os.environ.copy()
    system_path = env.get('PATH', '')
    if "/home/linuxbrew/.linuxbrew/bin" not in system_path:
        system_path = f"/home/linuxbrew/.linuxbrew/bin:{system_path}"
    env["PATH"] = f"{bin_dir}:{system_path}"
    env["HOMEBOX_IP"] = "127.0.0.1"
    env["HOMEBOX_API_KEY"] = "fake-key"
    
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "homebox.sh"))
    
    result = subprocess.run([script_path, "entity-types"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "ID: loc-123 | Name: Location" in result.stdout

def test_homebox_script_delete(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    
    curl_mock = bin_dir / "curl"
    curl_mock.write_text("""#!/bin/bash
    if [[ "$*" == *"-X DELETE"* && "$*" == *"/api/v1/entities/ent-123"* ]]; then
        echo "Deleted entity ent-123"
    fi
""")
    curl_mock.chmod(0o755)
    
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["HOMEBOX_IP"] = "127.0.0.1"
    env["HOMEBOX_API_KEY"] = "fake-key"
    
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "homebox.sh"))
    
    result = subprocess.run([script_path, "delete", "ent-123"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "Deleted entity ent-123" in result.stdout

def test_homebox_script_no_env(tmp_path):
    # If variables aren't set, it should exit with 1
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "homebox.sh"))
    
    env = os.environ.copy()
    if "HOMEBOX_IP" in env: del env["HOMEBOX_IP"]
    if "HOMEBOX_API_KEY" in env: del env["HOMEBOX_API_KEY"]
    
    # Run in tmp_path so it doesn't find the .env file in the repo root
    result = subprocess.run([script_path, "list"], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Error: HOMEBOX_IP or HOMEBOX_API_KEY not set" in result.stdout
