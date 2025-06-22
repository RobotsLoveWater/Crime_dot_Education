# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Social Science Component:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# account.py
# manages accounts

import os
import pickle


NO_CLASS_CODE = 'unmanaged'


def clean_classcode(classcode) -> str:
    if classcode is None or classcode == '': return NO_CLASS_CODE
    else: return classcode


def get_classcode_list() -> list[str]: return os.listdir('user')


def get_user_list(classcode) -> list[str]:

    # set as unmanaged if no classcode was used
    classcode = clean_classcode(classcode)

    if os.path.exists('user/' + classcode):

        return os.listdir('user/' + classcode)

    else:

        return []


def get_user_directory(userid) -> str: return 'user/' + userid + '.pickle'


def form_userid(username, classcode) -> str:

    # set as unmanaged if no classcode was used
    classcode = clean_classcode(classcode)

    return classcode + '/' + username


def retrieve(userid) -> dict:

    if os.path.exists(get_user_directory(userid)):

        with open(get_user_directory(userid), 'rb') as handle:
            return pickle.load(handle)

    else:

        raise FileNotFoundError


def create(username, classcode, password, overwrite=False) -> dict:

    # set as unmanaged if no classcode was used
    classcode = clean_classcode(classcode)

    # create userid
    userid = form_userid(username, classcode)

    if not overwrite and os.path.exists(get_user_directory(userid)):
        return retrieve(username)

    # structure of user account
    user = {
        'username': username,
        'classcode': classcode,
        'userid': userid,
        'password': password,
        'history': [{'desc': 'Loaded complete Minnesota felony sentencing data for 2001 to 2019', 'action': None}],
        'saved': []
    }

    if not os.path.exists('user/' + classcode): os.mkdir('user/' + classcode)  # create directory if needed

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

    return user


def history_add(userid, entry) -> None:

    user = retrieve(userid)
    user['history'].append(entry)

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)


def history_revert(userid, entry_number=1):

    # an entry number of 0 or below will break the system by wiping the base history
    assert entry_number > 0

    user = retrieve(userid)
    user['history'] = user['history'][:entry_number]

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)