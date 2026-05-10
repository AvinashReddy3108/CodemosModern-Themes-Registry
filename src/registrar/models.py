from dataclasses import dataclass


@dataclass
class Extension:
    publisher: str
    name: str
    version: str
    vsix_url: str
    license_url: str | None


@dataclass
class ThemeEntry:
    publisher: str
    extension: str
    theme: str
    origin: str
    license: str
    ui_type: str
