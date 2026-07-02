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

DATAFILE = 'cache/raw.csv'
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

    hist = []
    for item in full_history:
        hist.append('.'.join(item['action']))
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
            temp_data.load(DATAFILE)

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

    cache_list = dataobj.get_columns()

    if input('will you cache info? ').lower() == 'y':
        cache_info(dataobj, cache_list)
