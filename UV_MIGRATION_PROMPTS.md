# uv Migration — Implementation Prompts

Sequenced, self-contained prompts for switching this project's Python tooling from
**pip + `requirements.txt` + stdlib `venv`** to **[uv](https://docs.astral.sh/uv/)** (Astral's
fast resolver/installer). Feed **one phase at a time** to a fresh Claude instance (or use as a
dev checklist). Each phase should end green before the next starts. Read `CLAUDE.md` →
"Planned: uv migration" first for the rationale and the current starting state.

## How to use this file

- Do the phases **in order** — later phases assume the earlier ones exist.
- Each prompt names the files to read, what to build, and how to know it's done. Keep the
  "Global constraints" below in scope for every phase.
- After each phase: build a fresh environment from scratch, run the app, commit, then move on.

## Global constraints (apply to every phase)

- **Don't break the running app.** `flask --app app run` and the one-time `python cache.py`
  data bootstrap must keep working (via their uv equivalents) at every phase boundary.
- **This repo is Windows.** Verify commands in PowerShell. `.venv/`, `cache/`, `user/`, and
  `dataset.sav` are git-ignored and must stay that way.
- **This is a tooling switch, not a dependency change.** Reproduce the *same* packages at the
  *same* versions, resolved by uv instead of pip. Any version bump is a separate, deliberate
  change — not part of this migration.
- **Pin Python 3.13** (the current runtime). uv can install and manage it (`uv python`).
- **Prefer committed reproducibility.** The end state has a committed lockfile so a fresh
  checkout resolves to identical versions.

---

## Phase 0 — Prep: install uv, snapshot the current environment, decide the target

**Goal:** know exactly what you're reproducing, and get uv onto the machine, before changing
anything.

**Read first:** `requirements.txt`, `CLAUDE.md` ("Running it", "Data flow / bootstrap"),
`.gitignore`.

**Build:**
- Install uv on Windows: `pip install uv` (or the standalone installer, or
  `winget install astral-sh.uv`). Confirm `uv --version`.
- Snapshot the *actual* working versions from the existing `.venv` as a throwaway reference:
  `pip freeze > requirements.lock.txt` (a reference only — not a committed artifact).
- Record the exact interpreter: `python --version` (expect 3.13.x).
- **Decide the target** and note it in `CLAUDE.md`'s planned section:
  - **A (recommended): pyproject + uv.lock** — `pyproject.toml` becomes the source of truth, with
    a committed `uv.lock`.
  - **B (lighter): requirements-based** — keep `requirements.txt`, only swap pip→uv commands.

**Acceptance:** `uv --version` works; a reference freeze of current versions exists; the target
approach is chosen and recorded.

**Don't:** create a `pyproject.toml` or delete `requirements.txt` yet.

---

## Phase 1 — Prove parity: build the venv with uv from the *existing* requirements.txt

**Goal:** a uv-created environment holding the same packages as today, with zero new metadata
files — fully reversible.

**Read first:** Phase 0 output.

**Build:**
- Rename/remove the old `.venv`, then create a fresh one: `uv venv --python 3.13`.
- Install into it: `uv pip sync requirements.txt` (or `uv pip install -r requirements.txt`).
- Exercise the app and bootstrap through uv:
  - `uv run flask --app app run`
  - `uv run python cache.py` (only if you actually need to rebuild the data cache; otherwise a
    quick import check is enough).
- Sanity-check imports of the binary deps: `pandas`, `numpy`, `matplotlib`, `pyreadstat`,
  `Pillow`.

**Acceptance:** the app starts and serves pages under `uv run`, from a uv-built venv, with the
same versions as the Phase 0 reference freeze. No new files committed.

**Don't:** introduce a pyproject or lockfile yet — this phase only proves uv reproduces today's env.

---

## Phase 2 — Adopt pyproject.toml + uv.lock (the actual switch)  · target A

**Goal:** make `pyproject.toml` the dependency source of truth and commit a lockfile.

**Read first:** `requirements.txt`, the Phase 0 reference freeze.

**Build:**
- Create a `pyproject.toml` (`uv init` or by hand) with `[project]` name/version,
  `requires-python = ">=3.13"`, and `dependencies = [...]` carried over from `requirements.txt`.
  Preserve the existing intentional hard pins (e.g. `Flask==3.0.0`, `bcrypt==4.1.2`); leave the
  currently-unpinned deps loose and let the lockfile pin exact versions.
- Add a `.python-version` file containing `3.13`.
- `uv lock`, then `uv sync` (regenerates `.venv` from the lockfile).
- Re-run the Phase 1 parity checks under the synced env.

**Acceptance:** `pyproject.toml`, `uv.lock`, and `.python-version` exist; `uv sync` on a clean
`.venv` yields a working app; versions match the reference freeze (or any diff is understood and
intentional).

**Don't:** delete `requirements.txt` in this phase — docs still reference it, and it's the
rollback path.

---

## Phase 3 — Update the docs and .gitignore

**Goal:** every setup/run instruction points at uv, and the right files are tracked vs ignored.

**Read first:** `README.md`, `CLAUDE.md` ("Running it", "Data flow / bootstrap"), `.gitignore`.

**Build:**
- `README.md` "Getting started": replace `pip install -r requirements.txt`,
  `flask --app app run`, and `python cache.py` with the uv flow (`uv sync`;
  `uv run flask --app app run`; `uv run python cache.py`).
- `CLAUDE.md`: update "Running it" and the bootstrap note; convert the "Planned: uv migration"
  section to reflect completion (or fold its essence into "Running it").
- `.gitignore`: make sure `uv.lock` and `.python-version` are **committed** (not ignored) and
  `.venv/` stays ignored.

**Acceptance:** a reader following only the README can set up and run the app with uv, with no
pip step anywhere.

**Don't:** leave stale pip instructions behind — grep for `pip install` and `requirements.txt`
across the repo docs.

---

## Phase 4 — Verify from scratch, then settle requirements.txt

**Goal:** confirm a cold setup works, and decide the fate of `requirements.txt`.

**Read first:** everything changed in Phases 2–3.

**Build:**
- Cold test: delete `.venv`, run `uv sync`, then `uv run flask --app app run` and confirm pages
  load. If the data cache is absent, confirm `uv run python cache.py` still builds `cache/raw.csv`.
- Decide on `requirements.txt`:
  - **Remove it** (pyproject + uv.lock are authoritative), **or**
  - **Keep it as a generated export** for tools/hosts that still expect it:
    `uv export --format requirements-txt --no-hashes > requirements.txt`, and note in the README
    that it is generated (never hand-edited).

**Acceptance:** a fresh clone → `uv sync` → running app, with no pip and no manual steps beyond
obtaining `dataset.sav`. `requirements.txt` is either gone or clearly marked generated.

**Don't:** keep a hand-maintained `requirements.txt` alongside the lockfile — that's two sources
of truth that will drift.

---

## Appendix A — pip → uv command cheatsheet

| Task | Old (pip / venv) | New (uv) |
|------|------------------|----------|
| Create venv | `python -m venv .venv` | `uv venv --python 3.13` |
| Install from requirements | `pip install -r requirements.txt` | `uv pip sync requirements.txt` |
| Add a dependency | edit file + `pip install X` | `uv add X` |
| Remove a dependency | edit file + `pip uninstall X` | `uv remove X` |
| Recreate env from lock | — | `uv sync` |
| Run a command in the env | activate, then `python …` | `uv run python …` |
| Run the app | `flask --app app run` | `uv run flask --app app run` |
| Build the data cache | `python cache.py` | `uv run python cache.py` |
| Export a requirements.txt | `pip freeze` | `uv export --format requirements-txt --no-hashes` |

## Appendix B — Rollback

The switch is reversible at any phase. The old flow (`python -m venv .venv` +
`pip install -r requirements.txt`) keeps working as long as `requirements.txt` exists — which is
why it stays until Phase 4. If uv causes trouble, delete `pyproject.toml` / `uv.lock` /
`.python-version`, recreate `.venv` with stdlib `venv`, and reinstall from `requirements.txt`.
