---
name: issue-to-homebox
description: Processes a GitHub issue to extract item details from images, adds the item to Homebox if it doesn't exist, and creates a commit to close the issue.
---

# Issue to Homebox Skill

This skill guides the agent to process a GitHub issue, extract component information from attached images, and add the item to Homebox. 

## Workflow

1. **Read Issue**: 
   - Run `gh issue view <issue_number> | cat` to read the issue title, body, and extract any image URLs.

2. **Download & Process Images**: 
   - Download the attached image(s) (e.g., using `curl -O`).
   - Follow the repository's image parsing workflow: Process the image with `lit`, and then run `tesseract` on the output to extract text.

3. **Identify Item Details**:
   - Determine the component's name, description, and other relevant fields from the extracted text.
   - If a quantity is specified in the issue or text, use it. Otherwise, assume the quantity is `1`.

4. **Check Homebox**:
   - Use the `homebox` skill (e.g., `scripts/homebox.sh list`) to check if the component already exists in Homebox.
   - If the component **already exists**, inform the user that it exists. Do NOT increase the quantity or add a duplicate.

5. **Add to Homebox**:
   - If the component **does not exist**, use `scripts/homebox.sh create '<json_data>'` (or the Taskfile equivalent) to create it. 
   - After creating, use `scripts/homebox.sh attach <entity_id> <image_path>` to upload the image from the issue to the item. 

6. **Create Git Commit**:
   - Create an empty git commit (or commit related changes if any) to close the issue.
   - **Crucial**: The commit message MUST contain `fixes #<issue_number>` to ensure the issue is automatically closed when pushed to the repository.
   - Example: `git commit --allow-empty -m "chore: add component from issue to homebox

fixes #<issue_number>"`

## Requirements
- `gh` CLI for reading issues.
- `lit` and `tesseract` for OCR.
- `scripts/homebox.sh` for Homebox interactions.
