# Streamlit 1.63 audit — open findings

Working notes from the pre-release review. Everything listed here is **open** —
items already fixed are not repeated. P0-P3 are done and removed: the shared
Supabase client, the render caches, the six findings that discarded user work,
the Gravestones card, and the whole tab/expander restructure (every `st.tabs`
call site now passes `on_change="rerun"` and guards its bodies on `.open`, and
the sidebar's eleven expanders do the same). What is left is P4 performance work
and P5 hygiene. Verified against the Streamlit 1.63 reference docs bundled in
the installed package at:

```
<python>/Lib/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/
```

Delete this file once the list is worked off.

---

## P4 — performance, non-structural

### 1. Campaign encounter card re-encodes a discarded JPEG every rerun
`ui/campaign_mode/tabs/manage_tab_shared.py:341-353`

Calls `render_original_encounter(..., include_bytes=not cloud_low_memory)` but
only reads `res["card_img"]` — `card_bytes` is discarded. In V2's
unpicked-encounter view this multiplies by the number of options
(`manage_tab_v2.py:1062-1065`). Cheap fix: `include_bytes=False`. Real fix:
memoize on `(expansion, level, name, tuple(enemies), use_edited)` with
`max_entries`.

### 2. `st.rerun()` inside a fragment defaults to full-app scope
`ui/encounter_mode/panels/invader_panel.py:609`, `:620`, `:638`, `:644`

`_render_enemy_behaviors` is wrapped in `@st.fragment`
(`play_tab_v2.py:27` / `play_tab_v1.py:20`) specifically to keep heavy card
rendering off the interaction path, but these call bare `st.rerun()`, which is
`scope="app"` in 1.63. One "Draw next card" click re-executes every tab. Use
`st.rerun(scope="fragment")`, or drop the call — a button click inside a fragment
already triggers a fragment rerun.

### 3. Campaign dirty-check serializes the whole campaign ~2x per rerun
`ui/campaign_mode/persistence/dirty.py:26-36`

`campaign_signature()` deep-walks the state and `json.dumps` it. Called from
`setup_tab.py:264` (`any_campaign_has_unsaved_changes()` -> V1 + V2) and `:663-666`,
both in the always-rendering Setup tab. For a V2 campaign whose nodes carry full
`encounter_data`, that's hundreds of KB serialized twice per rerun. Cache against
a mutation counter, or compute only inside the handlers that need it.

### 4. Unbounded `@st.cache_data` keyed on 100 KB JSON strings
`ui/character_mode/aggregates.py:741`, `:777`

No `ttl`, no `max_entries`. Each distinct (filters x selection x armor x
upgrades) combination permanently retains a 361-row list (~90 KB). Process-wide,
so every user's permutations accumulate. `max_entries=64` on both would cap it.
Correctness is fine — neither reads `session_state`.

### 5. `load_encounter_data` is an unbounded cache over the byte-bounded one
`ui/encounter_mode/generation/__init__.py:770`

`@st.cache_data` with no `ttl`/`max_entries`, wrapping `load_encounter`, which
already has a byte budget. Measured: touching all 864 encounters left the inner
cache correctly at 21 entries / 187.8 MB, while the process retained **547 MB**.

**Fix:** drop the decorator and return `dict(load_encounter(...))` — a shallow
copy keeps the "callers get their own dict" property (which matters, since
`_shuffled_reward_replacements` is added as a top-level key) without a second
full copy.

### 6. `is_streamlit_cloud()` costs ~75 µs per call, called per image
`core/settings_manager.py:161-165`, `core/image_cache.py:420-431`

There is no `.streamlit/secrets.toml`, and `runtime/secrets.py:387-421` only
memoizes on success — so every call re-probes every path and raises. Benchmarked:
**74.8 µs** for `is_streamlit_cloud()`, **77.8 µs** for `get_config_bool()`.
`_should_bypass_image_cache_for_path` calls both, and is invoked per path from
four call sites — ~150-230 µs per image on grids of 30-100 thumbnails.
Local/Docker only (on Cloud the secrets file exists and memoizes).
`image_cache.py:70` already caches `_IS_CLOUD` at import; `:422` just doesn't use
it.

### 7. Every data table stores a duplicate DataFrame in session state
`ui/character_mode/widgets.py:15-22`

`st.session_state[initial_key] = data`. Measured: hand table 41.7 KB, attacks
89.6 KB, plus armor, armor-upgrades and one per selected hand item. ~150 KB+ per
session of pure duplication.

**Largely addressed by the P3 tab guarding** — the tables no longer rebuild for
hidden tabs, so at most one is built per rerun instead of three. What remains is
that the visible table still stores a full duplicate of its DataFrame; storing a
hash instead would close the rest.

### 8. Fonts re-serialized every rerun
`app.py:389`

`_DS_GLOBAL_STYLE` inlines two base64 TTFs — ~437 KB of markdown. The client
caches after the first send, but the server re-serializes and re-hashes 437 KB on
**every** rerun to compute the hash. Serving from `static/` would remove it.

---

## P5 — latent / hygiene

- **NG+ read inside a cached function** — `generation.py:371` `render_data_card`
  is `@cache_data` and delegates to `_render_data_card_impl` (`:294`), which
  calls `get_current_ngplus_level()` (`:315`, `:322`) -- not in the key. **Not currently exploitable**: the only affected enemies
  (Paladin Leeroy, Maneater Mildred) both have base health > 10, so
  `apply_ngplus_to_raw` scales health at every level and `raw_json` — which *is*
  in the key — differs. Verified 6 distinct keys across NG+0-5, zero collisions.
  Load-bearing on a coincidence: an enemy with `health: "∞"` or no health key
  would leak one user's NG+ card to everyone. Pass `level` explicitly.
- **`st.slider(value=..., key=...)` in the health tracker** —
  `ui/shared/health_tracker.py:154-162`. Verified in
  `elements/widgets/slider.py:861-867` that 1.63 uses
  `key_as_main_identity={"min_value","max_value","step"}`, so `value=` is inert
  once the widget exists. Breaks two live callers that write
  `tracker[...] = {"hp": ...}` expecting the slider to follow —
  `core/behavior/logic.py:432` (comment literally says *"so slider shows it"*)
  and `_apply_maldron_heatup` (`logic.py:1283-1290`). `_reset_deck` works only
  because it bumps `deck_reset_id`, changing the key.
- **`deck_reset_id` is global** — `ui/encounter_mode/panels/invader_panel.py:512`
  bakes it into every HP slider key, and it's bumped app-wide (`:123`, `:319`),
  so resetting one invader snaps **every** invader's HP slider back to default.
- **AoE "use randomized patterns" checkboxes reset to on** —
  `ui/boss_mode/panels/options.py:20-62`. Keys are dropped when the widget stops
  rendering, so an unchecked preference flips back to `True` on every boss
  switch. Add `persist_state="session"`.
- **Hidden Boss Fight tab overwrites Boss Mode's selector keys** —
  `ui/campaign_mode/tabs/boss_fight_tab.py:121-124` writes `boss_mode_choice` and
  `boss_mode_category` (both widget keys) on every campaign rerun. A designed
  one-shot handoff already exists (`boss_mode_pending_name` ->
  `apply_pending_boss_preselect`); this is a second, always-on mechanism.
- **Sidebar re-seeds only 3 of 10 widget groups** — `ui/sidebar.py:132-136`
  computes `ui_base_changed` but only `exp_active_*`, `party_char_*` and
  `ngplus_level` act on it. `enemy_incl_{eid}`, `cap_invaders_lvl_{lvl}`,
  `encounter_item_reward_mode`, `rules_show_only_in_phase`,
  `edited_encounters_global`, `ui_card_width`, `ui_compact` keep the **previous
  account's** state on account switch, then write it back into the newly loaded
  settings.
- **Event builder writes to already-instantiated widget keys** —
  `ui/event_mode/panels/builder.py:116-122`, `:153-159` assign
  `event_builder_pick` / `event_builder_name` after those widgets were created
  (`:47`, `:63`), inside `try/except: pass` that swallows the
  `StreamlitAPIException`. Both blocks are unreachable anyway, because
  `save_custom_event_decks` ends with `st.rerun()` (`ui/event_mode/logic.py:148`).
- **`st.radio` inside `st.form`** — `core/auth.py:216-249`. Selecting
  Reset/Migrate can't swap the form body until submit, so the first Submit runs
  the wrong branch. Move the mode selector outside the form.
- **`ui/behavior_decks/render.py` is dead** — its only importer is the shim
  `core/behavior/render.py:16`, which has zero callers. If revived: `:356`,
  `:372`, `:407`, `:429` interpolate raw PNG **bytes** into `<img src="...">`
  (needs `bytes_to_data_uri`), and `:307`, `:320`, `:333` interpolate a
  filesystem `Path` the browser can't fetch (no `static/` dir, no
  `server.enableStaticServing`).
- **`ui/shared/health_tracker.py:103`** — `st.session_state.setdefault(
  "behavior_deck", {})["priscilla_invisible"] = False` raises `TypeError` if
  `behavior_deck` is `None`, which is how `ensure_behavior_session_state`
  initializes it (`behavior_session_state.py:11`). Unreachable today.
- **Priscilla checkbox default disagrees with its reader** —
  `ui/behavior_viewer/panels/card_picker.py:75-79` creates it with `value=False`;
  `panels/card_display.py:164` reads `.get(key, True)`.
- **Keyless `st.text_input`** — `ui/encounter_mode/tabs/setup_tab.py:363`
  ("Save as:") has no `key`, so its identity includes `value`; any rerun that
  changes the selected encounter recreates the box and drops what was typed.
- **`_sync_deck_to_settings`** — `ui/event_mode/panels/simulator.py:43` calls
  `save_settings` on every draw/shuffle; `save_settings` runs a 33-file
  `iterdir()` **before** its fingerprint fast-path
  (`core/settings_manager.py:308-320`), and on Cloud issues a synchronous
  Supabase upsert per card draw with no spinner.
- **`use_container_width=True`** — `app.py:917`, deprecated in favour of
  `width="stretch"` (which the rest of the file uses). Debug-only path.
- **Module-scope session write** — `ui/sidebar.py:40-41` writes
  `st.session_state["sidebar_ngplus_expanded"]` at import time, so only the
  first session to import gets it.
- **`cm_gf_expansion` multiselect fights the Session State API** —
  `ui/character_mode/render.py:355`. Streamlit logs *"The widget with key
  `cm_gf_expansion` was created with a default value but also had its value set
  via the Session State API"* on every Character Mode render. Observed live, not
  just read. Pick one: seed the key before the widget, or pass `default=`.
- **Guarding a tab or expander prunes the keyed widgets inside it** — the flip
  side of the note below, learned while doing P3. Any widget behind a `.open`
  guard needs `persist_state="session"` or Streamlit drops its key while it is
  hidden. Two live symptoms during the work: a Character Mode stat tier snapping
  back to Base while the stats caption still showed the old value, and the
  sidebar deriving `active_expansions` as empty. The rule that came out of it:
  seed and derive *outside* the guard, keep only the widgets inside, and give
  every keyed widget in there `persist_state="session"`.
- **Streamlit's module watcher can serve stale bytecode** — during P3, edits to
  `ui/character_mode/render.py` produced tracebacks pointing at comment lines and
  a tab body that rendered nothing, both from the previous version of the module.
  Restart the dev server after editing an imported module rather than trusting
  the auto-reload; `app.py` itself does reload correctly.
- **Deleting a keyed widget's session key does not reset it** — established while
  fixing the campaign-name bug: in 1.63, `st.session_state.pop("<widget key>")`
  leaves a `text_input` still rendering its old value on the next run, even
  though `SessionState.__delitem__` clears `_new_session_state`, `_old_state`,
  `_key_id_mapper` and `_new_widget_state`. Assigning the key before the widget
  is created *does* work. Anywhere else in this repo that pops a widget key to
  force a re-seed is suspect — `app.py:547` still does it for the four
  sparks/souls `number_input`s, which were not re-verified.

---

## Coverage gaps

Not fully read during the audit, listed so nobody assumes they were cleared:

- `ui/campaign_mode/tabs/manage_tab_v1.py` lines 800-1487 (ASCII map / layout
  generator), `manage_tab_v2.py` lines 230-440.
- `ui/campaign_mode/generation/__init__.py` (805 lines) — skimmed for
  cache/threading only.
- `core/behavior/logic.py` — deck/shuffle logic beyond the cached function.
- `ui/event_mode/panels/discard.py`, `deck_selector.py` — not read.
- `ui/event_mode/panels/simulator.py` — lines 1-140 only.
