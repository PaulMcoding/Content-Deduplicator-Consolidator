from collections import defaultdict

from .models import DuplicateGroup, FileRecord


def compare_files(records: list[FileRecord]) -> list[DuplicateGroup]:
    """
    Group files by relative path and classify each group.

    Categories:
    - "exact_duplicate": Same relative path, same content hash across 2+ roots
    - "conflicting_versions": Same relative path, different content hashes
    - "unique": File exists in only one root
    """
    by_relpath: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        by_relpath[rec.relative_path].append(rec)

    groups = []
    for relpath, files in sorted(by_relpath.items()):
        unique_roots = {f.root_folder for f in files}
        unique_hashes = {f.sha256 for f in files}

        if len(unique_roots) == 1:
            category = "unique"
        elif len(unique_hashes) == 1:
            category = "exact_duplicate"
        else:
            category = "conflicting_versions"

        # Recommend the most recently modified file
        newest = max(files, key=lambda f: f.modified)

        groups.append(DuplicateGroup(
            relative_path=relpath,
            category=category,
            files=files,
            recommended=newest,
        ))

    return groups


def find_relocated_duplicates(records: list[FileRecord]) -> list[DuplicateGroup]:
    """
    Find files with the same content hash but different relative paths.

    These are files that may have been moved or renamed in one copy
    but not the other. Informational only.
    """
    by_hash: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        if rec.sha256 != "ERROR_READING_FILE":
            by_hash[rec.sha256].append(rec)

    groups = []
    for file_hash, files in by_hash.items():
        unique_paths = {f.relative_path for f in files}
        if len(unique_paths) > 1:
            groups.append(DuplicateGroup(
                relative_path=f"[multiple paths] hash={file_hash[:12]}...",
                category="relocated_duplicate",
                files=files,
                recommended=max(files, key=lambda f: f.modified),
            ))

    return groups


def summary_stats(groups: list[DuplicateGroup]) -> dict:
    """Compute summary statistics from comparison results."""
    stats = {
        "total_groups": len(groups),
        "exact_duplicates": 0,
        "conflicting_versions": 0,
        "unique_files": 0,
        "total_files": 0,
        "reclaimable_bytes": 0,
        "files_by_root": defaultdict(int),
        "size_by_root": defaultdict(int),
    }

    for group in groups:
        stats["total_files"] += len(group.files)
        cat = group.category

        if cat == "exact_duplicate":
            stats["exact_duplicates"] += 1
            # All copies but one are reclaimable
            sizes = sorted([f.size for f in group.files], reverse=True)
            stats["reclaimable_bytes"] += sum(sizes[1:])
        elif cat == "conflicting_versions":
            stats["conflicting_versions"] += 1
        elif cat == "unique":
            stats["unique_files"] += 1

        for f in group.files:
            stats["files_by_root"][f.root_folder] += 1
            stats["size_by_root"][f.root_folder] += f.size

    return stats
