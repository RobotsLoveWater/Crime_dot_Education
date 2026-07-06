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

import util
import make_history
import moc
import account
import classroom
import lessons

from data import Data

from cache import get_data, get_moc_options, _execute, history_text_to_item

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

# sort orders for the statistics value table: internal key -> student-facing label
SORT_OPTIONS = [
    ('occurrence', 'Most common'),
    ('reverse_occurrence', 'Least common'),
    ('alphanumeric', 'A to Z'),
    ('reverse_alphanumeric', 'Z to A')
]

# tooltip for the excluded columns in the column browser (replaces !!!WARNING!!!)
EXCLUDED_NOTE = 'Excluded from analysis — identifies individual people or cases.'


@app.template_filter('lesson_body')
def lesson_body(text):
    # Minimal, dependency-free markdown for lesson step bodies. The markdown-vs-HTML
    # question is still open (see LEARNING_MODULES_PROMPTS.md Appendix C); this covers the
    # small subset the fixtures use: paragraphs, **bold**, `inline code`, and "- " bullet lists.
    # Author text is HTML-escaped FIRST, so nothing here can inject markup.
    if not text:
        return Markup('')

    text = str(escape(text))
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)

    blocks = []
    for block in re.split(r'\n\s*\n', text):
        lines = [ln for ln in block.split('\n') if ln.strip() != '']
        if lines and all(ln.startswith('- ') for ln in lines):
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


def render_landing(user):
    # The marketing landing (logged-out home, and /landing for anyone). Honest metric
    # cards: the fixed dataset facts plus the real lesson count / completion for this user.
    modules = lessons.list_modules()

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
    for m in lessons.list_modules():
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
        user = account.retrieve(session['userid'])
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


# account creation page
@app.route("/new", methods=['GET', 'POST'])
def new():
    errors = None

    if request.method == 'POST':

        # the password MUST go through util.normalize_password — the same helper /login verifies
        # with — so create and verify can never drift (see util.py)
        password = util.normalize_password(request.form['password'])
        username = html.escape(request.form['username'])

        # resolve the overloaded "code" box: public / educator / class enrollment / error
        resolution = resolve_class_code(request.form['classcode'])

        # a non-blank, non-edu code matching no live class creates nothing (the old behavior
        # silently spun up a stray user/<code>/ directory — that is what this replaces)
        if resolution['kind'] == 'unknown':
            errors = ['No class found with that code. Leave the code blank to join the public '
                      'group, or check the join code with your teacher.']
            return render_template('new.html', errors=errors)

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
            # public ('unmanaged') or educator ('edu-*') — unchanged
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

            # resolve the code box the SAME way /new does, so a student who enrolled with a join
            # code signs in with that same code (it maps back to their class_id namespace). Legacy
            # accounts under a bare classcode still resolve via the 'unknown' branch (classcode =
            # the typed code), so Phase 0 login behavior is unchanged for them.
            classcode = resolve_class_code(request.form['classcode'])['classcode']

            if username not in account.get_user_list(classcode):
                error = bad_credentials

            else:

                user = account.retrieve(account.form_userid(username, classcode))

                if util.check_password(password, user['password']):

                    # sign them in from the stored account (classcode already cleaned to
                    # 'unmanaged' when blank), matching what /new stores in the session
                    session['username'] = user['username']
                    session['classcode'] = user['classcode']
                    session['userid'] = user['userid']

                    return redirect(url_for('index'))

                else:
                    error = bad_credentials

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


def build_chart(column_info, top=20):
    # distribution chart payload: top-N values by case count plus an "Other" bucket;
    # the value table below the chart carries every value
    by_count = sorted(column_info['each'], key=lambda e: e['num'], reverse=True)
    return {
        'labels': [display_value(e['value']) for e in by_count[:top]],
        'counts': [e['num'] for e in by_count[:top]],
        'other': sum(e['num'] for e in by_count[top:]),
        'otherValues': len(by_count) - min(len(by_count), top)
    }


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
        # column view, now showing updated chips, refreshed counts, or the zero-case state
        return redirect(url_for('explore_filter_column', column=column))

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


def slugify(text):
    # sanitize a raw id into a filename-/URL-safe slug ([a-z0-9-]); prevents path traversal
    return re.sub(r'[^a-z0-9-]+', '-', text.strip().lower()).strip('-')


@app.route('/admin')
def admin():
    blocked = require_educator()
    if blocked:
        return blocked

    user = account.retrieve(session['userid'])
    classcode = user['classcode']

    # educators manage the modules scoped to their own classcode
    mine = [m for m in lessons.list_modules() if m.get('author') == classcode]

    return render_template('admin.html', user=user, modules=mine, classcode=classcode)


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
        catalog = []
        for m in lessons.list_modules():
            entry = progress.get(m['id'])
            total = len(m['steps'])
            catalog.append({
                'module': m,
                'status': module_status(entry),
                'resume': resume_step(entry, total),
                'total_steps': total,
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

    # POST an answer -> grade it server-side, persist, then redirect back (Post/Redirect/Get)
    if request.method == 'POST' and current['type'] == 'question':
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
    question = build_question(module_id, step, current) if current['type'] == 'question' else None
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


def compute_expected(module_id, step):
    # Live-compute the expected numeric answer from the step's data state via Data
    # (never hardcoded), so grading stays correct if the state's filters change.
    compute = step['answer']['compute']
    override = [history_text_to_item(token) for token in resolve_lesson_state(module_id, step)]

    summary = get_data(None, history_override=override)

    if compute['stat'] == 'count':
        return float(summary['entries'])

    # mean/median/std need a real numeric column present in the filtered data
    if compute['column'] not in summary['column_list']:
        return None

    info = get_data(None, compute['column'], 'occurrence', override)['column_info']
    value = info[_STAT_KEY[compute['stat']]]
    return float(value) if value is not None else None


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


def build_question(module_id, step_index, step):
    # GET-render context for a question step: the form inputs plus any prior answer/feedback.
    answer = step['answer']
    prior = account.get_progress(session['userid'], module_id).get('answers', {}).get(str(step_index))

    return {
        'type': answer['type'],
        'options': answer.get('options'),          # choice
        'model_answer': answer.get('model_answer'),  # free
        'prior': prior,                            # {'type','value','correct'} or None
        'answered': prior is not None,
        'require_answer': step.get('require_answer', False)
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
