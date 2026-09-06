import hashlib
from pathlib import Path

import anyio
import msgspec
from asyncer import asyncify
from msgspec import DecodeError

from registrar.logging import log
from registrar.models import ThemeEntry

# Wrap sync file write with asyncify
_write_bytes_async = asyncify(lambda path, data: path.write_bytes(data))


class ThemeIndex(msgspec.Struct):
    """Serializable index document. ThemeEntry is itself a Struct, so msgspec
    round-trips the whole document with no manual dict conversion."""

    version: str = "v1.0.0"
    themes: dict[str, list[ThemeEntry]] = msgspec.field(
        default_factory=lambda: {"dark": [], "light": []}
    )


def _theme_key(t: ThemeEntry) -> str:
    return f"{t.publisher}/{t.extension}/{t.theme}"


codec = msgspec.json.Encoder()
decoder = msgspec.json.Decoder(ThemeIndex)


class IndexManager:
    def __init__(self, path: Path | None = None):
        self._lock = anyio.Lock()
        self.data = ThemeIndex()

        if path and path.exists():
            try:
                log.debug(f"Loading existing index from {path}.")
                self.data = decoder.decode(path.read_bytes())
                log.info(f"Loaded existing index (version {self.data.version}).")
            except (DecodeError, OSError) as e:
                log.error(f"Failed to load existing index — starting fresh: {e}")

    async def add(self, entry: ThemeEntry) -> None:
        async with self._lock:
            bucket = self.data.themes[entry.ui_type]
            key = _theme_key(entry)
            if any(_theme_key(t) == key for t in bucket):
                log.debug(
                    f"Skip existing [{entry.ui_type}] theme: "
                    f"{entry.publisher}/{entry.extension} → {entry.theme}"
                )
                return
            bucket.append(entry)
            log.debug(
                f"Staged [{entry.ui_type}] theme: {entry.publisher} / {entry.extension} → {entry.theme}"
            )

    def _bump_version(self) -> None:
        version: str = self.data.version
        prefix, ver = version[0], version[1:]
        major, minor, patch = map(int, ver.split("."))
        patch += 1
        old = self.data.version
        self.data.version = f"{prefix}{major}.{minor}.{patch}"
        log.info(f"Index version bumped: {old} → {self.data.version}")

    async def write(self, path: Path) -> None:
        log.debug("Sorting theme collections before write.")
        for ui_type in self.data.themes:
            self.data.themes[ui_type].sort(key=lambda e: (e.extension, e.theme))

        encoded = codec.encode(self.data)
        new_hash = hashlib.sha256(encoded).hexdigest()

        old_hash = None
        if path.exists():
            old_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        if new_hash != old_hash:
            self._bump_version()
            encoded = codec.encode(self.data)
            log.info(f"Writing updated index to {path}.")
            await _write_bytes_async(path, encoded)
        else:
            log.info("Index content unchanged — skipping write.")
