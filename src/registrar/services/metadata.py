from registrar.logging import log
from registrar.models import Extension
from registrar.utils.file import safe_filename


class MetadataService:
    def __init__(self, client, api_url: str):
        self.client = client
        self.api_url = api_url

    def _build_payload(self, extension_id: str) -> dict:
        return {
            "filters": [
                {
                    "criteria": [{"filterType": 4, "value": extension_id}],
                    "pageNumber": 1,
                    "pageSize": 1,
                }
            ],
            "flags": 870,
        }

    async def fetch(self, extension_id: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json; charset=utf-8; api-version=7.2-preview.1",
        }
        log.debug(f"Querying Marketplace metadata for: {extension_id}")
        resp = await self.client.post(
            self.api_url, headers=headers, json=self._build_payload(extension_id)
        )
        resp.raise_for_status()
        return resp.json()

    async def get_extension(self, extension_id: str) -> Extension | None:
        """Fetch metadata and parse into an Extension object."""
        data = await self.fetch(extension_id)
        return self.parse(data, extension_id)

    @staticmethod
    def _label(display: str, internal: str) -> str:
        """Return 'Display Name (internal)' when they differ, else just the display name."""
        return f"{display} ({internal})" if display != internal else display

    def parse(self, data: dict, extension_id: str) -> Extension | None:
        try:
            results = data.get("results", [])
            if not results or not results[0].get("extensions"):
                log.warning(f"No metadata returned for: {extension_id}")
                return None

            ext = results[0]["extensions"][0]
            versions = ext.get("versions", [])
            if not versions:
                log.warning(f"No released versions for: {extension_id}")
                return None

            version = versions[0]
            files = version.get("files", [])

            vsix_url = next(
                (f["source"] for f in files if "VSIXPackage" in f["assetType"]),
                None,
            )
            if not vsix_url:
                log.warning(f"No VSIX package URL for: {extension_id}")

            license_url = next(
                (f["source"] for f in files if "License" in f["assetType"]),
                None,
            )

            publisher_label = self._label(
                ext["publisher"]["displayName"],
                ext["publisher"]["publisherName"],
            )
            extension_label = self._label(
                ext["displayName"],
                ext["extensionName"],
            )

            parsed = Extension(
                publisher=safe_filename(publisher_label),
                name=safe_filename(extension_label),
                version=version["version"],
                vsix_url=vsix_url,
                license_url=license_url,
            )
            log.debug(
                f"Parsed {extension_id} → {parsed.publisher} / {parsed.name} v{parsed.version}"
            )
            return parsed

        except (KeyError, IndexError) as e:
            log.error(f"Failed to parse metadata for {extension_id}: {e}")
            return None
