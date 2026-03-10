import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

from deduplicator.scanner import scan_folders
from deduplicator.comparator import compare_files, find_relocated_duplicates, summary_stats
from deduplicator.reporter import build_report_dataframe, export_to_excel, export_to_csv
from deduplicator.consolidator import consolidate

st.set_page_config(
    page_title="Folder Deduplicator",
    page_icon="📁",
    layout="wide",
)

st.title("Folder Deduplicator")
st.caption("Compare folder contents, flag duplicates, and consolidate case files.")

# --- Sidebar: Input ---
with st.sidebar:
    st.header("Folder Paths")
    st.markdown(
        "Enter the paths to the duplicate root folders. "
        "These are the top-level folders that were duplicated "
        "(e.g., the original and its copies)."
    )

    num_folders = st.number_input("Number of folders to compare", min_value=2, max_value=10, value=2)

    folder_paths = []
    for i in range(int(num_folders)):
        path = st.text_input(f"Folder {i + 1}", key=f"folder_{i}", placeholder="/path/to/folder")
        if path.strip():
            folder_paths.append(path.strip())

    scan_button = st.button("Scan & Compare", type="primary", disabled=len(folder_paths) < 2)

    st.divider()
    st.markdown("**Tips:**")
    st.markdown(
        "- OneDrive folders are usually at:\n"
        "  `~/Library/CloudStorage/OneDrive-...`\n"
        "- Make sure all files are synced locally (not cloud-only)\n"
        "- Office temp files (`~$...`) are automatically skipped"
    )

# --- Main area ---
if scan_button:
    # Validate paths
    valid_paths = []
    for p in folder_paths:
        path = Path(p)
        if not path.exists():
            st.error(f"Path does not exist: {p}")
        elif not path.is_dir():
            st.error(f"Not a directory: {p}")
        else:
            valid_paths.append(path)

    if len(valid_paths) >= 2:
        # Scan
        with st.status("Scanning folders...", expanded=True) as status:
            st.write("Hashing files (this may take a while for large folders)...")
            records = []
            progress_bar = st.progress(0)
            file_count_text = st.empty()

            for rec in scan_folders(valid_paths):
                records.append(rec)
                if len(records) % 50 == 0:
                    file_count_text.text(f"Processed {len(records)} files...")

            progress_bar.progress(100)
            file_count_text.text(f"Processed {len(records)} files total.")

            st.write("Comparing files...")
            groups = compare_files(records)
            stats = summary_stats(groups)

            status.update(label="Scan complete!", state="complete")

        st.session_state["groups"] = groups
        st.session_state["stats"] = stats
        st.session_state["records"] = records
        st.session_state["folder_paths"] = folder_paths

# Display results if available
if "groups" in st.session_state:
    groups = st.session_state["groups"]
    stats = st.session_state["stats"]
    records = st.session_state["records"]

    # Summary metrics
    st.header("Summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Files", stats["total_files"])
    col2.metric("Exact Duplicates", f"{stats['exact_duplicates']} groups")
    col3.metric("Conflicts", f"{stats['conflicting_versions']} groups")
    col4.metric("Unique Files", f"{stats['unique_files']} groups")
    reclaimable_mb = stats["reclaimable_bytes"] / (1024 * 1024)
    col5.metric("Reclaimable Space", f"{reclaimable_mb:.1f} MB")

    # Files per root
    st.subheader("Files per Root Folder")
    root_data = []
    for root, count in stats["files_by_root"].items():
        size_mb = stats["size_by_root"][root] / (1024 * 1024)
        root_data.append({"Root Folder": root, "File Count": count, "Size (MB)": round(size_mb, 1)})
    st.dataframe(pd.DataFrame(root_data), use_container_width=True, hide_index=True)

    # Build full report DataFrame
    df = build_report_dataframe(groups)

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Conflicts (Review Needed)",
        "Exact Duplicates",
        "Unique Files",
        "All Files",
        "Consolidation",
    ])

    with tab1:
        st.subheader("Conflicting Versions")
        st.markdown(
            "These files exist in multiple folders with **different content**. "
            "Someone edited a different copy. Review these manually."
        )
        conflicts_df = df[df["Category"] == "conflicting_versions"].copy()
        if conflicts_df.empty:
            st.success("No conflicts found!")
        else:
            display_cols = ["Relative Path", "Root Folder", "Size (MB)", "Last Modified", "Recommended"]
            st.dataframe(
                conflicts_df[display_cols],
                use_container_width=True,
                hide_index=True,
            )
            st.info(f"{len(conflicts_df)} files across {stats['conflicting_versions']} conflict groups")

    with tab2:
        st.subheader("Exact Duplicates")
        st.markdown(
            "These files are **identical** across folders (same content hash). "
            "Safe to consolidate - keep the most recent copy."
        )
        dupes_df = df[df["Category"] == "exact_duplicate"].copy()
        if dupes_df.empty:
            st.info("No exact duplicates found.")
        else:
            display_cols = ["Relative Path", "Root Folder", "Size (MB)", "Last Modified", "Recommended"]
            st.dataframe(
                dupes_df[display_cols],
                use_container_width=True,
                hide_index=True,
            )
            st.info(f"{len(dupes_df)} files across {stats['exact_duplicates']} duplicate groups")

    with tab3:
        st.subheader("Unique Files")
        st.markdown(
            "These files exist in **only one** folder. They may be new files "
            "created after the duplication, or files deleted from the other copy."
        )
        unique_df = df[df["Category"] == "unique"].copy()
        if unique_df.empty:
            st.info("No unique files found.")
        else:
            display_cols = ["Relative Path", "Root Folder", "Size (MB)", "Last Modified"]
            st.dataframe(
                unique_df[display_cols],
                use_container_width=True,
                hide_index=True,
            )
            st.info(f"{len(unique_df)} unique files")

    with tab4:
        st.subheader("All Files")
        st.markdown("Complete listing of all scanned files.")

        # Filter controls
        cat_filter = st.multiselect(
            "Filter by category",
            options=["conflicting_versions", "exact_duplicate", "unique"],
            default=["conflicting_versions", "exact_duplicate", "unique"],
        )
        filtered = df[df["Category"].isin(cat_filter)]

        # Search
        search = st.text_input("Search by filename or path", "")
        if search:
            filtered = filtered[
                filtered["Relative Path"].str.contains(search, case=False, na=False)
            ]

        display_cols = [
            "Relative Path", "Root Folder", "Size (MB)",
            "Last Modified", "SHA-256", "Category", "Recommended",
        ]
        st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
        st.info(f"Showing {len(filtered)} of {len(df)} files")

    with tab5:
        st.subheader("Consolidation")
        st.markdown(
            "Copy files into a clean folder structure. "
            "**Originals are never deleted** - you can review and clean up manually."
        )

        output_dir = st.text_input(
            "Output directory",
            placeholder="/path/to/consolidated_output",
        )
        conflict_strategy = st.radio(
            "Conflict strategy",
            options=["keep_all", "keep_newest"],
            format_func=lambda x: {
                "keep_all": "Keep all versions (labeled with source folder name)",
                "keep_newest": "Keep only the newest version",
            }[x],
        )
        dry_run = st.checkbox("Dry run (preview only, no files copied)", value=True)

        if st.button("Run Consolidation", type="primary"):
            if not output_dir:
                st.error("Please enter an output directory path.")
            else:
                out_path = Path(output_dir)
                with st.spinner("Consolidating..."):
                    operations = consolidate(
                        groups, out_path,
                        dry_run=dry_run,
                        conflict_strategy=conflict_strategy,
                    )

                ops_df = pd.DataFrame(operations)
                st.dataframe(ops_df, use_container_width=True, hide_index=True)

                completed = sum(1 for op in operations if op["status"] in ("completed", "dry_run"))
                errors = sum(1 for op in operations if op["status"].startswith("error"))
                st.info(f"Operations: {completed} planned/completed, {errors} errors")

                if dry_run:
                    st.warning("This was a dry run. Uncheck 'Dry run' and run again to copy files.")

    # Export buttons
    st.divider()
    st.subheader("Export Report")
    col1, col2 = st.columns(2)

    with col1:
        # Excel export
        import io
        excel_buffer = io.BytesIO()
        export_to_excel(df, excel_buffer)
        excel_buffer.seek(0)
        st.download_button(
            "Download Excel Report",
            data=excel_buffer,
            file_name=f"dedup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col2:
        # CSV export
        csv_data = df.drop(columns=["SHA-256 Full"], errors="ignore").to_csv(index=False)
        st.download_button(
            "Download CSV Report",
            data=csv_data,
            file_name=f"dedup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
