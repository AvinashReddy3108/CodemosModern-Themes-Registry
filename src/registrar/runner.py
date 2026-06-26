import asyncio

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
    def __init__(self, max_pages: int | None = None, concurrency: int = 10):
        self.max_pages = max_pages
        self.concurrency = concurrency
        log.debug(
            f"Runner ready — concurrency: {concurrency}, "
            f"page cap: {max_pages or 'unlimited'}"
        )

    async def _producer(
        self,
        queue: asyncio.Queue,
        ext_service: ExtensionService,
        progress,
        p_task,
        e_task,
    ) -> None:
        page = 1
        total = 0
        log.info("Producer starting — discovering extensions...")
        try:
            while not self.max_pages or page <= self.max_pages:
                exts = await ext_service.fetch_page(page)
                if not exts:
                    log.info(f"No more extensions at page {page} — discovery complete.")
                    break

                for ext_id in exts:
                    await queue.put(ext_id)
                    total += 1
                    if progress:
                        progress.update(e_task, total=total)

                if progress:
                    progress.update(p_task, advance=1)
                page += 1

        except Exception as e:
            log.critical(f"Producer crashed: {e}")
        finally:
            log.info(
                f"Producer done. Discovered {total} extension(s). "
                "Sending shutdown signals to workers..."
            )
            for _ in range(self.concurrency):
                await queue.put(None)

    async def _consumer(
        self,
        queue: asyncio.Queue,
        meta_service: MetadataService,
        downloader: VSIXDownloader,
        extractor: Extractor,
        index: IndexManager,
        progress,
        e_task,
        t_task,
        failure_counter: list[int],
    ) -> None:
        worker = asyncio.current_task().get_name()  # ty:ignore[unresolved-attribute]
        log.debug(f"[{worker}] started.")

        while True:
            ext_id = await queue.get()
            if ext_id is None:
                log.debug(f"[{worker}] received shutdown signal.")
                queue.task_done()
                break

            try:
                log.debug(f"[{worker}] processing '{ext_id}'")
                data = await meta_service.fetch(ext_id)
                ext = meta_service.parse(data, ext_id)

                if not ext or not ext.vsix_url:
                    log.warning(f"Skipping '{ext_id}': invalid metadata.")
                    failure_counter[0] += 1
                    continue

                buf = await downloader.download(ext)
                themes = await extractor.extract_themes(buf, ext)

                if themes:
                    log.info(
                        f"[{worker}] extracted {len(themes)} theme(s) from '{ext_id}'."
                    )
                    for t in themes:
                        await index.add(t)
                        if progress:
                            progress.update(t_task, advance=1)

                    if progress:
                        current = progress.tasks[t_task].total or 0
                        progress.update(t_task, total=current + len(themes))
                else:
                    log.debug(f"No themes found in '{ext_id}'.")

            except Exception as e:
                log.error(f"[{worker}] failed on '{ext_id}': {e.with_traceback()}")  # ty:ignore[missing-argument]
                failure_counter[0] += 1
            finally:
                if progress:
                    progress.update(e_task, advance=1)
                queue.task_done()

    async def run_async(self, progress=None, tasks=None) -> None:
        log.info("Starting pipeline...")
        p_task = tasks.get("pages") if tasks else None
        e_task = tasks.get("exts") if tasks else None
        t_task = tasks.get("themes") if tasks else None

        index_path = OUTPUT_ROOT / "index.json"
        index = IndexManager(path=index_path)
        client = HTTPClient()

        ext_service = ExtensionService(client)
        meta_service = MetadataService(client, MARKETPLACE_API)
        downloader = VSIXDownloader(client)
        extractor = Extractor(OUTPUT_ROOT / "registry", client)

        # Bounded queue prevents unbounded memory growth when producers
        # outrun consumers.
        queue: asyncio.Queue = asyncio.Queue(maxsize=2 * self.concurrency)

        # Shared mutable counter for tracking failures across workers.
        # Using a single-element list so workers can mutate it without closures.
        failure_counter = [0]

        # Spin up exactly `concurrency` consumers; their count IS the concurrency
        # ceiling — no separate semaphore needed.
        consumers = [
            asyncio.create_task(
                self._consumer(
                    queue,
                    meta_service,
                    downloader,
                    extractor,
                    index,
                    progress,
                    e_task,
                    t_task,
                    failure_counter,
                ),
                name=f"CONSUMER-{i}",
            )
            for i in range(self.concurrency)
        ]

        await self._producer(queue, ext_service, progress, p_task, e_task)

        log.debug("Waiting for all workers to finish...")
        await asyncio.gather(*consumers)

        total_failures = failure_counter[0]
        if total_failures:
            log.warning(
                f"Pipeline complete with {total_failures} skipped/failed extension(s)."
            )
        else:
            log.info("Pipeline complete — no failures.")

        await index.write(index_path)
        await client.close()
        log.info("Shutdown complete.")

    run = runnify(run_async)
