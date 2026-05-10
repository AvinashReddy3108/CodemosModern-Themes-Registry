import gzip
import hashlib
import json
import time
from pathlib import Path

from registrar.config import DISABLE_CACHE


class ResponseCache:
    def __init__(self, root: Path, ttl: int = 86400, max_size: int = 1_000_000_000):
        self.root = root
        self.ttl = ttl
        self.max_size = max_size
        self.root.mkdir(parents=True, exist_ok=True)

    def _normalize_payload(self, payload):
        if payload is None:
            return ""
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _key(self, method, url, payload):
        raw = f"{method}:{url}:{self._normalize_payload(payload)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key):
        return self.root / f"{key}.gz"

    def _read(self, path):
        try:
            return json.loads(gzip.decompress(path.read_bytes()))
        except Exception:
            return None

    def _write(self, path, data):
        path.write_bytes(gzip.compress(json.dumps(data).encode("utf-8")))

    def get(self, method, url, payload=None):
        if DISABLE_CACHE:
            return None

        key = self._key(method, url, payload)
        path = self._path(key)

        if not path.exists():
            return None

        entry = self._read(path)
        if not entry:
            return None

        return entry["data"]

    def set(self, method, url, data, payload=None):
        if DISABLE_CACHE:
            return

        key = self._key(method, url, payload)
        path = self._path(key)

        self._write(path, {"timestamp": time.time(), "data": data})
