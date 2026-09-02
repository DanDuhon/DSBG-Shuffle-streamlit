"""Shared `st.cache_data` sizing for the behavior card pipeline.

Lives in its own module because both `logic.py` and `generation.py` need it and
`generation` already imports `logic`, so it cannot live in either.
"""


def cache_limits() -> dict:
    # Keep Cloud caching conservative to avoid OOM; local can cache more.
    try:
        from core.settings_manager import is_streamlit_cloud

        cloud = bool(is_streamlit_cloud())
    except Exception:
        cloud = False

    if cloud:
        return {"max_entries": 64, "ttl": 30 * 60}
    return {"max_entries": 512, "ttl": 6 * 60 * 60}
