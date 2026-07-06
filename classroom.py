# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# classroom.py
# manages classes (sections) for the educator portal -- class objects, join codes, rosters,
# per-module assignments. Schema documented in EDUCATOR_PORTAL_PROMPTS.md Appendix A.
#
# Pure module: stdlib only, no Flask (mirrors account.py / lessons.py). Classes live as
# classes/<class_id>.json, one file per class -- git-ignored, like user/ (rosters tie to real
# students). Concurrency: last-write-wins (read-modify-write on the JSON file); acceptable at
# classroom scale (one educator editing their own class at a time).

import os
import re
import json
import secrets
import string
import datetime

CLASSES_DIR = 'classes'

# class_id doubles as filename stem and URL segment, so keep it path/URL-safe
# (mirrors lessons.ID_PATTERN). It is a slug of the class name plus a random suffix and,
# once created, is immutable -- rotating the join code or editing the name never changes it.
ID_PATTERN = re.compile(r'^[a-z0-9-]+$')

SUFFIX_ALPHABET = string.ascii_lowercase + string.digits
SUFFIX_LENGTH = 4

# join codes are read aloud in class and typed by students, so the alphabet drops characters
# that are easy to confuse at a glance or by ear: 0/O, 1/I/L.
JOIN_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
JOIN_CODE_LENGTH = 6
JOIN_CODE_PATTERN = re.compile('^[' + JOIN_CODE_ALPHABET + ']{' + str(JOIN_CODE_LENGTH) + '}$')

VALID_ASSIGNMENT_STATES = {'required', 'optional', 'hidden', 'scheduled'}


class ClassError(Exception):
    """Raised when a class file is missing, unparseable, or malformed."""
    pass


# ---------------------------------------------------------------------------
# create / read / list / find
# ---------------------------------------------------------------------------

def create_class(owner_userid, name, email_policy=None) -> dict:

    name = name.strip() if isinstance(name, str) else ''
    if name == '':
        raise ClassError("class name must be a non-empty string")

    if not isinstance(owner_userid, str) or owner_userid == '':
        raise ClassError("owner_userid must be a non-empty string")

    class_obj = {
        'class_id': _generate_class_id(name),
        'name': name,
        'owner': owner_userid,
        'join_code': _generate_join_code(),
        'email_policy': email_policy if email_policy is not None else {'required': False, 'domains': []},
        'assignments': {},
        'policy': {'attempts': None, 'reveal_after_miss': False, 'show_tolerance': False},
        'roster': [],
        'archived': False,
        'created': _now_iso(),
    }

    validate(class_obj)
    _write_class(class_obj)
    return class_obj


def get_class(class_id) -> dict:

    # reject anything that could escape CLASSES_DIR (path traversal) or is not a real id
    if not isinstance(class_id, str) or not ID_PATTERN.match(class_id):
        raise ClassError("invalid class id '" + str(class_id) + "' (expected [a-z0-9-])")

    path = _class_path(class_id)
    if not os.path.exists(path):
        raise ClassError("class '" + class_id + "' not found at " + path)

    class_obj = _load_file(path)
    validate(class_obj, source=class_id + '.json')

    if class_obj['class_id'] != class_id:
        raise ClassError(class_id + ".json: class_id '" + str(class_obj['class_id']) + "' does not match filename")

    return class_obj


def list_classes(owner_userid) -> list:

    # missing directory just means no classes yet (mirrors get_user_list on a missing classcode)
    if not os.path.isdir(CLASSES_DIR):
        return []

    classes = []
    for name in sorted(os.listdir(CLASSES_DIR)):

        if not name.endswith('.json'):
            continue

        class_obj = _load_file(os.path.join(CLASSES_DIR, name))
        validate(class_obj, source=name)

        # class_id must match the filename stem, since both are the storage key
        stem = name[:-len('.json')]
        if class_obj['class_id'] != stem:
            raise ClassError(name + ": class_id '" + str(class_obj['class_id']) + "' does not match filename stem '" + stem + "'")

        if class_obj['owner'] == owner_userid:
            classes.append(class_obj)

    classes.sort(key=lambda c: (c.get('name', ''), c['class_id']))
    return classes


def find_by_join_code(code) -> dict | None:
    # case-insensitive scan for a non-archived class. Linear scan over classes/ -- fine at
    # classroom scale. Returns None (not an error) on no match, since this drives the signup
    # lookup where "no class with that code" is an expected, user-facing outcome.

    if not isinstance(code, str) or code.strip() == '':
        return None

    needle = code.strip().upper()

    if not os.path.isdir(CLASSES_DIR):
        return None

    for name in sorted(os.listdir(CLASSES_DIR)):

        if not name.endswith('.json'):
            continue

        class_obj = _load_file(os.path.join(CLASSES_DIR, name))
        validate(class_obj, source=name)

        if class_obj.get('archived'):
            continue

        if class_obj['join_code'].upper() == needle:
            return class_obj

    return None


# ---------------------------------------------------------------------------
# roster ops
# ---------------------------------------------------------------------------

def enroll(class_id, student_userid) -> dict:

    class_obj = get_class(class_id)
    if student_userid not in class_obj['roster']:
        class_obj['roster'].append(student_userid)
        _write_class(class_obj)
    return class_obj


def remove_student(class_id, student_userid) -> dict:

    class_obj = get_class(class_id)
    class_obj['roster'] = [u for u in class_obj['roster'] if u != student_userid]
    _write_class(class_obj)
    return class_obj


def rotate_join_code(class_id) -> dict:
    # new unique code; must not touch class_id (the storage key) or the roster

    class_obj = get_class(class_id)
    class_obj['join_code'] = _generate_join_code()
    _write_class(class_obj)
    return class_obj


# ---------------------------------------------------------------------------
# per-module assignment state
# ---------------------------------------------------------------------------

def get_assignments(class_id) -> dict:
    return get_class(class_id).get('assignments', {})


def set_assignments(class_id, assignments) -> dict:

    class_obj = get_class(class_id)
    _validate_assignments(assignments, class_id + '.assignments')
    class_obj['assignments'] = assignments
    _write_class(class_obj)
    return class_obj


# ---------------------------------------------------------------------------
# email policy / archive
# ---------------------------------------------------------------------------

def email_allowed(policy, username) -> bool:
    # Join-time enforcement for feature 3 (the educator sets the policy in a later phase; the
    # check lives here because joining is when it applies). Pure -- no file I/O.
    #
    #   required=False (or no policy)      -> any username passes (the default).
    #   required=True                      -> username must be a syntactically simple email
    #                                         (one '@', non-empty local + domain part).
    #   required=True and domains non-empty-> the domain must also match one of the allowed
    #                                         domains (case-insensitive; a leading '@' on a
    #                                         configured domain is tolerated).
    #   required=True and domains empty    -> any valid email passes (unrestricted).
    if not isinstance(policy, dict) or not policy.get('required'):
        return True

    if username.count('@') != 1:
        return False
    local, _, domain = username.partition('@')
    if local == '' or domain == '':
        return False

    allowed = [d.strip().lower().lstrip('@') for d in policy.get('domains', [])
               if isinstance(d, str) and d.strip()]
    if not allowed:
        return True
    return domain.lower() in allowed


def set_email_policy(class_id, policy) -> dict:

    class_obj = get_class(class_id)
    _validate_email_policy(policy, class_id + '.email_policy')
    class_obj['email_policy'] = policy
    _write_class(class_obj)
    return class_obj


def archive(class_id) -> dict:

    class_obj = get_class(class_id)
    class_obj['archived'] = True
    _write_class(class_obj)
    return class_obj


def unarchive(class_id) -> dict:

    class_obj = get_class(class_id)
    class_obj['archived'] = False
    _write_class(class_obj)
    return class_obj


# ---------------------------------------------------------------------------
# validation (mirrors lessons.validate)
# ---------------------------------------------------------------------------

def validate(class_obj, source=None) -> dict:

    # tag prefixes every error message so a malformed file is easy to locate
    tag = source
    if tag is None:
        tag = class_obj['class_id'] if isinstance(class_obj, dict) and 'class_id' in class_obj else '<class>'

    if not isinstance(class_obj, dict):
        raise ClassError(tag + ": class must be a JSON object")

    for field in ('class_id', 'name', 'owner', 'join_code'):
        if field not in class_obj:
            raise ClassError(tag + ": missing required field '" + field + "'")
        if not isinstance(class_obj[field], str) or class_obj[field] == '':
            raise ClassError(tag + ": '" + field + "' must be a non-empty string")

    if not ID_PATTERN.match(class_obj['class_id']):
        raise ClassError(tag + ": class_id '" + str(class_obj['class_id']) + "' must match [a-z0-9-]")

    if not JOIN_CODE_PATTERN.match(class_obj['join_code']):
        raise ClassError(tag + ": join_code '" + str(class_obj['join_code']) + "' must be "
                          + str(JOIN_CODE_LENGTH) + " characters from " + JOIN_CODE_ALPHABET)

    roster = class_obj.get('roster', [])
    if not isinstance(roster, list) or not all(isinstance(u, str) for u in roster):
        raise ClassError(tag + ": 'roster' must be a list of userid strings")

    if 'archived' in class_obj and not isinstance(class_obj['archived'], bool):
        raise ClassError(tag + ": 'archived' must be true or false")

    if 'created' in class_obj and not isinstance(class_obj['created'], str):
        raise ClassError(tag + ": 'created' must be a string timestamp")

    # optional fields -- older class files may predate these (read defensively per
    # EDUCATOR_PORTAL_PROMPTS.md Appendix A), so only validate shape when present
    if 'email_policy' in class_obj:
        _validate_email_policy(class_obj['email_policy'], tag + ".email_policy")

    if 'assignments' in class_obj:
        _validate_assignments(class_obj['assignments'], tag + ".assignments")

    if 'policy' in class_obj:
        _validate_policy(class_obj['policy'], tag + ".policy")

    return class_obj


def _validate_email_policy(policy, where) -> None:

    if not isinstance(policy, dict):
        raise ClassError(where + ": must be an object")

    if 'required' in policy and not isinstance(policy['required'], bool):
        raise ClassError(where + ": 'required' must be true or false")

    if 'domains' in policy:
        domains = policy['domains']
        if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
            raise ClassError(where + ": 'domains' must be a list of strings")


def _validate_assignments(assignments, where) -> None:

    if not isinstance(assignments, dict):
        raise ClassError(where + ": must be an object mapping module_id -> state")

    for module_id, entry in assignments.items():

        if not isinstance(module_id, str) or module_id == '':
            raise ClassError(where + ": module id keys must be non-empty strings")

        if not isinstance(entry, dict):
            raise ClassError(where + "['" + str(module_id) + "']: must be an object")

        state = entry.get('state')
        if state not in VALID_ASSIGNMENT_STATES:
            raise ClassError(where + "['" + module_id + "']: invalid state " + repr(state)
                              + " (expected one of " + str(sorted(VALID_ASSIGNMENT_STATES)) + ")")

        for key in ('open', 'due'):
            if key in entry and entry[key] is not None and not isinstance(entry[key], str):
                raise ClassError(where + "['" + module_id + "']: '" + key + "' must be a date string or null")


def _validate_policy(policy, where) -> None:

    if not isinstance(policy, dict):
        raise ClassError(where + ": must be an object")

    if 'attempts' in policy and policy['attempts'] is not None:
        # bool is a subclass of int, so exclude it explicitly
        if isinstance(policy['attempts'], bool) or not isinstance(policy['attempts'], int):
            raise ClassError(where + ": 'attempts' must be an integer or null")

    for key in ('reveal_after_miss', 'show_tolerance'):
        if key in policy and not isinstance(policy[key], bool):
            raise ClassError(where + ": '" + key + "' must be true or false")


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _slugify(name) -> str:
    slug = re.sub(r'[^a-z0-9-]+', '-', name.strip().lower()).strip('-')
    return slug if slug else 'class'


def _random_suffix() -> str:
    return ''.join(secrets.choice(SUFFIX_ALPHABET) for _ in range(SUFFIX_LENGTH))


def _generate_class_id(name) -> str:
    slug = _slugify(name)
    for _ in range(100):  # collisions are astronomically unlikely; bound the loop defensively
        candidate = slug + '-' + _random_suffix()
        if not os.path.exists(_class_path(candidate)):
            return candidate
    raise ClassError("could not generate a unique class_id for '" + name + "'")


def _generate_join_code() -> str:
    for _ in range(100):
        code = ''.join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
        if not _join_code_in_use(code):
            return code
    raise ClassError("could not generate a unique join_code")


def _join_code_in_use(code) -> bool:
    # bare existence probe used only for uniqueness at generation time -- deliberately skips
    # validate() on each file (a corrupt class elsewhere must not block creating a new one, and
    # this checks archived classes too, unlike find_by_join_code). The public find_by_join_code
    # above is the validated lookup used by the actual join flow.

    if not os.path.isdir(CLASSES_DIR):
        return False

    needle = code.upper()
    for name in os.listdir(CLASSES_DIR):

        if not name.endswith('.json'):
            continue

        try:
            class_obj = _load_file(os.path.join(CLASSES_DIR, name))
        except ClassError:
            continue

        if class_obj.get('join_code', '').upper() == needle:
            return True

    return False


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _class_path(class_id) -> str:
    return os.path.join(CLASSES_DIR, class_id + '.json')


def _write_class(class_obj) -> None:
    if not os.path.isdir(CLASSES_DIR):
        os.makedirs(CLASSES_DIR, exist_ok=True)
    with open(_class_path(class_obj['class_id']), 'w', encoding='utf-8') as handle:
        json.dump(class_obj, handle, indent=2)


def _load_file(path) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except json.JSONDecodeError as e:
        raise ClassError(os.path.basename(path) + ": invalid JSON (" + str(e) + ")")
