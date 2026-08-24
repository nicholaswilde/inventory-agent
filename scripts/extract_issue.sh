#!/bin/bash

# extract_issue.sh
# Automates the extraction of an issue, downloading attachments, and running OCR quietly to save token usage for agents.
# Usage: ./scripts/extract_issue.sh <issue_number>

if [ -z "$1" ]; then
  echo "Error: Issue number required."
  echo "Usage: $0 <issue_number>"
  exit 1
fi

ISSUE_NUM=$1
TEMP_DIR="/tmp/issue_${ISSUE_NUM}_extract"
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR" || exit 1

# 1. Fetch issue details silently
ISSUE_JSON=$(gh issue view "$ISSUE_NUM" --json title,body)
TITLE=$(echo "$ISSUE_JSON" | jq -r .title)
BODY=$(echo "$ISSUE_JSON" | jq -r .body)

echo "=== Issue #$ISSUE_NUM: $TITLE ==="
echo "Body:"
echo "$BODY"
echo "=================================="

# 2. Extract URLs (look for standard markdown image/file links or direct URLs)
# This simple regex extracts URLs that look like github attachments
URLS=$(echo "$BODY" | grep -o 'https://github.com/user-attachments/[^ )"]*')

if [ -z "$URLS" ]; then
  echo "No attachments found in issue body."
  exit 0
fi

echo -e "\n--- Processing Attachments ---"

# 3. Download and process each URL
count=1
for url in $URLS; do
  # Follow redirects silently
  filename=$(basename "$url")
  curl -sL -o "$filename" "$url"
  
  if [[ "$filename" == *.zip ]]; then
    # It's a zip file, extract it
    unzip -q "$filename" -d "extracted_$count"
    # Find all images and run lit quietly
    find "extracted_$count" -type f \( -iname \*.jpg -o -iname \*.jpeg -o -iname \*.png -o -iname \*.gif \) | while read -r img; do
      echo -e "\n[Image: $img]"
      # Run lit and suppress verbose output, only show extracted text
      lit parse "$img" --quiet 2>/dev/null | sed '/^\[liteparse\]/d' | grep -v "^--- Page" | tr -s '\n' | grep -v '^\s*$'
    done
  else
    # Treat as image
    echo -e "\n[Image: $filename]"
    lit parse "$filename" --quiet 2>/dev/null | sed '/^\[liteparse\]/d' | grep -v "^--- Page" | tr -s '\n' | grep -v '^\s*$'
  fi
  count=$((count + 1))
done

echo -e "\n--- Extraction Complete ---"
echo "All files are temporarily stored in: $TEMP_DIR"
