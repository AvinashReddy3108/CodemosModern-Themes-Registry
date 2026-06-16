from typing import Optional

import typer

from registrar.logging import setup_logging
from registrar.runner import Runner
from registrar.utils.progress import make_progress

app = typer.Typer(help="Theme Registrar CLI")


@app.command()
def scrape(
    pages: Optional[int] = None,
    concurrency: int = 10,
    log_level: str = "INFO",
):
    log = setup_logging(level=log_level)
    log.info("Theme Registrar starting.")

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
            log.critical(f"Fatal error: {e}")
            raise typer.Exit(code=1)
