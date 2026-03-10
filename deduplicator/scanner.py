import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Generator

from .models import FileRecord

SKIP_PATTERNS = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".gitignore",
}

SKIP_PREFIXES = ("~$", "._")

SKIP_EXTENSIONS = {".tmp", ".crdownload", ".partial"}


def should_skip(path: Path) -> bool:
    """Check if a file should be skipped (temp files, OS metadata, etc.)."""
    name = path.name
    if name in SKIP_PATTERNS:
        return True
    if any(name.startswith(p) for p in SKIP_PREFIXES):
        return True
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return True
    # Skip hidden files/folders (Unix-style)
    if any(part.startswith(".") for part in path.parts if part != "."):
        return True
    return False


def hash_file(path: Path, algorithm: str = "sha256") -> str:
    """Compute hash of a file using streaming reads (64KB chunks)."""
    h = hashlib.new(algorithm)
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except (PermissionError, OSError):
        return "ERROR_READING_FILE"
    return h.hexdigest()


def scan_folders(
    root_paths: list[Path],
    skip_zero_byte: bool = True,
    extra_skip_patterns: list[str] | None = None,
) -> Generator[FileRecord, None, None]:
    """
    Walk multiple root folders and yield FileRecord for each file.

    Files are yielded as they're discovered and hashed, allowing
    the caller to show progress in real-time.
    """
    extra = set(extra_skip_patterns) if extra_skip_patterns else set()

    for root in root_paths:
        root = root.resolve()
        root_name = root.name

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories in-place
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in extra
            ]

            for filename in filenames:
                filepath = Path(dirpath) / filename

                if should_skip(filepath):
                    continue
                if filename in extra:
                    continue

                try:
                    stat = filepath.stat()
                except (PermissionError, OSError):
                    continue

                size = stat.st_size

                if skip_zero_byte and size == 0:
                    continue

                modified = datetime.fromtimestamp(stat.st_mtime)
                relative = str(filepath.relative_to(root))
                file_hash = hash_file(filepath)

                yield FileRecord(
                    path=filepath,
                    relative_path=relative,
                    root_folder=root_name,
                    size=size,
                    modified=modified,
                    sha256=file_hash,
                )
