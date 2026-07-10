# CLAUDE.md — Crime[dot]Education / MN Sentencing Explorer

Guide for future Claude instances working in this repo. Read this before making changes.

## What this is

A **Flask web app** for exploring **Minnesota felony sentencing data, 2001–2019** (~294k cases).
It is a teaching tool: educators/students log in, apply a chain of filters to the dataset, and
view descriptive statistics and cross-tabulations. Author: Sidney D. Allen (academic project,
advised by Dr. Lindsey Vigesaa, Dr. Mary Clifford, David Hudson).

- Backend: Flask 3 + Jinja2 templates, pandas/numpy for analysis.
- Source data: SPSS `.sav` file read via `pyreadstat`.
- No database — **everything is pickle files and a disk cache on the filesystem.**
- Product name in UI: "Minnesota Sentencing Explorer" / "Crime[dot]Education".

## The one thing to understand first: history-driven state + cache

There is **no live dataframe per session.** Instead:

1. Each user account stores a **`history`** list — an ordered log of filter operations.
   The first entry is always the base "load everything" step (`action: None`).
2. On every request that needs data, the app **replays the entire history from scratch**
   (`cache._execute`) to rebuild the filtered dataframe, OR reads a precomputed result
   from disk cache.
3. The **disk cache is keyed by the history itself.** Each history step is serialized to a
   short text token (e.g. `f.time.gt.14`) and these tokens become a **directory path** under
   `cache/data/`. So filtering `time > 14` then `moc1 == H` caches into
   `cache/data/f.time.gt.14/f.moc1.eq.H/`.

Consequences:
- Applying a filter = **appending a history entry** to the user's pickle, then redirecting home.
  It does not mutate a dataframe.
- "Revert" (`/revert/<n>`) truncates the history list back to the clicked entry (keeps
  `history[:n]`, where `n` is that row's 1-based position); "Clear Data" (`/load`) reverts all
  the way to the base (full dataset).
- Cache files inside a history directory: `_data.bin` (dataset-level summary),
  `<column>.bin` (per-column stats), `_moc.bin` (offense-code option counts).
- The cache is **content-addressed and safe to delete** — it regenerates on demand (slowly).

## Data flow / bootstrap (IMPORTANT for setup)

The runtime does **not** read `dataset.sav` directly. It reads the **base datafile** — the typed
columnar `cache/raw.parquet` when present, else `cache/raw.csv` (Lever C).

```
dataset.sav (SPSS, ~141 MB, git-ignored)
    │  one-time precompute:  uv run python cache.py   (its __main__ block)
    ▼
cache/raw.csv  (~242 MB, git-ignored)   ← human-inspectable CSV base + CSV fallback
    │  cache.py __main__ then re-loads raw.csv and writes:
    ▼
cache/raw.parquet  (~23 MB, git-ignored)  ← DATAFILE that _execute() prefers at runtime
    │  optional: also pre-caches per-column stats into cache/data/
    ▼
runtime: cache._base_df() loads the base ONCE per process (Lever B), _execute() replays
         user history filters on top of that shared, immutable base
```

To stand the app up on a fresh machine you must obtain `dataset.sav` (not in git), then run
`uv run python cache.py` and answer `y` to the prompts (create raw csv? / create raw parquet? /
cache info?) to generate `cache/raw.csv` + `cache/raw.parquet` and warm the cache. `cache.py`
defines `DATAFILE_PARQUET`/`DATAFILE_CSV` and resolves `DATAFILE` to the Parquet base when it
exists (else the CSV); `DATAPATH = 'cache/data/'`. Repoint `DATAFILE` (or delete `raw.parquet`)
to force the CSV loader — it stays a working fallback.

**Base DataFrame optimization (Levers A–C, on `base-df-optimization`):** `Data.load` casts the
116 string columns to `category` (Lever A, ~8× RAM: ~1.72 GiB → ~0.22 GiB); `cache._base_df()`
memoizes the base so cache misses stop re-parsing it (Lever B); and `cache/raw.parquet` replaces
the 242 MB CSV parse (~4.2 s) with a ~0.25 s typed load (Lever C, ~10× smaller on disk). All three
are verified byte-identical against the Phase 0 golden `.bin` snapshot. Numeric columns stay
`float64` (the three `dtype == 'float64'` checks in `data.py` depend on it). One caveat: Parquet
needs one type per column, so `save_parquet` stringifies 4 mixed-type category columns
(`Statute_Chapter`, `Statute_Subdivision`, `presumptlifeid`, `ssection` — none are golden or
excluded columns); the CSV fallback keeps their original mixed values.

## Running it

No `app.run()` exists in `app.py`. The environment is managed by **uv** (`pyproject.toml` +
`uv.lock`; Python 3.13 pinned via `.python-version`). Build the env once, then launch via the
Flask CLI through uv:

```
uv sync                        # build .venv from the lockfile (installs Python 3.13 if needed)
uv run flask --app app run     # add --debug for reload
```

## Module map

| File | Role |
|------|------|
| `app.py` | Flask routes + the `is_logged_in` / `not_logged_in` helpers. Thin controller layer. At import time it eagerly warms `cache._base_df()` (guarded — a missing datafile logs and falls back to lazy load) so gunicorn `--preload` shares the base across workers (Lever D). |
| `data.py` | `Data` class — the actual pandas analysis engine: filtering, cross-tabs, per-column stats, MOC filtering. `load` reads `.sav`/`.parquet`/`.csv` and casts string (`object`) columns to `category` (Lever A — numeric dtypes untouched); `save_parquet` writes the typed Parquet base (Lever C — stringifies 4 mixed-type category columns pyarrow can't encode). Also `format_column_info()` (sorting for display) and `GROUP_ORDER` (column-browser group display order). `Data()` with no preload is cheap — it only parses `codebook.xml` (app.py keeps one as `CODEBOOK` for metadata). Visualization-expansion additions: `get_column_info` also returns `mode`/`mode_extra` (the tie count — first modal value, gated like `mean`/`mdn`/`std`); `aggregate_by_group(group_column, measure, aggregate)` is the one shared `(group, measure ∈ {'#', numeric col}, aggregate ∈ {count,mean,median,mode})` → per-group series helper every Visualize chart reads through; `distinct_counts(*cols)` guards the scatter builder's lattice-size budget before it pays for a full `get_table`. Request-path-optimization additions (P4/P5): `get_table` is one `groupby([x, y], observed=True)` count pass + per-group Series reductions for the measure (deliberately NOT `groupby.agg` — the Cython kernels accumulate in a different order and can flip a value on a rounding boundary; verified cell-for-cell against the old nested-filter path), and `num_each` is one `value_counts` pass re-keyed to `col.unique()`'s own elements in appearance order with a NaN key pinned to 0, so `<col>.bin` pickle bytes are unchanged (the order-preserving swap — verified byte-identical across all non-excluded columns). |
| `cache.py` | The history→cache→dataframe machinery: `get_data`, `get_moc_options`, `_execute`, plus `_base_df()` — the load-once base-DataFrame singleton (Lever B; debug-only shape/id mutation tripwire). `DATAFILE` resolves to `cache/raw.parquet` when present, else `cache/raw.csv`. `__main__` builds `cache/raw.csv` from `dataset.sav`, then `cache/raw.parquet` from the CSV. (Header comment calls it `precache.py`.) Visualization-expansion additions: `get_aggregate(session, group_column, measure, aggregate, history_override=None)` wraps `Data.aggregate_by_group` (fresh per request, never disk-cached, like crosstabs); `_county_crosswalk()` memoizes `{'district': {county: d}, 'region': {county: r}}` from `_base_df().groupby('county')[...].first()` next to `_base_df()`; `county_values()` returns the distinct county list `geo.assert_county_coverage` checks at app startup. Request-path-optimization addition (P3): `_filtered_cache` — the bounded (8-entry) **filtered-slice LRU** next to `_base_df()`/`_county_crosswalk()`, keyed on the canonical history-token tuple (`_slice_key`, the same tokens the disk-cache dir is built from); `_execute` serves cached slices read-only (same contract + tripwire as the base) and the real replay lives in `_replay_history` (the timed miss path); `_clear_filtered_cache()` backs the guardrail test's and benchmark's cold runs. |
| `geo.py` | **New** (visualization expansion). Pure stdlib (no Flask/pandas), mirrors `lessons.py`/`classroom.py`. Loads/memoizes the vendored `static/geo/mn-counties-topo.json` TopoJSON; `COUNTY_ALIASES` + `_normalize()` reconcile the dataset's county spellings (`LeSueur`, `Lac Qui Parle`, `Saint Louis`) to TopoJSON feature names; `resolve_county`/`county_feature_map` do the join; `assert_county_coverage(counties)` is the startup guard — all 87 dataset counties must map to exactly one feature or it fails loudly — called from `app.py` at import time right after the base-DataFrame preload succeeds, alongside warming `cache._county_crosswalk()`. Imported only by `app.py`; `cache.py`/`data.py` don't depend on it. |
| `account.py` | User accounts as pickles under `user/`. Create/retrieve/history-add/revert, plus **learning-module `progress`/`state` helpers** (`get_progress`, `set_progress`, `set_lesson_state`) and the `is_educator` role flag. Educator-portal additions: `create(..., classes=)` records class memberships; `add_class`/`remove_class` keep the account's `classes` list in sync with a roster; `reset_progress` and `delete_account` back the portal's roster-management ops. Request-path-optimization additions: `retrieve` is memoized per request in `flask.g` (`g._account_cache`, guarded by `has_app_context`; every writer drops the entry — P1) and `set_history_count` stamps the filter-apply route's remaining-cases count onto the active history entry so the sidebar badge renders without a history replay (P2; revert restores the reverted-to entry's own stamp). |
| `lessons.py` | Learning-modules loader/validator: `list_modules`, `get_module`, `validate`, `save_module` over `lessons/*.json`. Pure stdlib module (no Flask), mirrors `account.py`. `list_modules` is memoized on a directory signature (each file's name + mtime + size), so authored edits still show up without a restart (request-path P1). |
| `classroom.py` | **Educator-portal class model.** Pure stdlib (no Flask), mirrors `lessons.py`/`account.py` over a git-ignored `classes/<class_id>.json` store. `create_class`/`get_class`/`list_classes`, `find_by_join_code` (case-insensitive, skips archived), roster ops (`enroll`/`remove_student`), `rotate_join_code` (never touches the immutable `class_id` or roster), `set_assignments`/`get_assignments`, `set_email_policy`/`email_allowed`, `set_policy` (retake/feedback), `archive`/`unarchive`, and `validate`. Immutable `class_id` = slug + random suffix; rotatable `join_code` from an unambiguous alphabet (no `0/O/1/I/L`). Schema in `EDUCATOR_PORTAL_PROMPTS.md` Appendix A. |
| `analytics.py` | **Educator-portal attempt log.** Pure stdlib. One append-only JSONL per student at `user/<userid>.attempts.jsonl` (the full history of graded attempts — distinct from `progress['answers']`, which keeps only the latest per step). `log_attempt`/`read_attempts`/`delete_attempts` + pure aggregators (`item_stats`, `stuck_questions`, `last_active_ts`, `question_stats`) folded across a roster by the dashboard. `STUCK_ATTEMPTS` = the repeated-miss triage threshold. Format in `EDUCATOR_PORTAL_PROMPTS.md` Appendix B. |
| `make_history.py` | Builds history entry dicts (`action` list + human-readable `desc`). |
| `moc.py` | `MnOffenseCodes.CODES` — a huge (~1800-line) nested dict decoding the Minnesota Offense Code. Pure data + structure. |
| `util.py` | `ordinal()`, bcrypt `get_hashed_password` / `check_password`, and `normalize_password` — the single pre-hash/pre-verify normalization (`html.escape`, kept for hash compatibility; **don't change it without a migration**). |
| `codebook.xml` | Maps dataset column names → human descriptions; each entry also carries a `group` attribute placing the column in an explore column-browser category (display order in `Data.GROUP_ORDER`). Loaded by `Data.__init__` (descriptions → `self.codebook`, groups → `self.groups`). Some entry names don't match real dataset columns (see gotchas). |
| `settings.xml` | seaborn palette/style (`deep` / `darkgrid`). Not heavily used yet. |
| `test.py` | Ad-hoc scratch script for the history→cache-key encoding. Not a real test suite. |
| `test_base_immutability.py` | **Guardrail for the base DataFrame optimization**: asserts the base frame is byte-for-byte unchanged after the full filter/read pipeline and that `cache._execute` matches direct filtering. Run `uv run python test_base_immutability.py`; must keep passing — the load-once/CoW sharing rests on it. Extended for visualization expansion: also exercises `Data.aggregate_by_group` (count/mean/mode, plus district/region group columns), the raw `county` crosswalk `groupby`, and `base[CORRELATION_SUBSET].corr()` — all asserted read-only over the shared base. Extended again for the request-path optimization (P3): a filtered state executed twice must be served from the slice LRU as the *same* frame object, byte-identical to a direct boolean filter, and unchanged after a full `get_column_info`/`get_table`/`aggregate_by_group`/`get_moc_options` pass over it. |
| `test_map_filter_equivalence.py` | **Guardrail for map-as-filter** (visualization-expansion Phase 11, the "vital" phase). For every county/district/region shape — not a sample — asserts the choropleth's click-derived filter token round-trips and resolves to the identical `cache/data/` dir as hand-typing the same filter (district encodes as `"4.0"`, never `"4"`); the same equivalence for the Filter view's map, its OR-multiselect path, and the `safe_return_target` open-redirect guard on the `next` field. Run `uv run python test_map_filter_equivalence.py`. The failure mode it guards against is silent: a wrong token would resolve to a *different but plausible* cache dir. |
| `perf/` | **Request-path-optimization measurement scaffolding** (P0), committed to the repo (unlike the base-df golden scripts). `profiling.py` — the env-gated timing shim (`@timed('label')` + `span()`; fully unwrapped, zero overhead, when `PROFILE_REQUESTS` is unset; thread-local counters + `REQUEST_LOG` filled by `app.py`'s before/after_request hooks). `benchmark.py` — the repeatable four-flow driver (`uv run python -m perf.benchmark`; uses a dedicated `perf-bench/bench` account and clears its target cache dirs + the slice LRU for genuinely cold runs). `BASELINE.md` — the Phase 0 before-numbers **and** the all-phases-landed after-numbers. |
| `templates/` | Jinja2. `layout.html` is the base — the Phase 1 **workbench shell**: top bar (nav + theme toggle + identity), data-state **sidebar** (count badge, filter chips, Clear data; `{% block sidebar_extra %}` hosts view-specific modules), toast region, confirm `<dialog>`, htmx progress bar; others extend it via `{% block body %}`. `explore.html` + `templates/partials/` (`column_browser.html`, `explore_landing.html`, `explore_column.html`) are the Phase 2 statistics workbench — partials render standalone on htmx fragment requests (`fragment=True` adds the `<title>` htmx uses to retitle the page) and are `{% include %}`d on full loads. `compare.html` + `partials/compare_builder.html`/`compare_results.html` are the Phase 3 crosstab workbench on the same pattern (replacing the deleted `perm_menu.html`/`perm.html`). `filter.html` + `partials/filter_landing.html`/`filter_column.html`/`filter_preview.html`/`filter_zero.html` are the Phase 4 **Filter workbench** (same fragment pattern; the sidebar reuses the now-parametrized `column_browser.html` pointed at the filter routes); geography columns (`county`/`district`/`region`) additionally render `partials/filter_map.html` (visualization-expansion Phase 11) beside/below the categorical or numeric control. `moc1.html`/`moc.html` are the rebuilt offense-code chooser + 5-slot stepper. The Phase 4 rewrite deleted `filter_boolean.html`/`filter_boolean_menu.html`. `visualize.html` + `partials/visualize_view.html` are the visualization-expansion **Visualize workbench** — same shared-renderer/`wants_fragment()` pattern, sidebar reuses the parametrized column browser; one builder form (chart-type → column/measure/aggregate/grain pickers) dispatches to six chart types (pie, treemap, waterfall, choropleth, scatter/bubble, correlation matrix), all documented in `STYLEGUIDE.md`. `partials/other_cutoff_slider.html` is the reusable "Other"-cutoff long-tail control shared by the Explore distribution bar, the Visualize pie, and the Visualize treemap. `error.html` renders the styled 404/500 handlers. Learning-modules views (Phase 5 restyled + docked): `lesson_catalog.html`, `lesson.html`, `lesson_step.html` (extends `layout.html`, fills the new `{% block dock %}`; the main area `{% include %}`s `partials/lesson_data.html` — the read-only sandbox data view), `admin.html`, `admin_edit.html`. (`info.html`/`info_menu.html` were deleted in Phase 2.) **Educator-portal views** (all extend `layout.html`, component-system + both themes): `admin.html` is the portal home (Classes + Lessons); `admin_classes.html` (list + create form), `admin_class.html` (detail: join code, roster, email/retake policy, class tools), `admin_class_assignments.html` (per-module assignment editor), `admin_class_progress.html` (progress dashboard + "needs attention" triage + item-level miss rates), `admin_classes_compare.html` (section comparison), `admin_student_attempts.html` (answer-context inspection), `admin_student_delete.html` (two-step full-deletion confirm), `admin_module_answers.html` (computed answer key). Auth: `login.html`/`new.html` (overloaded class-code box) + `join.html` (logged-in "Join a class"). |
| `lessons/` | Authored learning-module content (`<id>.json`) + `README.md` schema. **Safe to commit** (unlike `user/`). |
| `LEARNING_MODULES_PROMPTS.md` | Phased build plan for the learning-modules feature. All phases are now implemented; the doc still reads as forward-looking. |
| `EDUCATOR_PORTAL.md` | **Design/scope authority** for the educator portal + class-code system: features (P0/P1/P2), the resolved class & identity model, privacy rules, open questions. **Auth + all of P0 and P1 are now built** (P2 deferred); read before touching that feature. |
| `EDUCATOR_PORTAL_PROMPTS.md` | Phased build order (14 phases, 0–13, each with a complexity rating → suggested model) for the educator portal + class-code system + auth hardening, plus Appendix A (class schema) and B (attempt-log format). **All phases done** — see "Educator portal (implemented)" below. |
| `UI_OVERHAUL_PROMPTS.md` | Phased build plan for the UI/UX overhaul (sidebar workbench redesign). **Phases 0 (hygiene/tokens/vendored assets), 1 (workbench shell), 2 (explore workbench), 3 (compare workbench + CSV export), 4 (filter workbench: live previews, searchable values, MOC stepper), 5 (docked lessons + checkpoint wiring), 6 (auth pages/landing/logged-in home), and 7 (responsive/a11y/dark QA + `style.css` removal) are done** — the overhaul is feature-complete; see "In progress: UI/UX overhaul" below. |
| `STYLEGUIDE.md` | **Design authority** for all UI work: tokens (light+dark), typography, layout, components, htmx conventions, a11y checklist. Read it before touching `templates/` or `static/`. |
| `BASE_DATAFRAME_OPTIMIZATION.md` | **Design/scope authority** for the runtime memory/latency optimization of the data layer (load-once / categorical-shrink / cross-worker share of the base DataFrame). Measured numbers, the immutability safety argument, the `float64` constraint, expected impact. Read before touching how `_execute`/`Data.load` build the base. **Levers A–D all built on `base-df-optimization` (Phases 0–4).** |
| `OPTIMIZATION_PROMPTS.md` | Phased build order (Phases 0–4) for the base DataFrame optimization above, house-style like the other `*_PROMPTS.md`. **All phases done (categorical + load-once + Parquet + `--preload`).** |
| `VISUALIZATION_EXPANSION.md` | **Design/scope authority** for the Visualize workbench: a new top-level tab with an extensive chart vocabulary (pie, treemap, waterfall, choropleth, scatter/bubble, correlation matrix) + map-as-filter, all over the current filtered slice. Verified data facts (geo encodings, numeric columns), the substrate-reuse argument, the confounding/`float64`/immutability constraints, risks. Read before touching the viz work. **Implemented — all 5 tiers/16 phases built on `visualization_expansion`; one acceptance criterion (a lesson using a chart) is tracked as an open gap** — see "Done: visualization expansion" below. |
| `VISUALIZATION_EXPANSION_PROMPTS.md` | Phased build order (16 phases, 0–15, across 5 tiers) for the visualization expansion, each with an effort · risk rating and a **recommended model** (Sonnet rarely / Opus with escalating effort incl. ultra / Fable only for the vital P11 cache-compat linchpin). House-style like the other `*_PROMPTS.md`. **All phases done.** |
| `REQUEST_PATH_OPTIMIZATION_PROMPTS.md` | Phased build order (Phases 0–5) for the **request-path optimization** — the per-request work layered on top of the base-df levers (measurement harness, per-request `account.retrieve` memo, sidebar badge without a replay, the filtered-slice LRU, `get_table`/`num_each` vectorization). Self-contained (rationale + build order in one doc), house-style like the other `*_PROMPTS.md`; each phase carries an effort · risk rating and a **recommended model from a four-model vocabulary — Sonnet ultracode / Opus xhigh / Opus ultracode / Fable xhigh** (Fable reserved for the Phase 5 `.bin` byte-identity linchpin, mirroring its P11 role in the viz prompts). **All phases done (0–5) on `optimizations-minor`; Phase 5 took the order-preserving option (a), so no `.bin` byte changed and no cache/golden re-warm was needed.** Before/after numbers in `perf/BASELINE.md`. See "Done: request-path optimization" below. |
| `static/css/tokens.css`, `static/css/base.css` | Phase 0 token system: all design tokens (both themes, exact `STYLEGUIDE.md` tables — plus `--overlay` for drawer/dialog backdrops) and reset/typography/focus/reduced-motion. Loaded first; theme switches via `data-theme` on `<html>` (FOUC-guard inline script in `layout.html` — which also sets a `js` class gating JS-only CSS — toggle in `static/js/theme.js`, persisted to `localStorage.theme`, fires a `themechange` event). |
| `static/css/components.css`, `static/css/views.css` | Phase 1 shell styles per the styleguide's file organization: `components.css` = buttons/badges/chips/toasts/dialog/alerts/empty-state/loading; `views.css` = top bar, workbench grid, sidebar + tablet drawer, breakpoints, **phone shell (data-state bar, bottom nav, sticky-first-column tables, bottom-sheet dock — Phase 7)**. The retired `style.css` is gone (Phase 7); its still-live base rules (`.container`, bare `h1`/`h2`/`h3`/`p`) moved here + into `base.css`. |
| `static/js/app.js` | Phase 1 shell behaviors (vanilla, no build step): toast auto-dismiss + `HX-Trigger`/`htmx:responseError` toast paths, `[data-confirm]` dialog interception, sidebar drawer with focus trap (Phase 7: opened by **any** `[aria-controls="sidebar"]` trigger — the tablet ☰ or the phone data-state bar — focus returns to the opener), htmx-bound global progress bar, `[data-loading]` submit feedback ("Computing statistics…"). Phase 3 added the **searchable picker**: a `[data-picker]` wrapper around a native `<select>` gets a filtering combobox (arrows/Enter/Esc); the hidden select keeps carrying the form value (and is the no-JS fallback). |
| `static/js/compare.js` | Phase 3 compare behaviors: stat toggle (sets `data-stat` on the crosstab — pure CSS show/hide, since all four stats ship in the markup — updates `aria-pressed`, and re-shades the `.heat-N` heatmap from each cell's `data-heat-<stat>` attributes) and the grouped-bar companion chart (theme-aware, ≤8×8 tables only, re-rendered on `themechange` and history restores). **The chart renders on `htmx:afterSettle` (not `afterSwap`) + a next-frame `chart.resize()`** — the swapped DOM/scroll must settle before Chart.js measures the container, or it intermittently paints blank until a manual refresh; don't move it back to `afterSwap`. Loaded (with `chart.umd.min.js`) only via `compare.html`'s `{% block head %}`. |
| `static/js/explore.js` | Phase 2 explore behaviors: distribution chart (Chart.js; colors read from CSS tokens at render time, re-rendered on `themechange` and history restores; horizontal bars when labels run long), column-browser search, value-table search + "show more" pagination, active-column `aria-current` sync, tablet-drawer auto-close on column pick. **The chart renders on `htmx:afterSettle` (not `afterSwap`) + a next-frame `chart.resize()`** (interactive bits — table/active-column — still run on `afterSwap`): Chart.js must measure the container after the swap/`show:window:top` scroll settles, or it intermittently paints blank until a refresh; don't move it back to `afterSwap`. Loaded (with `chart.umd.min.js`) only via `explore.html`'s `{% block head %}`. |
| `static/js/filter.js` | Phase 4 filter-workbench behaviors: column-browser search + active-column `aria-current` sync (against `#filter-view`), categorical value-list search + "Select shown"/"Clear" bulk actions, and MOC option/category table search. The live "~N cases match" preview is pure htmx (`hx-get` on the preview element) and needs no JS here — all of this is progressive enhancement over plain forms/links. Loaded via `filter.html`/`moc.html`/`moc1.html`'s `{% block head %}`. Visualization-expansion Phase 11 added the map input: `initFilterMap()` (bound on `htmx:afterSettle`, using the shared `geomap.js` plumbing) draws the county/district/region canvas and wires clicks to fill/toggle the existing form controls and fire `change` — the map is progressive enhancement; the categorical list/value input stays the complete no-JS/screen-reader path. |
| `static/js/visualize.js` | Visualization-expansion Visualize-view behaviors, loaded only via `visualize.html`'s `{% block head %}` (after `otherbucket.js`/`geomap.js`/the treemap and geo plugins). Reads one of five embedded `<script type="application/json">` payloads and renders the matching chart: `renderPie`, `renderTreemap`, `renderWaterfall` (Chart.js floating bars + an optional running-total line), `renderScatter` (bubble radius ∝ √count), and `renderChoropleth`/`drawChoropleth` (fills read the 8 `.heat-N` legend swatch colors so map/legend/crosstab stay in lockstep; `onClick` → `applyGeoFilter`, a hidden-form POST to the existing filter-apply route). The correlation matrix has no chart — it's a plain server-rendered `.heat-N` table. Small-N choropleth texture is a hand-rolled `hatchPattern()` `CanvasPattern` (diagonal stripes from an offscreen canvas tile) — **no `patternomaly` dependency**, despite the original plan considering one. Also here: chart-type picker field show/hide, the correlation column-subset picker (search + soft 8-cap), and companion-table search/"show more". **Same `htmx:afterSettle` + next-frame `resize()` lifecycle as `explore.js`/`compare.js`.** |
| `static/js/geomap.js` | Shared map plumbing used by *both* the Visualize choropleth and the Filter view's map (`filter.js`): registers the `chartjs-chart-geo` plugin components (the plugin doesn't self-register), fetches/memoizes the vendored TopoJSON once, and dissolves county geometry into district/region shapes at runtime via `topojson.merge` (memoized) per the data-derived crosswalk — so there are no separate district/region geometry files. Exposes `window.GeoMap`. |
| `static/js/otherbucket.js` | The reusable **"Other"-cutoff slider** control's JS half (markup in `templates/partials/other_cutoff_slider.html`): `bucket(payload, cutoff)` re-slices a value list into a head + "Other" tail entirely client-side (no refetch); `wireSlider()` binds the range input. Shared by three call sites: the Explore distribution bar, the Visualize pie, and the Visualize treemap. Exposes `window.chartBucket`. |
| `static/js/vendor/` | Vendored, pinned htmx 2.0.10 + Chart.js 4.5.1 + (visualization expansion) chartjs-chart-treemap 3.1.0 + chartjs-chart-geo 4.3.6 (`VERSIONS.md` is the manifest; never hand-edit). Inter variable font at `static/fonts/InterVariable.woff2`. `static/geo/mn-counties-topo.json` (~20 KB, derived from `us-atlas@3/counties-10m.json`, pruned to MN's 87 counties) is the one geometry file district/region shapes dissolve from at runtime. htmx is loaded by `layout.html`; Chart.js by each view that charts (`explore.html`, `compare.html`, `lesson_step.html`, `filter.html`, `visualize.html`); the treemap plugin loads only on `visualize.html`, the geo plugin on `visualize.html` and `filter.html` (for its map). **No `patternomaly`** — small-N texture is hand-rolled Canvas 2D. |

## Key data structures

**History entry** (stored in `user['history']`):
```python
{'desc': 'human readable', 'action': ['f', column, operation, value], 'active': True/False}
```
- `action[0]` codes: `f` = single filter, `o` = OR-same-column (value is a list),
  `d` = OR-different (stubbed), `a` = AND (stubbed).
- `operation` ∈ `eq, ne, gt, ge, lt, le`.
- Base entry has `action: None` → triggers a full dataset load in `_execute`.
- Only the most recent entry is `active: True`.

**MOC (`moc.py`) `CODES` structure** — decodes a 5-character offense code (`moc1`..`moc5`):
```python
CODES['A'] = [ 'Assault',                 # [0] title (comment '# Complete' = fully coded)
               {'COL':'Category', '1':..., 'A':...},   # [1] digit-2 meanings
               {'COL':'Act', ...},                     # [2] digit-3 meanings
               ... ]
```
- `moc1` is the top-level letter key (`A`=Assault, `H`=Homicide, …).
- Each following dict decodes one digit; `COL` is that digit's label.
- **Multi-digit codes:** a dict may carry `'INC': [3, 4]`, meaning this section consumes
  digits 3 AND 4 together (keys are 2 chars like `'01'`). The *next* dict is then a placeholder
  holding only `'INC': [3,4]` with no code keys. `data.get_moc_options` and `app.filter_moc`
  both special-case `INC` to know which digit position a code writes to. `*` = wildcard (any).

## Routes (in `app.py`)

- `/` — home. **Logged in:** redirects to `/explore` (the workbench is home), flashing a
  "Continue <lesson>" resume toast when a lesson is in progress (`in_progress_lesson`).
  **Logged out:** the marketing landing (`render_landing` → `index.html`). `/landing`
  (endpoint `landing`) always renders the landing, even when signed in. `revert`/`load`
  redirect to `/explore` (not `/`) so a data op never re-fires the resume toast. (Phase 6.)
- `/new`, `/login`, `/logout` — account/session. Session keys: `userid` (`classcode/username`), plus `username`/`classcode`.
- `/explore` (landing) and `/explore/column/<column>[/<sorting>]` — the Phase 2 statistics
  workbench: sidebar column browser + stat cards, Chart.js distribution (top 20 + "Other"),
  segmented sort control, searchable value table. `sorting` ∈ `Data.VALID_SORTING` (default
  `occurrence`, omitted from the canonical URL). One shared renderer (`render_explore`)
  returns the full page normally and just the `templates/partials/` fragment when
  `HX-Request` is present (`wants_fragment()` — htmx history restores get the full page);
  navigation uses `hx-push-url`. Excluded columns and unknown columns bounce to `/explore`
  with a flash. **Legacy redirects:** `/info/` → `/explore`, `/info/<column>[/<sorting>]` →
  `/explore/column/...` — endpoint names `info_menu`/`info_specific` survive for old bookmarks
  only (Phase 5 pointed the lesson deep links at `/explore/...`; nothing internal emits `/info/...`).
- `/explore/table` (builder) and `/explore/table/<dependant>/<x_axis>/<y_axis>` (results) —
  the Phase 3 **Compare (crosstab) workbench**, same shared-renderer pattern
  (`render_compare` + `wants_fragment()`). Builder: three searchable pickers (Measure =
  `#` count-of-cases or a numeric column; Rows; Columns) posting to `/explore/table`,
  which validates and redirects to the results URL. **Orientation:** `data.get_table`
  renders `x_axis` values as row headers and `y_axis` as column headers; the old UI's
  X/Y labels were backwards — the flip is contained (and commented) in the POST handler
  (Rows → `x_axis`, Columns → `y_axis`; users only see "Rows"/"Columns"). Results: all
  four stats (N/mean/median/std) ship in the markup, a JS segmented toggle shows one at a
  time (no refetch; no-JS shows them stacked with labels), 8-step heatmap on the active
  stat, N row/column totals (NaN rows/cols dropped from display), sticky headers, and a
  grouped-bar Chart.js companion for tables ≤8×8. Crosstabs are computed fresh per request
  (never disk-cached — matches pre-overhaul behavior). `dependant == '#'` means count only.
  **Legacy redirects:** `/table` → `/explore/table`, `/table/<d>/<x>/<y>` → results —
  endpoint names `table_menu`/`table` survive for old bookmarks only (Phase 5 pointed the
  lesson deep links at `/explore/table/...`; nothing internal emits `/table/...`).
- `/download?measure=<d>&rows=<x>&cols=<y>` — **implemented in Phase 3**: CSV export of
  that crosstab (`crosstab_csv` reuses the exact `get_table` + `build_crosstab` path, so
  numbers match the screen; UTF-8 BOM for Excel; `Content-Disposition` filename
  `crosstab-<measure>-<rows>-by-<cols>.csv`). Count-only exports one N table with totals;
  a measure adds mean/median/std sections.
- `/explore/filter` (landing) and `/explore/filter/<column>` (GET builder + POST apply) —
  the Phase 4 **Filter workbench** (same shared-renderer + `wants_fragment()` pattern as
  explore/compare; `render_filter`). Sidebar reuses the column browser pointed at the filter
  routes. **Numeric** columns get a comparison select + value input with a live "~N cases
  would match" preview served by `/explore/filter/<column>/preview` (htmx GET — computes the
  count via `get_data(session, history_override=[candidate])`, so it resolves to the SAME
  cache dir the apply will, and the preview count equals the post-apply chip count; no
  history mutation). **Categorical** columns get a searchable multi-select with per-value
  counts, "Select shown"/"Clear", and eq/ne mode; multi-value applies still emit the
  unchanged `o.col.op.v1~v2` OR token. Apply flashes "Filter applied — N cases remain" and
  redirects back to the same filter view (chips + counts refresh; 0 cases → empty state with
  an "Undo last filter" CTA via `revert(len(history)-1)`). **Geography columns** (`county`,
  `district`, `region`) additionally render `partials/filter_map.html` (visualization-expansion
  Phase 11) beside/below the categorical or numeric control — a canvas map that is an input
  device for the *same* form (a click fills the same checkbox/value and fires `change`), never a
  separate filter path; `build_filter_map`/`build_geo_dissolve` share the county→district/region
  crosswalk (`cache._county_crosswalk`) with the Visualize choropleth, and
  `test_map_filter_equivalence.py` pins that a map click and its hand-typed equivalent resolve to
  the identical cache dir.
- `/explore/moc/` (offense-code chooser, replaces the `moc1.html` table) and
  `/explore/moc/<moc1>/<moc2>/<moc3>/<moc4>/<moc5>/<active>` (GET stepper + POST apply) — the
  Phase 4 **MOC drill-down**: a 5-slot code stepper (each slot shows its digit + decoded
  meaning; wildcards read "Any"; INC multi-digit sections render as one merged slot that
  distributes a multi-char code across its digit positions). The remaining-counts table below
  lists the active slot's options with the case count each would leave (`get_moc_options`).
  Apply emits one `f.mocN.eq.X` filter per set digit (cache-compatible), flashes the remaining
  count, and returns to the chooser.
- **Legacy filter redirects:** `/filter/` and `/filter/boolean/...` → `/explore/filter[...]`;
  `/filter/moc/...` → `/explore/moc/...`. Endpoint names (`filter_menu`, `filter_boolean`,
  `filter_moc1`, `filter_moc`) survive for old bookmarks.
- `/visualize` (GET only) — the visualization-expansion **Visualize workbench**
  (`render_visualize` + `wants_fragment()`, the same shared-renderer/fragment pattern as
  explore/compare/filter). All state is URL query params (`chart`, `column`, `column2`,
  `measure`, `aggregate`, `grain`, repeated `cols`) — hard-refresh- and lesson-deep-link-safe; an
  unknown `chart` id falls back to the blank-canvas builder rather than 404ing. One builder
  (chart-type picker → column/measure/aggregate pickers, reusing `build_compare_options`)
  dispatches to six chart types (`VIZ_CHART_TYPES`, all `status: 'ready'`): **pie** and
  **treemap** (both share `partials/other_cutoff_slider.html`'s "Other"-cutoff control),
  **waterfall** (year-over-year over `sentyear`, Chart.js floating bars), **choropleth**
  (county/district/region grain toggle, `chartjs-chart-geo`, small-N hatch below
  `CHOROPLETH_MIN_N`), **scatter/bubble** (aggregated lattice, guarded by `SCATTER_MAX_CELLS`),
  and **correlation matrix** (a user-picked 2–8 numeric-column subset, `DataFrame.corr()`,
  computed fresh — never disk-cached — flagging near-mechanical pairs at
  `|r| ≥ CORRELATION_MECHANICAL_THRESHOLD` rather than hiding them). Every chart builder
  (`build_treemap`/`build_waterfall`/`build_choropleth`/`build_scatter`/`build_correlation` in
  `app.py`) reads the active history through `Data.aggregate_by_group` and never mutates the
  shared base. **Map-click → filter and the choropleth's per-row "Keep only" button both POST
  the existing `/explore/filter/<column>` route** (`explore_filter_column`) — there is no
  bespoke click-filter route, so the resulting history entry, chip, and cache dir are
  byte-identical to hand-typing the same filter (`safe_return_target` guards the `next` redirect
  target against open-redirect). Nav entry sits between Filter and Lessons in both the top bar
  and the phone bottom nav.
- `/load` — clear history (revert to the base full-dataset entry); no longer linked from the
  nav (the sidebar's confirmed "Clear data" button hits `/revert/1` instead). `/revert/<n>` —
  revert the history to a prior entry (`account.history_revert`, truncating to `history[:n]`;
  `n` is the 1-based history position — the sidebar chips link here: clicking a chip reverts
  to that step, the last chip's `×` removes just that step). Filter apply, revert, and clear
  all `flash()` a message that `layout.html` renders as a toast.
- **Learning modules:** `/lesson` (catalog with per-module status + resume), `/lesson/<module_id>` (overview), `/lesson/<module_id>/<int:step>` (Phase 5 **docked lesson**: workbench shell + lesson dock; the main area shows the step's read-only sandbox data, the sidebar shows the "Lesson data" module; POST grades a `question`, `checkpoint` steps compare state), `/lesson/<module_id>/complete` (mark done). See "Learning Modules" below.
- **Educator portal (educators only, `require_educator()` / `require_class_owner()`):**
  `/admin` (portal home — your classes + your authored modules), `/admin/edit[/<module_id>]`
  (lesson authoring → validated JSON to `lessons/`). Classes: `/admin/classes` (list + create),
  `/admin/classes/<class_id>` (detail: join code, roster, email + retake/feedback policy),
  `/admin/classes/<class_id>/assignments` (per-module required/optional/hidden/scheduled + dates),
  `/admin/classes/<class_id>/progress` (dashboard + "needs attention" triage + item-level miss
  rates), `/admin/classes/compare` (section comparison), `.../gradebook.csv` (flat CSV export,
  BOM), `.../policy` (retake/feedback POST). Roster ops (owner-guarded, `[data-confirm]`ed):
  `.../rotate-code`, `.../archive`|`/unarchive`, `.../roster/<userid>/remove`|`/reset`|`/delete`
  (full account+log deletion is a two-step confirm page), `.../roster/<userid>/attempts`
  (answer-context inspection). `/admin/modules/<module_id>/answers` — computed answer key (any
  educator; generated fresh, never cached). See "Educator portal (implemented)" below.
- **Accounts / enrollment:** both `/new` and `/login` carry an **"I'm an educator" checkbox**
  (`is_educator` form field); only **`/new`** also has a student **class-code box** — the join
  code is entered **once, at signup**, and is baked into the account's namespace, so **`/login`
  is just username + password** (no code re-entry). When the box is checked → the account is
  namespaced under `edu-<username>` (`educator_namespace()`; the `edu-` prefix is backend-only,
  never typed) — `/new` creates it, `/login` looks it up directly. On **`/new`** with the box
  unchecked, the class-code box is resolved by `resolve_class_code`: blank → public/`unmanaged`;
  a live **join code** → student enrolled under the class's immutable `class_id` namespace
  (roster + the pickle's `classes` set together); a literal `edu-…` still resolves to an educator
  account as a **legacy fallback**; else → error. On **`/login`** the classcode is not asked for:
  the checkbox scopes the lookup to `edu-<username>`, and an unchecked login resolves the account
  by looking the username up across every non-educator namespace
  (`account.find_userids_by_username`) and letting the **password** pick the match (so a username
  shared across classes, and legacy bare-directory accounts, still authenticate — the generic
  "Username or password is incorrect." keeps `/login` non-enumerable). `email_allowed`
  enforces a class's email-domain policy at join time. `/join` — logged-in "Join a class" by code
  (doesn't re-namespace the account; only grows the roster + `classes`). `/` (`index`) clears a
  **stale session** (cookie → deleted account) and falls back to the landing instead of erroring.
- `/share/<chain>` — **shareable data state** (educator feature, but any logged-in user can open
  one): validates an encoded filter-token chain (`parse_share_token`; length-capped), resets the
  user's **own** history to base, replays the chain via `make_history`, and lands in `/explore`.
  Unlike lessons, this **intentionally mutates the user's history**. The sidebar data-state
  module offers a "Copy link" affordance built from the current history.
- `/guide` — static guide page (replaced the old buggy `/lesson/get_started` stub). `/save`, `/other`, `/settings` — still **stubs** returning "WIP, Feature Not Implemented" (`/download` was implemented in Phase 3, see above).

Every data route follows the pattern: `if is_logged_in(): ... else: return not_logged_in()`.
(`not_logged_in()` is htmx-aware: on an `HX-Request` it answers with an `HX-Redirect` header
so the client does a full-page redirect instead of swapping the login page into a fragment.)

Styled `404`/`500` handlers render `error.html` (via the never-raising `current_user()` helper).
The `inject_globals` context processor also computes `datastate` (current + total case count)
for the sidebar badge on every logged-in render — since request-path P2 it reads the count
stamped on the active history entry (`account.set_history_count`, written by the filter-apply
route; a revert restores the target entry's own stamp, and the base entry maps to the memoized
`dataset_total()`) with `get_data` as the fallback for unstamped entries, so the badge no
longer forces a history replay after applying a new filter. `hx_toast()` sets the
`HX-Trigger` header for htmx-response toasts (used from Phase 2 on).

## Storage layout (all git-ignored — see `.gitignore`)

- `dataset.sav` — raw SPSS source (~141 MB). Not in git.
- `cache/raw.parquet` — typed columnar base the runtime **prefers** (~23 MB; Lever C). Not in git.
- `cache/raw.csv` — human-inspectable CSV base + fallback loader (~242 MB, exceeds GitHub's 100 MB limit). Not in git.
- `cache/data/<history-path>/…bin` — pickled computed results.
- `user/<classcode>/<username>.pickle` — **user accounts, including bcrypt password hashes.**
  Default classcode when none given: `unmanaged`; enrolled students are namespaced under their
  class's `class_id`. **Never commit this dir** (private user data).
- `user/<userid>.attempts.jsonl` — **append-only attempt log** per student (educator portal;
  `analytics.py`), sitting beside the account pickle under the same git-ignored `user/` tree.
- `classes/<class_id>.json` — **class objects** (roster, join code, assignments, policies;
  `classroom.py`). Rosters tie to real students, so — like `user/` — **git-ignored, never commit.**

## Conventions & gotchas

- **UI/styling changes follow `STYLEGUIDE.md`** — tokens only (no raw hex in components), no inline styles, both themes, no runtime CDN assets. Sequencing for the redesign is in `UI_OVERHAUL_PROMPTS.md`.
- **Crosstab X/Y orientation:** `data.get_table(d, x, y)` uses `x` values as row headers and `y` as column headers. The pre-overhaul form labeled these backwards ("flipped due to display issues"); since Phase 3 the flip is **contained in `explore_table`'s POST handler** (Rows → `x_axis`, Columns → `y_axis`, commented there). Don't rename `get_table`'s args or the `dependant/x_axis/y_axis` route args — legacy URLs and lesson deep links depend on them.
- `float64` columns coerce filter values to float so `16 == 16.0`. Numeric-only comparisons (`gt/ge/lt/le`) are validated against `float()` in the boolean-filter route.
- Rounding idiom throughout `data.py`: `round(x * 10**precision) / 10**precision`.
- Cache-path bug guard: trailing `/` is stripped in `get_data` before appending `_data.bin`.
- The header comment in `cache.py` is copy-paste-wrong (says `precache.py`; `util.py`'s was fixed in educator-portal Phase 0). Filenames in the table above are authoritative.
- **Codebook/dataset name mismatches:** `codebook.xml` documents `saytlnth`, `FindRestOnly`,
  `subscspred` but the dataset columns are `staylnth`, `FineRestOnly`, `subcscpred` (and
  `ethnic`, `sentord`, `fine`, `mocwpn`, `weapon`, `post802`, `Raceorig`, `prescon`, `dconv`,
  `countoff`, `recodeh`, `sextrafficking` have codebook entries but no dataset column at all) —
  those columns are invisible in the app. Renaming the tags would document them; left for the
  author to confirm. (Phase 2 already fixed the duplicated `<preason2>` → `<preason3>` and a
  stray `>` in `pper`'s text.)
- **Cached pickles can hold stale codebook text.** `_data.bin` stores the codebook-description
  dict and `<column>.bin` stores a `header`, both frozen at cache-build time. The explore views
  therefore read display names from the live codebook parse (`CODEBOOK` in `app.py`), never
  from the cache; the Phase 3 compare views do the same (the old crosstab menu, which showed
  cached descriptions, is gone).
- Line-ending: repo is on Windows; git may warn about LF→CRLF. Harmless.

## Known issues / incomplete (don't assume these work)

- ~~**Login does not verify the password.**~~ **Fixed in educator-portal Phase 0.** `/login`
  now verifies with `util.check_password`; both `/new` and `/login` run the password through
  the single `util.normalize_password` helper, which preserves the historical `html.escape`
  normalization — **changing it invalidates every stored hash** (needs a migration; see the
  loud comment in `util.py`). Unknown username and wrong password produce the same generic
  "Username or password is incorrect." message, so `/login` can't be used to enumerate users
  (the existence check on `/new` still discloses, by design). On success, all three session
  keys are set from the stored account (classcode already cleaned to `unmanaged` when blank).
- ~~**Hardcoded Flask `secret_key`**~~ **Fixed in educator-portal Phase 0.** `app.py` now reads
  `SECRET_KEY` from the environment; when unset it falls back to a clearly-marked insecure dev
  key and logs a startup warning (on the fallback, sessions are forgeable and not portable
  across machines). The old literal key shipped in this **public** repo — never reuse it.
- **Account create/login existence checks — fixed.** `get_user_list` now returns bare usernames
  (it used to return `.pickle`-suffixed filenames, so `/new` never detected duplicates — it fell
  through to `create` and crashed — and `/login` rejected every existing user); and
  `account.create` now returns `retrieve(userid)` (was `retrieve(username)`) on the already-exists
  path.
- ~~`/new` sets `session['userid']` but not `session['username']`/`session['classcode']`.~~
  **Fixed in Phase 6** — `/new` now sets all three (from the created account), matching `/login`.
- **Auth is verified but not *hardened*** (be honest about the posture). Login checks the
  password and `SECRET_KEY` reads from the environment, but there is no rate-limiting/lockout,
  no HTTPS enforcement, and the **`edu-` educator role is still self-selectable at signup**
  (anyone can create an `edu-` account — it is a convenience, not a trust boundary;
  `require_class_owner` scopes an educator to their *own* classes but not who may become an
  educator). Treat the portal as classroom-trust, not public-internet-grade.
- Stubbed/`pass`-only: `Data.filter_and`, `filter_or_diff` (partial), `make_history.filter_or_diff`, `filter_and`, `moc_or`; the `d` and `a` action codes are not handled by `_execute` (raise `ValueError`).
- ~~**Learning-module `checkpoint` steps are not wired up.**~~ **Fixed in Phase 5.**
  `app.build_checkpoint` compares the step's active lesson state (`resolve_lesson_state` — the
  step's own `state` or the inherited `progress[module_id]['state']`) to `expect_state` as a
  token **multiset** (`collections.Counter` diff), renders pass ("✓ Your data matches") or a
  fail diff ("Still needed: …" / "These shouldn't be applied: …" via `describe_token`), and
  gates Next like `require_answer`. It reads only the sandboxed lesson state — never the
  student's history. Both shipped lessons now complete. (Note: `current_year` is injected
  globally via a context processor and `index` passes `hero_image_url`, so those earlier
  template-variable gaps are resolved.)

## In progress: UI/UX overhaul (`ui-overhaul` branch)

A full redesign of the presentation layer, planned with the author (2026-07). **All phases
(0–7) are done** (see below). The overhaul is feature-complete on the `ui-overhaul` branch.

**Phase 0 (done — foundations, no redesign):** every child template's nested `<body>` (and
`load.html`/`guide.html`'s nested `<head>`) removed — `layout.html` owns the document shell
and a unified `<title>` via `{% block title %}` ("Minnesota Sentencing Explorer — <Page>");
flash rendering moved out of the `{% if error %}` conditional (and `/logout` now flashes a
confirmation, the first real `flash()` call); "disabled" sort/select options render as
non-interactive `<span aria-disabled="true">` instead of live links (killing the
`occurrencee` typo'd href); user-facing "Dependant" → "Dependent"; SVG favicon added;
htmx 2.0.10 + Chart.js 4.5.1 vendored (not yet loaded) and Inter self-hosted;
`tokens.css`/`base.css`/`theme.js` created with the FOUC-guarded light/dark toggle, and
`style.css` re-pointed at the tokens so all current pages already work in both themes.

**Phase 1 (done — workbench shell):** `layout.html` rebuilt as the shell — top bar (brand;
Statistics · Compare · Filter · Lessons nav with `aria-current="page"`; Authoring for
educators; theme toggle; identity + educator badge; logout) and the **data-state sidebar**
that replaced the on-page history table: live count badge ("N of 294,467 cases", from the
`datastate` context processor), filter chips from `history` descs (click a chip = revert to
that step, `<dialog>`-confirmed when it discards >1 step; only the last chip gets an `×`;
"Clear data" button — removed from the nav — always confirms and hits `/revert/1`). Sidebar
is persistent ≥1024px, a focus-trapped slide-over drawer at 768–1023px, hidden <768px with
JS (no-JS keeps it in-flow; phone treatment is Phase 7). Flask flashes render as **toasts**
(auto-dismiss 5s, pause on hover; filter apply/revert/clear/logout now flash); the
`HX-Trigger` toast path and `htmx:responseError` danger toast are wired for later phases.
htmx is loaded + bound to a global top progress bar (views still full-page-navigate);
`[data-loading]` forms (boolean/MOC filter, crosstab builder) show a submit spinner +
"Computing statistics…". Styled 404/500 (`error.html`) + empty-state component. New files:
`components.css`, `views.css`, `app.js`; new `--overlay` token (folded into `STYLEGUIDE.md`).

**Phase 2 (done — explore workbench):** `/explore` + `/explore/column/<col>[/<sorting>]`
replace the `/info` statistics views (old URLs redirect; endpoint names kept for lesson deep
links). One shared renderer serves full pages or `templates/partials/` fragments per
`wants_fragment()`; browser/sort navigation swaps `#explore-view` via htmx with
`hx-push-url`, so every state survives hard refresh. Sidebar gained the **column browser**
(grouped per `codebook.xml` `group` attributes + `Data.GROUP_ORDER`, JS search, excluded
columns disabled with a tooltip — the `!!!WARNING!!!` marker is gone). The statistics view:
stat cards (N, missing, mean/median/std), theme-aware Chart.js top-20+"Other" distribution
(`explore.js`), segmented sort control (links + `aria-current`), sticky-header value table
with search + "show more", and a "Filter this column" CTA into the filter route (wired to
`/explore/filter/<col>` in Phase 4). Display headers come from the live codebook parse, never cached pickles. Codebook
fixes: duplicate `<preason2>` → `<preason3>`, stray `>` in `pper`. New files: `explore.html`,
`templates/partials/*`, `explore.js`; deleted `info.html`/`info_menu.html`.

**Phase 3 (done — compare workbench + CSV export):** `/explore/table` (builder) +
`/explore/table/<d>/<x>/<y>` (results) replace the `/table` crosstab views (old URLs
redirect; endpoint names kept for lesson deep links until Phase 5). The 161-row × 3-radio
builder became three **searchable pickers** (native selects enhanced by the new
`[data-picker]` combobox in `app.js` — keyboard-complete, no-JS falls back to the plain
selects): honest "Measure / Rows / Columns" labels with the internal X/Y flip contained
and commented in the POST handler. Results: segmented **stat toggle** (N/mean/median/std
— all four ship in the markup; `compare.js` swaps `data-stat`, no refetch; no-JS shows
them stacked with labels), **8-step heatmap** on the active stat (`.heat-N` +
`color-mix` ramp, text flips to `--color-on-accent` at step 7 — spec folded into
`STYLEGUIDE.md`), N row/column totals with NaN rows/cols dropped, sticky
row/column/totals headers, grouped-bar Chart.js companion (≤8×8), and the `/download`
stub implemented as the crosstab **CSV export** (same compute path as the view; UTF-8
BOM; `Content-Disposition` filename). New files: `compare.html`,
`partials/compare_builder.html`, `partials/compare_results.html`, `compare.js`; deleted
`perm.html`/`perm_menu.html`.

**Phase 4 (done — filter workbench):** `/explore/filter[/<col>]` (builder + apply) and
`/explore/moc/...` (offense-code chooser + stepper) replace the `/filter/...` views (old URLs
redirect; endpoint names kept). Same shared-renderer/`wants_fragment()` pattern; the sidebar
reuses the **parametrized** `column_browser.html` (new `browser_endpoint`/`browser_target`/
`browser_title` vars, default to the explore ones) pointed at the filter routes. **Numeric**
columns: comparison select + number input + a live "~N cases would match" preview served by
`/explore/filter/<col>/preview` (htmx GET → `get_data(session, history_override=[candidate])`;
same cache dir as the eventual apply, so preview == post-apply count; no history mutation).
**Categorical** columns: searchable multi-select with per-value counts, "Select shown"/"Clear",
eq/ne mode — multi-value still emits the unchanged `o.` OR token (same cache dir as the old
UI). The **MOC stepper** collapses INC multi-digit sections into one merged slot that
distributes a multi-char code across its digit positions; apply emits one `f.mocN.eq.X` filter
per set digit. Every apply flashes "Filter applied — N cases remain" and lands back on the view
you came from; a 0-case result shows the empty state with an "Undo last filter" CTA. Also fixed
`cache.get_moc_options` to encode the history path with `history_item_to_text` (OR-filter `o.`
entries used to crash the bare `'.'.join`). New files: `filter.html`, `partials/filter_landing.html`,
`partials/filter_column.html`, `partials/filter_preview.html`, `partials/filter_zero.html`,
`filter.js`; rebuilt `moc1.html`/`moc.html`; deleted `filter_boolean.html`/`filter_boolean_menu.html`.

**Phase 5 (done — docked lessons + checkpoint wiring):** `/lesson/<id>/<int:step>` renders the
workbench shell with a **lesson dock** (right column ≥1024px via a new `{% block dock %}` in
`layout.html`; a stacked full-width panel below the data at ≤1023px). The **main area** shows a
**read-only** view of the lesson's sandbox data driven by the step's `focus` (`build_lesson_data`
→ `partials/lesson_data.html`: stat cards + Chart.js distribution + value table for `info`, a
stacked-stat crosstab for `table` — reusing the explore markup ids so `explore.js` powers the
chart/search; **no htmx nav and no editing** — the student manipulates their own data in the
workbench tabs). The **sidebar** swaps its data-state module for a read-only **"Lesson data"**
badge + chips (`lesson_chips`/`describe_token`) when a `lesson` context is present; the student's
own history is hidden and **never mutated** (verified byte-identical across a full playthrough).
`checkpoint` is wired (see Known issues, now struck through) and gates Next/Finish. `build_explore`
was replaced by `build_lesson_data`; lesson deep links now target `/explore/...` directly (so
nothing internal emits `/info/...` or `/table/...` — those endpoints stay only for old bookmarks).
`lesson_catalog.html`/`lesson.html`/`admin.html`/`admin_edit.html` restyled to the component
system (status badges, resume, `.field` forms — functional parity, no schema/authoring changes).
New file: `partials/lesson_data.html`; rebuilt `lesson_step.html`. New CSS: lesson dock/progress
dots/checkpoint/prose in `views.css`, textarea fields in `components.css`.

**Phase 6 (done — auth pages, landing, logged-in home):** `index.html` rebuilt as the
styleguide **landing** (hero + honest metric cards + feature grid + CTA; zero inline styles,
no hero image). `/` and `/landing` split: `/` redirects a logged-in user to `/explore` with a
"Continue <lesson>" resume toast (`in_progress_lesson` — `Markup.format`ed flash) and shows the
landing when logged out; `landing` (new endpoint) always renders the landing. `render_landing`
is the shared body. `login.html`/`new.html` are centered `.auth-card`s: visible labels, the
class-code explained (blank → public group; `edu-` → authoring), inline `.alert-danger`
validation (routes pass `errors`, **not** `error`, so the shell's top-of-main alert doesn't
double-render), and the **password field no longer carries a `value`** (was echoed on `login`).
`/new` now sets all three session keys (`username`/`classcode`/`userid`) from the created
account. `revert`/`load` redirect to `/explore` (not `/`) to avoid re-firing the resume toast.
Password verification stays out of scope (a code comment in `login` reaffirms the known issue).
New CSS: landing + auth in `views.css`; `.field-hint code`/`.field-optional` in `components.css`.

**Phase 7 (done — responsive deep pass, a11y, dark QA, cleanup):** the phone shell (<768px)
landed: a fixed **bottom nav** (Explore · Compare · Filter · Lessons, + Author for educators;
decorative inline-SVG icons + text label + `aria-current`) replaces the top-bar section nav,
and a full-width **data-state bar** under the top bar shows the live count/badge and, on tap,
opens the same off-canvas sidebar drawer used at tablet width (so the full data state + column
browser stay reachable — nothing hidden without a path). `app.js`'s drawer now binds **any**
`[aria-controls="sidebar"]` trigger (the tablet ☰ *and* the phone bar), traps focus, and
returns focus to the opener. Wide data tables keep a **sticky first column** and scroll
horizontally inside `.table-wrapper` (never the page); the lesson dock is a **bottom-sheet**
panel (rounded top + grab handle) below the data; `env(safe-area-inset-bottom)` + a body
`padding-bottom` keep the fixed nav off the footer. The legacy **`style.css` was deleted**
(its live base rules — `.container`, bare `h1`/`h2`/`h3`/`p` — moved to `views.css`/`base.css`;
`load.html` rebuilt on `.field`/`.btn`). Verified against the running app at 375 / 768 / 1280px
in **both themes**: no console errors, no failed/external requests (all assets local),
`VERSIONS.md` matches the vendored htmx 2.0.10 / Chart.js 4.5.1 / Inter. New markup:
`.datastate-bar` + `.bottom-nav` in `layout.html`; new CSS in `views.css` (phone shell) and
`base.css` (migrated element defaults).

**Locked direction** (author-approved): sidebar **workbench** IA (`/explore` with htmx
fragment swaps), hand-rolled CSS token system (no build step), Chart.js visuals, light+dark
themes from day one, **docked lesson panel** (lessons run beside live data), fully responsive
including phones, all assets vendored (no runtime CDN — school networks filter them).

**The two documents that govern the work:**
- `STYLEGUIDE.md` — design authority: tokens, typography, layout/breakpoints, component
  specs, htmx conventions, a11y checklist, voice/copy. Any template or CSS change — overhaul
  or not — must follow it; deviations get folded back into it in the same commit.
- `UI_OVERHAUL_PROMPTS.md` — the build order: 8 phases (0 hygiene/tokens → 1 shell →
  2 explore views → 3 crosstab → 4 filters → 5 docked lessons + **checkpoint wiring** →
  6 auth/landing → 7 responsive/a11y/dark QA), each with read-first files, acceptance
  criteria, and don'ts. Old URLs keep working via redirects at every phase boundary; cache
  compatibility (same filters → same cache dirs) is a hard constraint.

Note: Phase 5 fixed the "checkpoint steps not wired up" known issue above; Phase 6 fixed the
`/new` session-keys issue. Password verification and the hardcoded `secret_key` were out of scope
for the UI overhaul but have since been **fixed on the `educator-portal` branch** (Phase 0) — see
"Educator portal (implemented)" and the struck Known issues below.

## Educator portal + class-code system (implemented)

Built across the 14 phases (0–13) in `EDUCATOR_PORTAL_PROMPTS.md` on the `educator-portal`
branch — **auth hardening + all of P0 (features 1–6) and P1 (features 7–12) are done; P2 is
deferred.** Turns the thin `edu-` classcode convention into a real portal and class-code system.
`EDUCATOR_PORTAL.md` and the prompts doc still read partly as forward-looking plans; treat **this
section** (with the routes list and module map above) as the current-state authority.

**Classes as first-class objects (`classroom.py`, `classes/`).** An educator (an `edu-` account)
creates named **classes**, each an **immutable `class_id`** (slug + random suffix) with a
**rotatable `join_code`** (unambiguous alphabet), a roster, per-module `assignments`, an
`email_policy`, and a retake/feedback `policy` — one git-ignored `classes/<class_id>.json` per
class. Rotating the join code never changes the `class_id` or roster (storage keys off the id, so
no student is displaced). This resolves the old role-from-prefix flaw: students **join with a join
code** and stay members (`is_educator=False`), namespaced under the class's `class_id`, instead of
sharing the educator's `edu-` code.

**Educators sign up / in with an "I'm an educator" checkbox** (`is_educator` form field on
`new.html`/`login.html`) — the `edu-` classcode is **never shown or typed**. When checked, the
account lives under `edu-<username>` (`educator_namespace()`): `/new` creates it, `/login` looks it
up by that derived namespace, so no code is entered. The `edu-` prefix stays a backend-only
convention that flips `is_educator` via `account.is_educator_classcode`. A **student enters a
class join code only at signup** (`/new`): unchecked, its **class-code box is lookup-resolved**
(`resolve_class_code`): blank → public/`unmanaged`; a live join code → student enrollment (roster +
the pickle's `classes` written together); a literal `edu-…` → educator (legacy fallback); anything
else → an error. That classcode is then baked into the account's namespace, so **`/login` never
asks for it again** — an unchecked login resolves the account by matching the username across every
non-educator namespace (`account.find_userids_by_username`) and letting the password pick it (a
username shared across classes, and legacy bare-directory accounts, still authenticate).
Email-domain policy (`classroom.email_allowed`) is enforced at join time. The
checkbox is exactly as self-selectable as typing `edu-` was — **no new trust boundary** (see the
residual-posture note under "Known issues").

**Attempt logging (`analytics.py`).** `grade_and_store` appends every graded (non-`free`) attempt
to a per-student append-only JSONL log (`{ts, module, step, type, correct, submitted, state}`,
`state` = the resolved lesson-state tokens at answer time). This is the full attempt *history*,
distinct from `progress['answers']` (latest per step). It powers item-level miss rates, the
"needs attention" triage (`STUCK_ATTEMPTS` repeated misses), and answer-context inspection.

**The portal (`/admin*`, restructured).** Portal home; per-class **progress dashboard** with an
exception-first "needs attention" triage (stuck / inactive), per-student rows, per-module rollups,
and item-level miss rates (`build_class_dashboard`, reading stored progress + logs — nothing
re-graded at render time); **module assignment control** (required/optional/hidden/scheduled +
open/due dates) reflected on the student catalog (`resolve_assignment`/`visible_modules`);
**gradebook CSV export** (flat, BOM, matches the dashboard); **roster management** (rotate code,
remove/reset a student, archive, side-by-side section comparison, and a hard two-step full-account
deletion that also drops the attempt log); **answer-context inspection**; **computed answer keys**
(`build_answer_key`, generated fresh per request, never cached); **retake/feedback policy** threaded
into the student question flow for enrolled students (`resolve_policy`/`question_locked`);
**per-module teaching notes** (`educator_notes` in the lesson JSON, shown only to educators); and
**shareable data-state links** (`/share/<chain>` — the one feature that deliberately mutates the
opener's own history). Every per-class route is behind `require_class_owner()` and re-checks the
target is on *this* class's roster; dashboards show usernames/display names, **never emails**.

**Auth hardening** (Phase 0 prerequisite): `util.check_password` wired into `/login` via the shared
`util.normalize_password` helper (preserving `html.escape` so existing hashes match); `secret_key`
reads from the `SECRET_KEY` environment variable with a warned insecure dev fallback. See the
struck items and the honest residual-posture note under "Known issues" above.

**The two governing documents:** `EDUCATOR_PORTAL.md` (scope & design authority — class/identity
model, privacy, resolved decisions) and `EDUCATOR_PORTAL_PROMPTS.md` (the 14-phase build order +
Appendix A class schema / Appendix B attempt-log format).

## Learning Modules (implemented)

Guided lessons that reuse the history/cache substrate. Built across the phases in
`LEARNING_MODULES_PROMPTS.md` — **all phases are now implemented** on the `learning-modules`
branch. That doc and `lessons/README.md` still read as forward-looking plans (e.g. README says
"Phase 0 is data only"); treat **this section** as the current-state authority.

**Core idea — reuse the history/cache substrate.** A lesson is an ordered list of *steps*; a
step can carry a **data state** expressed as history tokens (the same `f.col.op.val` /
`o.col.op.v1~v2` encoding `cache.history_item_to_text` produces). Because every statistic is a
deterministic function of a history, a step reconstructs its exact filtered dataset via the
existing `_execute`/`get_data` path, and numeric questions are **graded live**
(`Data.get_column_info`) rather than hardcoded — so answers stay correct if the data changes.

**Files:**
- `lessons/<id>.json` — one module: `id`, `title`, `description`, `author` (classcode), optional
  `order` (catalog sort position — lower shows first, missing sorts last), `objectives`, ordered
  `steps`. Schema is documented in `lessons/README.md`. `id` must be `[a-z0-9-]` and match the
  filename stem (enforced by `lessons.validate`; also blocks path traversal). Three shipped
  lessons, sequenced via `order`: `intro-what-this-data-is.json` (data provenance/interpretation
  primer — where the dataset sits in the criminal-justice funnel, unit of analysis, description
  vs. explanation — `order: 0`, read/question-heavy with one `explore` step), then
  `intro-explorer-basics.json` (a hands-on tour of the Explorer's tools, `order: 1`), then
  `intro-descriptive-stats.json` (`order: 2`).
- `lessons.py` — loader/validator: `list_modules`, `get_module`, `validate`, `save_module`.

**Step types:** `read` (body only), `explore` (sets a data `state`; `focus` picks the main-area
view — `info` a column, `table` a crosstab — which the docked lesson renders read-only), `question`
(`numeric` graded live within `tolerance` / `choice` graded by index / `free` stored ungraded),
`checkpoint` (**wired in Phase 5**: `expect_state` is compared to the active lesson state as a
token multiset; pass/fail diff; gates Next — see `build_checkpoint`).

**Data-state override (the sandbox).** Lesson states are applied through the `history_override`
parameter on `cache.get_data` / `cache._execute`, appended on top of the base dataset (or the
student's history) **without ever mutating `user['history']`** — this completes the formerly
no-op `history_override` hook. `cache.history_text_to_item` decodes a token back into a history
`action` for this path. `app.build_lesson_data` / `compute_expected` drive it with `session=None`
so only the lesson's own tokens apply.

**Progress & state** live on the user pickle under `progress` (backwards-compatible via
`user.get('progress', {})`):
```python
user['progress'] = {
  '<module_id>': {
    'step': 3,                          # last-viewed step index (resume pointer)
    'completed': False,
    'answers': {'2': {'type': 'numeric', 'value': 41.7, 'correct': True}},  # keyed by step index
    'state': ['f.moc1.eq.A']            # active lesson data state — NEVER merged into history
  }
}
```
Helpers in `account.py`: `get_progress`, `set_progress` (merges — won't clobber sibling keys),
`set_lesson_state`. An `explore` step with its own `state` **sets** the active state; later
steps inherit it unless they carry their own.

**Grading is entirely server-side** (`app.grade_and_store` never trusts a client "correct"
flag). `numeric` recomputes the expected value from the step's active state via
`app.compute_expected` (`count` → dataset `entries`; `mean|median|std` → `get_column_info`'s
`mean`/`mdn`/`std`), correct if `abs(submitted - expected) <= tolerance`. `require_answer: true`
locks the Next button until an answer is submitted (a soft, URL-bypassable gate).

**Roles / authoring.** `account.is_educator(userid)` reads an `is_educator` flag set at account
creation from a **classcode convention**: a classcode starting `edu-`
(`account.EDUCATOR_CLASSCODE_PREFIX`) grants authoring/portal rights. Login now verifies
passwords (educator-portal Phase 0), but the `edu-` prefix is still **self-selectable at signup**,
so this is a convenience, **not a trust boundary for *who may become* an educator** — see the
residual-posture note under "Known issues." (`require_class_owner()` *does* scope an educator to
their own classes.) Educators use `/admin` + `/admin/edit` to create/edit modules scoped to their
own `classcode`; `require_educator()` guards those routes and `slugify()` sanitizes the module id
before it reaches the filesystem.

## Tooling: uv (dependency & environment management)

Dependencies, the virtualenv, and the Python version are managed by
**[uv](https://docs.astral.sh/uv/)**. The source of truth is `pyproject.toml` + the committed
`uv.lock`; `.python-version` pins **Python 3.13**. `uv sync` builds `.venv/` from the lockfile
(installing a managed Python 3.13 if the machine lacks it), and `uv run …` runs inside it — see
"Running it" and "Data flow / bootstrap" above. (Migrated from pip + `requirements.txt` + stdlib
`venv`; the phased plan is in `UV_MIGRATION_PROMPTS.md` — all phases (0–4) complete.)

**Why it mattered here:** the old stdlib `.venv/` was synced between machines via OneDrive and
was non-portable — it hard-coded another machine's Python path (`C:\Users\sid07\...`) and could
not run on this one. With uv, each machine runs `uv sync` to build its own local `.venv` from the
lockfile and never shares the venv itself. (If the repo lives under OneDrive, exclude `.venv/`
from OneDrive sync.)

**Dependency pinning (important).** `[project].dependencies` mirrors the old `requirements.txt`
exactly — the same intentional hard pins (`Flask==3.0.0`, `bcrypt==4.1.2`, …) and the same 8 deps
left loose (`contourpy`, `kiwisolver`, `matplotlib`, `numpy`, `pandas`, `Pillow`, `pyreadstat`,
`seaborn`). Those 8 are held at known-good versions by `[tool.uv] constraint-dependencies`, so
`uv.lock` reproduces the environment the app was developed against instead of pulling newer
majors (pandas 3.x, Pillow 12.x, …). **Upgrading is deliberate:** delete a line from
`constraint-dependencies` and re-run `uv lock`. One post-migration addition: `pyarrow` (the
Parquet engine for the Lever C base) was added loose and **is not** in `constraint-dependencies` —
`uv.lock` records the resolved version (24.0.0 at add time). The project is `package = false`
(an app, not a library, so uv manages the env without trying to build it).

**`requirements.txt` has been removed** (Phase 4) — `pyproject.toml` + `uv.lock` are the single
source of truth. If a tool or host ever needs a `requirements.txt`, generate one on demand with
`uv export --format requirements-txt --no-hashes`; never hand-maintain one alongside the lockfile
(they would drift). Rolling back to the old pip flow, if ever needed, is via git history.

**Windows gotchas (this machine):**
- `pip.exe` is blocked by an Application Control policy — standardize on uv. The reference freeze
  (`requirements.lock.txt`, git-ignored throwaway) was recovered from
  `.venv/Lib/site-packages/*.dist-info` because pip and the old venv were both unusable.
- uv installs a *managed* CPython 3.13 (only 3.12 was present globally). A first
  `uv venv --python 3.13` once errored mid-download on uv's internal "minor version link"
  bookkeeping; pointing uv at the concrete interpreter path — or re-running once the download
  settled — fixes it.
- The binary deps (`pandas`, `numpy`, `matplotlib`, `pyreadstat`, `Pillow`) have 3.13 Windows
  wheels — uv pulls the same PyPI wheels the app already used.

`.venv/` stays git-ignored; `uv.lock` and `.python-version` are committed.

## Done: visualization expansion (Visualize workbench + map-as-filter)

**All 5 tiers / 16 phases built** on the `visualization_expansion` branch (2026-07-09), verified by
Phase 14's cross-cutting QA (see below). Governed by two docs: **`VISUALIZATION_EXPANSION.md`**
(design/scope authority — the why, the verified data facts, the risks) and
**`VISUALIZATION_EXPANSION_PROMPTS.md`** (the phased build order, Phases 0–15, all marked done).

**What shipped:** a new **Visualize** tab (`/visualize` — see Routes) beside Statistics · Compare ·
Filter, with a blank-canvas builder dispatching to **six chart types**: pie, treemap (two-column
nested), waterfall (year-over-year over `sentyear`, Chart.js floating bars), choropleth
(county/judicial-district/region grain toggle, small-N hatch texture), scatter/bubble (aggregated
lattice, never raw rows), and a correlation matrix (user-picked 2–8 numeric columns, Pearson via
`DataFrame.corr`, computed fresh — never disk-cached — with near-mechanical `|r| ≥ 0.90` pairs
flagged, not hidden). A reusable "Other"-cutoff slider (`partials/other_cutoff_slider.html` +
`static/js/otherbucket.js`) backs pie, treemap, and (retrofit) the Explore distribution bar.
`Data.get_column_info` gained `mode`/`mode_extra` (the tie badge) and `Data.aggregate_by_group` is
the one shared `(group, measure, aggregate)` helper every chart reads through.

**Geography (`geo.py`, new):** a vendored MN-counties TopoJSON (`static/geo/mn-counties-topo.json`)
plus a county-name alias table reconcile the dataset's 87 county spellings to map features, with a
startup assertion (`geo.assert_county_coverage`, run from `app.py` at import time, right after the
base-DataFrame preload succeeds) that fails loudly on any unmatched or colliding county.
District/region shapes are **dissolved at runtime** from the county geometry via a crosswalk
`cache._county_crosswalk()` derives straight from the data (`groupby('county')[...].first()`) — no
separate geometry files.

**Map-as-filter (the differentiator, Phase 11):** clicking a shape on the Visualize choropleth, or
the Filter view's map input (`partials/filter_map.html`, beside/below the existing categorical or
numeric control), applies the exact filter typing it would. Neither path is a bespoke route — both
POST the pre-existing `/explore/filter/<column>` (`explore_filter_column`), so the resulting history
entry, chip, and `cache/data/` directory are byte-identical to hand-typing the filter. The
choropleth's companion table also carries a per-row "Keep only" button as the keyboard/no-JS twin
of a map click. `test_map_filter_equivalence.py` pins this for every shape at every grain, plus the
OR-multiselect path and the `safe_return_target` open-redirect guard on the `next` field.

**Verified (Phase 14 QA, 2026-07-09):** both guardrail tests green (`test_base_immutability.py`,
extended over `aggregate_by_group`/the crosswalk/`.corr()`; the new
`test_map_filter_equivalence.py`); an 11-combo spot-check (6 chart types × 3 grains × 4 aggregates)
matched Explore/Compare exactly; all 87 counties join; 52 low-N counties hatch under a deep filter;
`mode`'s tie badge fires correctly (`dsentenc`, 3 modes, the only shipped multimodal `float64`
column); responsive at 375/768/1280 in both themes; zero external/failed network requests
(`VERSIONS.md` matches disk: htmx 2.0.10, Chart.js 4.5.1, chartjs-chart-treemap 3.1.0,
chartjs-chart-geo 4.3.6 — **no `patternomaly`**, the small-N hatch is a hand-rolled `CanvasPattern`
in `static/js/visualize.js`).

**One open gap** (§10 criterion 7 in `VISUALIZATION_EXPANSION.md`): **no shipped lesson uses a
Visualize chart** — `app.build_lesson_data` only supports `info`/`table` focus views. Closing it
needs a new chart focus-view plus an authored lesson step; left as deliberate follow-up rather than
folded into the QA/docs passes (Phases 14–15).

## Done: base DataFrame optimization (runtime memory/latency)

**All four levers built** on the `base-df-optimization` branch (Phases 0–4 of
`OPTIMIZATION_PROMPTS.md`). Governed by two docs: **`BASE_DATAFRAME_OPTIMIZATION.md`** (design/scope
authority — the why) and **`OPTIMIZATION_PROMPTS.md`** (the phased build order — Phases 0–4). Every
phase is verified byte-identical against the Phase 0 golden `.bin` snapshot (see the immutability
guardrail `test_base_immutability.py` + the golden dir outside the tree).

**The runtime cost it targeted:** there was **no shared in-memory dataset**. Every request that
*missed* the disk cache rebuilt the base from scratch — `_execute` → `Data.load` →
`pd.read_csv('cache/raw.csv')` — a **242 MB text parse into a ~1.85 GB DataFrame** (294,467 rows ×
176 cols; the 116 string/`object` columns were the memory hogs). Each gunicorn worker did this
independently (`deploy/setup.sh` defaults to `WORKERS=3`), so cold RAM ≈ `WORKERS × ~1.85 GB`.
Cache *hits* are cheap (they just `pickle.load` `.bin` files and never touch the base).

**The four independently-shippable levers:** (A) **[done]** cast the 116 `object` columns to
`category` in `Data.load` — strings only, floats stay `float64` — measured **~8×** (1.72 GiB →
0.22 GiB), better than the 2.5–3.5× estimate; (B) **[done]** `cache._base_df()` memoizes the base
(a module-level singleton with a debug-only shape/identity tripwire) so cache misses stop
re-parsing — base load 4.2 s → ~1 µs on reuse, exactly one base-sized frame alive per process;
(C) **[done]** `cache/raw.parquet` typed columnar base (`Data.load` `.parquet` branch +
`save_parquet`; `DATAFILE` prefers it, CSV stays a fallback) — 242 MB → **~23 MB** on disk, cold
load 4.2 s → **~0.25 s**; (D) **[done]** gunicorn `--preload` (in `deploy/setup.sh`'s `ExecStart`)
+ an **import-time base warm in `app.py`** so the base loads once in the gunicorn master before
fork and workers inherit it copy-on-write instead of `×WORKERS`. CoW holds because Lever A made the
heavy columns numpy code-arrays: **~79% of the ~220 MiB base is CoW-shareable numpy** (higher in
warm-cache steady state, since workers rarely materialize category labels); 3 independent
(non-preload) copies measured ~2.16 GB total, which `--preload` collapses toward one shared base.
The import-time warm is best-effort (a missing datafile logs and falls back to per-request lazy
load); dropping `--preload` reverts cleanly to per-worker load-once. Result: deploy sizing drops
from 4 vCPU / 8 GB toward a comfortable 1 vCPU / 2 GB for a half-dozen users. The true 3-worker
shared RSS/PSS is a Linux-target measurement (Windows has no `fork`) — recipe in `deploy/README.md`.

**Two hard constraints** (both in the prompts doc's Global constraints): results and cache keys
must stay identical (so **numeric columns must stay `float64`** — the three checks at
[data.py:78](data.py:78)/[246](data.py:246)/[329](data.py:329) depend on it; only strings get
re-typed), and the base DataFrame is **never mutated in place** today (no `inplace=`/`.drop`/
`.fillna`/`astype` on `self.df`) — the sharing levers rest on keeping it that way.

## Done: request-path optimization (per-request work on top of the base)

**All six phases (0–5) built** on the `optimizations-minor` branch (off `main`, which includes the
merged visualization-expansion PR #4; landed 2026-07-09). Governed by one self-contained doc,
**`REQUEST_PATH_OPTIMIZATION_PROMPTS.md`** (rationale + phased build order + the per-phase
resolutions folded in). This is the **sequel** to the base DataFrame optimization: Levers A–D made
the *base* cheap to hold and share; this pass removed everything redundant that ran *on top of the
base, per request* — the repeated history replays, the O(n·k) stat loop, the nested-filter
crosstab, and the repeat pickle reads. Measured before/after for every flow is in
`perf/BASELINE.md`; headline: filter-then-browse-8-columns 535–555 ms → **135–156 ms** (9 replays →
1), Compare crosstab 207–216 ms → **~40 ms**, Visualize choropleth+scatter ~1.6 s → **~90–104 ms**,
cold column view ~109 ms → **~40–49 ms**.

**What each phase landed:**
- **P0 — Baseline & harness**: `perf/` (env-gated `@timed` shim, four-flow benchmark, before-numbers
  in `perf/BASELINE.md`). The shim is a no-op unless `PROFILE_REQUESTS=1`.
- **P1 — Cache-neutral I/O reclamation**: per-request `account.retrieve` memo in `flask.g`
  (writers invalidate), `build_column_browser` memo (keyed on the column/excluded tuples),
  `lessons.list_modules` memo on a name+mtime+size dir signature (authored edits still show up).
- **P2 — Sidebar badge without a replay**: the filter-apply route stamps its remaining-cases count
  onto the active history entry (`account.set_history_count`); `inject_globals` reads the stamp
  (base entry → memoized `dataset_total()`; unstamped → `get_data` fallback).
- **P3 — Filtered-slice LRU (the structural win)**: `cache._filtered_cache`, bounded at 8 slices,
  keyed on the canonical history-token tuple; `_execute` serves warm slices, `_replay_history` is
  the timed miss path. Collapsed flow (a) from 9 replays to 1 and the cold double-replay to 1;
  `get_aggregate`/`build_choropleth`/`get_moc_options` ride it too. `test_base_immutability.py`
  extended with the slice-served-and-immutable case.
- **P4 — Vectorize the crosstab**: `get_table` = one `groupby([x, y], observed=True)` count pass +
  per-group Series reductions for the measure — deliberately **not** `groupby.agg`, whose Cython
  sum order flipped one cell on a rounding boundary ('33.007' vs '33.008') during verification.
  Cell-for-cell identical output; never disk-cached, so no `.bin` exposure. ~8× on Compare, ~90×
  on the scatter lattice (1.53 s → 17 ms); `SCATTER_MAX_CELLS` is now a readability cap, not a
  perf cap (left unchanged — product call, logged in Appendix B).
- **P5 — Vectorize per-column stats (the cache-bytes linchpin)**: `num_each` = one `value_counts`
  pass, **order-preserving swap (option (a) of the gate)** — the pickled dict keeps `col.unique()`'s
  own key objects/order, Python-int values, NaN key pinned to 0, so `<col>.bin` bytes are unchanged
  and no cache or golden re-warm was needed. Verified by a before/after oracle over **all 170
  non-excluded columns × 2 history states**: 372 files (raw `.bin` pickles + formatted display
  output across all 5 sortings for 16 sample columns) byte-identical, plus an old-vs-new
  equivalence check on the all-distinct `Unnamed: 0` shape (unreachable in routes — no codebook
  entry — and infeasible under the old loop). `get_column_info` over all columns: 22.9 s → 0.96 s
  (23.8×); worst column `moc` (11,475 uniques): 4.22 s → 9 ms (~446×).

**Inherited hard constraints — all held:** cache byte-identity (P1–P4 cache-neutral by design; P5
verified byte-identical via the order-preserving swap), `float64` stays `float64`, and neither the
base nor a cached filtered slice is ever mutated in place (`test_base_immutability.py`, extended in
P3, and `test_map_filter_equivalence.py` both green after every phase). Appendix B of the prompts
doc holds the found-but-unscheduled leads (`get_moc_options`'s per-option sweep, `filter_or_same` →
`isin`, the dashboard N+1, deriving `get_column_info`'s unique-count/mode from the value counts,
raising `SCATTER_MAX_CELLS`).

## Git remotes

- `github` → `github.com/RobotsLoveWater/Crime_dot_Education.git` (public) — the **canonical
  remote**; push here. Auth is via the `gh` CLI over HTTPS (no SSH key is configured on this
  machine — the `git@github.com:` SSH URL will fail).
