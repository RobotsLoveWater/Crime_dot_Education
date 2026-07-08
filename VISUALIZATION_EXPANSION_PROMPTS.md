# Visualization Expansion — Implementation Prompts

> **Status: PLANNED — `visualization_expansion` branch (off `main`, which already includes the
> base-DataFrame optimization).** Nothing here is built yet. Feed **one phase at a time** to a fresh
> Claude instance (or use as a dev checklist). Each phase should end green before the next starts.

Sequenced, self-contained prompts for the **Visualize workbench**: a new top-level tab with an
extensive chart vocabulary (pie, treemap, waterfall, choropleth, scatter/bubble, correlation matrix),
plus map-as-filter — all over the current filtered slice.

Read **`VISUALIZATION_EXPANSION.md`** (the design/scope authority) first for the rationale, the
verified data facts (geo encodings, numeric columns), the substrate-reuse argument, and the risks.
This file is the *build order*; that file is the *why*.

## How to use this file

- Do the phases **in order** — later phases assume earlier ones exist. Tiers 2–4 plug into Tier 1's
  shell + aggregate model.
- Each prompt names files to read, what to build, how to know it's done, and what not to do. Keep the
  **Global constraints** below in scope for every phase.
- After each phase: run the app, verify in the browser (both themes), run
  `test_base_immutability.py`, commit, move on.
- **Tier 1 → 2 → 3 → 4 → 5.** Tier 3 (geography) is the centerpiece; Tiers 2 and 4 are each shippable
  on their own once the Tier 1 shell exists.

## Global constraints (apply to every phase)

- **Cache-compatible.** Map-click and hand-typed filters must resolve to **byte-identical
  `cache/data/` dirs**. Reuse `cache.history_item_to_text`/`make_history`; never touch history
  encoding or the cache-dir layout.
- **`float64` stays `float64`** — the three checks at [data.py:78](data.py:78) /
  [data.py:283](data.py:283) / [data.py:366](data.py:366) depend on it. New stats read floats; never
  downcast.
- **Base DataFrame immutable** — read views/copies only; no `inplace=`/`.drop`/`.fillna`/`astype`/
  column-assign on the shared base. Extend `test_base_immutability.py` over new read paths; keep it
  green.
- **No runtime CDN, no build step.** Vendor every new lib + TopoJSON (`VERSIONS.md`); load extra
  chart libs **only on the Visualize view**. Tokens only, both themes, no inline styles
  (`STYLEGUIDE.md`).
- **Rendering lifecycle.** New charts render on **`htmx:afterSettle` + next-frame `resize()`**, read
  colors from CSS tokens, re-render on `themechange` + htmx history restores.
- **Shared-renderer/fragment pattern.** `/visualize` mirrors explore/compare/filter: `render_*` +
  `wants_fragment()` + `templates/partials/` + `hx-push-url`; state URL-encoded (hard-refresh-safe,
  lesson-deep-linkable).
- **Windows repo.** Verify in PowerShell (or the Bash tool). `.venv/`, `cache/`, `user/`, `classes/`,
  `dataset.sav` stay git-ignored.

## Rating legend (effort · risk · model)

Each phase carries `**Effort:** S/M/L · **Risk:** Low/Med/High · **Model:** …`.

- **Sonnet** — *rarely*: mechanical, well-patterned, low-risk work (a stat card, a docs pass).
- **Opus** — the default workhorse for real feature work. Escalate reasoning:
  - **Opus** — normal.
  - **Opus (high)** — gnarly reasoning, multi-file, correctness-sensitive.
  - **Opus (ultra)** — highest complexity / broad blast radius; pair with `/code-review high` (or
    `ultra`) after.
- **Fable** — *only when vital*: the linchpin step where a silent, subtle correctness miss is
  expensive and hard to catch later. Used **once** here (P11, the map-click ↔ cache-dir equivalence).

---

# TIER 1 — Foundations

## Phase 0 — Guardrails & docs prep (no user-facing change)
**Effort:** S · **Risk:** Low · **Model:** Sonnet

**Goal:** extend the immutability guardrail to the read paths the new stats/aggregations will use, so
every later phase can prove it mutated nothing; confirm the twin docs are in place.

**Read first:** `VISUALIZATION_EXPANSION.md`, `test_base_immutability.py`, `data.py`
(`get_column_info`, `get_table`, `get_numeric_columns`), `cache.py` (`get_data`, `_execute`).

**Build:**
- Add assertions to `test_base_immutability.py` that after a representative aggregate/correlation read
  (once those exist, keep the hooks minimal now) the base frame's shape/`id`/spot-checked values are
  unchanged.
- No runtime behavior change.

**Acceptance:** `test_base_immutability.py` passes; docs present.
**Don't:** add features yet.

---

## Phase 1 — Backend: `mode` + shared measure/aggregate helper
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** the one new descriptive stat + the one shared aggregation code path every later tier reuses.

**Read first:** `data.py` (`get_column_info` [data.py:241](data.py:241), `get_numeric_columns`,
`get_table`, `num_each`), `cache.py` (`get_data`, `history_override`).

**Build:**
- Add `mode` to `get_column_info` output (gated like the other numeric stats,
  `dtype == 'float64' and nunique > 1`). **Tie rule: first modal value + `"+N more"`** metadata so
  multimodality is visible.
- A shared helper mapping `(group_column, measure, aggregate)` → by-group series over
  `get_data(session)`, where `measure` = `#`count or a numeric column and `aggregate` ∈
  `{count, mean, median, mode}`. This feeds choropleth fills, waterfall/treemap values, bubble sizes.
  Keep it read-only over a filtered view.

**Acceptance:** `mode` computes with the tie badge; the helper returns correct per-group values that
match hand-computed spot checks; immutability test green.
**Don't:** downcast floats; offer `mean/median/mode` where the mark is inherently share-only (pie).

---

## Phase 2 — Explore: `mode` stat card
**Effort:** S · **Risk:** Low · **Model:** Sonnet

**Goal:** surface `mode` beside mean/median in the Explore statistics view (the "minor upgrade" that
ships Phase 1's math to users).

**Read first:** `app.py` (`render_explore`, `build_chart`), `templates/explore.html`,
`templates/partials/explore_column.html`, `STYLEGUIDE.md` (stat cards).

**Build:** add a Mode stat card (value + "+N more" badge when multimodal); both themes; no layout
regression.

**Acceptance:** Mode renders for numeric columns, hides for non-numeric/`≤1 unique` (like the others);
multimodal badge shows.
**Don't:** read `mode` from cached pickles' stale text — use the live compute.

---

## Phase 3 — Visualize tab shell (blank canvas)
**Effort:** L · **Risk:** Med · **Model:** Opus (high)

**Goal:** the backbone all chart families plug into — a new tab, the fragment plumbing, the sidebar
sync, and an empty builder.

**Read first:** `app.py` (`render_compare`/`render_filter`, `wants_fragment`, `inject_globals`,
`build_column_browser`), `templates/layout.html` (top bar + phone bottom-nav + sidebar),
`templates/compare.html` + its partials, `static/js/compare.js`, `STYLEGUIDE.md`,
`UI_OVERHAUL_PROMPTS.md` (Phases 1–3 for the pattern).

**Build:**
- `/visualize` route family with `render_visualize()` + `wants_fragment()`; partials under
  `templates/partials/`; `hx-push-url`; state URL-encoded.
- Nav entry in the top bar **and** the phone bottom-nav (`aria-current`).
- Sidebar data-state stays in sync (reuse the `datastate` context processor + column browser).
- Blank-canvas builder skeleton: chart-type picker → column picker(s) → measure/aggregate picker
  (reusing Phase 1's model + the `[data-picker]` combobox) → render target. Renders a "pick a chart"
  empty state until Tier 2.
- Establish the "extra chart libs load only on the Visualize view" loading convention (like
  `explore.js`/`compare.js`).

**Acceptance:** `/visualize` loads full + as a fragment; nav highlights; sidebar count/chips match
Explore; builder posts state into a URL that survives hard refresh; no console errors, both themes.
**Don't:** compute anything off the active history; don't load chart libs globally.

---

# TIER 2 — New chart types

## Phase 4 — Reusable "Other"-cutoff slider + Pie
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** the first real chart + the reusable long-tail control.

**Read first:** Phase 3 output, `data.py` `num_each`, `static/js/explore.js` (distribution chart),
`STYLEGUIDE.md`.

**Build:**
- **Pie** — share-of-cases by a categorical column, hard-capped top-N + "Other".
- **"Other"-cutoff slider** — a reusable component (backend bucketing parametrized by N; front-end
  slider) wired into pie now, and retrofit onto the Explore distribution bar.

**Acceptance:** pie renders capped, both themes; dragging the slider re-buckets without a full
refetch where feasible; no-JS shows a sensible default.
**Don't:** offer mean/median/mode on a pie (share-only); render 161 slices.

---

## Phase 5 — Treemap (two-column nested)
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** the part-of-whole view for two columns (the treemap-over-sunburst decision).

**Read first:** Phase 4 output, `data.py` `get_table`, `static/js/vendor/VERSIONS.md`.

**Build:** vendor `chartjs-chart-treemap` (+ `VERSIONS.md`); treemap sized by count **or** a numeric
aggregate (Phase 1 helper); the "Other"-cutoff slider applies; theme-aware.

**Acceptance:** treemap renders a two-column nesting matching the crosstab totals; aggregate switch
works; loads only on the Visualize view.
**Don't:** add D3 or a sunburst; hand-edit vendored files.

---

## Phase 6 — Waterfall (year-over-year)
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** the time view — change in a numeric aggregate across `sentyear` (the natural home for the
2016 drug-reform break).

**Read first:** Phase 5 output, `data.py` `get_table`, Chart.js floating-bar docs (bar with
`[start,end]` data).

**Build:** waterfall over `sentyear` using Chart.js **floating bars** (no plugin); value = the Phase 1
aggregate; rising/falling deltas colored from tokens; optional running total.

**Acceptance:** deltas sum to the endpoints; a known series (e.g. drug-offense mean sentence) shows a
visible 2016-era step; both themes.
**Don't:** hardcode the year range; assume `sentyear` is int (it's `float64`).

---

# TIER 3 — Geography (the centerpiece)

## Phase 7 — Geo foundation: vendor + county-name join + crosswalk
**Effort:** L · **Risk:** High · **Model:** Opus (ultra)

**Goal:** the geometry + the reliable join everything geographic rests on.

**Read first:** `VISUALIZATION_EXPANSION.md` §4, `data.py` (`get_numeric_columns`, `filter`),
`cache.py` (`_base_df`), `static/js/vendor/VERSIONS.md`.

**Build:**
- Vendor `chartjs-chart-geo` + an **MN-counties TopoJSON** (`VERSIONS.md`).
- A **county-name alias/normalization table** (`LeSueur`→`Le Sueur`, `St. Louis`/`Saint Louis`,
  `Lac Qui Parle`, `Lake of the Woods`, `McLeod`, `Mille Lacs`, …) reconciling dataset names to
  feature names.
- **Startup assertion:** all 87 dataset counties map to exactly one feature, else fail loudly.
- Derive the county→district and county→region **crosswalk from the data**
  (`df.groupby('county')[…].first()`), memoized per process next to `_base_df`.

**Acceptance:** the assertion passes over all 87 counties; the crosswalk yields 10 districts + 4
regions; no external crosswalk file.
**Don't:** ship a silent name mismatch; fetch a TopoJSON at runtime.

---

## Phase 8 — County choropleth
**Effort:** L · **Risk:** High · **Model:** Opus (ultra)

**Goal:** the first map — MN colored by a measure+aggregate on the active slice.

**Read first:** Phase 7 output, Phase 1 helper, `static/js/compare.js` (`.heat-N` ramp, theme
re-render), `STYLEGUIDE.md` (heatmap spec).

**Build:** `chartjs-chart-geo` choropleth over Chart.js 4.5.1; fill from the Phase 1 measure+aggregate
(count/mean/median/mode); legend ramp; colors from tokens; render on `afterSettle`+`resize()`,
re-render on `themechange`/history restore.

**Acceptance:** each county's value **equals** the matching Compare/crosstab value for ≥5 sampled
combos; legend correct; both themes; no blank-until-refresh.
**Don't:** compute off anything but the active history; hardcode a color.

---

## Phase 9 — District / region dissolve + grain toggle
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** the three-level grain switch.

**Read first:** Phase 8 output, Phase 7 crosswalk.

**Build:** dissolve district/region geometry at runtime from the county TopoJSON via the crosswalk
(memoized, lazy); a county / "Judicial District N" / region toggle; friendly label for `Oth Metro`.

**Acceptance:** district renders 10 shapes, region 4; values match the equivalent categorical
aggregate; toggle is stateful in the URL.
**Don't:** add geometry files for district/region.

---

## Phase 10 — Small-N texture
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** make thin samples *look* uncertain instead of confidently colored.

**Read first:** Phase 8 output, `static/js/vendor/VERSIONS.md`, `analytics.py` (the `STUCK_ATTEMPTS`
named-constant idiom).

**Build:** below a single named N threshold, fill the geography with a **texture/hatch** (via
`patternomaly` — vendor + `VERSIONS.md` — or a `CanvasPattern` fill callback), not grey and not a
data color; tooltip states the suppression + the N.

**Acceptance:** a deliberately deep filter turns low-N counties to texture with an explanatory
tooltip; threshold is one documented constant; both themes.
**Don't:** silently drop or grey-out low-N geographies.

---

## Phase 11 — Map-click → filter (Visualize + Filter view) + a11y fallback  ⚠ VITAL
**Effort:** L · **Risk:** High · **Model:** Fable

**Goal:** the linchpin — clicking a geography appends the *exact* filter typing it would, on both
surfaces, with a fully accessible fallback. A silent divergence here (wrong token → different cache
dir → wrong-but-plausible numbers) is the worst failure in the whole effort, hence the model.

**Read first:** `app.py` (`explore_filter_column`, `explore_filter_preview`, `render_filter`,
`parse_share_token`), `cache.py` (`history_item_to_text`, `history_text_to_item`), `make_history.py`,
`templates/filter.html` + partials, `static/js/filter.js`.

**Build:**
- **Visualize:** map-click on county/district/region appends `f.county.eq.Hennepin` /
  `f.district.eq.4.0` / `f.region.eq.<v>` via the existing apply path (chips + count update;
  drill-down loop).
- **Filter view:** a map input beside the categorical multi-select — single click = `eq`,
  multi-select = the existing `o.col.op.v1~v2` OR token; the live "~N would match" preview reuses
  `/explore/filter/<col>/preview`.
- **a11y / no-JS fallback:** the categorical list + a readable values table remain fully usable; the
  map has an accessible name; tooltip content is reachable as text.
- **A test asserting click-token == typed-token → identical `cache/data/` dir** for each grain.

**Acceptance:** clicking Hennepin produces the same history, chip, URL, and cache dir as typing it
(district as `…4.0`); OR multi-select matches the list path; the preview count equals the post-apply
chip; screen-reader/no-JS path works; the equivalence test passes.
**Don't:** invent a bespoke token; make the map the only path to its filter.

---

# TIER 4 — Correlate (new math)

## Phase 12 — Aggregated lattice scatter / bubble
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** relationship view without 294k overplotted points.

**Read first:** Phase 3 shell, `data.py` `get_table`, `static/js/compare.js`.

**Build:** aggregate two numeric columns to lattice points (reuse `get_table`), plot as a
scatter/bubble with count → dot size (scatter and bubble are the same view). Both themes; renders on
`afterSettle`+`resize()`.

**Acceptance:** bubble sizes match cell counts; no raw-row rendering; a known pair (e.g. severity ×
presumptive `time`) shows the expected lattice.
**Don't:** scatter raw rows; treat bubble as a separate builder.

---

## Phase 13 — Correlation matrix
**Effort:** L · **Risk:** High · **Model:** Opus (ultra)

**Goal:** a numeric correlation heatmap that teaches the grid.

**Read first:** Phase 12 output, `data.py` `get_numeric_columns`, `static/js/compare.js` (`.heat-N`),
`STYLEGUIDE.md`.

**Build:** a **2–8 column numeric subset** multiselect (from `get_numeric_columns`); Pearson via
`DataFrame.corr` over the filtered slice; heatmap on the `.heat-N` ramp; **computed fresh per request,
never disk-cached**; annotate the grid-mechanical cells (severity × history × presumptive-`time`
≈ 1.0) as the teachable artifact.

**Acceptance:** matrix values match hand-computed `.corr` on the same slice; subset selection works;
no disk cache written; annotation present; immutability test green.
**Don't:** auto-plot all 48 numerics; correlate encoded categoricals; disk-cache the result.

---

# TIER 5 — QA & docs

## Phase 14 — Cross-cutting QA
**Effort:** L · **Risk:** Med · **Model:** Opus (high)

**Goal:** prove it holds together across themes, sizes, a11y, and the repo's hard lines.

**Read first:** `STYLEGUIDE.md` (a11y checklist), `static/js/vendor/VERSIONS.md`, `UI_OVERHAUL_PROMPTS.md`
(Phase 7 QA recipe).

**Build/verify:** both themes; responsive at 375 / 768 / 1280 (phone bottom-nav, drawer, sticky
tables, bottom-sheet where relevant); a11y (keyboard path + list/table fallbacks for the map); **zero
external requests** (all vendored, `VERSIONS.md` matches); `test_base_immutability.py` green;
**cache-compat** (map-click dirs == typed-filter dirs); the ≥5-combo correctness spot-check from the
design doc.

**Acceptance:** all Acceptance criteria in `VISUALIZATION_EXPANSION.md` §10 pass; no console errors;
no failed/external network requests.
**Don't:** sign off on a chart that paints blank or a map with no fallback.

---

## Phase 15 — Docs true + roadmap close-out
**Effort:** S–M · **Risk:** Low · **Model:** Sonnet

**Goal:** leave the repo docs matching reality.

**Read first:** `CLAUDE.md` (module map, routes, storage/vendor, the "In progress" sections),
`STYLEGUIDE.md`, `README.md`, `ROADMAP.md`, `VISUALIZATION_EXPANSION.md`.

**Build:** update `CLAUDE.md` (Visualize routes, new templates/JS/vendored libs, the module map, and
flip the "In progress: visualization expansion" section to done); fold new chart/component specs into
`STYLEGUIDE.md`; refresh `README.md`/`ROADMAP.md`; mark all phases done here (like the other
`*_PROMPTS.md` docs).

**Acceptance:** a fresh reader of `CLAUDE.md` + `STYLEGUIDE.md` can find every new route, template,
and vendored asset; this file reads as *done*.
**Don't:** leave forward-looking language once shipped.

---

## Done criteria (whole effort)
Mirrors `VISUALIZATION_EXPANSION.md` §10: charts compute on the active history and match
Explore/Compare exactly; map-click == typed-filter cache dirs; all 87 counties join; small-N is
texture; `mode` shipped with the tie badge; no external requests in both themes; immutability green;
no change to routes' meaning, cache layout, or the history schema; ≥1 lesson uses a Visualize chart.
