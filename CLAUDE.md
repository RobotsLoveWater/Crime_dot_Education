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
| `account.py` | User accounts as pickles under `user/`. Create/retrieve/history-add/revert, plus **learning-module `progress`/`state` helpers** (`get_progress`, `set_progress`, `set_lesson_state`) and the `is_educator` role flag. |
| `lessons.py` | Learning-modules loader/validator: `list_modules`, `get_module`, `validate`, `save_module` over `lessons/*.json`. Pure stdlib module (no Flask), mirrors `account.py`. |
| `make_history.py` | Builds history entry dicts (`action` list + human-readable `desc`). |
| `moc.py` | `MnOffenseCodes.CODES` — a huge (~1800-line) nested dict decoding the Minnesota Offense Code. Pure data + structure. |
| `util.py` | `ordinal()` and bcrypt `get_hashed_password` / `check_password`. (Header comment is wrong — says `make_history.py`.) |
| `codebook.xml` | Maps dataset column names → human descriptions (161 entries). Loaded by `Data.__init__`. |
| `settings.xml` | seaborn palette/style (`deep` / `darkgrid`). Not heavily used yet. |
| `test.py` | Ad-hoc scratch script for the history→cache-key encoding. Not a real test suite. |
| `templates/` | Jinja2. `layout.html` is the base (nav + history table + error block); others extend it. Learning-modules views: `lesson_catalog.html`, `lesson.html`, `lesson_step.html`, `admin.html`, `admin_edit.html`. |
| `lessons/` | Authored learning-module content (`<id>.json`) + `README.md` schema. **Safe to commit** (unlike `user/`). |
| `LEARNING_MODULES_PROMPTS.md` | Phased build plan for the learning-modules feature. All phases are now implemented; the doc still reads as forward-looking. |
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
- `/load` — revert/clear history.
- **Learning modules:** `/lesson` (catalog), `/lesson/<module_id>` (overview), `/lesson/<module_id>/<step>` (render; POST grades a `question`), `/lesson/<module_id>/complete` (mark done). See "Learning Modules" below.
- **Authoring (educators only):** `/admin` (list your class's modules), `/admin/edit[/<module_id>]` (create/edit → writes validated JSON to `lessons/`). Guarded by `require_educator()`.
- `/guide` — static guide page (replaced the old buggy `/lesson/get_started` stub). `/download`, `/save`, `/other`, `/settings` — still **stubs** returning "WIP, Feature Not Implemented".

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
- Stubbed/`pass`-only: `Data.filter_and`, `filter_or_diff` (partial), `make_history.filter_or_diff`, `filter_and`, `moc_or`; the `d` and `a` action codes are not handled by `_execute` (raise `ValueError`).
- **Learning-module `checkpoint` steps are not wired up.** `lessons.py` validates a step's `expect_state`, but `app.lesson_step` builds no context for `checkpoint` and `lesson_step.html` falls through to the generic "Interactive step — coming next phase" placeholder — nothing compares the student's active state to `expect_state`. The shipped `intro-descriptive-stats` lesson *ends* on such a step. (Note: `current_year` is now injected globally via a context processor and `index` passes `hero_image_url`, so those earlier template-variable gaps are resolved.)

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
- `lessons/<id>.json` — one module: `id`, `title`, `description`, `author` (classcode),
  `objectives`, ordered `steps`. Schema is documented in `lessons/README.md`. `id` must be
  `[a-z0-9-]` and match the filename stem (enforced by `lessons.validate`; also blocks path
  traversal). One shipped example: `lessons/intro-descriptive-stats.json`.
- `lessons.py` — loader/validator: `list_modules`, `get_module`, `validate`, `save_module`.

**Step types:** `read` (body only), `explore` (sets/deep-links a data `state`; `focus` links
into `/info/<column>` or `/table/...`), `question` (`numeric` graded live within `tolerance` /
`choice` graded by index / `free` stored ungraded), `checkpoint` (declared + validated but
**not yet functional** — see Known issues).

**Data-state override (the sandbox).** Lesson states are applied through the `history_override`
parameter on `cache.get_data` / `cache._execute`, appended on top of the base dataset (or the
student's history) **without ever mutating `user['history']`** — this completes the formerly
no-op `history_override` hook. `cache.history_text_to_item` decodes a token back into a history
`action` for this path. `app.build_explore` / `compute_expected` drive it with `session=None`
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

## Planned: uv migration (tooling — not yet done)

Plan to switch dependency/venv management from pip + `requirements.txt` + stdlib `venv` to
**[uv](https://docs.astral.sh/uv/)** (Astral's fast resolver/installer). **Docs-only so far — no
tooling has changed.** Phased implementation prompts live in `UV_MIGRATION_PROMPTS.md`; work
through them one phase at a time.

**Why:** faster installs, a committed lockfile for reproducible environments (useful for the
grant/handoff), and one tool for Python-version pinning + venv + dependency resolution.

**Current state (the starting point):** `requirements.txt` (mixed pinned/unpinned), a stdlib
`.venv/` (git-ignored), Python 3.13, `pip install -r requirements.txt`, `flask --app app run`,
and the one-time `python cache.py` data bootstrap. No `pyproject.toml`, no lockfile, no CI.

**Target (recommended):** a `pyproject.toml` declaring the deps, a committed `uv.lock`, and a
`.python-version` pinning 3.13 — `uv sync` to build the env, `uv run …` to launch. A
lighter-touch fallback keeps `requirements.txt` as the source of truth and only swaps the
commands (`uv venv` + `uv pip sync requirements.txt`).

**Touch points when it happens:** the "Running it" and "Data flow / bootstrap" sections here,
`README.md` (setup + run), `.gitignore` (commit `uv.lock` / `.python-version`; `.venv/` stays
ignored), and the fate of `requirements.txt` (drop it, or regenerate via `uv export` for tools
that still expect it).

**Gotchas:** the binary deps (`pandas`, `numpy`, `matplotlib`, `pyreadstat`, `Pillow`) already
have 3.13 wheels — the app runs today, and uv pulls the same PyPI wheels — but this repo is
Windows, so confirm a fresh `uv sync` resolves those wheels on Windows before retiring the old
flow. uv also defaults to a `.venv/` directory, so the existing git-ignore already covers it.

## Git remotes

- `origin` → GitLab (`gitlab.com/sidallen-scsu/cde.git`).
- `github` → `github.com/RobotsLoveWater/Crime_dot_Education.git` (public). Auth is via the `gh`
  CLI over HTTPS (no SSH key is configured on this machine — the `git@github.com:` SSH URL will fail).
