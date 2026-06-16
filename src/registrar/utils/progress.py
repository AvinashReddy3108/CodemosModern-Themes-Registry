from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
)


def make_progress() -> Progress:
    """Factory for a Rich Progress instance with standard columns."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        expand=True,
    )
