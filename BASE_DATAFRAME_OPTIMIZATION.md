# Base DataFrame Optimization (load-once, shrink, share)

**Status:** **IMPLEMENTED — all four levers (Phases 0–4), 2026-07-06, `base-df-optimization` branch.**
**Author of proposal:** Claude (for Sidney D. Allen)
**Date:** 2026-07-06 (proposed and built)
**Scope:** runtime memory + cold-request latency of the data layer (`cache.py` / `data.py`).
No change to features, URLs, cache keys, or the history/cache substrate.

## 0. Measured outcome (what actually landed)

Every phase was verified **byte-identical** against the Phase 0 golden `.bin` snapshot, and the
`test_base_immutability.py` guardrail passes throughout. Measured on the dev machine:

| | Before (Phase 0 baseline) | After (Levers A–D) |
|---|---|---|
| Base deep RAM per copy | 1,845,407,290 B (~1.72 GiB) | 231,380,458 B (~0.22 GiB) — **~8×**, beat the 2.5–3.5× estimate |
| Base load, cold process | ~4.2 s (242 MB CSV parse) | **~0.25 s** (Parquet) — then **~1 µs** per reuse (singleton) |
| Base on disk | 231 MiB `raw.csv` | **23 MiB** `raw.parquet` (~10×; CSV kept as fallback) |
| Base copies across workers | one per worker (`WORKERS ×`) | ~one, shared CoW via `--preload` (~79% of the base is shareable numpy) |

Where each lever lives: **A** — `Data.load` casts `object` → `category` ([data.py](data.py));
**B** — `cache._base_df()` module singleton + debug-only shape/id tripwire ([cache.py](cache.py));
**C** — `Data.save_parquet` + `.parquet` load branch; `cache.DATAFILE` prefers `cache/raw.parquet`,
falls back to `raw.csv`; built by `cache.py.__main__`'s new third prompt; **D** — import-time
`cache._base_df()` warm in [app.py](app.py) + `--preload` in `deploy/setup.sh`'s `ExecStart`.
One deviation from the plan as written: Parquet requires one type per column, so `save_parquet`
stringifies 4 mixed-type category columns (`Statute_Chapter`, `Statute_Subdivision`,
`presumptlifeid`, `ssection` — `read_csv` inference artifacts; none golden/excluded). The
sections below are the original proposal, kept as the design rationale.

---

## 1. Problem

The runtime has **no shared in-memory dataset**. Every request that misses the disk
cache rebuilds the full dataset from scratch:

- `cache._execute()` ([cache.py:188](cache.py:188)) creates a fresh `Data()` and, for the
  base history entry (`action: None`), calls `temp_data.load(DATAFILE)`
  ([cache.py:220](cache.py:220)).
- `Data.load()` ([data.py:158](data.py:158)) runs `pd.read_csv('cache/raw.csv')`
  ([data.py:169](data.py:169)) — a **242 MB text parse** — then filters are applied on top.

**Measured cost of that base load** (this machine, `cache/raw.csv`):

| Metric | Value |
|---|---|
| Rows × columns | 294,467 × 176 |
| Column dtypes | 116 `object` (string), 59 `float64`, 1 `int64` |
| CSV on disk | 242 MB |
| **Deep RAM once loaded** | **~1.85 GB** |
| CSV→RAM expansion | ~7.6× |

The 116 `object` (string) columns are the memory hogs: each cell is a separate Python
`str` object.

**Consequences at deploy time** (`deploy/setup.sh` defaults to `WORKERS=3`,
[setup.sh:32](deploy/setup.sh:32)):

1. **Time:** every cold request re-parses 242 MB of CSV (~3–8 s of single-core work)
   before it can compute anything.
2. **RAM ×  workers:** each gunicorn worker that cold-loads holds its own ~1.85 GB
   (plus transient copies during filtering). Three simultaneous cold loads ≈ 7 GB —
   which is why an 8 GB box is currently the safe floor and a 4 GB box risks the OOM
   killer.

This is pure overhead: the base load is **deterministic** — it produces the identical
DataFrame on every call. Only the filters layered on top vary.

## 2. Goals / non-goals

**Goals**
- Stop re-parsing the CSV on every cold request (attack latency).
- Shrink the resident base DataFrame well below 1.85 GB (attack per-worker RAM).
- Stop multiplying the base by worker count (attack total RAM).
- Zero change to computed results, disk-cache keys, routes, or the history model.

**Non-goals**
- Not rewriting the history→cache→dataframe substrate (it stays exactly as is).
- Not introducing a database or a background job system.
- Not changing lesson/analytics behavior.

## 3. Why this is safe: the base DataFrame is immutable in the current code

Audited `data.py`: **nothing mutates `self.df` in place.** There is no `inplace=True`
pandas call, no `.drop(...)`, no `.fillna(...)`, no `astype` assignment, and no column
assignment on `self.df`. Every filter (`filter`, `filter_or_same`, `filter_moc`,
[data.py:71–153](data.py:71)) produces a **new** DataFrame via boolean masking /
`concat`, and only replaces the whole `self.df` reference. All read paths
(`get_column_info`, `num_each`, `get_table`, `get_moc_options`) are read-only.

Therefore a single base DataFrame can be **cached and shared read-only** across
requests — and across worker processes — without risk of one request corrupting
another's data. This immutability is the property the whole proposal rests on; Phase 0
adds a test that locks it in.

## 4. The one hard compatibility constraint: `float64`

Three sites branch on a column being exactly `float64`:

- [data.py:78](data.py:78) — coerce the filter value to `float` so `16 == 16.0`.
- [data.py:246](data.py:246) — decide whether to emit mean/median/std.
- [data.py:329](data.py:329) — `get_numeric_columns()` (drives the Compare "Measure"
  picker and numeric filter UI).

**Implication:** the dtype optimization must **leave the 59 numeric columns as
`float64`** and only re-type the 116 **string** columns (`object` → `category`). This
keeps all three checks correct with no code change, and — because we don't touch the
floats — every cached statistic (means, std, crosstab cells) stays **numerically
identical**, so the content-addressed disk cache remains valid.

Categorical columns only ever receive `eq`/`ne` filters (numeric comparisons `gt/ge/lt/le`
are validated to numeric columns in the filter route), and pandas equality on a
`category` column against a string returns the same boolean mask as on `object`. This is
verified in Phase 1's tests, not assumed.

## 5. Design — three independent levers

Each phase is shippable on its own and compounds with the others.

### Lever A — Shrink: categorical string columns (biggest RAM win)
Convert the 116 `object` columns to `category` dtype. MN sentencing fields are
overwhelmingly low-cardinality codes (offense code, race, sex, county, disposition,
grid cell…), so `category` replaces per-row `str` pointers with a small int-code array +
a categories index.
- **Expected:** ~1.85 GB → **~500–800 MB** (a 2.5–3.5× cut; to be measured in Phase 0/1).
- Bonus: equality filtering on categoricals is faster.

### Lever B — Load once (kills the re-parse)
Memoize the base DataFrame per process. `_execute`'s base-load branch reads from an
in-process cache instead of re-parsing the file. Because the base is immutable
(§3), `_execute` can start each build from the shared base; the first filter replaces
the reference with a new frame.
- **Expected:** cold-request base cost drops from a 242 MB parse (~3–8 s) to a reference
  hand-off (~0 s after the first load in that process). Filter/stat compute is unchanged.

### Lever C — Store the base as Parquet with dtypes baked in
Build `cache/raw.parquet` (categoricals + `float64` preserved) once, in
`cache.py`'s `__main__`, alongside/instead of `raw.csv`. Add a `.parquet` branch to
`Data.load` and point `DATAFILE` at it.
- **Expected:** first-load time in each process drops further (Parquet is columnar +
  typed — no text parse, no re-categorize), and **disk shrinks 242 MB → ~60–90 MB.**

### Lever D — Share across workers (kills the ×workers multiplier)
Run gunicorn with `--preload`: load the base in the master **before** fork, so workers
share the base pages copy-on-write. With strings as categoricals (Lever A), the heavy
columns are numpy int-code arrays rather than per-cell Python objects, so CoW sharing
actually holds (the classic "refcounts dirty every string page" problem is largely
sidestepped).
- **Expected:** total base RAM ≈ **one** ~600 MB copy shared by all workers, instead of
  `WORKERS × 1.85 GB`.

## 6. Expected impact (before → after, all levers)

| | Today | After A+B+C+D |
|---|---|---|
| Base RAM per worker | ~1.85 GB | ~0.6 GB (shared) |
| Base RAM, 3 workers | up to ~5.5 GB | **~0.6 GB total** (preloaded, shared) |
| Cold-request base load | 242 MB CSV parse, ~3–8 s | ~0 s (shared) / ~0.3–0.8 s first parse |
| Base on disk | 242 MB CSV | ~60–90 MB Parquet |
| Safe RAM to provision | 8 GB | **2 GB comfortably; 1 GB viable** |
| Computed results / cache keys | — | **unchanged** |

This turns the earlier hosting recommendation (4 vCPU / 8 GB) into something that runs
comfortably on a **1 vCPU / 2 GB** VM for a half-dozen users.

## 7. Phased plan

Ordered by value-per-risk; ship and verify each before the next. **(All five phases are done —
see §0 for the measured outcome.)**

- **Phase 0 — Baseline & guardrails (no behavior change).**
  Add a small bench script that records base-load time and `memory_usage(deep=True)`.
  Add a test asserting the base DataFrame is unchanged after a representative filter
  chain (locks in the §3 immutability property). Record the current numbers.

- **Phase 1 — Lever A (categoricals at load).** In `Data.load`, after read, cast
  `object` columns to `category` (leave numeric dtypes untouched). Verify: filters,
  explore stats, crosstabs, and MOC options produce byte-identical `.bin` outputs vs.
  Phase 0; numeric checks at [data.py:78/246/329](data.py:78) still fire. Biggest RAM
  win, smallest surface area.

- **Phase 2 — Lever B (load-once memoization).** Cache the base DataFrame in a
  module-level singleton in `cache.py`; `_execute` starts from it. Add a defensive check
  (in debug) that the base's identity/shape is intact between requests.

- **Phase 3 — Lever C (Parquet base).** Emit `cache/raw.parquet` in `cache.py.__main__`;
  add a `.parquet` branch to `Data.load`; switch `DATAFILE`. Keep the CSV path working
  as a fallback. Update `deploy/setup.sh` + the bootstrap note in `CLAUDE.md`.

- **Phase 4 — Lever D (gunicorn `--preload`).** Add `--preload` to the systemd
  `ExecStart` ([setup.sh:189](deploy/setup.sh:189)) and load the base at import time.
  Measure resident RAM across workers to confirm sharing holds.

Phases 1–2 are worth doing even alone: together they remove the re-parse and cut
per-worker RAM ~3× with a handful of lines and no new files.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| A downcast changes a numeric result | Don't downcast floats — categorize **strings only**; floats stay `float64`. Phase 1 diffs `.bin` outputs. |
| A `category` column receives a numeric comparison and raises | Comparisons `gt/ge/lt/le` are already numeric-column-only; Phase 1 test covers eq/ne on categoricals. |
| Shared base mutated by a request | §3 audit + Phase 0 immutability test; share read-only, never hand out `self.df` for mutation. |
| CoW sharing erodes under refcount churn | Categoricals (Lever A) make the heavy columns numpy arrays, not per-cell objects; measure in Phase 4, fall back to per-worker load-once (Phase 2) if sharing underperforms. |
| Parquet dtype round-trip surprises | Parquet preserves `category`/`float64`; Phase 3 diffs outputs against Phase 0 and keeps the CSV loader as fallback. |
| Stale disk cache after the change | Results are unchanged by construction (floats untouched), so keys stay valid; if in doubt, `cache/data/` is safe to delete and regenerates. |

## 9. Rollback

Every phase is independently revertible:
- Phase 1: remove the categorize line.
- Phase 2: bypass the singleton (always `_execute` fresh).
- Phase 3: point `DATAFILE` back at `cache/raw.csv` (CSV loader retained).
- Phase 4: drop `--preload`.
No data migration; user pickles, classes, and the disk cache are untouched throughout.

## 10. Acceptance criteria

1. Base `memory_usage(deep=True)` reduced ≥2.5× vs. the Phase 0 baseline.
2. Explore stats, crosstab cells, and MOC counts are **identical** to pre-change for a
   representative filter chain (diff the generated `.bin` files).
3. Cold-request wall-clock time reduced substantially (target: base load no longer the
   dominant cost).
4. With `--preload`, total resident RAM across 3 workers is far below `3 × base`.
5. No change to routes, cache-dir layout, or the history schema.

## 11. Effort estimate

- Phases 1–2 (the ~3× RAM cut + no re-parse): **~half a day**, ~1 file each, low risk.
- Phases 3–4 (Parquet + cross-worker sharing): **~half a day**, touches `data.py`,
  `cache.py.__main__`, and `deploy/`.

Recommend doing **Phases 1–2 first** as a self-contained win, then evaluating whether
3–4 are worth it for the target box.
