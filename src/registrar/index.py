from registrar.logging import log
import asyncio
import hashlib
from pathlib import Path

import msgspec


class IndexManager:
    def __init__(self, path: Path | None = None):
        self._lock = asyncio.Lock()
        self.data = {"version": "v1.0.0", "themes": {"dark": [], "light": []}}

        # Load existing index if present
        if path and path.exists():
            try:
                log.debug(
                    f"Found pre-existing tracking index state file at: {path}. Hydrating dynamic memory mapping..."
                )
                raw = path.read_bytes()
                existing = msgspec.json.decode(raw)
                self.data = existing
                log.info(
                    f"Successfully loaded and structured existing database catalog index layout tracking (v{self.data.get('version')})"
                )
            except Exception as e:
                log.error(
                    f"Failed to cleanly structure localized database record elements from raw index: {e}"
                )

    async def add(self, entry):
        async with self._lock:
            self.data["themes"][entry.ui_type].append(entry)  # ty:ignore[unresolved-attribute]
            log.debug(
                f"Catalog database staging memory track modification: Appended [{entry.ui_type}] theme schema '{entry.publisher} - {entry.extension} -> {entry.theme}'"
            )

    def _bump_version(self):
        version = self.data.get("version", "v1.0.0")
        prefix, ver = version[0], version[1:]  # ty:ignore[invalid-argument-type]
        major, minor, patch = map(int, ver.split("."))  # ty:ignore[unresolved-attribute]
        patch += 1
        old_version = self.data["version"]
        self.data["version"] = f"{prefix}{major}.{minor}.{patch}"
        log.info(
            f"Index content mutated. Catalog semantic version state shifted from [{old_version}] to [{self.data['version']}]"
        )

    async def write(self, path: Path):
        log.debug(
            "Initiating sorting optimization algorithms across current theme collections..."
        )
        for ui_type in self.data["themes"]:
            self.data["themes"][ui_type].sort(  # ty:ignore[invalid-argument-type, unresolved-attribute]
                key=lambda e: (
                    e.__getattribute__("extension"),
                    e.__getattribute__("theme"),
                )
            )

        encoded = msgspec.json.encode(self.data)
        new_hash = hashlib.sha256(encoded).hexdigest()

        old_hash = None
        if path.exists():
            old_bytes = path.read_bytes()
            old_hash = hashlib.sha256(old_bytes).hexdigest()

        # Only bump version and write if content changed
        if new_hash != old_hash:
            self._bump_version()
            encoded = msgspec.json.encode(self.data)
            log.info(
                f"Flushing mutated operational records index updates cleanly to file system path target layout locations -> {path}"
            )
            await asyncio.to_thread(path.write_bytes, encoded)
