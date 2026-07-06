# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# analytics.py
# append-only attempt log for learning-module answers (educator portal feature 5) + the
# per-class aggregation that reads it back.
#
# Pure module: stdlib only, no Flask (mirrors account.py / classroom.py / lessons.py). One
# JSONL log per student -- user/<userid>.attempts.jsonl (userid = classcode/username, so the
# log sits right next to that student's account pickle under the same, already-git-ignored
# user/ tree; the classcode directory already exists by the time anyone can log in). Format is
# documented in EDUCATOR_PORTAL_PROMPTS.md Appendix B.
#
# This is the full HISTORY of every graded attempt -- distinct from account.py's
# progress['answers'], which stores only the latest answer per step (drives resume/feedback).
# Never trust a client-sent 'correct' flag: log_attempt is only ever called with a record that
# app.grade_and_store already graded server-side.

import os
import json
import datetime

# "needs attention" heuristic (used by the Phase 5 dashboard via app.build_class_dashboard):
# a student is flagged as stuck on a question after this many incorrect attempts with no later
# correct answer. Kept here beside the log-reading logic that computes it; the inactivity
# window (a wall-clock comparison) lives in app.py, which owns "now".
STUCK_ATTEMPTS = 3


def _log_path(userid) -> str:
    return 'user/' + userid + '.attempts.jsonl'


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def log_attempt(userid, record) -> None:
    # Append one JSON line; never rewrites or trims prior lines.
    with open(_log_path(userid), 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')


def read_attempts(userid) -> list:
    # Full attempt history for one student, oldest first. No log yet -> []. A corrupted line
    # (e.g. a torn write) is skipped rather than failing the whole read -- an append-only log
    # should degrade gracefully, not go unreadable because of one bad line.
    path = _log_path(userid)
    if not os.path.exists(path):
        return []

    attempts = []
    with open(path, 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                attempts.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return attempts


# ---------------------------------------------------------------------------
# pure aggregation over an already-read attempts list
#
# These operate on the list read_attempts returns (oldest-first), so a caller can read each
# student's log ONCE and derive everything -- last-active, item difficulty, stuck detection --
# without re-reading the file per module. The Phase 5 dashboard folds these across a roster.
# ---------------------------------------------------------------------------

def last_active_ts(attempts) -> str | None:
    # Most recent attempt timestamp (ISO string) in a list, or None. Timestamps are the only
    # dated signal we log; a student who only read/explored (never answered) has no timestamp.
    latest = None
    for record in attempts:
        ts = record.get('ts')
        if ts and (latest is None or ts > latest):
            latest = ts
    return latest


def item_stats(attempts, module_id) -> dict:
    # Per-question attempt/correct counts for ONE student's log, one module: {step (str):
    # {'attempts': n, 'correct': n}}. Counts every attempt (repeats included), so summing these
    # across a roster gives attempt-level item difficulty (distinct from a per-student score).
    per_question = {}
    for record in attempts:
        if record.get('module') != module_id:
            continue
        step = str(record.get('step'))
        entry = per_question.setdefault(step, {'attempts': 0, 'correct': 0})
        entry['attempts'] += 1
        if record.get('correct'):
            entry['correct'] += 1
    return per_question


def stuck_questions(attempts, module_id, threshold=STUCK_ATTEMPTS) -> list:
    # Questions in one module where this student is stuck: >= threshold incorrect attempts and
    # their MOST RECENT attempt on that question is still not correct (a later correct answer
    # means they recovered -- not stuck). Returns [{'step': int, 'misses': int}], step-ordered.
    by_step = {}
    for record in attempts:
        if record.get('module') != module_id:
            continue
        by_step.setdefault(str(record.get('step')), []).append(record)

    stuck = []
    for step, records in by_step.items():
        misses = sum(1 for r in records if r.get('correct') is False)
        if misses >= threshold and not records[-1].get('correct'):
            stuck.append({'step': int(step), 'misses': misses})

    stuck.sort(key=lambda s: s['step'])
    return stuck


def question_stats(class_obj, module_id) -> dict:
    # Aggregate one module's attempts across a class's roster: per-question (step index,
    # as a string key) correct/attempt counts for item-level miss rates, and per-student
    # last-active timestamps (this module only). Reads only the roster's own logs -- never
    # another class's students. (The Phase 5 dashboard reads each log once and folds the pure
    # helpers above instead; this stays as the standalone per-module summary.)
    per_question = {}
    last_active = {}

    for userid in class_obj.get('roster', []):
        attempts = read_attempts(userid)

        for step, counts in item_stats(attempts, module_id).items():
            entry = per_question.setdefault(step, {'attempts': 0, 'correct': 0})
            entry['attempts'] += counts['attempts']
            entry['correct'] += counts['correct']

        ts = last_active_ts([r for r in attempts if r.get('module') == module_id])
        if ts:
            last_active[userid] = ts

    return {'per_question': per_question, 'last_active': last_active}
