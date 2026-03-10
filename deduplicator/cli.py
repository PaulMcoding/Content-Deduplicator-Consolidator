import json
from pathlib import Path

import click
from tqdm import tqdm

from .comparator import compare_files, find_relocated_duplicates, summary_stats
from .consolidator import consolidate
from .reporter import build_report_dataframe, export_to_csv, export_to_excel
from .scanner import scan_folders


@click.group()
def cli():
    """Folder Deduplicator - Compare folder contents and flag duplicates."""
    pass


@cli.command()
@click.argument("folders", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--output", "-o", default="report.xlsx", help="Output report path (.xlsx or .csv)")
@click.option("--show-relocated", is_flag=True, help="Also detect files moved/renamed between roots")
def scan(folders, output, show_relocated):
    """Scan folders and generate a comparison report."""
    root_paths = [Path(f) for f in folders]

    click.echo(f"Scanning {len(root_paths)} folders...")
    records = []
    for rec in tqdm(scan_folders(root_paths), desc="Hashing files", unit="files"):
        records.append(rec)

    click.echo(f"\nFound {len(records)} files. Comparing...")
    groups = compare_files(records)
    stats = summary_stats(groups)

    # Print summary
    click.echo("\n--- Summary ---")
    click.echo(f"Total file groups: {stats['total_groups']}")
    click.echo(f"Total files:       {stats['total_files']}")
    click.echo(f"Exact duplicates:  {stats['exact_duplicates']} groups")
    click.echo(f"Conflicts:         {stats['conflicting_versions']} groups (REVIEW NEEDED)")
    click.echo(f"Unique files:      {stats['unique_files']} groups")
    reclaimable_mb = stats["reclaimable_bytes"] / (1024 * 1024)
    click.echo(f"Reclaimable space: {reclaimable_mb:.1f} MB")

    click.echo("\nFiles per root:")
    for root, count in stats["files_by_root"].items():
        size_mb = stats["size_by_root"][root] / (1024 * 1024)
        click.echo(f"  {root}: {count} files ({size_mb:.1f} MB)")

    if show_relocated:
        relocated = find_relocated_duplicates(records)
        if relocated:
            click.echo(f"\nRelocated duplicates: {len(relocated)} groups (same content, different path)")

    # Export report
    df = build_report_dataframe(groups)
    output_path = Path(output)

    if output_path.suffix == ".csv":
        export_to_csv(df, output_path)
    else:
        export_to_excel(df, output_path)

    click.echo(f"\nReport saved to: {output_path.resolve()}")


@cli.command()
@click.argument("folders", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--output-dir", "-d", required=True, type=click.Path(), help="Destination folder for consolidated files")
@click.option("--execute", is_flag=True, help="Actually copy files (default is dry-run)")
@click.option("--conflict-strategy", type=click.Choice(["keep_all", "keep_newest"]), default="keep_all")
@click.option("--report", "-r", default="consolidation_report.xlsx", help="Report output path")
def consolidate_cmd(folders, output_dir, execute, conflict_strategy, report):
    """Scan folders and consolidate files into a clean structure."""
    root_paths = [Path(f) for f in folders]
    dry_run = not execute

    click.echo(f"Scanning {len(root_paths)} folders...")
    records = list(tqdm(scan_folders(root_paths), desc="Hashing files", unit="files"))

    click.echo(f"Found {len(records)} files. Comparing...")
    groups = compare_files(records)

    mode = "DRY RUN" if dry_run else "EXECUTING"
    click.echo(f"\nConsolidating ({mode}) to: {output_dir}")

    operations = consolidate(
        groups,
        output_dir=Path(output_dir),
        dry_run=dry_run,
        conflict_strategy=conflict_strategy,
    )

    # Show operation summary
    completed = sum(1 for op in operations if op["status"] in ("completed", "dry_run"))
    errors = sum(1 for op in operations if op["status"].startswith("error"))
    click.echo(f"Operations: {completed} successful, {errors} errors")

    # Save operation log
    log_path = Path(output_dir) / "consolidation_log.json"
    if not dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(operations, f, indent=2)
        click.echo(f"Operation log: {log_path}")

    # Also generate the comparison report
    df = build_report_dataframe(groups)
    report_path = Path(report)
    if report_path.suffix == ".csv":
        export_to_csv(df, report_path)
    else:
        export_to_excel(df, report_path)
    click.echo(f"Report saved to: {report_path.resolve()}")


@cli.command(name="quick-scan")
@click.argument("folders", nargs=-1, required=True, type=click.Path(exists=True))
def quick_scan(folders):
    """Fast scan using file size + name only (no hashing). Good for a quick overview."""
    from collections import defaultdict
    from datetime import datetime
    import os

    root_paths = [Path(f) for f in folders]
    by_relpath = defaultdict(list)

    for root in root_paths:
        root = root.resolve()
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                fp = Path(dirpath) / fn
                try:
                    stat = fp.stat()
                except OSError:
                    continue
                rel = str(fp.relative_to(root))
                by_relpath[rel].append({
                    "root": root.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                })

    same_count = 0
    diff_count = 0
    unique_count = 0

    for relpath, entries in sorted(by_relpath.items()):
        roots = {e["root"] for e in entries}
        if len(roots) == 1:
            unique_count += 1
        else:
            sizes = {e["size"] for e in entries}
            if len(sizes) == 1:
                same_count += 1
            else:
                diff_count += 1
                newest = max(entries, key=lambda e: e["modified"])
                click.echo(
                    f"  CONFLICT: {relpath} "
                    f"(sizes: {[e['size'] for e in entries]}, "
                    f"newest in: {newest['root']})"
                )

    click.echo(f"\n--- Quick Scan Summary ---")
    click.echo(f"Likely identical: {same_count}")
    click.echo(f"Likely different: {diff_count}")
    click.echo(f"Unique to one root: {unique_count}")
    click.echo(f"\nRun 'scan' for full SHA-256 hash comparison.")


def main():
    cli()


if __name__ == "__main__":
    main()
