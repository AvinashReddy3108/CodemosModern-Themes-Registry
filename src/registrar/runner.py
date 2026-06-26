import anyio
from asyncer import runnify

from registrar.config import MARKETPLACE_API, OUTPUT_ROOT
from registrar.extractor import Extractor
from registrar.http import HTTPClient
from registrar.index import IndexManager
from registrar.logging import log
from registrar.services.downloader import VSIXDownloader
from registrar.services.extensions import ExtensionService
from registrar.services.metadata import MetadataService


class Runner:
    def __init__(self, max_pages: int | None = None):
        self.max_pages = max_pages

    async def _fetch_pages(self, ext_service, send, progress, p_task, e_task):
        self.page, self.total = 1, 0
        async with send:
            try:
                while not self.max_pages or self.page <= self.max_pages:
                    exts = await ext_service.fetch_page(self.page)
                    if not exts:
                        break
                    self.total += len(exts)
                    if progress:
                        progress.update(p_task, advance=1)
                        progress.update(e_task, total=self.total)
                    await send.send(exts)
                    self.page += 1
            except Exception as e:
                log.critical(f"Page fetcher crashed: {e}")

    async def _emit_ids(self, recv, send):
        async with recv, send:
            async for ext_ids in recv:
                for ext_id in ext_ids:
                    await send.send(ext_id)

    async def _meta_worker(self, recv, send, meta_service, failures, progress, e_task):
        async with recv, send:
            async for ext_id in recv:
                try:
                    data = await meta_service.fetch(ext_id)
                    ext = meta_service.parse(data, ext_id)
                    if ext and ext.vsix_url:
                        await send.send(ext)
                    else:
                        log.warning(f"Skipping '{ext_id}': bad metadata.")
                        failures[0] += 1
                except Exception as e:
                    log.error(f"Metadata failed for '{ext_id}': {e}")
                    failures[0] += 1
                finally:
                    if progress:
                        progress.update(e_task, advance=1)

    async def _dl_extract_worker(self, recv, send, downloader, extractor, failures):
        async with recv, send:
            async for ext in recv:
                try:
                    buf = await downloader.download(ext)
                    themes = await extractor.extract_themes(buf, ext)
                    for t in themes:
                        await send.send(t)
                except Exception as e:
                    log.error(
                        f"Download/extract failed for '{ext.publisher}.{ext.name}': {e}"
                    )
                    failures[0] += 1

    async def _index_writer(self, recv, index, progress, t_task):
        async with recv:
            async for theme in recv:
                try:
                    await index.add(theme)
                    if progress:
                        progress.update(t_task, advance=1)
                except Exception as e:
                    log.error(
                        f"Indexing failed for '{theme.extension}/{theme.theme}': {e}"
                    )

    async def run_async(self, progress=None, tasks=None):
        t = tasks or {}
        p_task = t.get("pages")
        e_task = t.get("exts")
        t_task = t.get("themes")

        index_path = OUTPUT_ROOT / "index.json"
        index = IndexManager(path=index_path)
        client = HTTPClient()

        ext_service = ExtensionService(client)
        meta_service = MetadataService(client, MARKETPLACE_API)
        downloader = VSIXDownloader(client)
        extractor = Extractor(OUTPUT_ROOT, client)

        failures = [0]

        page_send, page_recv = anyio.create_memory_object_stream(max_buffer_size=10)
        id_send, id_recv = anyio.create_memory_object_stream(max_buffer_size=200)
        meta_send, meta_recv = anyio.create_memory_object_stream(max_buffer_size=50)
        theme_send, theme_recv = anyio.create_memory_object_stream(max_buffer_size=500)

        async with anyio.create_task_group() as tg:
            tg.start_soon(
                self._fetch_pages, ext_service, page_send, progress, p_task, e_task
            )
            tg.start_soon(self._emit_ids, page_recv, id_send)

            for _ in range(10):
                tg.start_soon(
                    self._meta_worker,
                    id_recv.clone(),
                    meta_send.clone(),
                    meta_service,
                    failures,
                    progress,
                    e_task,
                )
            id_recv.close()
            meta_send.close()

            for _ in range(10):
                tg.start_soon(
                    self._dl_extract_worker,
                    meta_recv.clone(),
                    theme_send.clone(),
                    downloader,
                    extractor,
                    failures,
                )
            meta_recv.close()
            theme_send.close()

            tg.start_soon(self._index_writer, theme_recv, index, progress, t_task)

        if failures[0]:
            log.warning(f"Pipeline complete — {failures[0]} extension(s) failed.")
        else:
            log.info("Pipeline complete.")

        await index.write(index_path)
        await client.close()

    run = runnify(run_async)
