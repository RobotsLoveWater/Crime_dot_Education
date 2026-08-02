# Base DataFrame Optimization — Implementation Prompts

> **Status: all phases (0–4) are DONE** (2026-07-06, `base-df-optimization` branch), each verified
> byte-identical against the Phase 0 golden `.bin` snapshot with the `test_base_immutability.py`
> guardrail passing throughout. Measured results are in `BASE_DATAFRAME_OPTIMIZATION.md` §0
> (headline: base RAM ~8× down, cold base load 4.2 s → 0.25 s, disk 231 → 23 MB, one CoW-shared
> copy across workers). The prompts below are kept as the build record.

Sequenced, self-contained prompts for the runtime memory/latency optimization of the data
layer: **load the base dataset once, shrink it, and share it across workers** — so the app
stops re-parsing a 242 MB CSV into a ~1.85 GB DataFrame on every cache miss, in every worker.
Feed **one phase at a time** to a fresh Claude instance (or use as a dev checklist). Each phase
should end green before the next starts.

Read **`BASE_DATAFRAME_OPTIMIZATION.md`** (the design/scope authority) first for the rationale,
the measured numbers, the safety argument, and the expected impact. This file is the *build
order*; that file is the *why*.

## How to use this file

- Do the phases **in order** — later phases assume the earlier ones exist.
- Each prompt names the files to read, what to build, and how to know it's done. Keep the
  "Global constraints" below in scope for every phase.
- After each phase: rebuild the environment / warm a cache, diff outputs against the Phase 0
  baseline, run the app, commit, then move on.
- **Phases 1–2 are the self-contained win** (no re-parse + ~3× per-worker RAM cut). Ship and
  evaluate them before deciding whether 3–4 are worth it for the target box.

## Global constraints (apply to every phase)

- **Results must not change.** Explore stats, crosstab cells, and MOC option counts must stay
  identical to pre-change output for a representative filter chain. This is enforced by diffing
  the generated `cache/data/**.bin` files against the Phase 0 baseline.
- **Cache keys must not change.** The disk cache is content-addressed by the history tokens
  (`cache.history_item_to_text`). Nothing here touches history encoding or the cache-dir layout;
  a warm `cache/data/` from before the change stays valid (and is safe to delete + regenerate if
  ever in doubt).
- **Numeric columns stay `float64`.** Three sites branch on exactly `float64`
  ([data.py:78](data.py:78) filter coercion, [data.py:246](data.py:246) numeric stats,
  [data.py:329](data.py:329) `get_numeric_columns`). Only **string** (`object`) columns may be
  re-typed. Do not downcast floats — it would both break those checks and perturb cached means/std.
- **The base DataFrame is immutable — keep it that way.** No code in `data.py` mutates `self.df`
  in place (no `inplace=`, `.drop`, `.fillna`, `astype` assignment, or column assignment); every
  filter returns a new frame. The whole optimization rests on this. Never hand out the shared base
  for mutation.
- **This repo is Windows.** Verify commands in PowerShell (or the Bash tool for POSIX). `.venv/`,
  `cache/`, `user/`, `classes/`, and `dataset.sav` are git-ignored and must stay that way.
- **Each phase is independently revertible** with no data migration (see the proposal's Rollback
  section). Commit per phase.

---

## Phase 0 — Baseline & guardrails (no behavior change) ✅ DONE

*(Baseline: 294,467 × 176; 116 object / 59 float64 / 1 int64; deep RAM 1,845,407,290 B. Golden
snapshot + `BASELINE.md` live outside the tree; `test_base_immutability.py` is committed.)*

**Goal:** capture the current numbers and lock in the immutability property so every later phase
can prove it changed nothing.

**Read first:** `BASE_DATAFRAME_OPTIMIZATION.md`, `cache.py` (`_execute`, `get_data`), `data.py`
(`load`, `filter`, `get_column_info`, `get_numeric_columns`).

**Build:**
- A throwaway bench script (scratch, not committed) that loads `cache/raw.csv` via `Data.load`
  and records: rows × cols, dtype counts, `df.memory_usage(deep=True).sum()`, and wall-clock
  load time. Record the results in the phase's commit message / a scratch note.
- A **golden-output snapshot**: pick a representative filter chain (e.g. a numeric `f.` filter, a
  categorical `o.` OR filter, and a MOC drill-down), warm the cache for it, and copy the produced
  `cache/data/**.bin` somewhere outside the tree as the reference for later diffs.
- A small test (or scripted check) asserting the base DataFrame is **unchanged** (same shape,
  same `id` if shared, same values on a spot-checked column) after a representative filter chain
  runs through `_execute`.

**Acceptance:** baseline memory/time numbers recorded; golden `.bin` snapshot saved; the
immutability check passes on the current code.

**Don't:** change any runtime behavior yet.

---

## Phase 1 — Lever A: categorical string columns (the RAM win) ✅ DONE

*(Measured ~8× — 1.72 GiB → 0.215 GiB; golden diff clean; floats untouched.)*

**Goal:** cut the resident base ~2.5–3.5× by re-typing the 116 `object` columns to `category`,
with byte-identical results.

**Read first:** Phase 0 output, `data.py` `load` ([data.py:158](data.py:158)) and the three
`float64` sites.

**Build:**
- In `Data.load`, after the read, cast `object`-dtype columns to `category` and **leave numeric
  dtypes untouched** (do not touch `float64`/`int64`). Keep it a single, obvious, commented step.
- Verify equality filtering on a categorical column (`eq`/`ne`) returns the same rows as before
  (categoricals only ever get eq/ne — numeric comparisons are numeric-column-only).

**Acceptance:** re-warming the Phase 0 filter chain produces `.bin` files that **diff clean**
against the golden snapshot; `memory_usage(deep=True)` is down ≥2.5×; the three `float64` checks
still fire (numeric stats + numeric-column picker unaffected).

**Don't:** downcast floats; change `get_numeric_columns`; alter `codebook.xml` or cache encoding.

---

## Phase 2 — Lever B: load the base once per process ✅ DONE

*(`cache._base_df()` singleton; base reuse ~1 µs after first load; exactly one base-sized frame
alive across 60 builds; golden diff clean.)*

**Goal:** stop re-parsing the CSV on every cache miss — hand `_execute` a memoized base.

**Read first:** Phase 1 output, `cache.py` `_execute` ([cache.py:188](cache.py:188)) and
`get_data`.

**Build:**
- A module-level singleton in `cache.py` (e.g. a `_base_df()` helper / lazy global) that loads
  the base DataFrame **once** and returns it. `_execute`'s base-load branch
  ([cache.py:220](cache.py:220)) uses it instead of `temp_data.load(DATAFILE)`; because the base
  is immutable, the first filter replaces the reference with a new frame.
- A defensive debug-only assert that the base's shape/identity is intact between requests (catches
  any accidental in-place mutation regression).

**Acceptance:** the Phase 0 filter chain still diffs clean; a cold request no longer re-parses the
CSV (base-load time ≈ 0 after the first load in that process); memory does not grow request over
request.

**Don't:** cache anything history-specific in memory (the disk cache already owns that); don't
share a mutable frame.

---

## Phase 3 — Lever C: Parquet base (faster first load, smaller disk) ✅ DONE

*(231 MiB → 23 MiB on disk; cold load 4.2 s → 0.25 s; `DATAFILE` prefers `raw.parquet`, CSV loader
kept as fallback; 4 mixed-type category columns stringified — see the design doc §0; golden diff
clean from Parquet.)*

**Goal:** replace the 242 MB CSV base with a typed, columnar Parquet file so the first load is
fast and disk shrinks to ~60–90 MB.

**Read first:** Phase 2 output, `cache.py.__main__` ([cache.py:234](cache.py:234)),
`data.py` `load`/`save`, `deploy/setup.sh`, `CLAUDE.md` "Data flow / bootstrap".

**Build:**
- In `cache.py.__main__`, emit `cache/raw.parquet` (categoricals + `float64` preserved) alongside
  or instead of `raw.csv`.
- Add a `.parquet` branch to `Data.load` and point `DATAFILE` at it; **keep the CSV loader as a
  working fallback**.
- Update `deploy/setup.sh` (cache-build step) and the bootstrap note in `CLAUDE.md` and
  `deploy/README.md`.

**Acceptance:** the Phase 0 filter chain diffs clean loading from Parquet; first-load time is
lower than the CSV parse; `cache/raw.parquet` is materially smaller than `raw.csv`; the CSV path
still works if `DATAFILE` is repointed.

**Don't:** commit `raw.parquet` (git-ignored data, like `raw.csv`); drop the CSV loader.

---

## Phase 4 — Lever D: share the base across workers (`--preload`) ✅ DONE

*(Import-time warm in `app.py` — guarded, falls back to lazy load; `--preload` in the systemd
`ExecStart`; ~79% of the base is CoW-shareable numpy; 3 independent copies measured ~2.16 GB,
collapsed toward one by `--preload`. Final shared-PSS confirmation is a Linux-target measurement —
recipe in `deploy/README.md`.)*

**Goal:** collapse `WORKERS × base` down to ~one shared copy by loading before fork.

**Read first:** Phase 3 output, `deploy/setup.sh` systemd `ExecStart`
([setup.sh:189](deploy/setup.sh:189)), the proposal's Lever D + risks.

**Build:**
- Ensure the base loads at import time (Phase 2's singleton) so it exists in the gunicorn master.
- Add `--preload` to the systemd `ExecStart`. Document that workers now share the base
  copy-on-write (categoricals from Phase 1 make this hold — numpy code-arrays, not per-cell
  Python objects).
- Measure resident RAM across 3 workers and confirm it is far below `3 × base`.

**Acceptance:** with `--preload`, total resident base RAM ≈ one copy shared by all workers; the
app serves correctly; if CoW sharing underperforms, fall back to Phase 2's per-worker load-once
(still a large win) without reverting anything else.

**Don't:** rely on sharing for `object`-dtype columns (that's why Phase 1 comes first); don't add
worker-shared mutable state.

---

## Done criteria (whole effort)

1. Base `memory_usage(deep=True)` reduced ≥2.5× vs. Phase 0.
2. Explore stats, crosstab cells, and MOC counts **identical** to pre-change (`.bin` diffs clean).
3. Cold-request wall-clock materially lower (base load no longer the dominant cost).
4. With `--preload`, total resident RAM across workers far below `WORKERS × base`.
5. No change to routes, cache-dir layout, or the history schema.

The target outcome: the box sizing in the deploy notes drops from **4 vCPU / 8 GB** to a
comfortable **1 vCPU / 2 GB** for a half-dozen concurrent users.
