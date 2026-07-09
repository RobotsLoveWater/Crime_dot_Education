/* static/js/visualize.js
   Visualize workbench behaviors (VISUALIZATION_EXPANSION.md). Loaded ONLY on the
   Visualize view (visualize.html's {% block head %}), after chart.umd.min.js,
   chartjs-chart-treemap.min.js, and otherbucket.js — the same per-view convention
   as explore.js / compare.js. Jobs:
     1. live chart-type blurb under the picker + show/hide the builder fields each
        chart type actually uses (no-JS falls back to the server-rendered blurb and
        all fields visible);
     2. the chart render — Phase 4 ships the pie (share of cases by a categorical
        column), Phase 5 the treemap (two columns nested as proportional areas,
        data.get_table reshaped), both re-sliced by the reusable "Other"-cutoff
        slider (window.chartBucket) with no refetch; Phase 6 the waterfall; Phase 8
        the county choropleth (chartjs-chart-geo, filled from the same .heat-N ramp
        the crosstab uses, over a lazily-fetched vendored MN-counties TopoJSON);
        Phase 12 the scatter/bubble (two numeric columns aggregated to a lattice via
        data.get_table, case count -> bubble area);
     3. the companion value table (search + "show more") and the sidebar
        active-column sync across htmx swaps.
   Everything here is an enhancement over the server-rendered view. */

(function () {
  'use strict';

  var PAGE_SIZE = 50;   // rows shown initially in a value table
  var PAGE_STEP = 100;  // rows added per "Show more" click

  var chart = null;     // the live Chart.js instance (one chart per view)
  var kind = null;      // 'pie'|'treemap'|'waterfall'|'choropleth'|null — active payload
  var piePayload = null, pieCutoff = null;    // pie bucket payload + top-N cutoff
  var treePayload = null, treeCutoff = null;  // treemap payload + top-N parent cutoff
  var wfPayload = null;                        // waterfall year-over-year step payload
  var choroPayload = null;                     // choropleth per-county payload (Phase 8)
  var scatterPayload = null;                   // scatter/bubble lattice payload (Phase 12)

  // geo choropleth (Phase 8): plugin registration, the lazily-fetched vendored TopoJSON,
  // and the district/region dissolve all live in the shared window.GeoMap (geomap.js) —
  // one geometry implementation for this map and the Filter view's map input (Phase 11).

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  /* ---------- Live chart-type blurb + field visibility ---------- */

  function updateBlurb() {
    var select = document.querySelector('[data-viz-chart]');
    var hint = document.getElementById('viz-chart-blurb');
    if (!select || !hint) return;
    var opt = select.options[select.selectedIndex];
    var blurb = opt && opt.getAttribute('data-blurb');
    hint.textContent = blurb || hint.getAttribute('data-default') || '';
  }

  // Show only the builder fields the selected chart uses. A field carries
  // data-viz-fields="<chart ids…>"; it hides when a *ready* chart that isn't in the
  // list is selected (so the pie drops the second column / measure / aggregate), and
  // stays visible otherwise (no chart yet, or a not-yet-built type).
  function syncFieldVisibility() {
    var select = document.querySelector('[data-viz-chart]');
    var opt = select && select.options[select.selectedIndex];
    var chartId = opt ? opt.value : '';
    var status = opt ? opt.getAttribute('data-status') : '';
    document.querySelectorAll('[data-viz-fields]').forEach(function (field) {
      var list = (field.getAttribute('data-viz-fields') || '').split(/\s+/);
      field.hidden = !!chartId && status === 'ready' && list.indexOf(chartId) === -1;
    });
  }

  // Some builder fields do double duty across chart types — the two column pickers are the
  // treemap's parent/child AND the scatter's X/Y axes — so their label + hint swap to match
  // the selected chart. Each carries data-label-<id>/data-hint-<id> (with a -default
  // fallback); no-JS gets the correct text server-rendered, this keeps it in step when the
  // chart type changes without a reload. Plain text only (textContent), so no markup swap.
  function syncFieldLabels() {
    var select = document.querySelector('[data-viz-chart]');
    var opt = select && select.options[select.selectedIndex];
    var chartId = opt ? opt.value : '';
    document.querySelectorAll('[data-viz-label]').forEach(function (el) {
      var t = el.getAttribute('data-label-' + chartId) || el.getAttribute('data-label-default');
      if (t) el.textContent = t;
    });
    document.querySelectorAll('[data-viz-hint]').forEach(function (el) {
      var t = el.getAttribute('data-hint-' + chartId) || el.getAttribute('data-hint-default');
      if (t) el.textContent = t;
    });
  }

  /* ---------- Read the active payload ---------- */

  function readData() {
    piePayload = treePayload = wfPayload = choroPayload = scatterPayload = null;
    kind = null;
    var pieEl = document.getElementById('visualize-chart-data');
    var treeEl = document.getElementById('visualize-treemap-data');
    var wfEl = document.getElementById('visualize-waterfall-data');
    var choroEl = document.getElementById('visualize-choropleth-data');
    var scatterEl = document.getElementById('visualize-scatter-data');
    if (pieEl) {
      try { piePayload = JSON.parse(pieEl.textContent); kind = 'pie'; pieCutoff = piePayload.cutoff; }
      catch (e) { piePayload = null; }
    } else if (treeEl) {
      try { treePayload = JSON.parse(treeEl.textContent); kind = 'treemap'; treeCutoff = treePayload.cutoff; }
      catch (e) { treePayload = null; }
    } else if (wfEl) {
      try { wfPayload = JSON.parse(wfEl.textContent); kind = 'waterfall'; }
      catch (e) { wfPayload = null; }
    } else if (choroEl) {
      try { choroPayload = JSON.parse(choroEl.textContent); kind = 'choropleth'; }
      catch (e) { choroPayload = null; }
    } else if (scatterEl) {
      try { scatterPayload = JSON.parse(scatterEl.textContent); kind = 'scatter'; }
      catch (e) { scatterPayload = null; }
    }
  }

  /* ---------- Pie ---------- */

  function pieBucketed() {
    if (piePayload && window.chartBucket) return window.chartBucket.bucket(piePayload, pieCutoff);
    return piePayload; // no helper: fall back to the server's default bucketing
  }

  function renderPie() {
    var canvas = document.getElementById('visualize-chart');
    if (!canvas || !piePayload || typeof Chart === 'undefined') return;

    var view = pieBucketed();
    var labels = view.labels.slice();
    var counts = view.counts.slice();

    // slice colors cycle the 8-swatch chart palette; "Other" gets the muted catch-all
    var colors = labels.map(function (_, i) { return cssVar('--chart-' + (i % 8 + 1)); });
    if (view.other > 0) {
      labels.push('Other (' + view.otherValues.toLocaleString() + ' values)');
      counts.push(view.other);
      colors.push(cssVar('--color-text-faint'));
    }

    var total = view.total || counts.reduce(function (a, c) { return a + c; }, 0);
    // legend goes beside the pie on wide canvases, below it when the box is narrow
    var wide = canvas.parentNode.clientWidth >= 520;

    chart = new Chart(canvas, {
      type: 'pie',
      data: {
        labels: labels,
        datasets: [{
          data: counts,
          backgroundColor: colors,
          borderColor: cssVar('--color-surface'), // slice separators read in both themes
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // data tool, not a dashboard demo
        plugins: {
          legend: {
            position: wide ? 'right' : 'bottom',
            labels: { color: cssVar('--color-text-muted'), font: { family: cssVar('--font-base'), size: 12 } }
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var n = ctx.parsed;
                var pct = total ? (100 * n / total) : 0;
                return ctx.label + ': ' + n.toLocaleString() + ' cases (' + pct.toFixed(1) + '%)';
              }
            }
          }
        }
      }
    });
  }

  /* ---------- Treemap ---------- */

  // Re-slice the payload to a top-`cutoff` head of parent groups + an "Other" tail.
  // "Other" folds in both the parents past the cutoff and the residual tail beyond the
  // server's hard cap (tailValue/tailN/tailGroups), so it stays exact at any cutoff.
  function treemapBucket(payload, cutoff) {
    var parents = payload.parents || [];
    var n = Math.max(1, Math.min(cutoff || parents.length, parents.length));
    var head = parents.slice(0, n);
    var tail = parents.slice(n);
    var otherValue = payload.tailValue || 0;
    var otherN = payload.tailN || 0;
    var otherGroups = payload.tailGroups || 0;
    tail.forEach(function (p) { otherValue += p.value; otherN += p.n; otherGroups += 1; });
    return { head: head, otherValue: otherValue, otherN: otherN, otherGroups: otherGroups };
  }

  // Pick a readable label color for a leaf against its (theme-invariant) palette fill.
  function leafTextColor(hex) {
    var c = (hex || '').replace('#', '');
    if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
    if (c.length < 6) return '#ffffff';
    var r = parseInt(c.substr(0, 2), 16),
        g = parseInt(c.substr(2, 2), 16),
        b = parseInt(c.substr(4, 2), 16);
    var lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return lum > 0.62 ? '#1a1a1a' : '#ffffff'; // canvas contrast, not a themeable surface
  }

  function fmtValue(v) {
    if (v == null) return '–';
    return (Math.round(v * 1000) / 1000).toLocaleString();
  }

  // The case count for a drawn leaf. The plugin nests the original row under
  // _data.children (one row per leaf, since each (x, y) is unique), so n lives there —
  // _data.n itself is absent at the grouped leaf level. Falls back to _data.n if present.
  function leafN(raw) {
    var d = raw && raw._data;
    if (!d) return null;
    if (d.children && d.children.length && d.children[0].n != null) return d.children[0].n;
    return d.n != null ? d.n : null;
  }

  function renderTreemap() {
    var canvas = document.getElementById('visualize-treemap');
    if (!canvas || !treePayload || typeof Chart === 'undefined') return;

    var view = treemapBucket(treePayload, treeCutoff);
    var aggregate = treePayload.aggregate;
    var measureLabel = treePayload.measureLabel || 'cases';
    var aggLabel = aggregate.charAt(0).toUpperCase() + aggregate.slice(1);

    var palette = [];
    for (var i = 1; i <= 8; i++) palette.push(cssVar('--chart-' + i));
    var faint = cssVar('--color-text-faint');
    var surface = cssVar('--color-surface');
    var textMuted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');

    // color each parent group a distinct palette hue; "Other" is the muted catch-all
    var colorFor = {};
    view.head.forEach(function (p, idx) { colorFor[p.label] = palette[idx % 8]; });

    // flatten to the plugin's tree: one row per (parent, child); group by parent
    var tree = [];
    view.head.forEach(function (p) {
      p.children.forEach(function (c) { tree.push({ x: p.label, y: c.label, v: c.value, n: c.n }); });
    });
    if (view.otherValue > 0 && view.otherGroups > 0) {
      var otherLabel = 'Other (' + view.otherGroups.toLocaleString() +
                       ' group' + (view.otherGroups === 1 ? '' : 's') + ')';
      colorFor[otherLabel] = faint;
      tree.push({ x: otherLabel, y: '', v: view.otherValue, n: view.otherN });
    }

    // two grouping levels: x is the caption group (parent column), y is the drawn leaf
    // (second column). The plugin draws a rectangle per grouping level, so the DEEPEST
    // level (LEAF_LEVEL) holds the leaf tiles; shallower levels are the parent containers.
    var GROUPS = ['x', 'y'];
    var LEAF_LEVEL = GROUPS.length - 1;

    chart = new Chart(canvas, {
      type: 'treemap',
      data: {
        datasets: [{
          tree: tree,
          key: 'v',
          groups: GROUPS,
          spacing: 0.5,
          borderWidth: 1,
          borderColor: surface,   // separators read against both themes
          backgroundColor: function (ctx) {
            var raw = ctx.raw;
            // only fill the leaf tiles; parent-container rects stay transparent (their
            // caption + the leaves nested inside carry the meaning)
            if (!raw || raw.l !== LEAF_LEVEL || !raw._data) return 'transparent';
            return colorFor[raw._data.x] || faint;
          },
          captions: {
            display: true,
            align: 'left',
            color: textMuted,
            padding: 4,
            font: { family: fontBase, size: 12, weight: 'bold' }
          },
          labels: {
            display: true,
            overflow: 'hidden',
            font: { family: fontBase, size: 11 },
            color: function (ctx) {
              var raw = ctx.raw;
              if (!raw || raw.l !== LEAF_LEVEL || !raw._data) return textMuted;
              return leafTextColor(colorFor[raw._data.x]);
            },
            formatter: function (ctx) {
              var raw = ctx.raw;
              if (!raw || raw.l !== LEAF_LEVEL || !raw._data || !raw._data.y) return '';
              return raw._data.y;
            }
          }
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            // only the leaf tiles carry a cell; skip the transparent parent containers
            filter: function (item) { return item.raw && item.raw.l === LEAF_LEVEL; },
            callbacks: {
              title: function (items) {
                var d = items[0] && items[0].raw && items[0].raw._data;
                if (!d) return '';
                return d.y ? (d.x + ' → ' + d.y) : d.x;
              },
              label: function (ctx) {
                var d = ctx.raw && ctx.raw._data;
                if (!d) return '';
                var n = leafN(ctx.raw);
                var out = [];
                if (n != null) out.push(n.toLocaleString() + ' case' + (n === 1 ? '' : 's'));
                if (aggregate !== 'count') {
                  out.push(aggLabel + ' ' + measureLabel + ': ' + fmtValue(d.v));
                }
                return out;
              }
            }
          }
        }
      }
    });
  }

  /* ---------- Waterfall ---------- */

  // Year-over-year change in a numeric aggregate across sentencing years, drawn as Chart.js
  // floating bars (data = [start, end] per bar — core Chart.js, no plugin). The anchor bar
  // rises from 0 to the first year's value; every later bar floats from the prior year's
  // value to its own, so a bar's top sits at that year's true aggregate (the running total)
  // and the deltas sum to (last − first). Colors read from tokens each render (theme-aware).
  function renderWaterfall() {
    var canvas = document.getElementById('visualize-waterfall');
    if (!canvas || !wfPayload || typeof Chart === 'undefined') return;

    var steps = wfPayload.steps || [];
    var isCount = wfPayload.aggregate === 'count';
    var valueNoun = isCount ? 'Cases'
                            : cap(wfPayload.aggregate) + ' ' + (wfPayload.measureLabel || '');

    var accent = cssVar('--color-accent');
    var success = cssVar('--color-success');
    var danger = cssVar('--color-danger');
    var faint = cssVar('--color-text-faint');
    var muted = cssVar('--color-text-muted');
    var border = cssVar('--color-border');
    var fontBase = cssVar('--font-base');

    function barColor(dir) {
      if (dir === 'up') return success;
      if (dir === 'down') return danger;
      if (dir === 'flat') return faint;
      return accent;                              // 'base' — the anchor bar
    }

    var tickStyle = { color: muted, font: { family: fontBase, size: 12 } };

    // the running-total line is toggled by the js-only checkbox; read its state so a
    // theme re-render (which recreates the chart) preserves the user's choice
    var toggle = document.getElementById('viz-wf-running');
    var showRunning = !!(toggle && toggle.checked);

    chart = new Chart(canvas, {
      data: {
        labels: steps.map(function (s) { return s.year; }),
        datasets: [
          {
            type: 'bar',
            label: valueNoun,
            data: steps.map(function (s) { return [s.start, s.end]; }),
            backgroundColor: steps.map(function (s) { return barColor(s.direction); }),
            borderWidth: 0,
            borderSkipped: false,   // draw all four edges of a floating bar
            maxBarThickness: 48,
            order: 2
          },
          {
            type: 'line',
            label: 'Running total',
            data: steps.map(function (s) { return s.end; }),
            borderColor: muted,
            backgroundColor: muted,
            borderWidth: 2,
            pointRadius: 2,
            pointHoverRadius: 4,
            tension: 0,
            fill: false,
            hidden: !showRunning,
            order: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // data tool, not a dashboard demo
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: function (items) {
                var s = items[0] && steps[items[0].dataIndex];
                return s ? s.year : '';
              },
              label: function (ctx) {
                var s = steps[ctx.dataIndex];
                if (!s) return '';
                if (ctx.dataset.type === 'line') return 'Running total: ' + s.valueDisplay;
                var out = [valueNoun + ': ' + s.valueDisplay];
                if (s.direction !== 'base') out.push('Change: ' + s.deltaDisplay);
                return out;
              }
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: tickStyle },
          // beginAtZero keeps the anchor bar honest (bars sit at their true level)
          y: { beginAtZero: true, grid: { color: border }, ticks: tickStyle }
        }
      }
    });
  }

  /* ---------- Choropleth (Phase 8) ---------- */

  // The 8 discrete ramp colors, read from the server-rendered legend swatches (.heat-1..8 in
  // #viz-map-legend). Reading the SAME CSS tokens the crosstab heatmap uses guarantees a
  // county and a crosstab cell of equal value share a shade — and a theme flip re-reads them.
  function readRamp() {
    var ramp = [];
    for (var i = 1; i <= 8; i++) {
      var el = document.querySelector('#viz-map-legend .heat-' + i);
      ramp.push(el ? getComputedStyle(el).backgroundColor : cssVar('--color-accent'));
    }
    return ramp;
  }

  // Diagonal-hatch CanvasPattern for thin-sample geographies (Phase 10). A small-N shape is
  // filled with this texture rather than a ramp color or the grey no-data fill, so it reads as
  // uncertain instead of confidently colored. Both colors come from CSS tokens (muted lines over
  // the surface), so it themes for free — a theme flip recreates the chart, which re-reads them,
  // matching the CSS .viz-legend-lown-swatch in the legend. Same look, canvas + CSS.
  function hatchPattern(canvas, lineColor, bgColor) {
    var size = 6;
    var tile = document.createElement('canvas');
    tile.width = tile.height = size;
    var t = tile.getContext('2d');
    if (bgColor) { t.fillStyle = bgColor; t.fillRect(0, 0, size, size); }
    t.strokeStyle = lineColor;
    t.lineWidth = 1;
    // one 45° stroke plus its two corner wraps, so the lines tile seamlessly when repeated
    t.beginPath();
    t.moveTo(0, size); t.lineTo(size, 0);
    t.moveTo(-1, 1); t.lineTo(1, -1);
    t.moveTo(size - 1, size + 1); t.lineTo(size + 1, size - 1);
    t.stroke();
    return canvas.getContext('2d').createPattern(tile, 'repeat');
  }

  // Is the "Hatch thin samples" toggle on? Default true (the checkbox ships checked and no-JS
  // keeps the hatched default). Read live so a chart re-color / theme flip always reflects it.
  function hatchOn() {
    var t = document.getElementById('viz-map-hatch');
    return t ? t.checked : true;
  }

  // Apply a map-click filter (Phase 11) by POSTing the SAME fields the Filter view's form
  // (and the companion table's "Keep only" button) submits to the SAME apply route —
  // comparison=eq plus the server-shipped dataset filterValue — so a click produces a
  // history entry, chip, and cache directory byte-identical to typing the filter. `next`
  // returns the post-apply redirect to this Visualize URL (validated to a local path
  // server-side) so the drill-down loop continues on the map.
  function applyGeoFilter(applyUrl, value) {
    var form = document.createElement('form');
    form.method = 'post';
    form.action = applyUrl;
    form.hidden = true;
    [['comparison', 'eq'], ['value', value],
     ['next', location.pathname + location.search]].forEach(function (pair) {
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = pair[0];
      input.value = pair[1];
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
  }

  function renderChoropleth() {
    var canvas = document.getElementById('visualize-choropleth');
    if (!canvas || !choroPayload || typeof Chart === 'undefined' ||
        typeof ChartGeo === 'undefined' || !window.GeoMap || !GeoMap.ensure()) return;

    var payload = choroPayload;   // capture: the view may swap while the topo is in flight
    GeoMap.getTopo(payload.topoUrl).then(function (topo) {
      if (choroPayload !== payload) return;                 // a newer render superseded this
      var live = document.getElementById('visualize-choropleth');
      if (!live) return;
      var features;
      if (payload.grain && payload.grain !== 'county') {
        // district/region: merge county shapes by the crosswalk group key (10 / 4 features)
        features = GeoMap.dissolveFeatures(topo, payload.object,
                                           payload.dissolve, payload.groupLabels);
      } else {
        features = GeoMap.countyFeatures(topo, payload.object);
      }
      if (!features || !features.length) return;
      drawChoropleth(live, payload, features);
      requestAnimationFrame(function () { if (chart) chart.resize(); });
    }).catch(function () { /* topo unavailable — the county/level table stays as the fallback */ });
  }

  function drawChoropleth(canvas, payload, features) {
    if (chart) { chart.destroy(); chart = null; }   // guard against a racing async render

    var byFeature = payload.byFeature || {};
    var ramp = readRamp();
    var floor = cssVar('--color-accent-subtle');    // ramp zero-point (present, value ≤ 0)
    var noData = cssVar('--color-border');          // a county with no cases in this slice
    var sep = cssVar('--color-surface');            // county borders read in both themes
    var isCount = payload.aggregate === 'count';
    // texture for thin samples (Phase 10): built once per render so the theme flip (which
    // recreates the chart) re-reads the tokens. Distinct from `noData` (solid) and the ramp.
    var hatch = hatchPattern(canvas, cssVar('--color-text-muted'), cssVar('--color-surface'));

    // meta aligned to feature order (features[i] ↔ meta[i]); byFeature is keyed by feature name
    var meta = features.map(function (f) { return byFeature[f.properties.name] || null; });

    chart = new Chart(canvas, {
      type: 'choropleth',
      data: {
        labels: features.map(function (f) { return f.properties.name; }),
        datasets: [{
          label: payload.valueHeader,
          outline: features,          // fit the projection to the union of MN counties
          data: features.map(function (f) {
            var rec = byFeature[f.properties.name];
            return { feature: f, value: rec ? rec.value : null };
          }),
          borderColor: sep,
          borderWidth: 0.5,
          // dataset-level backgroundColor OVERRIDES the plugin's color-scale default, so the
          // fill is entirely ours: the server-computed heat step → the .heat-N token color,
          // matching the crosstab exactly (no dependence on the scale's normalization).
          backgroundColor: function (c) {
            var rec = meta[c.dataIndex];
            if (!rec) return noData;
            var on = hatchOn();
            if (rec.lowN && on) return hatch;   // thin sample → texture (the default)
            // toggle on → reliable-peak ramp (`heat`); toggle off → full-peak ramp (`heatFull`),
            // so revealed low-N groups shade on the same scale as everyone else.
            var step = on ? rec.heat : rec.heatFull;
            if (!step || step < 1) return floor;
            return ramp[Math.min(8, step) - 1];
          }
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // data tool, not a dashboard demo
        showOutline: false,
        showGraticule: false,
        // map-click → filter (Phase 11): shapes with data are clickable — the pointer
        // cursor signals it, the tooltip's last line says it, and the companion table's
        // "Keep only" buttons are the keyboard/no-JS path to the same POST.
        onHover: function (evt, elements) {
          var t = evt.native && evt.native.target;
          if (!t) return;
          var clickable = !!(payload.applyUrl && elements && elements.length &&
                             meta[elements[0].index]);
          t.style.cursor = clickable ? 'pointer' : '';
        },
        onClick: function (evt, elements) {
          if (!payload.applyUrl || !elements || !elements.length) return;
          var rec = meta[elements[0].index];   // no-data shapes have no rec → inert
          if (!rec || rec.filterValue == null) return;
          applyGeoFilter(payload.applyUrl, rec.filterValue);
        },
        scales: {
          projection: { axis: 'x', projection: 'mercator' },
          // the color scale is required by the choropleth type, but we drive colors ourselves
          // (dataset backgroundColor) and render our own legend — hide the scale's axis/legend
          color: { axis: 'x', display: false, legend: { display: false } }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: function (items) {
                var i = items[0];
                if (!i) return '';
                var f = features[i.dataIndex];
                // district/region features carry a friendly label; county features are named
                // by the county and read "<name> County" as before.
                if (payload.grain && payload.grain !== 'county') {
                  return (f.properties && (f.properties.label || f.properties.name)) || '';
                }
                return f.properties.name + ' County';
              },
              label: function (ctx) {
                var rec = meta[ctx.dataIndex];
                if (!rec) return 'No cases in this data state';
                var caseStr = rec.n.toLocaleString() + ' case' + (rec.n === 1 ? '' : 's');
                var out;
                if (rec.lowN && hatchOn()) {
                  // texture (Phase 10): state the suppression + the N; don't show a shaded value
                  out = isCount
                    ? [caseStr, 'Too few to shade (fewer than ' + payload.minN + ')']
                    : [caseStr + ' — too few to shade',
                       payload.aggLabel + ' ' + payload.measureLabel +
                       ' not shown (fewer than ' + payload.minN + ')'];
                } else {
                  // shown value: a reliable group, or a low-N one revealed by the toggle (which
                  // still gets an honest small-sample caveat so its value isn't read as solid).
                  out = isCount
                    ? [rec.display + ' case' + (rec.n === 1 ? '' : 's')]
                    : [payload.aggLabel + ' ' + payload.measureLabel + ': ' + rec.display, caseStr];
                  if (rec.lowN) out.push('Small sample — fewer than ' + payload.minN + ' cases');
                }
                if (payload.applyUrl && rec.filterValue != null) {
                  // the same affordance the table's "Keep only" button spells out
                  out.push('Click to keep only this ' + payload.grainLabel.toLowerCase());
                }
                return out;
              }
            }
          }
        }
      }
    });
  }

  // Keep the legend in step with the "Hatch thin samples" toggle: the ramp's high end swaps
  // between the reliable-peak and full-peak labels, and the "Fewer than N" chip hides when the
  // hatch is off (nothing is textured then). Reads the payload shipped with the map.
  function syncChoroplethControls() {
    if (kind !== 'choropleth' || !choroPayload) return;
    var on = hatchOn();
    var peak = document.getElementById('viz-map-peak');
    if (peak) peak.textContent = on ? choroPayload.peakDisplay : choroPayload.peakFullDisplay;
    var chip = document.getElementById('viz-map-lown-chip');
    if (chip) chip.hidden = !on;
  }

  // Wire the toggle. Flipping it re-colors the map in place (chart.update re-runs the scriptable
  // fill, which reads hatchOn() live) and re-syncs the legend — no refetch, both scales already
  // shipped. The checkbox is the source of truth, so theme flips / htmx swaps reflect it too.
  function initHatchToggle() {
    var toggle = document.getElementById('viz-map-hatch');
    if (!toggle || toggle.dataset.bound) { syncChoroplethControls(); return; }
    toggle.dataset.bound = '1';
    toggle.addEventListener('change', function () {
      if (chart && kind === 'choropleth') chart.update();
      syncChoroplethControls();
    });
    syncChoroplethControls();
  }

  /* ---------- Scatter / bubble (Phase 12) ---------- */

  // Convert a CSS color token to an rgba() string at `alpha`. getComputedStyle returns a
  // custom property's value verbatim (a hex/hsl), so we let the browser resolve it to rgb on a
  // hidden probe node, then re-wrap with alpha. Used for translucent bubble fills, so
  // overlapping lattice cells stay legible in both themes (a theme flip re-reads the token).
  function tokenRgba(token, alpha) {
    var probe = document.createElement('span');
    probe.style.color = cssVar(token);
    probe.style.position = 'absolute';
    probe.style.visibility = 'hidden';
    document.body.appendChild(probe);
    var rgb = getComputedStyle(probe).color;   // "rgb(r, g, b)" (or "rgba(...)")
    document.body.removeChild(probe);
    var m = rgb.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
    return m ? 'rgba(' + m[1] + ',' + m[2] + ',' + m[3] + ',' + alpha + ')' : rgb;
  }

  // Aggregated-lattice bubble: one dot per (x, y) cell with cases, at the numeric coordinates
  // (x, y), sized so its AREA is proportional to the case count (radius ∝ √count) — never one
  // dot per row. maxN sets the top of the size scale; a floor keeps single-case cells visible.
  // Colors read from tokens each render (theme-aware); the server draws big cells first so
  // small ones sit on top and stay clickable/legible.
  function renderScatter() {
    var canvas = document.getElementById('visualize-scatter');
    if (!canvas || !scatterPayload || typeof Chart === 'undefined') return;

    var points = scatterPayload.points || [];
    var maxN = scatterPayload.maxN || 1;
    var R_MIN = 4, R_MAX = 28;
    var data = points.map(function (p) {
      var r = maxN > 0 ? R_MIN + (R_MAX - R_MIN) * Math.sqrt(p.n / maxN) : R_MIN;
      return { x: p.x, y: p.y, r: r, n: p.n };
    });

    var fill = tokenRgba('--color-accent', 0.55);   // translucent so overlaps read
    var stroke = cssVar('--color-accent');
    var border = cssVar('--color-border');
    var xLabel = scatterPayload.xLabel || '';
    var yLabel = scatterPayload.yLabel || '';
    var axisTitle = { color: cssVar('--color-text-muted'),
                      font: { family: cssVar('--font-base'), size: 13, weight: '600' } };
    var tickStyle = { color: cssVar('--color-text-muted'),
                      font: { family: cssVar('--font-base'), size: 12 } };

    chart = new Chart(canvas, {
      type: 'bubble',
      data: {
        datasets: [{
          label: xLabel + ' × ' + yLabel,
          data: data,
          backgroundColor: fill,
          borderColor: stroke,
          borderWidth: 1,
          hoverBackgroundColor: fill,
          hoverBorderColor: stroke
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // data tool, not a dashboard demo
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: function (items) {
                var d = items[0] && items[0].raw;
                return d ? xLabel + ': ' + fmtValue(d.x) : '';
              },
              label: function (ctx) {
                var d = ctx.raw;
                if (!d) return '';
                return [yLabel + ': ' + fmtValue(d.y),
                        d.n.toLocaleString() + ' case' + (d.n === 1 ? '' : 's')];
              }
            }
          }
        },
        scales: {
          x: { type: 'linear', grid: { color: border }, ticks: tickStyle,
               title: { display: true, text: xLabel, color: axisTitle.color, font: axisTitle.font } },
          y: { type: 'linear', grid: { color: border }, ticks: tickStyle,
               title: { display: true, text: yLabel, color: axisTitle.color, font: axisTitle.font } }
        }
      }
    });
  }

  /* ---------- Render dispatch ---------- */

  function renderChart() {
    if (chart) { chart.destroy(); chart = null; }
    if (kind === 'pie') renderPie();
    else if (kind === 'treemap') renderTreemap();
    else if (kind === 'waterfall') renderWaterfall();
    else if (kind === 'choropleth') renderChoropleth();
    else if (kind === 'scatter') renderScatter();
  }

  function initSlider() {
    if (!window.chartBucket) return;
    var root = document.getElementById('visualize-view');
    if (kind === 'pie' && piePayload) {
      pieCutoff = window.chartBucket.wireSlider(root, piePayload, function (c) {
        pieCutoff = c;
        renderChart();
      });
    } else if (kind === 'treemap' && treePayload) {
      treeCutoff = window.chartBucket.wireSlider(root, treePayload, function (c) {
        treeCutoff = c;
        renderChart();
      });
    }
  }

  /* ---------- Companion value table: search + "show more" ---------- */

  // Generalized over the pie (prefix "viz-value") and treemap (prefix "viz-tree")
  // tables; whichever exists in the current fragment is wired.
  function initValueTable(prefix) {
    var table = document.getElementById(prefix + '-table');
    if (!table) return;

    var search = document.getElementById(prefix + '-search');
    var moreButton = document.getElementById(prefix + '-show-more');
    var countNote = document.getElementById(prefix + '-count');
    var rows = Array.prototype.slice.call(table.querySelectorAll('tbody tr'));
    var limit = PAGE_SIZE;
    var query = '';

    function apply() {
      var shown = 0;
      rows.forEach(function (row) {
        var visible;
        if (query) {
          visible = (row.getAttribute('data-value') || '').indexOf(query) !== -1;
        } else {
          visible = shown < limit;
        }
        if (visible) shown++;
        row.hidden = !visible;
      });

      var total = rows.length.toLocaleString();
      if (query) {
        countNote.textContent = shown.toLocaleString() + ' of ' + total + ' values match';
        if (moreButton) moreButton.hidden = true;
      } else {
        countNote.textContent = 'Showing ' + shown.toLocaleString() + ' of ' + total + ' values';
        if (moreButton) moreButton.hidden = shown >= rows.length;
      }
    }

    if (search) {
      search.addEventListener('input', function () {
        query = search.value.trim().toLowerCase();
        apply();
      });
    }
    if (moreButton) {
      moreButton.addEventListener('click', function () {
        limit += PAGE_STEP;
        apply();
      });
    }
    apply();
  }

  /* ---------- Correlation matrix column picker (Phase 13) ---------- */

  // The correlation builder is a checkbox multiselect over the numeric columns (name="cols").
  // The matrix itself is a server-rendered .heat-N table (no canvas), so this only enhances the
  // PICKER: a search filter, a live "N selected" count, a soft 2..8 cap, and a Clear button.
  // Everything degrades to a plain checkbox list that submits natively without JS.
  function initCorrPicker() {
    var list = document.getElementById('viz-corr-options');
    if (!list) return;
    var checks = Array.prototype.slice.call(list.querySelectorAll('input[type="checkbox"]'));
    var search = document.getElementById('viz-corr-search');
    var count = document.getElementById('viz-corr-count');
    var clear = document.getElementById('viz-corr-clear');
    var MIN = 2, MAX = 8;

    function selectedCount() {
      var n = 0;
      checks.forEach(function (c) { if (c.checked) n++; });
      return n;
    }

    function updateCount() {
      if (!count) return;
      var n = selectedCount();
      var msg = n + ' selected';
      if (n < MIN) msg += ' — pick at least ' + MIN;
      else if (n >= MAX) msg += ' — max ' + MAX;
      count.textContent = msg;
    }

    if (!list.dataset.bound) {
      list.dataset.bound = '1';
      list.addEventListener('change', function (e) {
        var t = e.target;
        // soft cap: refuse a pick that would exceed MAX (the server also enforces 2..8)
        if (t && t.type === 'checkbox' && t.checked && selectedCount() > MAX) {
          t.checked = false;
        }
        updateCount();
      });
    }
    if (search && !search.dataset.bound) {
      search.dataset.bound = '1';
      search.addEventListener('input', function () {
        var q = search.value.trim().toLowerCase();
        list.querySelectorAll('.corr-option').forEach(function (li) {
          li.hidden = !!q && (li.getAttribute('data-search') || '').indexOf(q) === -1;
        });
      });
    }
    if (clear && !clear.dataset.bound) {
      clear.dataset.bound = '1';
      clear.addEventListener('click', function () {
        checks.forEach(function (c) { c.checked = false; });
        updateCount();
      });
    }
    updateCount();
  }

  /* ---------- Sidebar active-column sync ---------- */

  function syncActiveColumn() {
    var view = document.querySelector('#visualize-view [data-column]');
    var code = view ? view.getAttribute('data-column') : null;
    document.querySelectorAll('.browser-item[aria-current]').forEach(function (link) {
      link.removeAttribute('aria-current');
    });
    if (code) {
      var active = document.querySelector('.browser-item[data-code="' + code + '"]');
      if (active) active.setAttribute('aria-current', 'page');
    }
  }

  /* ---------- Wiring ---------- */

  // Chart.js measures its container on creation; during an htmx swap the layout isn't
  // final until htmx settles (it also runs `show:window:top`), so a chart built on
  // afterSwap can paint blank until a manual refresh. Render on afterSettle + force one
  // resize next frame — the same lifecycle as explore.js / compare.js.
  function renderChartSafe() {
    renderChart();
    requestAnimationFrame(function () { if (chart) chart.resize(); });
  }

  function initInteractive() {
    var select = document.querySelector('[data-viz-chart]');
    if (select && !select.dataset.blurbBound) {
      select.dataset.blurbBound = '1';
      // app.js's picker enhancement dispatches a 'change' on the native <select>
      select.addEventListener('change', function () {
        updateBlurb();
        syncFieldVisibility();
        syncFieldLabels();
      });
    }
    syncFieldVisibility();
    syncFieldLabels();
    readData();
    initSlider();
    initValueTable('viz-value');   // pie table, if present
    initValueTable('viz-tree');    // treemap table, if present
    initValueTable('viz-map');     // choropleth county table, if present
    initValueTable('viz-scatter'); // scatter lattice table, if present
    initRunningTotal();          // waterfall running-total toggle, if present
    initHatchToggle();           // choropleth "hatch thin samples" toggle, if present
    initCorrPicker();            // correlation matrix column multiselect, if present
    syncActiveColumn();
  }

  // Wire the waterfall's running-total line toggle. Toggling flips the line dataset's
  // visibility in place (no re-render); the chart reads the checkbox on any full re-render
  // (theme flip / htmx swap) so the choice survives. The checkbox is the source of truth.
  function initRunningTotal() {
    var toggle = document.getElementById('viz-wf-running');
    if (!toggle || toggle.dataset.bound) return;
    toggle.dataset.bound = '1';
    toggle.addEventListener('change', function () {
      if (chart && kind === 'waterfall') {
        chart.setDatasetVisibility(1, toggle.checked);
        chart.update();
      }
    });
  }

  initInteractive();
  renderChartSafe();

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target && e.detail.target.id === 'visualize-view') {
      initInteractive();
      // picking a column from the tablet drawer should also close the drawer
      var backdrop = document.getElementById('sidebar-backdrop');
      if (backdrop && backdrop.classList.contains('open')) backdrop.click();
    }
  });
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail.target && e.detail.target.id === 'visualize-view') renderChartSafe();
  });
  document.body.addEventListener('htmx:historyRestore', function () {
    initInteractive();
    renderChartSafe();
  });
  document.addEventListener('themechange', renderChart);
})();
