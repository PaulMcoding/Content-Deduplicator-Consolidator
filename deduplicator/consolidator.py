import shutil
from datetime import datetime
from pathlib import Path

from .models import DuplicateGroup


def consolidate(
    groups: list[DuplicateGroup],
    output_dir: Path,
    dry_run: bool = True,
    conflict_strategy: str = "keep_all",
) -> list[dict]:
    """
    Consolidate files into a clean folder structure.

    Args:
        groups: Comparison results from comparator.
        output_dir: Destination folder for consolidated files.
        dry_run: If True, only logs what would happen without copying.
        conflict_strategy: "keep_all" copies all versions with source labels,
                          "keep_newest" copies only the most recent version.

    Returns:
        List of operation log entries.
    """
    operations = []

    for group in groups:
        if group.category == "exact_duplicate":
            # Keep only the recommended (newest) copy
            src = group.recommended
            dest = output_dir / src.relative_path
            operations.append(_op(
                "copy", src.path, dest, dry_run,
                reason="Exact duplicate - keeping newest",
            ))

        elif group.category == "conflicting_versions":
            if conflict_strategy == "keep_all":
                for f in group.files:
                    # Append source root to filename to preserve all versions
                    dest_path = Path(group.relative_path)
                    stem = dest_path.stem
                    suffix = dest_path.suffix
                    parent = dest_path.parent
                    labeled_name = f"{stem}_FROM_{f.root_folder}{suffix}"
                    dest = output_dir / parent / labeled_name
                    is_rec = (f.path == group.recommended.path)
                    operations.append(_op(
                        "copy", f.path, dest, dry_run,
                        reason=f"Conflict - {'RECOMMENDED (newest)' if is_rec else 'alternate version'}",
                    ))
            elif conflict_strategy == "keep_newest":
                src = group.recommended
                dest = output_dir / src.relative_path
                operations.append(_op(
                    "copy", src.path, dest, dry_run,
                    reason="Conflict - keeping newest only",
                ))

        elif group.category == "unique":
            for f in group.files:
                dest = output_dir / f.relative_path
                operations.append(_op(
                    "copy", f.path, dest, dry_run,
                    reason="Unique file - preserving",
                ))

    return operations


def _op(
    action: str,
    source: Path,
    destination: Path,
    dry_run: bool,
    reason: str = "",
) -> dict:
    """Execute or simulate a file operation and return a log entry."""
    entry = {
        "action": action,
        "source": str(source),
        "destination": str(destination),
        "reason": reason,
        "dry_run": dry_run,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
    }

    if not dry_run:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            entry["status"] = "completed"
        except Exception as e:
            entry["status"] = f"error: {e}"
    else:
        entry["status"] = "dry_run"

    return entry
