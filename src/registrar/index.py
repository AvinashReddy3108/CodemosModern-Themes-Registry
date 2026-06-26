import hashlib
from pathlib import Path

import anyio
import msgspec
from asyncer import asyncify

from registrar.logging import log

# Wrap sync file write with asyncify
_write_bytes_async = asyncify(lambda path, data: path.write_bytes(data))


class IndexManager:
    def __init__(self, path: Path | None = None):
        self._lock = anyio.Lock()
        self.data: dict = {"version": "v1.0.0", "themes": {"dark": [], "light": []}}

        if path and path.exists():
            try:
                log.debug(f"Loading existing index from {path}...")
                existing = msgspec.json.decode(path.read_bytes())
                self.data = existing
                log.info(f"Loaded existing index (version {self.data.get('version')}).")
            except Exception as e:
                log.error(f"Failed to load existing index — starting fresh: {e}")

    async def add(self, entry) -> None:
        async with self._lock:
            self.data["themes"][entry.ui_type].append(entry)
            log.debug(
                f"Staged [{entry.ui_type}] theme: {entry.publisher} / {entry.extension} → {entry.theme}"
            )

    def _bump_version(self) -> None:
        version: str = self.data.get("version", "v1.0.0")
        prefix, ver = version[0], version[1:]
        major, minor, patch = map(int, ver.split("."))
        patch += 1
        old = self.data["version"]
        self.data["version"] = f"{prefix}{major}.{minor}.{patch}"
        log.info(f"Index version bumped: {old} → {self.data['version']}")

    async def write(self, path: Path) -> None:
        log.debug("Sorting theme collections before write...")
        for ui_type in self.data["themes"]:
            self.data["themes"][ui_type].sort(key=lambda e: (e.extension, e.theme))

        encoded = msgspec.json.encode(self.data)
        new_hash = hashlib.sha256(encoded).hexdigest()

        old_hash = None
        if path.exists():
            old_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        if new_hash != old_hash:
            self._bump_version()
            encoded = msgspec.json.encode(self.data)
            log.info(f"Writing updated index to {path}...")
            # Use asyncer asyncify wrapper instead of anyio.to_thread.run_sync
            await _write_bytes_async(path, encoded)
        else:
            log.info("Index content unchanged — skipping write.")
