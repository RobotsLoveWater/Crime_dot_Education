# MN Analysis of Sentencing Trends — Roadmap

A tentative, status-aware roadmap for the **MN Analysis of Sentencing Trends (MAST)** project —
the *Minnesota Sentencing Explorer* web app. The project began as senior-thesis analysis and is
now developed toward a grant, with the goal of **making Minnesota Sentencing Commission felony
data accessible, understandable, and usable for teaching**.

This document supersedes the original roadmap: it re-frames the original goals against what is
now built, and lays out what remains. Nothing here is committed scope — it's a working plan.

## Vision

Disseminate Minnesota Sentencing Commission felony-sentencing data through a website that is:

- **Accessible** — the data is easy to reach and explore without specialist tooling.
- **Understandable** — findings are clearly presented and the data is contextualized.
- **Educational** — guided, commented "views" turn raw statistics into lessons.

## Where the original goals stand

| Original goal | Status | Notes |
|---|---|---|
| Findings clearly & concisely presented | Partial | Self-serve stats + guided lessons; no curated public "findings" views yet. |
| Data easily accessible | Partial | Web-accessible, but gated behind (insecure) login and with no export. |
| Filter by column, exclude by row value | **Done** | Core filter engine — `eq/ne/gt/ge/lt/le`, OR-same-column, MOC drill-down. |
| Date/time expressed sensibly & dynamically | Open | Year / sentence-length are plain numeric columns; no dynamic date handling. |
| Informative figures **and** tables | Tables only | Cross-tabs exist; **no visualization** in the web UI (a regression from the CLI). |
| Dynamically contextualize data | Partial | MOC decoder + codebook labels + lesson narrative. |
| Preset data views with team commentary | **Done (evolved)** | Became the **learning-modules** feature — graded and authorable. |

## Roadmap

Grouped by theme; ordering within each is roughly by priority.

### 1. Dissemination gaps (closest to the original goals)

- **Reintroduce figures / visualization.** The legacy CLI could graph with Seaborn; the web app
  cannot. `matplotlib`/`seaborn` are already dependencies and `settings.xml` still holds a
  palette — wire charts into the `/info` and `/table` views.
- **Data export.** Implement the stubbed `/download` so users can save a filtered view to CSV
  (reusing `Data.save`).
- **Sensible date/time handling.** Present year and sentence-length columns as dates / durations
  rather than bare floats.

### 2. Learning modules (continue the strongest thread)

- **Wire or retire `checkpoint` steps.** They are validated but inert today, and the sample
  lesson ends on one. Decide whether checkpoints become meaningful (which requires giving
  students agency over the lesson's data state) or are dropped.
- **Grow the lesson library** beyond the single intro module, with educator-facing authoring
  documentation.
- **Align the lesson docs.** `lessons/README.md` and `LEARNING_MODULES_PROMPTS.md` still read as
  forward-looking plans; update them to the shipped implementation (as `CLAUDE.md` now is).

### 3. Platform hardening (prerequisites for real deployment)

- **Real authentication.** Verify passwords (the bcrypt helper `util.check_password` exists but
  is never called) and move the Flask `secret_key` out of source into configuration.
- **Fix latent account bugs.** `account.create` returns the wrong value for an already-existing
  user; `/new` does not set all session keys.
- **Complete stubbed operations** if needed: AND / OR-across-different-columns filters (the `a`
  and `d` action codes), which are currently unimplemented.

### 4. Data coverage

- **Extend beyond 2001–2019** toward the full historical range of the Commission's data, and
  **reconcile the start year** — prior documents have cited both 1980 and 1981.

### 5. Deployment & delivery (grant)

- A hosting story that handles the large data file (the ~242 MB `cache/raw.csv` exceeds GitHub's
  100 MB limit and is git-ignored today).
- Curated, possibly public (no-login) "research views" for dissemination beyond the classroom.

## Principles (carried forward)

- **File-based, no database** — accounts as pickles, content as JSON/XML, results as a
  regenerable disk cache. Keep authored content (`lessons/`) committable and private/large data
  (`user/`, `cache/`) out of git.
- **The data state is the substrate.** Filtering, stats, tables, and lessons are all
  deterministic functions of a filter *history*; reuse that model rather than forking it.
