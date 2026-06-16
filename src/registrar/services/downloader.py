from io import BytesIO


from registrar.logging import log


class VSIXDownloader:
    def __init__(self, client):
        self.client = client

    async def download(self, ext) -> BytesIO:
        log.info(f"Downloading VSIX: {ext.publisher}.{ext.name} v{ext.version}")
        # Stream the response so we never hold the full body in httpx's internal
        # buffer before writing — important for large extensions.
        buf = BytesIO()
        async with self.client._client.stream("GET", ext.vsix_url) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=65_536):
                buf.write(chunk)

        size_mb = buf.tell() / (1024 * 1024)
        buf.seek(0)
        log.debug(f"Download complete: {ext.publisher}.{ext.name} ({size_mb:.2f} MB)")
        return buf
