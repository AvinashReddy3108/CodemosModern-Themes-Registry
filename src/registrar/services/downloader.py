from io import BytesIO

from registrar.logging import log


class VSIXDownloader:
    def __init__(self, client):
        self.client = client

    async def download(self, ext):
        log.info(
            f"Downloading VSIX package archive: {ext.publisher}.{ext.name} (v{ext.version})"
        )
        resp = await self.client.get(ext.vsix_url)
        resp.raise_for_status()
        size_mb = len(resp.content) / (1024 * 1024)
        log.debug(
            f"Download complete for {ext.publisher}.{ext.name} ({size_mb:.2f} MB extracted to stream buffer)"
        )
        return BytesIO(resp.content)
