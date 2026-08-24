import os
import subprocess
import zipfile
import shutil
import pytest

def test_process_images_script(tmp_path):
    # Set up directory structure in a temporary directory
    pending_dir = tmp_path / "images" / "pending"
    processed_dir = tmp_path / "images" / "processed"
    pending_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create a dummy image
    dummy_img = pending_dir / "test_image.jpg"
    dummy_img.write_text("dummy image content")

    # 2. Create a dummy zip with an image inside
    zip_path = pending_dir / "test_archive.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("nested_image.png", "nested image content")
        zf.writestr("not_an_image.txt", "text content")

    # The script uses relative paths, so we need to run it from tmp_path
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "process_images.sh"))
    
    # Ensure script is executable
    os.chmod(script_path, 0o755)
    
    # Run the bash script
    result = subprocess.run([script_path], cwd=tmp_path, capture_output=True, text=True)
    
    # Check if the script executed successfully
    assert result.returncode == 0, f"Script failed with output: {result.stderr}"

    # Verify the results
    # 1. Zip file should be moved to processed
    assert not zip_path.exists(), "Zip file was not moved from pending"
    assert (processed_dir / "test_archive.zip").exists(), "Zip file was not moved to processed"

    # 2. Dummy image should be moved to processed
    assert not dummy_img.exists(), "Dummy image was not moved from pending"
    assert (processed_dir / "test_image.jpg").exists(), "Dummy image was not moved to processed"

    # 3. Nested image from zip should be extracted and moved to processed
    assert not (pending_dir / "nested_image.png").exists(), "Nested image was not moved from pending"
    assert (processed_dir / "nested_image.png").exists(), "Nested image was not extracted/moved to processed"
    
    # Text file inside zip might be extracted but the script specifically uses `find` with image extensions
    # so we shouldn't see it in processed, or maybe it got left behind and deleted with the temp dir.
    assert not (processed_dir / "not_an_image.txt").exists(), "Non-image files should not be processed/moved"
