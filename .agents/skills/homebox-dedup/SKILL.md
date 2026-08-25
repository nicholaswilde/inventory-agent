---
name: homebox-dedup
description: Detects, deletes, and merges duplicate HomeBox entities using fuzzy name matching.
---

# HomeBox Dedup Skill

Finds and removes duplicate entities in HomeBox using exact and fuzzy (Jaccard) name matching.

## Script

`scripts/homebox_dedup.py`

## Usage

### Report Only (no changes)
```bash
uv run scripts/homebox_dedup.py [--threshold 0.8]
# or via Taskfile:
task homebox:dedup
task homebox:dedup THRESHOLD=0.7
```

### Delete Duplicates (keeps most descriptive entry)
```bash
uv run scripts/homebox_dedup.py --delete [--dry-run]
# or via Taskfile:
task homebox:dedup-delete
task homebox:dedup-delete DRY_RUN=1   # preview first
```

### Merge Quantities Then Delete
```bash
uv run scripts/homebox_dedup.py --merge [--dry-run]
# or via Taskfile:
task homebox:dedup-merge
task homebox:dedup-merge DRY_RUN=1   # preview first
```

## How It Works

1. **Exact duplicates** — case-insensitive name match.
2. **Near-duplicates** — Jaccard similarity on normalized names (stop-words, punctuation, and version numbers removed).
3. **Keeper selection** — longest name wins; ties broken by highest quantity.
4. **Merge** — sums quantities on the keeper before deleting duplicates.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--threshold` | `0.8` | Similarity cutoff (0–1). Lower = more aggressive. |
| `--delete` | off | Delete duplicate entities. |
| `--merge` | off | Merge quantities before deleting (implies `--delete`). |
| `--dry-run` | off | Preview changes without executing. |

## Guidelines for Agents

- Always run with `--dry-run` first to review before deleting.
- Use `--threshold 0.7` for more aggressive near-duplicate detection.
- Attachment merging is not automated — images remain on the deleted entity. If important, manually re-attach before deleting.
