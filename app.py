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

from markupsafe import Markup, escape

import html
import re

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


# homepage
@app.route("/")
@app.route("/landing")
def index():

    if is_logged_in():

        # set the user based on cookies
        user = account.retrieve(session['userid'])

    else: user = None

    return render_template('index.html', user=user)


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
    return not_logged_in()


@app.route("/info/")
def info_menu():
    if is_logged_in():

        user = account.retrieve(session['userid'])
        data = get_data(session)

        return render_template('info_menu.html', data=data, user=user)

    else:
        return not_logged_in()


@app.route("/info/<column>/")
def info_specific_redirect(column):
    return redirect(url_for('info_specific', column=column, sorting='occurrence'))


@app.route("/info/<column>/<sorting>")
def info_specific(column, sorting):
    if is_logged_in():
        user = account.retrieve(session['userid'])

        if sorting not in Data.VALID_SORTING:
            return redirect(url_for('info_specific', column=column, sorting='occurrence'))

        data = get_data(session, column, sorting)

        if column in data['column_list']:

            return render_template('info.html', column=column, data=data, user=user, sorting=sorting)

        else:
            return redirect(url_for('index'))

    else:
        return not_logged_in()


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
                    account.history_add(session['userid'], make_history.filter_single(column, request.form['comparison'], values[0]))
                    return redirect(url_for('index'))
                else:
                    account.history_add(session['userid'], make_history.filter_or_same(column, request.form['comparison'], values))
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
            for k,moc in enumerate(cur_moc):
                if moc != '*':
                    account.history_add(session['userid'], make_history.moc(k+1, moc))

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
                error = 'Invalid code'
            else:
                account.history_revert(session['userid'])
                return redirect(url_for('index'))

        return render_template('load.html', error=error, user=user)
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


@app.route('/admin')
def admin():
    return not_implemented()


@app.route('/lesson')
def lesson_catalog():
    if is_logged_in():
        user = account.retrieve(session['userid'])

        modules = lessons.list_modules()

        return render_template('lesson_catalog.html', modules=modules, user=user)

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

        return render_template('lesson.html', module=module, user=user)

    else:
        return not_logged_in()


@app.route('/lesson/<module_id>/<int:step>')
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

        # explore steps materialize their data state in a sandbox (never the student's history)
        explore = None
        if current['type'] == 'explore':
            explore = build_explore(module_id, current)

        return render_template('lesson_step.html', module=module, step=current,
                               step_index=step, total=len(steps), explore=explore, user=user)

    else:
        return not_logged_in()


def build_explore(module_id, step):
    # Reconstruct the step's data state as a sandboxed override and summarize it inline.
    # A step with its own `state` sets the module's active state; otherwise it inherits the
    # active state recorded on the student's progress. The student's own history is untouched.

    if 'state' in step:
        active_state = step['state']
        account.set_lesson_state(session['userid'], module_id, active_state)
    else:
        active_state = account.get_progress(session['userid'], module_id).get('state', [])

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


def is_logged_in(): return 'userid' in session
def not_loaded(): return redirect(url_for('load'))
def not_logged_in(): return redirect(url_for('login'))
def not_implemented(): return "WIP, Feature Not Implemented"
