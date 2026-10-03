import re

from pathvalidate import sanitize_filename


def safe_filename(name: str) -> str:
    # Collapse internal whitespace before sanitizing so multi-space gaps
    # don't survive as-is into filenames.
    name = re.sub(r"\s+", " ", name).strip()
    return sanitize_filename(name, replacement_text="-").strip()
