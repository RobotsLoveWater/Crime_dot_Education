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

import sys
import functools

import cache
import make_history
from data import Data

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


def main():
    checks = [
        ("base immutable through full pipeline", test_base_dataframe_immutable_through_pipeline),
        ("_execute matches direct + base intact", test_execute_matches_direct_and_leaves_base_intact),
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
