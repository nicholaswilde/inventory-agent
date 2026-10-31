---
name: optimize-images
description: Optimizes and compresses raw photos and images (< 500KB, max 1920x1080 resolution) in images/pending or images/processed using ImageMagick before Homebox attachment.
---

# Optimize Images Skill

Compresses and resizes raw high-resolution images or phone photos down to web-friendly sizes (< 500KB and max 1920x1080 resolution) using ImageMagick (`magick` / `convert`). Strips EXIF metadata to protect privacy and prevent database/storage bloat in Homebox.

## Guidelines

1. **Trigger**:
   - Use before attaching images to Homebox entities, after placing images in `images/pending/`, or when reviewing assets in `images/processed/`.

2. **Execution**:
   - **Preview Savings (Dry Run)**:
     ```bash
     task image:optimize DRY_RUN=1
     ```
   - **Optimize Pending and Processed Queues (In-Place)**:
     ```bash
     task image:optimize
     ```
   - **Target a Specific Directory**:
     ```bash
     task image:optimize TARGET="images/pending"
     ```
   - **Target a Single Image**:
     ```bash
     task image:optimize TARGET="path/to/image.jpg"
     ```
   - **Direct Script Execution with Custom Quality/Dimensions**:
     ```bash
     uv run scripts/optimize_image.py path/to/image.jpg --max-size-kb 400 --max-dimension 1600x900 --quality 80
     ```

3. **Key Specifications**:
   - **Max Resolution**: 1920x1080 bounding box (maintains original aspect ratio, only downsizes if larger).
   - **Max File Size**: 500KB target size limit.
   - **Metadata Stripping**: Strips EXIF and private metadata (`-strip`).
   - **Supported Extensions**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`, `.heic`.
