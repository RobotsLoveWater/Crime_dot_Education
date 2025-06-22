import tracemalloc

from data import Data


if __name__ == '__main__':

    entries = [
        {'desc': 'meep', 'action': ['f', 'time', 'gt', '14']},
        {'desc': 'meep', 'action': ['f', 'moc1', 'eq', 'H']},
        {'desc': 'meep', 'action': ['f', 'moc2', 'eq', '1']}
    ]

    full_history = entries

    hist = []
    for item in full_history:
        hist.append('.'.join(item['action']))

    code = '/'.join(hist)

    print(code)