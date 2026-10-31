#!/usr/bin/env bash

# Check if input is provided
if [ -z "$1" ]; then
  echo "Error: No text provided to print."
  exit 1
fi

# Create temporary files for processing
TMP_MD=$(mktemp --suffix=.md)
TMP_PDF=$(mktemp --suffix=.pdf)

# Write input to temporary markdown file
echo -e "$1" > "$TMP_MD"

# Convert markdown to PDF using pandoc and xetex engine
pandoc "$TMP_MD" -o "$TMP_PDF" --pdf-engine=xelatex

# Send the generated PDF to the Brother printer
lp -d BrotherPrinter "$TMP_PDF"

# Clean up temporary files
rm "$TMP_MD" "$TMP_PDF"
