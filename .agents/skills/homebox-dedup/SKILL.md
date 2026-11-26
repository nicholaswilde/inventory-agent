---
name: homebox-dedup
description: Detects, deletes, and merges duplicate HomeBox entities using fuzzy name matching via `hbctl item dedup`.
---

# HomeBox Dedup Skill

Finds and removes duplicate entities in HomeBox using `hbctl item dedup` (exact + Jaccard near-duplicate matching).

## Usage

### Report Only (no changes)

```bash
hbctl item dedup [--threshold 0.8]
# or via Taskfile:
task homebox:dedup
task homebox:dedup THRESHOLD=0.7
```

### Delete Duplicates (keeps most descriptive entry)

```bash
hbctl item dedup --delete [--dry-run]
# or via Taskfile:
task homebox:dedup-delete
task homebox:dedup-delete DRY_RUN=1   # preview first
```

### Merge Quantities Then Delete

```bash
hbctl item dedup --merge [--dry-run]
# or via Taskfile:
task homebox:dedup-merge
task homebox:dedup-merge DRY_RUN=1   # preview first
```

## How It Works

1. **Exact duplicates** — case-insensitive trimmed name match.
2. **Near-duplicates** — Jaccard similarity on normalized names (stop-words, punctuation, and version numbers removed).
3. **Keeper selection** — longest name wins; ties broken by highest quantity, then first encountered.
4. **Merge** — sums quantities onto keeper via `GET -> Merge -> PUT` before deleting duplicates.

## Guidelines for Agents

- Always run with `--dry-run` (`DRY_RUN=1`) first to preview changes (`Authorization: Bearer ***` redacted).
- Use `--threshold 0.7` for more aggressive near-duplicate detection.
- Attachment merging is not automated — images remain on the deleted entity.
