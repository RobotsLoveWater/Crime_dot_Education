# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# precache.py
# data pre-caching

import os
import pickle
from copy import deepcopy
from collections import OrderedDict

from data import Data
from data import format_column_info

import account
from perf.profiling import timed

# Base datafile: prefer the typed columnar Parquet base (Lever C -- ~10x smaller on disk,
# ~20x faster to parse) when it exists, else fall back to the CSV so a machine that only
# built cache/raw.csv still runs. Both are git-ignored; build them with `uv run python
# cache.py`. Repoint DATAFILE (or delete raw.parquet) to force the CSV loader.
DATAFILE_PARQUET = 'cache/raw.parquet'
DATAFILE_CSV = 'cache/raw.csv'
DATAFILE = DATAFILE_PARQUET if os.path.exists(DATAFILE_PARQUET) else DATAFILE_CSV
DATAPATH = 'cache/data/'

EXCLUDED_COLUMNS = [
    'dcnum',
    'lname',
    'mname',
    'fname',
    'dcnum2'
]

def history_item_to_text(item) -> str:

    if item['action'][0] == 'f':  # single filter
        return '.'.join(item['action'])
    elif item['action'][0] == 'o':  # or same filter
        final_text = 'o'
        final_text += '.' + item['action'][1] + '.' + item['action'][2] + '.'
        final_text += '~'.join(item['action'][3])
        return final_text

    # if we got this far, the action code was not valid
    raise ValueError


def history_text_to_item(text) -> dict:
    # inverse of history_item_to_text: turns a state token back into a history entry.
    # used to feed lesson `state` tokens through the override path as real history items.

    parts = text.split('.')
    code = parts[0]

    if code == 'f':  # single filter: f.col.op.val
        action = ['f', parts[1], parts[2], '.'.join(parts[3:])]
    elif code == 'o':  # or same filter: o.col.op.v1~v2~...
        action = ['o', parts[1], parts[2], '.'.join(parts[3:]).split('~')]
    else:
        # if we got this far, the action code was not valid
        raise ValueError

    return {'desc': 'lesson: ' + text, 'action': action}


def get_data(session, column=None, sorting=None, history_override=None, data_override=None) -> dict:

    if session:
        full_history = account.retrieve(session['userid'])['history'][1:]
    else:
        full_history = []

    if history_override:
        full_history = full_history + history_override

    hist = []
    for item in full_history:
        hist.append(history_item_to_text(item))

    code = DATAPATH + '/'.join(hist)

    # bugfix for cacheing
    if code[-1] == '/': code = code[:-1]

    # execute if needed
    exe = False
    if not os.path.exists(code + '/_data.bin'): exe = True
    if column and not os.path.exists(code + '/' + column + '.bin'): exe = True

    # the data will be loaded only when needed
    if exe:

        if data_override:
            temp_data = data_override
        else:
            temp_data = _execute(session, history_override)

        # if there is any need to execute, also create directories along the way
        walk = DATAPATH
        for item in full_history:
            walk += history_item_to_text(item) + '/'
            if not os.path.exists(walk):
                os.mkdir(walk)

    # a cache exists to use
    if os.path.exists(code + '/_data.bin'):

        with open(code + '/_data.bin', 'rb') as handle:
            data = pickle.load(handle)

    # need to generate and cache the data
    else:

        data = {
            'entries': temp_data.get_entries(),
            'columns': temp_data.get_columns_w_codebook(),  # actually the list of codebook entries for columns...
            'column_list': temp_data.get_columns(),  # this is the actual list of columns
            'numeric': temp_data.get_numeric_columns(),
            'excluded': EXCLUDED_COLUMNS
        }

        data['columns_alphanumeric'] = sorted(data['columns'])  # also actually codebook :(

        with open(code + '/_data.bin', 'wb') as handle:
            pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)

    # now, the same for columns
    if column:

        # yep, one exists
        if os.path.exists(code + '/' + column + '.bin'):

            with open(code + '/' + column + '.bin', 'rb') as handle:
                column_info = pickle.load(handle)

        # nope, generate for this specific column
        else:

            column_info = temp_data.get_column_info(column)

            with open(code + '/' + column + '.bin', 'wb') as handle:
                pickle.dump(column_info, handle, protocol=pickle.HIGHEST_PROTOCOL)

        # cache is not specific to column sorting, sorting is done after
        data['column_info'] = format_column_info(column_info, sorting)

    return data


def get_moc_options(session, moc_filter, active):

    full_history = account.retrieve(session['userid'])['history'][1:]

    # encode with the canonical helper so OR-same-column ('o') entries — which carry a
    # list value and would blow up a bare '.'.join — land in the same cache dir the rest
    # of the pipeline uses (single 'f' filters encode identically to the old join)
    hist = []
    for item in full_history:
        hist.append(history_item_to_text(item))
    code = DATAPATH + '/'.join(hist)

    # a cache exists to use
    if os.path.exists(code + '/_moc.bin'):

        with open(code + '/_moc.bin', 'rb') as handle:

            # get the options from disk
            temp_options = pickle.load(handle)

            # test if the filter has been done before
            try:
                return temp_options[str(moc_filter)][int(active)-1]

            # if it doesn't exist do it
            except KeyError:
                temp_options[str(moc_filter)] = _execute(session).get_moc_options(moc_filter)

    else:

        # create a temporary version of the options for saving
        temp_options = {str(moc_filter): _execute(session).get_moc_options(moc_filter)}

    # if we've made it this far we need to save
    with open(code + '/_moc.bin', 'wb') as handle:
        pickle.dump(temp_options, handle, protocol=pickle.HIGHEST_PROTOCOL)

    return temp_options[str(moc_filter)][int(active)-1]


def get_aggregate(session, group_column, measure, aggregate, history_override=None) -> dict:
    # Aggregate the active filtered slice: group_column -> {group_value: value}, via
    # Data.aggregate_by_group. The one session-aware entry point the Visualize tiers call
    # for choropleth fills, waterfall/treemap values, and bubble sizes.
    #
    # Computed FRESH per request and NEVER disk-cached -- the Visualize charts/maps ride
    # the per-request path (like crosstabs and, later, correlations), so this writes no new
    # .bin artifacts and adds nothing to the cache-dir layout. Reads the shared base through
    # _execute, read-only (the base stays immutable). history_override lets a lesson sandbox
    # apply its own state on top without touching the student's stored history.
    return _execute(session, history_override).aggregate_by_group(group_column, measure, aggregate)


def get_aggregate_two(session, group_a, group_b, measure, aggregate, history_override=None) -> dict:
    # Two-group sibling of get_aggregate: aggregate the active filtered slice into a nested
    # {a_value: {b_value: value}} matrix via Data.aggregate_by_two. The one session-aware
    # entry point the wave-2 Visualize charts call for grouped / stacked / 100%-stacked /
    # stacked-area / slope / bump / mosaic / animated payloads (CHART_LIBRARY_EXPANSION.md §5).
    #
    # Computed FRESH per request and NEVER disk-cached -- exactly like get_aggregate and the
    # crosstab/correlation reads: these charts ride the per-request path, so this writes no
    # new .bin artifacts and adds nothing to the cache-dir layout. Reads the shared base
    # through _execute, read-only (the base/slice stays immutable). history_override lets a
    # lesson sandbox apply its own state on top without touching the student's stored history.
    return _execute(session, history_override).aggregate_by_two(group_a, group_b, measure, aggregate)


def distribution_stats(session, column, group_column=None, bins=None, bandwidth=None,
                       history_override=None) -> dict:
    # Distribution engine over the active filtered slice: five-number summary + 1.5*IQR
    # whiskers, histogram, ECDF, and binned KDE per column (optionally split by a categorical
    # group_column), via Data.distribution_stats. The one session-aware entry point the wave-2
    # histogram / ECDF / KDE / box / violin charts call (CHART_LIBRARY_EXPANSION.md §5, B2).
    #
    # Computed FRESH per request and NEVER disk-cached -- exactly like get_aggregate/two and
    # the crosstab/correlation reads: these charts ride the per-request path, so this writes no
    # new .bin artifacts and adds nothing to the cache-dir layout. Reads the shared base
    # through _execute, read-only (the base/slice stays immutable). history_override lets a
    # lesson sandbox apply its own state on top without touching the student's stored history.
    return _execute(session, history_override).distribution_stats(
        column, group_column=group_column, bins=bins, bandwidth=bandwidth)


def kde_density(session, column, history_override=None) -> dict:
    # Density-curve read over the active filtered slice, via Data.kde_density -- the numpy-only
    # engine behind the KDE chart (chart-library-expansion Phase D2). Reuses distribution_stats
    # for the shared grid + FD histogram + Silverman bandwidth, and ADDS the pre-convolution
    # linear-binned gridded weights so the client convolves at any bandwidth with no refetch, plus
    # the spikiness flag driving the "read the histogram instead" nudge (CHART_LIBRARY_EXPANSION.md
    # §8). No raw per-row values leave the server -- the weights are a bounded density array.
    #
    # Computed FRESH per request and NEVER disk-cached -- exactly like get_aggregate/two,
    # distribution_stats, and bin2d: these charts ride the per-request path, so this writes no new
    # .bin artifacts and adds nothing to the cache-dir layout. Reads the shared base through
    # _execute, read-only (the base/slice stays immutable). history_override lets a lesson sandbox
    # apply its own state on top without touching the student's stored history.
    return _execute(session, history_override).kde_density(column)


def bin2d(session, col_x, col_y, history_override=None) -> dict:
    # 2D-binned density of two numeric columns over the active filtered slice, via Data.bin2d
    # -- the read behind the pair-plot / SPLOM off-diagonal panels (CHART_LIBRARY_EXPANSION.md
    # §4, Phase B3): one np.histogram2d grid (counts + edges), capped bins, discrete columns on
    # their natural value lattice.
    #
    # Computed FRESH per request and NEVER disk-cached -- exactly like get_aggregate/two and
    # distribution_stats: these charts ride the per-request path, so this writes no new .bin
    # artifacts and adds nothing to the cache-dir layout. Reads the shared base through
    # _execute, read-only (the base/slice stays immutable). history_override lets a lesson
    # sandbox apply its own state on top without touching the student's stored history.
    return _execute(session, history_override).bin2d(col_x, col_y)


# --- base DataFrame singleton (Lever B: load the base once per process) -----------
# The base (full-dataset) frame is identical for every request and is never mutated
# in place — filters return new frames via boolean indexing (see the immutability
# guardrail in test_base_immutability.py). So parse cache/raw.csv exactly once per
# process and hand every cache miss the same shared frame instead of re-reading the
# 242 MB CSV each time. History-specific results still live only in the disk cache.
_BASE = None
_BASE_FINGERPRINT = None  # (shape, id) captured at first load; debug-only tripwire


def _base_df():
    """Return the process-wide base DataFrame, loading it once on first use.

    The frame is shared and read-only by contract: callers assign it to a fresh
    Data().df and the first filter replaces that reference with a new frame, so the
    shared base is never reassigned or mutated. Do not mutate it in place.
    """
    global _BASE, _BASE_FINGERPRINT

    if _BASE is None:
        loader = Data()
        loader.load(DATAFILE)
        _BASE = loader.df
        _BASE_FINGERPRINT = (_BASE.shape, id(_BASE))

    # Debug-only tripwire (stripped under `python -O`): if any request mutated the
    # base in place, its shape/identity would have drifted from the first load.
    assert (_BASE.shape, id(_BASE)) == _BASE_FINGERPRINT, \
        'base DataFrame mutated between requests (shape/identity drift)'

    return _BASE


# --- county -> district / region crosswalk (Phase 7 geo foundation) ----------------
# Every row already carries county + district + region, so the dissolve mappings a
# district/region choropleth needs are DERIVED from the data (df.groupby('county')
# [...].first()) -- there are no external crosswalk files, only the vendored county
# TopoJSON. Verified functional: no county spans >1 district or >1 region, so .first()
# is exact (yields 10 districts + 4 regions). Memoized once per process next to _base_df;
# read-only over the shared base (groupby returns new objects -- the base stays immutable,
# guarded by test_base_immutability.py).
COUNTY_COLUMN = 'county'
CROSSWALK_COLUMNS = ['district', 'region']
_COUNTY_CROSSWALK = None  # {'district': {county: d}, 'region': {county: r}}


def _county_crosswalk() -> dict:
    """Return the process-wide county->{district, region} crosswalk, built once.

    Structure: {'district': {county_name: district_value},
                'region':   {county_name: region_value}}.
    Keys are the dataset's own county spellings (geo.py reconciles them to map
    feature names). District values are float (e.g. 4.0), matching the numeric-filter
    encoding a map-click emits (f.district.eq.4.0).
    """
    global _COUNTY_CROSSWALK

    if _COUNTY_CROSSWALK is None:
        base = _base_df()
        # observed=True: only the counties actually present; .first() is exact because
        # each county maps to a single district and region (see the module note above).
        grouped = base.groupby(COUNTY_COLUMN, observed=True)[CROSSWALK_COLUMNS].first()
        _COUNTY_CROSSWALK = {
            'district': grouped['district'].to_dict(),
            'region': grouped['region'].to_dict(),
        }

    return _COUNTY_CROSSWALK


def county_values() -> list:
    """Sorted list of the distinct county names present in the base dataset."""
    return sorted(_county_crosswalk()['district'].keys())


# --- filtered-slice LRU (Phase 3: memoize per-history-token filtered frames) --------
# Lever B memoized the *base*; every cache miss on a *filtered* state still replays the
# whole filter chain from the base. Viewing N columns of one filter state is N requests,
# each re-filtering the identical slice (flow (a) logged 9 _execute calls for 8 column
# views); a cold column render even replays twice in one page (render_explore's two
# get_data calls). This bounded LRU holds the already-filtered frame keyed by the canonical
# history-token tuple get_data builds its cache dir from, so repeat views of the same state
# hand back the shared frame instead of re-filtering.
#
# Bounded so a session walking many states can't grow memory without limit. Each slice is a
# row-subset far smaller than the base and shares its category index with the base, so a
# handful of entries is cheap. Callers treat the frame read-only (filter(inplace=False) /
# aggregate_by_group(source=) / get_table all return new frames), exactly as they treat the
# shared base -- so the same immutability contract (test_base_immutability.py) covers it.
_FILTERED_CACHE_MAX = 8
_filtered_cache = OrderedDict()       # token tuple -> filtered df (base excluded)
_filtered_fingerprints = {}           # token tuple -> (shape, id); debug-only tripwire


def _slice_key(history) -> tuple:
    """Canonical LRU key for a history: the filter-token tuple (the base entry at index 0
    excluded, any override already appended). Identical to the '/'.join(...) path get_data
    keys its disk cache dir on, so a slice can never be served for the wrong state -- the
    same failure mode test_map_filter_equivalence.py guards for cache dirs."""
    return tuple(history_item_to_text(item) for item in history[1:])


def _filtered_cache_insert(key, df) -> None:
    _filtered_cache[key] = df
    _filtered_cache.move_to_end(key)
    _filtered_fingerprints[key] = (df.shape, id(df))
    while len(_filtered_cache) > _FILTERED_CACHE_MAX:
        evicted, _ = _filtered_cache.popitem(last=False)  # drop the least-recently-used
        _filtered_fingerprints.pop(evicted, None)


def _clear_filtered_cache() -> None:
    """Drop every cached slice. Used by the guardrail test and the benchmark to force a
    genuinely cold run; not needed in normal operation (the LRU self-bounds)."""
    _filtered_cache.clear()
    _filtered_fingerprints.clear()


def _execute(session, history_override=None) -> Data:
    """Return a Data wrapping the filtered slice for this session (+ any lesson override).

    Serves the frame from the in-memory LRU when warm, else replays the history from the
    base (the timed, expensive path -- see _replay_history) and caches the result. The base
    (empty-filter) state is never cached: it IS the shared _base_df() singleton. The frame
    is handed out read-only by contract, exactly like _base_df().
    """
    if session:
        history = account.retrieve(session['userid'])['history']
    else:
        history = [{'desc': 'Error', 'action': None}]

    # lesson states are applied as an override on top of the base history; they are
    # never merged into the student's stored history (lessons are strictly sandboxed).
    if history_override:
        history = history + history_override

    temp_data = Data()

    key = _slice_key(history)

    # an empty filter chain IS the base itself -- hand back the shared base, never cache it.
    if not key:
        temp_data.df = _base_df()
        return temp_data

    cached = _filtered_cache.get(key)
    if cached is not None:
        _filtered_cache.move_to_end(key)  # mark most-recently-used
        # debug-only tripwire (stripped under `python -O`), mirroring _base_df: a served
        # slice must not have drifted in shape/identity since it was cached.
        assert (cached.shape, id(cached)) == _filtered_fingerprints[key], \
            'filtered slice mutated between requests (shape/identity drift)'
        temp_data.df = cached
        return temp_data

    # miss: replay the chain from the base (the one expensive path, timed as '_execute'),
    # then cache the resulting slice for the next viewer of this same state.
    _replay_history(temp_data, history)
    _filtered_cache_insert(key, temp_data.df)
    return temp_data


@timed('_execute')
def _replay_history(temp_data, history) -> None:
    # The actual base-replay -- runs ONLY on a slice-cache miss (the LRU short-circuit in
    # _execute returns before reaching here on a hit). This is what the benchmark's
    # '_execute' counter now measures: in Phase 0 every _execute was a real replay, so
    # 'apply filter -> view 8 columns' logged 9; the slice cache collapses the 8 repeat
    # column views to LRU hits, leaving 1 real replay. Mutates the passed-in temp_data.df.
    for item in history:
        if item['action']:
            action = item['action']

            # action is what the action is, exclusively filter (0) for now

            if action[0] == 'f':

                temp_data.filter(action[1], action[2], action[3])

            elif action[0] == 'o':

                temp_data.filter_or_same(action[1], action[2], action[3])

            else:
                raise ValueError

        else:
            # base entry: point at the shared, load-once base instead of re-parsing
            # the CSV. temp_data.df is None here (fresh Data), and the first filter
            # above replaces this reference with a new frame, so the base stays pristine.
            temp_data.df = _base_df()


def cache_info(loaded_data, columns, history_list=None):

    for kc, vc in enumerate(columns):
        if vc not in EXCLUDED_COLUMNS:
            print(vc + ' starting')
            get_data(None, vc, data_override=deepcopy(loaded_data))
            print(vc + ' done (' + str(kc) + '/' + str(len(columns)+1) + ')')


if __name__ == '__main__':
    dataobj = Data()
    dataobj.load('dataset.sav')

    if input('will you create a raw csv? ').lower() == 'y':
        dataobj.save('cache/raw')
        print('created raw csv')

    if input('will you create a raw parquet? ').lower() == 'y':
        # Build the Parquet base from cache/raw.csv (not dataset.sav): the CSV round-trip
        # is what produces the exact dtypes/values the runtime loads and the cache was
        # warmed against, so mirroring it keeps results byte-identical. Needs raw.csv.
        if os.path.exists(DATAFILE_CSV):
            csv_base = Data()
            csv_base.load(DATAFILE_CSV)
            csv_base.save_parquet('cache/raw')
            print('created raw parquet')
        else:
            print('skipped: ' + DATAFILE_CSV + ' not found -- create the raw csv first')

    cache_list = dataobj.get_columns()

    if input('will you cache info? ').lower() == 'y':
        cache_info(dataobj, cache_list)
