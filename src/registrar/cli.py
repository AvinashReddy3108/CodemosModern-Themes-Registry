import typer

from registrar.logging import setup_logging
from registrar.runner import Runner
from registrar.utils.progress import make_progress

app = typer.Typer(help="Theme Registrar CLI")


@app.command()
def scrape(
    pages: int | None = None,
    log_level: str = "INFO",
):
    log = setup_logging(level=log_level)
    log.info("Theme Registrar starting.")

    runner = Runner(max_pages=pages)

    with make_progress() as progress:
        # Create tasks for progress bars
        pages_task = progress.add_task("Scraping Pages", total=pages)
        extensions_task = progress.add_task("Processing Extensions", total=0)
        themes_task = progress.add_task("Extracting Themes", total=None)

        tasks_map = {
            "pages": pages_task,
            "exts": extensions_task,
            "themes": themes_task,
        }

        try:
            runner.run(progress=progress, tasks=tasks_map)
        except Exception:
            log.exception("Fatal error")
            raise typer.Exit(code=1)
