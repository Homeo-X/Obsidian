"""brain CLI — entry point for all subcommands."""
from __future__ import annotations

import sys
from pathlib import Path

import click

from brain.config import load_config, write_default_config


@click.group()
@click.option("--vault", default=None, help="Override vault path.")
@click.pass_context
def main(ctx: click.Context, vault: str | None) -> None:
    """brain — combined second-brain: P2 curation + P1 recall."""
    ctx.ensure_object(dict)
    ctx.obj["vault"] = vault


@main.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Validate config, vault health, index integrity (chunk-map vs files), and metrics."""
    import time
    from datetime import datetime

    vault_override = ctx.obj.get("vault")
    try:
        cfg = load_config(vault_path=vault_override)
    except Exception as e:
        click.echo(f"[DEGRADED] Config error: {e}", err=True)
        sys.exit(1)

    click.echo("=== brain doctor ===")
    click.echo(f"vault_path   : {cfg.vault_path}")
    click.echo(f"model        : {cfg.model}")
    click.echo(f"embed_dim    : {cfg.embed_dim}")
    click.echo(f"chunk_size   : {cfg.chunk_size}")
    click.echo(f"chunk_overlap: {cfg.chunk_overlap}")
    click.echo(f"methodology  : {cfg.methodology}")

    issues: list[str] = []

    # Vault structure
    brain_dir = cfg.brain_path
    if not brain_dir.exists():
        issues.append(f"Brain/ missing — run `brain init`: {brain_dir}")

    for subdir in ["inbox", "notes", "index", "preferences", "log"]:
        if not (brain_dir / subdir).exists():
            issues.append(f"Brain/{subdir}/ missing")

    # Index DB presence + metrics
    index_db = cfg.index_path / "brain.sqlite"
    if not index_db.exists():
        issues.append(f"Index DB missing — run `brain reindex --all`: {index_db}")
    else:
        db_size_kb = index_db.stat().st_size // 1024
        db_mtime = datetime.fromtimestamp(index_db.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"index_size   : {db_size_kb} KB")
        click.echo(f"last_reindex : {db_mtime}")

        # Chunk-map integrity: chunks in DB that point to missing files
        try:
            from brain.index import open_index
            with open_index(cfg) as idx:
                total_chunks = idx.total_chunk_count()
                click.echo(f"total_chunks : {total_chunks}")

                cur = idx._conn.cursor()
                cur.execute("SELECT DISTINCT note_path FROM chunks")
                indexed_paths = {row[0] for row in cur.fetchall()}

            orphans = [p for p in indexed_paths if not Path(p).exists()]
            if orphans:
                issues.append(
                    f"{len(orphans)} orphan chunk(s) in index point to missing files "
                    f"— run `brain reindex --all` to repair. First: {orphans[0]}"
                )
            else:
                click.echo(f"orphan_chunks: 0 (clean)")

            # Search latency (quick 1-shot)
            from brain.embed import embed_query
            t0 = time.perf_counter()
            embed_query("test query", cfg)
            latency_ms = (time.perf_counter() - t0) * 1000
            click.echo(f"embed_latency: {latency_ms:.1f} ms")

        except Exception as e:
            issues.append(f"Index integrity check failed: {e}")

    if issues:
        for issue in issues:
            click.echo(f"[DEGRADED] {issue}")
        sys.exit(1)
    else:
        click.echo("Status       : OK")


@main.command()
@click.option("--vault-path", default=None, help="Vault directory to scaffold.")
@click.pass_context
def init(ctx: click.Context, vault_path: str | None) -> None:
    """Scaffold vault layout and write default config."""
    from brain.vault import init_vault

    vault_override = vault_path or ctx.obj.get("vault")
    if not vault_override:
        default_vault = str(Path.home() / "vault")
        vault_override = click.prompt("Vault path", default=default_vault)

    write_default_config(vault_override)
    cfg = load_config(vault_path=vault_override)
    init_vault(cfg)
    click.echo(f"Vault initialized at {cfg.vault_path}")
    click.echo("Run `brain doctor` to verify.")


@main.command()
@click.argument("text")
@click.pass_context
def capture(ctx: click.Context, text: str) -> None:
    """Drop a raw signal into Brain/inbox/."""
    from brain.curation import capture_signal

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    path = capture_signal(cfg, text)
    click.echo(f"Captured → {path}")


@main.command()
@click.argument("inbox_path")
@click.option("--type", "note_type", default="note", help="Note type for routing.")
@click.option("--title", default=None, help="Note title (slug if omitted).")
@click.option("--links", default="", help="Comma-separated wikilink targets.")
@click.pass_context
def save(ctx: click.Context, inbox_path: str, note_type: str, title: str | None, links: str) -> None:
    """Route a captured signal to an atomic note under Brain/notes/."""
    from brain.curation import save_note

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    link_list = [l.strip() for l in links.split(",") if l.strip()]
    path = save_note(cfg, inbox_path, note_type=note_type, title=title, links=link_list)
    click.echo(f"Saved → {path}")


@main.command()
@click.argument("query")
@click.option("-k", default=5, help="Number of results.")
@click.pass_context
def find(ctx: click.Context, query: str, k: int) -> None:
    """Hybrid semantic + keyword search over the vault."""
    from brain.search import hybrid_search
    from brain.index import open_index

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    with open_index(cfg) as idx:
        results = hybrid_search(idx, cfg, query, k=k)

    if not results:
        click.echo("No results.")
        return
    for r in results:
        click.echo(f"\n[{r['score']:.3f}] {r['note_path']}")
        click.echo(f"  {r['snippet'][:200]}…")
        click.echo(f"  ⚠ pointer — read file before acting")


@main.command()
@click.option("--all", "all_files", is_flag=True, help="Full rebuild from all Markdown files.")
@click.argument("path", required=False)
@click.pass_context
def reindex(ctx: click.Context, all_files: bool, path: str | None) -> None:
    """Rebuild the search index from Markdown files."""
    from brain.index import rebuild_index, reindex_file, open_index

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    if all_files:
        click.echo("Rebuilding full index…")
        rebuild_index(cfg)
        click.echo("Done.")
    elif path:
        with open_index(cfg) as idx:
            reindex_file(idx, cfg, Path(path))
        click.echo(f"Reindexed {path}")
    else:
        click.echo("Specify --all or a file path.", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Start the file-watcher daemon (debounced re-embed on save)."""
    from brain.watch import start_watcher

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    click.echo(f"Watching {cfg.brain_path} (debounce {cfg.debounce_ms}ms)…")
    start_watcher(cfg)


@main.command()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Launch the MCP server exposing search + save + recall_preferences."""
    from brain.mcp_server import run_server

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    run_server(cfg)


@main.command()
@click.pass_context
def dream(ctx: click.Context) -> None:
    """Run the deterministic memory accretion pass (no LLM)."""
    from brain.memory import run_dream_pass

    cfg = load_config(vault_path=ctx.obj.get("vault"))
    result = run_dream_pass(cfg)
    click.echo(f"Dream pass complete: {result}")
