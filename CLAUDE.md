# CLAUDE.md — Operating contract for brain sessions

This file is the authoritative contract for all Claude Code sessions operating on this vault.
Read it before taking any action.

---

## THE CONTRACT (C1–C7 — never violate)

**C1 — Write contract.** You write ONLY inside `vault/Brain/`. `vault/Notes/` is read-only to
you except files explicitly opted-in via `_brain.yaml notes.read_paths`. Never edit, move, or
delete anything under `vault/Notes/`.

**C2 — Derived data is disposable.** `vault/.index/` and rebuildable parts of
`vault/.vault-meta/` are reconstructable from Markdown. Never treat them as source of truth.

**C3 — No LLM in the memory-mutation algorithm.** `brain dream` uses counters and file moves
only. You may detect signals and apply rules, but never directly mutate `Brain/preferences/`.
Call `brain dream` to run the accretion pass.

**C4 — Re-embed on change, full-replace.** On a note change, old chunks are deleted and
re-embedded. Never append duplicate chunks. The watcher handles this automatically.

**C5 — Atomic file writes.** All vault writes go through `vault.safe_write()` (temp → fsync →
rename). Never write directly.

**C6 — No secrets in vault or Git.** API keys live in `~/.config/brain/.env` (mode 600), never
in `vault/` or the repo.

**C7 — Verifier gate before commit of curated content.** Run `.claude/agents/verifier.md`
before committing a curated workstream.

---

## Vault layout

```
vault/
├── Brain/                    ← AGENT-WRITABLE (only here)
│   ├── _brain.yaml           ← schema, thresholds, read_paths
│   ├── inbox/                ← raw captured signals (pre-curation)
│   ├── notes/                ← atomic curated notes (one idea per file)
│   ├── index/                ← MOCs / _index.md per domain (navigation)
│   ├── preferences/          ← deterministic memory output (dream pass only)
│   └── log/                  ← append-only daily event log
├── Notes/                    ← OPERATOR-OWNED (read-only to you)
├── .index/                   ← DERIVED (SQLite FTS5 + vec; delete + rebuild anytime)
└── .vault-meta/              ← counters, thresholds, mode.json
```

---

## Navigation rule (index-first, token-efficient)

1. Read `vault/Brain/index/_index.md` first to discover domains.
2. Read the relevant `Brain/index/<domain>/_index.md` to find specific notes.
3. Direct-read the specific Markdown file to operate on it.

**Never scan the full tree.** This keeps token cost bounded as the vault grows.

---

## Retrieval policy (friction #2)

- **Discovery** ("what do I know about X", "find related notes") → use `brain find "<query>"`
  or the `search` MCP tool. Results are **pointers only** — read the live file before acting.
- **Operate on a known file** → direct file read. The index never overrides the live file.
- The index is always stale relative to the filesystem; always read the Markdown, not the embedding.

---

## CLI surface

```bash
brain --help                         # all commands
brain init                           # scaffold vault
brain doctor                         # health check
brain capture "<text>"               # drop raw signal → Brain/inbox/
brain save <inbox_path>              # route to atomic note → Brain/notes/
brain find "<query>" [-k N]          # hybrid search (discovery only)
brain reindex --all                  # full rebuild from Markdown
brain reindex <path>                 # single-file reindex
brain watch                          # start file-watcher daemon
brain mcp                            # start MCP server
brain dream                          # deterministic memory accretion pass
```

---

## Slash commands (`.claude/skills/`)

- `/capture <text>` — capture a raw signal to inbox
- `/save <path>` — curate an inbox signal to an atomic note
- `/find <query>` — hybrid search
- `/daily` — show today's log

---

## Pre-commit verifier (C7)

Before committing curated content, invoke `.claude/agents/verifier.md`.
The verifier is **read-only** (Read/Grep/Glob only) and returns tiered findings:
- **BLOCKER** — must fix before commit
- **HIGH** — strongly recommended fix
- **MEDIUM** — consider fixing
- **LOW** — informational

Only commit after no BLOCKER findings.

---

## Key invariants to check before any write

1. Is the target path under `vault/Brain/`? If not, refuse.
2. Does the write go through `vault.safe_write(cfg, path, content)`? If not, use it.
3. Is this a preference mutation? If yes, call `brain dream` instead.
4. Is this a secret? If yes, put it in `~/.config/brain/.env`, not here.
