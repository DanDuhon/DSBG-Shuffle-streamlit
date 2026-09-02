# Streamlit 1.63 audit — open findings

Working notes from the pre-release review. Everything listed here is **open** —
items already fixed are not repeated. P0-P3 are done and removed, along with six
of the eight P4 findings. What is left is the two P4 items below — both kept
because the proposed fix was wrong or the cost was overstated, with the
measurements that say so — plus P5 hygiene. Verified against the Streamlit 1.63
reference docs bundled in the installed package at:

```
<python>/Lib/site-packages/streamlit/.agents/skills/developing-with-streamlit/references/
```

Delete this file once the list is worked off.

---

## P4 — performance, non-structural

Six of the eight original findings are fixed and removed. Two are left, both
because the audit's proposed fix was wrong or the cost was overstated.

### 1. Campaign dirty-check walks the whole campaign per rerun
`ui/campaign_mode/persistence/dirty.py`

`campaign_signature()` deep-walks the state and serializes it. On a V2 campaign
whose nodes carry full `encounter_data` (~374 KB of JSON) that is **25.9 ms**,
split **19.5 ms** in `_strip_ephemeral` and **8.2 ms** in `json.dumps` — the
Python-level copy, not the serialization, is the cost.

Partly addressed: the signature now returns a 32-char digest instead of the
374 KB string, so the per-version baseline in `session_state` is no longer
hundreds of KB. And the original "~2x per rerun" no longer holds — the two
`any_campaign_has_unsaved_changes()` call sites (`_render_v1_setup` and
`_render_v2_setup`) are mutually exclusive, and P3 confined all of them to the
Setup tab.

Two rewrites were tried and **both rejected**, so don't repeat them:
- Streaming the walk straight into a hash, skipping the copy and the string:
  **151.7 ms**, 7.6x *slower*. Per-scalar `json.dumps` calls lose the C-level
  batching that makes one big `dumps` fast.
- A no-copy fast path (`_has_ephemeral` scan, then `dumps` the original when
  clean): 18.5 ms vs 25.9 ms, only 1.4x, and it adds a 10.6 ms penalty whenever
  ephemeral keys *are* present.

The remaining idea is the audit's other one: cache against a mutation counter.
That needs a counter the codebase does not have, which means touching every
campaign mutation site and risking stale-dirty bugs — a bigger change than the
~20 ms justifies.

### 2. Fonts are still hashed every rerun
`app.py`

`_DS_GLOBAL_STYLE` inlines two base64 TTFs (~427 KB of CSS; the TTFs are 158 KB
and 162 KB).

Partly addressed: the spliced stylesheet is now built once per process rather
than rebuilt on every rerun, removing a **0.168 ms** `.replace()` and its
430 KB transient allocation.

What is left is Streamlit hashing the 430 KB element to diff it: **0.726 ms per
rerun**. Only serving the fonts from `static/` removes that, and it is a
deployment change rather than a code change — it needs
`server.enableStaticServing = true` in `.streamlit/config.toml`, a `static/`
directory carrying a second copy of the two TTFs (the originals must stay in
`assets/`, where PIL reads them for card rendering), and `@font-face` rewritten
to `url("app/static/...")`. That path could not be verified against Streamlit
Cloud from here, so it is left as the owner's call.

Note the original audit called this "~437 KB re-serialized and re-hashed on
every rerun" without a timing. It is under a millisecond.

## P5 — latent / hygiene

- **`_dynamic_data_editor` stores the previous DataFrame, and has to** —
  `ui/character_mode/widgets.py`. An earlier audit entry proposed storing a hash
  instead of `st.session_state[f"{key}__initial_data"]`. That would break the
  widget: on the run after a cell edit the stored frame is passed back to
  `st.data_editor` *as its data*, so that freshly recomputed rows do not fight
  the edit. It is also a reference, not a copy — it retains one previous
  generation of the frame (~40-90 KB per table), not a duplicate of the current
  one. P3 already stopped hidden tabs from building theirs. Left alone
  deliberately.
- **NG+ read inside a cached function** — `generation.py:371` `render_data_card`
  is `@cache_data` and delegates to `_render_data_card_impl` (`:294`), which
  calls `get_current_ngplus_level()` (`:315`, `:322`) — not in the key. **Not currently exploitable**: the only affected enemies
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
