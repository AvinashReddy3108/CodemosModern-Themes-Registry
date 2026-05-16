import asyncio
from pathlib import Path

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
    def __init__(self, max_pages=None, concurrency=10):
        self.max_pages = max_pages
        self.concurrency = concurrency
        log.debug(
            f"Runner instance created with targeted constraints -> Concurrency: {concurrency}, Limit Page Cap: {max_pages or 'UNLIMITED'}"
        )

    async def producer(self, queue, ext_service, progress, p_task, e_task):
        page = 1
        total_exts = 0
        log.info(
            "Starting processing work tracking: Orchestrating producer event execution queue..."
        )
        try:
            while not self.max_pages or page <= self.max_pages:
                exts = await ext_service.fetch_page(page)
                if not exts:
                    log.info(
                        f"Producer reached an empty index listings page landscape on page {page}. Terminating discovery sweep loops."
                    )
                    break

                for ext_id in exts:
                    await queue.put(ext_id)
                    total_exts += 1
                    if progress:
                        progress.update(e_task, total=total_exts)

                if progress:
                    progress.update(p_task, advance=1)
                page += 1
        except Exception as e:
            log.critical(
                f"Producer encountered catastrophic functional crash tracking marketplace records pagination context loop: {e}"
            )
        finally:
            log.info(
                f"Producer lifecycle complete. Discovered total elements context counts: {total_exts}. Distributing terminal termination flags to worker threads..."
            )
            for _ in range(self.concurrency):
                await queue.put(None)

    async def consumer(
        self,
        queue,
        meta_service,
        downloader,
        extractor,
        index,
        progress,
        e_task,
        t_task,
    ):
        worker_id = asyncio.current_task().get_name()  # ty:ignore[unresolved-attribute]
        log.debug(
            f"Worker tracking thread [{worker_id}] connected and monitoring orchestration task queues."
        )
        while True:
            ext_id = await queue.get()
            if ext_id is None:
                log.debug(
                    f"Worker tracking thread [{worker_id}] received terminal exit token package. Closing routine loop execution contexts cleanly."
                )
                queue.task_done()
                break
            try:
                log.debug(
                    f"Worker tracking thread [{worker_id}] picked up job item identification target: '{ext_id}'"
                )
                data = await meta_service.fetch(ext_id)
                ext = meta_service.parse(data, ext_id)
                if not ext or not ext.vsix_url:
                    log.warning(
                        f"Skipping processing pipeline stack sequence for item target context '{ext_id}': Metadata failed formatting checks."
                    )
                    continue

                buf = await downloader.download(ext)
                themes = await extractor.extract_themes(buf, ext)

                if themes:
                    log.info(
                        f"Worker tracking thread [{worker_id}] successfully extracted validation files: Found ({len(themes)}) theme nodes within package '{ext_id}'"
                    )
                    for t in themes:
                        await index.add(t)
                        if progress:
                            progress.update(t_task, advance=1)

                    if progress:
                        current_total = progress.tasks[t_task].total or 0
                        progress.update(t_task, total=current_total + len(themes))
                else:
                    log.debug(
                        f"No thematic presentation elements located inside package installation structures for item identifier: {ext_id}"
                    )
            except Exception as e:
                log.error(
                    f"Unexpected worker tracking execution failure exception raised tracking extension processing loops reference '{ext_id}': {e}"
                )
            finally:
                if progress:
                    progress.update(e_task, advance=1)
                queue.task_done()

    async def run_async(self, progress=None, tasks=None):
        log.info("Initializing global workflow layout execution pipeline components...")
        p_task = tasks.get("pages") if tasks else None
        e_task = tasks.get("exts") if tasks else None
        t_task = tasks.get("themes") if tasks else None

        index = IndexManager()
        client = HTTPClient()

        ext_service = ExtensionService(client)
        meta_service = MetadataService(client, MARKETPLACE_API)
        downloader = VSIXDownloader(client)
        extractor = Extractor(
            OUTPUT_ROOT, client
        )  # Pass through shared connection client

        queue = asyncio.Queue(
            maxsize=100
        )  # Limit queue capacity to control extreme memory spikes

        # Removed redundant asyncio.Semaphore. The number of active consumers
        # naturally establishes the exact concurrency ceiling.

        consumers = [
            asyncio.create_task(
                self.consumer(
                    queue,
                    meta_service,
                    downloader,
                    extractor,
                    index,
                    progress,
                    e_task,
                    t_task,
                ),
                name=f"CONSUMER-{_}",
            )
            for _ in range(self.concurrency)
        ]

        await self.producer(queue, ext_service, progress, p_task, e_task)

        log.debug(
            "Awaiting terminal execution completion steps from all worker tasks landscapes..."
        )
        await asyncio.gather(*consumers)

        log.info(
            "Worker loops joined. Finalizing indexing registry modifications context loops..."
        )

        await index.write(Path(OUTPUT_ROOT) / "index.json")
        await client.close()
        log.info("System operational sequence execution concluded successfully.")

    run = runnify(run_async)
