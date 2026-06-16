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
        # root is OUTPUT_ROOT (e.g. "../registry").
        # All paths below are relative to root directly — no extra "registry/" segment.
        self.root = root
        self.client = http_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_jsonc(self, text: str) -> dict:
        return jsonc.loads(text)

    def _ext_dir(self, ext) -> Path:
        """Canonical output directory for a given extension."""
        return self.root / ext.publisher / ext.name

    def _get_spdx_id(self, pkg: dict, license_path: Path | None = None) -> str:
        """
        Resolve an SPDX identifier for an extension.

        Resolution order:
          1. package.json `license` field (baseline).
          2. ScanCode scan of the LICENSE file on disk (preferred when available).
        """
        lic = pkg.get("license")
        # package.json occasionally stores license as an object {"type": "MIT"}.
        spdx_id = (
            lic.get("type", "UNKNOWN")
            if isinstance(lic, dict)
            else (str(lic) if lic else "UNKNOWN")
        )

        if license_path and license_path.exists():
            try:
                log.debug(f"Running ScanCode on: {license_path}")
                # get_licenses returns a dict, not a list.
                results: dict = get_licenses(str(license_path))
                detected = results.get("detected_license_expression_spdx")
                if detected:
                    log.info(f"ScanCode detected SPDX: '{detected}'")
                    spdx_id = detected
            except Exception as e:
                log.warning(f"ScanCode failed for {license_path}: {e}")

        return spdx_id

    def _copy_license_from_vsix(self, z: zipfile.ZipFile, ext) -> bool:
        """Extract the LICENSE file from the VSIX zip, if present."""
        for name in z.namelist():
            if name.lower().startswith("extension/license"):
                license_path = self._ext_dir(ext) / "LICENSE"
                license_path.parent.mkdir(parents=True, exist_ok=True)
                license_path.write_bytes(z.read(name))
                log.info(
                    f"Extracted LICENSE from VSIX for {ext.publisher} / {ext.name}."
                )
                return True
        return False

    async def _fetch_license_from_url(self, ext) -> bool:
        """Download the LICENSE file from the Marketplace asset URL, if available."""
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
            log.info(f"Downloaded LICENSE for {ext.publisher} / {ext.name}.")
            return True
        except Exception as e:
            log.warning(f"Failed to fetch license from {ext.license_url}: {e}")
            return False

    async def _ensure_license(self, z: zipfile.ZipFile, pkg: dict, ext) -> str:
        """
        Guarantee a LICENSE file exists in the extension directory and return its SPDX ID.

        Priority:
          1. LICENSE bundled inside the VSIX.
          2. LICENSE fetched from the Marketplace asset URL.
          3. `license` field in package.json (fallback, no file on disk).

        After obtaining the file, ScanCode re-scans it for a more accurate SPDX expression.
        """
        # Try to obtain the LICENSE file (VSIX first, then remote URL).
        if not self._copy_license_from_vsix(z, ext):
            await self._fetch_license_from_url(ext)

        license_path = self._ext_dir(ext) / "LICENSE"
        # _get_spdx_id will use ScanCode if the file now exists on disk.
        return self._get_spdx_id(pkg, license_path=license_path)

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    def _sync_extract(self, buf, ext, spdx_id: str, pkg: dict) -> list[ThemeEntry]:
        """
        CPU-bound: decompress the VSIX, parse every theme JSON, and write
        them to disk.  Runs in a thread pool via asyncio.to_thread().

        We open a *fresh* ZipFile here from the rewound BytesIO buffer — the
        ZipFile opened in extract_themes() is already closed by the time this
        runs, but BytesIO itself persists and is safe to reuse after seek(0).
        """
        results: list[ThemeEntry] = []
        base_dir = self._ext_dir(ext)

        with zipfile.ZipFile(buf) as z:
            themes = pkg.get("contributes", {}).get("themes", [])
            log.debug(
                f"Extracting {len(themes)} theme(s) from {ext.publisher} / {ext.name}."
            )

            for theme in themes:
                path = f"extension/{theme['path'].lstrip('./')}"

                if not path.endswith((".json", ".jsonc")):
                    log.warning(f"Skipping '{path}' in {ext.name}: unsupported format.")
                    continue

                try:
                    raw = z.read(path).decode("utf-8")
                except KeyError:
                    log.warning(
                        f"Missing asset '{path}' in VSIX for {ext.publisher} / {ext.name}."
                    )
                    continue

                try:
                    parsed = self._parse_jsonc(raw)
                    parsed["$schema"] = "vscode://schemas/color-theme"

                    label = safe_filename(theme["label"])
                    file_path = base_dir / f"{label}.json"
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(msgspec.json.encode(parsed))
                    log.info(f"Wrote theme: {file_path.name}")

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
                    log.error(f"Failed to process theme '{path}' in {ext.name}: {e}")
                    continue

        return results

    async def extract_themes(self, buf, ext) -> list[ThemeEntry]:
        """
        Orchestrate async work (license resolution) then offload the
        CPU/IO-heavy zip extraction to a thread pool worker.
        """
        try:
            # Open the zip once to read package.json and handle the license file.
            # This ZipFile closes at the end of the block; the underlying BytesIO
            # buffer remains intact and is rewound below for the thread worker.
            with zipfile.ZipFile(buf) as z:
                pkg = msgspec.json.decode(z.read("extension/package.json"))
                spdx_id = await self._ensure_license(z, pkg, ext)
        except Exception as e:
            log.error(f"Failed to open VSIX for {ext.publisher} / {ext.name}: {e}")
            return []

        # Rewind so the thread worker can open a fresh ZipFile from the start.
        if hasattr(buf, "seek"):
            buf.seek(0)

        return await asyncio.to_thread(self._sync_extract, buf, ext, spdx_id, pkg)
