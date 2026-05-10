class ExtensionService:
    def __init__(self, client):
        self.client = client

    async def fetch_page(self, page: int):
        resp = await self.client.get(
            "https://vscodethemes.com",
            params={"_data": "routes/_index", "page": page},
        )
        resp.raise_for_status()
        data = resp.json()

        results = data["results"]["extensions"]
        if not results:
            return None

        return [f"{e['publisherName']}.{e['name']}" for e in results]
