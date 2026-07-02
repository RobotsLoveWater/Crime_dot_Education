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
- "Revert" (`/load`) just truncates the history list back to a shorter prefix.
- Cache files inside a history directory: `_data.bin` (dataset-level summary),
  `<column>.bin` (per-column stats), `_moc.bin` (offense-code option counts).
- The cache is **content-addressed and safe to delete** — it regenerates on demand (slowly).

## Data flow / bootstrap (IMPORTANT for setup)

The runtime does **not** read `dataset.sav` directly. It reads `cache/raw.csv`.

```
dataset.sav (SPSS, ~141 MB, git-ignored)
    │  one-time precompute:  python cache.py   (its __main__ block)
    ▼
cache/raw.csv  (~242 MB, git-ignored)   ← DATAFILE that _execute() loads at runtime
    │  optional: also pre-caches per-column stats into cache/data/
    ▼
runtime: cache._execute() loads cache/raw.csv, replays user history filters
```

To stand the app up on a fresh machine you must obtain `dataset.sav` (not in git), then run
`python cache.py` and answer `y` to both prompts to generate `cache/raw.csv` and warm the cache.
`DATAFILE = 'cache/raw.csv'` and `DATAPATH = 'cache/data/'` are defined at the top of `cache.py`.

## Running it

No `app.run()` exists in `app.py`. Launch via the Flask CLI (Python 3.13, see `requirements.txt`):

```
pip install -r requirements.txt
flask --app app run          # add --debug for reload
```

## Module map

| File | Role |
|------|------|
| `app.py` | Flask routes + the `is_logged_in` / `not_logged_in` helpers. Thin controller layer. |
| `data.py` | `Data` class — the actual pandas analysis engine: filtering, cross-tabs, per-column stats, MOC filtering. Also `format_column_info()` (sorting for display). |
| `cache.py` | The history→cache→dataframe machinery: `get_data`, `get_moc_options`, `_execute`. `__main__` builds `cache/raw.csv` from `dataset.sav`. (Header comment calls it `precache.py`.) |
| `account.py` | User accounts as pickles under `user/`. Create/retrieve/history-add/history-revert. |
| `make_history.py` | Builds history entry dicts (`action` list + human-readable `desc`). |
| `moc.py` | `MnOffenseCodes.CODES` — a huge (~1800-line) nested dict decoding the Minnesota Offense Code. Pure data + structure. |
| `util.py` | `ordinal()` and bcrypt `get_hashed_password` / `check_password`. (Header comment is wrong — says `make_history.py`.) |
| `codebook.xml` | Maps dataset column names → human descriptions (161 entries). Loaded by `Data.__init__`. |
| `settings.xml` | seaborn palette/style (`deep` / `darkgrid`). Not heavily used yet. |
| `test.py` | Ad-hoc scratch script for the history→cache-key encoding. Not a real test suite. |
| `templates/` | Jinja2. `layout.html` is the base (nav + history table + error block); others extend it. |
| `static/css/style.css` | Styling; theme via CSS variables (`--color-accent`, etc.). |

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

- `/`, `/landing` — home dashboard (shows history table via `layout.html`).
- `/new`, `/login`, `/logout` — account/session. Session keys: `userid` (`classcode/username`), plus `username`/`classcode`.
- `/info/`, `/info/<column>/<sorting>` — descriptive stats per column. `sorting` ∈ `Data.VALID_SORTING`.
- `/table`, `/table/<dependant>/<x_axis>/<y_axis>` — cross-tab (N, mean, median, std). `dependant == '#'` means count only.
- `/filter/` menu; `/filter/boolean/<column>/<sorting>` — comparison filters (single or OR-multiple); `/filter/moc/...` — offense-code drill-down.
- `/load` — revert/clear history. `/download`, `/save`, `/other`, `/settings`, `/admin`, `/lesson*` — **stubs** returning "WIP, Feature Not Implemented".

Every data route follows the pattern: `if is_logged_in(): ... else: return not_logged_in()`.

## Storage layout (all git-ignored — see `.gitignore`)

- `dataset.sav` — raw SPSS source (~141 MB). Not in git.
- `cache/raw.csv` — CSV the runtime actually loads (~242 MB, exceeds GitHub's 100 MB limit). Not in git.
- `cache/data/<history-path>/…bin` — pickled computed results.
- `user/<classcode>/<username>.pickle` — **user accounts, including bcrypt password hashes.**
  Default classcode when none given: `unmanaged`. **Never commit this dir** (private user data).

## Conventions & gotchas

- **X/Y axes are intentionally flipped** in `/table` form handling (`app.py` comments: "flipped due to display issues"). Don't "fix" without checking the template.
- `float64` columns coerce filter values to float so `16 == 16.0`. Numeric-only comparisons (`gt/ge/lt/le`) are validated against `float()` in the boolean-filter route.
- Rounding idiom throughout `data.py`: `round(x * 10**precision) / 10**precision`.
- Cache-path bug guard: trailing `/` is stripped in `get_data` before appending `_data.bin`.
- Header comments in `cache.py` and `util.py` are copy-paste-wrong (say `precache.py` / `make_history.py`). Filenames in the table above are authoritative.
- Line-ending: repo is on Windows; git may warn about LF→CRLF. Harmless.

## Known issues / incomplete (don't assume these work)

- **Login does not verify the password.** `util.check_password` exists but is never called;
  `/login` only checks that the username exists, then creates a session. Treat auth as insecure.
- **Hardcoded Flask `secret_key`** in `app.py` (marked "DEVELOPMENT ONLY"). The repo is a
  **public** GitHub repo — do not treat this key as secret; rotate + move to env var if productionizing.
- `account.create` returns `retrieve(username)` on an existing user (should be `userid`) — latent bug.
- `/new` sets `session['userid']` but not `session['username']`/`session['classcode']`.
- Templates reference `hero_image_url` and `current_year`, but no route passes them → they render empty.
- Stubbed/`pass`-only: `Data.filter_and`, `filter_or_diff` (partial), `make_history.filter_or_diff`, `filter_and`, `moc_or`; the `d` and `a` action codes are not handled by `_execute` (raise `ValueError`).

## Planned: Learning Modules framework (next phase — NOT yet built)

Design for the upcoming "learning modules" / guided-lessons feature. The UI already
anticipates it (`index.html` advertises "Guided Lessons" and a hardcoded "Interactive
Lessons: 0"; the `/lesson*` routes are stubs). **None of this is implemented yet — it is a
plan.** Detailed, phased implementation prompts live in `LEARNING_MODULES_PROMPTS.md`; work
through them one phase at a time.

**Core idea — reuse the history/cache substrate.** A lesson is an ordered sequence of
*steps*; each step optionally carries a **data state** expressed as history tokens (the same
`f.col.op.val` encoding `cache.history_item_to_text` already produces). Because every
statistic in the app is a deterministic function of a history, a step can (a) reconstruct
exactly the filtered dataset the lesson wants via the existing `_execute`/cache path, and
(b) **auto-grade numeric questions by computing the answer live** (`Data.get_column_info`,
`Data.get_table`) rather than hardcoding it — so answers stay correct if the data changes.
This shared data-state abstraction is what "links the statistical analysis" to lesson content.

**Module/step data model (file-based, no DB — matches the rest of the app):**
- `lessons/<module_id>.json` — a module: `id`, `title`, `description`, `author` (classcode),
  `objectives`, and an ordered `steps` list.
- Step types: `read` (markdown only), `explore` (sets a data `state` + deep-links into
  `/info` or `/table`), `question` (`choice` / `numeric` / `free` answers; `numeric` graded
  against live computation on the step's state), `checkpoint` (assert the user's current state
  matches an expected one).
- Loader: a new `lessons.py` that lists/parses `lessons/` (mirrors how `account.py` lists
  `user/`). `lessons/` is author-supplied content and **safe to commit** (unlike `user/`).

**Progress & sandboxing (key design decisions):**
- Store progress on the user pickle under a new **`progress`** key
  (`{module_id: {step, answers, completed}}`), defaulting to `{}` when the key is absent —
  the same backwards-compatible pattern as `saved`.
- **Lessons are strictly sandboxed (decided).** A lesson's data state must **never** be
  copied into, merged with, or mutate the student's own exploration `history` — there is no
  carry-over. Render lesson states via an **override history** instead of touching the account.
  Note:
  `cache.get_data` already has a half-wired `history_override` parameter that is currently a
  **no-op** (`full_history + history_override` is computed but never assigned, cache.py:54);
  completing it — and adding the same override to `_execute` — is the intended hook for
  lesson-scoped state.

**Routes to flesh out (currently stubs in `app.py`):** `/lesson` (catalog),
`/lesson/<module_id>` (overview), `/lesson/<module_id>/<step>` (render + POST to answer/
advance). The existing `/lesson/get_started/<page>` stub is also buggy — its view function
`lesson_guide()` omits the `page` argument. New templates extend `layout.html`:
`lesson_catalog.html`, `lesson.html`, `lesson_step.html`.

**Roles/authoring:** educators author modules as files scoped to their `classcode`; the stub
`/admin` route is the intended authoring surface. There is currently **no role system** (all
accounts are equal) — adding an educator flag to the account pickle is a prerequisite for
authoring/permissions.

## Git remotes

- `origin` → GitLab (`gitlab.com/sidallen-scsu/cde.git`).
- `github` → `github.com/RobotsLoveWater/Crime_dot_Education.git` (public). Auth is via the `gh`
  CLI over HTTPS (no SSH key is configured on this machine — the `git@github.com:` SSH URL will fail).
