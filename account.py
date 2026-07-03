# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# account.py
# manages accounts

import os
import pickle

NO_CLASS_CODE = 'unmanaged'

# classcode convention: signing up with a classcode like 'edu-smith' grants educator
# (authoring) rights, scoped to that classcode. This is a convenience convention, NOT a
# security boundary -- the app has no real authentication (see CLAUDE.md known issues).
EDUCATOR_CLASSCODE_PREFIX = 'edu-'


def clean_classcode(classcode) -> str:
    if classcode is None or classcode == '': return NO_CLASS_CODE
    else: return classcode


def is_educator_classcode(classcode) -> bool:
    return clean_classcode(classcode).startswith(EDUCATOR_CLASSCODE_PREFIX)


def is_educator(userid) -> bool:
    # backwards-compatible read: accounts created before roles have no 'is_educator' key
    return retrieve(userid).get('is_educator', False)


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
        'saved': [],
        'progress': {},
        'is_educator': is_educator_classcode(classcode)
    }

    if not os.path.exists('user/' + classcode): os.mkdir('user/' + classcode)  # create directory if needed

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

    return user


def history_add(userid, entry) -> None:

    user = retrieve(userid)

    # make only the most recent active
    new_history = []
    for ih in user['history']:
        temp_entry = ih
        temp_entry['active'] = False
        new_history.append(temp_entry)
    entry['active'] = True
    new_history.append(entry)
    user['history'] = new_history

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)


def history_revert(userid, entry_number=1):

    # an entry number of 0 or below will break the system by wiping the base history
    assert entry_number > 0

    user = retrieve(userid)
    user['history'] = user['history'][:entry_number]

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)


def get_progress(userid, module_id) -> dict:

    user = retrieve(userid)

    # read defensively: accounts created before learning modules have no 'progress' key
    return user.get('progress', {}).get(module_id, {})


def set_progress(userid, module_id, step, answers=None, completed=None) -> None:

    user = retrieve(userid)

    # lazily create the 'progress' key for pre-existing accounts on first write
    progress = user.get('progress', {})

    # merge into any existing progress for this module so we don't clobber
    # sibling keys such as 'state' (set by lesson exploration) or prior answers
    module_progress = progress.get(module_id, {})
    module_progress['step'] = step
    if answers is not None:
        module_progress['answers'] = answers

    # completed=None means "leave as-is" (so merely recording a step, e.g. on resume,
    # does not un-complete a finished module); initialize it to False on first write
    if completed is not None:
        module_progress['completed'] = completed
    elif 'completed' not in module_progress:
        module_progress['completed'] = False

    progress[module_id] = module_progress
    user['progress'] = progress

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)


def set_lesson_state(userid, module_id, state) -> None:

    # records the active lesson data state on progress[module_id]['state'].
    # this is the sandboxed lesson view only -- it is NEVER merged into user['history'].

    user = retrieve(userid)

    # lazily create 'progress' for pre-existing accounts, and merge so we don't
    # clobber 'step' / 'answers' / 'completed' already recorded for this module
    progress = user.get('progress', {})
    module_progress = progress.get(module_id, {})
    module_progress['state'] = state

    progress[module_id] = module_progress
    user['progress'] = progress

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)