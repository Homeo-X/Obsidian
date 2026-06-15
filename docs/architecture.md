# Combined Second-Brain Architecture: Curation (P2) + Recall (P1) over an Obsidian Vault

A synthesis sketch drawn from direct inspection of four repositories, not their READMEs.
Confidence labels mark what is observed in source vs. inferred.

**Sources inspected** (shallow-cloned `dev`/`main`, June 2026):

| Repo | Role in synthesis | What it actually is (verified) |
|---|---|---|
| `rahilp/second-brain-obsidian-plugin` | P1 — sync/chunk/embed | Single-file Obsidian TS plugin; chunked sync to a self-hosted MCP worker |
| `itechmeat/open-second-brain` | P1+P2 reference spine | Deterministic memory core + MCP server + rebuildable index; multi-runtime adapters |
| `AgriciDaniel/claude-obsidian` | P2 — self-organizing curation | Claude-Code-operated vault; methodology modes, verifier gate, semantic tiling |
| `coleam00/second-brain-starter` | Blueprint only (not code) | A *PRD generator* skill — produces a build spec, ships no running system |

---

## 1. The core claim

P1 and P2 are not competing designs. They occupy different layers of one stack and share a
single primitive: **plain Markdown files in a vault**. That shared substrate is why they
compose — point P1's embedder at the same files P2 writes.

- **P2 = write/curation path.** An agent creates, links, routes, and organizes Markdown.
- **P1 = read/recall path.** A derived index makes that Markdown semantically retrievable at scale.

Division of labor: *P2 maintains the vault; P1 makes it queryable.* Neither alone is sufficient —
P2 without P1 degrades to the agent grepping raw files (fails past a few hundred notes); P1
without P2 is read-only and never curates.

**[High confidence]** — directly supported: `open-second-brain` already runs both layers over
one vault; `claude-obsidian` runs P2 with a tiling index; `rahilp` runs P1 against a vault it
doesn't curate.

---

## 2. Layered model

```text
┌──────────────────────────────────────────────────────────────┐
│  Agent runtime (Claude Code / any MCP client)                 │
│    discovery via semantic search · operation via direct read  │
└───────────────┬──────────────────────────┬───────────────────┘
                │ MCP (canonical contract)  │
        ┌───────▼────────┐         ┌────────▼─────────┐
        │  P2 CURATION   │         │  P1 RECALL       │
        │  (writer)      │         │  (reader)        │
        │ ingest→route→  │         │ chunk→embed→     │
        │ link→verify    │         │ hybrid search    │
        └───────┬────────┘         └────────┬─────────┘
                │ writes (bounded)           │ reads + indexes
                ▼                            ▼
        ┌──────────────────────────────────────────────┐
        │  VAULT (plain Markdown — source of truth)     │
        │   Brain/        ← agent-writable (contract)   │
        │   Notes/        ← operator-owned (read-only)  │
        │   .index/       ← DERIVED, rebuildable        │
        │   .vault-meta/  ← deterministic counters      │
        └──────────────────────────────────────────────┘
```

Adapted from `open-second-brain/docs/architecture.md` (layered core + adapters) and its
`how-it-works.md` vault layout. **[High confidence]** on layout; the MCP-as-shared-contract
choice is its explicit design (`"the o2b mcp MCP server is the canonical way for any runtime
to reach the writer/reader tools"`).

---

## 3. The vault: one substrate, three write classes

The non-negotiable rule that makes the combination safe is a **write contract**.

```text
<vault>/
├── Brain/                  # AGENT-WRITABLE — the only place P2 writes
│   ├── _brain.yaml         #   schema, thresholds, retention, read-paths
│   ├── inbox/              #   raw captured signals (pre-curation)
│   ├── notes/              #   atomic curated notes (one idea per file)
│   ├── index/              #   MOCs / _index.md per domain (navigation)
│   └── log/                #   append-only daily event log (YYYY-MM-DD.md)
├── Notes/                  # OPERATOR-OWNED — agent reads only via opt-in markers
├── .index/                 # DERIVED — SQLite FTS5 + vector; delete & rebuild anytime
└── .vault-meta/            # DETERMINISTIC STATE — counters, tiling thresholds, mode
```

Three classes, three rules:
1. **Agent-writable** (`Brain/`): P2 writes here and nowhere else. Bounds blast radius.
2. **Operator-owned** (`Notes/`): agent scans read-only, only files opted in via path-list or
   an inline marker (`open-second-brain` uses `@osb`). Prevents the agent clobbering your notes.
3. **Derived** (`.index/`, parts of `.vault-meta/`): rebuildable from 1+2. Never source of truth.

**[High confidence]** — `Brain/`-only write contract and the derived/rebuildable index are
explicit in `open-second-brain`. The operator-owned read-only class is its `notes.read_paths`
mechanism.

---

## 4. P2 — Curation path (the writer)

Pipeline, drawn from `claude-obsidian`'s agent set and `open-second-brain`'s capture flow:

```text
source/conversation
   │
   ▼  CAPTURE         drop raw signal → Brain/inbox/  (cheap, no reasoning)
   ▼  ROUTE           wiki-mode.py route <type> <name>  → file under chosen methodology
   ▼  WRITE           atomic note + wikilinks; update domain _index.md / MOC
   ▼  VERIFY          read-only verifier agent: BLOCKER/HIGH/MEDIUM/LOW, file:line cites
   ▼  COMMIT          only after verifier pass (advisory but gated by convention)
```

Design points worth copying:
- **Methodology routing is data, not code.** `claude-obsidian` selects generic / LYT / PARA /
  Zettelkasten from `.vault-meta/mode.json` and routes via one script; consumer skills stay
  mode-agnostic. **[High confidence]** — observed in `CLAUDE.md` + `scripts/wiki-mode.py` reference.
- **Verifier is read-only and runs pre-commit.** It inspects `git diff --cached`, cannot modify,
  returns tiered findings. This is the gate that catches bad writes before they enter history.
  **[High confidence]** — `claude-obsidian/agents/verifier.md`, `CLAUDE.md §"Pre-commit verifier"`.
- **Index-first navigation.** Agent reads `index.md` → domain `_index.md` → drills to pages,
  rather than scanning the tree. Keeps token cost bounded as the vault grows.

---

## 5. P1 — Recall path (the reader)

Two viable index backends observed; pick by deployment:

| Backend | Source repo | Where it runs | Trade-off |
|---|---|---|---|
| **Local SQLite FTS5 + vector** | `open-second-brain` (`.index/brain.sqlite`, FTS5 + sqlite-vec); `coleam00` blueprint (FastEmbed ONNX + SQLite) | On-device, no network | Simplest, private, fast for ≤ tens of thousands of chunks |
| **Remote vector store** | `rahilp` (Cloudflare Workers + Vectorize) | Self-hosted edge | Multi-device sync, scales, but adds an external service + latency |

**Chunking + sync — the part that actually breaks, and how `rahilp` solves it** **[High confidence]**:
- Chunk long notes (`rahilp` default **1600 chars ≈ 400 tokens, 200-char overlap**); short notes
  stored whole. Overlap preserves context at boundaries.
- **Persist per-chunk IDs in the note** so re-sync maps to existing entries.
- **Re-embed on change via full replace** — `rahilp` switched from `/append` to `/update`
  (replace content + re-embed cleanly) precisely to avoid stale/duplicated embeddings. If the
  note shrinks, surplus chunk IDs are pruned.

Hybrid retrieval (`coleam00` blueprint, `open-second-brain` FTS5+vec): keyword (FTS) ∪ semantic
(vector), merged/re-ranked. Keyword catches exact terms vectors miss; vectors catch paraphrase.

---

## 6. The four friction points and how this design resolves them

These are the failures that actually bite when you wire P1 to P2. Each maps to a concrete mechanism.

1. **Index staleness — the dominant bug.** **[High confidence]**
   P2 writes constantly; if re-embedding isn't triggered on write, the agent saves a note and
   then can't semantically recall it.
   → *Resolve:* fire re-embed on file change (Obsidian save event in `rahilp`; a `PostToolUse`/
   post-write hook in a Claude-Code setup), debounced, hash-diffed to skip unchanged chunks,
   full-replace per `rahilp`'s `/update`.

2. **Two retrieval paths, no precedence.** **[Medium confidence]**
   The agent now has direct file-read *and* semantic search and may read redundantly or trust a
   stale embedding over the fresh file.
   → *Resolve:* explicit policy — **semantic search for discovery** ("what do I know about X"),
   **direct read for operating on a known file**. The index never overrides the file.

3. **Chunking vs. atomic notes.** **[Medium confidence]**
   P1 chunks long notes; chunk boundaries ignore wikilinks, so retrieval can surface a fragment
   stripped of its backlinks.
   → *Resolve:* keep notes **atomic (one idea ⇒ one chunk)** so chunk == note == link target;
   or embed at note granularity with link metadata attached. P2's Zettelkasten/LYT modes already
   push toward atomicity.

4. **Write contention / hallucinated memory.** **[High confidence]**
   If a "learning" layer also writes (preferences, derived rules), an LLM in that loop can invent
   memory or race the curator.
   → *Resolve:* `open-second-brain`'s pattern — a **deterministic accretion pass** (counters,
   thresholds, atomic file moves, **no LLM inside the mutation algorithm**) on a separate
   namespace (`Brain/preferences/` with an explicit `unconfirmed → confirmed → quarantine →
   retired` lifecycle). The LLM detects signals and applies rules; it never mutates memory directly.

---

## 7. Reference data flow (end to end)

```text
 ┌── WRITE (P2) ───────────────────────────────────────────────┐
 │ conversation ─signal→ Brain/inbox/ ─route→ Brain/notes/<atomic>.md
 │                                   └─link→ Brain/index/<domain>/_index.md
 │ on commit: verifier (read-only, tiered) ──gate──► git commit │
 └──────────────────────┬───────────────────────────────────────┘
                        │ file-change event (hook / plugin save)
                        ▼
 ┌── INDEX (P1) ───────────────────────────────────────────────┐
 │ changed file → chunk(1600/200) → re-embed(full replace) →    │
 │ .index/brain.sqlite  [FTS5 ∪ vector]    (DERIVED, rebuildable)│
 └──────────────────────┬───────────────────────────────────────┘
                        │ MCP query surface
                        ▼
 ┌── RECALL (agent) ───────────────────────────────────────────┐
 │ "what do I know about X" → hybrid search → note refs →       │
 │ agent direct-reads the live files (not the embedding) → acts │
 └──────────────────────────────────────────────────────────────┘

 ┌── MEMORY (deterministic, parallel) ─────────────────────────┐
 │ repeat signals → nightly accretion pass (counters, no LLM) → │
 │ Brain/preferences/  (unconfirmed→confirmed→quarantine→retired)│
 └──────────────────────────────────────────────────────────────┘
```

---

## 8. Minimal build order (if implementing)

1. **Vault + write contract.** Define `Brain/` (agent-writable) vs `Notes/` (read-only). Nothing
   else matters if this boundary isn't enforced first.
2. **P2 capture + atomic write + index-first read.** Get curation correct before adding recall.
3. **P1 index with change-triggered re-embed.** SQLite FTS5 + local ONNX embeddings (FastEmbed)
   is the lowest-friction start; add a remote vector store only when multi-device sync is needed.
4. **Hybrid retrieval + the discovery-vs-operate policy.**
5. **Deterministic memory pass** last — it's an optimization on top of a working brain, not a
   prerequisite.

---

## 9. Caveats and what remains unverified

- **`coleam00/second-brain-starter` ships no system.** It generates a PRD. Treat its architecture
  as a blueprint to read, not code to merge. **[High confidence]** — confirmed in its `SKILL.md`.
- **Tiling thresholds are uncalibrated.** `claude-obsidian` itself flags its semantic-tiling bands
  (error 0.90 / review 0.80, `nomic-embed-text`) as *not calibrated against any vault*; it cites
  community defaults (~0.75) and expects false negatives at 0.80. Any similarity-gated merge/dedup
  needs vault-specific calibration (50–100 labeled pairs) before you trust it. **[High confidence]**
  — verbatim caveat in `.vault-meta/tiling-thresholds.json`.
- **Per-repo maturity / commit health not audited.** I inspected structure and core logic, not
  test coverage, issue backlog, or whether each runs end-to-end. **This needs verification** before
  depending on any single repo in production.
- **Embedding model choice is left open.** `rahilp` uses a remote embedder (Vectorize), `coleam00`
  blueprint uses local FastEmbed ONNX, `claude-obsidian` references `nomic-embed-text`. Recall
  quality is dominated by this choice and by chunking — both need empirical tuning on *your* corpus,
  not defaults. **[Medium confidence]** on it being the dominant quality lever.
