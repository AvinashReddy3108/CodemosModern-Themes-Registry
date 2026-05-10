from registrar.logging import log
from registrar.models import Extension
from registrar.utils.file import safe_filename


class MetadataService:
    def __init__(self, client, api_url: str, cache):
        self.client = client
        self.api_url = api_url
        self.cache = cache

    def _build_payload(self, extension_id: str):
        return {
            "filters": [
                {
                    "criteria": [{"filterType": 7, "value": extension_id}],
                    "pageNumber": 1,
                    "pageSize": 1,
                }
            ],
            "flags": 870,
        }

    async def fetch(self, extension_id: str):
        log.debug(f"[metadata] fetch {extension_id}")

        payload = self._build_payload(extension_id)

        cached = self.cache.get("POST", self.api_url, payload)
        if cached:
            log.debug(f"[metadata] cache hit {extension_id}")
            return cached

        log.info(f"[metadata] cache miss {extension_id}")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json; charset=utf-8; api-version=7.2-preview.1",
        }

        resp = await self.client.post(
            self.api_url,
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()

        data = resp.json()

        self.cache.set("POST", self.api_url, data, payload)

        return data

    def parse(self, data: dict, extension_id: str) -> Extension:
        try:
            ext = data["results"][0]["extensions"][0]
            version = ext["versions"][0]

            log.debug(f"[metadata] parsed {extension_id}")

            return Extension(
                publisher=safe_filename(ext["publisher"]["displayName"]),
                name=safe_filename(ext["displayName"]),
                version=version["version"],
                vsix_url=next(
                    f["source"]
                    for f in version["files"]
                    if "VSIXPackage" in f["assetType"]
                ),
                license_url=next(
                    (
                        f["source"]
                        for f in version["files"]
                        if "License" in f["assetType"]
                    ),
                    None,
                ),
            )

        except Exception as e:
            log.error(f"[metadata] parse failed {extension_id}: {e}")
            raise
