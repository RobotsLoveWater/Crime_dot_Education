# Phase 0 baseline — Request-path optimization

Measured "before" numbers for `REQUEST_PATH_OPTIMIZATION_PROMPTS.md`'s Phase 0, captured with
the timing shim (`perf/profiling.py`) and the repeatable benchmark (`perf/benchmark.py`), both
committed to the repo (unlike the base-df work's golden scripts, which live outside the tree —
this is measurement scaffolding for an in-progress optimization, not a byte-identity oracle).

- **Date:** 2026-07-09
- **Host:** Minos (Windows 11), Python 3.13.14, pandas 2.3.0, numpy 2.3.1
- **Branch:** `optimizations-minor`
- **Base datafile:** `cache/raw.parquet` (Lever C)
- **Method:** Flask `test_client()` against the real app (real routes/templates/session),
  driving requests in-process. A dedicated benchmark account (`perf-bench/bench`) is
  created once and reused; each flow resets that account's history to the base entry first.
  `PROFILE_REQUESTS=1` gates the shim (set automatically by the script).

Run: `uv run python -m perf.benchmark` from the repo root.

## How to reproduce a genuinely cold run

Flows (b)/(c) exercise `_execute`/`get_table`/`aggregate_by_group` **directly** (bypassing
`get_data`'s disk cache — crosstabs and Visualize aggregates are never disk-cached by design),
so they're cold on every run with no extra effort. Flow (a) rides `get_data`'s disk cache
(keyed by history token), so the script clears its target `cache/data/f.time.gt.14/` directory
before running it — confirmed this makes the flow reproducible: two back-to-back runs before
this fix went 554ms → 60ms (9 `_execute` calls → 0) purely from cache reuse; after clearing the
directory first, three consecutive runs landed at 535–555ms / 9 execute calls each time.

## Results (3 consecutive runs, cold cache each time)

| Flow | requests | wall time | `_execute` | `get_column_info` | `get_table` |
|---|---|---|---|---|---|
| (a) filter + view 8 columns | 9 | 535–555 ms | **9 calls, ~342–355 ms total** | 8 calls, ~76–77 ms | — |
| (b) Compare crosstab (`time × sex × race`) | 1 | 207–216 ms | 1 call, <1 ms | — | **1 call, ~196–205 ms** |
| (c) Visualize choropleth + scatter | 2 | 1597–1608 ms | 2 calls, ~1 ms | — | **1 call, ~1530–1540 ms** (scatter) |
| (d) non-data lesson-step page (`/lesson/intro-explorer-basics/0`) | 1 | 22–24 ms | 0 calls | — | — |
| *(discovery)* cold column view, `_data.bin` + `<col>.bin` both missing | 1 | ~109 ms | **2 calls, ~42–43 ms total** | 1 call, ~52 ms | — |

## Reading these numbers

- **Flow (a) confirms the "N column views = N rebuilds" claim.** 9 requests → 9 `_execute`
  calls. Each column view (`/explore/column/<col>`) costs one `_execute` (~39–43 ms) even
  though the filtered `_data.bin` was already warmed by the filter-apply POST's own
  "remaining cases" count — the *column*-specific `.bin` is still a fresh miss every time.
  This is exactly Phase 3's target: collapsing 8 rebuilds of the identical `f.time.gt.14`
  slice down to 1.
- **The literal "double replay in one page render" (render_explore's two `get_data()` calls,
  `app.py` ~713/~729) does NOT show up in flow (a)** — because the filter-apply POST's
  `remaining = get_data(session)['entries']` call (app.py:1214-ish, in `explore_filter_column`)
  already warms `_data.bin` for that history token as a side effect, so by the time a column
  view lands, only the column-specific `get_data` call is a cache miss (1 `_execute`, not 2).
  The **(discovery)** row isolates the true cold case — a column view where *neither*
  `_data.bin` nor `<col>.bin` has ever been built (e.g. a lesson deep link or bookmark
  straight into an unvisited filtered state) — and there it's 2 `_execute` calls in one
  request, confirming the claim as written but narrowing when it actually fires in practice.
- **`get_table` is the dominant cost in both (b) and (c).** ~200 ms for an 8×~9-cell
  count+mean+median+std crosstab (`time × sex × race`), and **~1.5 s** for the scatter's
  lattice build (`time × history`, wider cardinality). This lines up with Phase 4's diagnosis
  (`get_table`'s nested per-cell `filter()` calls) and suggests the scatter path is currently
  the single most expensive thing measured in this pass — worth flagging for Phase 4's
  "profile & discover" (a `SCATTER_MAX_CELLS` cap exists specifically because this path is
  O(cells); the groupby rewrite may make a higher cap viable, a product call for later).
- **Flow (c)'s `_execute` calls are near-free (~1 ms)** because the account's history is just
  the base entry at that point — `_execute` for an unfiltered state is a single dict lookup
  into the already-loaded `_base_df()` singleton (Lever B), not a re-parse. The real cost in
  this flow is entirely in the *aggregation/crosstab* layer on top, not the base.
- **Flow (d) touches no data path at all** (0 `_execute` calls) — confirms lesson `read` steps
  are cheap today; `inject_globals`' badge computation (Phase 2's target) is the only
  per-request data cost on a page like this, and it's cache-hit-cheap once the account's
  current state has been viewed once (not separately isolated here; see Appendix B below).

## Guardrail tests

Both green on this branch, unaffected by the timing shim (no-op when `PROFILE_REQUESTS` is
unset) and unaffected by the benchmark's cache-directory churn (`cache/data/f.time.gt.14/` and
`cache/data/f.history.gt.3/` are runtime cache dirs inside `v1/`, distinct from the golden
snapshot at `MAST/phase0-golden/`, which the benchmark never touches):

```
uv run python test_base_immutability.py        # PASS (both checks)
uv run python test_map_filter_equivalence.py    # PASS (all 5 checks)
```

## Files

- `perf/profiling.py` — the timing shim: `@timed('label')` decorator (fully unwrapped,
  zero overhead, when `PROFILE_REQUESTS` is unset) + a `span()` context-manager twin;
  thread-local per-request counters; `REQUEST_LOG` (populated by `app.py`'s
  before/after_request hooks) so a benchmark can aggregate call counts across several
  requests in one flow.
- `perf/benchmark.py` — the repeatable driver for the four flows above (plus the discovery
  check). Re-run this same script after each later phase and diff against this table.

## After-numbers — all phases landed (recorded at Phase 5 close-out, 2026-07-09)

Same script, same host, same 3-consecutive-cold-runs method as the baseline table above,
with Phases 1–5 all applied. One reading note: since Phase 3 the `_execute` counter wraps
`_replay_history` (the LRU-miss path only), so it now counts **real history replays** — the
baseline's "(b)/(c) 1–2 calls, ~1 ms" rows were base-state lookups that the counter no longer
tallies (0 below means zero replays, not a missing measurement).

| Flow | wall before | wall after | replays before → after | notes |
|---|---|---|---|---|
| (a) filter + view 8 columns | 535–555 ms | **135–156 ms** | 9 → **1** (P3) | `get_column_info` 8 calls: ~76 ms → **~24 ms** (P5) |
| (b) Compare crosstab | 207–216 ms | **38–45 ms** | 0 real replays | `get_table` ~200 ms → **~28 ms** (P4) |
| (c) Visualize choropleth + scatter | 1597–1608 ms | **88–104 ms** | 0 real replays | scatter `get_table` ~1.5 s → **~20 ms** (P4) |
| (d) non-data lesson-step page | 22–24 ms | 23–28 ms | 0 → 0 | already cheap; unchanged (noise) |
| (discovery) cold column view | ~109 ms | **40–49 ms** | 2 → **1** (P3) | `get_column_info` ~52 ms → **~4 ms** (P5) |

**Phase 5 micro-benchmark** (the `num_each` O(n·k) → O(n) swap, measured by the byte-identity
oracle over all 170 non-excluded columns): `get_column_info` totals 22.92 s → 0.96 s (base
state, 23.8×) and 15.92 s → 0.72 s (`f.time.gt.14`, 22.0×); the worst column, `moc`
(11,475 uniques), went 4.22 s → 9 ms (~446×). Byte-identity verified the order-preserving
way: all 372 snapshot files (`<col>.bin` pickles for both states + formatted display output
for 16 sample columns × 5 sortings) byte-identical before/after, plus an old-loop-vs-new
equivalence check on the `Unnamed: 0` all-distinct shape (infeasible to snapshot under the
old path — ~a day of scans — and unreachable from any route since it has no codebook entry).
Both guardrail tests re-run green after the swap.

## Appendix B candidates confirmed / refined by this pass

(Cross-reference: `REQUEST_PATH_OPTIMIZATION_PROMPTS.md` Appendix B.)

- The plan's `get_table` cost claim is **understated for the scatter path specifically** —
  1.5 s for one scatter render on this dataset is worse than the ~200 ms crosstab case, purely
  from cardinality (`time × history` has more distinct value pairs than `time × sex × race`).
  Worth a note for Phase 4: measure the scatter case specifically as the upper bound, not just
  the Compare crosstab.
- The "double replay" framing in the Phase 3 write-up is accurate for the code shape but the
  benchmark shows it's **conditionally masked** by the filter-apply route's own count query in
  the common apply-then-browse flow — it still fires for cold direct navigation (deep links,
  bookmarks, lesson `explore` steps into a state the account hasn't visited before). Phase 3's
  fix (the filtered-slice LRU) removes the cost either way, so this doesn't change the plan —
  just narrows the "why" for the commit message.
