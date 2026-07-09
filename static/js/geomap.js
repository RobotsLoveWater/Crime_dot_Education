/* static/js/geomap.js
   Shared client-side geography plumbing for the MN maps (Phases 8-11): registering the
   vendored chartjs-chart-geo pieces with Chart.js, fetching + memoizing the vendored
   MN-counties TopoJSON, and dissolving county geometries into district/region shapes via
   the server-shipped crosswalk. ONE implementation used by BOTH map surfaces —
   static/js/visualize.js (the choropleth) and static/js/filter.js (the Filter view's map
   input) — so the two can never disagree about geometry. Loaded after chart.umd.min.js +
   chartjs-chart-geo.min.js and before the view scripts; exposes window.GeoMap. */

(function () {
  'use strict';

  var registered = false;
  var topoData = null, topoPromise = null;

  // The geo plugin's UMD build exposes the ChartGeo global and does NOT self-register, so
  // register its controller/element/scales once, lazily (only when a map is actually drawn).
  function ensure() {
    if (registered) return true;
    if (typeof Chart === 'undefined' || typeof ChartGeo === 'undefined') return false;
    try {
      Chart.register(ChartGeo.ChoroplethController, ChartGeo.GeoFeature,
                     ChartGeo.ColorScale, ChartGeo.ProjectionScale);
    } catch (e) { return false; }
    registered = true;
    return true;
  }

  // Fetch the vendored MN-counties TopoJSON once (same-origin static file) and memoize it,
  // so theme re-renders and view swaps never re-fetch it. On failure the promise is cleared
  // so a later render can retry; the value list/table remains the no-map fallback.
  function getTopo(url) {
    if (topoData) return Promise.resolve(topoData);
    if (!topoPromise) {
      topoPromise = fetch(url, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('topo ' + r.status); return r.json(); })
        .then(function (t) { topoData = t; return t; })
        .catch(function (e) { topoPromise = null; throw e; });
    }
    return topoPromise;
  }

  // The native county features from the TopoJSON object, or null if it's malformed.
  function countyFeatures(topo, objectName) {
    var obj = topo && topo.objects && topo.objects[objectName];
    if (!obj) return null;
    return ChartGeo.topojson.feature(topo, obj).features;
  }

  // Fallback dissolve if the vendored topojson build ever lacks merge(): concatenate the
  // member county polygons into one MultiPolygon (interior borders remain, but the SHAPE
  // COUNT is still correct — 10 districts / 4 regions), so the merged grains keep working.
  function concatPolygons(topo, members) {
    var coords = [];
    members.forEach(function (g) {
      var geo = ChartGeo.topojson.feature(topo, g).geometry;
      if (!geo) return;
      if (geo.type === 'Polygon') coords.push(geo.coordinates);
      else if (geo.type === 'MultiPolygon') geo.coordinates.forEach(function (p) { coords.push(p); });
    });
    return { type: 'MultiPolygon', coordinates: coords };
  }

  // Dissolve the county geometries into per-group (district/region) shapes at runtime —
  // there is NO district/region geometry file (Phase 9). `dissolve` maps each county
  // FEATURE name to its group key; counties sharing a key are merged (shared county
  // borders removed) into one feature. `labels` gives each synthetic feature its friendly
  // name ("Judicial District 4", "Other Metro"). The synthetic feature's properties.name
  // is the SAME group-key string the callers' per-group lookups are keyed by, so fills /
  // tooltips / click handlers work unchanged.
  function dissolveFeatures(topo, objectName, dissolve, labels) {
    var tj = ChartGeo.topojson;
    var obj = topo.objects && topo.objects[objectName];
    var geoms = (obj && obj.geometries) || [];
    dissolve = dissolve || {};
    labels = labels || {};

    var byGroup = {};   // group key -> [county geometry, ...]
    var order = [];     // group keys in first-seen order (stable feature order)
    geoms.forEach(function (g) {
      var name = g.properties && g.properties.name;
      var key = dissolve[name];
      if (key == null) return;                 // county not in the crosswalk (shouldn't happen)
      if (!byGroup[key]) { byGroup[key] = []; order.push(key); }
      byGroup[key].push(g);
    });

    var canMerge = tj && typeof tj.merge === 'function';
    return order.map(function (key) {
      var members = byGroup[key];
      // topojson.merge dissolves shared arcs -> a clean group outline (no interior lines)
      var geometry = canMerge ? tj.merge(topo, members) : concatPolygons(topo, members);
      return {
        type: 'Feature',
        properties: { name: String(key), label: labels[key] || String(key) },
        geometry: geometry
      };
    });
  }

  window.GeoMap = {
    ensure: ensure,
    getTopo: getTopo,
    countyFeatures: countyFeatures,
    dissolveFeatures: dissolveFeatures
  };
})();
