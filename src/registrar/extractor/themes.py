import json
import zipfile

from registrar.extractor.license import LicenseExtractor
from registrar.logging import log
from registrar.models import ThemeEntry
from registrar.utils.file import safe_filename
from registrar.utils.json import dumps_min
from registrar.utils.jsonc import load_jsonc


class ThemeExtractor:
    def __init__(self, output_root, client):
        self.root = output_root
        self.license_extractor = LicenseExtractor(client)

    async def extract(self, buf, ext, progress):
        results = []

        target_dir = self.root / "registry" / ext.publisher / ext.name
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(buf) as z:
                log.debug(f"[extract] opened {ext.name}")

                pkg = json.loads(z.read("extension/package.json"))
                themes = pkg.get("contributes", {}).get("themes", [])

                log.info(f"[extract] {ext.name}: {len(themes)} themes")
                progress.add_themes(len(themes))

                license_id = pkg.get("license", "UNKNOWN")

                for theme in themes:
                    label = theme.get("label")

                    try:
                        path = theme.get("path")

                        if not path:
                            log.warning(f"[extract] missing path {label}")
                            progress.done_theme()
                            continue

                        zip_path = f"extension/{path.lstrip('./')}"

                        if zip_path not in z.namelist():
                            log.warning(f"[extract] missing file {zip_path}")
                            progress.done_theme()
                            continue

                        if not zip_path.endswith((".json", ".jsonc")):
                            log.warning(f"[extract] invalid file {zip_path}")
                            progress.done_theme()
                            continue

                        raw = z.read(zip_path).decode("utf-8")
                        parsed: dict = load_jsonc(raw)
                        parsed.update({"$schema": "vscode://schemas/color-theme"})

                        file_path = target_dir / f"{safe_filename(label)}.json"
                        file_path.write_text(dumps_min(parsed))

                        results.append(
                            ThemeEntry(
                                publisher=ext.publisher,
                                extension=ext.name,
                                theme=safe_filename(label),
                                origin="Marketplace",
                                license=license_id,
                                ui_type="dark"
                                if theme.get("uiTheme") == "vs-dark"
                                else "light",
                            )
                        )

                        log.success(f"[extract] theme ok {label}")
                        progress.done_theme()

                    except Exception as e:
                        log.warning(f"[extract] theme failed {label}: {e}")

        except Exception as e:
            log.error(f"[extract] failed {ext.name}: {e}")

        return results
