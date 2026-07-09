# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# geo.py
# the geographic foundation for the Visualize choropleth (VISUALIZATION_EXPANSION.md
# §4 / _PROMPTS.md Phase 7): the vendored MN-counties TopoJSON, the dataset->feature
# county-name reconciliation, and the startup coverage assertion.
#
# Pure module: stdlib only, no Flask and no pandas (mirrors lessons.py / classroom.py).
# The county->district and county->region crosswalks are DATA-derived and therefore live
# in cache.py (next to the base-DataFrame singleton) -- this module is names + geometry.
#
# Why a name join at all: the dataset carries county *names* (no FIPS), and those names
# are spelled slightly differently from a standard TopoJSON ("LeSueur" vs "Le Sueur",
# "Lac Qui Parle" vs "Lac qui Parle"). Every dataset county MUST resolve to exactly one
# map feature or a choropleth would silently drop a county -- so resolution is layered
# (exact -> explicit alias -> normalized) and app.py asserts full coverage at startup.

import os
import re
import json

# The vendored MN-counties TopoJSON (see static/js/vendor/VERSIONS.md for provenance --
# derived from us-atlas@3 counties-10m.json, MN features only, arcs pruned). __file__-
# relative so it resolves regardless of the process CWD.
_HERE = os.path.dirname(os.path.abspath(__file__))
TOPOJSON_PATH = os.path.join(_HERE, 'static', 'geo', 'mn-counties-topo.json')

# Flask url_for('static', ...) path for the same file, for templates/JS (Phase 8).
TOPOJSON_STATIC = 'geo/mn-counties-topo.json'

# The TopoJSON object name holding the 87 county geometries.
TOPOJSON_OBJECT = 'counties'

# Explicit dataset-name -> feature-name overrides for the genuinely irregular spellings.
# These are also caught by _normalize() below, but the table documents intent and is a
# belt-and-suspenders guard if the vendored geometry is ever re-sourced with different
# casing/spacing. Keys are the DATASET spelling; values are the TopoJSON feature name.
#   - "LeSueur"       -> "Le Sueur"       (dataset drops the space)
#   - "Lac Qui Parle" -> "Lac qui Parle"  (dataset title-cases the "qui")
#   - "Saint Louis"   -> "St. Louis"      (defensive: the dataset uses "St. Louis" today,
#                                          but a re-export could spell it out)
COUNTY_ALIASES = {
    'LeSueur': 'Le Sueur',
    'Lac Qui Parle': 'Lac qui Parle',
    'Saint Louis': 'St. Louis',
}

# module-level memo of the parsed TopoJSON + derived name index (loaded once per process)
_TOPO = None
_FEATURE_NAMES = None       # list of feature county names, in TopoJSON order
_NORMALIZED_INDEX = None    # {_normalize(feature name): feature name}


def _normalize(name):
    # Canonical join key: casefold + drop everything but letters/digits. Collapses the
    # spacing/casing differences ("LeSueur"/"Le Sueur" -> "lesueur"; "Lac Qui Parle"/
    # "Lac qui Parle" -> "lacquiparle"; "St. Louis" -> "stlouis"). It does NOT bridge
    # "Saint" vs "St." -- that spelling difference is what COUNTY_ALIASES covers.
    return re.sub(r'[^a-z0-9]', '', str(name).casefold())


def _load():
    # Parse the vendored TopoJSON once and build the normalized feature-name index.
    # Raises loudly if the file is missing/corrupt or the expected object is absent --
    # a broken geometry file is a hard error, never a silent empty map.
    global _TOPO, _FEATURE_NAMES, _NORMALIZED_INDEX
    if _TOPO is not None:
        return

    with open(TOPOJSON_PATH, 'r', encoding='utf-8') as handle:
        topo = json.load(handle)

    try:
        geometries = topo['objects'][TOPOJSON_OBJECT]['geometries']
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            "MN counties TopoJSON is malformed (no objects.%s.geometries): %s"
            % (TOPOJSON_OBJECT, TOPOJSON_PATH)
        ) from exc

    names = [g['properties']['name'] for g in geometries]

    index = {}
    for name in names:
        key = _normalize(name)
        if key in index and index[key] != name:
            # two distinct features collapsing to one normalized key would make an
            # "exactly one feature" match ambiguous -- fail rather than pick silently.
            raise RuntimeError(
                "MN counties TopoJSON has ambiguous feature names %r and %r "
                "(both normalize to %r)" % (index[key], name, key)
            )
        index[key] = name

    _TOPO = topo
    _FEATURE_NAMES = names
    _NORMALIZED_INDEX = index


def feature_names():
    # The county names present in the vendored map, in TopoJSON order.
    _load()
    return list(_FEATURE_NAMES)


def topology():
    # The parsed TopoJSON object (for Phase 8 to serialize to the choropleth).
    _load()
    return _TOPO


def resolve_county(name):
    # Map a dataset county name to its TopoJSON feature name, or None if unmatched.
    # Layered: exact feature name -> explicit alias -> normalized match.
    _load()
    if name in _NORMALIZED_INDEX.values():
        return name
    alias = COUNTY_ALIASES.get(name)
    if alias is not None and alias in _NORMALIZED_INDEX.values():
        return alias
    return _NORMALIZED_INDEX.get(_normalize(name))


def county_feature_map(counties):
    # Resolve an iterable of dataset county names to {county: feature name}, plus the
    # list of names that failed to resolve. Pure -- callers decide whether to raise.
    mapping = {}
    unmatched = []
    for county in counties:
        feature = resolve_county(county)
        if feature is None:
            unmatched.append(county)
        else:
            mapping[county] = feature
    return mapping, unmatched


def assert_county_coverage(counties):
    # Startup guard (VISUALIZATION_EXPANSION.md §4, risk row 2): every dataset county
    # must map to exactly one map feature, or fail loudly. Two failure modes:
    #   1. an unmatched county (name the alias table / geometry doesn't cover), and
    #   2. two counties colliding onto the same feature (an alias bug).
    # Returns the {county: feature} mapping on success.
    counties = list(counties)
    mapping, unmatched = county_feature_map(counties)

    if unmatched:
        raise RuntimeError(
            "MN county name join failed: %d dataset county(ies) have no map feature: %s. "
            "Add them to geo.COUNTY_ALIASES or check the vendored TopoJSON."
            % (len(unmatched), ', '.join(repr(c) for c in sorted(unmatched)))
        )

    # each feature should be claimed by at most one dataset county (a many->one collapse
    # would mean two counties share a shape -- an alias mistake, not a real geography)
    collisions = {}
    for county, feature in mapping.items():
        collisions.setdefault(feature, []).append(county)
    dupes = {f: cs for f, cs in collisions.items() if len(cs) > 1}
    if dupes:
        detail = '; '.join('%r <- %s' % (f, ', '.join(repr(c) for c in cs))
                           for f, cs in sorted(dupes.items()))
        raise RuntimeError(
            "MN county name join is ambiguous: multiple dataset counties map to one "
            "feature: %s" % detail
        )

    return mapping
