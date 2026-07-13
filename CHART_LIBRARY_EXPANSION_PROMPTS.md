# Chart Library Expansion — Implementation Prompts

> **Status: all phases (A0–E3) are DONE** (2026-07-11, `chart-library-expansion` branch, off
> `optimizations-minor`, which carries the shipped wave-1 Visualize workbench + the request-path
> optimization + the base-DataFrame levers). Phase E2's cross-cutting QA passed everything
> verifiable — both guardrail tests, per-family correctness spot-checks against Explore/Compare/raw
> pandas, all 26 charts rendering with a companion table, zero external requests, both themes at
> 375/768/1280, the 6 shipped charts byte-identical to pre-A0. One caveat logged (not a blocker): the
> pair-plot SPLOM warms ≈150 ms at 3 columns → ≈370 ms at the 5-column cap, over the ~100 ms budget
> but an anticipated O(k²) peak the cap exists to bound. The prompts below are kept as the build
> record.

Sequenced, self-contained prompts for **wave 2 of the Visualize workbench**: grow it from 6 chart types
to ~26, add a chart **finder/search**, and give **every chart an info box**. The spine is a **chart
registry** (Phase A0) that all later phases read from.

Read **`CHART_LIBRARY_EXPANSION.md`** (the design/scope authority) first for the rationale, the
inventory, the registry design, and the risks. Read the wave-1 authority
(`VISUALIZATION_EXPANSION.md` + CLAUDE.md's "visualization expansion" section) to understand the
substrate this extends. This file is the *build order*; those are the *why*.

## How to use this file

- Do the phases **in order within a tier**; across tiers, **A → B → C/D → E** (C and D need B's engines;
  everything needs A0's registry).
- Each prompt names files to read, what to build, how to know it's done, and what not to do. Keep the
  **Global constraints** below in scope for every phase.
- After each phase: run the app, verify in the browser (both themes), run `test_base_immutability.py`
  (+ `test_map_filter_equivalence.py` after anything touching filters — nothing here should), commit,
  move on.

## Global constraints (apply to every phase)

- **Additive at the data layer.** New engines sit **beside** `get_table`/`aggregate_by_group`, never
  inside them. Nothing new is disk-cached; the compare-visible `get_table` ([data.py:357](data.py:357))
  is not modified — so **no `.bin` byte is at risk** this wave.
- **Base + cached slices immutable.** Read views/copies only; no `inplace=`/`.drop`/`.fillna`/`astype`/
  column-assign on `self.df`. Extend `test_base_immutability.py` over new read paths; keep it green.
- **`float64` stays `float64`** — the three checks at [data.py:78](data.py:78) /
  [data.py:283](data.py:283) / [data.py:366](data.py:366). New stats read floats; never downcast.
- **No runtime CDN, no build step.** Vendor every new lib (`static/js/vendor/` + `VERSIONS.md`); load
  extra chart libs **only on the Visualize view**. Tokens only, both themes, no inline styles
  (`STYLEGUIDE.md`).
- **Rendering lifecycle.** New charts render on **`htmx:afterSettle` + next-frame `resize()`**, read
  colors from CSS tokens, re-render on `themechange` + htmx history restores (wave-1 pattern in
  `visualize.js`).
- **Registry-driven.** After A0, a new chart is a `VIZ_CHART_TYPES` entry + a renderer-family branch —
  not a bespoke `build_*`/`render*` pair. Keep the `status: 'ready'` gate.
- **Every chart ships a companion data table** (a11y / no-JS / honesty twin). No canvas without its
  table.
- **Windows repo.** Verify in PowerShell (or the Bash tool). `.venv/`, `cache/`, `user/`, `classes/`,
  `dataset.sav` stay git-ignored.

## Rating legend (effort · risk · model)

Each phase carries `**Effort:** S/M/L · **Risk:** Low/Med/High · **Model:** …`.

- **Sonnet** — *rarely*: mechanical, well-patterned, low-risk (a docs pass). Used **once** here (E3).
- **Opus** — the default workhorse. Escalate reasoning:
  - **Opus** — normal feature work.
  - **Opus (high)** — gnarly / multi-file / correctness-sensitive; pair with `/code-review high` after.
  - **Opus (ultra)** — highest complexity / subtle stats / broad blast radius; `/code-review high` after.
- **Fable** — *only when vital* (a silent cache-keyed correctness miss). **No Fable phase this wave** —
  everything is additive, fresh-computed, and oracle-testable; the wave-1 Fable slot (map-click ↔
  cache-dir) has no equivalent here.

---

# TIER A — Registry, finder, info boxes (the spine)

## Phase A0 — Chart registry ✅ DONE
**Effort:** L · **Risk:** Med · **Model:** Opus (high)  ·  `/code-review high` after

**Goal:** turn `VIZ_CHART_TYPES` from a flat `{id,label,status,blurb}` list into the full descriptor all
later phases read from, and move the builder-form field logic + the JS dispatch onto it — migrating the
6 shipped charts with **zero behavior change**.

**Read first:** `app.py` (`VIZ_CHART_TYPES` [app.py:1573](app.py:1573), `render_visualize`
[app.py:2229](app.py:2229), `build_compare_options`, the six `build_*` builders), `static/js/visualize.js`
(`renderChart` [static/js/visualize.js:767](static/js/visualize.js:767), `renderChartSafe`),
`templates/visualize.html` + `templates/partials/visualize_view.html`, `CHART_LIBRARY_EXPANSION.md` §3.

**Build:** expand each registry entry to `{id, label, family, synonyms, tags, info{shows,best_for,
watch_out}, inputs[], aggregates[], column_types{}, renderer, status}`; drive the builder's picker
show/hide and the JS `renderChart` dispatch from it; migrate the 6 shipped charts (pie/treemap/waterfall/
choropleth/scatter/correlation) onto the registry unchanged.

**Acceptance:** the 6 shipped charts produce **byte-identical** builder output + URLs before/after (spot-
check each); adding a stub entry lights up the correct pickers with no new dispatch code; immutability
test green.
**Don't:** change any shipped chart's output; leave two dispatch paths (registry *and* the old `if`s).

---

## Phase A1 — Searchable chart gallery + info-box rendering ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** replace the flat type picker with a purpose-grouped, searchable card gallery, and render the
info box.

**Read first:** A0 output, `static/js/filter.js`/`static/js/explore.js` (search idiom), `static/js/app.js`
(`[data-picker]` combobox), `templates/partials/visualize_view.html`, `STYLEGUIDE.md`.

**Build:** cards grouped by the six families (Comparison · Composition · Distribution · Trend ·
Relationship · Geography); a search input filtering on label + `synonyms` + `tags`; the info box
(`shows/best_for/watch_out`) in the builder on selection and as a collapsible "About this chart" on
results. No-JS fallback = plain grouped list.

**Acceptance:** searching "proportion"/"over time"/"spread" surfaces the right charts; keyboard-complete;
no-JS shows the full grouped list; info box renders both places, both themes.
**Don't:** hide any chart behind search-only (the grouped list is the complete path).

---

## Phase A2 — Info content for all 26 charts ✅ DONE
**Effort:** M · **Risk:** Low · **Model:** Opus  (author-reviewable copy)

**Goal:** author every registry entry's `info{shows, best_for, watch_out}` — the honesty pedagogy.

**Read first:** A0/A1 output, `CHART_LIBRARY_EXPANSION.md` §8, `lessons/*.json` (voice), `STYLEGUIDE.md`
(voice/copy).

**Build:** concise, honest copy per chart. The `watch_out` field carries the data-fit caveats: KDE/violin
smooth away round-number plea clustering; 100% stacked hides absolute Ns; pie caps categories; animation
dramatizes noise; small-N maps mislead. Flag for author (Dr. Vigesaa / Dr. Clifford) review.

**Acceptance:** all 26 entries filled; no empty `watch_out`; reads as teaching copy, not filler.
**Don't:** overclaim (no causal language); pad with generic text.

---

# TIER B — Backend engines (additive, fresh-computed, ride the slice LRU)

## Phase B1 — Two-group aggregate helper ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus (high)  ·  `/code-review high` after

**Goal:** `Data.aggregate_by_two(group_a, group_b, measure, aggregate)` → matrix — the two-group sibling
of `aggregate_by_group`, feeding grouped/stacked/100%/stacked-area/slope/bump/mosaic/animated.

**Read first:** `data.py` (`aggregate_by_group` [data.py:441](data.py:441), `get_table`
[data.py:357](data.py:357), `_first_mode`, `VALID_AGGREGATES`, `COUNT_MEASURE`), the request-path P4
note in CLAUDE.md, `cache.py` (`get_aggregate`, `_filtered_cache`).

**Build:** one `groupby([a, b], observed=True)` count pass + per-group Series reductions for the measure
— **not** `groupby.agg` (P4: Cython accumulation order can flip a rounding-boundary cell). Wrap in a
fresh-per-request `cache` helper like `get_aggregate` (never disk-cached). Read-only over the slice.

**Acceptance:** matrix values match a slow nested-filter oracle cell-for-cell; `get_table` untouched;
immutability test green.
**Don't:** modify `get_table`; use `groupby.agg`; disk-cache the result.

---

## Phase B2 — Distribution stats engine (numpy-only) ✅ DONE
**Effort:** L · **Risk:** High · **Model:** Opus (ultra)  ·  `/code-review high` after

**Goal:** the shared stats behind histogram / ECDF / KDE / box / violin — **no `scipy`**.

**Read first:** B1 output, `data.py` (`num_each` [data.py:489](data.py:489), the `float64` gate),
`CHART_LIBRARY_EXPANSION.md` §5/§8.

**Build:** per column, optionally per group — five-number summary + 1.5·IQR whiskers (**summarized; no
raw outlier arrays to the client**); histogram (Freedman–Diaconis default, user bin override); **ECDF as
the cumulative sum of the vectorized `value_counts`** (never 294k points over the wire); **binned KDE**
(linear binning + Gaussian-kernel convolution, Silverman bandwidth default + control). Fresh-per-request,
read-only.

**Acceptance:** stats match hand-computed numpy/pandas on the same slice (oracle test); no raw-row payload
> a few KB; immutability green.
**Don't:** add scipy; ship raw per-row arrays; disk-cache.

---

## Phase B3 — 2D binning helper (SPLOM panels) ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** `Data.bin2d(col_x, col_y)` → grid via `np.histogram2d`, for the pair-plot off-diagonals.

**Read first:** B2 output, `data.py` (`distinct_counts` [data.py:433](data.py:433), `get_table`).

**Build:** `np.histogram2d` with a capped bin count; discrete columns use their natural integer lattice
(reuse `distinct_counts` to decide). Read-only, fresh-per-request.

**Acceptance:** bin grid matches a direct `np.histogram2d`; capped bins; immutability green.
**Don't:** bin high-cardinality columns unbounded; disk-cache.

---

# TIER C — Easy chart families

## Phase C1 — Categorical-series family ✅ DONE
**Effort:** L · **Risk:** Med · **Model:** Opus

**Goal:** bar, grouped bar, stacked bar, 100% stacked bar, lollipop, dot plot, donut — **one renderer**,
registry variants (stacking mode, mark style, cutout).

**Read first:** A0 registry, B1, `static/js/visualize.js` (`renderPie`, the dispatch),
`templates/partials/other_cutoff_slider.html` + `static/js/otherbucket.js` (`window.chartBucket`).

**Build:** a `renderCategoricalSeries` family reading single-series (`aggregate_by_group`) or two-group
(B1) data per the registry; native Chart.js bar/doughnut; 100%-stacked normalizes in JS; lollipop/dot are
mark-style variants; the "Other"-cutoff slider applies to single-series variants; companion table each.

**Acceptance:** each of the 7 renders + matches the companion table + Explore/Compare counts; both themes;
`afterSettle`+`resize()`; no blank-until-refresh.
**Don't:** fork a renderer per variant; drop the companion table.

---

## Phase C2 — Line family ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** line, area, stacked area, slope, bump.

**Read first:** C1 output, B1, `WATERFALL_GROUP`/`sentyear` handling in `app.py`.

**Build:** a `renderLine` family; native line/area/stacked-area; slope = a two-value ordered axis; bump =
a **server-side per-period rank transform** (in the backend helper, not JS), inverted axis, hand-rolled
end labels (no datalabels dep), top-N limiting.

**Acceptance:** line/area/stacked match the companion table; slope connects two periods; bump ranks match
a hand computation and don't spaghetti past the top-N cap; both themes.
**Don't:** hardcode the year range; assume `sentyear` is int (`float64`).

---

## Phase C3 — Histogram + ECDF ✅ DONE
**Effort:** M · **Risk:** Low-Med · **Model:** Opus

**Goal:** the two honest distribution charts.

**Read first:** B2 output, `static/js/otherbucket.js` (slider idiom), `static/js/explore.js`.

**Build:** histogram = native bar over B2 bins with a **bin-width slider** (reuse the cutoff-slider
idiom); ECDF = native stepped line over B2's cumulative counts; companion table each.

**Acceptance:** histogram bars sum to N; the bin slider re-bins without a full refetch where feasible;
ECDF is monotone 0→1; both themes.
**Don't:** ship raw values to bin client-side for 294k rows (bin server-side, B2).

---

# TIER D — Hard charts

## Phase D1 — Box + violin ✅ DONE
**Effort:** L · **Risk:** High · **Model:** Opus (ultra)  ·  `/code-review high` after

**Goal:** per-group distribution shape — the honest disparity view.

**Read first:** B2 output, `static/js/vendor/VERSIONS.md`, `static/js/visualize.js` (plugin-load pattern
for geo/treemap), `CHART_LIBRARY_EXPANSION.md` §9.

**Build:** **spike first** — confirm whether `@sgratzl/chartjs-chart-boxplot` (UMD, MIT, Chart.js-4)
accepts **precomputed** box stats + violin density. Vendor it (+ `VERSIONS.md`), load only on Visualize.
Box takes B2's five-number summary. **If violin demands raw arrays, do NOT ship them** — fall back to a
hand-rolled mirrored-area render from B2's KDE. Companion table each.

**Acceptance:** box whiskers/quartiles match B2; violin renders from precomputed density (or the KDE
fallback); no raw per-row arrays over the wire; both themes.
**Don't:** ship raw group arrays to satisfy the plugin; hand-edit the vendored file.

---

## Phase D2 — KDE chart ✅ DONE
**Effort:** S-M · **Risk:** Low · **Model:** Opus

**Goal:** a smooth density curve — with the loudest honesty guardrail in the library.

**Read first:** B2 output (KDE), C2 line family, `CHART_LIBRARY_EXPANSION.md` §8.

**Build:** line/area over B2's binned KDE; bandwidth control; **spikiness detection** — when mass
concentrates on few values, surface the `watch_out` nudge toward the histogram ("this data clusters on
round numbers"). Companion table (the underlying histogram).

**Acceptance:** curve integrates ~1; bandwidth control works; the round-number nudge fires on a spiky
column (e.g. a sentence-length field); both themes.
**Don't:** present KDE as ground truth on discrete data; hide the caveat.

---

## Phase D3 — Mosaic ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus (high)

**Goal:** a two-categorical proportional view — **server-rendered HTML/CSS**, no canvas (the correlation-
matrix precedent).

**Read first:** B1 output, `app.py` `build_correlation`/`build_crosstab` (the `.heat-N` server-HTML
pattern), `templates/partials/`, `STYLEGUIDE.md`.

**Build:** nested flex/grid rectangles from B1 shares — column widths ∝ column totals, cell heights ∝
within-column share — colored from tokens (`.heat-N`-style). Inherently screen-reader-friendly; the
companion table is the crosstab.

**Acceptance:** widths/heights match the crosstab proportions; readable + keyboard-navigable; both themes.
**Don't:** reach for canvas; hardcode colors.

---

## Phase D4 — Pair plot (SPLOM) ✅ DONE
**Effort:** L · **Risk:** High · **Model:** Opus (high)  ·  `/code-review high` after

**Goal:** the scatter-matrix companion to the correlation matrix ("see the shapes behind the r's").

**Read first:** B3 output, B2 (diagonal histograms), `app.py` `build_correlation` + its numeric-subset
picker (`build_compare_options`), `static/js/visualize.js` (correlation render).

**Build:** reuse the correlation matrix's **2–8 numeric-subset picker**, hard-cap ~5 for performance;
tiled canvases — off-diagonal = B3 2D-binned scatter, diagonal = B2 histogram. Companion table = the
correlation matrix.

**Acceptance:** an N×N grid renders for a small subset within a sane time budget; panels are binned (never
raw rows); both themes.
**Don't:** exceed the subset cap; render raw points; spawn unbounded canvases.

---

## Phase D5 — Animated time-series ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus

**Goal:** a year scrubber over the trend — motion as a teaching aid, not a gimmick.

**Read first:** C2 line family, B1 (per-year frames), `STYLEGUIDE.md` (reduced-motion).

**Build:** a play/pause + year scrubber stepping B1 frames through Chart.js transitions. **No autoplay;
respect `prefers-reduced-motion`;** the scrubber is keyboard-accessible; the static multi-line chart is
the fallback and the export truth. Companion table = the per-year matrix.

**Acceptance:** scrubbing/stepping updates the chart; reduced-motion disables animation; keyboard-usable;
static fallback present; both themes.
**Don't:** autoplay; make animation the only way to read the data.

---

# TIER E — Lesson bridge, QA, docs

## Phase E1 — `chart` focus-view in lessons ✅ DONE
**Effort:** M · **Risk:** Med · **Model:** Opus (high)

**Goal:** close the standing wave-1 gap (`VISUALIZATION_EXPANSION.md` §10 crit 7) so a lesson can pin a
Visualize chart — the reason this whole wave precedes lesson authoring.

**Read first:** `app.py` `build_lesson_data` (currently `info`/`table` only), `templates/partials/lesson_data.html`,
the lesson-state/sandbox path (`resolve_lesson_state`, `history_override`), `lessons/README.md`.

**Build:** extend `build_lesson_data` with a `chart` focus that renders a read-only Visualize chart from
lesson state (reuse the registry + renderers); no htmx nav / no editing in the lesson sandbox; never
mutate the student's history.

**Acceptance:** a lesson step with a `chart` focus renders the chart read-only from its state; student
history byte-identical across the step (immutability of the lesson sandbox); both themes.
**Don't:** let a lesson chart mutate history or re-use disk cache.

---

## Phase E2 — Cross-cutting QA ✅ DONE
**Effort:** L · **Risk:** Med · **Model:** Opus (high)

**Goal:** prove the 26-chart library holds together.

**Read first:** `CHART_LIBRARY_EXPANSION.md` §11, `STYLEGUIDE.md` (a11y checklist),
`static/js/vendor/VERSIONS.md`, `UI_OVERHAUL_PROMPTS.md` (Phase 7 QA recipe).

**Build/verify:** per-family correctness spot-checks vs. Explore/Compare; companion table present for all
26; both themes; responsive 375/768/1280; a11y (keyboard + table fallbacks); **zero external requests**
(all vendored, `VERSIONS.md` matches); both guardrail tests green; warm-payload perf budget (~100 ms) per
chart; the 6 shipped charts still byte-identical to pre-A0.

**Acceptance:** every §11 criterion in the design doc passes; no console errors; no failed/external
requests.
**Don't:** sign off a chart with no companion table or one that paints blank.

---

## Phase E3 — Docs true ✅ DONE
**Effort:** S · **Risk:** Low · **Model:** Sonnet

**Goal:** leave the repo docs matching reality.

**Read first:** `CLAUDE.md` (module map, routes, the Visualize section, vendor list), `STYLEGUIDE.md`,
`CHART_LIBRARY_EXPANSION.md`.

**Build:** update `CLAUDE.md` (the registry, the new engines, the finder/info-box, the new vendored
plugin, all 26 chart types, and flip the "In progress: chart library expansion" section to done); fold
the new chart/component specs into `STYLEGUIDE.md`; mark all phases done here (like the other
`*_PROMPTS.md` docs).

**Acceptance:** a fresh reader of `CLAUDE.md` + `STYLEGUIDE.md` can find every new chart, engine, route,
and vendored asset; this file reads as *done*.
**Don't:** leave forward-looking language once shipped.

---

## Done criteria (whole wave) — ✅ ALL MET (Phase E2, 2026-07-11)

Mirrors `CHART_LIBRARY_EXPANSION.md` §11: 26 charts from a registry-driven builder, the 6 shipped ones
byte-identical to pre-A0; per-family numbers match Explore/Compare; every chart has an info box + a
companion table; the finder search works with a no-JS fallback; no external requests in both themes;
both guardrail tests green; nothing new disk-cached and `get_table` unchanged; a lesson `chart`
focus-view closes the wave-1 gap. See CLAUDE.md's "Done: chart library expansion" section for the
verified after-the-fact summary, including the one logged, non-blocking caveat (pair-plot SPLOM warm
time at the 5-column cap).
