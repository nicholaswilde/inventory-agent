<!-- rtk-begin -->
## RTK Command Guidelines
- **Git Operations**: Prefix `git` commands with `rtk` (e.g., `rtk git status`, `rtk git diff`, `rtk git log`, `rtk git commit`, `rtk git push`).
- **GitHub CLI**: Prefix `gh` commands with `rtk` and pipe to `cat` (e.g., `rtk gh issue list | cat`, `rtk gh pr status | cat`). Always pipe to bypass interactive pagers.
- **File & Directory Inspection**: Use `rtk ls`, `rtk tree`, `rtk find`, or `rtk read` when listing or reading files for token-optimized output.
- **Searching**: Use `rtk rg` or `rg` (ripgrep) for line search pattern matching to save tokens.
- **Ripwire Operations**: Prefix `ripwire` commands with `rtk` (e.g., `rtk ripwire <dir> --for="<task>"`). Always invoke via CLI, never register or use MCP.
- **Python & UV Operations**: Prefix Python scripts and commands with `uv run`, and prefix `uv` commands with `rtk` (e.g., `rtk uv run <script.py>`, `rtk uv run <command>`, `rtk uv add`, `rtk uv sync`). Never run bare `python` or bare `uv`.
- **Build & Test Outputs**: Use `rtk err` or `rtk test` when running build/test commands to filter output to errors/failures only (e.g., `rtk test uv run pytest`).
- **Exceptions**: Inside `ctx_execute` / `ctx_batch_execute` sandbox code, skip `rtk` (only printed output enters context). Drop `rtk` when exact raw bytes or patch required (`git diff` patch).
<!-- rtk-end -->

<!-- context-mode-begin -->
## Context-Mode Routing Guidelines
- **Derive, Do Not Dump**: Do NOT use `ctx_execute_file` or `ctx_execute` to dump whole file or full config. Print only specific value, matches, count, or known line range needed.
- **Tool Call Surface**: When using MCP wrappers, call `call_mcp_tool` with `ServerName: "context-mode_context-mode"` (or `"context-mode"`) and `ToolName: "ctx_execute"`, `"ctx_execute_file"`, `"ctx_batch_execute"`, `"ctx_fetch_and_index"`, `"ctx_search"`, or `"ctx_index"`.
- **Mandatory Routing**:
  - For analyze/count/filter/compare/search/parse/transform tasks, write code with `ctx_execute` and print only final answer.
  - For analyzing/exploring inside file, use `ctx_execute_file`. Use native `read_file` only when editing requires exact bytes or small known range.
  - Use `ctx_batch_execute` for multi-command repository reconnaissance.
  - Use `ctx_execute` for shell commands whose output may exceed short fixed answer.
  - Use `ctx_fetch_and_index` for web content, then `ctx_search` to query it.
  - Return only derived answers, concise summaries, selected snippets, or file paths.
<!-- context-mode-end -->

<!-- ponytail-begin -->
## Ponytail (Lazy Senior Dev Mode) Guidelines
- **Stop at first rung that holds**:
  1. Need to build at all? (YAGNI)
  2. Already in codebase? Reuse existing helpers/utils/patterns.
  3. Stdlib does it? Use it.
  4. Native platform feature covers it? Use it.
  5. Installed dependency solves it? Use it.
  6. Can be one line? One line.
  7. Only then: write minimum working code.
- **Bug fix = root cause, not symptom**: Fix shared function/path rather than individual callers.
- **Rules**:
  - No unrequested abstractions, boilerplate, or avoidable dependencies.
  - Deletion over addition. Boring over clever. Fewest files possible.
  - Shortest working diff wins once problem understood.
  - Mark deliberate simplifications cutting real corner with `ponytail:` comment naming ceiling and upgrade path.
  - Ensure logic leaves behind ONE runnable check (assert-based demo/self-check or small test file). Trivial one-liners need none.
<!-- ponytail-end -->

<!-- caveman-begin -->
## Caveman Guidelines
Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging.
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.
<!-- caveman-end -->

<!-- codegraph-begin -->
## CodeGraph

In repositories indexed by CodeGraph (`.codegraph/` directory exists at repo root), reach for it BEFORE grep/find or reading files when exploring code:

- **MCP tool**: `codegraph_explore` answers source + call path + blast radius in one call. Dynamic-dispatch hops included. Name file or symbol in query to read current line-numbered source.
- **Shell**: `codegraph explore "<symbol names or question>"`.

If no `.codegraph/` directory exists, skip CodeGraph entirely.
<!-- codegraph-end -->

<!-- serena-begin -->
## Serena Semantic Navigation & LSP Integration
Use Serena (`serena`) MCP tools for semantic navigation, AST symbol inspection, LSP diagnostics, and project memories:
1. **Map first**: Call `get_symbols_overview` on target file instead of reading entire file.
2. **Read target symbol only**: Call `find_symbol` with `include_body: true` for target function/class/method.
3. **Check callers**: Call `find_referencing_symbols` or `find_implementations` before signature or behavior changes.
4. **Edit by symbol**: Use `replace_symbol_body`, `insert_after_symbol`, `insert_before_symbol`, or `rename_symbol`. Use standard edit for small tweaks or non-code files.
5. **Verify diagnostics**: Call `get_diagnostics_for_file` after edits to catch LSP errors before full test run.
<!-- serena-end -->

<!-- headroom-begin -->
## Headroom MCP (Context Window Compression)
Use Headroom (`headroom`) MCP tools to manage context window consumption on large payloads:
- `headroom_compress`: Shrink large tool outputs or raw data.
- `headroom_retrieve`: Retrieve original content by hash if specific details needed.
- `headroom_stats`: Monitor headroom cache usage.
<!-- headroom-end -->

<!-- ripwire-begin -->
## Ripwire CLI Guidelines
Use `ripwire` CLI (prefixed with `rtk ripwire`) for AST codebase mapping, call graphs, blast radius, and structural queries:
- **CLI First**: Always invoke `rtk ripwire <dir> [flags]` via CLI; do NOT use MCP server.
- **Task Orientation**: `rtk ripwire <dir> --for="<task>"` for ranked signatures and bodies.
- **Task Bundle**: `rtk ripwire <dir> --pack-task="<task>" --legend=compact`.
- **Stack Trace / Error**: `rtk ripwire <dir> --from-trace=FILE --legend=compact` (`-` for stdin).
- **Call Graph**: `rtk ripwire <dir> --callers=SYM`, `--callees=SYM`, `--uses=SYM`.
- **Blast Radius**: `rtk ripwire <dir> --impact=SYM --legend=compact` before changing shared code.
- **Quality Delta & Gate**: `rtk ripwire <dir> --quality-delta --legend=compact` and `--test-gate --legend=compact`.
- **Atomic Edits**: `rtk ripwire <dir> --replace-symbol-body=SYM --edit-payload=FILE` without whole-file re-reading.
<!-- ripwire-end -->

<!-- ripgrep-guidelines-begin -->
## Ripgrep Guidelines
- **Pattern Searching**: Always use `rg` (ripgrep) or `rtk rg` instead of standard `grep` to search text inside files quickly and save token output.
- **Scope**: Use `-t py` for Python files, `-l` for file listing, keep context small (`-C 1`).
<!-- ripgrep-guidelines-end -->

<!-- taplo-rules-begin -->
## Taplo TOML Rules
- **Format**: Run `taplo fmt` to format TOML files in-place (`pyproject.toml`).
- **Validation**: Run `taplo lint` to validate TOML syntax and schema.
<!-- taplo-rules-end -->

<!-- homebox-connection-begin -->
## Homebox Connection Rules
When connecting to Homebox API, strictly follow connection parameters:
1. **Credentials**: Source `HOMEBOX_IP` and `HOMEBOX_API_KEY` from local `.env` file. NEVER commit this file or output raw keys in logs.
2. **Port**: Homebox service runs on port `7745` (e.g., `http://$HOMEBOX_IP:7745`).
3. **Authentication**: Pass API key using standard Bearer token header: `-H "Authorization: Bearer $HOMEBOX_API_KEY"`.
<!-- homebox-connection-end -->

<!-- uv-rules-begin -->
## Python Tooling & Execution with `uv`
Always use `uv` to manage Python dependencies, run workflows, execute scripts, and invoke CLI tools:
- Prefix all Python commands and scripts with `uv run` or `rtk uv run` (e.g., `rtk uv run pytest`, `rtk uv run <script.py>`). Never run bare `python`, `pip`, or bare `uv`.
- Always keep `uv.lock` and `pyproject.toml` up-to-date and in sync whenever project dependencies or configurations change. Run `uv lock` or `uv sync` after modifying dependencies.
- Run tests with `rtk test uv run pytest` or `task test`.
<!-- uv-rules-end -->

<!-- taskfile-update-begin -->
## Taskfile Maintenance
When creating or modifying scripts and skills, always update `Taskfile.yml` to include or update relevant tasks for easy execution.
<!-- taskfile-update-end -->

<!-- image-optimization-begin -->
## Image Optimization & Compression
Ensure images uploaded to Homebox are web-friendly (< 500KB and max 1920x1080 resolution) to prevent database and storage bloat:
1. Run `task image:optimize` (or `uv run scripts/optimize_image.py`) to compress images in `images/pending/` or `images/processed/`.
2. Preview optimization savings with `task image:optimize DRY_RUN=1`.
3. Support target single file or custom directory via `task image:optimize TARGET="path/to/img"`.
<!-- image-optimization-end -->

<!-- document-parsing-begin -->
## Document Parsing Workflow
When parsing documents (PDF, DOCX, XLSX, invoices, manuals) to extract information:
1. Extract text with `lit parse -q --no-ocr <file>` first for rapid digital text extraction.
2. If no text extracted (e.g., scanned document or image-only PDF), fall back to `lit` built-in OCR with `lit parse -q <file>`.
3. If pdftotext available, use as secondary fallback for digital PDFs.
<!-- document-parsing-end -->

<!-- image-parsing-begin -->
## Image Parsing Workflow
When parsing images to extract text:
1. Process image with `lit`.
2. Run `tesseract` on output to extract text.
3. Fallback: use multimodal visual inspection when OCR returns insufficient text.
<!-- image-parsing-end -->

<!-- appliance-manual-begin -->
## Appliance Manual Ingestion Workflow
When processing appliance manuals or appliance-related GitHub issues:
1. Trigger via `task manual:ingest-issue ISSUE=<number>` or `task manual:ingest FILE="<url_or_path>"`.
2. Preview extraction with `DRY_RUN=1`.
3. Artifacts:
   - Generated cheat sheet: `appliances/<slug>.md`.
   - Processed manual: `images/processed/<Slug>_Manual.pdf`.
   - Homebox entity created with specs, error codes, and manual attachment.
4. Lookup: Query `appliances/<slug>.md` first before reading full PDF manual.
<!-- appliance-manual-end -->

<!-- script-tdd-begin -->
## Script Test-Driven Development (TDD)
When adding new script, ALWAYS create test for it first, then run script against test to verify functionality. When updating or modifying existing script, modify corresponding test first before making changes to script.
<!-- script-tdd-end -->

<!-- issue-management-begin -->
## GitHub Issue Management
When creating or updating GitHub issues, adhere to naming and labeling scheme:
- **Features**: Prefix title with `[feat]: ` and apply `enhancement` label.
- **Bugs**: Prefix title with `[bug]: ` and apply `bug` label.
- **Commit Closing**: GitHub issues only close automatically when commits containing `Fixes #<number>` are pushed to remote repository.
<!-- issue-management-end -->

<!-- readme-formatting-begin -->
## README Formatting
When adding or updating section and subsection headings in `README.md`, always include appropriate emoji shortcodes (e.g., `## :sparkles: Features`, `## :gear: Setup`, `## :test_tube: Testing`).
<!-- readme-formatting-end -->

<!-- api-response-handling-begin -->
## API Response Handling Guidelines
- **JSON Filtering**: Always use `jq` to filter API responses (like Homebox entities) to specific required fields (e.g., `jq '{name: .name, fields: .fields}'`). Do NOT dump full uncompressed JSON into context.
- **Context-Mode for Data**: For heavy JSON analysis, use `ctx_execute` to keep payload in sandbox and return only derived answer.
<!-- api-response-handling-end -->

<!-- sensitive-information-protection-begin -->
## Sensitive Information & PII Protection
NEVER commit or stage sensitive personal, financial, or security data to repository:
1. **Financial & Payment Data**: Never commit full or partial credit card numbers, CVVs, expiration dates, or cardholder payment records (e.g., `Visa •••• 1234`).
2. **Personal Identifiable Information (PII)**: Never commit real residential street addresses, personal phone numbers, or private personal emails. Anonymize invoice test fixtures, mock data, and examples with generic dummy placeholders (e.g., `Jane Doe`, `123 Test St`, `Visa •••• 0000`).
3. **Secrets & Credentials**: Never commit `.env` files, API keys, bearer tokens, passwords, or private encryption keys. Use `sops` (`task encrypt` / `task decrypt`) for encrypted secret storage.
4. **Explicit Staging**: Never use `git add .` when untracked secret files exist; stage explicitly by name.
5. **Permitted Identifiers**: Invoice numbers, order IDs, appliance model numbers, part numbers, and public product metadata permitted.
<!-- sensitive-information-protection-end -->
