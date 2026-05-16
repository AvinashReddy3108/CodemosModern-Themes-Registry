from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
)


def make_progress():
    """Factory to create a Rich Progress instance with our standard columns."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        expand=True,
    )
