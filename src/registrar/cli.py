from registrar.logging import log
from typing import Optional

import typer

from registrar.runner import Runner
from registrar.utils.progress import make_progress

app = typer.Typer(help="Theme Registrar CLI")


@app.command()
def scrape(pages: Optional[int] = None, concurrency: int = 10):
    log.info("Theme Registrar scraping runtime execution invoked via interface.")
    runner = Runner(max_pages=pages, concurrency=concurrency)

    with make_progress() as progress:
        pages_task = progress.add_task("Scraping Pages", total=pages)
        extensions_task = progress.add_task("Processing Extensions", total=None)
        themes_task = progress.add_task("Extracting Themes", total=None)

        tasks_map = {
            "pages": pages_task,
            "exts": extensions_task,
            "themes": themes_task,
        }
        try:
            runner.run(progress=progress, tasks=tasks_map)  # ty:ignore[missing-argument]
        except Exception as e:
            log.critical(
                f"Execution terminated via an unhandled root level CLI panic: {e}"
            )
            raise typer.Exit(code=1)
