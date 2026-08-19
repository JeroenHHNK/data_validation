"""Streamlit manual-validation dashboard for groundwater timeseries.

Run with:  streamlit run streamlit_app.py

Reviewers walk a series point-by-point, marking each observation as reviewed
(gecontroleerd) or rejected (afgekeurd) with an optional note. Validation state
is persisted per series and survives re-imports of new raw data.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard import data_access, validation_store
from dashboard.autoflags import load_flag_hints
from dashboard.config import load_settings
from dashboard.overview import (
    append_total_row,
    collect_all_stats,
    compute_folder_summary,
)
from dashboard.generate_tab import render_generate_tab
from dashboard.stitch_tab import render_stitch_tab
from dashboard.plotting import build_figure

st.set_page_config(page_title="Groundwater Validation Dashboard", layout="wide")

SETTINGS = load_settings()

if "migration_done" not in st.session_state:
    n = validation_store.migrate_legacy_stores(
        SETTINGS.base_data_dir, SETTINGS.validation_store_dir,
    )
    if n:
        st.toast(f"Migrated {n} validation file(s) to {SETTINGS.validation_store_dir.name}/")
    st.session_state.migration_done = True


# --------------------------------------------------------------------------- #
# Data loading                                                                #
# --------------------------------------------------------------------------- #
def load_series_into_state(ref: data_access.SeriesRef) -> None:
    """Load or build the master store for a series and cache it in session state."""
    raw_df = pd.read_csv(
        ref.only_csv, encoding="utf-8-sig", encoding_errors="replace"
    )

    if ref.dashboard_csv.exists():
        store = validation_store.load(ref.dashboard_csv)
        # Fold in any raw points that appeared since the store was last saved.
        store = validation_store.merge_new_raw(
            store, raw_df, round_freq=SETTINGS.round_freq
        )
    else:
        store = validation_store.merge_new_raw(
            validation_store.empty_store(), raw_df, round_freq=SETTINGS.round_freq
        )

    st.session_state.series_ref = ref
    st.session_state.series_key = str(ref.dashboard_csv)
    st.session_state.store_df = store
    st.session_state.flag_hints = load_flag_hints(
        ref.validated_csv, round_freq=SETTINGS.round_freq
    )
    st.session_state.dirty = False


@st.cache_data
def load_stressor_csv(path: str) -> dict:
    """Load precipitation and evaporation from a KNMI hourly CSV."""
    df = pd.read_csv(
        path, index_col=0, parse_dates=True,
        encoding="utf-8-sig", encoding_errors="replace",
    )
    required = {"precipitation_mm", "makkink_mm"}
    missing = required - set(df.columns)
    if missing:
        return {"error": f"Missing columns: {', '.join(sorted(missing))}"}
    prec = pd.to_numeric(df["precipitation_mm"], errors="coerce").dropna()
    evap = pd.to_numeric(df["makkink_mm"], errors="coerce").dropna()
    return {"precipitation": prec, "evaporation": evap}


def apply_editor_edits(edited: pd.DataFrame) -> None:
    """Write edits from the data_editor back into the master store by timestamp."""
    store = st.session_state.store_df.set_index("timestamp")
    ed = edited.set_index("timestamp")

    max_len = SETTINGS.notes_max_len
    if ed["note"].astype(str).str.len().gt(max_len).any():
        ed["note"] = ed["note"].astype(str).str.slice(0, max_len)
        st.warning(f"Some notes exceeded {max_len} characters and were truncated.")

    for col in ("gecontroleerd", "afgekeurd", "note"):
        store.loc[ed.index, col] = ed[col].values

    store.loc[store["afgekeurd"] == 1, "gecontroleerd"] = 1

    store = store.reset_index()
    new_store = validation_store.ensure_columns(store)

    if not new_store.equals(st.session_state.store_df):
        st.session_state.store_df = new_store
        st.session_state.dirty = True


# --------------------------------------------------------------------------- #
# Sidebar: selection + actions                                                #
# --------------------------------------------------------------------------- #
def render_sidebar() -> None:
    st.sidebar.title("Series selection")

    vendors = data_access.list_vendors(SETTINGS.base_data_dir)
    if not vendors:
        st.sidebar.error(f"No vendor folders under {SETTINGS.base_data_dir}")
        return

    vendor = st.sidebar.selectbox("Vendor", vendors)
    origins = data_access.list_origins(SETTINGS.base_data_dir, vendor)
    if not origins:
        st.sidebar.warning("No origins with only_csv/ found.")
        return

    origin = st.sidebar.selectbox("Origin", origins)
    refs = data_access.list_series(
        SETTINGS.base_data_dir, vendor, origin,
        validation_store_dir=SETTINGS.validation_store_dir,
    )
    if not refs:
        st.sidebar.warning("No series found.")
        return

    labels = {r.name: r for r in refs}
    reviewed_marks = {
        r.name: ("✓" if r.dashboard_csv.exists() else "·") for r in refs
    }
    display = st.sidebar.selectbox(
        "Series",
        list(labels.keys()),
        format_func=lambda n: f"{reviewed_marks[n]} {n}",
    )
    chosen = labels[display]

    if st.sidebar.button("Load series", type="primary", width="stretch"):
        load_series_into_state(chosen)

    # ---- Stressor overlay controls ----
    st.sidebar.divider()
    st.sidebar.caption("Stressor overlay")
    stressor_dir = SETTINGS.stressor_dir
    stressor_files = sorted(stressor_dir.glob("*.csv")) if stressor_dir.exists() else []
    stressor_options = ["None"] + [f.name for f in stressor_files]
    selected_stressor = st.sidebar.selectbox("Stressor file", stressor_options)
    show_stressors = st.sidebar.checkbox("Show stressor overlay", value=True)

    if selected_stressor != "None":
        result = load_stressor_csv(str(stressor_dir / selected_stressor))
        if "error" in result:
            st.sidebar.error(result["error"])
            st.session_state.stressor_data = None
        else:
            st.session_state.stressor_data = result if show_stressors else None
    else:
        st.session_state.stressor_data = None

    st.sidebar.divider()

    if "series_ref" in st.session_state:
        st.sidebar.caption("Actions")
        if st.sidebar.button("Import new raw data", width="stretch"):
            ref = st.session_state.series_ref
            raw_df = pd.read_csv(
                ref.only_csv, encoding="utf-8-sig", encoding_errors="replace"
            )
            st.session_state.store_df = validation_store.merge_new_raw(
                st.session_state.store_df, raw_df, round_freq=SETTINGS.round_freq
            )
            st.session_state.dirty = True
            st.sidebar.success("Merged new raw data (reviewed rows protected).")

        if st.sidebar.button("Save to CSV", type="primary", width="stretch"):
            ref = st.session_state.series_ref
            validation_store.save(ref.dashboard_csv, st.session_state.store_df)
            st.session_state.dirty = False
            collect_all_stats.clear()
            st.sidebar.success(f"Saved -> {ref.dashboard_csv.name}")


# --------------------------------------------------------------------------- #
# Main panel                                                                  #
# --------------------------------------------------------------------------- #
def render_main() -> None:
    if "store_df" not in st.session_state:
        st.info("Select a vendor, origin and series in the sidebar, then click "
                "**Load series**.")
        return

    ref = st.session_state.series_ref
    st.subheader(f"{ref.vendor} / {ref.origin}")
    st.caption(ref.name)
    if st.session_state.get("dirty"):
        st.warning("You have unsaved changes. Use **Save to CSV** in the sidebar.")

    stats_container = st.container()
    plot_container = st.container()

    # ---- Editor (executed before rendering plot so edits apply this run) ---- #
    st.markdown("### Review points")
    col_a, col_b = st.columns([1, 1])
    with col_a:
        only_unreviewed = st.checkbox("Show only unreviewed", value=True)
    with col_b:
        max_rows = st.number_input(
            "Max rows in editor", min_value=50, max_value=20000, value=500, step=50,
            help="Editing thousands of rows at once can be slow. The plot always "
                 "shows all points.",
        )

    store = st.session_state.store_df
    view = store[store["gecontroleerd"] == 0] if only_unreviewed else store

    col_start, col_end = st.columns([1, 1])
    with col_start:
        ts_dates = view["timestamp"].dt.date
        start_date = st.date_input(
            "Start from date",
            value=ts_dates.min() if not ts_dates.empty else None,
            min_value=ts_dates.min() if not ts_dates.empty else None,
            max_value=ts_dates.max() if not ts_dates.empty else None,
        )

    if start_date is not None:
        view = view[view["timestamp"].dt.date >= start_date]

    truncated = len(view) > max_rows
    view_capped = view.head(int(max_rows)).copy()
    view_capped.insert(0, "#", range(1, len(view_capped) + 1))

    with col_end:
        end_date = view_capped["timestamp"].dt.date.max() if not view_capped.empty else start_date
        st.date_input("End date", value=end_date, disabled=True)

    col_btn1, col_btn2, _ = st.columns([1, 1, 1])
    with col_btn1:
        if st.button("Mark all visible as reviewed and approved"):
            store.loc[view_capped.index, "gecontroleerd"] = 1
            store.loc[view_capped.index, "afgekeurd"] = 0
            st.session_state.store_df = validation_store.ensure_columns(store)
            st.session_state.dirty = True
            st.rerun()
    with col_btn2:
        if st.button("Mark all visible as rejected"):
            store.loc[view_capped.index, "gecontroleerd"] = 1
            store.loc[view_capped.index, "afgekeurd"] = 1
            st.session_state.store_df = validation_store.ensure_columns(store)
            st.session_state.dirty = True
            st.rerun()

    if truncated:
        st.caption(f"Showing first {int(max_rows)} of {len(view)} matching rows.")

    edited = st.data_editor(
        view_capped,
        key="editor",
        width="stretch",
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn("#", disabled=True),
            "timestamp": st.column_config.DatetimeColumn("Timestamp", disabled=True),
            "raw_data": st.column_config.NumberColumn(
                "Raw data (m)", format="%.4f", disabled=True
            ),
            "gecontroleerd": st.column_config.CheckboxColumn("Gecontroleerd"),
            "afgekeurd": st.column_config.CheckboxColumn("Afgekeurd"),
            "note": st.column_config.TextColumn(
                "Note", max_chars=SETTINGS.notes_max_len,
                help=f"Max {SETTINGS.notes_max_len} characters",
            ),
        },
    )
    if edited is not None and not edited.equals(view_capped):
        apply_editor_edits(edited)

    # ---- Stats + plot rendered into their (upper) containers ---- #
    store = st.session_state.store_df
    stats = validation_store.compute_stats(store)
    with stats_container:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total points", stats["total"])
        m2.metric("Reviewed", f"{stats['reviewed']} ({stats['pct_reviewed']:.1f}%)")
        m3.metric("Rejected", f"{stats['rejected']} ({stats['pct_rejected']:.1f}%)")
        m4.metric("Unreviewed", stats["unreviewed"])

    with plot_container:
        fig = build_figure(
            store,
            flag_hints=st.session_state.get("flag_hints"),
            title=ref.name,
            stressor_data=st.session_state.get("stressor_data"),
        )
        st.plotly_chart(fig, key="validation_chart", width="stretch")


# --------------------------------------------------------------------------- #
# Overview tab                                                                #
# --------------------------------------------------------------------------- #
def render_overview() -> None:
    detail = collect_all_stats(
        str(SETTINGS.base_data_dir), str(SETTINGS.validation_store_dir),
    )

    if st.button("Refresh"):
        collect_all_stats.clear()
        st.rerun()

    if detail.empty:
        st.info("No data found.")
        return

    summary = compute_folder_summary(detail)
    summary_with_total = append_total_row(summary)

    st.markdown("### Folder summary")
    st.dataframe(
        summary_with_total[["vendor", "folder", "series_count", "amount_of_rows",
                            "reviewed_rows", "gecontroleerd_%",
                            "rejected_rows", "afgekeurd_%"]],
        hide_index=True,
        column_config={
            "vendor": "Vendor",
            "folder": "Folder",
            "series_count": st.column_config.NumberColumn("Series"),
            "amount_of_rows": st.column_config.NumberColumn("Rows", format="%d"),
            "reviewed_rows": st.column_config.NumberColumn(
                "Gecontroleerd", format="%d",
                help="Number of rows marked gecontroleerd",
            ),
            "gecontroleerd_%": st.column_config.NumberColumn(
                "Gecontroleerd %", format="%.1f%%",
            ),
            "rejected_rows": st.column_config.NumberColumn(
                "Afgekeurd", format="%d",
                help="Number of rows marked afgekeurd",
            ),
            "afgekeurd_%": st.column_config.NumberColumn(
                "Afgekeurd %", format="%.1f%%",
            ),
        },
    )

    folder_labels = [
        f"{r.vendor} / {r.folder}" for _, r in summary.iterrows()
    ]
    selected = st.selectbox(
        "Select folder for details",
        ["All folders"] + folder_labels,
        key="overview_folder_filter",
    )

    if selected == "All folders":
        view = detail
    else:
        vendor, folder = selected.split(" / ", 1)
        view = detail[(detail["vendor"] == vendor) & (detail["folder"] == folder)]

    st.markdown("### Series details")
    st.dataframe(
        view[["vendor", "folder", "series", "amount_of_rows",
              "gecontroleerd_%", "afgekeurd_%"]],
        hide_index=True,
        column_config={
            "vendor": "Vendor",
            "folder": "Folder",
            "series": "Series",
            "amount_of_rows": st.column_config.NumberColumn("Rows"),
            "gecontroleerd_%": st.column_config.NumberColumn(
                "Gecontroleerd %", format="%.1f%%",
            ),
            "afgekeurd_%": st.column_config.NumberColumn(
                "Afgekeurd %", format="%.1f%%",
            ),
        },
    )


render_sidebar()

tab_overview, tab_validation, tab_generate, tab_stitch = st.tabs(
    ["Overview", "Validation", "Generate Data", "Sensor Stitching"],
)

with tab_overview:
    render_overview()

with tab_validation:
    render_main()

with tab_generate:
    render_generate_tab(
        input_dir=SETTINGS.repo_root / "input_data",
        output_dir=SETTINGS.base_data_dir,
        validation_dir=SETTINGS.validation_store_dir,
    )

with tab_stitch:
    render_stitch_tab(
        base_data_dir=SETTINGS.base_data_dir,
        validation_store_dir=SETTINGS.validation_store_dir,
        round_freq=SETTINGS.round_freq,
    )
