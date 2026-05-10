from io import BytesIO

from registrar.logging import log


class VSIXDownloader:
    def __init__(self, client, cache):
        self.client = client
        self.cache = cache

    async def download(self, ext):
        log.info(f"[vsix] {ext.publisher}.{ext.name}@{ext.version}")

        path = self.cache.path(ext.publisher, ext.name, ext.version)

        cached = self.cache.get(path)
        if cached:
            log.debug("[vsix] cache hit")
            return BytesIO(cached)

        log.debug(f"[vsix] downloading {ext.vsix_url}")

        resp = await self.client.get(ext.vsix_url)
        resp.raise_for_status()

        self.cache.save(path, resp.content)

        log.info(f"[vsix] saved {path}")
        return BytesIO(resp.content)
