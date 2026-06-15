# brain — Combined Second-Brain

Local-first AI second brain: **P2 curation** (write/organize) + **P1 recall** (hybrid search) over a plain Markdown Obsidian vault.

## Quick start (< 10 minutes)

### 1. Install

```bash
# requires Python 3.11+ and uv
curl -LsSf https://astral.sh/uv/install.sh | sh  # if uv not installed
make install
```

### 2. Initialize your vault

```bash
brain init --vault-path ~/my-vault
```

This scaffolds `Brain/`, `Notes/`, `.index/`, `.vault-meta/`, and writes a default config to
`~/.config/brain/config.yaml`.

### 3. Check health

```bash
brain doctor
```

### 4. Capture and save a note

```bash
brain capture "Atomic notes make retrieval easier than long documents"
# → drops to Brain/inbox/sig-....md

brain save Brain/inbox/sig-<date>-atomic-notes....md --title "atomic-notes" --links "[[Zettelkasten]]"
# → creates Brain/notes/atomic-notes.md + updates index
```

### 5. Search

```bash
brain find "small focused notes" -k 5
# → hybrid FTS + semantic results (pointers — read the live file before acting)
```

### 6. Start the watcher (keep index fresh)

```bash
brain watch
# → debounced 500ms; re-embeds on every save automatically
```

### 7. Run the MCP server

```bash
brain mcp
```

Add to your Claude config (`~/.claude.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "brain": {
      "command": "uv",
      "args": ["run", "brain", "mcp"],
      "cwd": "/path/to/this/repo"
    }
  }
}
```

MCP tools exposed: `search(query, k)`, `save(content, type, links)`, `recall_preferences(scope)`.

### 8. Run the deterministic memory pass

```bash
brain dream
# → accretes preferences from Brain/inbox/ signals; no LLM involved
```

---

## Configuration

`~/.config/brain/config.yaml`:

```yaml
vault_path: ~/my-vault
model: BAAI/bge-base-en-v1.5
embed_dim: 768
chunk_size: 1600
chunk_overlap: 200
debounce_ms: 500
thresholds:
  memory_confirm: 3
  memory_quarantine: 5
notes:
  read_paths: []   # relative paths under vault/ to also index (read-only)
methodology: generic   # generic | LYT | PARA | zettelkasten
```

Secrets (`~/.config/brain/.env`, mode 600 — never in vault or repo):

```
# No API keys needed for local-only operation
```

---

## Development

```bash
make test       # run all tests
make lint       # ruff check + format check
make lint-fix   # auto-fix lint issues
make doctor     # vault health check
```

---

## Architecture

See `docs/architecture.md` for the full layered design and `docs/decisions.md` for every
non-obvious library/API/config choice with rationale.

### Key invariants

| Code | Rule |
|---|---|
| C1 | Agent writes only inside `vault/Brain/` |
| C2 | `.index/` is derived — delete and rebuild anytime |
| C3 | No LLM inside `memory.py` |
| C4 | Re-embed on change, full-replace (no stale chunks) |
| C5 | All writes are atomic (temp → fsync → rename) |
| C6 | No secrets in vault or Git |
| C7 | Verifier gate before committing curated content |
