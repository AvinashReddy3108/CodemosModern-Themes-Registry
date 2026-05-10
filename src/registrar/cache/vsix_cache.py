from pathlib import Path

from registrar.config import DISABLE_CACHE


class VSIXCache:
    def __init__(self, root: Path):
        self.root = root

    def path(self, publisher, name, version):
        p = self.root / publisher / name
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{version}.vsix"

    def get(self, path: Path):
        if DISABLE_CACHE:
            return None

        if path.exists():
            return path.read_bytes()
        return None

    def save(self, path: Path, content: bytes):
        if DISABLE_CACHE:
            return

        path.write_bytes(content)

        # prune older
        for f in path.parent.glob("*.vsix"):
            if f != path:
                f.unlink(missing_ok=True)
