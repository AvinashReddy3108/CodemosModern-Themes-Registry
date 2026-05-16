import asyncio
import zipfile
from pathlib import Path

import jsonc
import msgspec
from scancode.api import get_licenses

from registrar.logging import log
from registrar.models import ThemeEntry
from registrar.utils.file import safe_filename


class Extractor:
    def __init__(self, root: Path, http_client):
        self.root = root
        self.client = http_client

    def _parse_jsonc(self, text: str) -> dict:
        return jsonc.loads(text)

    def _get_spdx_id(self, pkg: dict, license_path: Path | None = None) -> str:
        """
        Extract SPDX identifier from package.json or by scanning LICENSE file with ScanCode Toolkit.
        """
        # First try package.json
        lic = pkg.get("license")
        if isinstance(lic, dict):  # Edge-case: licenses can be objects in package.json
            spdx_id = lic.get("type", "UNKNOWN")
        else:
            spdx_id = str(lic) if lic else "UNKNOWN"

        # If LICENSE file exists, try ScanCode detection
        if license_path and license_path.exists():
            try:
                log.debug(
                    f"Running automated ScanCode heuristic analysis on local license file: {license_path}"
                )
                results = get_licenses(str(license_path))
                log.debug(results)

                # results is a list of dicts with license info
                if results:
                    detected = results.get("detected_license_expression_spdx")
                    if detected:
                        log.info(
                            f"ScanCode engine successfully recognized SPDX pattern expression: '{detected}'"
                        )
                        spdx_id = detected
            except Exception as e:
                log.warning(
                    f"ScanCode license inference system failed for path {license_path}: {e}"
                )

        return spdx_id

    def _copy_license_from_vsix(self, z: zipfile.ZipFile, ext) -> bool:
        """Copy LICENSE file verbatim from VSIX if present."""
        for name in z.namelist():
            if name.lower().startswith("extension/license"):
                license_path = (
                    self.root / "registry" / ext.publisher / ext.name / "LICENSE"
                )
                license_path.parent.mkdir(parents=True, exist_ok=True)
                with open(license_path, "wb") as f:
                    f.write(z.read(name))
                log.info(
                    f"Extracted and saved embedded package LICENSE from VSIX for extension: {ext.publisher} - {ext.name}"
                )
                return True
        return False

    async def _fetch_license_from_url(self, ext) -> bool:
        """Fetch LICENSE file from license_url if available."""
        if not ext.license_url:
            log.debug(
                f"No supplementary asset license URL discovered for {ext.publisher}.{ext.name}"
            )
            return False
        try:
            log.debug(
                f"Fetching structural marketplace licensing reference endpoint: {ext.license_url}"
            )
            resp = await self.client.get(ext.license_url)
            resp.raise_for_status()
            license_path = self.root / "registry" / ext.publisher / ext.name / "LICENSE"
            license_path.parent.mkdir(parents=True, exist_ok=True)
            license_path.write_bytes(resp.content)
            log.info(
                f"Successfully retrieved external LICENSE file for {ext.publisher}.{ext.name}"
            )
            return True
        except Exception as e:
            log.warning(
                f"Remote marketplace licensing collection failure at context URL {ext.license_url}: {e}"
            )
            return False

    async def _ensure_license(self, z: zipfile.ZipFile, pkg: dict, ext) -> str:
        """
        Ensure LICENSE file exists in extension folder, return SPDX ID.
        Prefers ScanCode detection if a LICENSE file is present.
        """
        # Default SPDX ID from package.json
        spdx_id = self._get_spdx_id(pkg)

        # Path where LICENSE would be stored
        license_path = self.root / "registry" / ext.publisher / ext.name / "LICENSE"

        # Try to copy LICENSE from VSIX, otherwise fetch from license_url
        if not self._copy_license_from_vsix(z, ext):
            await self._fetch_license_from_url(ext)

        # If LICENSE file exists, run ScanCode detection
        if license_path.exists():
            detected = self._get_spdx_id(pkg, license_path=license_path)
            if detected and detected != "UNKNOWN":
                spdx_id = detected

        log.debug(
            f"Resolved license legal structure for {ext.publisher}.{ext.name} to identifier index matching: [{spdx_id}]"
        )
        return spdx_id

    def _sync_extract(self, buf, ext, spdx_id: str, pkg: dict) -> list[ThemeEntry]:
        """
        Handles CPU-bound zip decompression and synchronous disk writes
        safely executed out of the async loop via asyncio.to_thread.
        """
        results = []
        base_dir = self.root / "registry" / ext.publisher / ext.name

        # We open a clean, thread-isolated ZipFile instance here
        with zipfile.ZipFile(buf) as z:
            themes = pkg.get("contributes", {}).get("themes", [])
            log.debug(
                f"Decompressing payload structure for {ext.publisher} - {ext.name}. Found {len(themes)} sub-theme manifestations."
            )
            for theme in themes:
                path = f"extension/{theme['path'].lstrip('./')}"

                if not path.endswith((".json", ".jsonc")):
                    log.warning(
                        f"Skipping structural asset path '{path}' within {ext.name}: File format validation failed."
                    )
                    continue

                try:
                    raw = z.read(path).decode("utf-8")
                except KeyError:
                    log.warning(
                        f"Manifest component mismatch: target asset missing inside zip boundaries for {ext.publisher} - {ext.name} -> Path: {path}"
                    )
                    continue

                try:
                    parsed = self._parse_jsonc(raw)
                    parsed["$schema"] = "vscode://schemas/color-theme"

                    file_path = base_dir / f"{safe_filename(theme['label'])}.json"
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    file_path.write_bytes(msgspec.json.encode(parsed))
                    log.info(
                        f"Theme definition asset written successfully to local registry store: {file_path.name}"
                    )

                    results.append(
                        ThemeEntry(
                            publisher=ext.publisher,
                            extension=ext.name,
                            theme=safe_filename(theme["label"]),
                            origin="Marketplace",
                            license=spdx_id,
                            ui_type="dark"
                            if theme.get("uiTheme") == "vs-dark"
                            else "light",
                        )
                    )
                except Exception as e:
                    log.error(
                        f"Exception encountered while transforming theme configuration {path} for layout {ext.name}: {e}"
                    )
                    continue

        return results

    async def extract_themes(self, buf, ext) -> list[ThemeEntry]:
        """
        Orchestrates async logic (like checking licenses) before offloading
        heavy CPU/IO zip extractions to a worker thread.
        """
        try:
            # Open the zip archive and KEEP it open for the duration of the license check
            with zipfile.ZipFile(buf) as z:
                pkg = msgspec.json.decode(z.read("extension/package.json"))

                # Now z is guaranteed open and valid inside _ensure_license
                spdx_id = await self._ensure_license(z, pkg, ext)

        except Exception as e:
            log.error(
                f"Decompression lifecycle exception encountered while reading core validation files for {ext.publisher}.{ext.name}: {e}"
            )
            return []

        # Seek the BytesIO buffer back to the start so the thread pool can read it from scratch
        if hasattr(buf, "seek"):
            buf.seek(0)

        # Offload the heavy work to the thread pool with its own isolated ZipFile lifecycle
        return await asyncio.to_thread(self._sync_extract, buf, ext, spdx_id, pkg)
