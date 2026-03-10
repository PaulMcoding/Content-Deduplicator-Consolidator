from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class FileRecord:
    """Represents a single file found during scanning."""
    path: Path
    relative_path: str
    root_folder: str
    size: int
    modified: datetime
    sha256: str


@dataclass
class DuplicateGroup:
    """A group of files sharing the same relative path across roots."""
    relative_path: str
    category: str  # "exact_duplicate" | "conflicting_versions" | "unique"
    files: list[FileRecord] = field(default_factory=list)
    recommended: FileRecord | None = None
