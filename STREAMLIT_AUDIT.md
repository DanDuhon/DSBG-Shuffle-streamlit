# Streamlit 1.63 audit — open findings

Working notes from the pre-release review. Everything listed here is **open** —
items already fixed are not repeated. P0-P3 are done and removed, as is all of
P5 bar two judgement calls, and six of the eight P4 findings. What is left is
four items, each kept for a stated reason rather than because nobody got to it,
with the measurements behind the decision. Verified against the Streamlit 1.63
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

## P5 — open items

Everything else on the original P5 list is fixed. Two are left, both because
they are a judgement call rather than a defect.

### `ui/behavior_decks/render.py` is dead code (449 lines)
Nothing imports it. Its only reference is the shim `core/behavior/render.py`,
and nothing imports that either — the other greps that look like importers are
stale path comments at the tops of `core/behavior/*.py`.

Left in place rather than deleted, because the original note framed it as
revivable. If it ever is: `:356`, `:372`, `:407`, `:429` interpolate raw PNG
**bytes** into `<img src="...">` (they need `bytes_to_data_uri`), and `:307`,
`:320`, `:333` interpolate a filesystem `Path` the browser cannot fetch. Delete
both files if the answer is no.

### `_dynamic_data_editor` stores the previous DataFrame, and has to
`ui/character_mode/widgets.py`. An earlier audit entry proposed storing a hash
instead of `st.session_state[f"{key}__initial_data"]`. That would break the
widget: on the run after a cell edit the stored frame is passed back to
`st.data_editor` *as its data*, so freshly recomputed rows do not fight the
edit. It is also a reference, not a copy — it retains one previous generation of
the frame (~40-90 KB per table), not a duplicate of the current one. P3 already
stopped hidden tabs from building theirs. Left alone deliberately.

---

## Streamlit 1.63 notes worth keeping

These cost real debugging time. They are not defects in this repo.

- **`value=` / `index=` / `default=` are inert once a keyed widget exists.**
  Widgets pass `key_as_main_identity`, so those arguments are only initializers.
  To change what a keyed widget shows, **assign its session key before the
  widget is created**. Passing both an initializer and a Session State value
  makes Streamlit ignore one and log *"was created with a default value but also
  had its value set via the Session State API"*.
- **Deleting a keyed widget's session key does not reset it.** In 1.63,
  `st.session_state.pop("<widget key>")` leaves a `text_input` rendering its old
  value on the next run, even though `SessionState.__delitem__` clears
  `_new_session_state`, `_old_state`, `_key_id_mapper` and `_new_widget_state`.
  Assign, do not pop. Where a pop appears to work, check whether the key was
  even present — the credit usually belongs to Streamlit's stale-widget GC plus
  a downstream reseed guard, which makes it depend on render order.
- **Guarding a tab or expander prunes the keyed widgets inside it.** Anything
  behind a `.open` guard needs `persist_state="session"`, and its seeding and
  deriving must live *outside* the guard. Two live symptoms while doing this: a
  Character Mode stat tier snapping back to Base while the stats caption still
  showed the old value, and the sidebar deriving `active_expansions` as empty.
- **`st.rerun()` inside a fragment defaults to `scope="app"`.** Pass
  `scope="fragment"` or the whole page re-executes.
- **A widget inside `st.form` cannot change what the form renders.** Form
  widgets do not rerun the script until submit, so any branch keyed off one is a
  run behind. Put the selector outside the form.
- **Streamlit's module watcher can serve stale bytecode.** Edits to an imported
  module produced tracebacks pointing at comment lines and a tab body that
  rendered nothing, both from the previous version. Restart the dev server after
  editing an imported module; `app.py` itself reloads correctly.

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
