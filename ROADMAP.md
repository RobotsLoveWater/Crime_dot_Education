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
| Data easily accessible | Partial | Web-accessible behind a real (password-verified) login; crosstab + gradebook CSV export exist, but there is still no login-free public view and no filtered-dataset export. |
| Filter by column, exclude by row value | **Done** | Core filter engine — `eq/ne/gt/ge/lt/le`, OR-same-column, MOC drill-down. |
| Date/time expressed sensibly & dynamically | Open | Year / sentence-length are plain numeric columns; no dynamic date handling. |
| Informative figures **and** tables | Partial | Cross-tabs + interactive Chart.js figures (distribution bars, grouped-bar crosstab companions) now in the web UI; the CLI's exportable Seaborn figures are still not reintroduced. |
| Dynamically contextualize data | Partial | MOC decoder + codebook labels + lesson narrative. |
| Preset data views with team commentary | **Done (evolved)** | Became the **learning-modules** feature — graded and authorable. |

## Roadmap

Grouped by theme; ordering within each is roughly by priority.

### 0. Educator portal & class-code system — **shipped** ✅

Delivered (scoped and built with the author, 2026-07). The implicit `edu-` classcode convention is
now a real **class-code system** — educators create **classes** as first-class objects (immutable
id + rotatable student **join code**, roster, assignments), and students **join with a code** and
stay members — with an **educator portal** on top: a student-progress dashboard + "needs
attention" triage, class/roster management (rotate / remove / reset / archive / delete),
per-module assignment & pacing, item-level analytics, gradebook CSV export, shareable data-state
links, computed answer keys, retake/feedback + email-domain policies, and per-module teaching
notes. This **subsumed the "Real authentication" item** under Platform hardening (below): Phase 0
now verifies passwords and reads `secret_key` from config, since the portal exposes cross-account
student data.

Governed by two documents: **`EDUCATOR_PORTAL.md`** (scope & design authority) and
**`EDUCATOR_PORTAL_PROMPTS.md`** (the 14-phase build order, 0–13). Delivered scope: auth + P0 + P1.
**Still deferred (P2 / grant scope):** fork-and-edit modules, standards-alignment tags, and a full
authoring UI — see section 5. Residual auth hardening (rate-limiting, HTTPS, a real educator-role
boundary) is also still open — see section 3.

### 0a. Visualization expansion (Visualize workbench + map-as-filter) — **shipped** ✅

Delivered on the `visualization_expansion` branch (2026-07-09): a new **Visualize** tab with an
extensive chart vocabulary over the current filtered slice — pie, treemap, waterfall (year-over-
year, surfacing the 2016 drug-sentencing-reform break), a county/judicial-district/region
**choropleth** (small samples rendered as texture rather than a confident color), an aggregated
scatter/bubble view, and a correlation matrix over a chosen numeric-column subset. **Map-as-filter**
threads through both the Visualize tab and the Filter view: clicking a geography applies the same
filter typing it would, verified byte-identical at the cache-directory level
(`test_map_filter_equivalence.py`). Also added `mode` as a descriptive statistic alongside mean/
median everywhere they appear.

Governed by two documents: **`VISUALIZATION_EXPANSION.md`** (scope & design authority) and
**`VISUALIZATION_EXPANSION_PROMPTS.md`** (the 16-phase build order, 0–15, all done). **One tracked
gap:** no shipped lesson uses a Visualize chart yet — `app.build_lesson_data` only supports `info`/
`table` focus views; closing it needs a new chart focus-view plus an authored lesson step (folded
into section 2's "grow the lesson library" item below, not a blocker on the tab itself).

### 1. Dissemination gaps (closest to the original goals)

- ~~**Richer figures / visualization.**~~ **Done** — the **Visualize workbench** (see section 0a
  below) added pie, treemap, waterfall (time), choropleth (geography), scatter/bubble, and a
  correlation matrix, plus map-as-filter. Still open: the legacy CLI's **exportable Seaborn
  figures** have not been reintroduced (`matplotlib`/`seaborn` remain dependencies and
  `settings.xml` still holds a palette).
- **Data export.** Crosstab CSV and the class gradebook CSV now export (both UTF-8 + BOM).
  Still missing: a **filtered-dataset export** — saving the current filtered view itself to CSV
  (reusing `Data.save`), not just its cross-tabulation.
- **Sensible date/time handling.** Present year and sentence-length columns as dates / durations
  rather than bare floats.

### 2. Learning modules (continue the strongest thread)

- ~~**Wire or retire `checkpoint` steps.**~~ **Done** — `checkpoint` steps compare the lesson's
  data state to an expected token multiset and gate progress (learning-modules Phase 5).
- **Grow the lesson library** beyond the current three intro modules, with educator-facing
  authoring documentation. (Per-module **teaching notes** now exist — an educator-only field on
  the lesson JSON — as does a computed answer-key view.)
- **Add a Visualize-chart lesson focus view.** The visualization expansion's one open acceptance
  gap: `app.build_lesson_data` only renders `info`/`table` focus views, so no lesson can dock a
  Visualize chart (pie/treemap/waterfall/choropleth/scatter/correlation) yet. Needs a new focus
  type plus an authored step using it.
- **Align the lesson docs.** `lessons/README.md` and `LEARNING_MODULES_PROMPTS.md` still read as
  forward-looking plans; update them to the shipped implementation (as `CLAUDE.md` now is).

### 3. Platform hardening (prerequisites for real deployment)

- ~~**Real authentication.**~~ **Done (Phase 0)** — `/login` verifies the password via
  `util.check_password`, and `secret_key` reads from the `SECRET_KEY` environment variable.
  **Still open — residual hardening:** no rate-limiting / account lockout, no HTTPS enforcement,
  and the `edu-` **educator role is still self-selectable at sign-up** (a classroom-trust
  convenience, not a trust boundary for who may author). These matter before any public deployment.
- ~~**Fix latent account bugs.**~~ **Done** — `account.create` returns `retrieve(userid)` on the
  already-exists path, and `/new` sets all three session keys.
- **Complete stubbed operations** if needed: AND / OR-across-different-columns filters (the `a`
  and `d` action codes), which are currently unimplemented.

### 4. Data coverage

- **Extend beyond 2001–2019** toward the full historical range of the Commission's data, and
  **reconcile the start year** — prior documents have cited both 1980 and 1981.

### 5. Deployment & delivery (grant)

- A hosting story that handles the large data files (git-ignored: the ~23 MB `cache/raw.parquet`
  base the runtime prefers, plus the ~242 MB `cache/raw.csv` it falls back to — the CSV exceeds
  GitHub's 100 MB limit). A first cut exists in `deploy/` (gunicorn + nginx + systemd
  provisioner). With the runtime optimization below, sizing a prototype for <6 concurrent users
  drops from the earlier 4 vCPU / 8 GB estimate to a comfortable **1 vCPU / 2 GB**.
- **Runtime footprint optimization (done, `base-df-optimization` branch).** The app used to have
  no shared in-memory dataset: every cache-miss re-parsed the 242 MB CSV into a ~1.85 GB
  DataFrame, per worker (`WORKERS=3` default). All four levers are now built and verified
  byte-identical against a golden cache snapshot: categorical string columns (~8× RAM:
  1.72 GiB → 0.22 GiB), load-once per process (base parse 4.2 s → ~0 on reuse), a typed Parquet
  base (231 MB → 23 MB on disk; cold load 4.2 s → 0.25 s), and gunicorn `--preload` so workers
  share one copy-on-write base instead of `workers ×`. Design authority:
  **`BASE_DATAFRAME_OPTIMIZATION.md`**; build order: **`OPTIMIZATION_PROMPTS.md`** (Phases 0–4).
- Curated, possibly public (no-login) "research views" for dissemination beyond the classroom.

## Principles (carried forward)

- **File-based, no database** — accounts as pickles, content as JSON/XML, results as a
  regenerable disk cache. Keep authored content (`lessons/`) committable and private/large data
  (`user/`, `cache/`) out of git.
- **The data state is the substrate.** Filtering, stats, tables, and lessons are all
  deterministic functions of a filter *history*; reuse that model rather than forking it.
