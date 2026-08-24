#!/bin/bash

# process_images.sh
# Processes zip files and images in images/pending using lit and tesseract, then moves them to images/processed

PENDING_DIR="images/pending"
PROCESSED_DIR="images/processed"

mkdir -p "$PENDING_DIR" "$PROCESSED_DIR"

# 1. Process Zip files first
for zip_file in "$PENDING_DIR"/*.zip; do
  # Check if glob expanded to actual file
  if [ -f "$zip_file" ]; then
    zip_name=$(basename "$zip_file")
    echo "Extracting $zip_name..."
    
    # Extract to a temporary directory inside pending
    temp_extract_dir="$PENDING_DIR/extracted_${zip_name%.*}"
    mkdir -p "$temp_extract_dir"
    
    unzip -q "$zip_file" -d "$temp_extract_dir"
    
    # Move extracted images to pending root for normal processing
    # Using find to handle any nested directories inside the zip
    find "$temp_extract_dir" -type f \( -iname \*.jpg -o -iname \*.jpeg -o -iname \*.png -o -iname \*.gif \) -exec mv {} "$PENDING_DIR/" \;
    
    # Cleanup temp dir and move zip to processed
    rm -rf "$temp_extract_dir"
    mv "$zip_file" "$PROCESSED_DIR/"
    echo "Extracted $zip_name and moved to $PROCESSED_DIR/"
  fi
done

# 2. Process all images
for img in "$PENDING_DIR"/*; do
  if [ -f "$img" ]; then
    filename=$(basename "$img")
    echo "Processing $filename..."
    
    # Run lit and tesseract (example pipeline based on guidelines)
    # lit "$img" -o "${img}.lit.png"
    # tesseract "${img}.lit.png" "${PENDING_DIR}/${filename%.*}"
    
    # Move to processed
    mv "$img" "$PROCESSED_DIR/"
    echo "Moved $filename to $PROCESSED_DIR/"
  fi
done

echo "Done processing."
