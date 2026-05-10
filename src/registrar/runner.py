import asyncio
from pathlib import Path

from registrar.cache.response_cache import ResponseCache
from registrar.cache.vsix_cache import VSIXCache
from registrar.config import CACHE_ROOT, MARKETPLACE_API, OUTPUT_ROOT
from registrar.extractor.themes import ThemeExtractor
from registrar.http.client import HTTPClient
from registrar.index import IndexManager
from registrar.logging import log
from registrar.services.downloader import VSIXDownloader
from registrar.services.extensions import ExtensionService
from registrar.services.metadata import MetadataService
from registrar.utils.progress import ProgressManager


class Runner:
    def __init__(self, max_pages=None, concurrency=10):
        self.max_pages = max_pages
        self.sem = asyncio.Semaphore(concurrency)
        log.info(f"Runner started pages={max_pages} concurrency={concurrency}")

    async def run_async(self):
        index = IndexManager()

        async with HTTPClient() as client:
            ext_service = ExtensionService(client)
            meta_service = MetadataService(
                client, MARKETPLACE_API, cache=ResponseCache(CACHE_ROOT / ".responses")
            )
            downloader = VSIXDownloader(client, VSIXCache(CACHE_ROOT))
            extractor = ThemeExtractor(OUTPUT_ROOT, client)

            with ProgressManager() as progress:
                page = 1

                while True:
                    if self.max_pages and page > self.max_pages:
                        log.info("max pages reached")
                        break

                    log.info(f"page {page} fetching")
                    progress.add_page()

                    exts = await ext_service.fetch_page(page)
                    if not exts:
                        log.info("no more extensions")
                        break

                    log.info(f"page {page}: {len(exts)} extensions")
                    progress.add_extensions(len(exts))

                    async def process(ext_id):
                        async with self.sem:
                            try:
                                log.debug(f"processing {ext_id}")

                                data = await meta_service.fetch(ext_id)
                                ext = meta_service.parse(data, ext_id)

                                buf = await downloader.download(ext)
                                themes = await extractor.extract(buf, ext, progress)

                                for t in themes:
                                    index.add(t)

                            except Exception as e:
                                log.error(f"failed {ext_id}: {e}")
                            finally:
                                progress.done_extension()

                    await asyncio.gather(*(process(e) for e in exts))

                    progress.done_page()
                    page += 1

        index.write(Path(OUTPUT_ROOT) / "index.json")
        log.info("index written → done")

    def run(self):
        asyncio.run(self.run_async())
