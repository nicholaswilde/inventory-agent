---
name: issue-to-homebox
description: Processes a GitHub issue to extract item details from images or zips, adds the item(s) to Homebox if they don't exist, and creates a commit to close the issue.
---

# Issue to Homebox Skill

This skill guides the agent to process a GitHub issue, extract item details, map them to HomeBox fields, process any attached images or zip files, and add the item(s) to Homebox. 

## Workflow

1. **Read Issue**: 
   - Run `gh issue view <issue_number> --json title,body -q '{title,body}'` (or simply pipe to `cat`) to read the issue title, body, and extract any file URLs (images or zip files).

2. **Download & Process Files**: 
   - Download the attached file(s) from the issue. **Crucial**: Because GitHub attachment links often redirect, you must use `curl -L` or `curl -sL -o <filename>` to follow redirects and download the actual file, not an HTML page.
   - **If the file is a zip archive**: Extract the `.zip` file into a temporary directory first, then process all images inside.
   - Follow the repository's primary image parsing workflow for each image: Process the image with `lit`, and then run `tesseract` on the output to extract text.
   - **Vision Fallback**: If the OCR pipeline fails to extract meaningful text, or if the component's type/model is unclear from the text alone, use your native multimodal capabilities (e.g. via `view_file` tool on the image) to visually inspect the component or board to identify its type, manufacturer, and model.

3. **Identify Item Details & Map to Homebox Fields**:
   - Determine if the provided images represent a **single item** or **multiple distinct items**. If a zip file contains images of completely different components, you must create a separate Homebox entry for each distinct component.
   - If the issue body contains structured fields (from the template), map them to the Homebox JSON payload:
     - **Item Name** -> `name`
     - **Manufacturer** -> `manufacturer`
     - **Model Number** -> `modelNumber`
     - **Quantity** -> `quantity` (If not specified, assume `1`)
     - **Notes / Description** -> `description` 
   - **Unstructured / Missing Info**: If the issue does not follow the structured template, or if fields are blank (e.g. just a title and a zip upload), use OCR and your visual identification to generate an appropriate `name`, `manufacturer`, `modelNumber`, and `description` for the Homebox JSON payload yourself.

4. **Check Homebox**:
   - Use the `homebox` skill (e.g., `scripts/homebox.sh list`) to check if the component(s) already exist in Homebox.
   - If a component **already exists**, inform the user that it exists. Do NOT increase the quantity or add a duplicate.

5. **Add to Homebox**:
   - For each new component, use `scripts/homebox.sh create '<json_data>'` (or the Taskfile equivalent) to create it. 
   - After creating, upload the corresponding image(s) to the item using `scripts/homebox.sh attach <entity_id> <image_path>`. 
   - If there are multiple images of the *same* component, attach ALL of them to that specific Homebox entry by calling the attach command repeatedly. 

6. **Create Git Commit**:
   - Create an empty git commit (or commit related changes if any) to close the issue.
   - **Crucial**: The commit message MUST contain `fixes #<issue_number>` to ensure the issue is automatically closed when pushed to the repository.
   - Example: `git commit --allow-empty -m "chore: add components from issue to homebox

fixes #<issue_number>"`

## Requirements
- `gh` CLI for reading issues.
- `lit` and `tesseract` for OCR.
- `scripts/homebox.sh` for Homebox interactions.
- `unzip` for handling zip files.
