# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# lessons.py
# loads and validates learning modules from the lessons/ directory
#
# Pure module: stdlib only, no Flask (mirrors account.py / data.py). The on-disk
# schema is documented in lessons/README.md and LEARNING_MODULES_PROMPTS.md (Appendix A).

import os
import re
import json

LESSONS_DIR = 'lessons'

VALID_STEP_TYPES = {'read', 'explore', 'question', 'checkpoint'}
VALID_ANSWER_TYPES = {'numeric', 'choice', 'free'}
VALID_STATS = {'mean', 'median', 'std', 'count'}
VALID_VIEWS = {'info', 'table', 'chart'}

# comparison operations, matching data.Data.filter
VALID_OPS = {'eq', 'ne', 'gt', 'ge', 'lt', 'le'}

# module ids double as filenames and URL segments, so keep them path/URL-safe
ID_PATTERN = re.compile(r'^[a-z0-9-]+$')


class LessonError(Exception):
    """Raised when a lesson module file is missing, unparseable, or malformed."""
    pass


# Memo for list_modules(): re-parsing every lessons/*.json on every call (catalog,
# dashboard, deep links) is wasted work between authoring edits. Keyed on a directory
# signature (each file's name + mtime + size) rather than a bare "have we run before"
# flag, so an edited/added/removed lesson file is picked up on the next call without
# a process restart.
_list_modules_cache = None  # (signature, modules) or None


def _lessons_signature():
    if not os.path.isdir(LESSONS_DIR):
        return None

    signature = []
    for name in sorted(os.listdir(LESSONS_DIR)):
        if not name.endswith('.json'):
            continue
        stat = os.stat(os.path.join(LESSONS_DIR, name))
        signature.append((name, stat.st_mtime_ns, stat.st_size))

    return tuple(signature)


def list_modules() -> list:

    global _list_modules_cache

    signature = _lessons_signature()
    if _list_modules_cache is not None and _list_modules_cache[0] == signature:
        return _list_modules_cache[1]

    # missing directory just means no lessons yet (mirrors get_user_list on a missing classcode)
    modules = []
    if os.path.isdir(LESSONS_DIR):
        for name in sorted(os.listdir(LESSONS_DIR)):

            if not name.endswith('.json'):
                continue

            module = _load_file(os.path.join(LESSONS_DIR, name))
            validate(module, source=name)

            # id must match the filename stem, since both are the URL segment
            stem = name[:-len('.json')]
            if module['id'] != stem:
                raise LessonError(name + ": id '" + str(module['id']) + "' does not match filename stem '" + stem + "'")

            modules.append(module)

        # optional 'order' controls catalog sequence (lower first); modules without it sort last,
        # ties broken by id. Both the catalog (/lesson) and the homepage read this order.
        modules.sort(key=lambda m: (m.get('order', 10**9), m['id']))

    _list_modules_cache = (signature, modules)
    return modules


def get_module(module_id) -> dict:

    # reject anything that could escape lessons/ (path traversal) or is not a real id
    if not isinstance(module_id, str) or not ID_PATTERN.match(module_id):
        raise LessonError("invalid module id '" + str(module_id) + "' (expected [a-z0-9-])")

    path = _module_path(module_id)
    if not os.path.exists(path):
        raise LessonError("module '" + module_id + "' not found at " + path)

    module = _load_file(path)
    validate(module, source=module_id + '.json')

    if module['id'] != module_id:
        raise LessonError(module_id + ".json: id '" + str(module['id']) + "' does not match filename")

    return module


def validate(module, source=None) -> dict:

    # tag prefixes every error message so a malformed file is easy to locate
    tag = source
    if tag is None:
        tag = module['id'] if isinstance(module, dict) and 'id' in module else '<module>'

    if not isinstance(module, dict):
        raise LessonError(tag + ": module must be a JSON object")

    # required string fields
    for field in ('id', 'title', 'description', 'author'):
        if field not in module:
            raise LessonError(tag + ": missing required field '" + field + "'")
        if not isinstance(module[field], str) or module[field] == '':
            raise LessonError(tag + ": '" + field + "' must be a non-empty string")

    if not ID_PATTERN.match(module['id']):
        raise LessonError(tag + ": id '" + str(module['id']) + "' must match [a-z0-9-]")

    objectives = module.get('objectives')
    if not isinstance(objectives, list) or not all(isinstance(o, str) for o in objectives):
        raise LessonError(tag + ": 'objectives' must be a list of strings")

    # optional: catalog ordering. Lower sorts first; missing sorts last (see list_modules).
    # bool is a subclass of int, so exclude it explicitly.
    if 'order' in module and (isinstance(module['order'], bool) or not isinstance(module['order'], int)):
        raise LessonError(tag + ": 'order' must be an integer")

    # optional: educator-only teaching notes for the whole module (discussion prompts,
    # misconceptions, framing). Never shown to students -- see app.py's is_educator gate.
    if 'educator_notes' in module:
        _validate_educator_notes(module['educator_notes'], tag + ".educator_notes")

    steps = module.get('steps')
    if not isinstance(steps, list) or len(steps) == 0:
        raise LessonError(tag + ": 'steps' must be a non-empty list")

    for i, step in enumerate(steps):
        _validate_step(step, tag + " step[" + str(i) + "]")

    return module


def _validate_step(step, where) -> None:

    if not isinstance(step, dict):
        raise LessonError(where + ": must be an object")

    stype = step.get('type')
    if stype not in VALID_STEP_TYPES:
        raise LessonError(where + ": invalid type " + repr(stype) + " (expected one of " + str(sorted(VALID_STEP_TYPES)) + ")")

    where = where + " (" + stype + ")"

    if not isinstance(step.get('title'), str) or step['title'] == '':
        raise LessonError(where + ": must have a non-empty 'title'")

    # every current step type carries a body of markdown/HTML
    if not isinstance(step.get('body'), str):
        raise LessonError(where + ": must have a string 'body'")

    # optional: educator-only teaching notes for this step (any step type may carry them)
    if 'educator_notes' in step:
        _validate_educator_notes(step['educator_notes'], where + ".educator_notes")

    if stype == 'explore':
        if 'state' in step:
            _validate_state(step['state'], where + ".state")
        if 'focus' in step:
            _validate_focus(step['focus'], where + ".focus")

    elif stype == 'question':
        _validate_answer(step.get('answer'), where + ".answer")
        if 'state' in step:
            _validate_state(step['state'], where + ".state")
        if 'require_answer' in step and not isinstance(step['require_answer'], bool):
            raise LessonError(where + ": 'require_answer' must be true or false")

    elif stype == 'checkpoint':
        if 'expect_state' not in step:
            raise LessonError(where + ": must have 'expect_state'")
        _validate_state(step['expect_state'], where + ".expect_state")


def _validate_educator_notes(notes, where) -> None:
    # a single string (one note/paragraph) or a list of strings (discussion prompts,
    # one per misconception, etc.) -- either shape renders fine in the templates.
    if isinstance(notes, str):
        if notes == '':
            raise LessonError(where + ": must not be an empty string")
        return

    if isinstance(notes, list):
        if not all(isinstance(n, str) and n != '' for n in notes):
            raise LessonError(where + ": list items must be non-empty strings")
        return

    raise LessonError(where + ": must be a string or a list of strings")


def _validate_focus(focus, where) -> None:

    if not isinstance(focus, dict):
        raise LessonError(where + ": must be an object")

    view = focus.get('view')
    if view not in VALID_VIEWS:
        raise LessonError(where + ": invalid view " + repr(view) + " (expected one of " + str(sorted(VALID_VIEWS)) + ")")

    if view == 'info':
        if not isinstance(focus.get('column'), str) or focus['column'] == '':
            raise LessonError(where + ": info view requires a 'column' string")
    elif view == 'table':
        for key in ('dependant', 'x_axis', 'y_axis'):
            if not isinstance(focus.get(key), str) or focus[key] == '':
                raise LessonError(where + ": table view requires a '" + key + "' string")
    else:  # chart (E1): a pinned Visualize chart. Structural checks only — the app's
           # build_lesson_chart resolves the chart against the live registry and degrades
           # to the "no chart pinned" nudge on an unknown/invalid pick, so we don't couple
           # this pure-stdlib validator to VIZ_CHART_TYPES.
        if not isinstance(focus.get('chart'), str) or focus['chart'] == '':
            raise LessonError(where + ": chart view requires a 'chart' type id (string)")
        for key in ('column', 'column2', 'measure', 'aggregate'):
            if key in focus and not isinstance(focus[key], str):
                raise LessonError(where + ": chart view '" + key + "' must be a string")
        if 'cols' in focus and not (isinstance(focus['cols'], list)
                                    and all(isinstance(c, str) and c for c in focus['cols'])):
            raise LessonError(where + ": chart view 'cols' must be a list of non-empty strings")


def _validate_answer(answer, where) -> None:

    if not isinstance(answer, dict):
        raise LessonError(where + ": question must have an 'answer' object")

    atype = answer.get('type')
    if atype not in VALID_ANSWER_TYPES:
        raise LessonError(where + ": invalid answer type " + repr(atype) + " (expected one of " + str(sorted(VALID_ANSWER_TYPES)) + ")")

    if atype == 'numeric':
        compute = answer.get('compute')
        if not isinstance(compute, dict):
            raise LessonError(where + ": numeric answer requires a 'compute' object")
        if compute.get('stat') not in VALID_STATS:
            raise LessonError(where + ": compute.stat must be one of " + str(sorted(VALID_STATS)))
        if not isinstance(compute.get('column'), str) or compute['column'] == '':
            raise LessonError(where + ": compute.column must be a non-empty string")
        # bool is a subclass of int/float, so exclude it explicitly
        tolerance = answer.get('tolerance')
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
            raise LessonError(where + ": numeric answer requires a numeric 'tolerance'")

    elif atype == 'choice':
        options = answer.get('options')
        if not isinstance(options, list) or len(options) < 2 or not all(isinstance(o, str) for o in options):
            raise LessonError(where + ": choice answer requires 'options' (a list of 2+ strings)")
        correct = answer.get('correct')
        if isinstance(correct, bool) or not isinstance(correct, int) or not (0 <= correct < len(options)):
            raise LessonError(where + ": choice answer 'correct' must be an index into options")

    elif atype == 'free':
        if 'model_answer' in answer and not isinstance(answer['model_answer'], str):
            raise LessonError(where + ": free answer 'model_answer' must be a string")


def _validate_state(tokens, where) -> None:
    # Structural check of history-token state. The canonical encoder is
    # cache.history_item_to_text; this validator mirrors that format without
    # importing cache (which pulls pandas via data.py). Keep the two in sync.

    if not isinstance(tokens, list):
        raise LessonError(where + ": must be a list of history tokens")

    for tok in tokens:

        if not isinstance(tok, str):
            raise LessonError(where + ": token " + repr(tok) + " must be a string")

        parts = tok.split('.')

        # <code>.<column>.<op>.<value> — value carries no '.' by convention
        if len(parts) != 4:
            raise LessonError(where + ": token '" + tok + "' must have the form <code>.<col>.<op>.<val>")

        code, column, op, value = parts

        if code not in ('f', 'o'):
            raise LessonError(where + ": token '" + tok + "' has unknown action code '" + code + "' (expected 'f' or 'o')")

        if column == '':
            raise LessonError(where + ": token '" + tok + "' has an empty column")

        if op not in VALID_OPS:
            raise LessonError(where + ": token '" + tok + "' has invalid operation '" + op + "' (expected one of " + str(sorted(VALID_OPS)) + ")")

        if code == 'o':
            # OR-same-column: values are tilde-separated, each non-empty
            if any(v == '' for v in value.split('~')):
                raise LessonError(where + ": token '" + tok + "' has an empty OR value")
        else:  # 'f'
            if value == '':
                raise LessonError(where + ": token '" + tok + "' has an empty value")
            if '~' in value:
                raise LessonError(where + ": single-filter token '" + tok + "' must not contain '~'")


def save_module(module) -> str:
    # validate BEFORE writing; validate() enforces id == [a-z0-9-], so the path cannot
    # escape LESSONS_DIR (no slashes/dots from form input reach the filesystem).
    validate(module)

    if not os.path.isdir(LESSONS_DIR):
        os.makedirs(LESSONS_DIR, exist_ok=True)

    with open(_module_path(module['id']), 'w', encoding='utf-8') as handle:
        json.dump(module, handle, indent=2)

    return module['id']


def _module_path(module_id) -> str:
    return os.path.join(LESSONS_DIR, module_id + '.json')


def _load_file(path) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except json.JSONDecodeError as e:
        raise LessonError(os.path.basename(path) + ": invalid JSON (" + str(e) + ")")
