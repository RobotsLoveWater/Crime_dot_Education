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
VALID_VIEWS = {'info', 'table'}

# comparison operations, matching data.Data.filter
VALID_OPS = {'eq', 'ne', 'gt', 'ge', 'lt', 'le'}

# module ids double as filenames and URL segments, so keep them path/URL-safe
ID_PATTERN = re.compile(r'^[a-z0-9-]+$')


class LessonError(Exception):
    """Raised when a lesson module file is missing, unparseable, or malformed."""
    pass


def list_modules() -> list:

    # missing directory just means no lessons yet (mirrors get_user_list on a missing classcode)
    if not os.path.isdir(LESSONS_DIR):
        return []

    modules = []
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


def _validate_focus(focus, where) -> None:

    if not isinstance(focus, dict):
        raise LessonError(where + ": must be an object")

    view = focus.get('view')
    if view not in VALID_VIEWS:
        raise LessonError(where + ": invalid view " + repr(view) + " (expected one of " + str(sorted(VALID_VIEWS)) + ")")

    if view == 'info':
        if not isinstance(focus.get('column'), str) or focus['column'] == '':
            raise LessonError(where + ": info view requires a 'column' string")
    else:  # table
        for key in ('dependant', 'x_axis', 'y_axis'):
            if not isinstance(focus.get(key), str) or focus[key] == '':
                raise LessonError(where + ": table view requires a '" + key + "' string")


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
