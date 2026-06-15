"""Debounced file-watcher daemon: change → re-embed (C4 staleness killer)."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from brain.config import Config


class _DebounceHandler(FileSystemEventHandler):
    def __init__(self, cfg: Config, debounce_ms: int) -> None:
        super().__init__()
        self._cfg = cfg
        self._delay = debounce_ms / 1000.0
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str) -> None:
        with self._lock:
            if path in self._timers:
                self._timers[path].cancel()
            t = threading.Timer(self._delay, self._process, args=(path,))
            self._timers[path] = t
            t.start()

    def _process(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)

        p = Path(path)
        if not p.suffix == ".md":
            return

        from brain.index import open_index, reindex_file
        try:
            with open_index(self._cfg) as idx:
                if p.exists():
                    reindex_file(idx, self._cfg, p)
                    print(f"[watch] reindexed {p.name}")
                else:
                    idx.delete_note(p)
                    print(f"[watch] removed {p.name}")
        except Exception as e:
            print(f"[watch] error processing {path}: {e}")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)
            self._schedule(event.dest_path)


def start_watcher(cfg: Config) -> None:
    """Block: watch Brain/ (+ opted-in Notes/ paths) and re-index on changes."""
    handler = _DebounceHandler(cfg, cfg.debounce_ms)
    observer = Observer()
    observer.schedule(handler, str(cfg.brain_path), recursive=True)

    for rel in cfg.notes_read_paths:
        watch_path = cfg.vault_path / rel
        if watch_path.exists():
            observer.schedule(handler, str(watch_path), recursive=True)
            print(f"[watch] also watching {watch_path}")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
