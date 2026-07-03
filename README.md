# MN Analysis of Sentencing Trends (MAST)

*Product name in the UI: **Minnesota Sentencing Explorer**, also styled **Crime[dot]Education**.*

A Flask web application for exploring **Minnesota felony sentencing data (2001–2019,
~294,000 sentenced counts)**. Social scientists, educators, and students log in, apply a chain
of filters to the dataset, and read descriptive statistics, cross-tabulations, and **guided
learning modules** built on top of the same data.

The project began as analysis for a senior thesis at St. Cloud State University and is now
developed toward a grant, with an emphasis on **education and public dissemination** of the data.

## Background

- **Data source:** the Minnesota Sentencing Commission — felony sentences from the
  sentencing-guidelines era onward. The working dataset used in development is restricted to
  **2001–2019**; broader historical coverage is a roadmap item (see [`ROADMAP.md`](ROADMAP.md)).
- **This repository is the web application.** A prior command-line tool (pandas + Seaborn
  graphing, tables, CSV export) predates it and is *not* included here — only fossils remain in
  the code (comments marked `cli-legacy`).

## Features

- **Chained filtering / exploration.** Build a dataset view by appending filters: compare any
  column with `eq, ne, gt, ge, lt, le` (so `ne` = *exclude by row value*), OR across several
  values of one column, or drill down through the **Minnesota Offense Code (MOC)** one digit at
  a time.
- **Descriptive statistics.** Per-column summaries — counts and percentage breakdown of each
  value, plus mean / median / std for numeric columns, in several sort orders.
- **Cross-tabulation tables.** N, mean, median, and std of a dependent variable across two
  grouping columns.
- **Guided learning modules.** Author-written lessons ("preset data views with commentary")
  made of `read` / `explore` / `question` steps. `explore` steps reconstruct a specific
  filtered dataset; `question` steps are **auto-graded live** against the data (numeric answers
  computed from the current filter, choice answers checked server-side). Per-student progress
  and completion are tracked.
- **Accounts & classes.** Users are scoped by an optional *classcode*; a classcode beginning
  `edu-` grants **educator** rights to author modules for that class.

## Architecture (at a glance)

- **Stack:** Flask 3 + Jinja2 templates; pandas / numpy for analysis; SPSS `.sav` read via
  `pyreadstat`.
- **No database.** User accounts are pickle files under `user/`; computed results are a
  content-addressed disk cache under `cache/data/`.
- **History-driven state.** There is no live per-session dataframe. Each account stores an
  ordered **history** of filter operations; the app replays (or reads from cache) that history
  to rebuild the filtered dataframe on demand. Each filter serializes to a token (e.g.
  `f.moc1.eq.A`) that doubles as the cache directory key. Learning-module data states reuse this
  same encoding through a sandboxed override that never touches the student's own history.
- **Deeper architectural notes for contributors live in [`CLAUDE.md`](CLAUDE.md).**

## Getting started

This project uses **[uv](https://docs.astral.sh/uv/)** for environment and dependency
management. The committed `pyproject.toml`, `uv.lock`, and `.python-version` (which pins
**Python 3.13**) let a fresh checkout reproduce the exact environment — with no manual
virtualenv and no `pip`.

1. **Install uv** if you don't have it (see the
   [install guide](https://docs.astral.sh/uv/getting-started/installation/)). On Windows:
   ```
   winget install astral-sh.uv
   ```
2. **Build the environment** — uv fetches Python 3.13 if needed and installs the locked
   dependencies into `.venv/`:
   ```
   uv sync
   ```

The runtime does **not** read the SPSS file directly — it loads `cache/raw.csv`. The raw data
files are large and are **not** committed to git, so first-time setup is a one-time precompute:

3. Obtain `dataset.sav` (the SPSS source, ~141 MB) and place it in the project root.
4. Build the runtime CSV and warm the cache — this writes `cache/raw.csv` (~242 MB) and
   pre-computes per-column stats into `cache/data/`:
   ```
   uv run python cache.py        # answer "y" to both prompts
   ```
5. Run the app:
   ```
   uv run flask --app app run    # add --debug for auto-reload
   ```

Every command runs inside uv's managed environment via `uv run …`, so there is no separate
"activate the virtualenv" step.

## Project status

This is an **active academic / research prototype**, not a hardened production service. Known
limitations (see [`ROADMAP.md`](ROADMAP.md) and [`CLAUDE.md`](CLAUDE.md) for the full list):

- **Authentication is not production-grade.** Login only checks that a username exists — it does
  *not* verify the password — and the Flask `secret_key` is a hardcoded development placeholder.
  Do not deploy as-is with real or sensitive user data.
- **No data export yet** (`/download` is a stub) and **no charts/figures** in the web UI (the
  CLI's Seaborn graphing has not been reintroduced, though the dependencies remain).
- **`checkpoint` lesson steps** are validated but not yet functional.

## Team

Maintained by a team at **St. Cloud State University**:

- Dr. Lindsey Vigesaa
- Dr. Mary Clifford
- David Hudson
- Sidney Allen

With additional thanks to **Indigo Allen**.

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE). Note that this repository is public.
