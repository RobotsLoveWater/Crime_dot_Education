# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# app.py
# web interface

from flask import Flask
from flask import render_template
from flask import session
from flask import request
from flask import redirect, url_for
from flask import flash
from flask import Response

from markupsafe import Markup, escape

import os
import html
import re
import json
import datetime
import io
import csv
import collections
import statistics
import urllib.parse

import util
import make_history
import moc
import account
import classroom
import lessons
import analytics
import geo

from data import Data

import cache
from cache import get_data, get_moc_options, _execute, history_text_to_item, history_item_to_text

# create the app
app = Flask(__name__)

# session signing key. In production set the SECRET_KEY environment variable; the
# fallback below is a clearly-marked development-only key. Because the fallback is
# committed to a public repo it provides no security, and any deployment without a
# stable SECRET_KEY will not keep sessions valid across machines (or across restarts
# if you swap the fallback for a random value).
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    app.secret_key = 'INSECURE-dev-only-secret-key--set-the-SECRET_KEY-environment-variable'
    app.logger.warning(
        'SECRET_KEY environment variable is not set - falling back to the INSECURE '
        'development-only key. Do not run this way in production: sessions are forgeable, '
        'and they will not be portable across machines without a stable SECRET_KEY.'
    )

# codes starts empty
codes = ['']

# MOC data is an object imported from another python file
MOC = moc.MnOffenseCodes

# codebook metadata only (descriptions + column-browser groups) — no dataframe is
# loaded; Data() without a preload just parses codebook.xml
CODEBOOK = Data()

# Eagerly load the shared, immutable base DataFrame at import time (Lever B's singleton).
# Under gunicorn `--preload` (Lever D) the WSGI app is imported in the master process
# BEFORE fork, so this parse happens once in the master and every worker inherits the
# base copy-on-write instead of parsing its own — collapsing WORKERS x base down to ~one
# shared copy. CoW only holds because the heavy columns are categorical (Lever A): they
# are backed by numpy int code-arrays, not per-cell Python objects, so serving reads over
# them don't churn refcounts and dirty the shared pages. Best-effort: a missing/broken
# base datafile must not block startup — log and fall back to Lever B's per-request lazy
# load (also what happens without `--preload`, giving per-worker load-once).
try:
    cache._base_df()
    app.logger.info('Base DataFrame preloaded at import (shared across --preload workers).')
except Exception as _base_exc:  # noqa: BLE001 — never let a missing base block app startup
    app.logger.warning(
        'Base DataFrame not preloaded at import (%s); falling back to lazy per-request load.',
        _base_exc,
    )
else:
    # Geo foundation startup assertion (VISUALIZATION_EXPANSION.md §4 / _PROMPTS.md Phase 7):
    # once the base is loaded, EVERY dataset county must map to exactly one map feature, or
    # a choropleth would silently drop a county. A mismatch is a real bug (data/geometry
    # drift), so — unlike a merely-missing base above — let it propagate and fail startup
    # loudly. Warming the crosswalk here also verifies its groupby succeeds. This runs only
    # when the base actually loaded; a base-less dev machine skips it (it can't build a map
    # anyway) rather than crashing the landing page.
    geo.assert_county_coverage(cache.county_values())
    cache._county_crosswalk()
    app.logger.info('MN county->feature join verified for all 87 counties; crosswalk warmed.')

# sort orders for the statistics value table: internal key -> student-facing label
SORT_OPTIONS = [
    ('occurrence', 'Most common'),
    ('reverse_occurrence', 'Least common'),
    ('alphanumeric', 'A to Z'),
    ('reverse_alphanumeric', 'Z to A')
]

# tooltip for the excluded columns in the column browser (replaces !!!WARNING!!!)
EXCLUDED_NOTE = 'Excluded from analysis — identifies individual people or cases.'


@app.template_filter('share_chain')
def share_chain(history):
    # Builds the /share/<chain> path segment from a user's own active filters (educator
    # portal Phase 9): history[1:] -- history[0] is always the base "load everything" entry
    # (action=None) and isn't itself a token. Each step's token is percent-encoded
    # independently before joining on ',' so a literal ',' (or '/', etc.) inside a filter
    # value can never be mistaken for the outer delimiter -- apply_share below reverses this
    # exactly (split on ',', then unquote each piece).
    tokens = [history_item_to_text(entry) for entry in history[1:]]
    return ','.join(urllib.parse.quote(t, safe='') for t in tokens)


@app.template_filter('lesson_body')
def lesson_body(text):
    # Minimal, dependency-free markdown for lesson step bodies. The markdown-vs-HTML
    # question is still open (see LEARNING_MODULES_PROMPTS.md Appendix C); this covers the
    # subset the fixtures use: paragraphs, **bold**, *italic*, `inline code`, "- " bullet
    # lists, and a lone "---" line as a horizontal rule (citation-heavy lessons use it to
    # separate body text from a references block).
    # Author text is HTML-escaped FIRST, so nothing here can inject markup.
    if not text:
        return Markup('')

    text = str(escape(text))
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*\n]+)\*', r'<em>\1</em>', text)

    blocks = []
    for block in re.split(r'\n\s*\n', text):
        lines = [ln for ln in block.split('\n') if ln.strip() != '']
        if len(lines) == 1 and lines[0].strip() == '---':
            blocks.append('<hr>')
        elif lines and all(ln.startswith('- ') for ln in lines):
            blocks.append('<ul>' + ''.join('<li>' + ln[2:] + '</li>' for ln in lines) + '</ul>')
        elif lines:
            blocks.append('<p>' + '<br>'.join(lines) + '</p>')

    return Markup(''.join(blocks))


# full-dataset case count for the sidebar badge ("N of 294,467 cases"); constant for a
# given cache/raw.csv, so compute it once per process from the base cache entry
_dataset_total = None


def dataset_total():
    # full-dataset case count, memoized (used by the sidebar badge and the lesson-data module)
    global _dataset_total
    if _dataset_total is None:
        _dataset_total = get_data(None)['entries']
    return _dataset_total


def current_user():
    # best-effort user lookup for layout context (error handlers, context processor);
    # never raises — a missing pickle just renders the logged-out shell
    if not is_logged_in():
        return None
    try:
        return account.retrieve(session['userid'])
    except FileNotFoundError:
        return None


@app.context_processor
def inject_globals():
    # layout.html needs these on every page: the footer year and the sidebar's
    # data-state counts. Failures degrade to no badge rather than a broken page.
    context = {'current_year': datetime.date.today().year, 'datastate': None}

    if is_logged_in():
        try:
            context['datastate'] = {
                'entries': get_data(session)['entries'],
                'total': dataset_total()
            }
        except Exception:
            pass

    return context


def hx_toast(response, message, category='info'):
    # htmx-response toast path (wired in Phase 1, used from Phase 2 on): the HX-Trigger
    # header fires a client-side "toast" event that app.js renders into the toast region
    response.headers['HX-Trigger'] = json.dumps({'toast': {'message': message, 'category': category}})
    return response


def wants_fragment():
    # htmx view swaps get just the partial; everything else — including htmx history
    # restores, which expect a complete document — gets the full workbench page
    return (request.headers.get('HX-Request') == 'true'
            and request.headers.get('HX-History-Restore-Request') != 'true')


@app.template_filter('display_value')
def display_value(value):
    # float64 columns hold integral values like 2015.0; show them as "2015"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', user=current_user(), code=404,
                           heading='Page not found',
                           message="That page doesn't exist or may have moved. "
                                   "Head back home to keep exploring."), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', user=current_user(), code=500,
                           heading='Something went wrong',
                           message='The server hit an unexpected error. Your data state is '
                                   'safe — try again, or head back home.'), 500


def resolve_assignment(user, module_id):
    # Effective per-module assignment state across every class a student is enrolled in
    # (educator portal Phase 6, feature 4). None means "no restriction" — public/unmanaged
    # users and educators (neither carries a 'classes' membership) always see every module.
    # A module is hidden only when EVERY enrolled class hides it; otherwise the most
    # permissive non-hidden entry applies (required/scheduled outrank optional, soonest due
    # date first) — a student in two sections isn't blocked by one section's settings. A
    # class with no explicit entry for a module defaults to 'optional'.
    class_ids = user.get('classes', [])
    if not class_ids:
        return None

    entries = []
    for class_id in class_ids:
        try:
            class_obj = classroom.get_class(class_id)
        except classroom.ClassError:
            continue
        entries.append(class_obj.get('assignments', {}).get(
            module_id, {'state': 'optional', 'open': None, 'due': None}))

    if not entries:
        return {'state': 'optional', 'open': None, 'due': None}

    visible = [e for e in entries if e.get('state') != 'hidden']
    if not visible:
        return {'state': 'hidden', 'open': None, 'due': None}

    def rank(e):
        priority = 0 if e['state'] in ('required', 'scheduled') else 1
        return (priority, e.get('due') or '9999-12-31')

    return min(visible, key=rank)


def visible_modules(user):
    # Catalog filtering (Phase 6): an enrolled student sees only their class's non-hidden
    # assigned modules; public/unmanaged users and educators see every module.
    modules = lessons.list_modules()
    if not user:
        return modules
    return [m for m in modules if (resolve_assignment(user, m['id']) or {}).get('state') != 'hidden']


_DEFAULT_POLICY = {'attempts': None, 'reveal_after_miss': False, 'show_tolerance': False}


def resolve_policy(user):
    # Retake & feedback policy (educator portal Phase 11, feature 11): per-class toggles that
    # govern the question flow -- attempts allowed, whether a miss reveals the correct answer,
    # whether the numeric tolerance is shown. Public/unmanaged users and educators (no 'classes'
    # membership) always get the permissive defaults above -- current behavior, unaffected.
    # A student in multiple classes takes the STRICTEST setting across all of them (mirrors
    # resolve_assignment's cross-class aggregation): the smallest attempts cap, and reveal/
    # tolerance only when every enrolled class allows it.
    class_ids = user.get('classes', [])
    if not class_ids:
        return dict(_DEFAULT_POLICY)

    entries = []
    for class_id in class_ids:
        try:
            class_obj = classroom.get_class(class_id)
        except classroom.ClassError:
            continue
        entries.append(class_obj.get('policy', _DEFAULT_POLICY))

    if not entries:
        return dict(_DEFAULT_POLICY)

    capped = [e.get('attempts') for e in entries if e.get('attempts') is not None]
    return {
        'attempts': min(capped) if capped else None,
        'reveal_after_miss': all(e.get('reveal_after_miss', False) for e in entries),
        'show_tolerance': all(e.get('show_tolerance', False) for e in entries),
    }


def attempts_used_for(userid, module_id, step_index):
    # Count of already-graded attempts on one question, read back from the append-only
    # attempt log (feature 5) -- the same source the item-analytics dashboard reads, so the
    # attempt cap and the "N misses" triage view can never disagree.
    attempts = analytics.read_attempts(userid)
    return analytics.item_stats(attempts, module_id).get(str(step_index), {}).get('attempts', 0)


def question_locked(userid, module_id, step_index, step, policy):
    # 'free' answers are never logged as attempts (nothing to grade), so a cap never applies.
    if step['answer']['type'] == 'free' or policy['attempts'] is None:
        return False
    return attempts_used_for(userid, module_id, step_index) >= policy['attempts']


def render_landing(user):
    # The marketing landing (logged-out home, and /landing for anyone). Honest metric
    # cards: the fixed dataset facts plus the real lesson count / completion for this user.
    modules = visible_modules(user)

    lessons_completed = 0
    if user:
        progress = user.get('progress', {})
        lessons_completed = sum(1 for m in modules if progress.get(m['id'], {}).get('completed'))

    return render_template('index.html', user=user, lesson_count=len(modules),
                           lessons_completed=lessons_completed)


def in_progress_lesson(user):
    # The first started-but-unfinished lesson (in catalog order), for the "Continue …"
    # resume nudge on arrival. Reads only stored progress — no data replay. None if none.
    progress = user.get('progress', {})
    for m in visible_modules(user):
        entry = progress.get(m['id'])
        if entry and not entry.get('completed'):
            return {'id': m['id'], 'title': m['title'],
                    'step': resume_step(entry, len(m['steps']))}
    return None


# homepage
@app.route("/")
def index():
    # For a logged-in user the workbench IS home: drop them straight into Statistics, with a
    # one-time "Continue <lesson>" toast when a lesson is still in progress. Logged out: the
    # landing. (/landing below always renders the landing, even when signed in.)
    if is_logged_in():
        try:
            user = account.retrieve(session['userid'])
        except FileNotFoundError:
            # the session points at an account that no longer exists (e.g. it was deleted from
            # the roster, or the user store was reset) — clear the stale cookie and treat the
            # visitor as logged out rather than 500ing. "/" is the entry point everyone hits, so
            # clearing here recovers the whole app for that session.
            session.clear()
            return render_landing(None)
        resume = in_progress_lesson(user)
        if resume:
            # Markup.format escapes the substituted title; the url_for value is already safe
            flash(Markup('Continue your lesson: <a href="{}">{}</a>.').format(
                url_for('lesson_step', module_id=resume['id'], step=resume['step']),
                resume['title']), 'info')
        return redirect(url_for('explore'))

    return render_landing(None)


@app.route("/landing")
def landing():
    # Always the landing page (unlike "/"), so a signed-in user can still reach the overview.
    return render_landing(current_user())


@app.route("/guide")
def guide():
    if is_logged_in():

        # set the user based on cookies
        user = account.retrieve(session['userid'])

    else:

        user = None

    return render_template('guide.html', user=user)

# ---------------------------------------------------------------------------
# Signup / login "code" box resolution (educator portal, Phase 2)
# ---------------------------------------------------------------------------

def resolve_class_code(raw_code):
    # The single "class code" field on /new and /login is overloaded; resolve it once, the same
    # way for both routes, so they can never disagree on what a code means. Returns a dict:
    #   'kind'      -- 'public' | 'educator' | 'class' | 'unknown'
    #   'classcode' -- the namespace an account lives under (unmanaged / edu-* / class_id / typed)
    #   'class_obj' -- the resolved class dict when kind == 'class', else None
    #
    #   blank      -> public / 'unmanaged'  (unchanged historical behavior)
    #   edu-*      -> educator account       (unchanged; is_educator=True at create)
    #   join code  -> student enrollment; the namespace is the immutable class_id
    #   else       -> 'unknown': /new rejects it ("no class found"); /login treats it as the
    #                 typed classcode, so pre-portal bare-directory accounts still authenticate.
    code = (raw_code or '').strip()

    if code == '':
        return {'kind': 'public', 'classcode': account.NO_CLASS_CODE, 'class_obj': None}

    # keep the historical html.escape on any stored classcode (edu-/legacy). Valid edu- and join
    # codes carry no HTML-special characters, so this never alters a real code.
    escaped = html.escape(code)

    if account.is_educator_classcode(escaped):
        return {'kind': 'educator', 'classcode': escaped, 'class_obj': None}

    # case-insensitive, skips archived classes, returns None on no match
    class_obj = classroom.find_by_join_code(code)
    if class_obj is not None:
        return {'kind': 'class', 'classcode': class_obj['class_id'], 'class_obj': class_obj}

    return {'kind': 'unknown', 'classcode': escaped, 'class_obj': None}


def email_policy_message(class_obj):
    # user-facing rejection copy when a class requires an allowed-domain email username (feature 3)
    policy = class_obj.get('email_policy', {})
    domains = [d.strip().lstrip('@') for d in policy.get('domains', [])
               if isinstance(d, str) and d.strip()]
    if domains:
        pretty = ' or '.join('@' + d for d in domains)
        return ('This class requires your username to be a school email address ending in '
                + pretty + '.')
    return 'This class requires your username to be a valid email address.'


def educator_namespace(username):
    # An educator account is stored under a namespace DERIVED from its own username
    # (edu-<username>), so the "I'm an educator" checkbox is the only thing an educator ever
    # supplies — /login can find the account without them typing any code. The edu- prefix stays
    # a BACKEND-ONLY convention: it still flips is_educator via account.is_educator_classcode,
    # but it is never shown or typed. Deriving the namespace from the username keeps each
    # educator's module-authoring scope (module 'author' == classcode) unique and makes educator
    # usernames globally unique. Pass the already-html.escaped username (as /new and /login do),
    # so the namespace matches the userid that form_userid builds.
    return account.EDUCATOR_CLASSCODE_PREFIX + username


# account creation page
@app.route("/new", methods=['GET', 'POST'])
def new():
    errors = None

    if request.method == 'POST':

        # the password MUST go through util.normalize_password — the same helper /login verifies
        # with — so create and verify can never drift (see util.py)
        password = util.normalize_password(request.form['password'])
        username = html.escape(request.form['username'])

        if request.form.get('is_educator') == 'on':
            # Educator signup: the "I'm an educator" checkbox is the only signal — the class-code
            # box is ignored. The account is namespaced under edu-<username> (educator_namespace),
            # a backend-only convention that account.create turns into is_educator=True.
            classcode = educator_namespace(username)
            if username in account.get_user_list(classcode):
                return render_template('new.html',
                                       errors=['An educator account named ' + username + ' already exists.'])
            new_user = account.create(username, classcode, util.get_hashed_password(password))
        else:
            # resolve the student/public "code" box: public / class enrollment / error. (Typing a
            # literal edu- code still resolves to an educator account as a legacy fallback, but the
            # checkbox above is the supported way to sign up as an educator.)
            resolution = resolve_class_code(request.form['classcode'])

            # a non-blank, non-edu code matching no live class creates nothing (the old behavior
            # silently spun up a stray user/<code>/ directory — that is what this replaces)
            if resolution['kind'] == 'unknown':
                return render_template('new.html',
                                       errors=['No class found with that code. Leave the code blank to join '
                                               'the public group, or check the join code with your teacher.'])

            # email-domain policy (feature 3) is a join-time check — enforce before creating anything
            if resolution['kind'] == 'class' and not classroom.email_allowed(
                    resolution['class_obj'].get('email_policy', {}), username):
                return render_template('new.html', errors=[email_policy_message(resolution['class_obj'])])

            classcode = resolution['classcode']

            # the already-exists check runs against the RESOLVED namespace (the class_id for a class)
            if username in account.get_user_list(classcode):
                errortext = 'A user by the name ' + username + ' already exists'
                if resolution['kind'] == 'class':
                    errortext += ' in ' + resolution['class_obj']['name']
                elif classcode != account.NO_CLASS_CODE:
                    errortext += ' in class ' + classcode
                return render_template('new.html', errors=[errortext])

            hashed_password = util.get_hashed_password(password)

            if resolution['kind'] == 'class':
                # student enrollment: the account is namespaced under the immutable class_id, its
                # membership is recorded on the pickle, and it is added to the class roster. Role
                # stays student (is_educator=False — a class_id never carries the edu- prefix). The
                # roster write and the 'classes' key are set together here so they cannot drift.
                class_id = resolution['class_obj']['class_id']
                new_user = account.create(username, class_id, hashed_password, classes=[class_id])
                classroom.enroll(class_id, new_user['userid'])
            else:
                # public ('unmanaged') or a legacy typed edu- code — unchanged
                new_user = account.create(username, classcode, hashed_password)

        # sign them in — set all three session keys (userid + username/classcode), matching /login
        session['username'] = new_user['username']
        session['classcode'] = new_user['classcode']
        session['userid'] = new_user['userid']

        # send them home (which drops into the workbench for a logged-in user)
        return redirect(url_for('index'))

    return render_template('new.html', errors=errors)


# login page
@app.route("/login", methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':

        # the password MUST go through util.normalize_password — the same helper /new hashes
        # with — or every stored hash would mismatch (see util.py)
        password = util.normalize_password(request.form['password'])
        username = html.escape(request.form['username'])

        if username == '':
            error = ['No username entered']

        else:

            # one generic message for BOTH unknown-username and wrong-password, so the
            # login form can't be used to enumerate which usernames exist in a class
            bad_credentials = ['Username or password is incorrect.']

            # A student no longer re-types their class code to sign in: the classcode is already
            # baked into the userid the account was created under (once, at signup), so we look
            # the username up across the class namespaces and let the password pick the account.
            if request.form.get('is_educator') == 'on':
                # Educator login: scope the lookup to the derived edu-<username> namespace — the
                # checkbox is the only signal, mirroring /new. (Educators already type no code.)
                edu_ns = educator_namespace(username)
                candidate_ids = ([account.form_userid(username, edu_ns)]
                                 if username in account.get_user_list(edu_ns) else [])
            else:
                # Student / public login: every account with this username under a non-educator
                # namespace (public 'unmanaged', a class_id, or a legacy bare classcode). A
                # username shared across classes is disambiguated by the password check below.
                candidate_ids = account.find_userids_by_username(username, include_educator=False)

            user = None
            for uid in candidate_ids:
                candidate = account.retrieve(uid)
                if util.check_password(password, candidate['password']):
                    user = candidate
                    break

            if user is None:
                error = bad_credentials
            else:
                # sign them in from the stored account (classcode already cleaned to
                # 'unmanaged' when blank), matching what /new stores in the session
                session['username'] = user['username']
                session['classcode'] = user['classcode']
                session['userid'] = user['userid']

                return redirect(url_for('index'))

    return render_template('login.html', errors=error)


@app.route("/join", methods=['GET', 'POST'])
def join():
    # Optional logged-in "Join a class" flow: an existing account enrolls in a class by its join
    # code. Unlike signup enrollment, this does NOT re-namespace the account — the pickle stays
    # under its original classcode; only the class roster and the account's 'classes' list grow
    # (updated together so they cannot drift). The email-domain policy still applies at join time.
    if not is_logged_in():
        return not_logged_in()

    user = account.retrieve(session['userid'])
    errors = None

    if request.method == 'POST':
        class_obj = classroom.find_by_join_code(request.form.get('classcode', ''))

        if class_obj is None:
            errors = ['No class found with that code. Check the join code with your teacher.']
        elif not classroom.email_allowed(class_obj.get('email_policy', {}), user['username']):
            errors = [email_policy_message(class_obj)]
        elif class_obj['class_id'] in user.get('classes', []):
            flash("You're already in " + class_obj['name'] + '.', 'info')
            return redirect(url_for('explore'))
        else:
            class_id = class_obj['class_id']
            classroom.enroll(class_id, user['userid'])
            account.add_class(user['userid'], class_id)
            flash('You joined ' + class_obj['name'] + '.', 'success')
            return redirect(url_for('explore'))

    return render_template('join.html', user=user, errors=errors)


@app.route("/logout")
def logout():
    session.pop('username', None)
    session.pop('classcode', None)
    session.pop('userid', None)
    flash('You have been logged out.')
    return not_logged_in()


def build_column_browser(data):
    # Sidebar column browser: every documented column in the current dataframe,
    # grouped per codebook.xml's `group` attributes and ordered by Data.GROUP_ORDER.
    # Descriptions come straight from the codebook parse (CODEBOOK), not the cached
    # `data['columns']` dict, so codebook edits show up without clearing the cache.
    groups = {}
    for code in data['column_list']:
        desc = CODEBOOK.codebook.get(code)
        if not desc:
            continue  # undocumented columns (e.g. dcnum2) stay out of the browser
        name = CODEBOOK.groups.get(code, 'Other')
        groups.setdefault(name, []).append({
            'code': code,
            'desc': desc,
            'excluded': code in data['excluded']
        })

    rank = {name: k for k, name in enumerate(Data.GROUP_ORDER)}
    return [{'name': name, 'columns': sorted(groups[name], key=lambda c: c['desc'].lower())}
            for name in sorted(groups, key=lambda n: (rank.get(n, len(rank)), n))]


# Hard caps on individually-drawn slices/bars for the reusable "Other"-cutoff control
# (VISUALIZATION_EXPANSION.md Phase 4). The bar tolerates a longer tail than a pie before
# "Other" takes over, but neither ever draws the full 161-value long tail (STYLEGUIDE:
# "no 161 slices"). Defaults are the no-JS/initial cutoff; the slider re-slices the head.
BAR_DEFAULT_CUTOFF, BAR_HARD_CAP = 20, 20
PIE_DEFAULT_CUTOFF, PIE_HARD_CAP = 8, 12
# The treemap caps the number of individually-drawn PARENT groups (the top-level nesting);
# the slider re-slices that head client-side and the tail folds into "Other". A treemap
# tolerates more top-level groups than a pie before it gets unreadable, but never the full
# 161-value long tail. Children (the second column) render in full under each shown parent.
TREEMAP_DEFAULT_CUTOFF, TREEMAP_HARD_CAP = 10, 30


def bucket_payload(each, default_cutoff, hard_cap):
    # Package a column's value counts as a top-N + "Other" chart payload the reusable
    # slider (static/js/otherbucket.js) can re-slice entirely client-side. Only the top
    # `hard_cap` values ship as individually-drawable marks; everything past the cap is
    # folded into a residual (tailCount + tailValues) so "Other" stays exact at any cutoff
    # without a refetch. Also emits a server-side default bucketing
    # (labels/counts/other/otherValues) for the no-JS fallback and the template chart-note.
    by_count = sorted(each, key=lambda e: e['num'], reverse=True)
    capped, tail = by_count[:hard_cap], by_count[hard_cap:]
    values = [{'label': display_value(e['value']), 'count': e['num']} for e in capped]
    tail_count = sum(e['num'] for e in tail)

    slider_max = len(values)
    slider_min = min(3, slider_max)
    cutoff = max(slider_min, min(default_cutoff, slider_max))

    head, rest = values[:cutoff], values[cutoff:]
    return {
        'values': values,               # capped head, client-sliceable
        'tailCount': tail_count,         # summed counts beyond the cap
        'tailValues': len(tail),         # distinct values beyond the cap
        'total': sum(e['num'] for e in by_count),  # all non-missing cases (share base)
        'cutoff': cutoff,
        'sliderMin': slider_min,
        'sliderMax': slider_max,
        # server-rendered default bucketing (no-JS + chart-note)
        'labels': [v['label'] for v in head],
        'counts': [v['count'] for v in head],
        'other': tail_count + sum(v['count'] for v in rest),
        'otherValues': len(rest) + len(tail),
    }


def build_chart(column_info, default_cutoff=BAR_DEFAULT_CUTOFF, hard_cap=BAR_HARD_CAP):
    # distribution bar payload (Explore + lesson data): top-N values by case count plus an
    # "Other" bucket, now carrying the reusable-slider fields so the bar's cutoff is
    # draggable. The value table below the chart still carries every value.
    return bucket_payload(column_info['each'], default_cutoff, hard_cap)


def render_explore(column=None, sorting='occurrence'):
    # Shared renderer for the explore workbench (STYLEGUIDE.md "htmx conventions"):
    # normal requests get the full page, htmx requests just the view fragment.
    user = account.retrieve(session['userid'])
    data = get_data(session)

    context = {'user': user, 'column': column, 'sorting': sorting,
               'sort_options': SORT_OPTIONS, 'excluded_note': EXCLUDED_NOTE,
               'browser': build_column_browser(data), 'data': data}

    if column:
        if column not in data['column_list'] or not CODEBOOK.codebook.get(column):
            flash("That column doesn't exist — pick one from the column browser.", 'danger')
            return redirect(url_for('explore'))

        if column in data['excluded']:
            flash('That column is excluded from analysis — it identifies individual '
                  'people or cases.', 'danger')
            return redirect(url_for('explore'))

        data = get_data(session, column, sorting)
        info = data['column_info']

        # info['each'] excludes missing rows, so missing = total - sum(value counts)
        missing = info['len'] - sum(e['num'] for e in info['each'])
        context.update({
            'data': data,
            'info': info,
            # display header from the live codebook parse, not the cached column_info —
            # cached pickles keep whatever description codebook.xml had when they were built
            'header': CODEBOOK.codebook[column],
            'missing': missing,
            'missing_percent': (100 * missing / info['len']) if info['len'] else 0,
            'chart': build_chart(info)
        })

    if wants_fragment():
        template = 'partials/explore_column.html' if column else 'partials/explore_landing.html'
        return render_template(template, fragment=True, **context)

    return render_template('explore.html', **context)


@app.route("/explore")
def explore():
    if is_logged_in():
        return render_explore()
    else:
        return not_logged_in()


@app.route("/explore/column/<column>", defaults={'sorting': 'occurrence'})
@app.route("/explore/column/<column>/<sorting>")
def explore_column(column, sorting):
    if is_logged_in():
        if sorting not in Data.VALID_SORTING:
            return redirect(url_for('explore_column', column=column))
        return render_explore(column, sorting)
    else:
        return not_logged_in()


# Legacy statistics URLs (pre-overhaul) — kept only for old bookmarks. Phase 5 pointed the
# lesson deep links at /explore/... directly, so nothing internal emits /info/... anymore.
@app.route("/info/")
def info_menu():
    return redirect(url_for('explore'))


@app.route("/info/<column>/")
@app.route("/info/<column>/<sorting>")
def info_specific(column, sorting='occurrence'):
    return redirect(url_for('explore_column', column=column, sorting=sorting))


def build_compare_options(data):
    # Picker option lists for the crosstab builder: Rows/Columns get every documented,
    # non-excluded column grouped like the column browser; the Measure picker gets the
    # numeric columns (each cell then shows that column's mean/median/std).
    axis_groups = []
    for group in build_column_browser(data):
        columns = [c for c in group['columns'] if not c['excluded']]
        if columns:
            axis_groups.append({'name': group['name'], 'columns': columns})

    numeric = sorted(
        ({'code': code, 'desc': CODEBOOK.codebook[code]}
         for code in data['numeric']
         if code not in data['excluded'] and CODEBOOK.codebook.get(code)),
        key=lambda c: c['desc'].lower())

    return axis_groups, numeric


def crosstab_error(data, measure, x_axis, y_axis):
    # Shared validation for crosstab URL args (results view, CSV download).
    # Returns a user-facing message, or None when the combination is valid.
    for col in (x_axis, y_axis):
        if (col not in data['column_list'] or col in data['excluded']
                or not CODEBOOK.codebook.get(col)):
            return "That comparison isn't available — pick columns from the lists."
    if x_axis == y_axis:
        return 'Rows and columns must be two different columns.'
    if measure != '#':
        if measure not in data['numeric'] or measure in data['excluded'] \
                or not CODEBOOK.codebook.get(measure):
            return "That measure isn't available — pick one from the list."
        if measure in (x_axis, y_axis):
            return 'The measure column must be different from the rows and columns.'
    return None


def _crosstab_key(value):
    # numeric-aware ordering for row/column headers: 2001.0 before 2010.0, text A→Z
    try:
        return (0, float(value), '')
    except (TypeError, ValueError):
        return (1, 0.0, str(value).lower())


def build_crosstab(sheet, has_measure):
    # Reshape data.get_table's nested dict into an ordered display table with per-stat
    # heatmap steps and N totals. sheet[x][y] keys arrive in dataframe order and can
    # include NaN (cases missing a value in that column) — NaN rows/columns are dropped
    # from display, so the totals only count cases that appear in the table.
    rows = sorted((x for x in sheet if x == x), key=_crosstab_key)
    cols = []
    if rows:
        cols = sorted((y for y in sheet[rows[0]] if y == y), key=_crosstab_key)

    stats = ['n', 'mean', 'mdn', 'std'] if has_measure else ['n']

    def parse(text):
        # get_table emits 'N/A' when a cell has no data for the measure column
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    grid = []
    for x in rows:
        line = []
        for y in cols:
            raw = sheet[x][y]
            cell = {'n': raw['N'],
                    'values': {'n': float(raw['N'])},
                    'display': {'n': '{:,}'.format(raw['N'])},
                    'heat': {}}
            if has_measure:
                for stat in ('mean', 'mdn', 'std'):
                    value = parse(raw[stat])
                    cell['values'][stat] = value
                    cell['display'][stat] = raw[stat] if value is not None else '–'
            line.append(cell)
        grid.append(line)

    # heatmap steps: linear 0→max ramp per stat, 8 steps (0 = unshaded); the active
    # stat's steps become .heat-N classes (server-set for N, swapped client-side)
    for stat in stats:
        peak = max((c['values'][stat] or 0 for line in grid for c in line), default=0)
        for line in grid:
            for cell in line:
                value = cell['values'][stat]
                step = 0
                if peak > 0 and value and value > 0:
                    step = max(1, round(8 * value / peak))
                cell['heat'][stat] = step

    row_totals = [sum(c['n'] for c in line) for line in grid]
    col_totals = [sum(line[j]['n'] for line in grid) for j in range(len(cols))]

    return {'rows': rows, 'cols': cols, 'grid': grid, 'stats': stats,
            'row_totals': row_totals, 'col_totals': col_totals,
            'total': sum(row_totals)}


def build_compare_chart(table):
    # grouped-bar companion, only for small tables (up to ~8×8 the bars stay readable);
    # stats holds every stat so the client-side toggle re-renders without a refetch
    if not table['rows'] or len(table['rows']) > 8 or len(table['cols']) > 8:
        return None
    return {
        'labels': [display_value(x) for x in table['rows']],
        'columns': [display_value(y) for y in table['cols']],
        'stats': {stat: [[line[j]['values'][stat] for line in table['grid']]
                         for j in range(len(table['cols']))]
                  for stat in table['stats']}
    }


def render_compare(dependant=None, x_axis=None, y_axis=None, error=None, form=None):
    # Shared renderer for the compare workbench (same pattern as render_explore):
    # builder without args, results with them; fragments on htmx requests.
    user = account.retrieve(session['userid'])
    data = get_data(session)
    context = {'user': user, 'data': data, 'error': error or []}

    if dependant:
        measure_col = None if dependant == '#' else dependant
        # crosstabs are computed fresh each time (never disk-cached, matching the old view)
        sheet = _execute(session).get_table(measure_col, x_axis, y_axis)
        table = build_crosstab(sheet, measure_col is not None)
        context.update({
            'dependant': dependant, 'x_axis': x_axis, 'y_axis': y_axis,
            'measure': measure_col,
            'measure_desc': CODEBOOK.codebook[measure_col] if measure_col else None,
            'row_desc': CODEBOOK.codebook[x_axis],
            'col_desc': CODEBOOK.codebook[y_axis],
            'table': table,
            'chart': build_compare_chart(table),
            # what the stat toggle starts on: the picked measure's mean, else the count
            'default_stat': 'mean' if measure_col else 'n'
        })
        partial = 'partials/compare_results.html'
    else:
        axis_groups, numeric = build_compare_options(data)
        context.update({'axis_groups': axis_groups, 'numeric_measures': numeric,
                        'form': form or {}})
        partial = 'partials/compare_builder.html'

    if wants_fragment():
        return render_template(partial, fragment=True, **context)
    return render_template('compare.html', **context)


@app.route("/explore/table", methods=['GET', 'POST'])
def explore_table():
    if is_logged_in():
        if request.method == 'POST':
            form = {'measure': request.form.get('measure', ''),
                    'rows': request.form.get('rows', ''),
                    'cols': request.form.get('cols', '')}

            error = []
            if not form['measure']:
                error.append('Choose a measure.')
            if not form['rows']:
                error.append('Choose a column for the rows.')
            if not form['cols']:
                error.append('Choose a column for the columns.')
            if not error:
                message = crosstab_error(get_data(session), form['measure'],
                                         form['rows'], form['cols'])
                if message:
                    error.append(message)

            if not error:
                # Orientation note: data.get_table renders x_axis values as the ROW
                # headers and y_axis values as the COLUMN headers (sheet[x][y] iterates
                # x as rows). The pre-overhaul UI labeled these "X axis"/"Y axis"
                # backwards; the flip is contained right here — Rows maps to x_axis,
                # Columns to y_axis, and users only ever see "Rows"/"Columns".
                return redirect(url_for('explore_table_view', dependant=form['measure'],
                                        x_axis=form['rows'], y_axis=form['cols']))

            return render_compare(error=error, form=form)

        return render_compare()
    else:
        return not_logged_in()


@app.route("/explore/table/<dependant>/<x_axis>/<y_axis>")
def explore_table_view(dependant, x_axis, y_axis):
    if is_logged_in():
        message = crosstab_error(get_data(session), dependant, x_axis, y_axis)
        if message:
            flash(message, 'danger')
            return redirect(url_for('explore_table'))
        return render_compare(dependant, x_axis, y_axis)
    else:
        return not_logged_in()


# Legacy crosstab URLs (pre-overhaul) — kept only for old bookmarks. Phase 5 pointed the
# lesson deep links at /explore/table/... directly, so nothing internal emits /table/... now.
@app.route("/table")
def table_menu():
    return redirect(url_for('explore_table'))


@app.route("/table/<dependant>/<x_axis>/<y_axis>")
def table(dependant, x_axis, y_axis):
    return redirect(url_for('explore_table_view', dependant=dependant,
                            x_axis=x_axis, y_axis=y_axis))


# ---------------------------------------------------------------------------
# Filter workbench (Phase 4): live previews, searchable values, MOC stepper.
# ---------------------------------------------------------------------------

def filter_column_error(data, column):
    # Shared validation for the filter column view / preview. Returns a user-facing
    # message, or None when the column can be filtered.
    if column not in data['column_list'] or not CODEBOOK.codebook.get(column):
        return "That column doesn't exist — pick one from the column browser."
    if column in data['excluded']:
        return ('That column is excluded from filtering — it identifies individual '
                'people or cases.')
    return None


def undo_target(user):
    # `revert` n for an "Undo last filter" CTA: drop just the most recent step.
    # history[0] is the base; len-1 removes the last filter (len==2 -> n=1 = base).
    return max(1, len(user['history']) - 1)


def filter_candidate(column, comparison, values):
    # The history entry a filter WOULD append, as a token-encodable action — used to
    # preview a count via history_override without mutating history. Mirrors the apply
    # path (make_history.filter_single / filter_or_same) exactly, so a preview and the
    # eventual apply resolve to the SAME cache directory (cache compatibility).
    if len(values) == 1:
        return {'desc': 'preview', 'action': ['f', column, comparison, values[0]]}
    return {'desc': 'preview', 'action': ['o', column, comparison, values]}


def numeric_value_error(values):
    # every candidate value must parse as a float (numeric columns coerce on filter)
    for value in values:
        try:
            float(value)
        except ValueError:
            return 'That value isn\'t a number. Enter a number like 14 or 14.5.'
    return None


def safe_return_target(raw):
    # A post-apply redirect override (the `next` form field a Visualize map-click / "Keep
    # only" apply sends so the drill-down lands back on the map) must stay on this site:
    # accept only an absolute local path — no scheme, no host, no protocol-relative '//',
    # and no backslashes (some browsers normalize '/\' to '//', reopening the redirect).
    if not raw or not raw.startswith('/') or raw.startswith('//') or '\\' in raw:
        return None
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return None
    return raw


# ---- Geographic map input (Phase 11) ----
# The three geography columns get a map INPUT beside their value picker: clicking a shape
# toggles the SAME checkbox (county/region) or fills the SAME numeric input (district) a
# hand-picked filter uses — the map never builds its own token, so the applied filter (and
# therefore the cache/data/ dir) is byte-identical to the list/typed path by construction.
# JS-only enhancement: the value list / input stays the complete no-JS and screen-reader
# path, with the same names and per-value counts as text.
GEO_FILTER_GRAINS = ('county', 'district', 'region')  # column name == choropleth grain id


def build_filter_map(column, info):
    # Payload for the Filter view's map input. `values` is keyed by MAP FEATURE key (the
    # TopoJSON county name, or the dissolved group key for district/region) and carries the
    # DATASET value the click must toggle/fill — for the alias counties ("LeSueur",
    # "Lac Qui Parle") the two spellings differ, and a district's value is the float-string
    # its token encodes ("4.0"). Only values present in the current slice are clickable,
    # exactly mirroring the checkbox list / input the map drives (an absent value has no
    # checkbox, so its shape is inert — same reach by map or by list).
    grain = column
    dissolve, group_labels = None, None
    if grain != 'county':
        dissolve, group_labels = build_geo_dissolve(grain)

    values = {}
    for row in info['each']:
        if grain == 'county':
            key = geo.resolve_county(row['value'])
            if key is None:                # unreconciled county (coverage asserted) — inert
                continue
            label = display_value(row['value'])
        else:
            key = _grain_key(row['value'], grain)
            label = group_labels.get(key) or _grain_label(row['value'], grain)
        # _grain_key is the dataset value as the form encodes it: the county/region string
        # verbatim, the district float as "4.0" — identical to the checkbox value attribute
        # / what a hand-typed "4.0" submits (pinned by test_map_filter_equivalence.py).
        values[key] = {'value': _grain_key(row['value'], grain),
                       'label': label,
                       'count': row['num']}

    grain_noun, grain_plural = CHOROPLETH_GRAIN_NOUNS[grain]
    return {
        'column': column,
        'grain': grain,
        # 'multi' toggles checkboxes in the categorical list; 'single' fills the numeric
        # value input (district's filter form) and forces the comparison to "equal to".
        'mode': 'single' if info['numeric'] else 'multi',
        'grainLabel': grain_noun,
        'grainLabelPlural': grain_plural,
        'topoUrl': url_for('static', filename=geo.TOPOJSON_STATIC),
        'object': geo.TOPOJSON_OBJECT,
        'dissolve': dissolve,          # {feature: group key} for district/region; None county
        'groupLabels': group_labels,   # {group key: label} so sliceless groups still name themselves
        'values': values,
    }


def render_filter(column=None, error=None):
    # Shared renderer for the filter workbench (same pattern as render_explore /
    # render_compare): full page normally, just the view fragment on htmx requests.
    user = account.retrieve(session['userid'])
    data = get_data(session)

    context = {'user': user, 'data': data, 'error': error or [], 'column': column,
               'browser': build_column_browser(data), 'excluded_note': EXCLUDED_NOTE,
               'undo_n': undo_target(user)}

    if column:
        message = filter_column_error(data, column)
        if message:
            flash(message, 'danger')
            return redirect(url_for('explore_filter'))

        data = get_data(session, column, 'occurrence')
        info = data['column_info']
        missing = info['len'] - sum(e['num'] for e in info['each'])
        context.update({
            'data': data, 'info': info,
            # display header from the live codebook parse, never the cached column_info
            'header': CODEBOOK.codebook[column],
            'missing': missing,
        })
        # geography columns get the map input beside the value picker (Phase 11); skipped
        # when the slice is empty / valueless — those states short-circuit before the form
        if column in GEO_FILTER_GRAINS and data['entries'] > 0 and info['each']:
            context['filter_map'] = build_filter_map(column, info)
        partial = 'partials/filter_column.html'
    else:
        partial = 'partials/filter_landing.html'

    if wants_fragment():
        return render_template(partial, fragment=True, **context)
    return render_template('filter.html', **context)


@app.route("/explore/filter")
def explore_filter():
    if is_logged_in():
        return render_filter()
    else:
        return not_logged_in()


@app.route("/explore/filter/<column>", methods=['GET', 'POST'])
def explore_filter_column(column):
    if not is_logged_in():
        return not_logged_in()

    data = get_data(session)
    message = filter_column_error(data, column)
    if message:
        flash(message, 'danger')
        return redirect(url_for('explore_filter'))

    if request.method == 'POST':
        error = []
        comparison = request.form.get('comparison', '')
        values = [v for v in request.form.getlist('value') if v != '']

        if comparison not in ('eq', 'ne', 'gt', 'ge', 'lt', 'le'):
            error.append('Choose how to compare.')
        elif not values:
            error.append('Enter or pick at least one value to filter by.')
        # numeric comparisons — and any comparison on a numeric column (which coerces
        # values to float) — require numeric input
        elif comparison in ('gt', 'ge', 'lt', 'le') or column in data['numeric']:
            message = numeric_value_error(values)
            if message:
                error.append(message)

        if error:
            return render_filter(column, error=error)

        # single value -> 'f'; multiple -> 'o' OR-same-column. Encoding unchanged, so a
        # multi-value categorical filter lands in the same cache dir as the old UI.
        if len(values) == 1:
            entry = make_history.filter_single(column, comparison, values[0])
        else:
            entry = make_history.filter_or_same(column, comparison, values)
        account.history_add(session['userid'], entry)

        remaining = get_data(session)['entries']
        flash('Filter applied — {:,} cases remain.'.format(remaining), 'success')
        # land back on the view we came from (not a bare redirect home): the same filter
        # column view, now showing updated chips, refreshed counts, or the zero-case state.
        # A Visualize map-click / "Keep only" apply (Phase 11) rides this same handler —
        # same validation, same make_history entry, same cache dir — and passes a validated
        # local `next` so its redirect returns to the map and the drill-down loop continues.
        target = safe_return_target(request.form.get('next'))
        return redirect(target or url_for('explore_filter_column', column=column))

    return render_filter(column)


@app.route("/explore/filter/<column>/preview")
def explore_filter_preview(column):
    # Small htmx GET: how many cases a candidate filter would keep, computed via
    # history_override with the candidate token (no history mutation). The candidate
    # resolves to the same cache dir the apply will, so this preview count equals the
    # post-apply chip count. JS-off, this endpoint is simply never called.
    if not is_logged_in():
        return not_logged_in()

    data = get_data(session)
    if filter_column_error(data, column):
        return ''  # nothing to preview for a bad/excluded column

    comparison = request.args.get('comparison', 'eq')
    values = [v for v in request.args.getlist('value') if v != '']

    context = {'count': None, 'current': data['entries'], 'message': None}

    if comparison not in ('eq', 'ne', 'gt', 'ge', 'lt', 'le'):
        context['message'] = 'Choose how to compare.'
    elif not values:
        context['message'] = 'Enter a value to preview how many cases match.'
    else:
        message = None
        if comparison in ('gt', 'ge', 'lt', 'le') or column in data['numeric']:
            message = numeric_value_error(values)
        if message:
            context['message'] = message
        else:
            candidate = filter_candidate(column, comparison, values)
            try:
                context['count'] = get_data(session, history_override=[candidate])['entries']
            except Exception:
                context['message'] = "Couldn't preview that filter — check the value."

    return render_template('partials/filter_preview.html', **context)


# ---- MOC (Minnesota Offense Code) drill-down ----

def moc_slot_positions(code_list):
    # Editable slot positions (indices into code_list, which line up with cur_moc).
    # Multi-digit INC sections collapse to their first position (the trailing INC
    # placeholder dicts are not their own slot) — same rule the old moc_col built.
    positions = []
    prev_inc = False
    for i in range(1, 5):
        if i >= len(code_list):
            break
        has_inc = isinstance(code_list[i], dict) and 'INC' in code_list[i]
        if has_inc:
            if not prev_inc:
                positions.append(i)
            prev_inc = True
        else:
            positions.append(i)
            prev_inc = False
    return positions


def moc_slot_digits(code_list, i):
    # cur_moc positions a slot writes: its own, or every digit in its INC group.
    slot = code_list[i] if i < len(code_list) else None
    if isinstance(slot, dict) and 'INC' in slot:
        return list(slot['INC'])
    return [i]


def moc_url(moc_list, active):
    return url_for('explore_moc_step', moc1=moc_list[0], moc2=moc_list[1],
                   moc3=moc_list[2], moc4=moc_list[3], moc5=moc_list[4], active=active)


def build_moc_slots(code_list, cur_moc, active):
    # One display slot per editable position: its label, decoded current value (or
    # wildcard), and a link that makes it the active slot.
    slots = []
    for i in moc_slot_positions(code_list):
        digits = moc_slot_digits(code_list, i)
        key = ''.join(cur_moc[p] for p in digits)
        is_wild = all(cur_moc[p] == '*' for p in digits)
        if is_wild:
            value = None
        elif key in code_list[i]:
            value = code_list[i][key]
        else:
            value = key  # partially set / unrecognized — show the raw digits
        slots.append({
            'index': i,
            'label': code_list[i].get('COL', 'Digit ' + str(i)),
            'value': value,
            'is_wildcard': is_wild,
            'is_active': i == active,
            'href': moc_url(cur_moc, i),
        })
    return slots


def build_moc_options(code_list, cur_moc, active, counts):
    # Choices for the active slot with the case count each would leave. An INC option
    # is a multi-char code distributed across its digit positions (e.g. '01' -> two
    # digits), so applying it later emits one per-digit `f.mocN.eq.X` filter each.
    digits = moc_slot_digits(code_list, active)

    reset = cur_moc[:]
    for p in digits:
        reset[p] = '*'
    options = [{'code': '*', 'label': "Any — don't filter this digit",
                'count': counts.get('*'), 'href': moc_url(reset, active), 'is_reset': True}]

    for key in code_list[active]:
        if key in ('COL', 'INC'):
            continue
        target = cur_moc[:]
        for offset, p in enumerate(digits):
            target[p] = key[offset]
        options.append({'code': key, 'label': code_list[active][key],
                        'count': counts.get(key), 'href': moc_url(target, active),
                        'is_reset': False})
    return options


@app.route("/explore/moc/")
def explore_moc():
    if not is_logged_in():
        return not_logged_in()

    user = account.retrieve(session['userid'])
    data = get_data(session)
    codes = [{'code': c, 'title': MOC.CODES[c][0]} for c in MOC.CODES]

    return render_template('moc1.html', user=user, data=data, codes=codes,
                           undo_n=undo_target(user))


@app.route("/explore/moc/<moc1>/<moc2>/<moc3>/<moc4>/<moc5>/<active>", methods=['GET', 'POST'])
def explore_moc_step(moc1, moc2, moc3, moc4, moc5, active):
    if not is_logged_in():
        return not_logged_in()

    if moc1 not in MOC.CODES:
        return redirect(url_for('explore_moc'))

    cur_moc = [moc1, moc2, moc3, moc4, moc5]

    if request.method == 'POST':
        # each set (non-wildcard) digit becomes its own single-filter history entry,
        # exactly as before — cache-compatible per-digit `f.mocN.eq.X` tokens
        applied = 0
        for k, digit in enumerate(cur_moc):
            if digit != '*':
                account.history_add(session['userid'], make_history.moc(k + 1, digit))
                applied += 1

        remaining = get_data(session)['entries']
        if applied:
            flash('Offense code filter applied — {:,} cases remain.'.format(remaining), 'success')
        else:
            flash('No offense-code digits were set, so nothing was filtered.', 'info')
        # back to the offense-code chooser (chips updated) to build another, if wanted
        return redirect(url_for('explore_moc'))

    user = account.retrieve(session['userid'])
    code_list = MOC.CODES[moc1]

    positions = moc_slot_positions(code_list)
    active = int(active)
    if active not in positions:
        active = positions[0] if positions else 1

    data = get_data(session)
    counts = get_moc_options(session, cur_moc[:], active)

    return render_template('moc.html', user=user, data=data, code_list=code_list,
                           cur_moc=cur_moc, active=active,
                           slots=build_moc_slots(code_list, cur_moc, active),
                           options=build_moc_options(code_list, cur_moc, active, counts),
                           active_label=code_list[active].get('COL', ''),
                           undo_n=undo_target(user))


# ---- Legacy filter URLs (pre-overhaul). Endpoint names survive for any bookmarks. ----
@app.route("/filter/")
def filter_menu():
    return redirect(url_for('explore_filter'))


@app.route("/filter/boolean/")
def filter_boolean_menu():
    return redirect(url_for('explore_filter'))


@app.route("/filter/boolean/<column>/")
@app.route("/filter/boolean/<column>/<sorting>")
def filter_boolean(column, sorting='occurrence'):
    return redirect(url_for('explore_filter_column', column=column))


@app.route("/filter/moc/")
def filter_moc1():
    return redirect(url_for('explore_moc'))


@app.route("/filter/moc/<moc1>/<moc2>/<moc3>/<moc4>/<moc5>/<active>")
def filter_moc(moc1, moc2, moc3, moc4, moc5, active):
    return redirect(url_for('explore_moc_step', moc1=moc1, moc2=moc2, moc3=moc3,
                            moc4=moc4, moc5=moc5, active=active))


def crosstab_csv(dependant, x_axis, y_axis):
    # CSV of the crosstab the results view renders — same get_table call, same
    # build_crosstab reshaping, so the numbers always match the screen.
    measure_col = None if dependant == '#' else dependant
    sheet = _execute(session).get_table(measure_col, x_axis, y_axis)
    table = build_crosstab(sheet, measure_col is not None)
    entries = get_data(session)['entries']

    row_desc = CODEBOOK.codebook[x_axis]
    col_desc = CODEBOOK.codebook[y_axis]
    measure_label = ('Mean of ' + CODEBOOK.codebook[measure_col]) if measure_col \
        else 'Count of cases'

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Minnesota Sentencing Explorer crosstab'])
    writer.writerow(['Measure', measure_label])
    writer.writerow(['Rows', row_desc + ' (' + x_axis + ')'])
    writer.writerow(['Columns', col_desc + ' (' + y_axis + ')'])
    writer.writerow(['Data state', str(entries) + ' cases'])

    col_headers = [display_value(y) for y in table['cols']]

    sections = [('n', 'Count of cases')]
    if measure_col:
        desc = CODEBOOK.codebook[measure_col]
        sections += [('mean', 'Mean of ' + desc),
                     ('mdn', 'Median of ' + desc),
                     ('std', 'Std. deviation of ' + desc)]

    for stat, label in sections:
        writer.writerow([])
        writer.writerow([label])
        header = [row_desc] + col_headers
        if stat == 'n':
            header.append('Total')
        writer.writerow(header)
        for i, x in enumerate(table['rows']):
            line = [display_value(x)]
            for j in range(len(table['cols'])):
                cell = table['grid'][i][j]
                if stat == 'n':
                    line.append(cell['n'])  # raw int — Excel-friendly, no thousands separator
                else:
                    value = cell['values'][stat]
                    # the display string carries the same rounding the screen shows
                    line.append('' if value is None else cell['display'][stat])
            if stat == 'n':
                line.append(table['row_totals'][i])
            writer.writerow(line)
        if stat == 'n':
            writer.writerow(['Total'] + table['col_totals'] + [table['total']])

    filename = ('crosstab-' + (measure_col if measure_col else 'count')
                + '-' + x_axis + '-by-' + y_axis + '.csv')
    # BOM so Excel reads the file as UTF-8 (codebook descriptions can carry non-ASCII)
    response = Response('\ufeff' + buffer.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename="' + filename + '"'
    return response


@app.route('/download')
def download():
    # Crosstab CSV export (Phase 3). Query args mirror the results view: measure
    # ('#' = count of cases) plus the rows/cols display columns.
    if is_logged_in():
        measure = request.args.get('measure', '')
        rows = request.args.get('rows', '')
        cols = request.args.get('cols', '')

        if not (measure and rows and cols):
            flash('Build a comparison first — the CSV download exports the table '
                  'you are viewing.', 'danger')
            return redirect(url_for('explore_table'))

        message = crosstab_error(get_data(session), measure, rows, cols)
        if message:
            flash(message, 'danger')
            return redirect(url_for('explore_table'))

        return crosstab_csv(measure, rows, cols)
    else:
        return not_logged_in()


# ---------------------------------------------------------------------------
# Visualize workbench (VISUALIZATION_EXPANSION.md): a blank-canvas chart builder
# over the current data state. Phase 3 is the shell — the route family, the
# fragment plumbing, the sidebar sync, and an empty builder. Chart families
# (pie / treemap / waterfall / choropleth / scatter / correlation) plug their
# render in across Tiers 2–4; until a type is built the canvas shows a "coming
# soon" placeholder, but its selection is already URL-encoded so hard refresh and
# lesson deep links work from day one. Nothing here computes off the active
# history yet (that starts with the real charts).
# ---------------------------------------------------------------------------

# The chart-type registry. `status` gates the canvas: 'coming' shows the placeholder,
# flipped to 'ready' as each tier lands. Order = builder display order.
VIZ_CHART_TYPES = [
    {'id': 'pie',         'label': 'Pie',                'status': 'ready',
     'blurb': 'Share of cases across one categorical column.'},
    {'id': 'treemap',     'label': 'Treemap',            'status': 'ready',
     'blurb': 'Two columns nested as proportional areas.'},
    {'id': 'waterfall',   'label': 'Waterfall',          'status': 'ready',
     'blurb': 'Year-over-year change in a count, mean, or median across sentencing years.'},
    {'id': 'choropleth',  'label': 'Map (choropleth)',   'status': 'ready',
     'blurb': 'Minnesota counties shaded by case count, mean, median, or mode.'},
    {'id': 'scatter',     'label': 'Scatter / bubble',   'status': 'ready',
     'blurb': 'Two numeric columns as an aggregated lattice; case count sizes the dots.'},
    {'id': 'correlation', 'label': 'Correlation matrix', 'status': 'ready',
     'blurb': 'Pearson correlations across a numeric subset, drawn as a heatmap.'},
]

# Aggregate picker options: student-facing labels over Phase 1's Data.VALID_AGGREGATES.
VIZ_AGGREGATE_OPTIONS = [
    ('count', 'Count of cases'),
    ('mean', 'Mean'),
    ('median', 'Median'),
    ('mode', 'Mode'),
]

# The get_table stat key each treemap aggregate reads (count sizes by the cell N directly).
# 'mode' is intentionally absent: get_table computes no mode, and sizing a part-of-whole
# area by a modal value is nonsensical (VISUALIZATION_EXPANSION.md §6.1's carve-out).
TREEMAP_STAT_KEY = {'mean': 'mean', 'median': 'mdn'}

# The waterfall walks a numeric aggregate across sentencing years, so its group column is
# fixed (unlike pie/treemap, which chart a user-picked column) — the 2016 Drug Sentencing
# Reform break is the marquee series. Only the *column* is fixed; build_waterfall reads
# whatever year range the current slice actually contains, so nothing is hardcoded.
WATERFALL_GROUP = 'sentyear'

# The aggregates a waterfall can walk. 'mode' is intentionally excluded (like the treemap):
# a year-over-year change in a modal value doesn't read as a running total and its deltas
# don't sum meaningfully. count/mean/median each produce a coherent delta chain.
WATERFALL_AGGREGATES = ('count', 'mean', 'median')

# The choropleth (Phase 8) shades MN counties by a per-county aggregate over the active slice.
# Unlike the treemap/waterfall it DOES allow 'mode' — a modal numeric value per county is a
# coherent point statistic (it's not a running total or a part-of-whole), so all four
# aggregates in VIZ_AGGREGATE_OPTIONS are valid: count needs no measure, mean/median/mode
# summarize a numeric measure. Phase 8 is county grain only; the district/region grain toggle
# lands in Phase 9 (the geometry dissolves from the same county TopoJSON via cache's crosswalk).
CHOROPLETH_AGGREGATES = ('count', 'mean', 'median', 'mode')
# The choropleth reuses the crosstab heatmap's discrete ramp: an 8-step 0→peak scale, colored
# from the same .heat-1..8 CSS tokens (build_crosstab / STYLEGUIDE "Heatmap cells"), so a county
# and a crosstab cell of equal value read the same shade.
CHOROPLETH_HEAT_STEPS = 8

# Small-N texture (Phase 10). A geography with only a handful of cases is a thin sample: its
# aggregate (a mean/median/mode, or even a raw count read as a "hotspot") is dominated by one or
# two atypical cases and shouldn't read as a confident color. Below this many cases a shape is
# filled with a hatch TEXTURE instead — not grey (that's "no data") and not a ramp color — and
# its tooltip states the suppression + the N. Thin groups are ALSO excluded from the ramp's peak
# so a single noisy small sample can't set the color scale for the reliable ones; they are never
# dropped or greyed (that would hide the uncertainty rather than flag it). One documented
# threshold, in the same named-constant spirit as analytics.STUCK_ATTEMPTS — a small-cell
# reliability floor (10 is a common suppression cutoff in public reporting), not a formal power
# calculation (this is the population of sentences, not a sample).
CHOROPLETH_MIN_N = 10

# --- Choropleth grain (Phase 9): county | judicial district | region -----------------
# The three-level grain switch. `county` uses the native county TopoJSON; `district` and
# `region` DISSOLVE that same geometry at runtime (client-side, via cache's county->district/
# region crosswalk) — there is NO district/region geometry file. Switching grain switches the
# GROUP COLUMN the per-group aggregate reads (county/district/region), so each shape's value is
# the categorical aggregate over that column directly — never a sum or mean of county values.
CHOROPLETH_GRAINS = [
    {'id': 'county',   'label': 'County'},
    {'id': 'district', 'label': 'Judicial district'},
    {'id': 'region',   'label': 'Region'},
]
CHOROPLETH_GRAIN_IDS = {g['id'] for g in CHOROPLETH_GRAINS}
# The dataset column each grain groups by (and, in Phase 11, the map-click filter targets).
CHOROPLETH_GRAIN_COLUMN = {'county': cache.COUNTY_COLUMN, 'district': 'district', 'region': 'region'}
# Singular / plural nouns for headings + the companion table, per grain.
CHOROPLETH_GRAIN_NOUNS = {
    'county':   ('County', 'counties'),
    'district': ('Judicial District', 'judicial districts'),
    'region':   ('Region', 'regions'),
}
# Friendly display overrides for cryptic categorical group values (region's "Oth Metro").
REGION_LABELS = {'Oth Metro': 'Other Metro'}


def _grain_key(value, grain):
    # Canonical string key for a grain group value — shared by the by-feature map, the dissolve
    # map, and (Phase 11) the filter token. `district` is float64, so its key is "4.0" — exactly
    # what f.district.eq.4.0 encodes; region/county keys are the string value.
    if grain == 'district':
        return str(float(value))
    return str(value)


def _grain_label(value, grain):
    # Human label for a grain group: a district float reads "Judicial District 4"; region's
    # cryptic "Oth Metro" reads "Other Metro"; anything else keeps its display spelling.
    if grain == 'district':
        return 'Judicial District %d' % int(round(float(value)))
    if grain == 'region':
        return REGION_LABELS.get(str(value), str(value))
    return display_value(value)


def build_geo_dissolve(grain):
    # The dissolve map for a merged grain (district/region): {county feature name: group key}
    # — how the client merges county shapes into one feature per group — plus
    # {group key: display label} naming every group in the grain. ONE implementation shared
    # by the choropleth payload and the Filter view's map input (Phase 11), so the two map
    # surfaces can never disagree about which counties form a district or region. Group keys
    # come from _grain_key, so a district's key is the exact string its filter token carries
    # ("4.0" — see the map-click equivalence in test_map_filter_equivalence.py).
    crosswalk = cache._county_crosswalk()[grain]   # {county name: district/region value}
    dissolve = {}          # {county feature name: group key}
    group_labels = {}      # {group key: display label} — ALL groups in the grain
    for county, group_val in crosswalk.items():
        feature = geo.resolve_county(county)
        if feature is None:                        # coverage asserted at startup
            continue
        key = _grain_key(group_val, grain)
        dissolve[feature] = key
        group_labels[key] = _grain_label(group_val, grain)
    return dissolve, group_labels


def _viz_column_ok(data, column, errors):
    # Same validation Explore uses before charting a column; appends a user-facing message
    # to `errors` and returns False when the column can't be charted.
    if column not in data['column_list'] or not CODEBOOK.codebook.get(column):
        errors.append("That column doesn't exist — pick one from the column browser.")
        return False
    if column in data['excluded']:
        errors.append('That column is excluded from analysis — it identifies individual '
                      'people or cases.')
        return False
    return True


def resolve_treemap_measure(measure, aggregate, data, errors):
    # Resolve a treemap's (measure, aggregate) into the get_table measure column.
    # count -> None (size areas by case count); mean/median -> a numeric measure column.
    # Appends a message + returns (None, False) when the pair is incoherent for a treemap.
    if aggregate == 'count':
        return None, True                       # measure is irrelevant to a plain count
    if aggregate not in TREEMAP_STAT_KEY:
        errors.append('The treemap sizes areas by count, mean, or median — mode isn’t '
                      'available for it.')
        return None, False
    if measure == '#' or measure not in data['numeric'] \
            or measure in data['excluded'] or not CODEBOOK.codebook.get(measure):
        errors.append('Mean and median need a numeric measure — pick one from the '
                      'Measure list.')
        return None, False
    return measure, True


def build_treemap(sheet, aggregate, measure_col, x_col, y_col):
    # Reshape data.get_table's nested sheet[x][y] = {N, mean, mdn, std} (the SAME crosstab
    # the Compare view draws) into a nested top-N-parents + "Other" treemap payload plus a
    # flat companion table. Leaf area = the chosen aggregate per cell: count -> N;
    # mean/median -> the cell statistic (get_table emits 'N/A' when the measure is all-NaN,
    # which we drop). Parents are ordered by case count (N) so the slider's "top N groups"
    # reads intuitively; the tail folds into "Other". For count the areas are a true
    # part-of-whole — each parent = its crosstab row total, and every shown value reconciles
    # with the Compare crosstab exactly.
    stat_key = TREEMAP_STAT_KEY.get(aggregate)

    def cell_value(cell):
        if aggregate == 'count':
            return float(cell['N'])
        try:
            return float(cell[stat_key])
        except (TypeError, ValueError):
            return None                          # 'N/A' -> no area to draw

    parents = []
    for x in sheet:
        if x != x:                               # drop NaN row key (missing this column)
            continue
        children = []
        for y in sheet[x]:
            if y != y:                           # drop NaN column key
                continue
            cell = sheet[x][y]
            n = int(cell['N'])
            value = cell_value(cell)
            if n <= 0 or value is None or value <= 0:
                continue                         # nothing to draw for this cell
            children.append({'label': display_value(y), 'value': value, 'n': n})
        if not children:
            continue
        children.sort(key=lambda c: c['value'], reverse=True)
        parents.append({'label': display_value(x),
                        'value': sum(c['value'] for c in children),
                        'n': sum(c['n'] for c in children),
                        'children': children})

    parents.sort(key=lambda p: p['n'], reverse=True)

    # cap the individually-drawn parent groups; the slider re-slices this head client-side
    # (static/js/visualize.js) and folds everything past the cutoff — plus the tail beyond
    # the hard cap — into "Other", with no refetch.
    capped = parents[:TREEMAP_HARD_CAP]
    tail = parents[TREEMAP_HARD_CAP:]
    slider_max = len(capped)
    slider_min = min(3, slider_max)
    cutoff = max(slider_min, min(TREEMAP_DEFAULT_CUTOFF, slider_max))

    payload = {
        'parents': capped,
        'tailValue': sum(p['value'] for p in tail),   # summed leaf value beyond the cap
        'tailN': sum(p['n'] for p in tail),
        'tailGroups': len(tail),                       # distinct parents beyond the cap
        'aggregate': aggregate,
        'total': sum(p['value'] for p in parents),
        'totalN': sum(p['n'] for p in parents),
        'cutoff': cutoff, 'sliderMin': slider_min, 'sliderMax': slider_max,
        'xLabel': CODEBOOK.codebook[x_col], 'yLabel': CODEBOOK.codebook[y_col],
        'measureLabel': 'cases' if aggregate == 'count' else CODEBOOK.codebook[measure_col],
    }

    # flat companion table: every drawn cell, largest value first (the no-JS/a11y fallback)
    rows = [{'x': p['label'], 'y': c['label'], 'value': c['value'], 'n': c['n']}
            for p in parents for c in p['children']]
    rows.sort(key=lambda r: r['value'], reverse=True)

    return payload, rows


# Scatter / bubble (Phase 12). Two NUMERIC columns aggregated to a lattice: one bubble per
# (x, y) cell that has cases, positioned at those numeric coordinates and sized by the cell's
# count. NEVER one mark per row — 294k points overplot into noise (the design doc's whole point).
# The lattice IS data.get_table(None, x, y) — the SAME cell counts a Compare crosstab shows — so a
# bubble's size reconciles with the crosstab exactly. Because get_table is O(|x_unique| * |y_unique|)
# nested filters, a pair of high-cardinality numerics (e.g. two ~200-value columns) is both slow to
# build and unreadable once drawn, so the builder rejects a lattice whose cell budget exceeds this
# cap with a "filter first / pick lower-cardinality columns" message — the honest guard, in the same
# named-threshold spirit as CHOROPLETH_MIN_N (a readability/perf floor, not a statistical one).
SCATTER_MAX_CELLS = 10000

# --- Correlation matrix (Phase 13) -----------------------------------------------------
# A Pearson correlation heatmap over a user-picked NUMERIC subset, computed fresh over the
# active slice and NEVER disk-cached (like the crosstab). The subset is bounded: below 2
# columns there is no pair to correlate, and past 8 the k×k grid stops being readable and
# stops teaching (VISUALIZATION_EXPANSION.md §6.5 — "a user-picked subset of 2–8 numeric
# columns", never auto-plot all ~48 numerics).
CORRELATION_MIN_COLS = 2
CORRELATION_MAX_COLS = 8
# The shade reuses Compare's discrete 8-step .heat-N ramp, but scaled to |r| on the ABSOLUTE
# 0→1 scale (not the matrix peak): correlation already has a fixed, interpretable range, so a
# cell's shade means the same thing in every matrix. Sign can't ride a single-hue ramp, so the
# always-rendered signed number carries direction (STYLEGUIDE "Heatmap cells").
CORRELATION_HEAT_STEPS = 8
# The teachable artifact (VISUALIZATION_EXPANSION.md §6.5): an OFF-diagonal pair at or above
# this |r| is flagged "near-mechanical". Minnesota's presumptive sentence is READ OFF the
# guidelines grid (offense severity × criminal-history score), so the grid's own outputs
# (presumptive time, its lower/upper range, grid-cell time) are near-duplicates BY CONSTRUCTION
# — a relationship the grid builds in, not one the data reveals. Empirically these pairs sit at
# |r| ≈ 0.90–1.00 in this dataset, so 0.90 cleanly separates the grid arithmetic from ordinary
# strong-but-real correlations. One documented threshold, in the named-constant spirit of
# analytics.STUCK_ATTEMPTS / CHOROPLETH_MIN_N.
CORRELATION_MECHANICAL_THRESHOLD = 0.90


def _fmt_corr(r):
    # A Pearson r for display: 2 decimals, a real minus sign for negatives (matching the
    # waterfall's "−"). Color carries magnitude only, so this signed number is the sole
    # carrier of direction — the sign must always be visible.
    v = round(r, 2)
    if v == 0:            # collapse -0.0 → 0.00 (no spurious minus on a ~zero correlation)
        return '0.00'
    if v < 0:
        return '−' + '{:.2f}'.format(abs(v))
    return '{:.2f}'.format(v)


def resolve_correlation_columns(cols, data, errors):
    # Validate the user-picked numeric subset for the correlation matrix: keep only documented,
    # non-excluded, numeric (float64) columns, de-duplicated in pick order, and enforce the
    # 2..8 bound. Appends a user-facing message + returns [] when the pick can't drive a matrix.
    seen = []
    for c in cols or []:
        if c in seen:
            continue
        # the checkbox UI only offers documented numeric columns; a stray non-numeric pick can
        # only come from a hand-crafted URL, so drop it silently and let the count checks below
        # produce the actionable message.
        if c not in data['numeric'] or c in data['excluded'] or not CODEBOOK.codebook.get(c):
            continue
        seen.append(c)
    if len(seen) < CORRELATION_MIN_COLS:
        errors.append('Pick at least %d numeric columns to correlate — choose them from the '
                      'list.' % CORRELATION_MIN_COLS)
        return []
    if len(seen) > CORRELATION_MAX_COLS:
        errors.append('Pick at most %d numeric columns — a correlation matrix stays readable up '
                      'to %d. Deselect a few.' % (CORRELATION_MAX_COLS, CORRELATION_MAX_COLS))
        return []
    return seen


def build_correlation(frame, columns):
    # Pearson correlation matrix over a user-picked numeric subset (2..8 columns), computed
    # FRESH over the active slice and NEVER disk-cached — like the crosstab. DataFrame.corr is
    # pairwise-complete (each cell uses the rows where BOTH columns are present); the co-present
    # count rides along per cell for the tooltip so a thin pair reads as such.
    #
    # Shade = |r| on the ABSOLUTE 0→1 scale mapped to the .heat-N ramp (step 0 = unshaded); the
    # signed number carries direction. Off-diagonal cells at |r| ≥ CORRELATION_MECHANICAL_THRESHOLD
    # are flagged as near-mechanical (the guidelines grid showing through) — annotated, not hidden.
    #
    # Read-only over the shared base: selecting columns + .corr()/.notna() return NEW objects and
    # never mutate frame.df (guarded by test_base_immutability.py's representative corr read).
    df = frame.df
    corr = df[columns].corr()                          # pairwise-complete Pearson, k×k
    # pairwise sample size (rows where BOTH columns are non-null), as an integer k×k matrix
    present = df[columns].notna().astype('int64')
    pair_n = present.T.dot(present)

    labels = [CODEBOOK.codebook[c] for c in columns]
    k = len(columns)
    threshold = CORRELATION_MECHANICAL_THRESHOLD

    grid = []
    mechanical_pairs = []
    for i in range(k):
        line = []
        for j in range(k):
            raw = corr.iloc[i, j]
            r = None if (raw is None or raw != raw) else float(raw)   # raw != raw catches NaN
            diag = (i == j)
            n = int(pair_n.iloc[i, j])
            if r is None:
                # a constant column (zero variance) or a pair with < 2 shared cases → r undefined
                cell = {'r': None, 'display': '—', 'heat': 0, 'sign': 'na',
                        'diag': diag, 'mechanical': False, 'n': n}
            else:
                a = abs(r)
                step = min(CORRELATION_HEAT_STEPS, round(CORRELATION_HEAT_STEPS * a))
                # key the sign off the ROUNDED value so a cell that displays "0.00" (a ~zero
                # correlation) never gets the negative underline — display and sign stay in step.
                rounded = round(r, 2)
                sign = 'neg' if rounded < 0 else ('pos' if rounded > 0 else 'zero')
                mechanical = (not diag) and a >= threshold
                cell = {'r': r, 'display': _fmt_corr(r), 'heat': step, 'sign': sign,
                        'diag': diag, 'mechanical': mechanical, 'n': n}
                if mechanical and i < j:                # collect each unordered pair once
                    mechanical_pairs.append({'a': labels[i], 'b': labels[j],
                                             'aCode': columns[i], 'bCode': columns[j],
                                             'display': cell['display'], 'r': r})
            line.append(cell)
        grid.append(line)

    mechanical_pairs.sort(key=lambda p: abs(p['r']), reverse=True)
    return {
        'codes': list(columns),
        'labels': labels,
        'grid': grid,
        'k': k,
        'sliceN': len(df),
        'mechanicalThreshold': threshold,
        'mechanicalDisplay': '{:.2f}'.format(threshold),
        'mechanicalCount': len(mechanical_pairs),
        'mechanicalPairs': mechanical_pairs,
        'anyNegative': any(c['sign'] == 'neg' for line in grid for c in line),
    }


def build_scatter(sheet, x_col, y_col):
    # Reshape data.get_table's nested sheet[x][y] = {'N': count} (d_col=None -> count only) into
    # an aggregated-lattice bubble payload: one point per (x, y) cell with cases, at the numeric
    # coordinates (x, y), sized by N client-side (static/js/visualize.js: bubble area ∝ count).
    # Both axes are numeric (float64), so the sheet keys ARE the plot coordinates; NaN keys (a
    # case missing a value in either column) are dropped. The same point list, largest cell first,
    # doubles as the companion value table (the a11y / no-JS fallback) — no raw rows anywhere.
    points = []
    max_n = 0
    total_n = 0
    for x in sheet:
        if x != x:                               # drop NaN x-key (missing this column)
            continue
        for y in sheet[x]:
            if y != y:                           # drop NaN y-key
                continue
            n = int(sheet[x][y]['N'])
            if n <= 0:
                continue
            points.append({'x': float(x), 'y': float(y), 'n': n})
            total_n += n
            if n > max_n:
                max_n = n
    # largest cell first: the chart draws big bubbles under smaller ones (so small cells stay
    # visible), and the companion table leads with the heaviest combinations.
    points.sort(key=lambda p: p['n'], reverse=True)

    payload = {
        'points': points,
        'maxN': max_n,
        'totalN': total_n,
        'cellCount': len(points),
        'xLabel': CODEBOOK.codebook[x_col], 'yLabel': CODEBOOK.codebook[y_col],
        'xCode': x_col, 'yCode': y_col,
    }
    # the point list IS the companion table (same objects); the template formats x/y for display
    return payload, points


def resolve_waterfall_measure(measure, aggregate, data, errors):
    # Resolve a waterfall's (measure, aggregate) into the numeric column aggregate_by_group
    # reads. count -> None (walk the case count per year); mean/median -> a numeric measure
    # column. Appends a message + returns (None, False) when the pair can't drive a waterfall.
    if aggregate == 'count':
        return None, True                       # measure is irrelevant to a plain count
    if aggregate not in WATERFALL_AGGREGATES:
        errors.append('A waterfall walks the change in a count, mean, or median — mode '
                      'isn’t available for it.')
        return None, False
    if measure == '#' or measure not in data['numeric'] \
            or measure in data['excluded'] or not CODEBOOK.codebook.get(measure):
        errors.append('Mean and median need a numeric measure — pick one from the '
                      'Measure list.')
        return None, False
    return measure, True


def _fmt_measure(value, is_count):
    # A year's aggregate value for display: counts as thousands-separated integers,
    # mean/median rounded to 2 places (%g trims a trailing .0).
    if is_count:
        return '{:,}'.format(int(round(value)))
    return '{:g}'.format(round(value, 2))


def _fmt_delta(delta, is_count):
    # A signed change for display (leading +/−; ± for exactly zero). Same rounding as
    # _fmt_measure so the table's Change column reads consistently with its Value column.
    sign = '+' if delta > 0 else ('−' if delta < 0 else '±')
    return sign + _fmt_measure(abs(delta), is_count)


def build_waterfall(series, aggregate, measure_col):
    # Turn a {sentyear: value} aggregate (from Data.aggregate_by_group over the ACTIVE slice)
    # into a year-over-year floating-bar waterfall payload. The first year is an anchor bar
    # (0 -> its value); every later year is a floating bar from the prior year's value to its
    # own, so a bar's top sits at that year's true aggregate (the running total) and the
    # deltas sum to (last - first). Rising/falling/flat drives the token color in
    # static/js/visualize.js. Years and values come from the data — no hardcoded range.
    is_count = (aggregate == 'count')

    # sort by year, dropping missing-year keys (k == k is False for NaN) and any year whose
    # aggregate is undefined (a numeric measure all-NaN within a year after deep filtering).
    points = []
    for year_key in sorted(k for k in series if k == k):
        value = series[year_key]
        if value != value:                      # NaN aggregate — no bar to draw this year
            continue
        points.append((int(year_key), float(value)))

    steps = []
    prev = None
    for year, value in points:
        if prev is None:                        # anchor bar establishes the starting level
            direction, delta = 'base', None
            start, end = 0.0, value
        else:
            delta = value - prev
            start, end = prev, value
            direction = 'up' if delta > 0 else ('down' if delta < 0 else 'flat')
        steps.append({
            'year': str(year),
            'value': value, 'start': start, 'end': end,
            'delta': delta, 'direction': direction,
            'valueDisplay': _fmt_measure(value, is_count),
            'deltaDisplay': '—' if delta is None else _fmt_delta(delta, is_count),
        })
        prev = value

    first = points[0][1] if points else 0.0
    last = points[-1][1] if points else 0.0
    net = last - first
    return {
        'steps': steps,
        'aggregate': aggregate,
        'groupLabel': CODEBOOK.codebook[WATERFALL_GROUP],
        'measureLabel': 'cases' if is_count else CODEBOOK.codebook[measure_col],
        'valueHeader': 'Cases' if is_count
                       else aggregate.capitalize() + ' ' + CODEBOOK.codebook[measure_col],
        'first': first, 'last': last, 'totalDelta': net,
        'firstYear': steps[0]['year'] if steps else '',
        'lastYear': steps[-1]['year'] if steps else '',
        'firstDisplay': steps[0]['valueDisplay'] if steps else '—',
        'lastDisplay': steps[-1]['valueDisplay'] if steps else '—',
        'netDisplay': _fmt_delta(net, is_count) if steps else '—',
        'netDirection': 'up' if net > 0 else ('down' if net < 0 else 'flat'),
    }


def resolve_choropleth_measure(measure, aggregate, data, errors):
    # Resolve a choropleth's (measure, aggregate) into the numeric column aggregate_by_group
    # reads. count -> None (color counties by case count); mean/median/mode -> a numeric
    # measure column. Appends a message + returns (None, False) when the pair can't drive a map.
    if aggregate == 'count':
        return None, True                       # measure is irrelevant to a plain count
    if aggregate not in CHOROPLETH_AGGREGATES:
        errors.append('A map colors counties by count, mean, median, or mode — that '
                      'summary isn’t available.')
        return None, False
    if measure == Data.COUNT_MEASURE or measure not in data['numeric'] \
            or measure in data['excluded'] or not CODEBOOK.codebook.get(measure):
        errors.append('Mean, median, and mode need a numeric measure — pick one from the '
                      'Measure list.')
        return None, False
    return measure, True


def build_choropleth(session, aggregate, measure, measure_col, grain='county'):
    # Color a Minnesota geography by a per-group aggregate over the ACTIVE slice. Phase 8
    # shipped the county grain; Phase 9 adds district + region by switching the GROUP COLUMN
    # (county -> district/region), so each shape's value is the SAME categorical aggregate a
    # Compare crosstab would show for that column — district/region values are aggregated
    # directly from the data, never summed from counties (a mean of county means would be
    # wrong). The district/region GEOMETRY is dissolved client-side from the county TopoJSON
    # via the crosswalk (there is no district/region geometry file), so this ships the
    # county->group `dissolve` map and the full group-label set to drive that merge.
    # Reuses the Phase 1 helper (Data.aggregate_by_group) through _execute — read-only over the
    # shared base, computed FRESH per request and NEVER disk-cached, like the crosstab.
    is_count = (aggregate == 'count')
    group_column = CHOROPLETH_GRAIN_COLUMN[grain]

    # replay history once, then aggregate the SAME filtered frame twice (value + case count) so
    # a mean/median/mode map still carries N per group for the tooltip and the a11y table.
    sheet = _execute(session)
    counts = sheet.aggregate_by_group(group_column, Data.COUNT_MEASURE, 'count')
    raw_values = counts if is_count \
        else sheet.aggregate_by_group(group_column, measure, aggregate)

    # For district/region: build the dissolve map ({county feature name: group key}) and the
    # FULL group-label set from the crosswalk — the client merges county shapes by group key,
    # and every group must render (even ones with no cases in this slice show as "no data").
    # County grain has no dissolve: it uses the native TopoJSON geometry as-is.
    dissolve = None
    group_labels = None
    if grain == 'county':
        unit_total = len(geo.feature_names())
    else:
        dissolve, group_labels = build_geo_dissolve(grain)
        unit_total = len(group_labels)

    # map each aggregated group to its map-feature key + display label. A group absent from the
    # slice simply isn't a key here, so it renders as "no data" — never silently dropped. For
    # county grain the feature key is the reconciled TopoJSON name (geo bridges the spellings);
    # for district/region it's the canonical group key that dissolve/byFeature agree on.
    by_feature = {}
    total_n = 0
    for group_val, value in raw_values.items():
        if value is None or value != value:     # NaN aggregate (all-NaN measure in a group)
            continue
        if grain == 'county':
            fkey = geo.resolve_county(group_val)
            if fkey is None:                    # unreconciled county (coverage asserted) — skip
                continue
            label = display_value(group_val)
        else:
            fkey = _grain_key(group_val, grain)
            label = group_labels.get(fkey) or _grain_label(group_val, grain)
        val = float(value)
        n = int(counts.get(group_val, 0))
        by_feature[fkey] = {
            'value': val, 'n': n,
            'display': _fmt_measure(val, is_count),
            'label': label,
            'lowN': n < CHOROPLETH_MIN_N,       # thin sample → rendered as texture, not a shade
            # the DATASET value a click-to-filter must submit (Phase 11). For counties this
            # is the dataset spelling ("LeSueur"), which differs from the feature key for the
            # alias counties; for district/region it's the canonical group key ("4.0"), the
            # exact string the filter token encodes. Never derive this client-side from the
            # feature name — that's the silent-divergence trap.
            'filterValue': _grain_key(group_val, grain),
        }
        total_n += n

    # Two ramp peaks, so the client's "hatch thin samples" toggle can recolor without a refetch:
    #  • `peak` — over RELIABLE groups only (n ≥ CHOROPLETH_MIN_N): the DEFAULT (hatched) view, so
    #    one 2-case county with a wild mean can't blow out the scale and wash the real signal pale.
    #    NB: this deliberately relaxes the Phase 8 "map & crosstab share a peak" nicety — per-feature
    #    *values* still match Compare exactly; only the shade normalization drops the unreliable tail.
    #  • `peak_full` — over ALL groups with data: the OVERRIDE view (toggle off), where low-N groups
    #    are shaded like everyone else, so the scale must include them.
    # If nothing clears the bar, `peak` stays 0 (the whole map is texture / no-data) — the honest read.
    peak = max((rec['value'] for rec in by_feature.values() if not rec['lowN']), default=0.0)
    peak_full = max((rec['value'] for rec in by_feature.values()), default=0.0)

    # heat step per group: the SAME 0→peak linear ramp the crosstab heatmap uses (build_crosstab):
    # step = max(1, round(8 * value / peak)); 0 = unshaded (value ≤ 0). Each group carries BOTH a
    # reliable-peak step (`heat`; 0 for low-N → the front-end textures them) and a full-peak step
    # (`heatFull`; low-N included) so the toggle just switches which one the fill reads.
    for rec in by_feature.values():
        step = 0
        if not rec['lowN'] and peak > 0 and rec['value'] > 0:
            step = max(1, round(CHOROPLETH_HEAT_STEPS * rec['value'] / peak))
        rec['heat'] = step
        step_full = 0
        if peak_full > 0 and rec['value'] > 0:
            step_full = max(1, round(CHOROPLETH_HEAT_STEPS * rec['value'] / peak_full))
        rec['heatFull'] = step_full

    low_n_count = sum(1 for rec in by_feature.values() if rec['lowN'])

    agg_label = aggregate.capitalize()
    measure_label = 'cases' if is_count else CODEBOOK.codebook[measure_col]
    grain_noun, grain_plural = CHOROPLETH_GRAIN_NOUNS[grain]

    # companion table (a11y / no-JS fallback): every group with data, largest value first.
    # lowN rides along so the table marks thin samples too — the map textures them, so the
    # no-JS/screen-reader path must flag them as well rather than present them as reliable.
    # filterValue feeds each row's "Keep only" form (Phase 11) — the keyboard/no-JS twin of
    # the map click, posting the same fields to the same apply route.
    rows = sorted(
        ({'label': rec['label'], 'value': rec['value'], 'n': rec['n'],
          'display': rec['display'], 'lowN': rec['lowN'],
          'filterValue': rec['filterValue']} for rec in by_feature.values()),
        key=lambda r: (r['value'], r['n']), reverse=True)

    return {
        'grain': grain,
        'grainLabel': grain_noun,           # singular noun ("Judicial District")
        'grainLabelPlural': grain_plural,   # plural noun ("judicial districts")
        # map-click → filter (Phase 11): the dataset column a click filters, and the
        # EXISTING filter-apply route the click posts to (comparison=eq + a shape's
        # filterValue + a local `next` back to this view) — never a bespoke token path.
        'filterColumn': group_column,
        'applyUrl': url_for('explore_filter_column', column=group_column),
        'unitTotal': unit_total,            # total groups in the grain (87 / 10 / 4)
        'unitsWithData': len(by_feature),   # groups with cases in the slice
        'minN': CHOROPLETH_MIN_N,           # small-N texture threshold (Phase 10)
        'lowNCount': low_n_count,           # groups below the threshold (rendered as texture)
        'aggregate': aggregate,
        'measureLabel': measure_label,
        'aggLabel': agg_label,
        'valueHeader': 'Cases' if is_count else agg_label + ' ' + measure_label,
        'byFeature': by_feature,       # {feature key: {value, n, display, label, heat, heatFull, lowN}}
        'dissolve': dissolve,          # {feature name: group key} for district/region; None county
        'groupLabels': group_labels,   # {group key: label} for district/region; None for county
        'peak': peak,
        'peakDisplay': _fmt_measure(peak, is_count) if peak > 0 else '—',
        'peakFull': peak_full,         # peak incl. low-N groups — the toggle-off (shown) ramp end
        'peakFullDisplay': _fmt_measure(peak_full, is_count) if peak_full > 0 else '—',
        'totalN': total_n,
        'topoUrl': url_for('static', filename=geo.TOPOJSON_STATIC),
        'object': geo.TOPOJSON_OBJECT,
        'rows': rows,
    }


def render_visualize(chart=None, form=None, error=None):
    # Shared renderer for the Visualize workbench (same pattern as render_explore /
    # render_compare / render_filter): full page normally, just the view fragment on htmx
    # requests. A chart type flagged 'ready' computes off the active history (Phase 4: pie);
    # the rest still show the "coming soon" placeholder with their selection URL-encoded.
    user = account.retrieve(session['userid'])
    data = get_data(session)

    # reuse Compare's option builders: grouped documented columns + the numeric list
    axis_groups, numeric = build_compare_options(data)
    form = form or {}
    errors = list(error or [])

    column = form.get('column') or None
    column2 = form.get('column2') or None
    header = None
    chart_payload = None    # reusable bucket payload feeding a ready single-column chart (pie)
    share = None            # pie companion value table (share of shown cases)
    treemap_payload = None  # nested top-N + "Other" payload feeding the treemap
    treemap_rows = None     # treemap companion table (every drawn cell)
    waterfall_payload = None  # year-over-year floating-bar payload feeding the waterfall
    choropleth_payload = None  # per-county aggregate payload feeding the choropleth map
    scatter_payload = None  # aggregated-lattice bubble payload feeding the scatter/bubble chart
    scatter_rows = None     # scatter companion table (every drawn lattice cell)
    correlation_payload = None  # Pearson correlation matrix payload (numeric subset)
    selected_cols = form.get('cols') or []  # raw picked numeric columns (echoed to checkboxes)

    if chart and chart.get('status') == 'ready':
        if chart['id'] == 'pie' and column:
            if _viz_column_ok(data, column, errors):
                # share-of-cases only (no measure/aggregate) — the pie is inherently a
                # part-of-whole mark; mean/median/mode have no place on it (STYLEGUIDE).
                header = CODEBOOK.codebook[column]
                info = get_data(session, column, 'occurrence')['column_info']
                chart_payload = bucket_payload(info['each'], PIE_DEFAULT_CUTOFF, PIE_HARD_CAP)
                share = sorted(info['each'], key=lambda e: e['num'], reverse=True)
            else:
                column = None
        elif chart['id'] == 'treemap' and column and column2:
            # two-column nesting = data.get_table (the SAME crosstab Compare draws), sized by
            # the chosen aggregate. Validate both columns + the measure/aggregate coherence,
            # then reshape the sheet into a nested payload. Computed fresh (never disk-cached).
            col_ok = _viz_column_ok(data, column, errors)
            col2_ok = _viz_column_ok(data, column2, errors)
            if column == column2:
                errors.append('Pick two different columns to nest.')
            measure = form.get('measure') or '#'
            aggregate = form.get('aggregate') or 'count'
            measure_col, agg_ok = resolve_treemap_measure(measure, aggregate, data, errors)
            if col_ok and col2_ok and column != column2 and agg_ok:
                header = CODEBOOK.codebook[column]
                sheet = _execute(session).get_table(measure_col, column, column2)
                treemap_payload, treemap_rows = build_treemap(
                    sheet, aggregate, measure_col, column, column2)
            else:
                if not col_ok:
                    column = None
        elif chart['id'] == 'waterfall':
            # year-over-year change in a numeric aggregate across sentyear (the group column
            # is fixed; the user picks measure + aggregate). Computed fresh over the active
            # slice via the Phase 1 helper — read-only, never disk-cached.
            measure = form.get('measure') or '#'
            aggregate = form.get('aggregate') or 'count'
            measure_col, agg_ok = resolve_waterfall_measure(measure, aggregate, data, errors)
            if WATERFALL_GROUP not in data['column_list']:
                errors.append('The sentencing-year column isn’t available in this dataset.')
            elif agg_ok:
                series = _execute(session).aggregate_by_group(
                    WATERFALL_GROUP, measure, aggregate)
                waterfall_payload = build_waterfall(series, aggregate, measure_col)
                if not waterfall_payload['steps']:
                    errors.append('No sentencing-year data matches the current data state — '
                                  'clear a filter and try again.')
                    waterfall_payload = None
        elif chart['id'] == 'choropleth':
            # MN geography shaded by a per-group aggregate over the active slice. The user picks
            # a grain (county | judicial district | region — Phase 9) plus measure + aggregate;
            # count works with no measure, so selecting the map renders immediately. Computed
            # fresh via the Phase 1 helper — read-only, never disk-cached.
            grain = form.get('grain') or 'county'
            if grain not in CHOROPLETH_GRAIN_IDS:      # unknown grain → fall back to county
                grain = 'county'
            measure = form.get('measure') or Data.COUNT_MEASURE
            aggregate = form.get('aggregate') or 'count'
            measure_col, agg_ok = resolve_choropleth_measure(measure, aggregate, data, errors)
            grain_column = CHOROPLETH_GRAIN_COLUMN[grain]
            if grain_column not in data['column_list']:
                errors.append('The map’s geography column isn’t available in this dataset.')
            elif agg_ok:
                choropleth_payload = build_choropleth(
                    session, aggregate, measure, measure_col, grain)
                if not choropleth_payload['byFeature']:
                    errors.append('No data matches the current data state at this map level '
                                  '— clear a filter and try again.')
                    choropleth_payload = None
        elif chart['id'] == 'scatter' and column and column2:
            # two NUMERIC columns aggregated to a lattice: one bubble per (x, y) cell with
            # cases, sized by that cell's count. Reuses data.get_table (the SAME crosstab
            # Compare draws, d_col=None -> count only) so bubble sizes reconcile exactly —
            # never one mark per row. Both axes must be numeric (float64) to have real plot
            # coordinates; a categorical column (e.g. severity, which mixes '1'..'11' with
            # 'A'..'H') has no linear position, so it's rejected with a clear message.
            # Computed fresh, read-only over the shared base, never disk-cached.
            col_ok = _viz_column_ok(data, column, errors)
            col2_ok = _viz_column_ok(data, column2, errors)
            num_ok = True
            if col_ok and column not in data['numeric']:
                errors.append('The horizontal axis must be a numeric column — “%s” isn’t '
                              'numeric. Pick numeric columns for both axes.'
                              % CODEBOOK.codebook[column])
                num_ok = False
            if col2_ok and column2 not in data['numeric']:
                errors.append('The vertical axis must be a numeric column — “%s” isn’t '
                              'numeric. Pick numeric columns for both axes.'
                              % CODEBOOK.codebook[column2])
                num_ok = False
            if column == column2:
                errors.append('Pick two different numeric columns to plot.')
            if col_ok and col2_ok and num_ok and column != column2:
                frame = _execute(session)
                # guard the O(|x_unique| * |y_unique|) get_table build (and an unreadable
                # cloud) against a pathological high-cardinality pair — filter first instead.
                nx, ny = frame.distinct_counts(column, column2)
                if nx * ny > SCATTER_MAX_CELLS:
                    errors.append('Those columns have too many distinct values to plot as a '
                                  'lattice ({:,} × {:,} = {:,} cells). Pick lower-cardinality '
                                  'numeric columns, or apply a filter first to narrow the '
                                  'values.'.format(nx, ny, nx * ny))
                else:
                    header = CODEBOOK.codebook[column]
                    sheet = frame.get_table(None, column, column2)
                    scatter_payload, scatter_rows = build_scatter(sheet, column, column2)
                    if not scatter_payload['points']:
                        # no (x, y) cell carries a case (the slice is empty, or both columns
                        # are all-missing here) — an empty chart would read as broken.
                        errors.append('No cases have a value for both columns in the current '
                                      'data state — clear a filter and try again.')
                        scatter_payload, scatter_rows = None, None
            elif not col_ok:
                column = None
        elif chart['id'] == 'correlation':
            # Pearson correlation matrix over a user-picked numeric subset (2..8 columns).
            # Computed fresh over the active slice via _execute — read-only over the shared
            # base, NEVER disk-cached (like the crosstab). The matrix is server-rendered as a
            # .heat-N table (the a11y / no-JS path IS the table); no canvas.
            columns = resolve_correlation_columns(selected_cols, data, errors)
            if columns:
                correlation_payload = build_correlation(_execute(session), columns)

    context = {
        'user': user, 'data': data, 'error': errors,
        'browser': build_column_browser(data), 'excluded_note': EXCLUDED_NOTE,
        'chart_types': VIZ_CHART_TYPES,
        'choropleth_grains': CHOROPLETH_GRAINS,   # county / district / region grain toggle
        'axis_groups': axis_groups, 'numeric_measures': numeric,
        'aggregate_options': VIZ_AGGREGATE_OPTIONS,
        'form': form,
        'chart': chart,                # the selected chart-type dict, or None
        'column': column,              # validated primary column (for the browser aria-current)
        'column2': column2,            # second (nesting) column, for the treemap
        'header': header,              # display name of the primary column, when charted
        'chart_payload': chart_payload,
        'share': share,                # pie companion table rows, or None
        'treemap_payload': treemap_payload,
        'treemap_rows': treemap_rows,  # treemap companion table rows, or None
        'waterfall_payload': waterfall_payload,  # year-over-year waterfall payload, or None
        'choropleth_payload': choropleth_payload,  # per-county choropleth payload, or None
        'scatter_payload': scatter_payload,  # aggregated-lattice bubble payload, or None
        'scatter_rows': scatter_rows,        # scatter companion table rows, or None
        'correlation_payload': correlation_payload,  # Pearson correlation matrix, or None
        'selected_cols': selected_cols,      # raw picked numeric columns (checkbox state)
        'correlation_min': CORRELATION_MIN_COLS,
        'correlation_max': CORRELATION_MAX_COLS,
    }

    if wants_fragment():
        return render_template('partials/visualize_view.html', fragment=True, **context)
    return render_template('visualize.html', **context)


@app.route("/visualize")
def visualize():
    # One GET route; state lives in the query string (chart + column + measure +
    # aggregate) so it survives a hard refresh and can be authored into a lesson deep
    # link. The builder is a GET form — no-JS submits natively and reloads with the
    # params; with JS, htmx swaps the fragment and pushes the URL. An unknown chart id
    # falls back to the blank canvas rather than 404ing.
    if not is_logged_in():
        return not_logged_in()

    chart_id = request.args.get('chart', '')
    chart = next((c for c in VIZ_CHART_TYPES if c['id'] == chart_id), None)

    form = {
        'chart': chart['id'] if chart else '',
        'column': request.args.get('column', ''),
        'column2': request.args.get('column2', ''),   # second nesting column (treemap)
        'measure': request.args.get('measure', '#'),
        'aggregate': request.args.get('aggregate', 'count'),
        'grain': request.args.get('grain', 'county'),  # choropleth grain (Phase 9)
        # correlation matrix (Phase 13): a repeated ?cols= param → the 2..8 numeric subset.
        # getlist keeps every pick, so the matrix survives a hard refresh and lesson deep links.
        'cols': request.args.getlist('cols'),
    }
    return render_visualize(chart=chart, form=form)


@app.route('/load', methods=['GET', 'POST'])
def load():
    if is_logged_in():
        error = []
        user = account.retrieve(session['userid'])

        if request.method == 'POST':
            if request.form['code'] not in codes:
                error = ['Invalid code']
            else:
                account.history_revert(session['userid'])
                flash('All filters cleared — full dataset restored.')
                # land in the workbench, not "/" (which would re-fire the resume nudge)
                return redirect(url_for('explore'))

        return render_template('load.html', error=error, user=user)
    else:
        return not_logged_in()


@app.route('/revert/<int:n>')
def revert(n):
    if is_logged_in():
        # n is the 1-based history position from the table (loop.index); history_revert
        # truncates to history[:n], so the clicked row's entry and everything before it
        # survive. The <int> converter rejects negatives; an over-large n is a harmless
        # no-op, and n < 1 is skipped so we never trip history_revert's assert.
        if n >= 1:
            account.history_revert(session['userid'], n)
            if n == 1:
                flash('All filters cleared — full dataset restored.')
            else:
                flash('Data state reverted — later filter steps removed.')
        # land in the workbench, not "/" (which would re-fire the resume nudge)
        return redirect(url_for('explore'))
    else:
        return not_logged_in()


# ---------------------------------------------------------------------------
# Shareable data states (educator portal Phase 9, feature 8)
# ---------------------------------------------------------------------------
#
# The one deliberate exception to "never mutate history except via the user's own filter
# actions": opening a share link resets the visiting user's OWN history to the shared chain,
# same as clicking through Clear Data + re-applying each filter by hand. Unlike lesson state
# (which is a read-only sandbox overlay, see build_lesson_data), this really does rewrite
# user['history'] -- that's the point (a projector-led "everyone look at this view" link).
# The chain is untrusted URL input, so every token is re-validated against the live dataset
# shape before anything is written (never trust history_text_to_item's parse alone).

SHARE_MAX_TOKENS = 25
SHARE_MAX_CHAIN_LEN = 4000


def parse_share_token(token, data):
    # Validates one decoded share-chain token against the current dataset shape and returns
    # (code, column, op, value) -- value is a single string for 'f', a list for 'o'. Raises
    # ValueError (a short, user-facing reason) on anything malformed, unknown, or excluded.
    try:
        code, column, op, value = history_text_to_item(token)['action']
    except (ValueError, IndexError):
        raise ValueError('an unrecognized filter token')

    if op not in ('eq', 'ne', 'gt', 'ge', 'lt', 'le'):
        raise ValueError('an unknown comparison')
    if column not in data['column_list'] or not CODEBOOK.codebook.get(column):
        raise ValueError('a column that no longer exists')
    if column in data['excluded']:
        raise ValueError('a column excluded from filtering')

    values = value if code == 'o' else [value]
    if not values or any(v == '' for v in values):
        raise ValueError('a missing value')
    if op in ('gt', 'ge', 'lt', 'le') or column in data['numeric']:
        if numeric_value_error(values):
            raise ValueError('a non-numeric value on a numeric comparison')

    return code, column, op, value


@app.route('/share/<chain>')
def apply_share(chain):
    if not is_logged_in():
        return not_logged_in()

    raw_tokens = [t for t in chain.split(',') if t]
    if not raw_tokens or len(raw_tokens) > SHARE_MAX_TOKENS or len(chain) > SHARE_MAX_CHAIN_LEN:
        flash('That share link is invalid or too long.', 'danger')
        return redirect(url_for('explore'))

    # dataset shape (column_list/excluded/numeric) doesn't depend on filter state, so this
    # is safe to read before resetting history
    data = get_data(session)

    entries = []
    for encoded in raw_tokens:
        token = urllib.parse.unquote(encoded)
        try:
            code, column, op, value = parse_share_token(token, data)
        except ValueError as reason:
            flash('That share link contains ' + str(reason) + ' and could not be applied.', 'danger')
            return redirect(url_for('explore'))
        # rebuild through make_history (not by hand) so the resulting entry — desc included —
        # is identical to what a manual filter apply would have produced
        if code == 'f':
            entries.append(make_history.filter_single(column, op, value))
        else:
            entries.append(make_history.filter_or_same(column, op, value))

    # reset to the base entry, then replay the shared chain in order -- reproduces the
    # sharer's exact view (and lands in the same cache directory a manual replay would)
    account.history_revert(session['userid'], 1)
    for entry in entries:
        account.history_add(session['userid'], entry)

    remaining = get_data(session)['entries']
    flash('Shared data state applied — {:,} cases shown.'.format(remaining), 'success')
    return redirect(url_for('explore'))


@app.route('/save', methods=['GET', 'POST'])
def save():
    if is_logged_in():
        return not_implemented()
    else:
        return not_logged_in()


@app.route('/other')
def other():
    if is_logged_in():
        return not_implemented()
    else:
        return not_logged_in()


@app.route('/settings')
def settings():
    if is_logged_in():
        return not_implemented()
    else:
        return not_logged_in()


# a helpful starting point for the steps textarea when authoring a new module
DEFAULT_STEPS_JSON = json.dumps([
    {"type": "read", "title": "Introduction", "body": "Write your lesson introduction here."}
], indent=2)


def require_educator():
    # authoring guard: returns a redirect response if the user may not author, else None.
    # logged-out -> login; logged-in non-educator -> home.
    if not is_logged_in():
        return not_logged_in()
    if not account.is_educator(session['userid']):
        return redirect(url_for('index'))
    return None


def require_class_owner(class_id):
    # per-class portal guard: educator AND owns this class, else a redirect response (else
    # None). Layered on require_educator() so a non-educator gets the same bounce as /admin.
    blocked = require_educator()
    if blocked:
        return blocked
    try:
        class_obj = classroom.get_class(class_id)
    except classroom.ClassError:
        flash("That class doesn't exist.", 'danger')
        return redirect(url_for('admin_classes'))
    if class_obj['owner'] != session['userid']:
        flash("That class belongs to another educator.", 'danger')
        return redirect(url_for('admin_classes'))
    return None


def slugify(text):
    # sanitize a raw id into a filename-/URL-safe slug ([a-z0-9-]); prevents path traversal
    return re.sub(r'[^a-z0-9-]+', '-', text.strip().lower()).strip('-')


def student_display_name(userid):
    # roster entries are full userids ("<namespace>/<username>") -- strip the namespace for
    # display (classes hold no PII beyond userids; see classroom.py). Used by the class detail
    # roster table and by the roster-management flashes below.
    return userid.split('/', 1)[1] if '/' in userid else userid


def parse_email_policy(form):
    # shared "email policy" fieldset parsing (new-class form + class-detail form): a checkbox
    # plus a comma/whitespace-separated domain list.
    domains = [d.strip() for d in re.split(r'[,\s]+', form.get('email_domains', '')) if d.strip()]
    return {'required': form.get('email_required') == 'on', 'domains': domains}


def parse_retake_policy(form):
    # "Retake & feedback policy" fieldset parsing (feature 11): blank attempts field means
    # unlimited (stored as None, classroom.py's existing default).
    raw = form.get('attempts', '').strip()
    if raw == '':
        attempts = None
    else:
        try:
            attempts = int(raw)
        except ValueError:
            raise classroom.ClassError("Attempts allowed must be a whole number, or blank for unlimited.")
        if attempts < 1:
            raise classroom.ClassError("Attempts allowed must be at least 1.")

    return {
        'attempts': attempts,
        'reveal_after_miss': form.get('reveal_after_miss') == 'on',
        'show_tolerance': form.get('show_tolerance') == 'on',
    }


@app.route('/admin')
def admin():
    blocked = require_educator()
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    classcode = user['classcode']

    # archived sections drop off active lists (Phase 8, feature 7) -- still reachable from
    # /admin/classes's "Archived classes" panel, just not surfaced on the portal home
    classes = [c for c in classroom.list_classes(session['userid']) if not c.get('archived')]
    # educators manage the modules scoped to their own classcode
    mine = [m for m in lessons.list_modules() if m.get('author') == classcode]

    return render_template('admin.html', user=user, classes=classes, modules=mine, classcode=classcode)


@app.route('/admin/classes', methods=['GET', 'POST'])
def admin_classes():
    blocked = require_educator()
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    error = []
    form = {'name': '', 'email_required': False, 'email_domains': ''}

    if request.method == 'POST':
        form = {'name': request.form.get('name', ''),
                'email_required': request.form.get('email_required') == 'on',
                'email_domains': request.form.get('email_domains', '')}

        try:
            class_obj = classroom.create_class(session['userid'], form['name'],
                                               parse_email_policy(request.form))
            flash('Class created — share the join code with students.', 'success')
            return redirect(url_for('admin_class', class_id=class_obj['class_id']))
        except classroom.ClassError as e:
            error.append(str(e))

    all_classes = classroom.list_classes(session['userid'])
    classes = [c for c in all_classes if not c.get('archived')]
    archived = [c for c in all_classes if c.get('archived')]
    return render_template('admin_classes.html', user=user, classes=classes, archived=archived,
                           form=form, error=error)


@app.route('/admin/classes/compare')
def admin_classes_compare():
    # Multiple-sections-per-educator comparison view (Phase 8, feature 7): completion rate and
    # median score per lesson, one column per active class. Reuses build_class_dashboard (the
    # per-student progress dashboard's own aggregator) so the numbers can never drift from what
    # a class's own progress page shows; archived sections are left out, matching admin/admin_classes.
    blocked = require_educator()
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    classes = [c for c in classroom.list_classes(session['userid']) if not c.get('archived')]
    modules = [{'id': m['id'], 'title': m['title']} for m in lessons.list_modules()]

    sections = []
    for class_obj in classes:
        dashboard = build_class_dashboard(class_obj)
        sections.append({
            'class_obj': class_obj,
            'roster_size': dashboard['roster_size'],
            'rollup_by_id': {r['id']: r for r in dashboard['rollups']},
        })

    return render_template('admin_classes_compare.html', user=user, modules=modules, sections=sections)


@app.route('/admin/classes/<class_id>', methods=['GET', 'POST'])
def admin_class(class_id):
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])

    if request.method == 'POST':
        classroom.set_email_policy(class_id, parse_email_policy(request.form))
        flash('Email policy updated.', 'success')
        return redirect(url_for('admin_class', class_id=class_id))

    class_obj = classroom.get_class(class_id)
    policy = class_obj.get('email_policy', {'required': False, 'domains': []})
    retake_policy = class_obj.get('policy', {'attempts': None, 'reveal_after_miss': False, 'show_tolerance': False})
    # roster entries are userids ("<class_id>/<username>", or a joined-in-place student's
    # original "<classcode>/<username>") — split for display, no account reads needed
    # (classes hold no PII beyond userids; see classroom.py)
    roster = [{'userid': u, 'username': student_display_name(u)} for u in class_obj['roster']]

    return render_template('admin_class.html', user=user, class_obj=class_obj,
                           roster=roster, policy=policy, retake_policy=retake_policy)


@app.route('/admin/classes/<class_id>/policy', methods=['POST'])
def admin_class_policy(class_id):
    # Retake & feedback policy (feature 11): its own route/form, separate from admin_class's
    # email-policy POST, since the two fieldsets live on the same page but save independently.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    try:
        classroom.set_policy(class_id, parse_retake_policy(request.form))
        flash('Retake & feedback policy updated.', 'success')
    except classroom.ClassError as e:
        flash(str(e), 'danger')

    return redirect(url_for('admin_class', class_id=class_id))


# ---------------------------------------------------------------------------
# Roster management (educator portal Phase 8, feature 7)
# ---------------------------------------------------------------------------
#
# Every action below is reached only through require_class_owner, and every route re-checks
# that the target userid is actually on THIS class's roster before touching anything -- an
# educator can only ever act on their own students, never on an arbitrary userid guessed off
# another class. All are GET links (matching the existing revert/clear-data convention, and
# guarded client-side by the same [data-confirm] dialog) except full account deletion, which
# gets its own GET+POST confirmation page instead of just the one-click dialog (see
# admin_class_delete_student).

def _roster_or_none(class_obj, userid):
    # Shared guard for every roster action: bounces with a flash if userid isn't on this
    # class's roster, else returns the class_obj unchanged (so callers can chain it in an if).
    if userid not in class_obj.get('roster', []):
        flash("That student isn't on this class's roster.", 'danger')
        return None
    return class_obj


@app.route('/admin/classes/<class_id>/roster/<path:userid>/remove')
def admin_class_remove_student(class_id, userid):
    # Unenroll a student: drops the roster entry and the class from their own 'classes' list,
    # but keeps their account, history, and progress intact -- they can rejoin with the join
    # code later. Distinct from admin_class_delete_student, which destroys the account.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.get_class(class_id)
    if _roster_or_none(class_obj, userid):
        classroom.remove_student(class_id, userid)
        try:
            account.remove_class(userid, class_id)
        except FileNotFoundError:
            pass  # roster entry with no account (shouldn't happen) -- roster is fixed either way
        flash('Removed ' + student_display_name(userid) + ' from ' + class_obj['name'] + '.', 'success')

    return redirect(url_for('admin_class', class_id=class_id))


@app.route('/admin/classes/<class_id>/roster/<path:userid>/reset')
def admin_class_reset_progress(class_id, userid):
    # Clears the student's lesson progress across every module the class dashboard tracks
    # (account.reset_progress documents the scope) so they get a clean restart. The attempt
    # log is deliberately left alone -- it backs the item-level analytics/thesis data.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.get_class(class_id)
    if _roster_or_none(class_obj, userid):
        module_ids = [m['id'] for m in lessons.list_modules()]
        try:
            account.reset_progress(userid, module_ids)
            flash("Reset " + student_display_name(userid) + "'s lesson progress.", 'success')
        except FileNotFoundError:
            flash("That student's account could not be found.", 'danger')

    return redirect(url_for('admin_class', class_id=class_id))


@app.route('/admin/classes/<class_id>/rotate-code')
def admin_class_rotate_code(class_id):
    # New join code; class_id (the storage key) and the roster are untouched, so no
    # already-enrolled student is displaced -- only the old code stops working.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.rotate_join_code(class_id)
    flash('New join code: ' + class_obj['join_code'] + '. The old code no longer works.', 'success')
    return redirect(url_for('admin_class', class_id=class_id))


@app.route('/admin/classes/<class_id>/archive')
def admin_class_archive(class_id):
    # Archiving drops a section off the active /admin and /admin/classes lists (feature 7) --
    # the roster and every record stay intact, and it can be restored any time.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.archive(class_id)
    flash(class_obj['name'] + ' archived. Restore it any time from Archived classes.', 'success')
    return redirect(url_for('admin_class', class_id=class_id))


@app.route('/admin/classes/<class_id>/unarchive')
def admin_class_unarchive(class_id):
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.unarchive(class_id)
    flash(class_obj['name'] + ' restored to your active classes.', 'success')
    return redirect(url_for('admin_class', class_id=class_id))


@app.route('/admin/classes/<class_id>/roster/<path:userid>/delete', methods=['GET', 'POST'])
def admin_class_delete_student(class_id, userid):
    # Educator-initiated full deletion (EDUCATOR_PORTAL.md Privacy section) -- permanently
    # destroys the account pickle and the attempt log, not just the roster membership. This
    # is meaningfully more destructive than "Remove", so it is guarded harder: a dedicated,
    # visually distinct confirmation page (not just the one-click dialog) that requires typing
    # the student's exact username before the POST is honored.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.get_class(class_id)
    if _roster_or_none(class_obj, userid) is None:
        return redirect(url_for('admin_class', class_id=class_id))

    username = student_display_name(userid)
    # named 'errors' (list), not 'error' -- layout.html's top-of-main alert renders any
    # truthy 'error' in context by iterating it, so a plain string there gets shredded into
    # one <p> per character (same gotcha new.html/login.html already dodge this way)
    errors = None

    if request.method == 'POST':
        if request.form.get('confirm_username', '') != username:
            errors = ['Type the username exactly as shown below to confirm.']
        else:
            classroom.remove_student(class_id, userid)
            analytics.delete_attempts(userid)
            account.delete_account(userid)
            flash('Permanently deleted ' + username + "'s account, progress, and attempt history.", 'success')
            return redirect(url_for('admin_class', class_id=class_id))

    return render_template('admin_student_delete.html', user=account.retrieve(session['userid']),
                           class_obj=class_obj, username=username, errors=errors)


# ISO date (YYYY-MM-DD) — same lexical form <input type="date"> emits, so string
# comparison against date.today().isoformat() sorts correctly without parsing.
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


@app.route('/admin/classes/<class_id>/assignments', methods=['GET', 'POST'])
def admin_class_assignments(class_id):
    # Per-module assignment control (educator portal Phase 6, feature 4): required /
    # optional / hidden / scheduled, the last with an open and/or due date.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    class_obj = classroom.get_class(class_id)
    modules = lessons.list_modules()
    current = class_obj.get('assignments', {})
    error = []

    if request.method == 'POST':
        assignments = {}

        for m in modules:
            mid = m['id']
            state = request.form.get('state_' + mid, 'optional')
            if state not in classroom.VALID_ASSIGNMENT_STATES:
                state = 'optional'

            open_date = request.form.get('open_' + mid, '').strip()
            due_date = request.form.get('due_' + mid, '').strip()
            if open_date and not _ISO_DATE.match(open_date):
                error.append(m['title'] + ': open date must be YYYY-MM-DD.')
                open_date = ''
            if due_date and not _ISO_DATE.match(due_date):
                error.append(m['title'] + ': due date must be YYYY-MM-DD.')
                due_date = ''

            if state == 'scheduled' and not open_date and not due_date:
                error.append(m['title'] + ': Scheduled needs an open and/or due date.')

            # dates only mean anything for a scheduled module — drop stray values left
            # over from switching a module's state away from Scheduled
            if state != 'scheduled':
                open_date = due_date = ''

            assignments[mid] = {'state': state, 'open': open_date or None, 'due': due_date or None}

        if not error:
            classroom.set_assignments(class_id, assignments)
            flash('Assignments updated.', 'success')
            return redirect(url_for('admin_class_assignments', class_id=class_id))

        current = assignments  # re-render with what they just typed, not the stored state

    rows = [{'module': m,
             'assignment': current.get(m['id'], {'state': 'optional', 'open': None, 'due': None})}
            for m in modules]

    return render_template('admin_class_assignments.html', user=user, class_obj=class_obj,
                           rows=rows, error=error)


# ---------------------------------------------------------------------------
# Progress dashboard + "needs attention" triage (educator portal, Phase 5, features 1 & 2)
# ---------------------------------------------------------------------------

# Triage heuristic (paired with analytics.STUCK_ATTEMPTS for repeated misses): a student with
# no graded activity for this many days while a module is still in progress is surfaced in the
# "needs attention" list. Kept here because judging inactivity needs wall-clock "now".
INACTIVE_DAYS = 7

# per-student table sort keys that aren't a specific module column
_BASE_SORT_KEYS = {'student', 'started', 'completed', 'last_active'}


def _parse_ts(ts):
    # attempt-log timestamps are ISO-8601 with a 'Z' suffix (analytics.now_iso). Parse to an
    # aware datetime; return None on anything malformed so one torn log line never breaks the page.
    if not isinstance(ts, str):
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None


def graded_step_indices(module):
    # step indices of the auto-graded questions (numeric/choice); 'free' answers carry no
    # correct/incorrect, so they never count toward a score.
    return [i for i, step in enumerate(module['steps'])
            if step.get('type') == 'question'
            and step.get('answer', {}).get('type') in ('numeric', 'choice')]


def _student_module_cell(graded, prog):
    # One student's standing in one module, read from STORED progress (never re-graded): the
    # status plus an accuracy score over the graded questions they have ANSWERED so far.
    answers = prog.get('answers', {})
    answered = [i for i in graded if str(i) in answers]
    correct = sum(1 for i in answered if answers[str(i)].get('correct'))
    return {
        'status': module_status(prog),
        'answered': len(answered),
        'correct': correct,
        'total': len(graded),
        # accuracy over answered questions; None until they've answered one (so a just-started
        # student doesn't show a misleading 0%)
        'score': (correct / len(answered)) if answered else None,
    }


def _sort_rows(rows, sort, direction):
    # Server-side sort for the per-student table (URL-backed, so it works with JS off). Rows
    # missing the sort value (no activity yet, or a module not started) always sink to the
    # bottom regardless of direction, so "sort by last active" never buries active students
    # under students who have no timestamp at all.
    reverse = (direction == 'desc')

    if sort == 'student':
        return sorted(rows, key=lambda r: r['username'].lower(), reverse=reverse)
    if sort in ('started', 'completed'):
        return sorted(rows, key=lambda r: r[sort], reverse=reverse)

    if sort == 'last_active':
        def is_missing(r):
            return r['last_active'] is None

        def value(r):
            return r['last_active']
    else:  # 'mod:<module id>' — sort by that module's score
        mid = sort.split(':', 1)[1]

        def is_missing(r):
            return r['cells'].get(mid, {}).get('score') is None

        def value(r):
            return r['cells'][mid]['score']

    present = sorted((r for r in rows if not is_missing(r)), key=value, reverse=reverse)
    return present + [r for r in rows if is_missing(r)]


def build_class_dashboard(class_obj, sort='last_active', direction='desc'):
    # Cross-account aggregation for the class progress dashboard. Reads each rostered student's
    # stored progress (one pickle) and attempt log (one JSONL) ONCE, never re-grades a cell, and
    # never touches a student outside this class's roster (privacy). Returns everything the
    # template renders: the triage list, the per-student rows, and the per-module rollups.
    modules = lessons.list_modules()
    graded = {m['id']: graded_step_indices(m) for m in modules}
    now = datetime.datetime.now(datetime.timezone.utc)

    rows = []
    attention = []
    # per-module accumulators for the rollup
    started_count = {m['id']: 0 for m in modules}
    completed_count = {m['id']: 0 for m in modules}
    scores = {m['id']: [] for m in modules}   # accuracy scores of students who've answered ≥1
    items = {m['id']: {} for m in modules}    # step(str) -> {'attempts','correct'} across roster

    for userid in class_obj.get('roster', []):
        try:
            student = account.retrieve(userid)
        except FileNotFoundError:
            continue  # roster entry with no account (shouldn't happen) — skip defensively

        username = student.get('username') or userid.split('/', 1)[-1]
        progress = student.get('progress', {})
        attempts = analytics.read_attempts(userid)

        cells = {}
        started = completed = 0
        for m in modules:
            mid = m['id']
            prog = progress.get(mid, {})
            cell = _student_module_cell(graded[mid], prog)
            cells[mid] = cell

            if cell['status'] != 'not_started':
                started += 1
                started_count[mid] += 1
            if cell['status'] == 'completed':
                completed += 1
                completed_count[mid] += 1
            if cell['score'] is not None:
                scores[mid].append(cell['score'])

            # fold this student's item-level attempts into the class totals (attempt-level, so
            # repeats count — that's the item-difficulty signal, distinct from the score above)
            for step, counts in analytics.item_stats(attempts, mid).items():
                agg = items[mid].setdefault(step, {'attempts': 0, 'correct': 0})
                agg['attempts'] += counts['attempts']
                agg['correct'] += counts['correct']

        last_ts = analytics.last_active_ts(attempts)
        last_dt = _parse_ts(last_ts)
        last_days = (now - last_dt).days if last_dt else None

        # ---- triage reasons for this student ----
        reasons = []
        for m in modules:
            for sq in analytics.stuck_questions(attempts, m['id']):
                step = sq['step']
                title = m['steps'][step]['title'] if step < len(m['steps']) else 'a question'
                reasons.append({'kind': 'stuck', 'module': m['title'],
                                'question': title, 'misses': sq['misses']})
        # inactivity: quiet too long while something is still in progress
        in_progress = [m['title'] for m in modules if cells[m['id']]['status'] == 'in_progress']
        if last_days is not None and last_days >= INACTIVE_DAYS and in_progress:
            reasons.append({'kind': 'inactive', 'days': last_days, 'modules': in_progress})

        if reasons:
            attention.append({'username': username, 'reasons': reasons})

        rows.append({
            'userid': userid, 'username': username,
            'started': started, 'completed': completed,
            'last_active': last_ts, 'last_days': last_days,
            'flagged': bool(reasons),
            'cells': cells,
        })

    roster_size = len(rows)

    # triage first (principle 1): stuck students ahead of merely-inactive ones, then most reasons
    attention.sort(key=lambda a: (
        -sum(1 for r in a['reasons'] if r['kind'] == 'stuck'),
        -len(a['reasons']), a['username'].lower()))

    # per-module rollup: completion rate, median score, and item-level miss rates
    rollups = []
    for m in modules:
        mid = m['id']
        item_rows = []
        for i in graded[mid]:
            counts = items[mid].get(str(i), {'attempts': 0, 'correct': 0})
            attempts_n = counts['attempts']
            item_rows.append({
                'step': i,
                'question': m['steps'][i]['title'],
                'attempts': attempts_n,
                'correct': counts['correct'],
                'miss_rate': ((attempts_n - counts['correct']) / attempts_n) if attempts_n else None,
            })
        rollups.append({
            'id': mid, 'title': m['title'],
            'started': started_count[mid], 'completed': completed_count[mid],
            'completion_rate': (completed_count[mid] / roster_size) if roster_size else None,
            'median_score': statistics.median(scores[mid]) if scores[mid] else None,
            'graded': len(graded[mid]),
            'items': item_rows,
        })

    rows = _sort_rows(rows, sort, direction)

    return {
        'modules': [{'id': m['id'], 'title': m['title']} for m in modules],
        'rows': rows, 'attention': attention, 'rollups': rollups,
        'roster_size': roster_size, 'sort': sort, 'direction': direction,
    }


@app.route('/admin/classes/<class_id>/progress')
def admin_class_progress(class_id):
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    class_obj = classroom.get_class(class_id)

    # validate the sort controls (untrusted query args): a base key, or 'mod:<known module id>'
    sort = request.args.get('sort', 'last_active')
    module_ids = {m['id'] for m in lessons.list_modules()}
    if sort not in _BASE_SORT_KEYS and not (
            sort.startswith('mod:') and sort.split(':', 1)[1] in module_ids):
        sort = 'last_active'
    direction = request.args.get('dir', 'desc')
    if direction not in ('asc', 'desc'):
        direction = 'desc'

    dashboard = build_class_dashboard(class_obj, sort, direction)
    return render_template('admin_class_progress.html', user=user,
                           class_obj=class_obj, dashboard=dashboard)


# ---------------------------------------------------------------------------
# Answer-context inspection (educator portal Phase 10, feature 9)
# ---------------------------------------------------------------------------

def build_student_attempts(userid):
    # One student's full attempt history, newest first. Module/question titles and choice
    # labels are resolved from the LIVE module (a module can be edited after the attempt was
    # logged), but the 'state' tokens are exactly what was recorded at answer time -- decoded to
    # plain language via describe_token so a teacher can tell "filtered the wrong year" from
    # "can't read a median" on an incorrect answer.
    modules = {}
    rows = []

    for record in reversed(analytics.read_attempts(userid)):
        mid = record.get('module')
        if mid not in modules:
            try:
                modules[mid] = lessons.get_module(mid)
            except lessons.LessonError:
                modules[mid] = None
        module = modules[mid]

        step_i = record.get('step')
        step = None
        if module and isinstance(step_i, int) and 0 <= step_i < len(module['steps']):
            step = module['steps'][step_i]

        # a deleted/edited-away choice option just falls back to the raw stored index
        submitted = record.get('submitted')
        if step and record.get('type') == 'choice':
            options = step.get('answer', {}).get('options', [])
            if isinstance(submitted, int) and 0 <= submitted < len(options):
                submitted = options[submitted]

        rows.append({
            'ts': record.get('ts'),
            'module_title': module['title'] if module else (mid or 'Unknown module'),
            'question_title': step['title'] if step else ('Step ' + str(step_i)),
            'type': record.get('type'),
            'submitted': submitted,
            'correct': record.get('correct'),
            'chips': lesson_chips(record.get('state', [])),
        })

    return rows


@app.route('/admin/classes/<class_id>/roster/<path:userid>/attempts')
def admin_student_attempts(class_id, userid):
    # From the progress dashboard, drill into one student's graded history to see the data
    # state active when each answer was submitted (feature 9). Same roster guard as every other
    # per-student action -- an educator can only ever inspect their own class's students.
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.get_class(class_id)
    if _roster_or_none(class_obj, userid) is None:
        return redirect(url_for('admin_class_progress', class_id=class_id))

    try:
        account.retrieve(userid)
    except FileNotFoundError:
        flash("That student's account could not be found.", 'danger')
        return redirect(url_for('admin_class_progress', class_id=class_id))

    user = account.retrieve(session['userid'])
    return render_template('admin_student_attempts.html', user=user, class_obj=class_obj,
                           username=student_display_name(userid),
                           attempts=build_student_attempts(userid))


def class_gradebook_csv(class_obj):
    # Flat gradebook export (feature 6): one row per student, two columns per module
    # (completion + score), plus one last-active timestamp column. Deliberately flat --
    # no title/preamble rows like crosstab_csv's -- so it imports cleanly into Canvas /
    # Google Classroom / PowerSchool. Built from build_class_dashboard so the numbers
    # always match the progress dashboard.
    #
    # "Complete" (EDUCATOR_PORTAL.md open question 4) defaults to the module's own
    # `completed` flag -- the same definition module_status/the dashboard already use,
    # not a separate per-class setting.
    dashboard = build_class_dashboard(class_obj)

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    header = ['Username']
    for m in dashboard['modules']:
        header += [m['title'] + ' - Completed', m['title'] + ' - Score (%)']
    header.append('Last Active (UTC)')
    writer.writerow(header)

    for row in dashboard['rows']:
        line = [row['username']]
        for m in dashboard['modules']:
            cell = row['cells'][m['id']]
            line.append('Yes' if cell['status'] == 'completed' else 'No')
            line.append('' if cell['score'] is None else round(cell['score'] * 100))
        line.append(row['last_active'] or '')
        writer.writerow(line)

    filename = 'gradebook-' + class_obj['class_id'] + '.csv'
    # BOM so Excel reads the file as UTF-8 (matches crosstab_csv)
    response = Response('﻿' + buffer.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename="' + filename + '"'
    return response


@app.route('/admin/classes/<class_id>/gradebook.csv')
def admin_class_gradebook(class_id):
    blocked = require_class_owner(class_id)
    if blocked:
        return blocked

    class_obj = classroom.get_class(class_id)
    return class_gradebook_csv(class_obj)


# ---------------------------------------------------------------------------
# Computed answer key (educator portal Phase 10, feature 10)
# ---------------------------------------------------------------------------

@app.route('/admin/modules/<module_id>/answers')
def admin_module_answers(module_id):
    # Any educator can view any module's key -- it carries no student data, so it isn't scoped
    # to modules this educator authored (classes routinely run the shared starter lessons
    # authored under 'unmanaged'). Generated fresh every request, never persisted, so it always
    # matches the live dataset.
    blocked = require_educator()
    if blocked:
        return blocked

    try:
        module = lessons.get_module(module_id)
    except lessons.LessonError:
        flash("That module doesn't exist.", 'danger')
        return redirect(url_for('admin'))

    user = account.retrieve(session['userid'])
    return render_template('admin_module_answers.html', user=user, module=module,
                           answer_key=build_answer_key(module))


@app.route('/admin/edit', methods=['GET', 'POST'])
@app.route('/admin/edit/<module_id>', methods=['GET', 'POST'])
def admin_edit(module_id=None):
    blocked = require_educator()
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    classcode = user['classcode']
    error = []

    if request.method == 'POST':
        new_id = slugify(request.form.get('module_id', ''))
        form = {
            'module_id': new_id,
            'title': request.form.get('title', '').strip(),
            'description': request.form.get('description', '').strip(),
            'objectives': request.form.get('objectives', ''),
            'steps': request.form.get('steps', '')
        }

        if not new_id:
            error.append('Module id must contain at least one letter or number.')

        # never let one class overwrite another class's module
        try:
            prior = lessons.get_module(new_id)
            if prior.get('author') != classcode:
                error.append("A module named '" + new_id + "' already exists in another class.")
        except lessons.LessonError:
            pass

        steps = None
        try:
            steps = json.loads(form['steps'] or '[]')
        except ValueError as e:
            error.append('Steps must be valid JSON: ' + str(e))

        if not error:
            module = {
                'id': new_id,
                'title': form['title'],
                'description': form['description'],
                'author': classcode,  # scoped to the educator; cannot be spoofed from the form
                'objectives': [ln.strip() for ln in form['objectives'].splitlines() if ln.strip()],
                'steps': steps
            }
            try:
                lessons.save_module(module)
                return redirect(url_for('lesson_overview', module_id=new_id))
            except lessons.LessonError as e:
                error.append(str(e))

        return render_template('admin_edit.html', user=user, form=form, error=error, editing=bool(module_id))

    # GET: blank template for new, or prefill from an existing (owned) module
    form = {'module_id': '', 'title': '', 'description': '', 'objectives': '', 'steps': DEFAULT_STEPS_JSON}

    if module_id:
        try:
            existing = lessons.get_module(module_id)
        except lessons.LessonError:
            return redirect(url_for('admin'))
        if existing.get('author') != classcode:
            return redirect(url_for('admin'))
        form = {
            'module_id': existing['id'],
            'title': existing['title'],
            'description': existing['description'],
            'objectives': '\n'.join(existing['objectives']),
            'steps': json.dumps(existing['steps'], indent=2)
        }

    return render_template('admin_edit.html', user=user, form=form, error=error, editing=bool(module_id))


def module_status(entry):
    # derive a module's status from its stored progress entry (no data replay)
    if not entry:
        return 'not_started'
    if entry.get('completed'):
        return 'completed'
    return 'in_progress'


def resume_step(entry, total):
    # where "Resume" jumps to: last-viewed step, clamped; completed modules restart at 0
    if not entry or entry.get('completed'):
        return 0
    step = entry.get('step', 0)
    return max(0, min(step, total - 1))


@app.route('/lesson')
def lesson_catalog():
    if is_logged_in():
        user = account.retrieve(session['userid'])

        progress = user.get('progress', {})
        today = datetime.date.today().isoformat()
        catalog = []
        for m in visible_modules(user):
            assignment = resolve_assignment(user, m['id'])
            entry = progress.get(m['id'])
            total = len(m['steps'])
            # scheduled modules stay in the catalog but are locked until their open date
            locked = bool(assignment and assignment['state'] == 'scheduled'
                          and assignment.get('open') and assignment['open'] > today)
            catalog.append({
                'module': m,
                'status': module_status(entry),
                'resume': resume_step(entry, total),
                'total_steps': total,
                'assignment': assignment,
                'locked': locked,
            })

        return render_template('lesson_catalog.html', catalog=catalog, user=user)

    else:
        return not_logged_in()


@app.route('/lesson/<module_id>')
def lesson_overview(module_id):
    if is_logged_in():
        user = account.retrieve(session['userid'])

        # a bad/unknown module id just bounces back to the catalog
        try:
            module = lessons.get_module(module_id)
        except lessons.LessonError:
            return redirect(url_for('lesson_catalog'))

        entry = user.get('progress', {}).get(module_id)

        return render_template('lesson.html', module=module, user=user,
                               status=module_status(entry),
                               resume=resume_step(entry, len(module['steps'])))

    else:
        return not_logged_in()


@app.route('/lesson/<module_id>/<int:step>', methods=['GET', 'POST'])
def lesson_step(module_id, step):
    if not is_logged_in():
        return not_logged_in()

    user = account.retrieve(session['userid'])

    try:
        module = lessons.get_module(module_id)
    except lessons.LessonError:
        return redirect(url_for('lesson_catalog'))

    steps = module['steps']

    # out-of-range step falls back to the module overview
    if step < 0 or step >= len(steps):
        return redirect(url_for('lesson_overview', module_id=module_id))

    current = steps[step]
    policy = resolve_policy(user)

    # POST an answer -> grade it server-side, persist, then redirect back (Post/Redirect/Get).
    # A locked question (attempt cap already reached) never grades another try, even if the
    # client bypasses the disabled form -- the policy is enforced here, not just in the UI.
    if request.method == 'POST' and current['type'] == 'question':
        if not question_locked(session['userid'], module_id, step, current, policy):
            grade_and_store(module_id, step, current)
        return redirect(url_for('lesson_step', module_id=module_id, step=step))

    # record the resume pointer, but only when it actually moves (avoid redundant writes)
    if account.get_progress(session['userid'], module_id).get('step') != step:
        account.set_progress(session['userid'], module_id, step=step)

    # explore steps set the active lesson state in the sandbox (never the student's history)
    if current['type'] == 'explore' and 'state' in current:
        account.set_lesson_state(session['userid'], module_id, current['state'])

    # the main area shows this step's data view (its focus, or the nearest preceding one's)
    focus = lesson_active_focus(module, step)
    lesson_data = build_lesson_data(module_id, current, focus)

    # question steps render their form + any prior answer/feedback read back from progress
    question = build_question(module_id, step, current, policy) if current['type'] == 'question' else None
    # checkpoint steps compare the active lesson state to expect_state (Phase 5)
    checkpoint = build_checkpoint(module_id, current) if current['type'] == 'checkpoint' else None

    # Next is a soft (URL-bypassable) gate: locked while a required question is unanswered or
    # a checkpoint has not matched — same spirit as require_answer.
    next_locked = bool((question and question['require_answer'] and not question['answered'])
                       or (checkpoint and not checkpoint['passed']))

    lesson = {
        'module': module, 'entries': lesson_data['entries'],
        'total': lesson_data['total'], 'chips': lesson_data['chips'],
        'step_index': step, 'total_steps': len(steps),
    }

    return render_template('lesson_step.html', module=module, step=current,
                           step_index=step, total=len(steps), user=user,
                           lesson=lesson, lesson_data=lesson_data,
                           question=question, checkpoint=checkpoint,
                           next_locked=next_locked)


@app.route('/lesson/<module_id>/complete')
def lesson_complete(module_id):
    if is_logged_in():

        try:
            module = lessons.get_module(module_id)
        except lessons.LessonError:
            return redirect(url_for('lesson_catalog'))

        # mark the module finished; the overview then shows the completion state
        account.set_progress(session['userid'], module_id,
                             step=len(module['steps']) - 1, completed=True)

        return redirect(url_for('lesson_overview', module_id=module_id))

    else:
        return not_logged_in()


def resolve_lesson_state(module_id, step):
    # a step's own `state` overrides; otherwise inherit the module's active state from progress
    if 'state' in step:
        return step['state']
    return account.get_progress(session['userid'], module_id).get('state', [])


def resolve_module_state(module, step_index):
    # Static counterpart to resolve_lesson_state: walks the module's OWN step list backward for
    # the nearest 'state' (mirrors lesson_active_focus's focus inheritance) instead of reading
    # any signed-in student's progress. Used by the answer-key view (Phase 10, feature 10),
    # which previews a module cold rather than from a specific learner's walkthrough.
    for i in range(step_index, -1, -1):
        if 'state' in module['steps'][i]:
            return module['steps'][i]['state']
    return []


# op code -> readable phrase, for lesson chips and the checkpoint diff
_OP_WORDS = {'eq': 'is', 'ne': 'is not', 'gt': 'is greater than',
             'ge': 'is at least', 'lt': 'is less than', 'le': 'is at most'}


def describe_token(token):
    # A human-readable phrase for one lesson state token (f.col.op.val / o.col.op.v1~v2),
    # e.g. 'f.moc1.eq.A' -> 'Minnesota Offense Code (first character) is A'. Uses the live
    # codebook for the column's friendly name and falls back to the raw code if undocumented.
    action = history_text_to_item(token)['action']
    label = CODEBOOK.codebook.get(action[1], action[1])
    op = _OP_WORDS.get(action[2], action[2])
    value = ' or '.join(action[3]) if action[0] == 'o' else action[3]
    return label + ' ' + op + ' ' + value


def lesson_chips(state):
    # read-only chips (token + friendly desc) for the sidebar "Lesson data" module
    return [{'token': token, 'desc': describe_token(token)} for token in state]


def lesson_active_focus(module, step_index):
    # The data view the main area shows for a step: the step's own `focus`, or the nearest
    # preceding explore step's focus — so a question/checkpoint inherits the view it discusses.
    for i in range(step_index, -1, -1):
        focus = module['steps'][i].get('focus')
        if focus:
            return focus
    return None


def build_lesson_data(module_id, step, focus):
    # Read-only data view for the lesson main area, computed on the step's active lesson state
    # as a sandboxed override on the base dataset (session=None). The student's history is
    # never read or mutated here — lessons are strictly sandboxed (see CLAUDE.md).
    active_state = resolve_lesson_state(module_id, step)
    override = [history_text_to_item(token) for token in active_state]

    summary = get_data(None, history_override=override)
    view = {'kind': None, 'state': active_state, 'chips': lesson_chips(active_state),
            'entries': summary['entries'], 'total': dataset_total(),
            'focus': focus, 'deeplink': None}

    if not focus:
        return view

    if focus.get('view') == 'info':
        column = focus.get('column')
        if column in summary['column_list'] and CODEBOOK.codebook.get(column):
            info = get_data(None, column, 'occurrence', override)['column_info']
            missing = info['len'] - sum(e['num'] for e in info['each'])
            view.update({
                'kind': 'info', 'column': column,
                'header': CODEBOOK.codebook[column], 'info': info, 'missing': missing,
                'missing_percent': (100 * missing / info['len']) if info['len'] else 0,
                'chart': build_chart(info),
                'deeplink': url_for('explore_column', column=column, sorting='occurrence'),
            })

    elif focus.get('view') == 'table':
        dependant, x_axis, y_axis = focus.get('dependant'), focus.get('x_axis'), focus.get('y_axis')
        measure_col = None if dependant == '#' else dependant
        columns_ok = (x_axis in summary['column_list'] and y_axis in summary['column_list']
                      and (measure_col is None or measure_col in summary['column_list']))
        if columns_ok:
            sheet = _execute(None, override).get_table(measure_col, x_axis, y_axis)
            table = build_crosstab(sheet, measure_col is not None)
            view.update({
                'kind': 'table', 'measure': measure_col,
                'measure_desc': CODEBOOK.codebook.get(measure_col) if measure_col else None,
                'row_desc': CODEBOOK.codebook.get(x_axis, x_axis),
                'col_desc': CODEBOOK.codebook.get(y_axis, y_axis),
                'table': table,
                'deeplink': url_for('explore_table_view', dependant=dependant,
                                    x_axis=x_axis, y_axis=y_axis),
            })

    return view


def build_checkpoint(module_id, step):
    # Wire the checkpoint step type: compare the active lesson state (resolved exactly as the
    # explore/grading path resolves it — the step's own state or the inherited progress state)
    # to the step's expect_state as a token MULTISET. This reads only the sandboxed lesson
    # state, never the student's history. Missing/extra tokens become a helpful diff.
    active = resolve_lesson_state(module_id, step)
    expected = step['expect_state']

    missing = list((collections.Counter(expected) - collections.Counter(active)).elements())
    extra = list((collections.Counter(active) - collections.Counter(expected)).elements())

    return {
        'passed': not missing and not extra,
        'expect_state': expected,
        'active_state': active,
        'missing': [describe_token(token) for token in missing],
        'extra': [describe_token(token) for token in extra],
    }


# maps answer.compute.stat -> the key Data.get_column_info returns it under
_STAT_KEY = {'mean': 'mean', 'median': 'mdn', 'std': 'std'}


def compute_expected(module_id, step, state=None):
    # Live-compute the expected numeric answer from the step's data state via Data
    # (never hardcoded), so grading stays correct if the state's filters change. `state`
    # overrides the (session-bound) resolved state -- used by the answer-key view (Phase 10,
    # feature 10), which has no signed-in student to resolve progress from.
    compute = step['answer']['compute']
    tokens = state if state is not None else resolve_lesson_state(module_id, step)
    override = [history_text_to_item(token) for token in tokens]

    summary = get_data(None, history_override=override)

    if compute['stat'] == 'count':
        return float(summary['entries'])

    # mean/median/std need a real numeric column present in the filtered data
    if compute['column'] not in summary['column_list']:
        return None

    info = get_data(None, compute['column'], 'occurrence', override)['column_info']
    value = info[_STAT_KEY[compute['stat']]]
    return float(value) if value is not None else None


def build_answer_key(module):
    # Computed answer key for every graded question in a module (feature 10): generated fresh
    # on each request -- never cached -- so it always reflects the live dataset. Numeric answers
    # reuse compute_expected (the exact function that grades a real submission); choice answers
    # just resolve the authored correct option; free-response questions have no fixed answer.
    rows = []

    for i, step in enumerate(module['steps']):
        if step.get('type') != 'question':
            continue

        answer = step['answer']
        state = resolve_module_state(module, i)
        row = {'step': i, 'title': step['title'], 'type': answer['type'], 'chips': lesson_chips(state)}

        if answer['type'] == 'numeric':
            row['expected'] = compute_expected(module['id'], step, state=state)
            row['tolerance'] = answer['tolerance']
        elif answer['type'] == 'choice':
            row['correct_label'] = answer['options'][answer['correct']]
        else:  # free -- ungraded, no fixed answer
            row['model_answer'] = answer.get('model_answer')

        rows.append(row)

    return rows


def grade_and_store(module_id, step_index, step):
    # Grade a submitted answer entirely server-side. The client never sends a "correct" flag.
    answer = step['answer']
    atype = answer['type']
    submitted = request.form.get('answer', '').strip()

    record = {'type': atype, 'value': submitted, 'correct': None}

    if atype == 'numeric':
        try:
            value = float(submitted)
        except ValueError:
            value = None
        if value is None:
            record['correct'] = False
        else:
            record['value'] = value
            expected = compute_expected(module_id, step)
            record['correct'] = expected is not None and abs(value - expected) <= answer['tolerance'] + 1e-9

    elif atype == 'choice':
        try:
            index = int(submitted)
        except ValueError:
            index = -1
        record['value'] = index
        record['correct'] = (index == answer['correct'])

    # 'free' is not auto-graded: keep value, leave correct = None

    progress = account.get_progress(session['userid'], module_id)
    answers = dict(progress.get('answers', {}))
    answers[str(step_index)] = record
    account.set_progress(session['userid'], module_id, step=step_index, answers=answers)

    # append-only attempt history (feature 5): distinct from progress['answers'] above, which
    # only keeps the latest answer per step -- this is the full history item analytics reads.
    # Only graded attempt types are logged ('free' has no correct/incorrect to aggregate).
    if atype != 'free':
        analytics.log_attempt(session['userid'], {
            'ts': analytics.now_iso(),
            'module': module_id,
            'step': step_index,
            'type': atype,
            'correct': record['correct'],
            'submitted': record['value'],
            'state': resolve_lesson_state(module_id, step),
        })


def build_question(module_id, step_index, step, policy):
    # GET-render context for a question step: the form inputs plus any prior answer/feedback,
    # shaped by the resolved retake & feedback policy (feature 11).
    answer = step['answer']
    prior = account.get_progress(session['userid'], module_id).get('answers', {}).get(str(step_index))

    attempts_used = attempts_used_for(session['userid'], module_id, step_index) if answer['type'] != 'free' else 0
    attempts_allowed = policy['attempts']

    # reveal the correct answer only after a miss, and only when the policy allows it -- 'free'
    # answers have no fixed correct value to reveal (model_answer, below, covers that case)
    reveal = None
    if policy['reveal_after_miss'] and prior is not None and prior.get('correct') is False:
        if answer['type'] == 'numeric':
            reveal = compute_expected(module_id, step)
        elif answer['type'] == 'choice':
            reveal = answer['options'][answer['correct']]

    return {
        'type': answer['type'],
        'options': answer.get('options'),          # choice
        'model_answer': answer.get('model_answer'),  # free
        'prior': prior,                            # {'type','value','correct'} or None
        'answered': prior is not None,
        'require_answer': step.get('require_answer', False),
        'attempts_used': attempts_used,
        'attempts_allowed': attempts_allowed,
        'locked': attempts_allowed is not None and attempts_used >= attempts_allowed,
        'reveal': reveal,
        'show_tolerance': policy['show_tolerance'],
        'tolerance': answer.get('tolerance'),       # numeric
    }


def is_logged_in(): return 'userid' in session
def not_loaded(): return redirect(url_for('load'))


def not_logged_in():
    # a 302 inside an htmx swap would inline the login page into the view fragment;
    # HX-Redirect makes the client do a full-page redirect instead
    if request.headers.get('HX-Request') == 'true':
        response = app.make_response('')
        response.headers['HX-Redirect'] = url_for('login')
        return response
    return redirect(url_for('login'))


def not_implemented(): return "WIP, Feature Not Implemented"
