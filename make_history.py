# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Social Science Component:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# make_history.py
# create history entries

from util import ordinal

CODES = {
    'action': [
        'f',  # single filter
        'o',  # or
        'a'   # and
    ]
}


def operation_text(operation):

    # determine operation text
    if operation == 'eq':
        return ' equal to '
    elif operation == 'ne':
        return ' not equal to '
    elif operation == 'gt':
        return ' greater than '
    elif operation == 'ge':
        return ' greater than or equal to '
    elif operation == 'lt':
        return ' less than '
    elif operation == 'le':
        return ' less than or equal to '


def filter_single(column, operation, value) -> dict:

    entry = {}

    # what we're doing
    entry['action'] = [CODES['action'][0], column, operation, value]

    # what the user will see
    entry['desc'] = 'Kept only entries where ' + column + ' was'
    entry['desc'] += operation_text(operation)
    entry['desc'] += value

    return entry


def filter_or(column, operation, values) -> list:

    pass


def filter_and(column, operation, values) -> list:

    pass


def moc(position, value) -> dict:

    entry = {}

    # what we're doing
    entry['action'] = [CODES['action'][0], 'moc'+str(position), 'eq', value]

    # what the user will see
    entry['desc'] = 'Kept only entries where the ' + ordinal(position) + ' Minnesota Offense Code digit was was ' + value

    return entry


def moc_or(position, values) -> dict:

    pass
