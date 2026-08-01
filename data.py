# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# data.py
# data analysis

import pandas as pd
import numpy as np
import pyreadstat  # not used directly, but absolutely necessary for loading SPSS files.
import math

import xml.etree.ElementTree as ET

import moc
from perf.profiling import timed


# --- distribution-stats engine tunables (chart-library expansion Phase B2) ----------
# Bounds that keep the numpy-only distribution engine's payload SUMMARIZED (never raw
# per-row -- see CHART_LIBRARY_EXPANSION.md §8): the KDE is evaluated on a bounded grid, the
# histogram bin count is capped (Freedman-Diaconis can explode on wide-range data), the ECDF
# is thinned to at most this many (value, cumulative) points, and a grouped request over more
# than this many observed groups is rejected rather than shipping a bloated payload (later
# builder phases pre-check, like the scatter lattice guard).
#
# The KDE grid is sized to RESOLVE its Gaussian kernel (~1 grid step per bandwidth) so the
# discretized density integrates to ~1 without aliasing -- clamped to [MIN, MAX] so a tiny
# Silverman bandwidth over a wide range (e.g. `time`, whose long tail spreads the range while
# 294k rows shrink the bandwidth) can't blow the point count up. MIN keeps a smooth curve,
# MAX keeps the payload bounded.
KDE_GRID_MIN = 256           # floor on KDE grid points (a smooth curve at minimum)
KDE_GRID_MAX = 512           # ceiling on KDE grid points (bounded payload; the bandwidth
                             # floor -- not the grid size -- is what prevents aliasing, so a
                             # smaller ceiling only smooths spiky columns a touch more)
KDE_GRID_STEPS_PER_BW = 2.0  # target grid steps per bandwidth (and the min-bandwidth floor)
HISTOGRAM_MAX_BINS = 100     # cap on the Freedman-Diaconis / user-override bin count
ECDF_MAX_POINTS = 500        # cap on ECDF (value, cumulative) pairs before downsampling
DISTRIBUTION_MAX_GROUPS = 100  # reject a grouped request above this many observed groups


# --- 2D-binning helper tunable (chart-library expansion Phase B3) ----------------------
# Cap on bins per axis for Data.bin2d -- the read behind the pair-plot / SPLOM off-diagonal
# panels. Doubles as the discrete/continuous threshold: a column with <= this many distinct
# values bins onto its NATURAL value lattice (one bin per distinct value), a higher-cardinality
# column onto this many equal-width bins. Either way the grid is <= BIN2D_MAX_BINS**2 cells, so
# a pair plot's N^2 tiles stay bounded (never one mark per row). See CHART_LIBRARY_EXPANSION.md §4.
BIN2D_MAX_BINS = 50


# --- KDE-chart spikiness probe (chart-library expansion Phase D2) ----------------------
# The KDE's honesty guardrail (CHART_LIBRARY_EXPANSION.md §8): a numeric column is "spiky" when a
# large share of its cases pile onto a few EXACT values -- sentence lengths cluster on round
# numbers (12/24/36/48/60 months), the very pattern a smooth density curve erases. Data.kde_density
# flags it when the KDE_SPIKY_TOP_K most common values together hold >= KDE_SPIKY_SHARE of the
# cases, and the chart raises the loud "read the histogram instead" nudge. A genuinely continuous
# column spreads its mass across many values, so its top-K share stays small and it isn't flagged.
KDE_SPIKY_TOP_K = 5
KDE_SPIKY_SHARE = 0.5


class Data:
    # beep, boop; I do the data.

    CODEBOOK_FILE = 'codebook.xml'
    DEFAULT_FILE = 'dataset.sav'
    MOC = moc.MnOffenseCodes()

    VALID_SORTING = [
        'reverse_occurrence',
        'occurrence',
        'alphanumeric',
        'reverse_alphanumeric'
    ]

    # Shared measure/aggregate vocabulary for the Visualize workbench (see
    # VISUALIZATION_EXPANSION.md §6.1). A "measure" is either COUNT_MEASURE ('#',
    # count-of-cases -- the same sentinel the Compare builder already uses) or a numeric
    # column name; an "aggregate" is one of these. `aggregate_by_group` maps
    # (group_column, measure, aggregate) -> a by-group series over the filtered slice.
    COUNT_MEASURE = '#'
    VALID_AGGREGATES = [
        'count',
        'mean',
        'median',
        'mode'
    ]

    # display order for the explore column browser's groups; group names come from
    # the `group` attribute on codebook.xml entries (parsed into self.groups below).
    # Any group not listed here - including the "Other" fallback - sorts last.
    GROUP_ORDER = [
        'Offense',
        'Sentence',
        'Departures & reasons',
        'Criminal history',
        'Demographics',
        'Court & process',
        'Dates',
        'Sentencing grid',
        'Identifiers'
    ]

    def __init__(self, preload=None):

        # the active dataframe
        if preload: self.df = preload
        else: self.df = None

        # the codebook for looking up descriptions, this is the entry displayed for undocumented columns
        self.codebook = {False: "<Not Documented>"}

        # column -> column-browser group, from each entry's `group` attribute
        self.groups = {}

        # create codebook from xml
        # descriptions are taken from the codebook provided
        tree = ET.parse(self.CODEBOOK_FILE)
        root = tree.getroot()
        for entry in root:
            self.codebook[entry.tag] = entry.text
            self.groups[entry.tag] = entry.get('group', 'Other')

    def filter(self, column, operation, value, inplace=True, source=None) -> pd.DataFrame:

        # no source means self.df is used
        if source is None: source = self.df

        # make the value numeric so 16.0 == 16, etc.
        temp_value = value
        if source[column].dtype == 'float64': temp_value = float(value)

        # do the filter based on operation then input in temp
        temp = None
        if operation == 'eq':
            temp = source[(source[column] == temp_value)]
        elif operation == 'ne':
            temp = source[(source[column] != temp_value)]
        elif operation == 'gt':
            temp = source[(source[column] > temp_value)]
        elif operation == 'ge':
            temp = source[(source[column] >= temp_value)]
        elif operation == 'lt':
            temp = source[(source[column] < temp_value)]
        elif operation == 'le':
            temp = source[(source[column] <= temp_value)]
        else:
            raise Exception(str(operation) + " is not a valid filter operation.")

        # if in place make changes before returning
        if inplace: self.df = temp
        return temp

    def filter_or_same(self, column, operation, values, inplace=True, source=None) -> pd.DataFrame:

        # no source means self.df is used
        if source is None: source = self.df

        # create a list of filtered results
        filter_list = []
        for ii in range(len(values)):
            filter_list.append(self.filter(column, operation, values[ii], inplace=False, source=source))

        # combine the filtered lists then drop duplicate entries
        filter_df = pd.concat(filter_list).drop_duplicates()

        # if in place make changes before returning
        if inplace: self.df = filter_df
        return filter_df

    def filter_or_diff(self, columns, operations, values, inplace=True, source=None) -> pd.DataFrame:

        # no source means self.df is used
        if source is None: source = self.df

        # there must be the same number of columns, operations, and values, this avoids weird behavior
        assert len(columns) == len(operations) and len(columns) == len(values)

        # create a list of filtered results
        filter_list = []
        for ii in range(len(columns)):
            filter_list.append(self.filter(columns[ii], operations[ii], values[ii], inplace=False, source=source))

        # combine the filtered lists then drop duplicate entries
        filter_df = pd.concat(filter_list).drop_duplicates()

        # if in place make changes before returning
        if inplace: self.df = filter_df
        return filter_df

    def filter_and(self) -> pd.DataFrame:
        pass

    def filter_moc(self, moc_list, inplace=True, source=None) -> pd.DataFrame:

        # no source means self.df is used
        if source is None: source = self.df
        filter_df = source

        # filter each moc in order
        for k, moc in enumerate(moc_list):
            if moc != '*': filter_df = self.filter('moc' + str(k+1), 'eq', moc, inplace=False, source=filter_df)

        # if in place make changes before returning
        if inplace: self.df = filter_df
        return filter_df

    def save(self, filename, ext='.csv') -> None:
        self.df.to_csv(filename + ext)

    def save_parquet(self, filename, ext='.parquet') -> None:
        # Write the base as a typed columnar Parquet file (Lever C: ~10x smaller on disk,
        # ~20x faster to parse than the CSV). pyarrow needs a single Arrow type per column,
        # but a few category columns carry mixed str/float categories (a read_csv
        # type-inference artifact on messy source values) that can't be dictionary-encoded.
        # Stringify just those columns' categories; every other column (all float64 + the
        # clean categoricals) is written verbatim, so a Parquet round-trip is byte-identical
        # to the CSV base for them. The handful of mixed columns normalize to string labels
        # (and a couple merge equal-looking values). See BASE_DATAFRAME_OPTIMIZATION.md.
        out = self.df
        fixups = {}
        for col in out.columns:
            s = out[col]
            if str(s.dtype) == 'category' and not all(isinstance(c, str) for c in s.cat.categories):
                obj = s.astype(object)          # category -> object; missing stays NaN
                mask = s.notna()
                obj[mask] = obj[mask].map(str)  # str() only the present values (keep NaN)
                fixups[col] = obj.astype('category')
        if fixups:
            out = out.assign(**fixups)          # new frame; self.df is left untouched
        out.to_parquet(filename + ext, engine='pyarrow', index=False)

    def load(self, filename) -> None:
        # load dataframe or concat with existing
        # filenames is expecting a string

        # this will temporarily hold the dataframe
        temp_df = None

        # if the last three characters of the filename is 'sav' assume the file is in spss format, .csv for csv
        if filename[-4:] == '.sav':
            temp_df = pd.read_spss(filename)
        elif filename[-8:] == '.parquet':
            # typed columnar base (Lever C): dtypes (category + float64) are stored in the
            # file, so no type re-inference or category cast is needed on read.
            temp_df = pd.read_parquet(filename)
        elif filename[-4:] == '.csv':
            temp_df = pd.read_csv(filename)
        else:
            raise ValueError(filename + " is not a valid SPSS, Parquet, or CSV file.")

        # Lever A (base DataFrame optimization): the string columns dominate the base's
        # resident memory (~92% of it). Re-type object -> category to cut RAM ~2.5-3.5x.
        # Numeric columns (float64/int64) are left untouched on purpose: the filter/stat
        # code branches on `dtype == 'float64'` (filter / get_column_info /
        # get_numeric_columns above), and eq/ne on a categorical selects the same rows as
        # on object, so results and cache keys stay byte-identical. See
        # BASE_DATAFRAME_OPTIMIZATION.md.
        cast = {c: 'category' for c in temp_df.select_dtypes(include='object').columns}
        if cast:
            temp_df = temp_df.astype(cast)

        # if no file is currently loaded replace the emptiness with the new dataframe
        if self.df is None:
            self.df = temp_df

        # if there is a dataframe, concatenate
        else:
            self.df = pd.concat([self.df, temp_df])

        return

    def get_entries(self) -> int:
        return len(self.df)

    def get_columns(self) -> list:
        return self.df.columns

    def get_columns_w_codebook(self, only_documented=True) -> dict:
        # print all headers with codebook info
        output = {}

        # create a list of columns with the attached codebook name
        for i_col in self.df.columns:
            entry = None
            if i_col in self.codebook:
                entry = self.codebook[i_col]
            elif not only_documented:
                entry = self.codebook[False]
            if entry: output[i_col] = entry

        return output

    @timed('get_column_info')
    def get_column_info(self, header, precision=3) -> dict:

        column = self.df[header]

        # create blank output
        output = {'header': None,
                  'entries': len(self.df),
                  'each': [],
                  'nan': None,
                  'mean': None,
                  'mdn': None,
                  'std': None,
                  'mode': None,
                  'mode_extra': 0}

        # set the header from the codebook
        output['header'] = self.codebook[False]
        if header in self.codebook:
            output['header'] = self.codebook[header]

        # get the percent of each unique occurrence

        # this sorts from least to most common
        raw_numbers = self.num_each(column)
        raw_numbers = {k: v for k, v in sorted(raw_numbers.items(), key=lambda item: item[1])}

        total_not_nan = 0
        for iu in raw_numbers.keys():
            if pd.notna(iu):
                total_not_nan += raw_numbers[iu]

        # output the number of empty rows
        total_nan = (len(column) - total_not_nan)

        # prevent division by zero in edge case where there was a dataframe but no data
        if len(column) > 0:
            percent_nan = 100 * (total_nan / len(column))
        else:
            percent_nan = 0

        output['nan'] = "nan: " + str(total_nan) + '=' + str(round(percent_nan * 10 ** precision) / 10 ** precision) + '%'

        # get relevant values if working with a numeric column
        output['numeric'] = False
        if column.dtype == 'float64' and len(column.unique()) > 1:
            output['numeric'] = True
            output['mean'] = str(round(column.mean() * 10 ** precision) / 10 ** precision)
            output['mdn'] = str(round(column.median() * 10 ** precision) / 10 ** precision)
            output['std'] = str(round(column.std() * 10 ** precision) / 10 ** precision)
            # mode: plea bargaining clusters sentences on round numbers (12/24/36/48/60
            # months), so the mode is a real fingerprint of plea practice -- but it is
            # genuinely multimodal. Show the first modal value + how many others tie it
            # ("+N more") so multimodality is surfaced, never silently dropped.
            modes = column.mode()  # dropna=True, sorted ascending
            if len(modes) > 0:
                output['mode'] = str(round(modes.iloc[0] * 10 ** precision) / 10 ** precision)
                output['mode_extra'] = int(len(modes) - 1)

        output['raw_numbers'] = raw_numbers
        output['len'] = len(column)

        return output

    def get_moc_options(self, moc_filter) -> list:

        # create a version for each possible active filter
        possible = []
        for active in range(1,5):
            output = {}
            to_edit = active

            # output assuming only what's already in place
            output['*'] = str(len(self.filter_moc(moc_filter)))

            try:
                inc = self.MOC.CODES[moc_filter[0]][active]['INC']
                to_edit = inc[0]
            except KeyError:
                inc = [int(active)]

            # grab all potential code entries
            for k_moc in self.MOC.CODES[moc_filter[0]][to_edit]:

                # skip meta-data entries
                if k_moc == 'COL' or k_moc == 'INC': continue

                # create a filter list by offsetting code across the inc list
                temp_moc = moc_filter[:]
                i = 0
                for i_moc in inc:
                    temp_moc[i_moc] = k_moc[i]
                    i += 1

                # create the output
                temp_df = self.filter_moc(temp_moc, inplace=False)
                output[k_moc] = str(len(temp_df))

            possible.append(output)
        return possible

    @timed('get_table')
    def get_table(self, d_col, x_col, y_col, precision=3) -> dict:
        # One grouped aggregation replaces the old O(|x_unique| * |y_unique|) nested-filter
        # sweep (a filter(x == ix) then filter(y == iy) per cell). Crosstabs are NEVER
        # disk-cached (computed fresh per request), so there is no .bin compatibility risk
        # here -- the only bar is exact display parity with the old per-cell path, which the
        # reshape below preserves cell-for-cell (request-path optimization Phase 4):
        #   * every (ix, iy) in x_unique x y_unique still gets a cell (empty ones -> N=0), and
        #   * NaN row/column keys are still emitted -- the old filter(col == ix) matched no rows
        #     when ix was NaN (NaN == NaN is False), so those cells were all N=0 / 'N/A'.
        #     build_crosstab and the treemap/scatter builders drop NaN keys downstream, but
        #     get_table's historical output carried them, so we keep emitting them.
        scale = 10 ** precision

        x_unique = self.df[x_col].unique()
        y_unique = self.df[y_col].unique()

        # observed=True keeps only the (x, y) combinations actually present in the slice;
        # dropna=True (the default) omits any group whose x or y key is NaN -- matching the old
        # path exactly (== NaN never selected a row). Absent combinations default to N=0 below.
        grouped = self.df.groupby([x_col, y_col], observed=True)
        counts = grouped.size().to_dict()               # {(ix, iy): N}

        means = medians = stds = None
        if d_col:
            # Per-group Series reductions -- NOT a vectorized groupby.agg. groupby's Cython
            # mean/std kernels accumulate the sum in a different order than Series.mean/std,
            # which can differ by a ULP and flip a value sitting exactly on a rounding boundary
            # (measured: one cell went '33.007' vs '33.008' at 33.0075). Iterating the observed
            # groups and calling the SAME Series reductions the old per-cell path used -- over
            # the SAME rows in the SAME order (groupby is stable within a group) -- reproduces
            # the old numbers bit-for-bit. Only observed (non-empty) groups are visited, so this
            # is still far cheaper than the old O(cells) double boolean-mask filtering; empty
            # cells fall through to 'N/A' below. mean/median skip NaN and std is sample std
            # (ddof=1) -- the same defaults the old per-cell reductions used.
            means, medians, stds = {}, {}, {}
            for key, col in grouped[d_col]:
                m = col.mean()
                if pd.notna(m): means[key] = m
                md = col.median()
                if pd.notna(md): medians[key] = md
                sd = col.std()
                if pd.notna(sd): stds[key] = sd

        def fmt(value):
            # 'N/A' when the aggregate is absent (empty cell, or an all-NaN / 1-row group whose
            # reduction was NaN and so was never stored), else the identical
            # str(round(v * scale) / scale) the nested-loop path produced.
            if value is None:
                return 'N/A'
            return str(round(value * scale) / scale)

        sheet = {}
        for ix in x_unique:
            row = {}
            for iy in y_unique:
                cell = {'N': int(counts.get((ix, iy), 0))}
                if d_col:
                    key = (ix, iy)
                    cell['mean'] = fmt(means.get(key))
                    cell['mdn'] = fmt(medians.get(key))
                    cell['std'] = fmt(stds.get(key))
                row[iy] = cell
            sheet[ix] = row

        return sheet

    def get_numeric_columns(self) -> list:

        output = []

        for ic in self.df.keys():
            if self.df[ic].dtype == 'float64':
                output.append(str(ic))

        return output

    def distinct_counts(self, *cols) -> list:
        # Number of distinct non-null values per column over the current filtered view.
        # Read-only by contract: Series.nunique returns a scalar and never mutates self.df
        # (the shared base stays immutable, guarded by test_base_immutability.py). Used by the
        # scatter lattice guard to reject a pathologically high-cardinality column pair BEFORE
        # paying get_table's O(|x_unique| * |y_unique|) nested-filter build.
        return [int(self.df[c].nunique(dropna=True)) for c in cols]

    def aggregate_by_group(self, group_column, measure, aggregate, source=None) -> dict:
        # Map (group_column, measure, aggregate) -> {group_value: value} over the current
        # filtered view. This is the one shared aggregation path the Visualize tiers reuse:
        # it feeds choropleth fills, waterfall/treemap values, and bubble sizes
        # (VISUALIZATION_EXPANSION.md §6.1). measure == COUNT_MEASURE ('#') counts cases;
        # otherwise measure is a numeric column aggregated by `aggregate`.
        #
        # Read-only by contract: groupby + the reductions below return NEW objects, so the
        # shared base is never mutated (guarded by test_base_immutability.py). Returns raw
        # numeric values (not the rounded strings get_column_info/get_table return) because
        # the consumers are charts/color-scales; presentation rounds for display.

        # no source means self.df is used
        if source is None: source = self.df

        if aggregate not in self.VALID_AGGREGATES:
            raise ValueError(str(aggregate) + " is not a valid aggregate.")

        # observed=True so a categorical group key (e.g. county) yields only the groups
        # actually present in the slice -- absent geographies are omitted, not emitted as
        # NaN. sort=True (the default) leaves the returned dict in sorted group-key order.
        grouped = source.groupby(group_column, observed=True)

        if aggregate == 'count':
            # count-of-cases per group; the measure is irrelevant to a plain count. Matches
            # Compare's N = len(cell), so a count map reconciles with the crosstab exactly.
            series = grouped.size()
        else:
            # mean/median/mode aggregate a numeric column, so '#' (count-of-cases) has
            # nothing to reduce -- reject it rather than silently returning counts.
            if measure == self.COUNT_MEASURE:
                raise ValueError(aggregate + " needs a numeric measure, not '" + self.COUNT_MEASURE + "'.")
            column = grouped[measure]
            if aggregate == 'mean':
                series = column.mean()
            elif aggregate == 'median':
                series = column.median()
            else:  # mode -- first modal value per group (ties -> first, like get_column_info)
                series = column.agg(_first_mode)

        return series.to_dict()

    def aggregate_by_two(self, group_a, group_b, measure, aggregate, source=None) -> dict:
        # Map (group_a, group_b, measure, aggregate) -> a nested {a_value: {b_value: value}}
        # matrix over the current filtered view -- the two-group sibling of
        # aggregate_by_group. This is the one shared two-group aggregation the wave-2
        # Visualize charts reuse: grouped / stacked / 100%-stacked / stacked-area / slope /
        # bump / mosaic / animated all read this matrix (CHART_LIBRARY_EXPANSION.md §5).
        # Like aggregate_by_group it returns RAW numeric values (not the rounded strings
        # get_table returns) -- the consumers are charts and presentation rounds for display.
        #
        # Read-only by contract: the groupby + the reductions below all return NEW objects,
        # so the shared base/slice is never mutated (guarded by test_base_immutability.py).
        #
        # Built on the request-path Phase 4 single-pass pattern -- ONE groupby([a, b])
        # over the (a, b) lattice, then per-group Series reductions for the measure. It is
        # deliberately NOT groupby.agg / groupby.mean: those Cython kernels accumulate the
        # sum in a different order than Series.mean/median and can flip a value sitting on a
        # rounding boundary by a ULP (get_table carries the same warning). Iterating the
        # observed groups and calling the SAME Series reduction a nested
        # (a == av) & (b == bv) filter would use reproduces that oracle cell-for-cell -- the
        # property test_base_immutability.py's aggregate_by_two oracle pins.

        # no source means self.df is used
        if source is None: source = self.df

        if aggregate not in self.VALID_AGGREGATES:
            raise ValueError(str(aggregate) + " is not a valid aggregate.")

        # observed=True keeps only the (a, b) combinations actually present in the slice
        # (absent combos are omitted, not emitted -- the renderer fills gaps, matching
        # aggregate_by_group's per-group contract); dropna=True (the default) drops any
        # group whose a- or b-key is NaN, exactly as a nested `col == NaN` filter selects
        # no rows. sort=True (the default) yields keys in sorted (a, b) order.
        grouped = source.groupby([group_a, group_b], observed=True)

        if aggregate == 'count':
            # count-of-cases per (a, b) cell; the measure is irrelevant to a plain count.
            # Cast to Python int (like get_table) -- a nested len() oracle returns int and
            # the matrix feeds JSON chart payloads downstream.
            cells = {key: int(n) for key, n in grouped.size().to_dict().items()}
        else:
            # mean/median/mode aggregate a numeric column, so '#' (count-of-cases) has
            # nothing to reduce -- reject it rather than silently returning counts.
            if measure == self.COUNT_MEASURE:
                raise ValueError(aggregate + " needs a numeric measure, not '" + self.COUNT_MEASURE + "'.")
            cells = {}
            for key, col in grouped[measure]:
                if aggregate == 'mean':
                    cells[key] = col.mean()
                elif aggregate == 'median':
                    cells[key] = col.median()
                else:  # mode -- first modal value (ties -> smallest, like get_column_info)
                    cells[key] = _first_mode(col)

        # reshape the flat {(a, b): value} into the nested {a: {b: value}} matrix, keeping
        # the sorted group order the groupby produced (dict insertion order == iteration
        # order in the sorted key stream).
        matrix = {}
        for (av, bv), value in cells.items():
            matrix.setdefault(av, {})[bv] = value
        return matrix

    @timed('distribution_stats')
    def distribution_stats(self, column, group_column=None, bins=None,
                           bandwidth=None, source=None) -> dict:
        # The one shared distribution engine behind the wave-2 histogram / ECDF / KDE / box /
        # violin charts (CHART_LIBRARY_EXPANSION.md §5, Phase B2). numpy-only -- NO scipy.
        # Computes, over the current filtered view (optionally split by a categorical
        # group_column), per block:
        #   * a five-number summary + 1.5*IQR Tukey whiskers, with outliers SUMMARIZED as
        #     counts (never a raw outlier array -- 294k rows can carry thousands of them);
        #   * a histogram (Freedman-Diaconis default bin count, capped; `bins` overrides);
        #   * an ECDF built from the cumulative sum of the vectorized value counts (distinct
        #     values only, downsampled to ECDF_MAX_POINTS -- never the raw points); and
        #   * a binned Gaussian KDE (linear binning onto a shared grid + kernel convolution,
        #     Silverman-rule bandwidth default; `bandwidth` overrides).
        #
        # Read-only by contract: every op below (dropna / to_numpy / groupby / percentile /
        # unique) returns a NEW object, so the shared base/slice is never mutated (guarded by
        # test_base_immutability.py). Returns RAW numeric payloads cast to Python float/int
        # (presentation rounds downstream) -- like aggregate_by_group/two, the consumers are
        # charts. Fresh-computed per request and never disk-cached (cache.distribution_stats).
        #
        # The histogram `bin_edges` and the `kde_grid` are derived ONCE from the whole column
        # and SHARED across every group block, so grouped histograms/KDEs sit on one common
        # axis and are directly comparable (an overlay/violin reads groups off the same grid).

        # no source means self.df is used
        if source is None: source = self.df

        # numeric-only, matching the float64 gate everywhere else (get_numeric_columns,
        # get_column_info's stats branch): a distribution needs an ordered numeric axis.
        if source[column].dtype != 'float64':
            raise ValueError(str(column) + " is not a numeric column; distribution stats need float64.")

        # validate + cap the overrides up front
        if bins is not None:
            bins = int(bins)
            if bins < 1:
                raise ValueError("bins must be a positive integer.")
            bins = min(bins, HISTOGRAM_MAX_BINS)
        if bandwidth is not None:
            bandwidth = float(bandwidth)
            if bandwidth <= 0:
                raise ValueError("bandwidth must be positive.")

        overall_vals = _finite_values(source[column])
        n_overall = overall_vals.size

        # whole column is empty/all-NaN: nothing to summarize -- return a degenerate shell.
        if n_overall == 0:
            return {
                'column': column,
                'group_column': group_column,
                'n': 0,
                'domain': None,
                'bin_edges': [],
                'kde_grid': None,
                'overall': _empty_distribution_block(0),
                'groups': ({} if group_column is not None else None),
            }

        # shared axis derived once from the whole column ----------------------------------
        overall_summary = _five_number_summary(overall_vals)
        data_min, data_max = overall_summary['min'], overall_summary['max']

        if bins is not None:
            n_bins = bins
        else:
            n_bins = _fd_bin_count(n_overall, overall_summary['q1'],
                                   overall_summary['q3'], data_min, data_max)
            n_bins = max(1, min(n_bins, HISTOGRAM_MAX_BINS))
        # shared edges span exactly [data_min, data_max]; every group's values are a subset
        # of that range, so no group point ever falls outside the shared histogram.
        bin_edges = np.histogram_bin_edges(overall_vals, bins=n_bins, range=(data_min, data_max))

        overall_bw = (bandwidth if bandwidth is not None
                      else _silverman_bandwidth(n_overall, overall_summary['std'],
                                                overall_summary['iqr']))
        # KDE grid: pad by 4 bandwidths so the (4-bandwidth) Gaussian kernel fits inside the
        # grid at the data edges (bounded boundary mass loss); sized to KDE_GRID_STEPS_PER_BW
        # grid steps per bandwidth so the discretized kernel isn't aliased (an undersampled
        # grid overshoots the unit integral), clamped to [KDE_GRID_MIN, KDE_GRID_MAX]. None
        # when the KDE is degenerate (single distinct value / zero spread -> no curve to draw).
        grid = None
        kde_min_bw = 0.0
        kde_max_bw = 0.0
        if overall_bw > 0 and data_max > data_min:
            pad = 4.0 * overall_bw
            span = (data_max - data_min) + 2.0 * pad
            n_grid = min(max(KDE_GRID_MIN,
                             int(math.ceil(KDE_GRID_STEPS_PER_BW * span / overall_bw)) + 1),
                         KDE_GRID_MAX)
            grid = np.linspace(data_min - pad, data_max + pad, n_grid)
            dx = span / (n_grid - 1)  # == grid[1] - grid[0]
            # Floor every block's KDE bandwidth at the grid resolution: a bandwidth finer than
            # the grid can't be shown and would alias the binned KDE off the exact one. Only
            # bites when a tiny Silverman bandwidth over a wide range clamps the grid at MAX
            # (e.g. `time`/`aggsentc`, whose outlier tails stretch the range while 294k rows
            # shrink the bandwidth). In the common case bw sits between the two bounds.
            kde_min_bw = KDE_GRID_STEPS_PER_BW * dx
            # Cap it too: the kernel spans half = ceil(4*bw/dx) grid steps each side, so bw must
            # stay small enough that 2*half+1 <= n_grid or np.convolve(mode='same') would return
            # an array LONGER than the grid (kde misaligned from kde_grid). A bandwidth this wide
            # is smoother than the grid window can show anyway, so clamp it here (reported
            # honestly as the block bandwidth). At the cap the kernel's 4-sigma reach is exactly
            # the half-grid width, so its tail mass is still negligible -- no shape distortion.
            kde_max_bw = ((n_grid - 1) // 2) * dx / 4.0

        def build_block(vals, summ=None, bw=None):
            # summ/bw let the overall block reuse the whole-column summary + bandwidth the
            # shared axis already computed, instead of a second _five_number_summary +
            # _silverman pass over the (up to 294k-row) full array.
            n = vals.size
            if n == 0:
                return _empty_distribution_block(len(bin_edges) - 1 if len(bin_edges) else 0)
            if summ is None:
                summ = _five_number_summary(vals)
            if bw is None:
                bw = (bandwidth if bandwidth is not None
                      else _silverman_bandwidth(n, summ['std'], summ['iqr']))
            block = {'n': int(n)}
            block.update(summ)
            block['hist_counts'] = _histogram_counts(vals, bin_edges)
            block['ecdf'] = _ecdf_from_values(vals)
            if grid is not None and bw > 0:
                # keep the kernel resolved by AND fitting within the grid (see the kde_min_bw /
                # kde_max_bw notes above): floor then cap the bandwidth to the grid's window.
                bw_eff = min(max(bw, kde_min_bw), kde_max_bw)
                block['kde'] = _binned_kde(vals, grid, bw_eff)
                block['bandwidth'] = float(bw_eff)
            else:
                block['kde'] = None
                block['bandwidth'] = None
            return block

        overall_block = build_block(overall_vals)

        groups_out = None
        if group_column is not None:
            # reject a pathological split (e.g. a case-id column) before paying for it, so the
            # payload stays bounded; realistic categorical/geographic splits pass comfortably.
            n_groups = int(source[group_column].nunique(dropna=True))
            if n_groups > DISTRIBUTION_MAX_GROUPS:
                raise ValueError("grouping by '" + str(group_column) + "' yields "
                                 + str(n_groups) + " groups (max " + str(DISTRIBUTION_MAX_GROUPS)
                                 + ") -- filter to fewer groups first.")
            groups_out = {}
            # observed=True yields only the groups present in the slice; within-group row order
            # matches a boolean `col == g` mask, so each block is byte-identical to the direct
            # slice the oracle checks (test_distribution_stats_matches_numpy_oracle).
            for gval, sub in source.groupby(group_column, observed=True)[column]:
                groups_out[gval] = build_block(_finite_values(sub))

        return {
            'column': column,
            'group_column': group_column,
            'n': int(n_overall),
            'domain': {'min': float(data_min), 'max': float(data_max)},
            'bin_edges': [float(e) for e in bin_edges],
            'kde_grid': ([float(g) for g in grid] if grid is not None else None),
            'overall': overall_block,
            'groups': groups_out,
        }

    def kde_density(self, column, source=None) -> dict:
        # The read behind the KDE chart (chart-library-expansion Phase D2): a smooth density curve
        # for one numeric column over the current filtered view, WITH the loudest honesty guardrail
        # in the library. Reuses the numpy-only B2 engine (distribution_stats) for the shared grid,
        # the Freedman-Diaconis histogram (the chart's companion table + the spikiness probe), the
        # five-number summary, and the Silverman default bandwidth; ADDS the pre-convolution
        # linear-binned gridded WEIGHTS (_linear_bin) so the client can convolve them with a
        # Gaussian kernel at ANY bandwidth with no refetch -- the same "re-slice a server payload"
        # idiom as the histogram bin slider / the "Other"-cutoff slider. The weights are a
        # <= KDE_GRID_MAX-point density: fully summarized, never raw per-row values. Fresh per
        # request, never disk-cached (cache.kde_density).
        #
        # Read-only by contract: distribution_stats / value_counts / _linear_bin each return NEW
        # objects, so the shared base/slice is never mutated (guarded by test_base_immutability.py).
        if source is None: source = self.df

        # distribution_stats does the float64 gate, the shared-grid sizing, the FD histogram, the
        # five-number summary AND the Silverman bandwidth in one pass -- reuse it wholesale rather
        # than duplicating that logic. (It raises on a non-float64 column, so kde_density inherits
        # the numeric gate for free.)
        stats = self.distribution_stats(column, source=source)
        block = stats['overall']
        n = stats['n']

        # Spikiness (the honesty guardrail, CHART_LIBRARY_EXPANSION.md §8): the share of cases
        # sitting on the KDE_SPIKY_TOP_K most common EXACT values. A round-number-clustered column
        # (sentence lengths on 12/24/36/48/60 months) piles a large share on a few values -- exactly
        # what a KDE smooths away -- while a genuinely continuous column spreads its mass thin. One
        # value_counts pass (O(n)); the top values are reported so the chart can name them.
        vc = source[column].value_counts()               # dropna, descending by count
        n_distinct = int(vc.size)
        top_k = min(KDE_SPIKY_TOP_K, n_distinct)
        top_share = (float(vc.iloc[:top_k].sum()) / n) if n else 0.0
        top_values = [{'value': float(v), 'share': (float(c) / n if n else 0.0)}
                      for v, c in vc.iloc[:top_k].items()]
        spiky = bool(n and top_share >= KDE_SPIKY_SHARE)

        result = {
            'column': column,
            'n': int(n),
            'domain': stats['domain'],
            'bin_edges': stats['bin_edges'],          # FD histogram edges (companion table)
            'hist_counts': block['hist_counts'],      # FD histogram counts (companion table)
            'median': block['median'], 'q1': block['q1'], 'q3': block['q3'],
            'min': block['min'], 'max': block['max'], 'mean': block['mean'],
            'std': block['std'], 'n_outliers': block['n_outliers'],
            'n_distinct': n_distinct,
            'top_share': top_share, 'top_k': top_k, 'top_values': top_values, 'spiky': spiky,
            # KDE curve ingredients -- None when the column is degenerate (single value / zero
            # spread), in which case there is no curve to draw and the chart shows only the histogram.
            'kde_grid': stats['kde_grid'],
            'kde_weights': None,
            'bandwidth': block['bandwidth'],   # Silverman default (effective: floored + capped to grid)
            'bandwidth_min': None,             # below this the kernel is finer than the grid (aliases)
            'bandwidth_max': None,             # above this the kernel wouldn't fit the grid window
        }

        grid = stats['kde_grid']
        if grid is not None and block['bandwidth'] is not None:
            g = np.asarray(grid, dtype=float)
            x = _finite_values(source[column])           # same finite array B2's overall block used
            result['kde_weights'] = [float(w) for w in _linear_bin(x, g)]
            # dx from the grid ENDPOINTS -- the same value the client (visualize.js) derives, so the
            # bounds, the JS clamp, and the JS convolution all agree. These are the two bounds
            # distribution_stats floors/caps its own bandwidth to (kde_min_bw/kde_max_bw), recomputed
            # from the returned grid so the client can't drive np.convolve off the grid.
            dx = (g[-1] - g[0]) / (g.size - 1)
            bw_min = KDE_GRID_STEPS_PER_BW * dx
            bw_max = ((g.size - 1) // 2) * dx / 4.0
            # distribution_stats computed its span as (max-min)+2*pad while we take the endpoint
            # difference, so the already floored/capped default can land ~1 ULP outside [bw_min,
            # bw_max]. Widen the bounds to include it so the default always lies within the slider
            # range and the JS clamp never nudges the initial curve off the server's KDE.
            auto = block['bandwidth']
            result['bandwidth_min'] = float(min(bw_min, auto))
            result['bandwidth_max'] = float(max(bw_max, auto))

        return result

    def bin2d(self, col_x, col_y) -> dict:
        # 2D histogram of two numeric columns over the current filtered view -- the read behind
        # the pair-plot / SPLOM off-diagonal panels (CHART_LIBRARY_EXPANSION.md §4, Phase B3).
        # ONE np.histogram2d over the jointly-finite (x, y) pairs, with a CAPPED bin count per
        # axis: a low-cardinality ("discrete") column bins onto its natural value lattice (one
        # bin per distinct value), a high-cardinality column onto BIN2D_MAX_BINS equal-width
        # bins. NEVER one mark per row -- 294k points overplot into noise; the whole point of a
        # SPLOM panel is the binned density. Like the other wave-2 engines it returns a RAW
        # numeric payload (counts + edges; the renderer draws them), is fresh-computed per
        # request, and is NEVER disk-cached (cache.bin2d).
        #
        # Read-only by contract: nunique / dropna / to_numpy / np.unique / np.histogram2d each
        # return NEW objects, so the shared base/slice is never mutated (guarded by
        # test_base_immutability.py). No source= param -- like get_table / distinct_counts it
        # reads self.df, and the cache wrapper sets self.df to the active slice.

        # numeric-only, matching the float64 gate everywhere else (get_numeric_columns,
        # distribution_stats): a 2D density needs two ordered numeric axes.
        for c in (col_x, col_y):
            if self.df[c].dtype != 'float64':
                raise ValueError(str(c) + " is not a numeric column; bin2d needs float64.")

        # whole-column distinct counts decide each axis's binning: reuse distinct_counts -- the
        # same cardinality measure the scatter lattice guard uses. <= cap -> discrete (natural
        # value lattice); > cap -> continuous (capped equal-width bins). A paired axis's uniques
        # are a subset of its whole-column uniques, so a "discrete" axis never yields more than
        # cap lattice bins.
        nx_all, ny_all = self.distinct_counts(col_x, col_y)
        x_discrete = nx_all <= BIN2D_MAX_BINS
        y_discrete = ny_all <= BIN2D_MAX_BINS

        # jointly-finite pairs: drop any row where EITHER column is NaN (np.histogram2d needs
        # paired coordinates), matching a scatter/crosstab's both-present cell contract.
        paired = self.df[[col_x, col_y]].dropna()
        n = len(paired)

        if n == 0:
            # nothing to bin -- degenerate shell (stable shape so the renderer never
            # special-cases a missing panel).
            return {
                'column_x': col_x, 'column_y': col_y, 'n': 0,
                'x_discrete': x_discrete, 'y_discrete': y_discrete,
                'x_edges': [], 'y_edges': [], 'counts': [],
            }

        px = paired[col_x].to_numpy(dtype=float)
        py = paired[col_y].to_numpy(dtype=float)

        # np.histogram2d accepts a mixed [edges_array, int] / [int, edges_array] bin spec, so
        # each axis is binned independently: a discrete axis by its lattice edges, a continuous
        # one by the integer cap (numpy then makes that many equal-width bins over the range).
        x_bins = _lattice_edges(px) if x_discrete else BIN2D_MAX_BINS
        y_bins = _lattice_edges(py) if y_discrete else BIN2D_MAX_BINS

        counts, x_edges, y_edges = np.histogram2d(px, py, bins=[x_bins, y_bins])

        return {
            'column_x': col_x,
            'column_y': col_y,
            'n': int(n),
            'x_discrete': x_discrete,
            'y_discrete': y_discrete,
            'x_edges': [float(e) for e in x_edges],
            'y_edges': [float(e) for e in y_edges],
            'counts': [[int(c) for c in row] for row in counts],
        }

    def num_occur(self, col, val) -> int:
        # grandfathered in from cli-legacy

        # calculate the number of times a value occurs in a column
        return len(col[col == val])

    def num_each(self, col) -> dict:
        # grandfathered in from cli-legacy

        # calculate the occurrence of each unique value in a column
        #
        # One value_counts pass (O(n)) replaces the per-unique-value num_occur scan
        # (len(col[col == iu]) for each of k uniques -- O(n*k); request-path optimization
        # Phase 5, order-preserving swap). This dict is pickled into <col>.bin via
        # get_column_info, so its layout is contract:
        #   * keys are the elements of col.unique() itself, in order of appearance -- the
        #     same np.float64/str/np.nan objects, NOT value_counts' index (whose sort
        #     order and key boxing differ);
        #   * values are Python ints (value_counts holds np.int64);
        #   * a NaN key stays 0, exactly as the old `col == nan` never matched a row
        #     (get_column_info derives the real NaN count separately from the not-NaN sum).
        counts = col.value_counts().to_dict()  # dropna: the NaN key is pinned to 0 below
        return {iu: (int(counts.get(iu, 0)) if pd.notna(iu) else 0) for iu in col.unique()}

    def get_unique_cases(self):
        return self.df['dcnum'].unique()

    def has_column(self, column):
        return column in self.df


def _first_mode(series):
    # First modal value of a Series (ties -> the smallest, matching Series.mode()'s sort);
    # NaN when the group is empty / all-NaN. Shared by get_column_info's mode stat and the
    # groupby-mode aggregate so both apply the identical tie rule.
    modes = series.mode()  # dropna=True, sorted ascending
    if len(modes) == 0:
        return float('nan')
    return modes.iloc[0]


# --- distribution-stats engine internals (chart-library expansion Phase B2) ----------
# numpy-only building blocks Data.distribution_stats assembles. Each takes a plain finite
# numpy array (or a Series) and returns JSON-ready Python scalars/lists -- no scipy, no raw
# per-row payloads. Kept at module scope (like _first_mode) so they are independently
# oracle-testable against pandas/numpy.

def _finite_values(series):
    """Non-null values of a Series as a fresh float numpy array (read-only over the source).
    NaNs are dropped, matching the skipna reductions used everywhere else in this module."""
    return series.dropna().to_numpy(dtype=float)


def _five_number_summary(x):
    """Five-number summary + moments + 1.5*IQR Tukey whiskers for a finite array `x`.
    Quartiles use np.percentile's default linear interpolation (== pandas .quantile / the
    median used across the app); std is the sample std (ddof=1, == pandas .std). Whiskers are
    the most extreme data points still within the fences; OUTLIERS ARE SUMMARIZED AS COUNTS
    (no raw outlier array -- CHART_LIBRARY_EXPANSION.md §8). All scalars are Python floats/ints."""
    n = x.size
    q1, median, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    lo_fence = q1 - 1.5 * iqr
    hi_fence = q3 + 1.5 * iqr
    # {x >= lo_fence} and {x < lo_fence} partition x, so the outlier counts fall straight out
    # of the whisker masks' sizes -- no extra boolean-sum passes.
    within_lo = x[x >= lo_fence]  # points not below the low fence
    within_hi = x[x <= hi_fence]  # points not above the high fence
    whisker_low = within_lo.min() if within_lo.size else q1
    whisker_high = within_hi.max() if within_hi.size else q3
    n_out_low = int(n - within_lo.size)
    n_out_high = int(n - within_hi.size)
    return {
        'min': float(x.min()),
        'max': float(x.max()),
        'mean': float(x.mean()),
        'std': (float(x.std(ddof=1)) if n > 1 else None),
        'q1': float(q1),
        'median': float(median),
        'q3': float(q3),
        'iqr': float(iqr),
        'whisker_low': float(whisker_low),
        'whisker_high': float(whisker_high),
        'n_outliers_low': n_out_low,
        'n_outliers_high': n_out_high,
        'n_outliers': n_out_low + n_out_high,
    }


def _fd_bin_count(n, q1, q3, lo, hi):
    """Freedman-Diaconis bin COUNT (the caller caps it): width h = 2*IQR / n**(1/3),
    count = ceil((max-min)/h). Falls back to Sturges (ceil(log2 n)+1) when the IQR or the
    range is zero, mirroring numpy's own 'fd' fallback. Computed WITHOUT materializing the
    edge array, so wide-range data can't blow up memory the way np.histogram(bins='fd') can
    before the cap in distribution_stats applies."""
    if n <= 0:
        return 1
    iqr = q3 - q1
    span = hi - lo
    if iqr > 0 and span > 0:
        width = 2.0 * iqr / (n ** (1.0 / 3.0))
        if width > 0:
            return int(math.ceil(span / width))
    return int(math.ceil(math.log2(n) + 1)) if n > 1 else 1


def _histogram_counts(x, edges):
    """Counts of `x` in the (shared) `edges` bins, as a Python int list aligned to
    len(edges)-1. np.histogram closes the final bin on both ends; since the shared edges span
    the whole column's [min, max] and every group is a subset, no group point is ever dropped."""
    counts, _ = np.histogram(x, bins=edges)
    return [int(c) for c in counts]


def _ecdf_from_values(x):
    """ECDF as the cumulative sum of the vectorized value counts: np.unique returns the
    distinct values (ascending) with their counts in one O(n) pass -- the numpy twin of
    value_counts().sort_index() -- and the ECDF is their normalized cumsum. Downsampled to at
    most ECDF_MAX_POINTS (value, cumulative) pairs, so the raw points never go over the wire."""
    uniq, counts = np.unique(x, return_counts=True)
    cumulative = np.cumsum(counts) / counts.sum()
    uniq, cumulative = _downsample_ecdf(uniq, cumulative, ECDF_MAX_POINTS)
    return {'values': [float(v) for v in uniq],
            'cumulative': [float(c) for c in cumulative]}


def _downsample_ecdf(values, cumulative, max_points):
    """Thin an ECDF (`values` ascending, `cumulative` in (0, 1]) to at most max_points
    evenly-spaced points, always keeping the first and last (so the min value and the 1.0
    endpoint survive and the step function keeps its shape). A no-op when it already fits."""
    m = values.size
    if m <= max_points:
        return values, cumulative
    idx = np.unique(np.linspace(0, m - 1, max_points).round().astype(np.intp))
    return values[idx], cumulative[idx]


def _silverman_bandwidth(n, std, iqr):
    """Silverman's rule-of-thumb Gaussian KDE bandwidth: 0.9 * min(std, IQR/1.349) * n**(-1/5).
    Returns 0.0 when it can't be estimated (n < 2, or zero spread -- a degenerate spike), in
    which case distribution_stats skips the KDE for that block."""
    if n < 2:
        return 0.0
    spread = std if (std and std > 0) else 0.0
    if iqr > 0:
        iqr_sigma = iqr / 1.349
        spread = min(spread, iqr_sigma) if spread > 0 else iqr_sigma
    if spread <= 0:
        return 0.0
    return 0.9 * spread * (n ** (-1.0 / 5.0))


def _linear_bin(x, grid):
    """Linear binning of `x`'s unit weights onto the equally-spaced ascending `grid`: each point
    splits its unit weight between the two bracketing grid nodes (bincount is the vectorized
    scatter-add), so the returned gridded weights SUM TO 1 (indices clipped defensively -- the
    4-bandwidth grid padding already brackets every value). This is the shared front half of the
    binned KDE: _binned_kde convolves these weights with a Gaussian, and the KDE chart ships them
    so the client can convolve at any bandwidth with no refetch (chart-library expansion D2)."""
    n = x.size
    G = grid.size
    dx = (grid[-1] - grid[0]) / (G - 1)
    pos = (x - grid[0]) / dx
    left = np.floor(pos).astype(np.intp)
    frac = pos - left
    lo_idx = np.clip(left, 0, G - 1)
    hi_idx = np.clip(left + 1, 0, G - 1)
    binned = (np.bincount(lo_idx, weights=1.0 - frac, minlength=G)[:G]
              + np.bincount(hi_idx, weights=frac, minlength=G)[:G])
    return binned / n  # normalized gridded weights (sum to 1)


def _binned_kde(x, grid, bandwidth):
    """Binned Gaussian KDE evaluated on `grid` (equally spaced, ascending), numpy-only:
    linear-bin each value's unit weight onto its two nearest grid nodes (_linear_bin), then
    convolve the gridded weights with a Gaussian kernel sampled at the grid spacing (the standard
    fast KDE -- KDEpy/R `density()` in spirit). Returns the density at each grid point as a Python
    list; it integrates to ~1 over the grid by construction, and memory is O(grid) regardless of
    how many points/uniques feed it. The linear-binning approximation is why the oracle checks the
    KDE by properties + shape, not exact float equality (unlike the deterministic stats)."""
    G = grid.size
    dx = (grid[-1] - grid[0]) / (G - 1)
    weights = _linear_bin(x, grid)  # normalized gridded weights (sum to 1)
    # Gaussian kernel K_h(u) = (1/(h*sqrt(2pi))) exp(-u^2/(2 h^2)) sampled on the grid out to
    # +/-4 bandwidths; convolving the gridded weights with it evaluates the KDE at each node.
    half = int(math.ceil(4.0 * bandwidth / dx))
    offsets = np.arange(-half, half + 1) * dx
    kernel = np.exp(-0.5 * (offsets / bandwidth) ** 2) / (bandwidth * math.sqrt(2.0 * math.pi))
    density = np.convolve(weights, kernel, mode='same')
    # renormalize to unit area over the grid (rectangle rule; density ~ 0 at the padded
    # edges), compensating the tiny boundary truncation + discretization so the returned
    # curve is a proper density -- standard for a binned KDE used as a plotted density.
    area = float(density.sum()) * dx
    if area > 0:
        density = density / area
    return [float(v) for v in density]


def _empty_distribution_block(n_bins):
    """A distribution block for an empty (all-NaN / absent) group: zero counts, null stats.
    Keeps the block shape stable so consumers never special-case a missing group."""
    return {
        'n': 0,
        'min': None, 'max': None, 'mean': None, 'std': None,
        'q1': None, 'median': None, 'q3': None, 'iqr': None,
        'whisker_low': None, 'whisker_high': None,
        'n_outliers_low': 0, 'n_outliers_high': 0, 'n_outliers': 0,
        'hist_counts': [0] * n_bins,
        'ecdf': {'values': [], 'cumulative': []},
        'kde': None, 'bandwidth': None,
    }


# --- 2D-binning helper internals (chart-library expansion Phase B3) --------------------
# numpy-only building block Data.bin2d assembles. Kept at module scope (like the B2
# internals) so it is independently oracle-testable against numpy.

def _lattice_edges(values):
    """Bin edges placing one bin around each distinct value of a discrete axis. `values` is a
    finite numpy array; the edges are the midpoints between consecutive sorted uniques, with the
    outer edges a half-gap beyond the ends (a unit half-step for a single distinct value). k
    uniques -> k+1 edges -> k bins, each holding exactly one value; np.histogram2d closes the
    final bin on both ends, so the max value lands in the last bin. This is what makes a SPLOM
    panel show clean rows/columns for a low-cardinality column instead of arbitrary aliasing."""
    u = np.unique(values)  # ascending, deduped
    if u.size == 1:
        return np.array([u[0] - 0.5, u[0] + 0.5])
    mids = (u[:-1] + u[1:]) / 2.0
    left = u[0] - (u[1] - u[0]) / 2.0
    right = u[-1] + (u[-1] - u[-2]) / 2.0
    return np.concatenate(([left], mids, [right]))


def format_column_info(output, sorting, precision=2):

    raw_numbers = output['raw_numbers']

    if sorting == 'reverse_occurrence':
        iterator = raw_numbers.keys()
    elif sorting == 'occurrence':
        iterator = reversed(raw_numbers)

    elif sorting == 'alphanumeric':
        iterator = sorted(raw_numbers.keys())
    elif sorting == 'reverse_alphanumeric':
        iterator = reversed(sorted(raw_numbers.keys()))

    else: iterator = raw_numbers.keys()  # exclusively for pre-cacheing

    for iu in iterator:
        if pd.notna(iu):
            percent = 100 * (raw_numbers[iu] / output['len'])
            each = {}
            each['text'] = str(iu).ljust(20, '-') + '>' + str(raw_numbers[iu])
            each['text'] += '=' + str(round(percent * 10 ** precision) / 10 ** precision) + '%'
            each['value'] = iu
            each['num'] = raw_numbers[iu]
            each['percent'] = percent
            output['each'].append(each)

    return output
