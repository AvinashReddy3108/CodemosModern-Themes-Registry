import zipfile
from pathlib import Path

import jsonc
import msgspec
from asyncer import asyncify
from scancode.api import get_licenses

from registrar.logging import log
from registrar.models import ThemeEntry
from registrar.utils.file import safe_filename

# Wrap ScanCode sync call with asyncify
_get_licenses_async = asyncify(get_licenses)


class Extractor:
    def __init__(self, root: Path, http_client):
        self.root = root
        self.client = http_client
        # Wrap sync extraction with asyncify
        self._async_extract = asyncify(self._sync_extract)

    def _ext_dir(self, ext) -> Path:
        return self.root / ext.publisher / ext.name

    async def _get_spdx_id(self, pkg: dict, license_path: Path | None = None) -> str:
        lic = pkg.get("license")
        spdx_id = (
            lic.get("type", "UNKNOWN")
            if isinstance(lic, dict)
            else (str(lic) if lic else "UNKNOWN")
        )
        if license_path and license_path.exists():
            try:
                # Use asyncified ScanCode call
                results: dict = await _get_licenses_async(str(license_path))
                detected = results.get("detected_license_expression_spdx")
                if detected:
                    log.info(f"ScanCode detected SPDX: '{detected}'")
                    spdx_id = detected
            except Exception as e:
                log.warning(f"ScanCode failed for {license_path}: {e}")
        return spdx_id

    def _copy_license_from_vsix(self, z: zipfile.ZipFile, ext) -> bool:
        for name in z.namelist():
            if name.lower().startswith("extension/license"):
                license_path = self._ext_dir(ext) / "LICENSE"
                license_path.parent.mkdir(parents=True, exist_ok=True)
                license_path.write_bytes(z.read(name))
                log.info(f"Extracted LICENSE from VSIX for {ext.publisher}/{ext.name}.")
                return True
        return False

    async def _fetch_license_from_url(self, ext) -> bool:
        if not ext.license_url:
            log.debug(f"No license URL for {ext.publisher}.{ext.name}.")
            return False
        try:
            log.debug(f"Fetching license from {ext.license_url}")
            resp = await self.client.get(ext.license_url)
            resp.raise_for_status()
            license_path = self._ext_dir(ext) / "LICENSE"
            license_path.parent.mkdir(parents=True, exist_ok=True)
            license_path.write_bytes(resp.content)
            log.info(f"Downloaded LICENSE for {ext.publisher}/{ext.name}.")
            return True
        except Exception as e:
            log.warning(f"Failed to fetch license from {ext.license_url}: {e}")
            return False

    async def _ensure_license(self, z: zipfile.ZipFile, pkg: dict, ext) -> str:
        if not self._copy_license_from_vsix(z, ext):
            await self._fetch_license_from_url(ext)
        license_path = self._ext_dir(ext) / "LICENSE"
        # Now _get_spdx_id is async
        return await self._get_spdx_id(pkg, license_path=license_path)

    def _sync_extract(self, buf, ext, spdx_id: str, pkg: dict) -> list[ThemeEntry]:
        results: list[ThemeEntry] = []
        base_dir = self._ext_dir(ext)

        with zipfile.ZipFile(buf) as z:
            themes = pkg.get("contributes", {}).get("themes", [])
            log.debug(
                f"Extracting {len(themes)} theme(s) from {ext.publisher}/{ext.name}"
            )

            for theme in themes:
                path = f"extension/{theme['path'].lstrip('./')}"
                if not path.endswith((".json", ".jsonc")):
                    log.warning(f"Skipping {path}: unsupported format.")
                    continue
                try:
                    raw = z.read(path).decode("utf-8")
                    parsed = jsonc.loads(raw)
                    parsed["$schema"] = "vscode://schemas/color-theme"

                    label = safe_filename(theme["label"])
                    file_path = base_dir / f"{label}.json"
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(msgspec.json.encode(parsed))

                    results.append(
                        ThemeEntry(
                            publisher=ext.publisher,
                            extension=ext.name,
                            theme=label,
                            origin="Marketplace",
                            license=spdx_id,
                            ui_type="dark"
                            if theme.get("uiTheme") == "vs-dark"
                            else "light",
                        )
                    )
                except Exception as e:
                    log.error(f"Failed to process theme {path}: {e}")
        return results

    async def extract_themes(self, buf, ext) -> list[ThemeEntry]:
        try:
            with zipfile.ZipFile(buf) as z:
                pkg = msgspec.json.decode(z.read("extension/package.json"))
                spdx_id = await self._ensure_license(z, pkg, ext)
        except Exception as e:
            log.error(f"Failed to open VSIX for {ext.publisher}/{ext.name}: {e}")
            return []

        if hasattr(buf, "seek"):
            buf.seek(0)

        return await self._async_extract(buf, ext, spdx_id, pkg)
