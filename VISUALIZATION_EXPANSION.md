# Visualization Expansion (a Visualize workbench: charts, maps, correlation)

**Status:** **IMPLEMENTED — all 5 tiers / 16 phases, 2026-07-09, `visualization_expansion` branch**
(off `main`, which already includes the base-DataFrame optimization). All six chart types (pie,
treemap, waterfall, choropleth, scatter/bubble, correlation matrix), the "Other"-cutoff slider,
`mode`, and map-as-filter on both the Visualize tab and the Filter view are built and QA'd (§10
below). **One acceptance criterion is not met:** no shipped lesson uses a Visualize chart (§10
item 7) — tracked as follow-up, not a blocker for the tab itself. See `CLAUDE.md`'s
"visualization expansion" section for the current-state authority and exact routes/files.
**Author of proposal:** Claude (for Sidney D. Allen)
**Date:** 2026-07-08 (brainstormed + spec'd)
**Scope:** a new top-level **Visualize** workbench tab plus two map affordances, giving the Explorer
an extensive vocabulary of chart types over the *current filtered slice*. Reuses the
history/cache/`Data` substrate; adds one new descriptive statistic (`mode`) and one new family of
computed results (Pearson correlations). **No change to routes' meaning, cache-dir layout, or the
history schema** — map-clicks compile to ordinary filter tokens.

This file is the **design/scope authority** (the *why* + the decisions). The phased build order —
with per-step effort/risk and a recommended model — lives in **`VISUALIZATION_EXPANSION_PROMPTS.md`**.

---

## 0. What we're building (five tiers)

A blank-canvas **Visualize** tab beside Statistics · Compare · Filter, where a student picks a chart
type, picks columns, picks a measure + aggregate, and renders — all computed on the active history
(so it stays in sync with the sidebar count and chips). Plus a **map-as-filter** affordance woven
into the Filter view.

| Tier | Delivers |
|---|---|
| **1 — Foundations** | Twin docs; `mode` stat (backend + Explore stat card); the shared **measure + aggregate** helper; the **Visualize tab shell** (route family, nav, shared-renderer/fragment pattern, sidebar sync, empty builder). |
| **2 — Chart types** | **Pie** (capped), **Treemap** (two-column nested), **Waterfall** (year-over-year); the reusable **"Other"-cutoff slider**. |
| **3 — Geography** | **Choropleth** at county / judicial-district / region, colored by any measure+aggregate; **small-N texture**; **map-click → filter** in Visualize *and* the Filter view. The differentiator. |
| **4 — Correlate** | **Scatter/bubble** (aggregated lattice) and a **correlation matrix** (numeric subset, Pearson) drawn as a heatmap. The only tier with new statistical math. |
| **5 — QA & docs** | Cross-theme / responsive / a11y / no-CDN / immutability / cache-compat sweep; make the repo docs true; close out the roadmap. |

## 1. Problem

Today the app has **three charts total**: one top-20 distribution bar per column in Explore, a
grouped-bar companion + CSS heatmap on `≤8×8` crosstabs in Compare. Every statistic is a **static
cross-section** — a single number collapsed across all 19 years (2001–2019) and all 87 counties.
Two dimensions the dataset *already carries* are invisible to the tool:

- **Time** (`sentyear`, 2001–2019): the app can't show a trend, so it can't reveal a policy change
  (e.g. the 2016 Drug Sentencing Reform Act should be a visible break in drug-offense sentences).
- **Geography** (`county` / `district` / `region`): the app can't show *where* patterns differ —
  arguably the most intuitive on-ramp to disparity for a newcomer — and the only way to filter to a
  place is hunting an 87-item list.

And the chart *vocabulary* is thin: no histograms of distribution shape, no part-of-whole (pie /
treemap), no relationship views (scatter / correlation). For a **teaching tool**, the visual
grammar is the pedagogy — a box of one bar chart is a box of one idea.

## 2. Goals / non-goals

**Goals**
- A rich, blank-canvas chart vocabulary (pie, treemap, waterfall, choropleth, scatter/bubble,
  correlation matrix) over the current filtered slice, in sync with the sidebar data-state.
- Surface **time** and **geography**, the two flattened dimensions, as first-class views.
- **Map-as-filter**: clicking a geography appends the exact filter typing it would — same history,
  chips, and `cache/data/` dir.
- Charts that are **hard to misread**: capped "Other" with a live cutoff, small-N geographies shown
  as *uncertain* (texture) not confident (color), distribution shape over mean-only summaries.
- Add `mode` as an explicit descriptive statistic everywhere `mean`/`median` appear, and everywhere
  `count` is an aggregate offer `mean`/`median`/`mode` too.
- **Zero regression** on the repo's hard lines (§5).

**Non-goals**
- Not rewriting the history→cache→`Data` substrate (it stays exactly as is).
- Not a database, background jobs, or a client-side data layer.
- Not sub-county geography (city/ZIP/precinct — not in the data) or invented compass regions
  (`region` is the dataset's own 4-value metro classification, §4).
- Not bubble-*on-map* / proportional-symbol maps, not time-animated maps (parked, §7).
- No new **disk-cached** artifacts for charts/maps/correlations — they ride the existing
  per-request/cached path (crosstabs already compute fresh; correlations do too).

## 3. Why this is cheap: reuse the substrate

Every statistic in the app is a deterministic function of a *history* replayed by `cache._execute`
onto the shared base `Data`. The Visualize tab is mostly a **new presentation** of results the
engine already produces:

- **Pie** = a column's `Data.num_each` value-counts (already in `<column>.bin`).
- **Treemap / sunburst-story** = a two-column crosstab (`Data.get_table`) drawn as nested area.
- **Waterfall** = `get_table` by `sentyear` → turned into year-over-year deltas (Chart.js floating
  bars — no plugin).
- **Choropleth cell** = the chosen measure+aggregate per geography over `get_data(session)` — for
  `count`, literally `num_each`; for `mean`/`median`/`mode`, the new aggregate helper.
- **Scatter / bubble** = an aggregated lattice — nearly a crosstab (`get_table` again), count → dot
  size, so 294k rows don't collapse into ~70 overplotted points.
- **Map-click filter** = `cache.history_item_to_text` / `make_history` — the click *is* the existing
  filter apply. This is the whole reason geography is the highest wow-per-effort tier.

**Genuinely new math** is small and contained: `mode` (in `Data.get_column_info`) and Pearson
correlation (numeric subset, `DataFrame.corr`, computed fresh per request — never disk-cached, like
crosstabs).

## 4. The data facts that shape the design (verified against `cache/raw.parquet`)

- **`county`** — `category`, **87 clean names** ("Hennepin", "St. Louis", "Otter Tail", …), but with
  **join-hostile spellings** vs. a standard TopoJSON: `LeSueur` (no space), `Lac Qui Parle`,
  `Lake of the Woods`, `McLeod`, `Mille Lacs`, and `St. Louis`/`Saint Louis`. A normalization/alias
  table + a **startup assertion that all 87 map to exactly one map feature** is required (an
  unmatched county must fail loudly, never silently drop).
- **`district`** — `float64`, **1.0–10.0** (the 10 MN judicial districts). Map-click emits
  `f.district.eq.4.0` (float-coerced, matching the existing numeric-filter path). Note it is *also*
  a numeric column, so it appears in the measure picker too — a harmless quirk.
- **`region`** — `category`, **4 values**: `Greater MN`, `Hennepin`, `Oth Metro`, `Ramsey`. This is a
  **metro classification, not compass regions**: Hennepin and Ramsey are single counties, `Oth Metro`
  is the rest of the 7-county metro, `Greater MN` is everything else. A region choropleth is 4 shapes.
- **All three crosswalks derive from the data itself** — every row carries county + district +
  region, so `df.groupby('county')['district'].first()` (and the same for `region`) yields the
  dissolve mapping. **No external crosswalk files** — only one MN-counties TopoJSON to vendor.
- **Numeric columns:** **59 `float64`** (48 documented), the **measure** candidates behind
  mean/median/mode. Key ones: `time` (presumptive time), `staylnth` (stay length), `confine`,
  `aggsentc`, `agesent`/`ageoff`, `history`/`totprior`, and `sentyear` (the **year axis** for
  waterfalls). Because there are ~48 of them, the **correlation matrix must take a user-picked subset
  (2–8 columns)**, not auto-plot all numerics.

## 5. Hard constraints (apply to every tier)

- **No runtime CDN.** School networks filter them. `chartjs-chart-geo`, `chartjs-chart-treemap`,
  `patternomaly` (if used for texture), and the MN-counties TopoJSON are **vendored** under
  `static/js/vendor/` (or `static/geo/`) with `VERSIONS.md` updated. Extra chart libs load **only on
  the Visualize view** (mirroring how `explore.js`/`compare.js` load Chart.js only on their views).
- **No build step.** Hand-rolled, per `STYLEGUIDE.md`; tokens only (no raw hex), both light + dark
  themes from day one, no inline styles.
- **Cache-compatible.** Map-click and hand-typed filters must resolve to **byte-identical
  `cache/data/` dirs**. Reuse `cache.history_item_to_text` / `make_history`; touch neither history
  encoding nor the cache-dir layout.
- **`float64` stays `float64`.** The three checks at [data.py:78](data.py:78) (filter coercion),
  [data.py:283](data.py:283) (numeric stats gate), [data.py:366](data.py:366)
  (`get_numeric_columns`) depend on it. `mode` and correlations read floats; they never downcast.
- **The base DataFrame is immutable.** No `inplace=`/`.drop`/`.fillna`/`astype`/column-assign on the
  shared base — every aggregate and correlation reads a filtered *view/copy*. `test_base_immutability.py`
  must stay green (extend it to cover the new read paths).
- **Rendering lifecycle.** Every new chart renders on **`htmx:afterSettle` + a next-frame
  `resize()`** (the documented blank-canvas gotcha in `explore.js`/`compare.js`), reads colors from
  CSS tokens at render time, and re-renders on `themechange` and htmx history restores.
- **Shared-renderer / fragment pattern.** `/visualize` uses the same `render_*` + `wants_fragment()`
  + `templates/partials/` + `hx-push-url` pattern as explore/compare/filter. State is URL-encoded so
  it survives hard refresh and can be authored into a lesson deep link.

## 6. Design — the new pieces

### 6.1 Shared measure + aggregate model (Tier 1)
Generalize Compare's Measure picker into one helper: **measure** = `#` (count-of-cases) *or* a
numeric column (from `get_numeric_columns`); **aggregate** ∈ `{count, mean, median, mode}`. It maps
`(group_column, measure, aggregate)` → a by-group series over `get_data(session)`. One code path
feeds the choropleth fill, the waterfall/treemap value, and the bubble size. **Rule:** anywhere
`count` is offered, so are `mean`/`median`/`mode` — except where an aggregate is nonsensical for the
mark (a pie is inherently *share-of-count*; don't offer "mean per slice").

### 6.2 `mode` (Tier 1)
Add to `Data.get_column_info` (currently `mean`/`mdn`/`std`, gated on
`dtype == 'float64' and nunique > 1`). Tie rule: **show the first modal value + a "+N more" badge**
so multimodality is visible, never silently dropped. Note this dataset makes mode *meaningful*:
plea bargaining clusters sentences on round numbers (12/24/36/48/60 months), so the mode is a real
fingerprint of plea practice — but it is genuinely multimodal, hence the badge. Surfaces both as an
Explore stat card and as an aggregate option.

### 6.3 "Other"-cutoff slider (Tier 2)
A reusable control: any chart that buckets a long tail into "Other" (pie, treemap, and a retrofit of
the Explore distribution bar) exposes the top-N boundary as a live slider, turning "Other" from a
lie-of-convenience into something the student interrogates. Backend bucketing is parametrized by N;
front-end is progressive enhancement over a default.

### 6.4 Geography (Tier 3)
- **Choropleth** on `chartjs-chart-geo` over the existing Chart.js 4.5.1; a **county / district /
  region** grain toggle. District/region geometry is **dissolved at runtime** from the county
  TopoJSON via the data-derived crosswalk (memoized per process next to the `_base_df` singleton),
  so there are no district/region geometry files.
- **Small-N → texture** (via `patternomaly` or a `CanvasPattern` fill callback), not grey-out and
  not a confident color; threshold is one named constant (à la `STUCK_ATTEMPTS`), and the tooltip
  states the suppression + the N.
- **Map-click → filter** on two surfaces: a chart type in Visualize (drill-down loop: view filtered
  → click → filter deeper → chips update) and a **map input in the Filter view** alongside the
  existing categorical multi-select (single click = `eq`; multi-select = the existing
  `o.col.op.v1~v2` OR token). The categorical list + a readable value table remain the **no-JS /
  screen-reader fallback** — the map is never the only path to its function.

### 6.5 Correlate (Tier 4)
- **Scatter = bubble = one view**: aggregate to lattice points (e.g. severity × history) and encode
  case count as dot size (reusing `get_table`), so overplotting is impossible by construction.
- **Correlation matrix**: a **user-picked subset of 2–8 numeric columns**, Pearson via
  `DataFrame.corr` over the filtered slice, drawn as a heatmap reusing Compare's `.heat-N` ramp,
  **computed fresh per request** (never disk-cached). The severity × history × presumptive-`time`
  cells will glow near 1.0 — that is not a bug but the single most teachable artifact (the grid made
  visible); annotate it rather than hide it.

## 7. Future considerations (explicitly parked)
- **Confounding nudge** ("this map may reflect offense mix — control for severity?") — the mitigation
  for the naming trap (§8). Ship honest defaults now; design tooltip/legend copy so it can be added
  without rework.
- Proportional-symbol (bubble) **maps**; **small-multiple** maps/charts (per offense category or year
  bin); **year-animated** maps; per-1,000 **rate normalization** for count maps.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Maps lie by confounding** — a "mean sentence by county" choropleth mostly renders each county's *offense mix / criminal-history distribution*, not court harshness (the grid-pinning trap in a new costume). Confident-looking maps persuade harder than confident numbers. | Honest defaults: measure+aggregate flexibility, small-N **texture**, tooltip N. Park the explicit "what might explain this?" nudge (§7) but design for it. This is the **riskiest assumption** of the whole effort. |
| County-name join drops counties silently | Alias table + **startup assertion**: all 87 dataset counties map to exactly one feature, or fail loudly. |
| Map-click diverges from typed filter → different cache dir | Reuse `history_item_to_text`/`make_history`; a test asserts click-token == typed-token → identical `cache/data/` path. |
| 294k points overplot a scatter into meaningless blobs | Aggregate to a lattice; count → size. Never render raw rows. |
| Correlation matrix is huge / meaningless across 48 numerics | User picks a 2–8 column subset; annotate the grid-mechanical cells. |
| `mode` fragile / multimodal | First value + "+N more" badge; gate like the other numeric stats (`nunique > 1`). |
| New chart libraries as CDN/build deps | Vendor + `VERSIONS.md`; load only on the Visualize view; no build step. |
| A read path mutates the shared base | Read views/copies only; extend `test_base_immutability.py` over the aggregate + correlation paths. |
| Chart paints blank until refresh | Render on `afterSettle` + next-frame `resize()`; re-render on `themechange`/history restore. |

## 9. Rollback
Each tier is independently revertible and additive — none changes existing routes' behavior:
- Tiers 2 & 4 are chart types behind the new tab; removing a builder option removes the chart.
- Tier 1's `mode` is a new dict key + a stat card; the aggregate helper is new code with existing
  callers unchanged.
- Tier 3's map-as-filter sits *beside* the categorical list (the fallback is the pre-existing path),
  so pulling the map leaves filtering intact.
No data migration; user pickles, classes, lessons, and the disk cache are untouched throughout.

## 10. Acceptance criteria (whole effort) — verified 2026-07-09, Phase 14 QA
1. **Met.** Every Visualize chart computes on the **active history** and reconciles with the
   sidebar count.
2. **Met.** An 11-combo spot-check across all 6 chart types × 3 grains × 4 aggregates matched
   Explore/Compare exactly.
3. **Met.** `test_map_filter_equivalence.py` asserts this for every shape at every grain (not just
   a sample) — map-click and hand-typed filters produce **byte-identical `cache/data/` dirs**.
4. **Met.** All 87 counties join (startup assertion, `geo.assert_county_coverage`); a deep filter
   QA run showed 52 low-N counties rendering as hatch texture.
5. **Met.** `mode` appears as an Explore stat card and an aggregate option, with the "+N more" tie
   badge (`dsentenc` is the only shipped multimodal float64 column, 3 modes).
6. **Met.** Zero external/failed requests at 375 / 768 / 1280 in both themes; `VERSIONS.md` matches
   the vendored libs (htmx, Chart.js, chartjs-chart-treemap, chartjs-chart-geo — patternomaly was
   **not** needed, the small-N hatch is a hand-rolled `CanvasPattern`); `test_base_immutability.py`
   green.
7. **Partially met.** No change to routes' meaning, cache-dir layout, or the history schema — the
   only new route is `/visualize`; map-click and the "Keep only" button both ride the pre-existing
   `/explore/filter/<column>` POST. **`≥1` lesson uses a Visualize chart is NOT met** — no shipped
   `lessons/*.json` references a chart, and `app.build_lesson_data` only supports `info`/`table`
   focus views. Closing this needs a new chart focus-view plus an authored lesson step; left as
   deliberate follow-up work rather than folded into the QA/docs passes (Phases 14–15).

## 11. Effort estimate
- **Tier 1 (foundations):** ~1 day — backend `mode` + aggregate helper + the tab shell (the shell is
  the big piece; the rest is small).
- **Tier 2 (chart types):** ~1 day — three chart types + one reusable slider, all over existing data.
- **Tier 3 (geography):** ~2 days — the vendoring, the county-name join, the dissolve, texture, and
  the two map-as-filter surfaces + a11y fallback. Highest risk, highest payoff.
- **Tier 4 (correlate):** ~1 day — lattice scatter (cheap, it's a crosstab) + the correlation matrix
  (new math, small).
- **Tier 5 (QA & docs):** ~half a day.

Recommend **Tier 1 → 2 → 3 → 4 → 5** in order (later tiers plug into Tier 1's shell + aggregate
model). Tier 3 is the centerpiece; Tiers 2 and 4 are each shippable on their own once the shell
exists.
