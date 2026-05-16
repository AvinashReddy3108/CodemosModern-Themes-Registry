from registrar.logging import log


class ExtensionService:
    def __init__(self, client):
        self.client = client

    async def fetch_page(self, page: int):
        log.debug(f"Fetching theme index, page {page}")
        resp = await self.client.get(
            "https://vscodethemes.com",
            params={"_data": "routes/_index", "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data["results"]["extensions"]

        if not results:
            log.info(
                f"No more extensions found on page {page}. Index page threshold hit."
            )
            return None

        identifiers = [f"{e['publisherName']}.{e['name']}" for e in results]
        log.info(
            f"Successfully discovered {len(identifiers)} extensions on page {page}."
        )

        return identifiers
