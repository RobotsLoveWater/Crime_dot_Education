# Request-Path Optimization — phased build plan

Companion to `BASE_DATAFRAME_OPTIMIZATION.md` / `OPTIMIZATION_PROMPTS.md`. Those four levers
(A–D) made the **base** DataFrame cheap to hold and share. This plan targets everything that
happens **on top of the base, per request** — the redundant history replays, the O(n·k) stat
loop, the nested-filter crosstab, and the repeat pickle reads that the base optimization did not
touch. House-style like the other `*_PROMPTS.md` docs: phases in dependency order, each with an
effort · risk rating, a recommended model, read-first files, acceptance criteria, and don'ts.

**Recommended-model vocabulary.** Each phase names one of four models, escalating with the care the
work demands: **Sonnet ultracode** (mechanical, cache-neutral, low-risk), **Opus xhigh** (real
reasoning but a contained blast radius), **Opus ultracode** (the large structural build with the
immutability guardrail on the line), and **Fable xhigh** (reserved for the one phase that can shift
`.bin` bytes — the cache-compat linchpin, mirroring Fable's P11 role in the viz prompts).

A standing instruction runs through every phase: **while executing, keep profiling and keep
looking.** Each phase ends with a short "profile & discover" step that feeds Appendix B (the
running candidate list). The point is not just to land these seven changes but to leave the
request path measured and the next round of wins already scouted.

---

## Global constraints (do not violate — inherited from the base-df work)

1. **Cache byte-identity.** The disk cache under `cache/data/` is content-addressed by the
   history token path. Any change that alters what gets pickled into `_data.bin` / `<col>.bin` /
   `_moc.bin`, or which cache dir a state resolves to, is a breaking change. Phases 1–4 are
   designed to be **cache-neutral** (they change *when/how often* work runs, not its output).
   Phase 5 is the one exception and is gated behind a golden-snapshot re-validation.
2. **`float64` stays `float64`.** The three `dtype == 'float64'` checks
   ([data.py:91](data.py:91), [298](data.py:298), [389](data.py:389)) and the numeric-filter
   coercion depend on it. No numeric column may become categorical.
3. **The base is never mutated in place**, and now **neither are cached filtered slices.** Every
   filter returns a new frame; every stat/aggregate reads read-only. This is the safety argument
   the whole sharing story rests on — `test_base_immutability.py` is the guardrail and must keep
   passing (Phase 3 extends it).
4. **Behavioral parity.** Every displayed number — stat cards, crosstab cells, chart values,
   sidebar badge — must be identical before and after. Phases that change a compute path
   (4, 5) verify against the current output, not just "looks right."

---

## Phase 0 — Baseline & measurement harness · effort S · risk none · **Sonnet ultracode**

You cannot claim a win you didn't measure, and this repo's culture is byte-identity proof, not
vibes. Stand up the measurement before touching a hot path.

**Read first:** `cache.py` (`_base_df`, `_execute`, `get_data`), `test_base_immutability.py`,
the "base DataFrame optimization" section of `CLAUDE.md`, `BASE_DATAFRAME_OPTIMIZATION.md`.

**Do:**
- Add a tiny, opt-in timing shim (env-gated, e.g. `PROFILE_REQUESTS=1`) that logs wall-time for
  `_execute`, `get_column_info`, `get_table`, and total request time. Keep it out of the hot path
  when the env var is unset (a cheap `if` guard). This is scaffolding, not a feature — it can live
  in a `perf/` helper imported only when profiling.
- Write a small repeatable benchmark script (scratchpad or `perf/`) that drives the target flows
  against a warm process: (a) apply a filter then view 8 different columns; (b) render a Compare
  crosstab; (c) render the Visualize choropleth + scatter; (d) hit a non-data page (a lesson step)
  logged in. Record `_execute` call counts and timings per flow. **These are the before-numbers.**
- Confirm the Phase 0 golden `.bin` snapshot still exists (memory: `MAST\phase0-golden`) and that
  `test_base_immutability.py` + `test_map_filter_equivalence.py` pass on this branch. That golden
  set is Phase 5's oracle.

**Acceptance:** before-numbers captured for all four flows; both guardrail tests green; timing
shim is a no-op when unset.

**Don't:** don't optimize anything yet. Don't leave the timing shim running unconditionally.

**Profile & discover:** the call-count table alone will confirm the "N executes per flow" claims
below and probably surface one or two more. Log them in Appendix B.

---

## Phase 1 — Cache-neutral I/O reclamation · effort S · risk low · **Sonnet ultracode**

The cheapest wins: stop re-reading things that don't change within a request or a process. None
of this alters any computed output or cache key.

**Read first:** `app.py` (`inject_globals`, `render_explore`, `build_column_browser`,
`current_user`), `account.py` (`retrieve` and every writer), `lessons.py` (`list_modules`).

**Do (three independent sub-changes, land separately):**
1. **Per-request `account.retrieve` memo.** `retrieve(session['userid'])` unpickles the user file
   4–6× on a single explore render (once in `render_explore`, again inside each `get_data` →
   `_execute` for the history, again in `inject_globals`). Memoize per request in `flask.g` keyed
   by userid (`from flask import g`). **Invalidate on write:** every route that calls
   `history_add` / `history_revert` / `set_progress` / etc. must not serve a stale `g` copy
   afterward — simplest is for the writer helpers to drop the `g` entry (or only cache in `g`
   inside the GET data path). Prove no write route reads a stale account post-write.
2. **Memoize `build_column_browser`.** Its output derives only from the full column list + the
   codebook, both process-constant (filters never drop columns). Build it once per process (or
   cache on the `data['column_list']` identity). Runs on every explore/filter/compare render today.
3. **Memoize `lessons.list_modules`.** It re-reads and re-parses every `lessons/*.json` on each
   call (catalog, dashboard, deep links). Memoize with an mtime/dir-signature check so authored
   edits still show up without a restart.

**Acceptance:** column-view render issues **one** `retrieve` disk read, not 5–6; `_data.bin` /
`<col>.bin` bytes unchanged (diff against golden); a filter-apply → next page shows the correct
new count (no stale `g`); editing a lesson JSON still updates the catalog without restart.

**Don't:** don't cache the account in a module global (it's mutable per-user state — request scope
only). Don't memoize `build_column_browser` on `data` object identity if `data` is rebuilt per
request (key on the column tuple instead).

**Profile & discover:** re-run the Phase 0 benchmark; the non-data-page flow (d) should drop
noticeably from the `retrieve` memo alone. Note the residual — Phase 2 attacks it.

---

## Phase 2 — Sidebar badge without a replay · effort S · risk low · **Opus xhigh**

`inject_globals` ([app.py:181](app.py:181)) calls `get_data(session)['entries']` on **every
logged-in page**, including lessons/admin pages that render no data. Right after a filter apply the
state is cache-cold, so the badge alone forces a full history replay — a cost `CLAUDE.md` already
flags as accepted. The filter-apply route *already computes* the remaining count for its
"N cases remain" flash; stop throwing it away.

**Read first:** `app.py` (`inject_globals`, `dataset_total`, the filter-apply handler
`explore_filter_column` and `revert`/`load`), `cache.py` (`get_data`).

**Do:**
- Persist the current filtered count where `inject_globals` can read it without a replay — the
  cleanest home is the **active history entry** (write the resulting `entries` onto it when a
  filter/revert is applied) or the session. `inject_globals` reads that cached count; only when it's
  absent (e.g. first load of an already-filtered account) does it fall back to `get_data`.
- Keep `_data.bin` as the source of truth on a genuine cache miss — this is a fast-path read, not a
  new cache artifact. **Do not** write the count into `_data.bin` (that would change its bytes).

**Acceptance:** applying a filter and landing on any page issues **zero** extra `_execute` calls
for the badge (verify via Phase 0 counters); the badge count always equals the real filtered
`entries`; revert/clear update it correctly.

**Don't:** don't compute the badge on pages that don't render it if you can avoid it, but never let
the badge show a stale number — correctness beats the saved replay.

**Profile & discover:** with Phases 1–2 in, the "apply filter → view N columns" flow's `_execute`
count is the headline number for Phase 3. Record it.

---

## Phase 3 — Filtered-slice memoization (the structural win) · effort M · risk med · **Opus ultracode**

This is the core issue. Lever B memoized the **base**; every cache-miss on a *filtered* state still
replays the whole filter chain from the base. Two concrete costs:

- **N column views = N identical rebuilds.** Viewing 8 columns of one filter state is 8 requests,
  each `get_data(session, col)` → `_execute` replays the same filter chain from the base again.
- **Double replay within one cold render.** `render_explore` calls `get_data(session)`
  ([app.py:713](app.py:713), builds `_data.bin`, execute #1) then `get_data(session, col, sort)`
  ([app.py:729](app.py:729), builds `<col>.bin`, execute #2) — two full replays for one page.

**Fix:** a small **bounded LRU of filtered slices**, keyed by the history token path, sitting right
next to `_base_df()` / `_county_crosswalk()` in `cache.py`. `_execute` computes the same token key
`get_data` already builds (`'/'.join(history_item_to_text(...))`, including any `history_override`);
on a hit it hands back the cached frame instead of re-filtering. Cap it (e.g. 8 entries) so memory
stays bounded — each slice is a row-subset far smaller than the base, and category columns share
their category index with the base.

**Read first:** `cache.py` (`_execute`, `_base_df`, `get_data`, `get_aggregate`,
`get_moc_options`), `data.py` (`filter`, `aggregate_by_group`, `get_table`),
`test_base_immutability.py`.

**Do:**
- Add `_filtered_cache` (an `OrderedDict`/`functools.lru_cache`-style LRU) in `cache.py`. Key =
  the full history token tuple (base excluded, override included). Value = the filtered `df`.
- In `_execute`, after building the token key, return a `Data` whose `.df` is the cached slice when
  present; otherwise filter as today and insert the result. **Hand out the shared frame the same
  way `_base_df` does** — assign to a fresh `Data().df`; callers must treat it read-only (they
  already do: `filter(inplace=False)`, `aggregate_by_group(source=...)`, `get_table` all produce
  new frames).
- Mirror the base's debug-only tripwire: assert a cached slice's shape/identity hasn't drifted
  between hits (catches an accidental in-place mutation).
- The base entry keeps pointing at `_base_df()` (an empty-history state is the base itself — don't
  double-cache it).

**This subsumes Phase 3's double-replay for free**: the second `get_data` in `render_explore` hits
the slice cache instead of re-filtering. `get_aggregate`, `build_choropleth`
([app.py:2044](app.py:2044)), and `get_moc_options` all ride `_execute`, so they benefit too.

**Extend the guardrail:** add a case to `test_base_immutability.py` that (a) executes a filtered
state twice and asserts the second is served from cache and byte-identical, and (b) asserts a
cached slice is unchanged after a full `get_column_info` / `get_table` / `aggregate_by_group` pass
over it.

**Acceptance:** "apply filter → view 8 columns" drops from ~8–9 `_execute` calls to **1**; a cold
column render drops from 2 replays to 1; `test_base_immutability.py` (extended) green; all `.bin`
bytes unchanged vs. golden; memory ceiling bounded and measured (LRU size × typical slice).

**Don't:** don't cache by the mutable `Data` object — cache the `df` and wrap per call. Don't make
the LRU unbounded (a session could walk many states). Don't key on anything but the canonical token
path, or a slice could be served for the wrong state (this is the same failure mode
`test_map_filter_equivalence.py` guards for cache dirs — silent and plausible).

**Profile & discover:** this is the phase most likely to expose the *next* bottleneck once replays
collapse — likely `get_column_info` itself (Phase 5) now dominates a cold column view. Confirm and
log.

---

## Phase 4 — Vectorize the crosstab (`get_table`) · effort M · risk med · **Opus xhigh**

`get_table` ([data.py:354](data.py:354)) is nested Python loops: for every (x, y) cell it does
`filter(x==ix)` then `filter(y==iy)` — an O(cells) sweep of boolean-index passes. It is **never
disk-cached** (crosstabs compute fresh, by design), so *every* Compare view, every lesson `table`
step, and every Visualize **scatter** (`build_scatter` reads a `get_table` sheet,
[app.py:1881](app.py:1881)) pays it live, on every request.

**Fix:** replace the nested loops with a single grouped aggregation —
`df.groupby([x_col, y_col], observed=True)[d_col].agg(['size', 'mean', 'median', 'std'])` (or
`size()` alone when `d_col` is None) — then reshape into the same nested `sheet[x][y]` dict the
callers expect. Not cached ⇒ **no `.bin` compat risk**; the only bar is exact display parity.

**Read first:** `data.py` (`get_table`, `filter`, the rounding idiom), `app.py` (`build_crosstab`,
`build_scatter`, `crosstab_csv`, `render_compare`), the "Crosstab X/Y orientation" gotcha in
`CLAUDE.md`.

**Do:**
- Reproduce the current contract exactly: `sheet[x][y] = {'N': ...}` and, when a measure is set,
  `'mean' | 'mdn' | 'std'` as **the same rounded strings** (`round(v*10**p)/10**p`) with the
  **`'N/A'` sentinel** when the aggregate is NaN. Preserve the same NaN-key rows/cols (they're
  dropped downstream by `build_crosstab`, but `get_table` currently emits them — match that).
- Keep x-as-rows / y-as-columns orientation and the arg names (`d_col, x_col, y_col`) — legacy URLs
  and lesson deep links depend on them.
- Watch `std`: pandas `groupby.std()` is sample std (ddof=1) — confirm it matches the current
  per-cell `Series.std()` (it does; both ddof=1) so numbers don't shift.

**Acceptance:** for a representative set of crosstabs (count-only and with a measure, small and
large, including cells with 1 row where std is NaN → `'N/A'`), the reshaped `sheet` equals the
current `get_table` output **cell for cell** (write a throwaway equivalence check); Compare view,
CSV export, and scatter all render identical numbers; measured speedup on the Compare/scatter flow.

**Don't:** don't change orientation, arg names, rounding, or the `'N/A'` sentinel. Don't drop NaN
keys inside `get_table` (that's `build_crosstab`'s job — moving it would change scatter/CSV).

**Profile & discover:** scatter's lattice guard (`distinct_counts` / `SCATTER_MAX_CELLS`) exists
because the old path was O(cells); note whether the groupby makes a higher cap safe (a product
decision — log it, don't change it here).

---

## Phase 5 — Vectorize per-column stats (`num_each`) · effort M · risk **high (cache bytes)** · **Fable xhigh**

`num_each` ([data.py:450](data.py:450)) is O(n·k): for each of the column's k unique values it
calls `num_occur = len(col[col == val])`, a full 294k-row scan **per unique value**. This is the
heart of `get_column_info`, run on every column cache-miss — and after Phase 3 collapses the
replays, it's likely the top cost of a cold column view. `col.value_counts(dropna=False)` computes
the identical mapping in a single O(n) pass.

**Why this is last and gated:** `get_column_info`'s output is pickled into `<col>.bin`. The dict
`raw_numbers` is later re-sorted by count, but its **insertion order is serialized**, and
`value_counts` orders ties differently from the current `unique()`-then-`sorted(by value)` path.
Different order ⇒ different pickle bytes ⇒ the golden-snapshot check fails even though every
displayed number is identical. So this phase touches Global Constraint 1 head-on.

**Read first:** `data.py` (`num_each`, `num_occur`, `get_column_info`, `format_column_info`),
`cache.py` (`get_data`'s `<col>.bin` write, `cache_info`), the "Cached pickles" gotcha in
`CLAUDE.md`, the Phase 0 golden dir.

**Do — pick one, decide explicitly with the author:**
- **(a) Order-preserving swap.** Replace the `num_occur` loop with `value_counts(dropna=False)` but
  re-impose the *current* dict ordering before it's stored, so `<col>.bin` bytes are unchanged and
  the golden check passes as-is. Lowest blast radius, keeps the cache valid.
- **(b) Swap + re-warm.** Take the natural `value_counts` order, accept the `.bin` bytes change,
  **re-generate the golden snapshot and the shipped cache** (`cache.py`'s `cache_info`), and update
  the immutability oracle. Cleaner code, but it invalidates every existing `cache/data/*` and the
  golden set — a deliberate, documented reset, not a silent one.

Either way: assert the **displayed** stats (mean/median/std/mode/mode_extra, nan line, per-value
counts and percents) are identical to the pre-change output across a sample of low- and
high-cardinality columns.

**Acceptance:** `get_column_info` timing on a high-cardinality column drops from O(n·k) to ~O(n)
(measure a wide column); chosen path's cache-compat story holds — (a) golden bytes unchanged, or
(b) golden re-warmed and both guardrail tests updated + green; all displayed numbers identical.

**Don't:** don't ship this without resolving the byte-identity question first — a silent `.bin`
drift is exactly the failure the cache culture exists to prevent. Don't change `float64` handling
or the mode tie-count logic.

**Profile & discover:** with 3–5 landed, re-run every Phase 0 flow and record the after-numbers.
Anything still hot goes to Appendix B for a possible round two.

---

## Appendix A — Change ledger (for the CLAUDE.md update at the end)

| # | Change | File(s) | Cache bytes? | Guardrail |
|---|--------|---------|--------------|-----------|
| 1a | Per-request `retrieve` memo (`flask.g`) | `app.py` | neutral | manual: post-write freshness |
| 1b | Memoize `build_column_browser` | `app.py` | neutral | — |
| 1c | Memoize `lessons.list_modules` (mtime) | `lessons.py` | neutral | edit-still-shows check |
| 2 | Badge count without replay | `app.py` | neutral (not in `.bin`) | badge == real entries |
| 3 | Filtered-slice LRU | `cache.py` | neutral | `test_base_immutability.py` (extended) |
| 4 | `get_table` → groupby | `data.py` | n/a (never cached) | cell-for-cell equivalence |
| 5 | `num_each` → `value_counts` | `data.py` | **changes unless order-preserved** | golden `.bin` |

At the end, fold a "Done: request-path optimization" section into `CLAUDE.md` (mirroring the
"Done: base DataFrame optimization" section) and note the new LRU next to `_base_df`/`_county_crosswalk`
in the module map.

## Appendix B — Candidate leads found but not scheduled (the "keep looking" list)

Discovered while reading; **not** in the phase plan above. Re-evaluate with the Phase 0 profiler
before committing to any — several may not be worth the risk at this app's scale.

- **`get_moc_options`** ([cache.py:154](cache.py:154), [data.py:317](data.py:317)) re-executes the
  filter chain and runs many `filter_moc` passes on a cold `_moc.bin`. Phase 3's LRU removes the
  replay for free; the per-option `filter_moc` sweep could later become a single `groupby` over the
  active `mocN` slots. Low traffic — measure before touching.
- **`filter_or_same`** ([data.py:114](data.py:114)) does `pd.concat(...).drop_duplicates()` across
  per-value filters. For the common `eq` OR-multiselect this is exactly `col.isin(values)` — one
  pass, no concat/dedup. Cache-neutral (same rows selected) but verify row order into the cache key
  doesn't matter (it shouldn't — cache keys off the token, not row order).
- **`build_class_dashboard`** ([app.py:2985](app.py:2985)) is a clean O(roster) N+1 (one pickle +
  one JSONL per student). Already careful (reads each once, folds pure aggregators). Fine at
  classroom scale (dozens); only worth attention if rosters ever get large. The Phase 1 `retrieve`
  memo does **not** help here (distinct users).
- **`get_column_info` recomputes `len(column.unique())` and `column.mode()`** on top of the value
  counts — once `num_each` is `value_counts` (Phase 5), the unique count and modal values can be
  derived from it without extra full passes.
- **Directory creation in `get_data`** ([cache.py:103](cache.py:103)) walks and `os.mkdir`s per
  history step on a miss — negligible, listed only for completeness.
- **Correlation `pair_n`** ([app.py:1830](app.py:1830), `present.T.dot(present)`) is already
  vectorized and fine; noted so a future reader doesn't "optimize" it needlessly.

---

## Suggested execution order & sizing

Phases are in dependency order. **1 → 2 → 3** are the safe, high-leverage core (do these first;
3 is the big one). **4** is independent of 1–3 and can land in parallel. **5** is last and needs an
explicit cache-compat decision. Ship each phase as its own commit with its before/after numbers in
the message. Land Phase 0's profiler first and never skip a phase's "profile & discover" step —
that's the "search for more optimizations along the way" the plan is built around.
