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

from markupsafe import Markup, escape

import html
import re
import json
import datetime

import util
import make_history
import moc
import account
import lessons

from data import Data

from cache import get_data, get_moc_options, _execute, history_text_to_item

# create the app
app = Flask(__name__)

# DEVELOPMENT ONLY - this is the secret key
app.secret_key = b'YVjOnAn6NmJ7eHEOPH9RMGAizZRoZsMrbvyHkZaIVMMX71NdS8wRdvJPFe7GEzNwQ6oCELKLmeQUDLeUZk92ooUKKtyNcVBzsnbK'

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
        global _dataset_total
        try:
            if _dataset_total is None:
                _dataset_total = get_data(None)['entries']
            context['datastate'] = {
                'entries': get_data(session)['entries'],
                'total': _dataset_total
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


# homepage
@app.route("/")
@app.route("/landing")
def index():

    if is_logged_in():

        # set the user based on cookies
        user = account.retrieve(session['userid'])

    else: user = None

    # real lesson metrics for the homepage cards (replaces the hardcoded 0)
    modules = lessons.list_modules()
    lesson_count = len(modules)

    lessons_completed = 0
    if user:
        progress = user.get('progress', {})
        lessons_completed = sum(1 for m in modules if progress.get(m['id'], {}).get('completed'))

    return render_template('index.html', user=user, lesson_count=lesson_count,
                           lessons_completed=lessons_completed, hero_image_url='')


@app.route("/guide")
def guide():
    if is_logged_in():

        # set the user based on cookies
        user = account.retrieve(session['userid'])

    else:

        user = None

    return render_template('guide.html', user=user)

# account creation page
@app.route("/new", methods=['GET', 'POST'])
def new():
    error = None

    if request.method == 'POST':

        sanitized_form = {
            'password': html.escape(request.form['password']),
            'username': html.escape(request.form['username']),
            'classcode': html.escape(request.form['classcode'])
        }

        # if this user does not exist, create
        if sanitized_form['username'] not in account.get_user_list(sanitized_form['classcode']):

            # deal with the password
            hashed_password = util.get_hashed_password(sanitized_form['password'])

            # generate the new user account
            new_user = account.create(sanitized_form['username'], sanitized_form['classcode'],  hashed_password)

            # get derived userid
            session['userid'] = new_user['userid']

            # send them to the homepage
            return redirect(url_for('index'))

        # user already exists, let them know
        else:
            errortext = 'A user by the name ' + sanitized_form['username'] + ' already exists'
            if sanitized_form['classcode']: errortext += ' in class ' + sanitized_form['classcode']
            error = [errortext]

    return render_template('new.html', error=error)


# login page
@app.route("/login", methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':

        sanitized_form = {
            'password': html.escape(request.form['password']),
            'username': html.escape(request.form['username']),
            'classcode': html.escape(request.form['classcode'])
        }


        if sanitized_form['username'] == '':
            error = ['No username entered']

        else:

            if sanitized_form['username'] not in account.get_user_list(sanitized_form['classcode']):
                errortext = 'A user by the name ' + sanitized_form['username'] + ' does not exist'
                if sanitized_form['classcode']: errortext += ' in class ' + sanitized_form['classcode']
                error = [errortext]

            else:

                session['username'] = sanitized_form['username']
                session['classcode'] = sanitized_form['classcode']
                session['userid'] = account.form_userid(session['username'], session['classcode'])

                return redirect(url_for('index'))

    return render_template('login.html', error=error)


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


# Legacy statistics URLs (pre-overhaul). The endpoint names survive on purpose:
# lesson deep links (build_explore) still emit /info/... until Phase 5.
@app.route("/info/")
def info_menu():
    return redirect(url_for('explore'))


@app.route("/info/<column>/")
@app.route("/info/<column>/<sorting>")
def info_specific(column, sorting='occurrence'):
    return redirect(url_for('explore_column', column=column, sorting=sorting))


@app.route("/table", methods=['GET', 'POST'])
def table_menu():
    if is_logged_in():
        error = []
        user = account.retrieve(session['userid'])

        if request.method == 'POST':

            # check that the form was filled out
            if request.form['dependant'] == '':
                error.append("Dependant variable not selected.")
            if request.form['x_axis'] == '':
                error.append("Y-Axis variable not selected.")  # flipped due to display issues
            if request.form['y_axis'] == '':
                error.append("X-Axis variable not selected.")  # flipped due to display issues

            # check that the form has no duplicates
            form_result = [request.form['dependant'], request.form['x_axis'], request.form['y_axis']]
            if len(set(form_result)) != len(form_result):
                error.append("There are duplicates selected.")

            if len(error) == 0:
                return redirect(url_for('table', dependant=request.form['dependant'], x_axis=request.form['x_axis'], y_axis=request.form['y_axis']))

        data = get_data(session)
        return render_template('perm_menu.html', data=data, error=error, user=user)

    else:
        return not_logged_in()


@app.route("/table/<dependant>/<x_axis>/<y_axis>")
def table(dependant, x_axis, y_axis):
    if is_logged_in():
        user = account.retrieve(session['userid'])

        temp_data = _execute(session)

        data = get_data(session)

        columns = temp_data.get_columns_w_codebook()
        variables = {
            'x': [x_axis, columns[x_axis]],
            'y': [y_axis, columns[y_axis]]
        }

        # deal with the dependant variable possibly being simply the number of times occurring
        variables['d'] = [dependant, '']
        if dependant == '#':
            variables['d'][1] = 'Number of Occurrences.'
            dependant = None
        else:
            variables['d'][1] = columns[dependant]

        sheet = temp_data.get_table(dependant, x_axis, y_axis)

        yh = sheet[list(sheet.keys())[0]]

        return render_template('perm.html', data=data, variables=variables, y_headers=yh, sheet=sheet, user=user)

    else:
        return not_logged_in()


@app.route("/filter/")
def filter_menu():
    if is_logged_in():
        user = account.retrieve(session['userid'])

        return render_template('filter.html', user=user)

    else:
        return not_logged_in()


@app.route("/filter/boolean/")
def filter_boolean_menu():
    if is_logged_in():
        user = account.retrieve(session['userid'])

        data = get_data(session)

        return render_template('filter_boolean_menu.html', data=data, user=user)

    else:
        return not_logged_in()


@app.route("/filter/boolean/<column>/")
def filter_boolean_redirect(column):
    return redirect(url_for('filter_boolean', column=column, sorting='occurrence'))


@app.route("/filter/boolean/<column>/<sorting>", methods=['GET', 'POST'])
def filter_boolean(column, sorting):
    if is_logged_in():
        error = []
        user = account.retrieve(session['userid'])
        values = request.form.getlist('value')

        if request.method == 'POST':

            # trying to compare to nothing
            if values is None or values == []:
                error.append("Filter value input cannot be blank.")

            # trying to compare non-numbers numerically
            elif request.form['comparison'] in ['gt', 'ge', 'lt', 'le']:
                try:
                    float(values[0])
                except ValueError:
                    error.append("Filter value: " + values[0] + " is not numeric and a numeric comparison was selected.")

            # no comparison selected
            if request.form['comparison'] not in ['eq', 'ne', 'gt', 'ge', 'lt', 'le']:
                error.append('No comparison selected.')

            # edit the history log
            else:
                if len(values) == 1:
                    entry = make_history.filter_single(column, request.form['comparison'], values[0])
                else:
                    entry = make_history.filter_or_same(column, request.form['comparison'], values)
                account.history_add(session['userid'], entry)
                flash(entry['desc'], 'success')
                return redirect(url_for('index'))

        if sorting not in Data.VALID_SORTING:
            return redirect(url_for('filter_boolean', column=column, sorting='occurrence'))

        data = get_data(session, column, sorting)

        if column in data['column_list']:

            return render_template('filter_boolean.html', column=column, data=data, error=error, user=user, sorting=sorting)

        else:

            return redirect(url_for('filter_boolean_menu'))

    else:
        return not_logged_in()


@app.route("/filter/moc/")
def filter_moc1():
    if is_logged_in():
        user = account.retrieve(session['userid'])

        data = get_data(session)

        return render_template('moc1.html', data=data, code_list=MOC.CODES, user=user)

    else:
        return not_logged_in()


@app.route("/filter/moc/<moc1>/<moc2>/<moc3>/<moc4>/<moc5>/<active>", methods=['GET', 'POST'])
def filter_moc(moc1, moc2, moc3, moc4, moc5, active):
    if is_logged_in():

        if request.method == 'GET':
            user = account.retrieve(session['userid'])

            code_list = MOC.CODES[moc1]
            cur_moc = [moc1, moc2, moc3, moc4, moc5]

            moc_col = []

            # this creates a list of relevant code positions, taking into effect
            # the fact that some codes may span multiple digits

            # did the previous value fell under inc
            prev_inc = False
            for ii in range(1,5):
                try:
                    MOC.CODES[moc1][ii]['INC']
                    if prev_inc == False:
                        moc_col.append(ii)
                    prev_inc = True
                except KeyError:
                    moc_col.append(ii)
                    prev_inc = False

            data = get_data(session)
            data['moc_options'] = get_moc_options(session, cur_moc[:], active)

            return render_template('moc.html', code_list=code_list, moc_col=moc_col, cur_moc=cur_moc, active=int(active), data=data, user=user)

        else:

            # create the new history entry based on the moc changes, excluding wildcards
            cur_moc = [moc1, moc2, moc3, moc4, moc5]
            applied = []
            for k, digit in enumerate(cur_moc):
                if digit != '*':
                    entry = make_history.moc(k+1, digit)
                    account.history_add(session['userid'], entry)
                    applied.append(entry['desc'])

            if len(applied) == 1:
                flash(applied[0], 'success')
            elif applied:
                flash('Offense code filter applied (' + str(len(applied)) + ' steps).', 'success')

            return redirect(url_for('index'))

    else:
        return not_logged_in()


@app.route('/download')
def download():
    if is_logged_in():
        return not_implemented()
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
                return redirect(url_for('index'))

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
        return redirect(url_for('index'))
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
        catalog = [{'module': m, 'status': module_status(progress.get(m['id']))}
                   for m in lessons.list_modules()]

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
    if is_logged_in():
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

        # explore steps materialize their data state in a sandbox (never the student's history)
        explore = None
        if current['type'] == 'explore':
            explore = build_explore(module_id, current)

        # question steps render their form + any prior answer/feedback read back from progress
        question = None
        if current['type'] == 'question':
            question = build_question(module_id, step, current)

        return render_template('lesson_step.html', module=module, step=current,
                               step_index=step, total=len(steps),
                               explore=explore, question=question, user=user)

    else:
        return not_logged_in()


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


def build_explore(module_id, step):
    # Reconstruct the step's data state as a sandboxed override and summarize it inline.
    # A step with its own `state` sets the module's active state; otherwise it inherits the
    # active state recorded on the student's progress. The student's own history is untouched.

    if 'state' in step:
        account.set_lesson_state(session['userid'], module_id, step['state'])

    active_state = resolve_lesson_state(module_id, step)

    # tokens -> history items, applied on top of the base dataset only (session=None)
    override = [history_text_to_item(token) for token in active_state]
    summary = get_data(None, history_override=override)

    focus = step.get('focus') or {}
    column_info = None
    deeplink = None

    if focus.get('view') == 'info' and focus.get('column') in summary['column_list']:
        column = focus['column']
        column_info = get_data(None, column, 'occurrence', override)['column_info']
        deeplink = url_for('info_specific', column=column, sorting='occurrence')

    elif focus.get('view') == 'table':
        deeplink = url_for('table', dependant=focus['dependant'],
                           x_axis=focus['x_axis'], y_axis=focus['y_axis'])

    return {
        'state': active_state,
        'entries': summary['entries'],
        'focus': focus,
        'column_info': column_info,
        'deeplink': deeplink
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
