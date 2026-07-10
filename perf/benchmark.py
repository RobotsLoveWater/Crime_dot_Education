# perf/benchmark.py
#
# Phase 0 repeatable benchmark (REQUEST_PATH_OPTIMIZATION_PROMPTS.md). Drives four flows
# against a warm, in-process Flask app (via test_client — real routes, real templates, real
# session) and reports wall time plus per-flow _execute/get_column_info/get_table call
# counts, using the perf/profiling.py timing shim:
#
#   (a) apply a filter, then view 8 different columns
#   (b) render a Compare crosstab
#   (c) render the Visualize choropleth + scatter
#   (d) hit a non-data page (a lesson step) while logged in
#
# These are the "before numbers" Phase 0 exists to capture; later phases re-run this same
# script and diff against the printed summary.
#
# Usage (from the repo root):
#   uv run python perf/benchmark.py
#
# PROFILE_REQUESTS must be on for the shim to record anything -- this script sets it before
# importing app/cache/data if the caller didn't already (profiling.ENABLED is latched at
# import time), so plain `uv run python perf/benchmark.py` works without remembering the
# env var separately.

import os
import shutil
import sys
import time

os.environ.setdefault('PROFILE_REQUESTS', '1')

import app as flask_app
import account
import cache
import make_history
import perf.profiling as profiling

BENCH_USERNAME = 'bench'
BENCH_CLASSCODE = 'perf-bench'

# Columns exercised by flow (a) -- a spread of categorical + numeric, low + high cardinality,
# distinct from the 'time' column the filter itself targets.
FLOW_A_COLUMNS = ['sex', 'race', 'county', 'moc1', 'district', 'severity', 'offtype', 'sentyear']


def _ensure_account() -> str:
    # Dedicated benchmark account under its own classcode so this never touches a real
    # student/educator pickle. Reused across runs (idempotent) rather than deleted after,
    # matching this repo's throwaway-but-inspectable convention for scratch fixtures.
    userid = account.form_userid(BENCH_USERNAME, BENCH_CLASSCODE)
    try:
        account.retrieve(userid)
    except FileNotFoundError:
        account.create(BENCH_USERNAME, BENCH_CLASSCODE, 'unused-benchmark-password')
    return userid


def _login(client, userid) -> None:
    # Sign the test client in directly via the session -- same three keys /login sets
    # (app.py's login()) -- bypassing password verification entirely, since auth isn't
    # part of the request-path work being measured.
    user = account.retrieve(userid)
    with client.session_transaction() as sess:
        sess['userid'] = user['userid']
        sess['username'] = user['username']
        sess['classcode'] = user['classcode']


def _reset_history(userid) -> None:
    account.history_revert(userid, 1)


def _run_flow(name, client, userid, drive) -> dict:
    _reset_history(userid)
    profiling.REQUEST_LOG.clear()

    wall_start = time.perf_counter()
    drive(client)
    wall_elapsed = time.perf_counter() - wall_start

    totals = {}
    for entry in profiling.REQUEST_LOG:
        for label, stats in entry['counters'].items():
            agg = totals.setdefault(label, {'count': 0, 'total': 0.0})
            agg['count'] += stats['count']
            agg['total'] += stats['total']

    print()
    print('=' * 70)
    print('FLOW: {}'.format(name))
    print('=' * 70)
    print('  requests:   {}'.format(len(profiling.REQUEST_LOG)))
    print('  wall time:  {:.2f}ms'.format(wall_elapsed * 1000))
    for label, stats in sorted(totals.items()):
        print('  {:<18} {} call(s), {:.2f}ms total'.format(
            label + ':', stats['count'], stats['total'] * 1000))

    return {'name': name, 'requests': len(profiling.REQUEST_LOG),
            'wall_ms': wall_elapsed * 1000, 'counters': totals}


# ---- flow definitions ------------------------------------------------------

FLOW_A_TOKEN = 'f.time.gt.14'


def flow_a(client):
    # apply a filter, then view 8 different columns. get_data() disk-caches by history
    # token (unlike flows b/c, which call _execute directly and are never cached), so a
    # rerun of this script would otherwise hit a warm cache and understate the cost --
    # clear this flow's target dir first, mirroring the golden-snapshot warmer's convention
    # (MAST/phase0-golden/scripts/warm_golden.py) of force-recomputing before measuring.
    _clear_cache_dir(FLOW_A_TOKEN)
    cache._clear_filtered_cache()  # Phase 3: also cold the in-memory slice LRU, or a rerun
                                   # in a persistent process would hide the first replay
    client.post('/explore/filter/time', data={'comparison': 'gt', 'value': '14'})
    for col in FLOW_A_COLUMNS:
        client.get('/explore/column/{}'.format(col))


def flow_b(client):
    # render a Compare crosstab (a numeric measure over two categoricals)
    client.get('/explore/table/time/sex/race')


def flow_c(client):
    # render the Visualize choropleth + scatter
    client.get('/visualize?chart=choropleth')
    client.get('/visualize?chart=scatter&column=time&column2=history')


def flow_d(client):
    # hit a non-data page (a lesson step) while logged in
    client.get('/lesson/intro-explorer-basics/0')


# ---- supplementary discovery check ----------------------------------------
# Not one of the four required flows -- isolates the literal "double replay in one cold
# render" case REQUEST_PATH_OPTIMIZATION_PROMPTS.md Phase 3 targets (render_explore's two
# get_data() calls, app.py ~713/~729). Flow (a) alone doesn't show 2 execute calls per column
# because the filter-apply POST's own "remaining cases" count already warms _data.bin as a
# side effect; this check bypasses that by seeding the history directly, so BOTH _data.bin
# and <col>.bin are missing when the single /explore/column/<col> request lands.
COLD_TOKEN = 'f.history.gt.3'
COLD_COLUMN = 'aggsentc'


def _clear_cache_dir(token) -> None:
    path = cache.DATAPATH + token
    if os.path.isdir(path):
        shutil.rmtree(path)


def flow_cold_column(client, userid):
    _clear_cache_dir(COLD_TOKEN)
    cache._clear_filtered_cache()  # Phase 3: cold the slice LRU too, so the single column
                                   # view is the genuine 2-replays-in-one-page cold case
    account.history_add(userid, make_history.filter_single('history', 'gt', '3'))
    client.get('/explore/column/{}'.format(COLD_COLUMN))


def main() -> int:
    if not profiling.ENABLED:
        print('PROFILE_REQUESTS is not enabled (perf.profiling.ENABLED is False) -- '
              'this should not happen since main() sets it before import. Aborting.')
        return 1

    flask_app.app.testing = True
    client = flask_app.app.test_client()

    userid = _ensure_account()
    _login(client, userid)

    results = [
        _run_flow('(a) filter + view 8 columns', client, userid, flow_a),
        _run_flow('(b) Compare crosstab', client, userid, flow_b),
        _run_flow('(c) Visualize choropleth + scatter', client, userid, flow_c),
        _run_flow('(d) non-data lesson-step page', client, userid, flow_d),
        _run_flow('(discovery) cold column view (_data.bin + <col>.bin both missing)',
                  client, userid, lambda c: flow_cold_column(c, userid)),
    ]

    _reset_history(userid)  # leave the benchmark account clean for the next run

    print()
    print('=' * 70)
    print('SUMMARY')
    print('=' * 70)
    for r in results:
        execs = r['counters'].get('_execute', {}).get('count', 0)
        print('  {:<38} requests={:<3} wall={:>9.2f}ms  _execute={}'.format(
            r['name'], r['requests'], r['wall_ms'], execs))

    return 0


if __name__ == '__main__':
    sys.exit(main())
