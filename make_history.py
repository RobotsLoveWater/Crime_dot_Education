# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
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
        'o',  # or same
        'd',  # or different
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


def filter_or_same(column, operation, values) -> dict:
    # an or filter operation on the same column

    entry = {}

    # what we're doing
    entry['action'] = [CODES['action'][1], column, operation, values]

    # what the user will see
    entry['desc'] = 'Kept only entries where ' + column + ' was'
    entry['desc'] += operation_text(operation)

    # add all the values we're filtering
    for value in values:
        entry['desc'] += value
        entry['desc'] += ' OR '

    # cut the final ' OR '
    entry['desc'] = entry['desc'][:-4]

    return entry

def filter_or_diff(columns, operations, values) -> list:
    # an or filter operation on different columns

    pass

def filter_and(columns, operations, values) -> list:

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
