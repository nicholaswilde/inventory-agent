---
name: issue-to-homebox
description: Processes a GitHub issue to extract item details from images or zips, adds the item to Homebox if it doesn't exist, and creates a commit to close the issue.
---

# Issue to Homebox Skill

This skill guides the agent to process a GitHub issue, extract item details, map them to HomeBox fields, process any attached images or zip files, and add the item to Homebox. 

## Workflow

1. **Read Issue**: 
   - Run `gh issue view <issue_number> | cat` to read the issue title, body, and extract any file URLs (images or zip files).

2. **Download & Process Files**: 
   - Download the attached file(s) from the issue (e.g., using `curl -O`).
   - **If the file is a zip archive**: Extract the `.zip` file into a temporary directory first, then process all images inside.
   - Follow the repository's primary image parsing workflow for each image: Process the image with `lit`, and then run `tesseract` on the output to extract text.
   - **Vision Fallback**: If the OCR pipeline fails to extract meaningful text, or if the component's type/model is unclear from the text alone, use your native multimodal capabilities (e.g. via `view_file` tool on the image) to visually inspect the component or board to identify its type, manufacturer, and model.

3. **Identify Item Details & Map to Homebox Fields**:
   - Parse the structured fields from the issue body. Based on the issue template, map these fields directly to the Homebox JSON payload:
     - **Item Name** -> `name` (Use OCR or visual identification if the issue left this blank or vague)
     - **Manufacturer** -> `manufacturer`
     - **Model Number** -> `modelNumber`
     - **Quantity** -> `quantity` (If not specified, assume `1`)
     - **Notes / Description** -> `description` (Append any text extracted from OCR or details derived from visual inspection here)

4. **Check Homebox**:
   - Use the `homebox` skill (e.g., `scripts/homebox.sh list`) to check if the component already exists in Homebox.
   - If the component **already exists**, inform the user that it exists. Do NOT increase the quantity or add a duplicate.

5. **Add to Homebox**:
   - If the component **does not exist**, use `scripts/homebox.sh create '<json_data>'` (or the Taskfile equivalent) to create it. 
   - After creating, upload the image(s) from the issue to the item using `scripts/homebox.sh attach <entity_id> <image_path>`. 
   - If there are multiple images (e.g., extracted from a zip file or uploaded separately), upload ALL of them to the Homebox entry by calling the attach command for each image. 

6. **Create Git Commit**:
   - Create an empty git commit (or commit related changes if any) to close the issue.
   - **Crucial**: The commit message MUST contain `fixes #<issue_number>` to ensure the issue is automatically closed when pushed to the repository.
   - Example: `git commit --allow-empty -m "chore: add component from issue to homebox

fixes #<issue_number>"`

## Requirements
- `gh` CLI for reading issues.
- `lit` and `tesseract` for OCR.
- `scripts/homebox.sh` for Homebox interactions.
- `unzip` for handling zip files.
