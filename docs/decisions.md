# docs/decisions.md — Running decision log

## Library versions (verified against live docs/PyPI, June 2026)

| Library | Pinned in pyproject.toml | Verified source |
|---|---|---|
| fastembed | >=0.4 | qdrant.github.io/fastembed + PyPI |
| sqlite-vec | >=0.1 | alexgarcia.xyz/sqlite-vec/python.html |
| fastmcp | >=2.0 | pypi.org/project/fastmcp (v2 actively maintained) |
| watchdog | >=4.0 | python-watchdog.readthedocs.io |
| click | >=8.1 | standard CLI library |
| pyyaml | >=6.0 | standard YAML library |
| python-dotenv | >=1.0 | standard .env library |
| pytest | >=8.0 | dev dependency |
| pytest-asyncio | >=0.23 | dev dependency (MCP async) |
| ruff | >=0.9 | dev dependency |

## Embedding model

- **Model:** `BAAI/bge-base-en-v1.5`
- **Dimension:** 768
- **Runtime:** FastEmbed local ONNX (no network at inference time)
- **Rationale:** operator chose bge-base over bge-small for better recall;
  768-dim provides meaningfully higher quality than 384-dim at ~3× model size.
  This dominates recall quality and is expensive to change (full re-embed required).
  `[Medium confidence]` per spec — empirical tuning on operator's corpus recommended.

## Chunking parameters

- **Chunk size:** 1600 chars (~400 tokens at ~4 chars/token average)
- **Overlap:** 200 chars
- **Rationale:** directly from `rahilp/second-brain-obsidian-plugin` main.ts (high confidence).
  Overlap preserves context at boundaries. Notes shorter than chunk_size stored whole.

## Index store (Fork #1)

- **Decision:** Local SQLite (FTS5 + sqlite-vec in vault/.index/brain.sqlite)
- **Rationale:** operator chose local — private, zero external services, fast for tens of
  thousands of notes. Remote vector store (Cloudflare Vectorize) available as upgrade path.

## Sync mechanism (Fork #2)

- **Decision:** Both — file-watcher daemon + Claude Code PostToolUse hook
- **Watcher:** watchdog (debounced 500ms, hash-diffed) watching Brain/ + opted-in Notes/
- **Hook:** hooks/post-tool-use-reindex.sh (opt-in via .claude/settings.json)
- **Rationale:** watcher covers background/human edits; hook tightens agent-write latency.

## MCP server

- **Package:** fastmcp (standalone, v2) — preferred over mcp.server.fastmcp
- **Rationale:** fastmcp v2 is more actively maintained (70% of MCP servers use it),
  has cleaner decorator API. The mcp.server.fastmcp path is available as fallback.

## Hybrid retrieval merge strategy

- **Algorithm:** Reciprocal Rank Fusion (RRF, k=60)
- **Rationale:** parameter-free, robust, well-studied in IR. Avoids needing to calibrate
  score normalization between FTS BM25 ranks and L2 distances.
  Results are de-duplicated at note granularity (not chunk).

## Write contract boundary

- Agent writes ONLY to vault/Brain/. Any path outside raises WriteContractViolation.
- Checks use Path.resolve().relative_to() to defeat path traversal via `..`.

## Tiling thresholds

- Similarity thresholds (error: 0.90, review: 0.80) are NOT calibrated against any vault.
  These are community defaults. Calibrate with 50–100 labeled pairs before trusting merge/dedup.
  `[High confidence — verbatim caveat from claude-obsidian .vault-meta/tiling-thresholds.json]`
