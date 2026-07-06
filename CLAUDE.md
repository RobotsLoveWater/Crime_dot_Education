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

The runtime does **not** read `dataset.sav` directly. It reads `cache/raw.csv`.

```
dataset.sav (SPSS, ~141 MB, git-ignored)
    │  one-time precompute:  uv run python cache.py   (its __main__ block)
    ▼
cache/raw.csv  (~242 MB, git-ignored)   ← DATAFILE that _execute() loads at runtime
    │  optional: also pre-caches per-column stats into cache/data/
    ▼
runtime: cache._execute() loads cache/raw.csv, replays user history filters
```

To stand the app up on a fresh machine you must obtain `dataset.sav` (not in git), then run
`uv run python cache.py` and answer `y` to both prompts to generate `cache/raw.csv` and warm the cache.
`DATAFILE = 'cache/raw.csv'` and `DATAPATH = 'cache/data/'` are defined at the top of `cache.py`.

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
| `app.py` | Flask routes + the `is_logged_in` / `not_logged_in` helpers. Thin controller layer. |
| `data.py` | `Data` class — the actual pandas analysis engine: filtering, cross-tabs, per-column stats, MOC filtering. Also `format_column_info()` (sorting for display) and `GROUP_ORDER` (column-browser group display order). `Data()` with no preload is cheap — it only parses `codebook.xml` (app.py keeps one as `CODEBOOK` for metadata). |
| `cache.py` | The history→cache→dataframe machinery: `get_data`, `get_moc_options`, `_execute`. `__main__` builds `cache/raw.csv` from `dataset.sav`. (Header comment calls it `precache.py`.) |
| `account.py` | User accounts as pickles under `user/`. Create/retrieve/history-add/revert, plus **learning-module `progress`/`state` helpers** (`get_progress`, `set_progress`, `set_lesson_state`) and the `is_educator` role flag. |
| `lessons.py` | Learning-modules loader/validator: `list_modules`, `get_module`, `validate`, `save_module` over `lessons/*.json`. Pure stdlib module (no Flask), mirrors `account.py`. |
| `make_history.py` | Builds history entry dicts (`action` list + human-readable `desc`). |
| `moc.py` | `MnOffenseCodes.CODES` — a huge (~1800-line) nested dict decoding the Minnesota Offense Code. Pure data + structure. |
| `util.py` | `ordinal()` and bcrypt `get_hashed_password` / `check_password`. (Header comment is wrong — says `make_history.py`.) |
| `codebook.xml` | Maps dataset column names → human descriptions; each entry also carries a `group` attribute placing the column in an explore column-browser category (display order in `Data.GROUP_ORDER`). Loaded by `Data.__init__` (descriptions → `self.codebook`, groups → `self.groups`). Some entry names don't match real dataset columns (see gotchas). |
| `settings.xml` | seaborn palette/style (`deep` / `darkgrid`). Not heavily used yet. |
| `test.py` | Ad-hoc scratch script for the history→cache-key encoding. Not a real test suite. |
| `templates/` | Jinja2. `layout.html` is the base — the Phase 1 **workbench shell**: top bar (nav + theme toggle + identity), data-state **sidebar** (count badge, filter chips, Clear data; `{% block sidebar_extra %}` hosts view-specific modules), toast region, confirm `<dialog>`, htmx progress bar; others extend it via `{% block body %}`. `explore.html` + `templates/partials/` (`column_browser.html`, `explore_landing.html`, `explore_column.html`) are the Phase 2 statistics workbench — partials render standalone on htmx fragment requests (`fragment=True` adds the `<title>` htmx uses to retitle the page) and are `{% include %}`d on full loads. `compare.html` + `partials/compare_builder.html`/`compare_results.html` are the Phase 3 crosstab workbench on the same pattern (replacing the deleted `perm_menu.html`/`perm.html`). `filter.html` + `partials/filter_landing.html`/`filter_column.html`/`filter_preview.html`/`filter_zero.html` are the Phase 4 **Filter workbench** (same fragment pattern; the sidebar reuses the now-parametrized `column_browser.html` pointed at the filter routes), and `moc1.html`/`moc.html` are the rebuilt offense-code chooser + 5-slot stepper. The Phase 4 rewrite deleted `filter_boolean.html`/`filter_boolean_menu.html`. `error.html` renders the styled 404/500 handlers. Learning-modules views (Phase 5 restyled + docked): `lesson_catalog.html`, `lesson.html`, `lesson_step.html` (extends `layout.html`, fills the new `{% block dock %}`; the main area `{% include %}`s `partials/lesson_data.html` — the read-only sandbox data view), `admin.html`, `admin_edit.html`. (`info.html`/`info_menu.html` were deleted in Phase 2.) |
| `lessons/` | Authored learning-module content (`<id>.json`) + `README.md` schema. **Safe to commit** (unlike `user/`). |
| `LEARNING_MODULES_PROMPTS.md` | Phased build plan for the learning-modules feature. All phases are now implemented; the doc still reads as forward-looking. |
| `UI_OVERHAUL_PROMPTS.md` | Phased build plan for the UI/UX overhaul (sidebar workbench redesign). **Phases 0 (hygiene/tokens/vendored assets), 1 (workbench shell), 2 (explore workbench), 3 (compare workbench + CSV export), 4 (filter workbench: live previews, searchable values, MOC stepper), 5 (docked lessons + checkpoint wiring), 6 (auth pages/landing/logged-in home), and 7 (responsive/a11y/dark QA + `style.css` removal) are done** — the overhaul is feature-complete; see "In progress: UI/UX overhaul" below. |
| `STYLEGUIDE.md` | **Design authority** for all UI work: tokens (light+dark), typography, layout, components, htmx conventions, a11y checklist. Read it before touching `templates/` or `static/`. |
| `static/css/tokens.css`, `static/css/base.css` | Phase 0 token system: all design tokens (both themes, exact `STYLEGUIDE.md` tables — plus `--overlay` for drawer/dialog backdrops) and reset/typography/focus/reduced-motion. Loaded first; theme switches via `data-theme` on `<html>` (FOUC-guard inline script in `layout.html` — which also sets a `js` class gating JS-only CSS — toggle in `static/js/theme.js`, persisted to `localStorage.theme`, fires a `themechange` event). |
| `static/css/components.css`, `static/css/views.css` | Phase 1 shell styles per the styleguide's file organization: `components.css` = buttons/badges/chips/toasts/dialog/alerts/empty-state/loading; `views.css` = top bar, workbench grid, sidebar + tablet drawer, breakpoints, **phone shell (data-state bar, bottom nav, sticky-first-column tables, bottom-sheet dock — Phase 7)**. The retired `style.css` is gone (Phase 7); its still-live base rules (`.container`, bare `h1`/`h2`/`h3`/`p`) moved here + into `base.css`. |
| `static/js/app.js` | Phase 1 shell behaviors (vanilla, no build step): toast auto-dismiss + `HX-Trigger`/`htmx:responseError` toast paths, `[data-confirm]` dialog interception, sidebar drawer with focus trap (Phase 7: opened by **any** `[aria-controls="sidebar"]` trigger — the tablet ☰ or the phone data-state bar — focus returns to the opener), htmx-bound global progress bar, `[data-loading]` submit feedback ("Computing statistics…"). Phase 3 added the **searchable picker**: a `[data-picker]` wrapper around a native `<select>` gets a filtering combobox (arrows/Enter/Esc); the hidden select keeps carrying the form value (and is the no-JS fallback). |
| `static/js/compare.js` | Phase 3 compare behaviors: stat toggle (sets `data-stat` on the crosstab — pure CSS show/hide, since all four stats ship in the markup — updates `aria-pressed`, and re-shades the `.heat-N` heatmap from each cell's `data-heat-<stat>` attributes) and the grouped-bar companion chart (theme-aware, ≤8×8 tables only, re-rendered on `themechange` and history restores). **The chart renders on `htmx:afterSettle` (not `afterSwap`) + a next-frame `chart.resize()`** — the swapped DOM/scroll must settle before Chart.js measures the container, or it intermittently paints blank until a manual refresh; don't move it back to `afterSwap`. Loaded (with `chart.umd.min.js`) only via `compare.html`'s `{% block head %}`. |
| `static/js/explore.js` | Phase 2 explore behaviors: distribution chart (Chart.js; colors read from CSS tokens at render time, re-rendered on `themechange` and history restores; horizontal bars when labels run long), column-browser search, value-table search + "show more" pagination, active-column `aria-current` sync, tablet-drawer auto-close on column pick. **The chart renders on `htmx:afterSettle` (not `afterSwap`) + a next-frame `chart.resize()`** (interactive bits — table/active-column — still run on `afterSwap`): Chart.js must measure the container after the swap/`show:window:top` scroll settles, or it intermittently paints blank until a refresh; don't move it back to `afterSwap`. Loaded (with `chart.umd.min.js`) only via `explore.html`'s `{% block head %}`. |
| `static/js/filter.js` | Phase 4 filter-workbench behaviors: column-browser search + active-column `aria-current` sync (against `#filter-view`), categorical value-list search + "Select shown"/"Clear" bulk actions, and MOC option/category table search. The live "~N cases match" preview is pure htmx (`hx-get` on the preview element) and needs no JS here — all of this is progressive enhancement over plain forms/links. Loaded via `filter.html`/`moc.html`/`moc1.html`'s `{% block head %}`. |
| `static/js/vendor/` | Vendored, pinned htmx 2.0.10 + Chart.js 4.5.1 (`VERSIONS.md` is the manifest; never hand-edit). Inter variable font at `static/fonts/InterVariable.woff2`. htmx is loaded by `layout.html`; Chart.js only by `explore.html`. |

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
  an "Undo last filter" CTA via `revert(len(history)-1)`).
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
- `/load` — clear history (revert to the base full-dataset entry); no longer linked from the
  nav (the sidebar's confirmed "Clear data" button hits `/revert/1` instead). `/revert/<n>` —
  revert the history to a prior entry (`account.history_revert`, truncating to `history[:n]`;
  `n` is the 1-based history position — the sidebar chips link here: clicking a chip reverts
  to that step, the last chip's `×` removes just that step). Filter apply, revert, and clear
  all `flash()` a message that `layout.html` renders as a toast.
- **Learning modules:** `/lesson` (catalog with per-module status + resume), `/lesson/<module_id>` (overview), `/lesson/<module_id>/<int:step>` (Phase 5 **docked lesson**: workbench shell + lesson dock; the main area shows the step's read-only sandbox data, the sidebar shows the "Lesson data" module; POST grades a `question`, `checkpoint` steps compare state), `/lesson/<module_id>/complete` (mark done). See "Learning Modules" below.
- **Authoring (educators only):** `/admin` (list your class's modules), `/admin/edit[/<module_id>]` (create/edit → writes validated JSON to `lessons/`). Guarded by `require_educator()`.
- `/guide` — static guide page (replaced the old buggy `/lesson/get_started` stub). `/save`, `/other`, `/settings` — still **stubs** returning "WIP, Feature Not Implemented" (`/download` was implemented in Phase 3, see above).

Every data route follows the pattern: `if is_logged_in(): ... else: return not_logged_in()`.
(`not_logged_in()` is htmx-aware: on an `HX-Request` it answers with an `HX-Redirect` header
so the client does a full-page redirect instead of swapping the login page into a fragment.)

Styled `404`/`500` handlers render `error.html` (via the never-raising `current_user()` helper).
The `inject_globals` context processor also computes `datastate` (current + total case count)
for the sidebar badge on every logged-in render — cheap when cached, but it means the redirect
after applying a *new* filter pays the history replay immediately rather than on the next data
view. `hx_toast()` sets the `HX-Trigger` header for htmx-response toasts (used from Phase 2 on).

## Storage layout (all git-ignored — see `.gitignore`)

- `dataset.sav` — raw SPSS source (~141 MB). Not in git.
- `cache/raw.csv` — CSV the runtime actually loads (~242 MB, exceeds GitHub's 100 MB limit). Not in git.
- `cache/data/<history-path>/…bin` — pickled computed results.
- `user/<classcode>/<username>.pickle` — **user accounts, including bcrypt password hashes.**
  Default classcode when none given: `unmanaged`. **Never commit this dir** (private user data).

## Conventions & gotchas

- **UI/styling changes follow `STYLEGUIDE.md`** — tokens only (no raw hex in components), no inline styles, both themes, no runtime CDN assets. Sequencing for the redesign is in `UI_OVERHAUL_PROMPTS.md`.
- **Crosstab X/Y orientation:** `data.get_table(d, x, y)` uses `x` values as row headers and `y` as column headers. The pre-overhaul form labeled these backwards ("flipped due to display issues"); since Phase 3 the flip is **contained in `explore_table`'s POST handler** (Rows → `x_axis`, Columns → `y_axis`, commented there). Don't rename `get_table`'s args or the `dependant/x_axis/y_axis` route args — legacy URLs and lesson deep links depend on them.
- `float64` columns coerce filter values to float so `16 == 16.0`. Numeric-only comparisons (`gt/ge/lt/le`) are validated against `float()` in the boolean-filter route.
- Rounding idiom throughout `data.py`: `round(x * 10**precision) / 10**precision`.
- Cache-path bug guard: trailing `/` is stripped in `get_data` before appending `_data.bin`.
- Header comments in `cache.py` and `util.py` are copy-paste-wrong (say `precache.py` / `make_history.py`). Filenames in the table above are authoritative.
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

- **Login does not verify the password.** `util.check_password` exists but is never called;
  `/login` only checks that the username exists, then creates a session. Treat auth as insecure.
- **Hardcoded Flask `secret_key`** in `app.py` (marked "DEVELOPMENT ONLY"). The repo is a
  **public** GitHub repo — do not treat this key as secret; rotate + move to env var if productionizing.
- **Account create/login existence checks — fixed.** `get_user_list` now returns bare usernames
  (it used to return `.pickle`-suffixed filenames, so `/new` never detected duplicates — it fell
  through to `create` and crashed — and `/login` rejected every existing user); and
  `account.create` now returns `retrieve(userid)` (was `retrieve(username)`) on the already-exists
  path. Login still does **not** verify the password (see above).
- ~~`/new` sets `session['userid']` but not `session['username']`/`session['classcode']`.~~
  **Fixed in Phase 6** — `/new` now sets all three (from the created account), matching `/login`.
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
`/new` session-keys issue. Password verification and the hardcoded `secret_key` stay **out of
scope** (separate branch — see the prompts doc's Appendix C).

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
  filename stem (enforced by `lessons.validate`; also blocks path traversal). Two shipped lessons,
  sequenced via `order`: `intro-explorer-basics.json` (a hands-on tour of the Explorer's tools,
  `order: 1`) then `intro-descriptive-stats.json` (`order: 2`).
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
(`account.EDUCATOR_CLASSCODE_PREFIX`) grants authoring rights. This is a convenience, **not a
security boundary** (the app has no real auth). Educators use `/admin` + `/admin/edit` to
create/edit modules scoped to their own `classcode`; `require_educator()` guards those routes
and `slugify()` sanitizes the module id before it reaches the filesystem.

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
`constraint-dependencies` and re-run `uv lock`. The project is `package = false` (an app, not a
library, so uv manages the env without trying to build it).

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

## Git remotes

- `github` → `github.com/RobotsLoveWater/Crime_dot_Education.git` (public) — the **canonical
  remote**; push here. Auth is via the `gh` CLI over HTTPS (no SSH key is configured on this
  machine — the `git@github.com:` SSH URL will fail).
- `origin` → GitLab (`gitlab.com/sidallen-scsu/cde.git`) — legacy mirror, not used for pushing.
