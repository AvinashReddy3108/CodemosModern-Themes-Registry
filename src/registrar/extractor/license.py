import zipfile
from pathlib import Path


class LicenseExtractor:
    def __init__(self, client):
        self.client = client

    async def fetch_marketplace(self, url: str, target_dir: Path):
        if not url:
            return False

        try:
            resp = await self.client.get(url)
            if resp.content.strip():
                (target_dir / "LICENSE").write_bytes(resp.content)
                return True
        except Exception:
            return False

        return False

    def extract_from_vsix(self, z: zipfile.ZipFile, target_dir: Path):
        for name in z.namelist():
            base = Path(name).name.lower()
            if base.startswith("license"):
                content = z.read(name)
                if content.strip():
                    suffix = Path(name).suffix
                    (target_dir / f"LICENSE{suffix}").write_bytes(content)
                    return True
        return False
