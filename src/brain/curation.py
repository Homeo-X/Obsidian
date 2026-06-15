"""P2 curation path: capture → route → atomic note + links → daily log."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from brain.config import Config
from brain.vault import safe_write, read_mode, next_zettel_id, atomic_write


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50].strip("-")


def capture_signal(cfg: Config, text: str, source: str = "cli") -> Path:
    """Drop raw signal into Brain/inbox/. Cheap — no reasoning."""
    now = datetime.utcnow()
    slug = _slug(text[:40])
    filename = f"sig-{now.strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    path = cfg.brain_path / "inbox" / filename

    frontmatter = {
        "created": now.isoformat(),
        "source": source,
        "status": "raw",
    }
    import yaml
    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).rstrip()
    content = f"---\n{fm_str}\n---\n\n{text}\n"

    safe_write(cfg, path, content)
    _log_event(cfg, "captured", str(path))
    return path


def route(cfg: Config, note_type: str, name: str) -> tuple[Path, str]:
    """
    Return (target_path, filing_convention) based on methodology mode.
    Consumer skills call this — no methodology special-casing in skills.
    """
    mode = read_mode(cfg)
    slug = _slug(name)

    if mode == "zettelkasten":
        zid = next_zettel_id(cfg)
        filename = f"{zid}-{slug}.md"
        target = cfg.brain_path / "notes" / filename
        convention = f"zettelkasten-id:{zid}"
    elif mode == "PARA":
        subdir = _para_subdir(note_type)
        filename = f"{slug}.md"
        target = cfg.brain_path / "notes" / subdir / filename
        convention = f"PARA:{subdir}"
    elif mode == "LYT":
        filename = f"{slug}.md"
        target = cfg.brain_path / "notes" / filename
        convention = "LYT:atomic-note"
    else:
        filename = f"{slug}.md"
        target = cfg.brain_path / "notes" / filename
        convention = "generic"

    return target, convention


def _para_subdir(note_type: str) -> str:
    mapping = {
        "project": "projects",
        "area": "areas",
        "resource": "resources",
        "archive": "archive",
    }
    return mapping.get(note_type.lower(), "resources")


def save_note(
    cfg: Config,
    inbox_path: str,
    note_type: str = "note",
    title: str | None = None,
    links: list[str] | None = None,
) -> Path:
    """
    Turn a captured inbox signal into an atomic note under Brain/notes/.
    Updates domain _index.md.
    """
    inbox_file = Path(inbox_path)
    raw_text = inbox_file.read_text(encoding="utf-8") if inbox_file.exists() else inbox_path

    from brain.frontmatter import parse as parse_fm
    fm, body = parse_fm(raw_text)

    name = title or _slug(body[:60])
    target, convention = route(cfg, note_type, name)
    target.parent.mkdir(parents=True, exist_ok=True)

    wikilinks = links or []
    link_section = ""
    if wikilinks:
        link_section = "\n\n## Links\n\n" + "\n".join(f"- [[{l}]]" for l in wikilinks)

    now = datetime.utcnow()
    new_fm = {
        "title": title or name,
        "created": now.isoformat(),
        "type": note_type,
        "status": "curated",
        "source_inbox": str(inbox_path) if inbox_file.exists() else None,
        "methodology": convention,
    }
    import yaml
    fm_str = yaml.dump(new_fm, default_flow_style=False, sort_keys=False).rstrip()
    content = f"---\n{fm_str}\n---\n\n{body.strip()}{link_section}\n"

    safe_write(cfg, target, content)
    _update_domain_index(cfg, target, note_type)
    _log_event(cfg, "saved", str(target))

    return target


def _update_domain_index(cfg: Config, note_path: Path, note_type: str) -> None:
    """Append or update the note reference in Brain/index/_index.md."""
    index_path = cfg.brain_path / "index" / "_index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    rel = note_path.relative_to(cfg.brain_path)
    wikilink = f"[[{rel}]]"

    if index_path.exists():
        current = index_path.read_text(encoding="utf-8")
        if str(rel) in current:
            return
        content = current.rstrip() + f"\n- {wikilink}\n"
    else:
        content = f"# Brain Index\n\n- {wikilink}\n"

    atomic_write(index_path, content)


def _log_event(cfg: Config, event_type: str, detail: str) -> None:
    """Append a typed event to Brain/log/YYYY-MM-DD.md."""
    today = date.today().isoformat()
    log_path = cfg.brain_path / "log" / f"{today}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().strftime("%H:%M:%S")
    line = f"- `{now}` {event_type}: {detail}\n"

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        content = existing.rstrip() + "\n" + line
    else:
        content = f"# Log {today}\n\n{line}"

    atomic_write(log_path, content)
