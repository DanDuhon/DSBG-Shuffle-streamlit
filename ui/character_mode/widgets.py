import streamlit as st
import pandas as pd
from typing import Any, Dict, List, Optional, Callable
from ui.character_mode.item_fields import _id
from ui.character_mode.tables import _rows_for_table


def _dynamic_data_editor(data: pd.DataFrame, *, key: str, **kwargs) -> pd.DataFrame:
    changed_key = f"{key}__changed"
    initial_key = f"{key}__initial_data"

    def _on_change():
        st.session_state[changed_key] = True

    if st.session_state.get(changed_key, False):
        data_to_pass = st.session_state.get(initial_key, data)
        st.session_state[changed_key] = False
    else:
        st.session_state[initial_key] = data
        data_to_pass = data

    return st.data_editor(data_to_pass, key=key, on_change=_on_change, **kwargs)


def _render_selection_table(
    *,
    items: List[Dict[str, Any]],
    selected_ids: List[str],
    single_select: bool,
    key: str,
    height: Optional[int] = 420,
    extra_columns: Optional[Dict[str, List[Any]]] = None,
    rows_fn: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    column_config_override: Optional[Dict[str, Any]] = None,
    column_order: Optional[List[str]] = None,
) -> List[str]:
    if not items:
        st.dataframe([], width="stretch", hide_index=True, height=height or 100)
        return []

    rows = rows_fn(items) if rows_fn else _rows_for_table(items)
    sel = set(selected_ids)

    for i, row in enumerate(rows):
        row["Select"] = _id(items[i]) in sel
        if extra_columns:
            for col, values in extra_columns.items():
                row[col] = values[i] if i < len(values) else None

    df = pd.DataFrame(rows)

    # Put Select first in the underlying DF (helps even without column_order)
    if "Select" in df.columns:
        df = df[["Select"] + [c for c in df.columns if c != "Select"]]

    kwargs: Dict[str, Any] = {
        "hide_index": True,
        "width": "stretch",
        "disabled": [c for c in df.columns if c != "Select"],
        "num_rows": "fixed",
    }

    if height is not None:
        kwargs["height"] = int(height)

    # Optional explicit display order (also hides unspecified columns)
    if column_order:
        # Ensure Select is present and filter to columns that exist
        co = ["Select"] + [c for c in column_order if c != "Select"]
        co = [c for c in co if c in df.columns]
        kwargs["column_order"] = co

    if getattr(st, "column_config", None) is not None:
        cfg: Dict[str, Any] = {
            "Select": st.column_config.CheckboxColumn("Select", width="small")
        }
        if column_config_override:
            cfg.update(column_config_override)
        kwargs["column_config"] = cfg

    edited = _dynamic_data_editor(df, key=key, **kwargs)

    chosen = [_id(items[i]) for i, v in enumerate(list(edited["Select"])) if bool(v)]
    return chosen[:1] if single_select else chosen