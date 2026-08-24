---
name: process-local-images
description: Processes local images and zip files from images/pending and moves them to images/processed.
---

# Process Local Images and Zip Files

## Guidelines
1. Images and zip files to be processed should be placed in `images/pending/`.
2. Any `.zip` files found will be extracted automatically. The images inside will be moved to `images/pending/` for processing, and the original zip file will be moved to `images/processed/`.
3. Process each image using `lit` and then `tesseract` to extract text.
   - **Vision Fallback**: If the text extraction yields no meaningful results, use your native multimodal vision capabilities (e.g. by using `view_file` on the image path) to visually inspect the image and identify the component or board directly.
4. Once an image is successfully processed and identified, move it to `images/processed/`.
5. Run `task process-images` to execute the automated processing script.

## Execution
Use `scripts/process_images.sh` to automate this workflow.
