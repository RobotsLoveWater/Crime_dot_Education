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
  made of `read` / `explore` / `question` / `checkpoint` steps, run beside a live read-only view
  of the data they describe. `explore` steps reconstruct a specific filtered dataset; `question`
  steps are **auto-graded live** against the data (numeric answers computed from the current
  filter, choice answers checked server-side); `checkpoint` steps verify the lesson's data state.
  Per-student progress and completion are tracked.
- **Accounts, classes & enrollment.** One overloaded sign-up field: leave it blank to join the
  public group, enter a class **join code** to enroll as a student in that class, or use an `edu-`
  code to create an **educator** account. Join codes are validated by lookup, so students land in
  a real class (namespaced under its immutable id) rather than a stray directory.
- **Educator portal.** Educators create **classes** (each with a rotatable join code and roster),
  **assign and pace modules** (required / optional / hidden / scheduled with open & due dates),
  and read a **progress dashboard** with a "needs attention" triage, per-question miss rates,
  and per-student answer-context inspection. Plus a **gradebook CSV export** (imports cleanly
  into Canvas / Google Classroom / PowerSchool), computed answer keys, per-class retake/feedback
  and email-domain policies, roster management, and shareable data-state links.
- **Data export.** Cross-tabulation tables and the class gradebook download as CSV (UTF-8 with a
  BOM so Excel opens them cleanly).

## Architecture (at a glance)

- **Stack:** Flask 3 + Jinja2 templates; pandas / numpy for analysis; SPSS `.sav` read via
  `pyreadstat`.
- **No database.** User accounts are pickle files under `user/` (with per-student append-only
  attempt logs beside them); classes are JSON under `classes/`; computed results are a
  content-addressed disk cache under `cache/data/`. All of these are git-ignored.
- **History-driven state.** There is no live per-session dataframe. Each account stores an
  ordered **history** of filter operations; the app replays (or reads from cache) that history
  to rebuild the filtered dataframe on demand. Each filter serializes to a token (e.g.
  `f.moc1.eq.A`) that doubles as the cache directory key. Learning-module data states reuse this
  same encoding through a sandboxed override that never touches the student's own history.
- **Shared immutable base.** The full dataset loads **once per process** (from a typed Parquet
  base, string columns stored as pandas categoricals for ~8× less RAM) and is replayed against
  read-only — filters always produce new frames. In production, gunicorn `--preload` lets all
  workers share that one copy copy-on-write.
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

The runtime does **not** read the SPSS file directly — it loads a precomputed base datafile:
the typed columnar `cache/raw.parquet` (~23 MB, fast to parse) when present, falling back to
`cache/raw.csv` (~242 MB). The raw data files are large and are **not** committed to git, so
first-time setup is a one-time precompute:

3. Obtain `dataset.sav` (the SPSS source, ~141 MB) and place it in the project root.
4. Build the runtime base and warm the cache — this writes `cache/raw.csv`, then
   `cache/raw.parquet` from it, and pre-computes per-column stats into `cache/data/`:
   ```
   uv run python cache.py        # answer "y" to all three prompts
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

- **Authentication is verified but not fully hardened.** Login now checks the password
  (bcrypt via `util.check_password`) and the Flask `secret_key` reads from the `SECRET_KEY`
  environment variable — but there is no rate-limiting or account lockout, no HTTPS enforcement,
  and the `edu-` **educator role is self-selectable at sign-up** (a classroom-trust convenience,
  not a public-internet trust boundary). Harden further before any deployment with real data.
- **Charts are in the web UI** (Chart.js distributions and grouped-bar crosstab companions), but
  the CLI's Seaborn figure export has not been reintroduced (its dependencies remain).
- Some engine operations remain **stubbed** — AND / OR-across-different-columns filters (the `a`
  and `d` action codes) are not implemented.

## Team

Maintained by a team at **St. Cloud State University**:

- Dr. Lindsey Vigesaa
- Dr. Mary Clifford
- David Hudson
- Sidney Allen

With additional thanks to **Indigo Allen**.

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE). Note that this repository is public.
