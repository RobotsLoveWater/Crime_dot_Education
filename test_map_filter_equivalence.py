# MN Analysis of Sentencing Trends
# test_map_filter_equivalence.py
#
# Guardrail for Phase 11 of the visualization expansion (map-click → filter): the linchpin
# equivalence. Clicking a geography must append EXACTLY the history entry typing that
# filter would — same token, same cache/data/ directory — on both surfaces (the Visualize
# choropleth and the Filter view's map input). A silent divergence here (a county submitted
# with the TopoJSON's spelling instead of the dataset's, a district encoded "4" instead of
# "4.0") would land in a DIFFERENT cache directory and serve wrong-but-plausible numbers —
# the worst failure mode in the whole effort — so this pins the payloads' filter values
# end-to-end, over EVERY county / district / region, not a sample.
#
# Both surfaces are equivalent BY CONSTRUCTION (the Filter map toggles the same checkboxes
# / fills the same input the hand path uses; the Visualize click posts the same fields to
# the same apply route), so what this test pins is the one datum the maps ship that a hand
# path types: the per-shape `filterValue` / `value`.
#
# Runs standalone (`uv run python test_map_filter_equivalence.py`, prints a report and
# exits non-zero on failure). The test_* functions are also pytest-compatible. Needs the
# base datafile (cache/raw.parquet or cache/raw.csv), like test_base_immutability.py.

import sys

import app as app_module
import cache
import make_history
from data import Data

# One hand-typed exemplar per grain (the acceptance criteria's spellings: district as "4.0").
TYPED = {
    'county': 'Hennepin',
    'district': '4.0',
    'region': 'Oth Metro',
}

# The counties whose DATASET spelling differs from the TopoJSON feature name (geo.py's
# alias table). These are where a naive "use the map's name" click silently diverges.
ALIASED = {'Le Sueur': 'LeSueur', 'Lac qui Parle': 'Lac Qui Parle'}  # {feature: dataset}

# Expected geography counts over the full base dataset.
EXPECTED_UNITS = {'county': 87, 'district': 10, 'region': 4}


def _direct_count(column, value):
    # The row count typing `f.<column>.eq.<value>` would keep: the production filter,
    # read-only over the shared base (Data.filter coerces to float on float64 columns,
    # so "4.0" hits district exactly the way the boolean-filter route does).
    engine = Data()
    return len(engine.filter(column, 'eq', value, inplace=False, source=cache._base_df()))


def _token_and_dir(entry):
    token = cache.history_item_to_text(entry)
    return token, cache.DATAPATH + token


def test_choropleth_click_equals_typed():
    """Visualize surface: every shape's filterValue produces the typed filter's exact
    token + cache dir, and selects exactly the cases the map colored the shape with."""
    for grain, typed_value in TYPED.items():
        with app_module.app.test_request_context():
            payload = app_module.build_choropleth(None, 'count', Data.COUNT_MEASURE,
                                                  None, grain)

        column = payload['filterColumn']
        assert column == grain, f'{grain}: filterColumn drifted to {column!r}'
        assert payload['applyUrl'] == '/explore/filter/' + column, \
            f'{grain}: applyUrl {payload["applyUrl"]!r} is not the filter apply route'

        by_feature = payload['byFeature']
        assert len(by_feature) == EXPECTED_UNITS[grain], \
            f'{grain}: expected {EXPECTED_UNITS[grain]} shapes with data, got {len(by_feature)}'

        # EVERY shape: the click token must keep exactly the shape's own cases. This is
        # the spelling trap detector — a feature-spelled county ("Le Sueur") or an
        # int-spelled district ("4") keeps 0 rows / lands in a different dir.
        for fkey, rec in by_feature.items():
            value = rec['filterValue']
            entry_click = make_history.filter_single(column, 'eq', value)
            token, _ = _token_and_dir(entry_click)
            assert token == f'f.{column}.eq.{value}', f'{grain}/{fkey}: token {token!r}'
            kept = _direct_count(column, value)
            assert kept == rec['n'], (
                f'{grain}/{fkey}: clicking keeps {kept} cases but the map shows '
                f'{rec["n"]} — filterValue {value!r} diverges from the dataset value')
            # token round-trips through the decoder the lesson/share paths use
            assert cache.history_text_to_item(token)['action'] == entry_click['action'], \
                f'{grain}/{fkey}: token does not round-trip'

        # the hand-typed exemplar resolves to the SAME entry, token, and cache dir
        # (byFeature is keyed by feature key: the TopoJSON county name / the group key —
        # for these exemplars identical to the typed value)
        assert typed_value in by_feature, \
            f'{grain}: typed exemplar {typed_value!r} missing from byFeature'
        click_value = by_feature[typed_value]['filterValue']
        entry_click = make_history.filter_single(column, 'eq', click_value)
        entry_typed = make_history.filter_single(column, 'eq', typed_value)
        assert entry_click['action'] == entry_typed['action'], \
            f'{grain}: click action {entry_click["action"]} != typed {entry_typed["action"]}'
        click_token, click_dir = _token_and_dir(entry_click)
        typed_token, typed_dir = _token_and_dir(entry_typed)
        assert click_token == typed_token and click_dir == typed_dir, \
            f'{grain}: click dir {click_dir!r} != typed dir {typed_dir!r}'

        # district must encode as the float string ("4.0"), never the bare int
        if grain == 'district':
            assert click_value == '4.0', f'district filterValue {click_value!r} != "4.0"'

        # the row payload (the "Keep only" no-JS path) carries the same values
        row_values = {r['filterValue'] for r in payload['rows']}
        assert row_values == {rec['filterValue'] for rec in by_feature.values()}, \
            f'{grain}: table rows and map shapes disagree on filter values'


def test_choropleth_click_matches_production_pipeline():
    """One end-to-end per grain: the click entry replayed through the REAL cache pipeline
    (get_data + history_override) lands in the typed dir and reports the typed count."""
    for grain, typed_value in TYPED.items():
        entry = make_history.filter_single(grain, 'eq', typed_value)
        result = cache.get_data(None, history_override=[entry])
        expected = _direct_count(grain, typed_value)
        assert result['entries'] == expected, (
            f'{grain}: pipeline kept {result["entries"]} cases, direct filter keeps '
            f'{expected}')


def test_filter_map_values_match_the_list():
    """Filter-view surface: every map shape's value is EXACTLY a value the checkbox list /
    numeric input carries (same string, same count) — the map can only ever submit what
    the hand path would."""
    for grain in TYPED:
        info = cache.get_data(None, grain, 'occurrence')['column_info']
        with app_module.app.test_request_context():
            fm = app_module.build_filter_map(grain, info)

        expected_mode = 'single' if info['numeric'] else 'multi'
        assert fm['mode'] == expected_mode, f'{grain}: mode {fm["mode"]!r}'
        assert len(fm['values']) == EXPECTED_UNITS[grain], \
            f'{grain}: expected {EXPECTED_UNITS[grain]} clickable shapes, got {len(fm["values"])}'

        # the list path's exact submittable strings + counts (what Jinja renders into
        # value="..." for checkboxes, and what a hand-typed district value is)
        list_values = {str(row['value']): row['num'] for row in info['each']}
        for key, rec in fm['values'].items():
            assert rec['value'] in list_values, (
                f'{grain}/{key}: map value {rec["value"]!r} has no matching list value — '
                'a click could never equal the hand path')
            assert rec['count'] == list_values[rec['value']], \
                f'{grain}/{key}: count {rec["count"]} != list count {list_values[rec["value"]]}'

        # the two alias counties: map feature key -> DATASET spelling (the whole point)
        if grain == 'county':
            for feature, dataset_spelling in ALIASED.items():
                assert feature in fm['values'], f'county: feature {feature!r} missing'
                assert fm['values'][feature]['value'] == dataset_spelling, (
                    f'county: {feature!r} submits {fm["values"][feature]["value"]!r}, '
                    f'not the dataset spelling {dataset_spelling!r}')

        # dissolved grains ship the same crosswalk the choropleth uses
        if grain != 'county':
            dissolve, labels = app_module.build_geo_dissolve(grain)
            assert fm['dissolve'] == dissolve and fm['groupLabels'] == labels, \
                f'{grain}: filter map and choropleth dissolve maps disagree'


def test_or_multiselect_matches_list_path():
    """Multi-select via the map = the same checkboxes = the same `o.` OR token, and the
    preview candidate resolves to the same dir the apply will."""
    values = ['Hennepin', 'Ramsey']
    entry = make_history.filter_or_same('county', 'eq', values)
    token, or_dir = _token_and_dir(entry)
    assert token == 'o.county.eq.Hennepin~Ramsey', f'OR token drifted: {token!r}'
    assert cache.history_text_to_item(token)['action'] == entry['action']

    # the live-preview candidate (filter_candidate) encodes to the same token/dir, so the
    # "~N would match" count equals the post-apply chip count — multi and single value
    cand_token, cand_dir = _token_and_dir(app_module.filter_candidate('county', 'eq', values))
    assert (cand_token, cand_dir) == (token, or_dir), 'preview candidate diverges (OR)'
    single = make_history.filter_single('county', 'eq', 'Hennepin')
    cand_single = app_module.filter_candidate('county', 'eq', ['Hennepin'])
    assert _token_and_dir(cand_single) == _token_and_dir(single), \
        'preview candidate diverges (single)'


def test_safe_return_target():
    """The `next` redirect override accepts only local absolute paths (no open redirect)."""
    ok = '/visualize?chart=choropleth&grain=county&measure=%23&aggregate=count'
    assert app_module.safe_return_target(ok) == ok
    for bad in (None, '', 'visualize', 'https://evil.example/x', '//evil.example',
                '/\\evil.example', 'javascript:alert(1)', 'http:/evil'):
        assert app_module.safe_return_target(bad) is None, f'accepted {bad!r}'


def main():
    checks = [
        ('choropleth click == typed (token, dir, rows; all shapes)',
         test_choropleth_click_equals_typed),
        ('click entry through the real cache pipeline',
         test_choropleth_click_matches_production_pipeline),
        ('filter-view map values == list values (incl. alias counties)',
         test_filter_map_values_match_the_list),
        ('OR multi-select == list path; preview == apply dir',
         test_or_multiselect_matches_list_path),
        ('next-redirect override rejects non-local targets',
         test_safe_return_target),
    ]
    print('=' * 70)
    print('map-click -> filter equivalence guardrail (Phase 11)')
    print('=' * 70)

    failed = 0
    for name, fn in checks:
        try:
            fn()
            print(f'  PASS  {name}')
        except AssertionError as exc:
            failed += 1
            print(f'  FAIL  {name}: {exc}')
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f'  ERROR {name}: {type(exc).__name__}: {exc}')

    print('=' * 70)
    if failed:
        print(f'{failed} check(s) FAILED')
        return 1
    print('all checks passed — map clicks and typed filters are one path')
    return 0


if __name__ == '__main__':
    sys.exit(main())
