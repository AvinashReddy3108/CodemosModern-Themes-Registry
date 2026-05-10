from pathvalidate import sanitize_filename


def safe_filename(name: str) -> str:
    return sanitize_filename(name, replacement_text="-").strip()
