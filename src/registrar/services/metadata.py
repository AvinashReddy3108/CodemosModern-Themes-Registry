from registrar.logging import log
from registrar.models import Extension
from registrar.utils.file import safe_filename


class MetadataService:
    def __init__(self, client, api_url: str):
        self.client = client
        self.api_url = api_url

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
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json; charset=utf-8; api-version=7.2-preview.1",
        }
        log.debug(f"Querying Marketplace metadata for ID: {extension_id}")
        resp = await self.client.post(
            self.api_url, headers=headers, json=self._build_payload(extension_id)
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_extension_name(self, ext: dict):
        name = ext["extensionName"]
        display_name = ext["displayName"]
        return f"{display_name} ({name})" if display_name != name else f"{display_name}"

    def _parse_publisher(self, ext: dict):
        name = ext["publisher"]["publisherName"]
        display_name = ext["publisher"]["displayName"]
        return f"{display_name} ({name})" if display_name != name else f"{display_name}"

    def parse(self, data: dict, extension_id: str) -> Extension | None:
        try:
            results = data.get("results", [])
            if not results or not results[0].get("extensions"):
                log.warning(
                    f"Marketplace returned no metadata record for ID: {extension_id}"
                )
                return None

            ext = results[0]["extensions"][0]
            versions = ext.get("versions", [])
            if not versions:
                log.warning(
                    f"No released versions found for extension ID: {extension_id}"
                )
                return None

            version = versions[0]

            vsix_url = next(
                (
                    f["source"]
                    for f in version.get("files", [])
                    if "VSIXPackage" in f["assetType"]
                ),
                None,
            )

            if not vsix_url:
                log.warning(
                    f"Extension {extension_id} has no valid VSIX package URL reference."
                )

            license_url = next(
                (
                    f["source"]
                    for f in version.get("files", [])
                    if "License" in f["assetType"]
                ),
                None,
            )

            parsed_ext = Extension(
                publisher=safe_filename(self._parse_publisher(ext)),
                name=safe_filename(self._parse_extension_name(ext)),
                version=version["version"],
                vsix_url=vsix_url,  # ty:ignore[invalid-argument-type]
                license_url=license_url,
            )
            log.debug(
                f"Parsed metadata for {extension_id} -> {parsed_ext.publisher} - {parsed_ext.name} (v{parsed_ext.version})"
            )
            return parsed_ext

        except (KeyError, IndexError) as e:
            log.error(
                f"Failed structure parsing payload schemas for extension {extension_id}: {e}"
            )
            return None
