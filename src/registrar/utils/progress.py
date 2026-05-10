from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)


class ProgressManager:
    def __enter__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("{task.completed}/{task.total}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            expand=True,
        )
        self.progress.__enter__()

        self.pages = self.progress.add_task("Pages", total=0)
        self.extensions = self.progress.add_task("Extensions", total=0)
        self.themes = self.progress.add_task("Themes", total=0)

        return self

    def __exit__(self, *args):
        self.progress.__exit__(*args)

    def add_page(self):
        self.progress.update(
            self.pages, total=self.progress.tasks[self.pages].total + 1
        )

    def done_page(self):
        self.progress.advance(self.pages)

    def add_extensions(self, count):
        self.progress.update(
            self.extensions,
            total=self.progress.tasks[self.extensions].total + count,
        )

    def done_extension(self):
        self.progress.advance(self.extensions)

    def add_themes(self, count):
        self.progress.update(
            self.themes,
            total=self.progress.tasks[self.themes].total + count,
        )

    def done_theme(self):
        self.progress.advance(self.themes)
