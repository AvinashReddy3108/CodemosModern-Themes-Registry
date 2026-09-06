import msgspec


class Extension(msgspec.Struct):
    publisher: str
    name: str
    version: str
    vsix_url: str | None
    license_url: str | None


class ThemeEntry(msgspec.Struct):
    publisher: str
    extension: str
    theme: str
    origin: str
    license: str
    ui_type: str
