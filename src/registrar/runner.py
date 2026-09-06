import json
import zipfile

import anyio
import httpx
import msgspec
from asyncer import runnify

from registrar.config import MARKETPLACE_API, OUTPUT_ROOT
from registrar.extractor import Extractor
from registrar.http import HTTPClient
from registrar.index import IndexManager
from registrar.logging import log
from registrar.services.downloader import VSIXDownloader
from registrar.services.extensions import ExtensionService
from registrar.services.metadata import MetadataService

# Worker pool sizes. The Marketplace metadata stage is rate-limited
# (150 req / 5 min), so it needs the most concurrent in-flight requests
# to stay saturated. Download and extraction are independent pools so a
# slow download never blocks extraction of other VSIXes (and vice versa).
META_WORKERS = 30
DOWNLOAD_WORKERS = 12
EXTRACT_WORKERS = 20


class Runner:
    def __init__(self, max_pages: int | None = None):
        self.max_pages = max_pages

    async def _fetch_pages(self, ext_service, id_send, progress, p_task, e_task):
        """Fetch theme index pages and emit each extension ID downstream."""
        page = 1
        total = 0
        async with id_send:
            try:
                while not self.max_pages or page <= self.max_pages:
                    exts = await ext_service.fetch_page(page)
                    if not exts:
                        break
                    total += len(exts)
                    if progress:
                        progress.update(p_task, advance=1)
                        progress.update(e_task, total=total)
                    for ext_id in exts:
                        await id_send.send(ext_id)
                    page += 1
            except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
                log.critical(f"Page fetcher crashed: {e}")

    async def _meta_worker(self, recv, send, meta_service, failures, progress, e_task):
        async with recv, send:
            async for ext_id in recv:
                try:
                    ext = await meta_service.get_extension(ext_id)
                    if ext and ext.vsix_url:
                        await send.send(ext)
                    else:
                        log.warning(f"Skipping '{ext_id}': bad metadata.")
                        failures[0] += 1
                except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
                    log.error(f"Metadata failed for '{ext_id}': {e}")
                    failures[0] += 1
                finally:
                    if progress:
                        progress.update(e_task, advance=1)

    async def _downloader(self, recv, send, downloader, failures):
        async with recv, send:
            async for ext in recv:
                try:
                    buf = await downloader.download(ext)
                    await send.send((ext, buf))
                except (httpx.HTTPError, OSError) as e:
                    log.error(f"Download failed for '{ext.publisher}.{ext.name}': {e}")
                    failures[0] += 1

    async def _extractor(self, recv, send, extractor, failures):
        async with recv, send:
            async for ext, buf in recv:
                try:
                    themes = await extractor.extract_themes(buf, ext)
                    for t in themes:
                        await send.send(t)
                except (
                    OSError,
                    KeyError,
                    ValueError,
                    TypeError,
                    zipfile.BadZipFile,
                    msgspec.DecodeError,
                ) as e:
                    log.error(f"Extract failed for '{ext.publisher}.{ext.name}': {e}")
                    failures[0] += 1

    async def _index_writer(self, recv, index, progress, t_task):
        async with recv:
            async for theme in recv:
                try:
                    await index.add(theme)
                    if progress:
                        progress.update(t_task, advance=1)
                except KeyError as e:
                    log.error(
                        f"Indexing failed for '{theme.extension}/{theme.theme}': {e}"
                    )

    async def run_async(self, progress=None, tasks=None):
        t = tasks or {}
        p_task, e_task, t_task = t.get("pages"), t.get("exts"), t.get("themes")

        index_path = OUTPUT_ROOT / "index.json"
        index = IndexManager(path=index_path)
        client = HTTPClient()
        failures = [0]

        ext_service = ExtensionService(client)
        meta_service = MetadataService(client, MARKETPLACE_API)
        downloader = VSIXDownloader(client)
        extractor = Extractor(OUTPUT_ROOT / "registry", client)

        # Memory-object streams between stages. Generous buffers decouple
        # producer/consumer speed so one stage's backpressure doesn't stall the
        # next. Each stream's ORIGINAL send/recv end must be closed once all
        # workers have been given clones, or downstream stages never see EOF
        # and the task group hangs.
        id_send, id_recv = anyio.create_memory_object_stream(max_buffer_size=1000)
        meta_send, meta_recv = anyio.create_memory_object_stream(max_buffer_size=200)
        vsix_send, vsix_recv = anyio.create_memory_object_stream(max_buffer_size=20)
        theme_send, theme_recv = anyio.create_memory_object_stream(max_buffer_size=1000)

        try:
            async with anyio.create_task_group() as tg:
                # page fetch → extension IDs (sole producer owns id_send)
                tg.start_soon(
                    self._fetch_pages, ext_service, id_send, progress, p_task, e_task
                )

                # metadata workers
                for _ in range(META_WORKERS):
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

                # download workers (VSIX bytes)
                for _ in range(DOWNLOAD_WORKERS):
                    tg.start_soon(
                        self._downloader,
                        meta_recv.clone(),
                        vsix_send.clone(),
                        downloader,
                        failures,
                    )
                meta_recv.close()
                vsix_send.close()

                # extract workers (themes)
                for _ in range(EXTRACT_WORKERS):
                    tg.start_soon(
                        self._extractor,
                        vsix_recv.clone(),
                        theme_send.clone(),
                        extractor,
                        failures,
                    )
                vsix_recv.close()
                theme_send.close()

                # final writer (sole consumer owns theme_recv)
                tg.start_soon(self._index_writer, theme_recv, index, progress, t_task)

            if failures[0]:
                log.warning(f"Pipeline complete — {failures[0]} extension(s) failed.")
            else:
                log.info("Pipeline complete.")
        finally:
            # Persist whatever made it through and free the connection pool even
            # when the group is cancelled or a stage crashes.
            await index.write(index_path)
            await client.close()

    run = runnify(run_async)
