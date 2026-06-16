from registrar.config import THEMES_SITE
from registrar.logging import log


class ExtensionService:
    def __init__(self, client):
        self.client = client

    async def fetch_page(self, page: int) -> list[str] | None:
        log.debug(f"Fetching theme index page {page}.")
        resp = await self.client.get(
            THEMES_SITE,
            params={"_data": "routes/_index", "page": page, "sort": "updatedAt"},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data["results"]["extensions"]

        if not results:
            log.info(f"No extensions on page {page} — end of index reached.")
            return None

        identifiers = [f"{e['publisherName']}.{e['name']}" for e in results]
        log.info(f"Discovered {len(identifiers)} extensions on page {page}.")
        return identifiers
