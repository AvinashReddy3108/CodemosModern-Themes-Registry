import typer

from registrar.runner import Runner

app = typer.Typer()


@app.command()
def run(
    max_pages: int = typer.Option(None),
    concurrency: int = typer.Option(10),
):
    Runner(max_pages=max_pages, concurrency=concurrency).run()
