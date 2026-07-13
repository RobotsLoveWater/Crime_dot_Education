# Chart Library Expansion (the Visualize workbench, wave 2)

**Status:** **SHIPPED — all 5 tiers / 17 phases built on `chart-library-expansion` branch (off
`optimizations-minor`, which carries the shipped wave-1 Visualize workbench + the request-path
optimization + the base-DataFrame levers).** Phase E2's cross-cutting QA passed everything
verifiable (26/26 charts render with a companion table, the 6 shipped charts byte-identical to
pre-A0, both guardrail tests green, zero external requests, both themes at 375/768/1280). See
CLAUDE.md's "Done: chart library expansion" section for the after-the-fact summary; this file and
`CHART_LIBRARY_EXPANSION_PROMPTS.md` are kept as the design/build record.
**Author of proposal:** Claude (for Sidney D. Allen)
**Date:** 2026-07-09 (brainstormed + spec'd), shipped 2026-07-11
**Scope:** grow the Visualize tab from **6 chart types to ~26**, add a **chart finder/search**, and
give **every chart an info box** (what it shows · what it's best for · what to watch out for). This is
the pre-lessons overhaul — the chart vocabulary an educator draws from before authoring lessons that
pin a chart. **No new statistical claims** (regression is parked, §2); everything is additive,
fresh-computed, and never disk-cached.

This file is the **design/scope authority** (the *why* + the decisions). The phased build order — with
a recommended model **for every step** — lives in **`CHART_LIBRARY_EXPANSION_PROMPTS.md`**. Read the
shipped wave-1 authority (`VISUALIZATION_EXPANSION.md` + CLAUDE.md's "visualization expansion" section)
first: this wave extends that substrate, it does not replace it.

---

## 0. What we're building

Three pillars, one architectural spine:

1. **The charts** — 13 Easy + 7 Hard new types on top of the shipped 6 (regression's two flavors
   parked, §2). Full inventory in §4.
2. **A chart finder** — a searchable, purpose-grouped gallery replacing the flat type picker, so 26
   options stay navigable (search on name + synonyms + purpose tags).
3. **An info box per chart** (all 26) — *what it shows · what it's best for · what to watch out for* —
   rendered in the builder on selection and as an "About this chart" panel on results. This is where
   the honesty pedagogy lives (§8).

The spine (§3) is a **chart registry**: 26 charts cannot be 26 hand-coded builder/renderer pairs the
way the first 6 were, so the registry becomes the single source of truth and the builder form, the
finder, the info boxes, and the renderers all read from it.

## 1. Problem / why now

The shipped Visualize tab (wave 1) has **6 chart types**, each with a bespoke `build_*` function in
`app.py` and a bespoke `render*` in `static/js/visualize.js` (`renderPie`/`renderTreemap`/… dispatched
by `renderChart`). That hand-coded-per-chart shape was fine for 6. **It does not survive being
multiplied by four** — 26 `if kind === …` branches and 26 builders would rot both files, and the type
picker (`VIZ_CHART_TYPES`, a flat list of `{id, label, status, blurb}`) becomes an unnavigable wall.

And the tab isn't yet rich enough to author lessons against: the standing open gap
(`VISUALIZATION_EXPANSION.md` §10 crit 7 — no lesson uses a Visualize chart) is *upstream* of "which
chart." You wanted the vocabulary broad and self-explaining **before** wiring charts into lessons.
This wave delivers that vocabulary + the self-explanation (info boxes) + the navigation (finder), and
closes the lesson-bridge gap at the end (§E1).

## 2. Goals / non-goals

**Goals**
- 26 chart types reachable from one builder, each computed on the current filtered slice, in sync
  with the sidebar (unchanged from wave 1).
- A **registry-driven** builder so adding chart #27 is a data entry, not a refactor.
- A **finder** (search + purpose families) and an **info box** for every chart.
- Every chart ships an **accessible companion data table** (the no-JS / screen-reader / honesty twin).
- Close the lesson `chart` focus-view gap so lessons can pin a chart.

**Non-goals (explicitly parked)**
- **Regression** (bivariate line+CI *and* multiple/coefficient) — deferred to a future wave by author
  decision. Do not add `statsmodels`/`scipy`. (The design leaves room: a "Relationship" family and a
  distribution engine it could later reuse.)
- **The improbable list** (`sunburst`, `strip/swarm`, `ridgeline`, `hexbin`, `calendar heatmap`) — see
  the wave-2 feasibility triage in the session record; each needs D3 / a custom engine or fights the
  294k-row, discrete-numeric, year-granular data.
- **The domain-shaped views** floated in brainstorm (grid heatmap, dumbbell, departure-as-default
  measure, small multiples, diverging bar) — genuinely valuable, but a separate initiative; noted in
  §7 of `VISUALIZATION_EXPANSION.md`'s spirit. (The **grid heatmap is nearly free** — the Compare
  `.heat-N` crosstab reskinned — if ever wanted as #27.)
- No new **disk-cached** artifacts; no change to routes' meaning, cache-dir layout, or history schema;
  no new statistical *claims* beyond descriptive summaries.

## 3. The spine: a chart registry

Today `VIZ_CHART_TYPES` ([app.py:1573](app.py:1573)) is a flat list of `{id, label, status, blurb}`,
and the six builders are hand-dispatched in `render_visualize` ([app.py:2229](app.py:2229)) and in
`renderChart` ([static/js/visualize.js:767](static/js/visualize.js:767)). **A0 expands each entry into
a full descriptor** and moves the builder-form field logic and the JS dispatch to read from it:

```
{ id, label, family,                      # family ∈ Comparison|Composition|Distribution|Trend|Relationship|Geography
  synonyms: [...], tags: [...],           # powers the finder's search
  info: { shows, best_for, watch_out },   # powers the info box (§6, §8)
  inputs: [ ...slot specs... ],           # which pickers show (column, column2, measure, aggregate, grain, subset, cutoff, bins)
  aggregates: [...],                       # subset of VALID_AGGREGATES this chart allows (some exclude mode — see wave-1 carve-outs)
  column_types: {...},                     # categorical/numeric/geo constraints per slot
  renderer,                                # renderer-family key (Categorical-series | Line | Distribution | Plugin | Server-HTML | Tiled)
  status }                                 # 'ready' (keep the wave-1 gate)
```

**Hard requirement:** the six shipped charts migrate onto the registry with **zero behavior change** —
their builder output and URLs must be byte-identical before/after A0 (spot-checked). A0 is the only
phase that touches proven shipped code; it is the refactor-risk phase and is gated first.

## 4. The chart inventory (families → data shape → renderer)

| New charts | Data shape (backend source) | Renderer family |
|---|---|---|
| **bar, lollipop, dot plot, donut** | one-group series (`Data.aggregate_by_group` — exists, [data.py:441](data.py:441)) | Categorical-series (donut = pie w/ cutout) |
| **grouped / stacked / 100% stacked bar** | two-group matrix (**new** `aggregate_by_two`, B1) | Categorical-series |
| **line, area, stacked area, slope, bump** | one/two-group series over an ordered axis; bump adds a rank transform | Line |
| **histogram, ECDF, KDE** | distribution stats (**new** numpy engine, B2) | Distribution (bar / stepped line / area) |
| **box, violin** | per-group five-number summary + density (**new** engine + a vendored plugin) | Plugin (`@sgratzl/chartjs-chart-boxplot`) |
| **mosaic** | two-group crosstab shares (B1) | **Server-rendered HTML/CSS** (no canvas — the correlation-matrix precedent) |
| **pair plot (SPLOM)** | pairwise 2D bins (**new** `bin2d`, B3) + diagonal histograms (B2) | Tiled canvases |
| **animated time-series** | per-year frames of a two-group matrix (B1) | Line/bar + scrubber |

Already shipped (migrate onto the registry, unchanged): **pie, treemap, waterfall, choropleth,
scatter/bubble, correlation matrix.**

## 5. Backend engines (all additive, fresh-computed, ride the slice LRU)

Three new read-only helpers on `Data`, each built **beside** existing code, never into it:

- **B1 — `aggregate_by_two(group_a, group_b, measure, aggregate)` → matrix.** The two-group sibling of
  `aggregate_by_group`. Built on the **request-path P4 pattern** — one `groupby([a,b], observed=True)`
  count pass + per-group Series reductions for the measure, **not** `groupby.agg` (P4 proved the Cython
  accumulation order can flip a cell on a rounding boundary). Feeds grouped/stacked/100%/stacked-area/
  slope/bump/mosaic/animated. Verified against slow nested-filter oracles; `get_table`
  ([data.py:357](data.py:357)) is left byte-for-byte untouched (its output is compare-visible).
- **B2 — distribution stats engine, `numpy`-only (no `scipy`).** Per column, optionally per group:
  five-number summary + 1.5·IQR whiskers (summarized — **no raw outlier arrays shipped to the
  client**); histogram (Freedman–Diaconis default bin width, user override); **ECDF as the cumulative
  sum of the already-vectorized `value_counts`** (never 294k points over the wire); and a **binned KDE**
  (linear binning + Gaussian-kernel convolution, Silverman-rule bandwidth default + control). Oracle-
  tested against pandas/numpy directly.
- **B3 — `bin2d(col_x, col_y)` → grid** via `np.histogram2d`, bin count capped; discrete columns use
  their natural integer lattice. Feeds the SPLOM's off-diagonal panels.

All three are read-only over the filtered view (`test_base_immutability.py` extended to cover them),
return raw numeric payloads (presentation rounds), and are wrapped by a fresh-per-request `cache`
helper like `get_aggregate` — **never disk-cached** (matching crosstabs/correlations), riding the
existing filtered-slice LRU (`cache._filtered_cache`).

## 6. Finder + info boxes

- **Finder (A1):** the flat picker becomes a card gallery grouped by the six **purpose families**, with
  a search input filtering on `label` + `synonyms` + `tags` (e.g. "proportion", "over time", "spread",
  "share", "relationship"). Reuses the existing search idiom (`filter.js`/`explore.js` column search,
  the `[data-picker]` combobox) — keyboard-complete; the no-JS fallback is the plain grouped list.
- **Info box (A1 render + A2 content):** each registry entry's `info: {shows, best_for, watch_out}`
  renders in the builder on selection and as a collapsible "About this chart" on the result. A2 authors
  all 26 entries; this is teaching copy (author-reviewable), not filler — see §8.

## 7. Hard constraints

All of wave 1's (from `VISUALIZATION_EXPANSION.md` §5): map/cache-compat untouched (this wave adds no
map paths), `float64` stays `float64`, base + cached slices immutable, **no runtime CDN / no build
step** (vendor every new lib + `VERSIONS.md`; chart libs load only on the Visualize view), tokens +
both themes, charts render on **`htmx:afterSettle` + next-frame `resize()`**, `render_visualize` +
`wants_fragment()` + URL-encoded state with the unknown-`chart` → blank-canvas fallback. Plus **two new
ones** for this wave:

1. **Additive at the data layer.** New engines sit *beside* `get_table`/`aggregate_by_group`, never
   inside them. No `.bin` byte is at risk anywhere in this wave (nothing new is disk-cached, and the
   compare-visible `get_table` is not modified).
2. **Every chart ships a companion data table.** It is the a11y fallback, the no-JS path, and the
   honesty check in one. No canvas without its table twin.

## 8. Data-fit honesty (the info boxes carry it)

The recurring caveats from the feasibility triage are load-bearing pedagogy on this dataset, and the
`watch_out` field is where they live:

- **Discrete-spiky numerics.** Sentence lengths cluster on round numbers (12/24/36/48/60 months — the
  `mode` insight). **KDE, violin** *smooth those spikes away* — the exact phenomenon the tool teaches.
  Their info boxes must say so, and D2 (KDE) should detect mass concentrated on few values and nudge
  toward the histogram.
- **294k rows.** Nothing per-point survives — every distribution/relationship chart **summarizes
  server-side** (five-number stats, binned KDE, ECDF from counts, 2D bins). Raw rows never leave the
  server. This is why strip/swarm/hexbin are parked, not built.
- **Composition can mislead.** 100% stacked bars hide absolute Ns (the companion table restores them);
  pie/treemap cap categories via the "Other"-cutoff slider (`partials/other_cutoff_slider.html` /
  `otherbucket.js`, `window.chartBucket`).
- **Animation dramatizes noise.** The animated time-series must not autoplay, must respect
  `prefers-reduced-motion`, and its static multi-line fallback is the export truth.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| A0's registry refactor breaks a shipped chart | Migrate the 6 with **before/after URL + builder-output spot-checks**; A0 is gated first and reviewed (`/code-review high`). |
| 26 types overwhelm the picker | That's exactly what the finder's families + search (A1) exist to solve; usability-check at 26. |
| `@sgratzl/chartjs-chart-boxplot` violin API demands raw arrays | **Spike D1 first**: if it won't take precomputed density, violin falls back to a hand-rolled mirrored-area render from B2's KDE. Box is unambiguous (takes precomputed stats). |
| KDE/violin mislead on spiky data | Loud `watch_out` copy + D2 spikiness nudge; box/ECDF/histogram offered as honest alternatives. |
| SPLOM's N² canvases hurt performance | Hard-cap the numeric subset (~5) reusing `build_compare_options`; panels are aggregated (B3), never raw. |
| A read path mutates the base | Engines read views/copies; extend `test_base_immutability.py`; no `inplace`/`astype` on `self.df`. |
| Payload bloat | Summarize server-side; nothing raw-row ships; warm-payload perf budget (~100 ms) checked in E2. |
| Chart paints blank until refresh | `afterSettle` + `resize()`; re-render on `themechange`/history restore (wave-1 lifecycle). |

## 10. Rollback

Additive and reversible. Each chart is a registry entry + a renderer-family branch; removing an entry
removes the chart. The engines are new methods with no existing callers changed. A0's registry, if it
ever regressed a shipped chart, reverts to the wave-1 hand-dispatch (kept in git history). No data
migration; pickles, classes, lessons, and the disk cache are untouched.

## 11. Acceptance criteria

1. All 26 chart types render from the registry-driven builder over the active slice and reconcile with
   the sidebar count; the 6 shipped charts are byte-identical to pre-A0.
2. Per-family correctness spot-checks match Explore/Compare numbers exactly.
3. Every chart has an info box (shows/best_for/watch_out) **and** a companion data table.
4. The finder search returns the right charts for purpose queries ("proportion", "over time", "spread")
   and is keyboard-usable with a no-JS fallback.
5. **No external requests** in both themes at 375 / 768 / 1280; `VERSIONS.md` matches vendored libs;
   both guardrail tests (`test_base_immutability.py`, `test_map_filter_equivalence.py`) green.
6. No new disk-cached artifacts; `get_table` output unchanged; no change to routes' meaning, cache
   layout, or history schema.
7. A lesson `chart` focus-view exists (`build_lesson_data` extended beyond `info`/`table`), closing the
   standing wave-1 gap so a lesson can pin a Visualize chart.

## 12. Effort estimate

~8–10 focused days: Tier A ~2 (A0 the big one), Tier B ~2, Tier C ~1.5, Tier D ~3 (box/violin + SPLOM
are the peaks), Tier E ~1.5. **No Fable phase this wave** — wave 1's Fable slot existed for the
map-click ↔ cache-dir linchpin; nothing here is disk-cached or cache-keyed, so every step is additive,
fresh-computed, and oracle-testable. The two peaks (B2 stats engine, D1 plugin) are Opus (ultra) +
`/code-review high`, not Fable.
