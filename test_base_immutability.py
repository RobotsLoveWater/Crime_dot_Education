# MN Analysis of Sentencing Trends
# test_base_immutability.py
#
# Guardrail for the base DataFrame optimization (see BASE_DATAFRAME_OPTIMIZATION.md /
# OPTIMIZATION_PROMPTS.md). Locks in the property the whole proposal rests on (§3):
#
#     Running the production filter/read pipeline against a base DataFrame NEVER
#     mutates that base DataFrame in place.
#
# Because the base is immutable, later phases can memoize it and share it read-only
# across requests (and, with --preload, across worker processes). This test must keep
# passing through every phase; if a change ever mutates the shared base, it fails here.
#
# Runs standalone (`uv run python test_base_immutability.py`, prints a report and exits
# non-zero on failure). The test_* functions are also pytest-compatible if pytest is
# ever added to the env (it is not a project dependency today).
#
# Visualization-expansion (see VISUALIZATION_EXPANSION.md / _PROMPTS.md) extended the
# pipeline below with aggregate + correlation reads: the aggregate read routes through the
# real Phase 1 helper (Data.aggregate_by_group -- choropleth/waterfall/treemap/bubble values),
# and the correlation read exercises the exact df[cols].corr() shape Tier 4's correlation
# matrix now uses (app.build_correlation, Phase 13). Both prove those read shapes leave the
# shared base untouched.
#
# Chart-library expansion (see CHART_LIBRARY_EXPANSION.md / _PROMPTS.md Phase B1) added the
# two-group aggregate read (Data.aggregate_by_two -- the grouped/stacked/100%/stacked-area/
# slope/bump/mosaic/animated matrix): the same read-only contract, now over TWO group keys,
# is exercised below over the base and the cached slice. test_aggregate_by_two_matches_
# nested_oracle additionally pins the matrix cell-for-cell against a slow nested-filter
# ground truth (the O(cells) double-boolean-mask path the single groupby replaces).
#
# Phase B2 added the numpy-only distribution engine (Data.distribution_stats -- five-number
# summary + whiskers, histogram, ECDF, binned KDE per column, optionally per group; the read
# behind the wave-2 histogram/ECDF/KDE/box/violin charts). The same read-only contract is
# exercised over the base and the cached slice, and test_distribution_stats_matches_numpy_
# oracle pins every DETERMINISTIC component (five-number/whiskers/outlier counts, histogram,
# ECDF) exactly against hand-computed numpy, plus KDE by properties (unit integral, non-neg,
# shape) since it is a smoothing estimator -- and checks nothing raw-per-row is ever emitted.
#
# Phase B3 added the 2D-binning helper (Data.bin2d -- the np.histogram2d grid behind the
# pair-plot / SPLOM off-diagonal panels; capped bins, discrete columns on their natural value
# lattice). The same read-only contract is exercised over the base and the cached slice, and
# test_bin2d_matches_numpy_oracle pins the grid as a direct np.histogram2d over the returned
# edges, checks the bin cap + point conservation, and independently verifies the discrete-axis
# lattice (each bin holds exactly one distinct value) via the axis marginals.

import sys
import math
import functools

import numpy as np
import pandas as pd

import cache
import data
import make_history
from data import Data, _first_mode

# A spread of dtypes: numeric (float64) + low-cardinality categorical (object).
# 'county' is included because it's the group key the visualization-expansion
# aggregate/correlation reads below exercise (see VISUALIZATION_EXPANSION.md §6.1/§6.5).
SPOT_COLS = ["time", "sex", "moc1", "race", "county"]

# Numeric subset for the representative correlation read below -- mirrors the kind of
# 2-8 column pick Tier 4's correlation matrix (VISUALIZATION_EXPANSION_PROMPTS.md
# Phase 13) will let a user make.
CORRELATION_SUBSET = ["time", "history", "aggsentc"]

# Representative chain exercising all three filter kinds the app emits.
NUMERIC = make_history.filter_single("time", "gt", "14")                          # f.time.gt.14
OR_SAME = make_history.filter_or_same("race", "eq", ["White", "Black", "Am Ind"])  # o.race.eq...
MOC1 = make_history.moc(1, "A")                                                    # f.moc1.eq.A
MOC2 = make_history.moc(2, "9")                                                    # f.moc2.eq.9


@functools.lru_cache(maxsize=1)
def _load_base():
    # Build the base exactly the way cache._execute does for the `action: None` entry.
    d = Data()
    d.load(cache.DATAFILE)
    return d


def _snapshot(df):
    return {
        "id": id(df),
        "shape": df.shape,
        "dtypes": df.dtypes.copy(),
        "copy": df.copy(deep=True),
        "spot": {c: df[c].copy(deep=True) for c in SPOT_COLS},
    }


def _run_pipeline(base):
    # Simulate a shared-base build: every operation reads `base` as its source and
    # returns a NEW frame (boolean masking / concat). This is what a load-once /
    # preloaded base will be subjected to on every request.
    results = {}

    engine = Data()  # fresh Data; only parses codebook

    # --- filters (the write-shaped ops) ---
    results["numeric"] = engine.filter("time", "gt", "14", inplace=False, source=base)
    results["or"] = engine.filter_or_same("race", "eq", ["White", "Black", "Am Ind"],
                                          inplace=False, source=base)
    results["moc"] = engine.filter_moc(["A", "9", "*", "*", "*"], inplace=False, source=base)

    # --- read paths (must be read-only over the base) ---
    reader = Data()
    reader.df = base
    reader.get_column_info("time")   # numeric-stats branch (mean/median/std)
    reader.get_column_info("sex")    # categorical branch (num_each)
    reader.get_numeric_columns()     # float64 detection (data.py:329)
    reader.get_table("time", "sex", "race")  # crosstab: filters internally, read-only
    # get_moc_options reassigns the *reader's* self.df (inplace filter_moc default) but
    # must never mutate the underlying base frame object -- that's the crux of the property.
    reader.get_moc_options(["A", "*", "*", "*", "*"])

    # --- visualization-expansion read shapes ---

    # Aggregate reads through the real Phase 1 helper (Data.aggregate_by_group): the
    # (group_column, measure, aggregate) -> by-group series that feeds choropleth fills,
    # waterfall/treemap values, and bubble sizes (VISUALIZATION_EXPANSION.md §6.1). Exercise
    # all three branches (count / numeric mean / groupby-mode) against the base via an
    # explicit source= so each is proven read-only over the shared frame.
    results["agg_count"] = reader.aggregate_by_group("county", "#", "count", source=base)
    results["agg_mean"] = reader.aggregate_by_group("county", "time", "mean", source=base)
    results["agg_mode"] = reader.aggregate_by_group("county", "time", "mode", source=base)

    # Phase 9 grain switch aggregates over the district (float64) and region (categorical)
    # columns instead of county — same helper, different group column, same read-only contract.
    results["agg_district"] = reader.aggregate_by_group("district", "time", "mean", source=base)
    results["agg_region"] = reader.aggregate_by_group("region", "#", "count", source=base)

    # Two-group aggregate reads (chart-library expansion Phase B1, Data.aggregate_by_two): the
    # (group_a, group_b, measure, aggregate) -> {a: {b: value}} matrix feeding the wave-2
    # grouped/stacked/slope/mosaic/animated charts. Exercise the count and numeric-mean
    # branches against the base via an explicit source= so each is proven read-only.
    results["agg2_count"] = reader.aggregate_by_two("sex", "race", "#", "count", source=base)
    results["agg2_mean"] = reader.aggregate_by_two("sex", "race", "time", "mean", source=base)

    # Distribution-stats reads (chart-library expansion Phase B2, Data.distribution_stats): the
    # numpy-only five-number/whiskers/histogram/ECDF/binned-KDE engine behind the wave-2
    # histogram/ECDF/KDE/box/violin charts. Exercise both the whole-column and the grouped
    # shape against the base via source= so each is proven read-only over the shared frame.
    results["dist_overall"] = reader.distribution_stats("time", source=base)
    results["dist_grouped"] = reader.distribution_stats("time", group_column="sex", source=base)

    # 2D-binning reads (chart-library expansion Phase B3, Data.bin2d): the np.histogram2d grid
    # behind the pair-plot / SPLOM off-diagonal panels. bin2d has no source= param (it reuses
    # distinct_counts + self.df, like get_table); reader.df is base here, so exercising it
    # proves the whole read leaves the shared base untouched. One continuous x discrete pair and
    # one continuous x continuous pair.
    results["bin2d_disc"] = reader.bin2d("time", "history")
    results["bin2d_cont"] = reader.bin2d("time", "aggsentc")

    # KDE-chart read (chart-library expansion Phase D2, Data.kde_density): the density engine behind
    # the KDE chart -- reuses distribution_stats and ADDS the linear-binned gridded weights (the
    # client convolves them at any bandwidth) + the spikiness probe. source= proves it read-only.
    results["kde"] = reader.kde_density("time", source=base)

    # County->district/region crosswalk read (Phase 7 geo foundation): the groupby.first()
    # that cache._county_crosswalk() derives from the base. Read-only over the shared frame,
    # so exercise the same shape here to prove it leaves the base untouched.
    results["crosswalk"] = base.groupby("county", observed=True)[["district", "region"]].first()

    # Correlation read: the exact df[cols].corr() shape Tier 4's Pearson correlation matrix
    # uses (VISUALIZATION_EXPANSION.md §6.5 / app.build_correlation, Phase 13) -- a user-picked
    # numeric subset, computed fresh and never disk-cached.
    results["correlation"] = base[CORRELATION_SUBSET].corr()

    return results


def _assert_unchanged(base, snap):
    assert id(base) == snap["id"], "base object identity changed"
    assert base.shape == snap["shape"], f"shape changed: {base.shape} != {snap['shape']}"
    assert base.dtypes.equals(snap["dtypes"]), "column dtypes changed"
    for col in SPOT_COLS:
        assert base[col].equals(snap["spot"][col]), f"spot column '{col}' changed"
    # strongest check: full-frame value equality (NaN == NaN under .equals)
    assert base.equals(snap["copy"]), "base DataFrame values changed"


def test_base_dataframe_immutable_through_pipeline():
    """The base DataFrame is byte-for-byte unchanged after the full pipeline runs."""
    base = _load_base().df
    snap = _snapshot(base)

    _run_pipeline(base)

    _assert_unchanged(base, snap)


def test_execute_matches_direct_and_leaves_base_intact():
    """cache._execute (the production path) reproduces the direct filter counts, and
    running it does not disturb our held base."""
    base = _load_base().df
    snap = _snapshot(base)

    direct = _run_pipeline(base)

    # Same chains, but through the real production replay (session=None + override).
    exec_numeric = cache._execute(None, [NUMERIC])
    exec_or = cache._execute(None, [OR_SAME])
    exec_moc = cache._execute(None, [MOC1, MOC2])

    assert len(exec_numeric.df) == len(direct["numeric"]), "numeric filter count drifted"
    assert len(exec_or.df) == len(direct["or"]), "OR filter count drifted"
    assert len(exec_moc.df) == len(direct["moc"]), "MOC drill count drifted"

    _assert_unchanged(base, snap)


def test_filtered_slice_cache_serves_and_stays_immutable():
    """Phase 3 (request-path optimization): a filtered state executed twice is served from
    the in-memory slice LRU (the SAME frame object, byte-identical to a direct filter), and
    a full get_column_info / get_table / aggregate_by_group / get_moc_options pass over that
    cached slice never mutates it. This is the filtered-slice twin of the base guardrail:
    the LRU shares slices read-only exactly as _base_df shares the base."""
    base = _load_base().df
    base_snap = _snapshot(base)

    # start from a clean LRU so this is an unambiguous miss -> hit
    cache._clear_filtered_cache()

    key = (cache.history_item_to_text(NUMERIC),)  # f.time.gt.14 -- the canonical token

    exec1 = cache._execute(None, [NUMERIC])   # miss: builds + caches the slice
    exec2 = cache._execute(None, [NUMERIC])   # hit: must be the SAME cached frame

    assert exec2.df is exec1.df, "second _execute was not served from the slice LRU"
    assert cache._filtered_cache[key] is exec1.df, "LRU is not holding the built slice"

    # byte-identical to a direct boolean filter of the base (the slice is correct, not just
    # cached) -- the wrong-state failure mode the plan warns about would surface here
    direct = Data().filter("time", "gt", "14", inplace=False, source=base)
    assert exec1.df.equals(direct), "cached slice != direct filter result"

    # snapshot the cached slice, then run the read pipeline over it (the same read shapes the
    # base guardrail exercises, but pointed at the shared SLICE)
    slice_snap = _snapshot(exec1.df)
    reader = Data()
    reader.df = exec1.df
    reader.get_column_info("time")                 # numeric-stats branch
    reader.get_column_info("sex")                  # categorical branch
    reader.get_table("time", "sex", "race")        # crosstab: filters internally, read-only
    reader.aggregate_by_group("county", "#", "count", source=exec1.df)
    reader.aggregate_by_group("county", "time", "mean", source=exec1.df)
    reader.aggregate_by_two("sex", "race", "#", "count", source=exec1.df)     # Phase B1, two-group
    reader.aggregate_by_two("sex", "race", "time", "mean", source=exec1.df)   # Phase B1, two-group
    reader.distribution_stats("time", source=exec1.df)                        # Phase B2, distribution
    reader.distribution_stats("time", group_column="sex", source=exec1.df)    # Phase B2, grouped
    reader.kde_density("time", source=exec1.df)                               # Phase D2, KDE density
    reader.bin2d("time", "history")                                           # Phase B3, 2D binning
    reader.bin2d("time", "aggsentc")                                          # Phase B3, 2D binning
    reader.get_moc_options(["A", "*", "*", "*", "*"])  # reassigns reader.df, must not mutate slice

    # the cached slice is byte-for-byte unchanged and still the object the LRU holds
    _assert_unchanged(exec1.df, slice_snap)
    assert cache._filtered_cache[key] is exec1.df, "LRU slice replaced/mutated by reads"

    # a third execute still hits the same untouched frame (tripwire must stay green)
    exec3 = cache._execute(None, [NUMERIC])
    assert exec3.df is exec1.df, "post-read _execute stopped serving the cached slice"

    # and the shared base underneath is likewise untouched
    _assert_unchanged(base, base_snap)


# Column pairs + aggregates the aggregate_by_two oracle check covers -- low-cardinality on
# purpose so the O(cells) nested-filter ground truth stays fast, spanning categorical x
# categorical (sex x race) and categorical x float64 (moc1 x district / race x history), and
# all four aggregates (count / mean / median / mode).
_AGG2_CASES = [
    ("sex", "race", "#", "count"),
    ("sex", "race", "time", "mean"),
    ("sex", "race", "time", "median"),
    ("moc1", "sex", "time", "mode"),
    ("race", "district", "history", "mean"),
]


def _aggregate_by_two_oracle(df, group_a, group_b, measure, aggregate):
    """Slow ground truth for Data.aggregate_by_two: for each observed (a, b) combination
    (both keys non-null) select the sub-frame with two boolean masks and reduce -- the
    O(|a_unique| * |b_unique|) nested-filter path the single groupby replaces. Returns the
    same nested {a: {b: value}} matrix, using the SAME Series reductions (mean/median/
    _first_mode), so the two can be compared cell-for-cell. Empty combinations are skipped
    to mirror observed=True; NaN keys are excluded to mirror groupby's dropna default."""
    a_values = [v for v in df[group_a].unique() if pd.notna(v)]
    b_values = [v for v in df[group_b].unique() if pd.notna(v)]
    matrix = {}
    for av in a_values:
        mask_a = df[group_a] == av
        for bv in b_values:
            subset = df[mask_a & (df[group_b] == bv)]
            if len(subset) == 0:
                continue  # observed=True omits empty combos
            if aggregate == 'count':
                value = len(subset)
            elif aggregate == 'mean':
                value = subset[measure].mean()
            elif aggregate == 'median':
                value = subset[measure].median()
            else:  # mode
                value = _first_mode(subset[measure])
            matrix.setdefault(av, {})[bv] = value
    return matrix


def _assert_matrices_equal(got, oracle, label):
    """Cell-for-cell equality of two {a: {b: value}} matrices, NaN-aware (a reduction over an
    all-NaN measure yields NaN in both, and NaN != NaN)."""
    assert set(got.keys()) == set(oracle.keys()), \
        f"{label}: row keys differ ({set(got) ^ set(oracle)})"
    for a in oracle:
        row_got, row_oracle = got[a], oracle[a]
        assert set(row_got.keys()) == set(row_oracle.keys()), \
            f"{label}: col keys differ for row {a!r} ({set(row_got) ^ set(row_oracle)})"
        for b in row_oracle:
            vg, vo = row_got[b], row_oracle[b]
            if pd.isna(vg) and pd.isna(vo):
                continue
            assert vg == vo, f"{label}: cell ({a!r}, {b!r}) {vg!r} != oracle {vo!r}"


def test_aggregate_by_two_matches_nested_oracle():
    """Chart-library expansion Phase B1: Data.aggregate_by_two's single-groupby matrix equals
    the slow nested-filter oracle cell-for-cell, across all four aggregates and both
    categorical x categorical and categorical x float64 pairs -- and leaves the base intact."""
    base = _load_base().df
    snap = _snapshot(base)

    reader = Data()
    reader.df = base
    for group_a, group_b, measure, aggregate in _AGG2_CASES:
        got = reader.aggregate_by_two(group_a, group_b, measure, aggregate, source=base)
        oracle = _aggregate_by_two_oracle(base, group_a, group_b, measure, aggregate)
        label = f"aggregate_by_two({group_a}, {group_b}, {measure}, {aggregate})"
        _assert_matrices_equal(got, oracle, label)

    _assert_unchanged(base, snap)


# Distribution-stats oracle helpers (Phase B2). The deterministic components are checked
# EXACTLY against hand-computed numpy on the same slice; the KDE (a smoothing estimator) is
# checked by properties + rough shape agreement with an independent exact Gaussian KDE.

def _finite(series):
    """The finite-value view the engine reduces over -- same dropna + float cast, so a group
    block and its `base[mask]` oracle operate on the identical ordered array."""
    return series.dropna().to_numpy(dtype=float)


def _exact_kde(grid, x, h):
    """Exact Gaussian KDE at each grid point, computed from the distinct-value counts
    (np.unique) for speed -- the ground truth the engine's linear-binned KDE approximates."""
    uniq, counts = np.unique(x, return_counts=True)
    diffs = (grid[:, None] - uniq[None, :]) / h
    kern = np.exp(-0.5 * diffs ** 2) / (h * math.sqrt(2.0 * math.pi))
    return (kern * counts[None, :]).sum(axis=1) / x.size


def _kde_from_weights(weights, grid, bandwidth):
    """Python mirror of visualize.js's kdeDensityFromWeights (and of data._binned_kde's back half):
    convolve the shipped gridded weights with a Gaussian kernel at `bandwidth`, renormalize to unit
    area. Proves the no-refetch contract -- the client can rebuild the engine's KDE from the weights
    alone -- so a drift between the JS convolution and the server's would surface as an oracle fail."""
    G = grid.size
    dx = (grid[-1] - grid[0]) / (G - 1)
    half = int(math.ceil(4.0 * bandwidth / dx))
    offsets = np.arange(-half, half + 1) * dx
    kernel = np.exp(-0.5 * (offsets / bandwidth) ** 2) / (bandwidth * math.sqrt(2.0 * math.pi))
    density = np.convolve(weights, kernel, mode='same')
    area = float(density.sum()) * dx
    if area > 0:
        density = density / area
    return density


def _silverman_oracle(x):
    """Independent Silverman's-rule bandwidth: recomputes 0.9 * min(std, IQR/1.349) * n**(-1/5)
    with fresh literals so an engine typo in the constant / exponent / IQR term is caught here,
    rather than passing self-consistently through _exact_kde (which reuses the engine's own bw)."""
    n = x.size
    if n < 2:
        return 0.0
    std = float(x.std(ddof=1))
    q1, q3 = np.percentile(x, [25, 75])
    iqr = q3 - q1
    spread = std if std > 0 else 0.0
    if iqr > 0:
        iqr_sigma = iqr / 1.349
        spread = min(spread, iqr_sigma) if spread > 0 else iqr_sigma
    if spread <= 0:
        return 0.0
    return 0.9 * spread * (n ** (-1.0 / 5.0))


def _assert_block_matches(block, x, edges, grid, label):
    n = x.size
    assert block['n'] == n, f"{label}: n {block['n']} != {n}"

    # --- five-number summary + moments (exact vs numpy) ---
    q1, median, q3 = np.percentile(x, [25, 50, 75])
    assert block['q1'] == q1, f"{label}: q1 {block['q1']} != {q1}"
    assert block['median'] == median, f"{label}: median {block['median']} != {median}"
    assert block['q3'] == q3, f"{label}: q3 {block['q3']} != {q3}"
    assert block['min'] == x.min() and block['max'] == x.max(), f"{label}: min/max drift"
    assert math.isclose(block['mean'], x.mean(), rel_tol=0, abs_tol=1e-9), f"{label}: mean drift"
    if n > 1:
        assert math.isclose(block['std'], x.std(ddof=1), rel_tol=1e-12, abs_tol=1e-9), \
            f"{label}: std drift"

    # --- whiskers + outlier counts (exact, same Tukey rule) ---
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    assert block['whisker_low'] == x[x >= lo_fence].min(), f"{label}: whisker_low drift"
    assert block['whisker_high'] == x[x <= hi_fence].max(), f"{label}: whisker_high drift"
    assert block['n_outliers_low'] == int((x < lo_fence).sum()), f"{label}: outliers_low drift"
    assert block['n_outliers_high'] == int((x > hi_fence).sum()), f"{label}: outliers_high drift"
    assert block['n_outliers'] == int((x < lo_fence).sum()) + int((x > hi_fence).sum()), \
        f"{label}: n_outliers total drift"
    assert block['n_outliers'] == block['n_outliers_low'] + block['n_outliers_high'], \
        f"{label}: n_outliers != low + high"

    # --- histogram (exact vs np.histogram on the SHARED edges) ---
    exp_counts, _ = np.histogram(x, bins=edges)
    assert block['hist_counts'] == [int(c) for c in exp_counts], f"{label}: histogram drift"
    # shared edges bracket every group value, so the histogram conserves all points
    assert sum(block['hist_counts']) == n, f"{label}: histogram dropped points"

    # --- ECDF (cumsum of the vectorized value counts) ---
    ev = np.asarray(block['ecdf']['values'], dtype=float)
    ec = np.asarray(block['ecdf']['cumulative'], dtype=float)
    assert ev.size <= data.ECDF_MAX_POINTS, f"{label}: ECDF exceeds cap"
    if ev.size > 1:
        assert np.all(np.diff(ev) > 0), f"{label}: ECDF values not strictly ascending"
        assert np.all(np.diff(ec) >= 0), f"{label}: ECDF cumulative not monotone"
    assert math.isclose(ec[-1], 1.0, abs_tol=1e-12), f"{label}: ECDF does not reach 1.0"
    uniq, counts = np.unique(x, return_counts=True)
    if uniq.size <= data.ECDF_MAX_POINTS:
        assert np.array_equal(ev, uniq), f"{label}: ECDF values != np.unique"
        assert np.allclose(ec, np.cumsum(counts) / counts.sum()), f"{label}: ECDF cumsum drift"
    else:
        assert ev[0] == uniq[0] and ev[-1] == uniq[-1], f"{label}: ECDF endpoints not preserved"

    # --- no raw-row payload: no component ships an array as long as the row count ---
    assert ev.size < n or n <= data.ECDF_MAX_POINTS, f"{label}: ECDF is raw-row length"
    assert len(block['hist_counts']) == len(edges) - 1, f"{label}: histogram wrong length"

    # --- KDE: a smoothing estimator, checked by properties + shape (not exact float match) ---
    if block['kde'] is not None:
        assert grid is not None, f"{label}: KDE present but no grid"
        g = np.asarray(grid, dtype=float)
        dens = np.asarray(block['kde'], dtype=float)
        assert dens.size == g.size, f"{label}: KDE length != grid length"
        assert data.KDE_GRID_MIN <= dens.size <= data.KDE_GRID_MAX, f"{label}: KDE grid out of bounds"
        assert np.all(dens >= -1e-12), f"{label}: KDE has negative density"
        # bandwidth independently pinned: (recomputed) Silverman floored at the grid resolution,
        # so a formula typo can't slip through the (bw-reusing) exact-KDE shape check below
        expected_bw = max(_silverman_oracle(x), data.KDE_GRID_STEPS_PER_BW * (g[1] - g[0]))
        assert math.isclose(block['bandwidth'], expected_bw, rel_tol=1e-9, abs_tol=1e-12), \
            f"{label}: bandwidth {block['bandwidth']} != expected {expected_bw}"
        # rectangle-rule integral (== the engine's own renormalization, so ~1 exactly)
        area = float(dens.sum()) * (g[1] - g[0])
        assert abs(area - 1.0) < 1e-6, f"{label}: KDE integral {area} not ~1"
        # rough agreement with the exact Gaussian KDE where the density is meaningful
        exact = _exact_kde(g, x, block['bandwidth'])
        sig = exact > 0.10 * exact.max()
        rel = np.abs(dens[sig] - exact[sig]) / exact[sig]
        assert rel.max() < 0.15, f"{label}: binned KDE {rel.max():.3f} off exact KDE"


def test_distribution_stats_matches_numpy_oracle():
    """Chart-library expansion Phase B2: Data.distribution_stats's deterministic components
    (five-number summary + whiskers + outlier counts, histogram on shared edges, ECDF from the
    vectorized value counts) match hand-computed numpy EXACTLY on the same slice -- whole column
    and split by a 2-level categorical -- and the binned KDE is a valid density (non-negative,
    unit integral) roughly tracking the exact Gaussian KDE. Nothing raw-per-row is emitted, and
    the base is left intact."""
    base = _load_base().df
    snap = _snapshot(base)

    reader = Data()
    reader.df = base

    for column, group_column in [("time", None), ("time", "sex"), ("aggsentc", "race")]:
        stats = reader.distribution_stats(column, group_column=group_column, source=base)
        edges = np.asarray(stats['bin_edges'], dtype=float)
        grid = stats['kde_grid']

        # overall block vs the whole finite column
        _assert_block_matches(stats['overall'], _finite(base[column]), edges, grid,
                              f"distribution_stats({column}) overall")

        # each group block vs the direct boolean-masked slice
        if group_column is not None:
            for gval, block in stats['groups'].items():
                gx = _finite(base.loc[base[group_column] == gval, column])
                _assert_block_matches(block, gx, edges, grid,
                                      f"distribution_stats({column} by {group_column}={gval!r})")

    _assert_unchanged(base, snap)


def test_distribution_stats_overrides_and_degenerate():
    """Chart-library expansion Phase B2: the user-facing bins/bandwidth override + cap paths
    and the empty/degenerate paths (the ones real chart interaction hits) behave, invalid
    inputs are rejected, and everything stays read-only over the base."""
    base = _load_base().df
    snap = _snapshot(base)
    reader = Data()
    reader.df = base

    # bins override honored; histogram still conserves every point
    o = reader.distribution_stats("time", bins=20, source=base)
    assert len(o['overall']['hist_counts']) == 20, "bins override not honored"
    assert sum(o['overall']['hist_counts']) == o['overall']['n'], "override histogram dropped points"

    # bins clamped at HISTOGRAM_MAX_BINS
    capped = reader.distribution_stats("time", bins=10 ** 6, source=base)
    assert len(capped['overall']['hist_counts']) == data.HISTOGRAM_MAX_BINS, "bins not capped"

    # bandwidth override -> the block bandwidth is that value floored at the grid resolution
    b = reader.distribution_stats("time", bandwidth=5.0, source=base)
    g = np.asarray(b['kde_grid'], dtype=float)
    floor = data.KDE_GRID_STEPS_PER_BW * (g[1] - g[0])
    assert b['overall']['bandwidth'] == max(5.0, floor), "bandwidth override not honored/floored"

    # a bandwidth wider than the grid window is CAPPED so the Gaussian kernel still fits the
    # grid -- otherwise np.convolve(mode='same') returns an array longer than kde_grid (the
    # kernel-overflow bug). The KDE must stay a valid density aligned to the grid.
    huge = reader.distribution_stats("time", bandwidth=10 ** 9, source=base)
    hg = np.asarray(huge['kde_grid'], dtype=float)
    hd = np.asarray(huge['overall']['kde'], dtype=float)
    assert hd.size == hg.size, "KDE length != grid length (kernel overflowed the grid)"
    assert huge['overall']['bandwidth'] < 10 ** 9, "over-wide bandwidth not capped to the grid"
    assert np.all(hd >= -1e-12) and abs(hd.sum() * (hg[1] - hg[0]) - 1.0) < 1e-6, \
        "capped-bandwidth KDE is not a valid density"

    # invalid overrides + non-numeric column are rejected
    for bad, why in [(lambda: reader.distribution_stats("time", bins=0, source=base), "bins<1"),
                     (lambda: reader.distribution_stats("time", bandwidth=0, source=base), "bandwidth<=0"),
                     (lambda: reader.distribution_stats("sex", source=base), "non-float64")]:
        try:
            bad()
            assert False, f"expected ValueError ({why})"
        except ValueError:
            pass

    # empty slice -> the n==0 shell: no crash, stable shape, everything nulled
    empty = base[base["time"] < -999]
    assert len(empty) == 0
    ereader = Data()
    ereader.df = empty
    es = ereader.distribution_stats("time")
    assert es['n'] == 0 and es['domain'] is None and es['bin_edges'] == [] and es['kde_grid'] is None
    eb = es['overall']
    assert (eb['n'] == 0 and eb['kde'] is None and eb['bandwidth'] is None
            and eb['hist_counts'] == [] and eb['std'] is None
            and eb['ecdf'] == {'values': [], 'cumulative': []}), "empty block shape drifted"

    _assert_unchanged(base, snap)


def test_kde_density_passthrough_and_readonly():
    """Chart-library expansion Phase D2: Data.kde_density passes the shared grid / FD histogram /
    five-number summary / Silverman bandwidth straight through from distribution_stats, ADDS the
    linear-binned gridded weights (which conserve mass -> sum to ~1 and are non-negative) plus the
    physical bandwidth bounds that bracket the default, and convolving the shipped weights at the
    reported bandwidth reproduces the engine's own binned KDE -- the no-refetch bandwidth contract
    the JS slider relies on. All read-only over the shared base."""
    base = _load_base().df
    snap = _snapshot(base)
    reader = Data()
    reader.df = base

    for col in ("time", "aggsentc"):
        k = reader.kde_density(col, source=base)
        s = reader.distribution_stats(col, source=base)
        b = s['overall']
        # pass-through: identical to distribution_stats' shared axis + overall block
        assert k['kde_grid'] == s['kde_grid'], f"{col}: KDE grid != distribution_stats grid"
        assert k['bin_edges'] == s['bin_edges'], f"{col}: hist edges drift"
        assert k['hist_counts'] == b['hist_counts'], f"{col}: hist counts drift"
        assert k['bandwidth'] == b['bandwidth'], f"{col}: bandwidth drift"
        assert (k['median'], k['q1'], k['q3'], k['min'], k['max'], k['n']) == \
               (b['median'], b['q1'], b['q3'], b['min'], b['max'], s['n']), f"{col}: summary drift"

        # weights: conserve mass (linear binning splits each unit weight across two nodes) and are
        # non-negative; the physical bandwidth bounds bracket the reported default.
        w = np.asarray(k['kde_weights'], dtype=float)
        grid = np.asarray(k['kde_grid'], dtype=float)
        assert w.size == grid.size, f"{col}: weights length != grid length"
        assert abs(w.sum() - 1.0) < 1e-9, f"{col}: weights sum {w.sum()} != 1"
        assert np.all(w >= -1e-12), f"{col}: negative weight"
        assert k['bandwidth_min'] <= k['bandwidth'] <= k['bandwidth_max'], f"{col}: bw out of bounds"

        # the no-refetch contract: convolving the shipped weights == the engine's own KDE, and the
        # result is a valid density (non-negative, unit integral).
        client = _kde_from_weights(w, grid, k['bandwidth'])
        server = np.asarray(b['kde'], dtype=float)
        assert np.allclose(client, server, atol=1e-9), f"{col}: client conv != server KDE"
        dx = (grid[-1] - grid[0]) / (grid.size - 1)
        assert abs(float(client.sum()) * dx - 1.0) < 1e-6, f"{col}: KDE integral not ~1"
        assert np.all(client >= -1e-12), f"{col}: KDE has negative density"

    _assert_unchanged(base, snap)


def test_kde_density_spikiness_flag():
    """Chart-library expansion Phase D2: the spikiness guardrail (CHART_LIBRARY_EXPANSION.md §8)
    fires on round-number clustering and stays quiet on a genuinely continuous column. Synthetic
    frames so the threshold behavior is pinned regardless of which real column happens to be spiky:
    a column with most of its mass on 5 exact values is flagged (and its top values named, ordered
    by share); a continuous normal column is not."""
    rng = np.random.default_rng(0)
    # spiky: 2000 cases on five round-number pillars + 200 spread thin around them
    spiky = np.concatenate([np.repeat([12.0, 24.0, 36.0, 48.0, 60.0], 400),
                            rng.uniform(6.0, 66.0, 200)])
    smooth = rng.normal(36.0, 10.0, 2200)             # continuous: mass spread across ~2200 values
    df = pd.DataFrame({'spiky': spiky.astype(float), 'smooth': smooth.astype(float)})
    reader = Data()
    reader.df = df

    ks = reader.kde_density('spiky')
    assert ks['spiky'] is True, f"round-number column not flagged (top_share={ks['top_share']})"
    assert 0.0 <= ks['top_share'] <= 1.0
    assert ks['top_share'] >= data.KDE_SPIKY_SHARE
    shares = [tv['share'] for tv in ks['top_values']]
    assert shares == sorted(shares, reverse=True), "top_values not ordered by share"
    assert 0 < len(ks['top_values']) <= data.KDE_SPIKY_TOP_K
    # the five pillars are the named values
    named = sorted(round(tv['value']) for tv in ks['top_values'])
    assert named == [12, 24, 36, 48, 60], f"top values not the pillars: {named}"

    kc = reader.kde_density('smooth')
    assert kc['spiky'] is False, f"continuous column wrongly flagged (top_share={kc['top_share']})"
    assert kc['top_share'] < data.KDE_SPIKY_SHARE


# Column pairs the bin2d oracle covers -- spanning every discrete/continuous combination so
# both binning branches are exercised (from the measured cardinalities: history 7, sentyear 19
# are discrete <= BIN2D_MAX_BINS; time 216, aggsentc 733 are continuous).
_BIN2D_CASES = [
    ("time", "history"),      # continuous x discrete
    ("history", "aggsentc"),  # discrete x continuous
    ("time", "aggsentc"),     # continuous x continuous
    ("sentyear", "history"),  # discrete x discrete
]


def test_bin2d_matches_numpy_oracle():
    """Chart-library expansion Phase B3: Data.bin2d's grid is EXACTLY a direct np.histogram2d
    over the returned edges (the acceptance criterion), the bin count is capped per axis, every
    jointly-finite point is binned, and a discrete axis's lattice places each distinct value in
    its own bin (verified independently via the axis marginals) -- across all four discrete /
    continuous combinations, leaving the base intact."""
    base = _load_base().df
    snap = _snapshot(base)

    reader = Data()
    reader.df = base

    for col_x, col_y in _BIN2D_CASES:
        got = reader.bin2d(col_x, col_y)
        label = f"bin2d({col_x}, {col_y})"

        paired = base[[col_x, col_y]].dropna()
        px = paired[col_x].to_numpy(dtype=float)
        py = paired[col_y].to_numpy(dtype=float)

        xe = np.asarray(got['x_edges'], dtype=float)
        ye = np.asarray(got['y_edges'], dtype=float)
        counts = np.asarray(got['counts'], dtype=float)

        # 1) the grid IS a direct np.histogram2d over the returned edges (acceptance criterion)
        direct, dxe, dye = np.histogram2d(px, py, bins=[xe, ye])
        assert np.array_equal(counts, direct), f"{label}: grid != direct np.histogram2d"
        assert np.allclose(xe, dxe) and np.allclose(ye, dye), f"{label}: edges not reproduced"

        # 2) shape + capped bins per axis
        assert counts.shape == (xe.size - 1, ye.size - 1), f"{label}: counts shape != edges"
        assert xe.size - 1 <= data.BIN2D_MAX_BINS, f"{label}: x bins exceed cap"
        assert ye.size - 1 <= data.BIN2D_MAX_BINS, f"{label}: y bins exceed cap"

        # 3) every jointly-finite point is binned (shared edges bracket the paired data)
        assert counts.sum() == got['n'] == len(paired), f"{label}: bin2d dropped points"

        # 4) the discrete/continuous decision + edge structure, per axis, checked independently:
        #    a discrete axis (whole-column distinct <= cap) is one lattice bin per distinct
        #    PAIRED value and its marginal equals the per-value counts (so each bin holds exactly
        #    one value); a continuous axis is exactly the capped equal-width bins.
        for axis, (vals, edges, disc, col) in enumerate([
                (px, xe, got['x_discrete'], col_x),
                (py, ye, got['y_discrete'], col_y)]):
            distinct_all = int(base[col].nunique(dropna=True))
            assert disc == (distinct_all <= data.BIN2D_MAX_BINS), f"{label}: {col} discrete flag wrong"
            if disc:
                uniq, cnts = np.unique(vals, return_counts=True)
                assert edges.size - 1 == uniq.size, f"{label}: {col} lattice bins != n_uniques"
                marginal = counts.sum(axis=1 - axis)  # axis 0 -> x-marginal, axis 1 -> y-marginal
                assert np.array_equal(marginal, cnts), f"{label}: {col} lattice bin != value counts"
            else:
                assert edges.size - 1 == data.BIN2D_MAX_BINS, f"{label}: {col} continuous != cap bins"

    _assert_unchanged(base, snap)


def test_bin2d_degenerate_and_non_numeric():
    """Chart-library expansion Phase B3: bin2d's edge paths -- an empty slice yields the stable
    n==0 shell (no crash), and a non-numeric column is rejected -- all read-only over the base."""
    base = _load_base().df
    snap = _snapshot(base)

    # non-numeric column rejected (bin2d needs float64 axes, like distribution_stats)
    reader = Data()
    reader.df = base
    try:
        reader.bin2d("time", "sex")
        assert False, "expected ValueError for a non-numeric column"
    except ValueError:
        pass

    # empty slice -> the n==0 shell: no crash, stable shape, empty grid + edges
    empty = base[base["time"] < -999]
    assert len(empty) == 0
    ereader = Data()
    ereader.df = empty
    es = ereader.bin2d("time", "history")
    assert (es['n'] == 0 and es['x_edges'] == [] and es['y_edges'] == []
            and es['counts'] == []), "empty bin2d shell shape drifted"

    _assert_unchanged(base, snap)


def main():
    checks = [
        ("base immutable through full pipeline", test_base_dataframe_immutable_through_pipeline),
        ("_execute matches direct + base intact", test_execute_matches_direct_and_leaves_base_intact),
        ("filtered-slice LRU serves + stays immutable", test_filtered_slice_cache_serves_and_stays_immutable),
        ("aggregate_by_two matches nested-filter oracle", test_aggregate_by_two_matches_nested_oracle),
        ("distribution_stats matches numpy oracle", test_distribution_stats_matches_numpy_oracle),
        ("distribution_stats overrides + degenerate paths", test_distribution_stats_overrides_and_degenerate),
        ("kde_density pass-through + weights contract", test_kde_density_passthrough_and_readonly),
        ("kde_density spikiness guardrail", test_kde_density_spikiness_flag),
        ("bin2d matches numpy oracle", test_bin2d_matches_numpy_oracle),
        ("bin2d degenerate + non-numeric paths", test_bin2d_degenerate_and_non_numeric),
    ]
    print("=" * 70)
    print("base DataFrame immutability guardrail")
    print("=" * 70)

    # touch the base once up front so timing/memory is obvious in the report
    base = _load_base().df
    print(f"base loaded: {base.shape[0]:,} rows x {base.shape[1]} cols; id={id(base)}")
    print("-" * 70)

    failed = 0
    for name, fn in checks:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    print("=" * 70)
    if failed:
        print(f"{failed} check(s) FAILED")
        return 1
    print("all checks passed — base DataFrame immutability holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
