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
