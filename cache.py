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

from data import Data
from data import format_column_info

import account

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


def _execute(session, history_override=None) -> Data:

    temp_data = Data()

    if session:
        history = account.retrieve(session['userid'])['history']
    else:
        history = [{'desc': 'Error', 'action': None}]

    # lesson states are applied as an override on top of the base history; they are
    # never merged into the student's stored history (lessons are strictly sandboxed).
    if history_override:
        history = history + history_override

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

    return temp_data


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
