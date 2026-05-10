import os
from pathlib import Path

CACHE_ROOT = Path("./.cache")
OUTPUT_ROOT = Path("../registry")

CACHE_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

MARKETPLACE_API = (
    "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
)
THEMES_SITE = "https://vscodethemes.com"

DISABLE_CACHE = os.getenv("DISABLE_CACHE", "false").lower() in ("1", "true", "yes")
