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

from flask import g, has_app_context

NO_CLASS_CODE = 'unmanaged'

# classcode convention: signing up with a classcode like 'edu-smith' grants educator
# (authoring) rights, scoped to that classcode. This is a convenience convention, NOT a
# security boundary -- anyone can self-select an 'edu-' classcode at signup (the planned
# class-code system in EDUCATOR_PORTAL.md replaces this).
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

        # accounts are stored as '<username>.pickle'; strip the extension so callers can
        # compare against a submitted username (the /new and /login existence checks)
        return [name[:-len('.pickle')] for name in os.listdir('user/' + classcode)
                if name.endswith('.pickle')]

    else:

        return []


def find_userids_by_username(username, include_educator=True) -> list[str]:

    # Return the userid of every stored account whose username matches, across ALL class
    # namespaces. Student usernames are only unique WITHIN a class
    # (user/<classcode>/<username>.pickle), so a bare username can map to several accounts in
    # different classes. Login uses this to sign a student in by username + password alone: the
    # classcode is already baked into the userid the account was created under, so there is no
    # need to make the student re-type it. Ordering is stable (classcodes sorted) so a
    # same-username collision resolves deterministically; the caller disambiguates by password.
    userids = []

    for classcode in sorted(get_classcode_list()):

        # get_classcode_list() is a bare os.listdir('user'); skip anything that isn't a class
        # directory (defensive -- the tree only holds directories today)
        if not os.path.isdir(os.path.join('user', classcode)):
            continue

        if not include_educator and is_educator_classcode(classcode):
            continue

        if username in get_user_list(classcode):
            userids.append(form_userid(username, classcode))

    return userids


def get_user_directory(userid) -> str: return 'user/' + userid + '.pickle'


def form_userid(username, classcode) -> str:

    # set as unmanaged if no classcode was used
    classcode = clean_classcode(classcode)

    return classcode + '/' + username


def _request_cache() -> dict:
    # flask.g lives exactly as long as the current application context (one per
    # request), so a dict hung off it is a free per-request memo -- never a module
    # global, since accounts are mutable per-user state (REQUEST_PATH_OPTIMIZATION_PROMPTS.md
    # Phase 1 "Don't"). Callers must check has_app_context() first.
    if not hasattr(g, '_account_cache'):
        g._account_cache = {}
    return g._account_cache


def _invalidate(userid) -> None:
    # Every writer below calls this right after persisting, so a route that writes
    # then reads within the same request never sees the pre-write copy. No-op outside
    # a request (nothing was cached to begin with).
    if has_app_context():
        _request_cache().pop(userid, None)


def retrieve(userid) -> dict:

    # Memoized per request (flask.g) -- a single explore render unpickles the same
    # user file 4-6x (once per get_data()/_execute() call plus inject_globals)
    # without this. Falls back to a plain disk read with no caching when there is no
    # active Flask application context (e.g. perf/benchmark.py's setup calls, which run
    # outside request dispatch), so behavior there is unchanged.
    if has_app_context():
        cached = _request_cache()
        if userid in cached:
            return cached[userid]

    if os.path.exists(get_user_directory(userid)):

        with open(get_user_directory(userid), 'rb') as handle:
            user = pickle.load(handle)

    else:

        raise FileNotFoundError

    if has_app_context():
        _request_cache()[userid] = user

    return user


def create(username, classcode, password, overwrite=False, classes=None) -> dict:

    # set as unmanaged if no classcode was used
    classcode = clean_classcode(classcode)

    # create userid
    userid = form_userid(username, classcode)

    if not overwrite and os.path.exists(get_user_directory(userid)):
        return retrieve(userid)

    # structure of user account
    user = {
        'username': username,
        'classcode': classcode,
        'userid': userid,
        'password': password,
        'history': [{'desc': 'Loaded complete Minnesota felony sentencing data for 2001 to 2019', 'action': None}],
        'saved': [],
        'progress': {},
        # class memberships for the educator portal (feature 3): the class_id(s) a student has
        # joined. Empty for public/'edu-' accounts. Read defensively elsewhere (user.get('classes', []))
        # so pre-portal pickles without this key stay valid.
        'classes': list(classes) if classes else [],
        'is_educator': is_educator_classcode(classcode)
    }

    if not os.path.exists('user/' + classcode): os.mkdir('user/' + classcode)  # create directory if needed

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

    _invalidate(userid)

    return user


def add_class(userid, class_id) -> dict:

    # record a class membership on an existing account (the logged-in "Join a class" flow).
    # Unlike signup enrollment, this does NOT re-namespace the account -- the pickle stays under
    # its original classcode; only the 'classes' list grows. The class roster is updated
    # separately by classroom.enroll (the route keeps the two in sync). Idempotent.
    user = retrieve(userid)

    classes = user.get('classes', [])  # defensive: pre-portal accounts have no 'classes' key
    if class_id not in classes:
        classes.append(class_id)
    user['classes'] = classes

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

    _invalidate(userid)

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

    _invalidate(userid)


def history_revert(userid, entry_number=1):

    # an entry number of 0 or below will break the system by wiping the base history
    assert entry_number > 0

    user = retrieve(userid)
    user['history'] = user['history'][:entry_number]

    # the reverted-to entry is now the most recent; mark only it active (a display flag,
    # mirroring history_add) so the history table shows it as 'Current' rather than 'Revert'
    for entry in user['history']:
        entry['active'] = False
    user['history'][-1]['active'] = True

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

    _invalidate(userid)


def set_history_count(userid, count) -> None:

    # Cache the filtered case count on the active (most recent) history entry, so the
    # sidebar badge (app.inject_globals) can read it WITHOUT replaying the history
    # (REQUEST_PATH_OPTIMIZATION_PROMPTS.md Phase 2). Written by the filter-apply route
    # right after it computes the count for its "N cases remain" flash. The count rides
    # along through revert/clear: reverting to an entry restores the count stamped when it
    # was applied, and the base entry carries none (the badge treats the unfiltered state
    # as the full dataset). Purely a display cache -- it never enters the cache/data/ path
    # (cache.history_item_to_text reads only 'action'), so cache keys and .bin bytes are
    # unchanged; the .bin files stay the source of truth on a genuine miss.
    user = retrieve(userid)

    if user['history']:
        user['history'][-1]['count'] = count

        with open(get_user_directory(userid), 'wb') as handle:
            pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

        _invalidate(userid)


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

    _invalidate(userid)


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

    _invalidate(userid)


def remove_class(userid, class_id) -> dict:

    # inverse of add_class -- drops a class membership (the roster "Remove" route in the
    # educator portal keeps this in sync with classroom.remove_student). Leaves the account,
    # its history, and its progress untouched: only the 'classes' list shrinks, so a removed
    # student goes back to seeing every module unrestricted, like a public/unmanaged user,
    # rather than staying gated by assignment rules from a class they're no longer in.
    user = retrieve(userid)

    classes = user.get('classes', [])
    if class_id in classes:
        user['classes'] = [c for c in classes if c != class_id]

        with open(get_user_directory(userid), 'wb') as handle:
            pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

        _invalidate(userid)

    return user


def reset_progress(userid, module_ids) -> dict:

    # Roster-management "reset a student's progress" (educator portal Phase 8, feature 7).
    # Scope (documented per the phase prompt): clears progress -- resume step, stored
    # answers, completed flag, and any lesson-sandbox 'state' -- for exactly the module ids
    # the caller passes in. The educator portal calls this with every lesson module, since
    # that is the same set the class progress dashboard tracks (dashboards are not filtered
    # by this class's assignment states). This deliberately does NOT touch the append-only
    # attempt log (see analytics.delete_attempts) -- item-difficulty history used by the
    # per-class analytics and the thesis evaluation survives a reset; only the student's own
    # resume point is cleared, giving them a clean restart on the module.
    user = retrieve(userid)

    progress = user.get('progress', {})
    for module_id in module_ids:
        progress.pop(module_id, None)
    user['progress'] = progress

    with open(get_user_directory(userid), 'wb') as handle:
        pickle.dump(user, handle, protocol=pickle.HIGHEST_PROTOCOL)

    _invalidate(userid)

    return user


def delete_account(userid) -> None:

    # Educator-initiated full deletion (EDUCATOR_PORTAL.md Privacy section): permanently
    # removes the account pickle. Callers are also responsible for classroom.remove_student
    # (drop the roster entry) and analytics.delete_attempts (drop the attempt log) -- this
    # function only ever touches the account file itself. No-op if already gone, so a retry
    # or a double-click never raises.
    path = get_user_directory(userid)
    if os.path.exists(path):
        os.remove(path)

    _invalidate(userid)