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
        data.get_table, case count -> bubble area); wave 2 adds the categorical-series,
        line, distribution (histogram/ECDF), box/violin, and KDE families — the KDE
        (D2) convolves the server's binned weights client-side so its bandwidth slider
        re-smooths with no refetch;
     3. the companion value table (search + "show more") and the sidebar
        active-column sync across htmx swaps.
   Everything here is an enhancement over the server-rendered view. */

(function () {
  'use strict';

  var PAGE_SIZE = 50;   // rows shown initially in a value table
  var PAGE_STEP = 100;  // rows added per "Show more" click

  var ANIM_FRAME_MS = 900;   // animated time-series (D5): dwell per year when playing back

  var chart = null;     // the live Chart.js instance (one chart per view)
  var pairCharts = [];  // the pair-plot / SPLOM's k×k panel instances (many canvases, one chart each)
  var kind = null;      // 'pie'|'treemap'|'waterfall'|'choropleth'|'categorical-series'|'line'|'animated'|'distribution'|'kde'|'plugin'|'tiled'|null
  var piePayload = null, pieCutoff = null;    // pie bucket payload + top-N cutoff
  var treePayload = null, treeCutoff = null;  // treemap payload + top-N parent cutoff
  var wfPayload = null;                        // waterfall year-over-year step payload
  var choroPayload = null;                     // choropleth per-county payload (Phase 8)
  var scatterPayload = null;                   // scatter/bubble lattice payload (Phase 12)
  var catseriesPayload = null, catCutoff = null; // categorical-series payload + top-N cutoff (C1)
  var linePayload = null;                      // line-family payload (line/area/stacked-area/slope/bump, C2)
  var animPayload = null, animIndex = null, animTimer = null; // animated time-series payload, reveal index, playback handle (D5)
  var distPayload = null, histM = 1;           // distribution payload (histogram/ECDF) + histogram merge factor (C3)
  var bvPayload = null;                         // box/violin payload (plugin renderer, D1)
  var kdePayload = null, kdeBw = null;          // density-curve payload + current bandwidth (D2)
  var pairPayload = null;                       // pair-plot / SPLOM tiled-panel payload (D4)

  // geo choropleth (Phase 8): plugin registration, the lazily-fetched vendored TopoJSON,
  // and the district/region dissolve all live in the shared window.GeoMap (geomap.js) —
  // one geometry implementation for this map and the Filter view's map input (Phase 11).

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  /* ---------- Chart finder: selection, info box, field visibility, search ---------- */

  // The chart type is now a family-grouped card gallery of radios (name="chart") — the checked
  // one is the selection (A1). No radio checked = the blank-canvas state.
  function selectedChart() {
    return document.querySelector('input[name="chart"]:checked');
  }

  // The builder info box (#viz-info): shows / best_for / watch_out for the selected chart, read
  // from the checked card's data-info-* attributes. Repopulates in place on card change (the
  // server rendered it for the initial selection); hides when nothing is picked. The results
  // "About this chart" disclosure carries the same content server-side and isn't touched here.
  function setInfoField(box, name, text) {
    var el = box.querySelector('[data-info-field="' + name + '"]');
    if (el) el.textContent = text || '';
  }

  function updateInfoBox() {
    var box = document.getElementById('viz-info');
    if (!box) return;
    var radio = selectedChart();
    if (!radio) { box.hidden = true; return; }
    setInfoField(box, 'label', radio.getAttribute('data-info-label'));
    setInfoField(box, 'shows', radio.getAttribute('data-info-shows'));
    setInfoField(box, 'best_for', radio.getAttribute('data-info-best'));
    setInfoField(box, 'watch_out', radio.getAttribute('data-info-watch'));
    box.hidden = false;
  }

  // Show only the builder fields the selected chart uses. A field carries
  // data-viz-fields="<chart ids…>"; it hides when a *ready* chart that isn't in the
  // list is selected (so the pie drops the second column / measure / aggregate), and
  // stays visible otherwise (no chart yet, or a not-yet-built type).
  function syncFieldVisibility() {
    var radio = selectedChart();
    var chartId = radio ? radio.value : '';
    var status = radio ? radio.getAttribute('data-status') : '';
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
    var radio = selectedChart();
    var chartId = radio ? radio.value : '';
    document.querySelectorAll('[data-viz-label]').forEach(function (el) {
      var t = el.getAttribute('data-label-' + chartId) || el.getAttribute('data-label-default');
      if (t) el.textContent = t;
    });
    document.querySelectorAll('[data-viz-hint]').forEach(function (el) {
      var t = el.getAttribute('data-hint-' + chartId) || el.getAttribute('data-hint-default');
      if (t) el.textContent = t;
    });
  }

  // Chart-finder search: filter the gallery cards by data-search (label + synonyms + tags),
  // hiding families that end up empty and showing a "no matches" note — the same idiom as the
  // column-browser / value-table search. Progressive enhancement: the input is .js-only and the
  // full grouped list is the no-JS path, so no chart is ever reachable only through search.
  function initChartSearch() {
    var input = document.getElementById('viz-chart-search');
    if (!input || input.dataset.bound) return;
    input.dataset.bound = '1';
    var note = document.getElementById('viz-chart-noresults');
    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      var anyVisible = false;
      document.querySelectorAll('.viz-gallery-group').forEach(function (group) {
        var visible = 0;
        group.querySelectorAll('.viz-card-item').forEach(function (item) {
          var match = !query || (item.getAttribute('data-search') || '').indexOf(query) !== -1;
          item.hidden = !match;
          if (match) visible++;
        });
        group.hidden = visible === 0;
        // the Legacy group is a <details> collapsed by default — open it while a search matches
        // one of its cards, re-collapse when the query clears.
        if (group.tagName === 'DETAILS') group.open = !!query && visible > 0;
        if (visible) anyVisible = true;
      });
      if (note) {
        note.hidden = anyVisible;
        note.textContent = anyVisible ? '' : ('No chart types match “' + input.value.trim() + '”.');
      }
    });
  }

  /* ---------- Read the active payload ---------- */

  function readData() {
    piePayload = treePayload = wfPayload = choroPayload = scatterPayload = catseriesPayload = null;
    linePayload = distPayload = bvPayload = kdePayload = pairPayload = null;
    animPayload = null; animIndex = null;
    if (animTimer) { clearInterval(animTimer); animTimer = null; }
    kind = null;
    var pieEl = document.getElementById('visualize-chart-data');
    var treeEl = document.getElementById('visualize-treemap-data');
    var wfEl = document.getElementById('visualize-waterfall-data');
    var choroEl = document.getElementById('visualize-choropleth-data');
    var scatterEl = document.getElementById('visualize-scatter-data');
    var catEl = document.getElementById('visualize-catseries-data');
    var lineEl = document.getElementById('visualize-line-data');
    var animEl = document.getElementById('visualize-animated-data');
    var distEl = document.getElementById('visualize-distribution-data');
    var bvEl = document.getElementById('visualize-boxviolin-data');
    var kdeEl = document.getElementById('visualize-kde-data');
    var pairEl = document.getElementById('visualize-pairplot-data');
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
    } else if (catEl) {
      try { catseriesPayload = JSON.parse(catEl.textContent); kind = 'categorical-series';
            catCutoff = catseriesPayload.cutoff; }
      catch (e) { catseriesPayload = null; }
    } else if (lineEl) {
      try { linePayload = JSON.parse(lineEl.textContent); kind = 'line'; }
      catch (e) { linePayload = null; }
    } else if (animEl) {
      try { animPayload = JSON.parse(animEl.textContent); kind = 'animated'; animIndex = null; }
      catch (e) { animPayload = null; }
    } else if (distEl) {
      try { distPayload = JSON.parse(distEl.textContent); kind = 'distribution';
            histM = distPayload.defaultM || 1; }
      catch (e) { distPayload = null; }
    } else if (bvEl) {
      try { bvPayload = JSON.parse(bvEl.textContent); kind = 'plugin'; }
      catch (e) { bvPayload = null; }
    } else if (kdeEl) {
      try { kdePayload = JSON.parse(kdeEl.textContent); kind = 'kde';
            kdeBw = kdePayload.bandwidth; }
      catch (e) { kdePayload = null; }
    } else if (pairEl) {
      try { pairPayload = JSON.parse(pairEl.textContent); kind = 'tiled'; }
      catch (e) { pairPayload = null; }
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
        // hover anywhere in a year's column band, not just on the (often tiny) delta bar
        interaction: { mode: 'index', intersect: false },
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

    // the fill (heat step → ramp color, or the small-N hatch). Shared by the resting fill AND the
    // hover fill so the color never CHANGES on hover — the glow plugin below is the hover cue.
    var fillColor = function (c) {
      var rec = meta[c.dataIndex];
      if (!rec) return noData;
      var on = hatchOn();
      if (rec.lowN && on) return hatch;   // thin sample → texture (the default)
      // toggle on → reliable-peak ramp (`heat`); toggle off → full-peak ramp (`heatFull`),
      // so revealed low-N groups shade on the same scale as everyone else.
      var step = on ? rec.heat : rec.heatFull;
      if (!step || step < 1) return floor;
      return ramp[Math.min(8, step) - 1];
    };

    // hover cue: a luminous ring around the hovered shape, with NO change to its fill (designer:
    // "glow on hover instead of color change"). Re-draws the active feature under a canvas shadow
    // so a halo bleeds past its edges; the fill underneath is identical to the resting state.
    var glowColor = cssVar('--color-accent');
    var choroGlow = {
      id: 'choroGlow',
      afterDatasetsDraw: function (c) {
        var active = c.getActiveElements && c.getActiveElements();
        if (!active || !active.length) return;
        var g = c.ctx;
        active.forEach(function (a) {
          var el = a.element;
          if (!el || typeof el.draw !== 'function') return;
          g.save();
          g.shadowColor = glowColor;
          g.shadowBlur = 15;
          el.draw(g);   // two passes build the blurred shadow into a visible halo
          el.draw(g);
          g.restore();
        });
      }
    };

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
          // dataset-level backgroundColor OVERRIDES the plugin's color-scale default, so the fill
          // is entirely ours (heat step → .heat-N token color, matching the crosstab). Shared with
          // hoverBackgroundColor so the fill doesn't change on hover — choroGlow is the hover cue.
          backgroundColor: fillColor,
          hoverBackgroundColor: fillColor,
          hoverBorderColor: sep,
          hoverBorderWidth: 0.5
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
      },
      plugins: [choroGlow]
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
    return tokenRgbaFromColor(cssVar(token), alpha);
  }

  // Resolve an arbitrary CSS color string (a token value, hex, hsl…) to rgba() at `alpha`,
  // using a hidden probe so the browser normalizes it to rgb first. Shared by the translucent
  // bubble fills and the stacked-area band fills (whose colors come from the palette, not a token).
  function tokenRgbaFromColor(color, alpha) {
    var probe = document.createElement('span');
    probe.style.color = color;
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

    var fill = tokenRgba('--color-accent', 0.40);   // translucent so overlapping cells read (designer: lighter)
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

  /* ---------- Categorical-series family (Phase C1) ---------- */

  // ONE renderer for seven registry variants: bar / lollipop / dot / donut (single-series) and
  // grouped / stacked / 100%-stacked bar (two-group). The payload's `variant` {series, mark,
  // stacking} drives every drawing choice, so no chart forks a renderer
  // (CHART_LIBRARY_EXPANSION.md §5). Colors read from CSS tokens at render time (theme-aware); a
  // companion table carries the exact numbers (the a11y / no-JS twin).

  var CAT_PALETTE_SIZE = 8;

  // Distinct point marker per series, cycled with the palette. Used by the multi-series line
  // charts that carry per-line markers (slope / bump), so lines stay separable by SHAPE as well
  // as color — a redundant channel that survives grayscale and color-vision deficiencies.
  var POINT_SHAPES = ['circle', 'triangle', 'rect', 'rectRot', 'star', 'cross', 'crossRot', 'rectRounded'];

  function palette() {
    var p = [];
    for (var i = 1; i <= CAT_PALETTE_SIZE; i++) p.push(cssVar('--chart-' + i));
    return p;
  }

  // Re-slice a single-series payload to the top-`cutoff` head (+ an "Other" bucket for count).
  // COUNT reuses window.chartBucket — the exact pie/Explore path, so counts and "Other" match
  // Explore; a numeric aggregate truncates to the top-N and never fabricates an "Other".
  function catSingleView(payload, cutoff) {
    if (payload.aggregate === 'count' && window.chartBucket) {
      var v = window.chartBucket.bucket(payload, cutoff);
      var labels = v.labels.slice(), values = v.counts.slice(), ns = v.counts.slice();
      var otherIndex = -1;
      if (v.other > 0) {
        otherIndex = labels.length;
        labels.push('Other (' + v.otherValues.toLocaleString() + ' values)');
        values.push(v.other); ns.push(v.other);
      }
      return { labels: labels, values: values, ns: ns, total: v.total, otherIndex: otherIndex };
    }
    var head = payload.values || [];
    if (cutoff) head = head.slice(0, cutoff);
    return {
      labels: head.map(function (g) { return g.label; }),
      values: head.map(function (g) { return g.value; }),
      ns: head.map(function (g) { return g.n; }),
      total: payload.totalN || 0,
      otherIndex: -1
    };
  }

  function renderCatSingle(canvas, payload, variant, cutoff) {
    var view = catSingleView(payload, cutoff);
    var mark = variant.mark;
    var isCount = payload.aggregate === 'count';
    var valueNoun = isCount ? 'Cases'
                            : ((payload.aggLabel || 'Value') + ' ' + (payload.measureLabel || ''));

    if (mark === 'donut') {
      // composition ring: a pie with the middle open (share of cases), palette-cycled slices
      var pal = palette();
      var colors = view.labels.map(function (_, i) { return pal[i % CAT_PALETTE_SIZE]; });
      if (view.otherIndex >= 0) colors[view.otherIndex] = cssVar('--color-text-faint');
      var wide = canvas.parentNode.clientWidth >= 520;
      chart = new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: view.labels,
          datasets: [{
            data: view.values, backgroundColor: colors,
            borderColor: cssVar('--color-surface'), borderWidth: 2
          }]
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          cutout: '58%',
          plugins: {
            legend: {
              position: wide ? 'right' : 'bottom',
              labels: { color: cssVar('--color-text-muted'),
                        font: { family: cssVar('--font-base'), size: 12 } }
            },
            tooltip: { callbacks: { label: function (ctx) {
              var n = ctx.parsed;
              var pct = view.total ? (100 * n / view.total) : 0;
              return ctx.label + ': ' + n.toLocaleString() + ' cases (' + pct.toFixed(1) + '%)';
            } } }
          }
        }
      });
      return;
    }

    // bar / lollipop / dot — horizontal bars (long category labels read left-aligned). Lollipop
    // and dot are mark variants: a thin/absent stem plus a tip dot drawn by an inline plugin.
    var accent = cssVar('--color-accent');
    var barFill = tokenRgba('--color-accent', 0.55);   // solid enough to read on both themes
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var isLolli = mark === 'lollipop', isDot = mark === 'dot';
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    // paint the tip dot for lollipop/dot after the (thin/absent) stem bar is drawn. In a
    // horizontal bar each element's (x, y) is (value pixel, category-band center), so the dot
    // sits exactly at the bar's value end.
    var tipPlugin = {
      id: 'catseriesTips',
      afterDatasetsDraw: function (c) {
        if (!isLolli && !isDot) return;
        var g = c.ctx, meta = c.getDatasetMeta(0);
        g.save();
        g.fillStyle = accent;
        meta.data.forEach(function (el) {
          g.beginPath();
          g.arc(el.x, el.y, 5, 0, 2 * Math.PI);
          g.fill();
        });
        g.restore();
      }
    };

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: view.labels,
        datasets: [{
          label: valueNoun,
          data: view.values,
          backgroundColor: isDot ? 'transparent' : (isLolli ? border : barFill),
          borderColor: accent,
          borderWidth: (isDot || isLolli) ? 0 : 1,
          barThickness: (isLolli || isDot) ? 3 : undefined,
          maxBarThickness: (isLolli || isDot) ? 3 : 42,
          _ns: view.ns
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) { return items.length ? items[0].label : ''; },
            label: function (ctx) {
              var n = (ctx.dataset._ns || [])[ctx.dataIndex];
              if (isCount) return (n || 0).toLocaleString() + ' case' + (n === 1 ? '' : 's');
              var out = [valueNoun + ': ' + fmtValue(ctx.parsed.x)];
              if (n != null) out.push(n.toLocaleString() + ' case' + (n === 1 ? '' : 's'));
              return out;
            }
          } }
        },
        scales: {
          // bars/lollipops read from zero (honest length); a dot plot compares close values, so
          // it lets the axis fit the data instead of pinning to zero (registry watch_out).
          x: { beginAtZero: !isDot, grid: { color: border }, ticks: tick,
               title: { display: true, text: valueNoun, color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } },
          y: { grid: { display: false }, ticks: tick }
        }
      },
      plugins: [tipPlugin]
    });
  }

  function renderCatTwo(canvas, payload, variant) {
    var cats = payload.categories || [];
    var series = payload.series || [];
    var stacking = variant.stacking;
    var stacked = stacking === 'stack' || stacking === 'percent';
    var percent = stacking === 'percent';
    var isCount = payload.aggregate === 'count';
    var pal = palette();
    var faint = cssVar('--color-text-faint');
    var surface = cssVar('--color-surface');
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    // per-category totals across all series — for 100%-stacked normalization + tooltip shares
    var catTotals = cats.map(function (_, j) {
      var t = 0;
      series.forEach(function (s) { var v = s.values[j]; if (v != null) t += v; });
      return t;
    });

    var datasets = series.map(function (s, i) {
      var raw = s.values;
      var plotted = percent
        ? raw.map(function (v, j) { return v == null ? null : (catTotals[j] ? 100 * v / catTotals[j] : 0); })
        : raw.slice();
      return {
        label: s.label,
        data: plotted,
        backgroundColor: s.isOther ? faint : pal[i % CAT_PALETTE_SIZE],
        borderColor: surface,
        borderWidth: stacked ? 1 : 0,
        _ns: s.ns, _raw: raw
      };
    });

    var valueNoun = isCount ? 'Cases' : ((payload.aggLabel || 'Value') + ' ' + (payload.measureLabel || ''));

    chart = new Chart(canvas, {
      type: 'bar',
      data: { labels: cats, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom',
                    labels: { color: muted, font: { family: fontBase, size: 12 } } },
          tooltip: { callbacks: {
            label: function (ctx) {
              var ds = ctx.dataset, j = ctx.dataIndex;
              var n = (ds._ns || [])[j], raw = (ds._raw || [])[j];
              var cases = (n || 0).toLocaleString() + ' case' + (n === 1 ? '' : 's');
              if (percent) {
                var pct = ctx.parsed.y;
                return ds.label + ': ' + (pct == null ? '–' : pct.toFixed(1) + '%') + ' (' + cases + ')';
              }
              if (isCount) return ds.label + ': ' + cases;
              return ds.label + ': ' + (raw == null ? '–' : fmtValue(raw)) + ' (' + cases + ')';
            }
          } }
        },
        scales: {
          x: { stacked: stacked, grid: { display: false }, ticks: tick },
          y: {
            stacked: stacked, beginAtZero: true, grid: { color: border },
            max: percent ? 100 : undefined,
            title: { display: true, text: percent ? 'Share of group (%)' : valueNoun,
                     color: muted, font: { family: fontBase, size: 13, weight: '600' } },
            ticks: percent
              ? { color: muted, font: { family: fontBase, size: 12 },
                  callback: function (v) { return v + '%'; } }
              : tick
          }
        }
      }
    });
  }

  function renderCategoricalSeries() {
    var canvas = document.getElementById('visualize-catseries');
    if (!canvas || !catseriesPayload || typeof Chart === 'undefined') return;
    var variant = catseriesPayload.variant || {};
    if (variant.series === 'two') renderCatTwo(canvas, catseriesPayload, variant);
    else renderCatSingle(canvas, catseriesPayload, variant, catCutoff);
  }

  /* ---------- Line family (Phase C2) ---------- */

  // ONE renderer for five registry variants keyed by payload.mode: line / area (single series
  // over an ordered x column, via aggregate_by_group) and stacked-area / slope / bump (two-group,
  // via the B1 aggregate_by_two matrix; the server does the bump RANK transform, not JS). Colors
  // read from CSS tokens at render time (theme-aware); a companion table carries the exact numbers.

  // Draw each series' name at the last (and, for slope, first) PERIOD — the "hand-rolled end
  // label" the bump/slope charts use instead of a datalabels plugin. Anchored to the TERMINAL x
  // positions (index length-1 / 0), and drawn only when the series actually has a value there:
  // a category that drops out before the final period (a trailing null rank / a slope endpoint
  // present in only one period) gets no floating mid-plot label. Reads the palette color the
  // dataset was drawn in so the label matches its line.
  function endLabelPlugin(bothEnds) {
    return {
      id: 'lineEndLabels',
      afterDatasetsDraw: function (c) {
        var g = c.ctx;
        var fontBase = cssVar('--font-base');
        g.save();
        g.font = '600 12px ' + (fontBase || 'sans-serif');
        g.textBaseline = 'middle';
        c.data.datasets.forEach(function (ds, di) {
          var meta = c.getDatasetMeta(di);
          if (!meta || meta.hidden || !meta.data || !meta.data.length) return;
          var color = typeof ds.borderColor === 'string' ? ds.borderColor : cssVar('--color-text');
          g.fillStyle = color;
          var lastIdx = ds.data.length - 1;
          // label at the FINAL period, right of its point — only if the series ends there
          if (ds.data[lastIdx] != null && meta.data[lastIdx]) {
            g.textAlign = 'left';
            g.fillText(' ' + ds.label, meta.data[lastIdx].x + 4, meta.data[lastIdx].y);
          }
          // label at the FIRST period (slope), left of its point — only if the series starts there
          if (bothEnds && ds.data[0] != null && meta.data[0]) {
            g.textAlign = 'right';
            g.fillText(ds.label + ' ', meta.data[0].x - 4, meta.data[0].y);
          }
        });
        g.restore();
      }
    };
  }

  function renderLineSingle(canvas, payload, mode) {
    var pts = payload.points || [];
    var isCount = payload.aggregate === 'count';
    var valueNoun = isCount ? 'Cases'
                            : ((payload.aggLabel || 'Value') + ' ' + (payload.measureLabel || ''));
    var accent = cssVar('--color-accent');
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: pts.map(function (p) { return p.x; }),
        datasets: [{
          label: valueNoun,
          data: pts.map(function (p) { return p.value; }),
          borderColor: accent,
          backgroundColor: mode === 'area' ? tokenRgba('--color-accent', 0.18) : accent,
          borderWidth: 2,
          pointRadius: pts.length > 40 ? 0 : 3,
          pointHoverRadius: 4,
          tension: 0,
          fill: mode === 'area' ? 'origin' : false,
          _ns: pts.map(function (p) { return p.n; })
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) { return items.length ? items[0].label : ''; },
            label: function (ctx) {
              var n = (ctx.dataset._ns || [])[ctx.dataIndex];
              if (isCount) return (n || 0).toLocaleString() + ' case' + (n === 1 ? '' : 's');
              var out = [valueNoun + ': ' + fmtValue(ctx.parsed.y)];
              if (n != null) out.push(n.toLocaleString() + ' case' + (n === 1 ? '' : 's'));
              return out;
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick },
          // start at zero so the trend isn't visually exaggerated by a cropped axis (the
          // registry watch_out); area needs a zero baseline to fill against anyway.
          y: { beginAtZero: true, grid: { color: border }, ticks: tick,
               title: { display: true, text: valueNoun, color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
  }

  function renderStackedArea(canvas, payload) {
    var periods = payload.periods || [];
    var series = payload.series || [];
    var pal = palette();
    var faint = cssVar('--color-text-faint');
    var surface = cssVar('--color-surface');
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    var datasets = series.map(function (s, i) {
      var color = s.isOther ? faint : pal[i % CAT_PALETTE_SIZE];
      return {
        label: s.label,
        data: s.values.slice(),
        borderColor: color,
        backgroundColor: tokenRgbaFromColor(color, 0.55),
        borderWidth: 1,
        pointRadius: 0,
        pointHoverRadius: 3,
        tension: 0,
        fill: true,
        _ns: s.ns
      };
    });

    chart = new Chart(canvas, {
      type: 'line',
      data: { labels: periods, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom',
                    labels: { color: muted, font: { family: fontBase, size: 12 } } },
          tooltip: { callbacks: {
            label: function (ctx) {
              var n = (ctx.dataset._ns || [])[ctx.dataIndex];
              return ctx.dataset.label + ': ' + (n || 0).toLocaleString()
                     + ' case' + (n === 1 ? '' : 's');
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick },
          y: { stacked: true, beginAtZero: true, grid: { color: border }, ticks: tick,
               title: { display: true, text: 'Cases', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
  }

  function renderSlope(canvas, payload) {
    var periods = payload.periods || [];
    var series = payload.series || [];
    var isCount = payload.aggregate === 'count';
    var valueNoun = isCount ? 'Cases'
                            : ((payload.aggLabel || 'Value') + ' ' + (payload.measureLabel || ''));
    var pal = palette();
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    var datasets = series.map(function (s, i) {
      var color = pal[i % CAT_PALETTE_SIZE];
      return {
        label: s.label,
        data: s.values.slice(),
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 6,
        pointStyle: POINT_SHAPES[i % POINT_SHAPES.length],
        tension: 0,
        fill: false,
        spanGaps: false,
        _ns: s.ns
      };
    });

    chart = new Chart(canvas, {
      type: 'line',
      data: { labels: periods, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        // room for the hand-rolled category labels at both ends
        layout: { padding: { left: 96, right: 96 } },
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            title: function (items) { return items.length ? periods[items[0].dataIndex] : ''; },
            label: function (ctx) {
              var n = (ctx.dataset._ns || [])[ctx.dataIndex];
              var v = isCount ? (n || 0).toLocaleString() : fmtValue(ctx.parsed.y);
              return ctx.dataset.label + ': ' + v
                     + (isCount ? '' : ' (' + (n || 0).toLocaleString() + ' cases)');
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick, offset: true },
          y: { grid: { color: border }, ticks: tick,
               title: { display: true, text: valueNoun, color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      },
      plugins: [endLabelPlugin(true)]
    });
  }

  function renderBump(canvas, payload) {
    var periods = payload.periods || [];
    var series = payload.series || [];
    var maxRank = payload.maxRank || series.length || 1;
    var pal = palette();
    var muted = cssVar('--color-text-muted');
    var border = cssVar('--color-border');
    var fontBase = cssVar('--font-base');
    var isCount = payload.aggregate === 'count';
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    var datasets = series.map(function (s, i) {
      var color = pal[i % CAT_PALETTE_SIZE];
      return {
        label: s.label,
        data: s.ranks.slice(),          // the y value IS the rank (1 = highest)
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 6,
        pointStyle: POINT_SHAPES[i % POINT_SHAPES.length],
        tension: 0,
        spanGaps: false,
        fill: false,
        _vals: s.values, _ns: s.ns
      };
    });

    chart = new Chart(canvas, {
      type: 'line',
      data: { labels: periods, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        layout: { padding: { right: 120 } },   // room for the end labels
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            title: function (items) { return items.length ? periods[items[0].dataIndex] : ''; },
            label: function (ctx) {
              var rank = ctx.parsed.y;
              var v = (ctx.dataset._vals || [])[ctx.dataIndex];
              var n = (ctx.dataset._ns || [])[ctx.dataIndex];
              var basis = isCount ? ((n || 0).toLocaleString() + ' cases')
                                  : (v == null ? '–' : fmtValue(v));
              return ctx.dataset.label + ': #' + (rank == null ? '–' : rank) + ' (' + basis + ')';
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick, offset: true },
          // rank axis: 1 at the top (reversed), integer steps, no fractional ticks
          y: { reverse: true, min: 1, max: maxRank, grid: { color: border },
               ticks: { color: muted, font: { family: fontBase, size: 12 }, stepSize: 1,
                        precision: 0, callback: function (v) { return '#' + v; } },
               title: { display: true, text: 'Rank', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      },
      plugins: [endLabelPlugin(false)]
    });
  }

  function renderLine() {
    var canvas = document.getElementById('visualize-line');
    if (!canvas || !linePayload || typeof Chart === 'undefined') return;
    var mode = linePayload.mode;
    if (mode === 'stacked-area') renderStackedArea(canvas, linePayload);
    else if (mode === 'slope') renderSlope(canvas, linePayload);
    else if (mode === 'bump') renderBump(canvas, linePayload);
    else renderLineSingle(canvas, linePayload, mode);   // line / area
  }

  /* ---------- Animated time-series (Phase D5) ---------- */

  // A multi-line trend over the FIXED sentencing-year axis (the payload's periods) with the
  // user-picked column split into lines, plus a play/pause + year scrubber that REVEALS the
  // lines up to a year. Motion is a teaching aid: it never autoplays (the resting state shows
  // every year — the static multi-line chart, the fallback + export truth) and it honors
  // prefers-reduced-motion (no Chart.js tween, no play button). The reveal, the year scrubber,
  // and the fixed y-axis are all client-side over the same B1 per-year matrix the table carries.

  function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  // Reveal the series up to (and including) period index `upto`; later periods -> null (a gap),
  // so the line "draws" forward as the index advances. spanGaps:false keeps the break honest.
  function animRevealData(values, upto) {
    return values.map(function (v, idx) { return idx <= upto ? v : null; });
  }

  function renderAnimated() {
    var canvas = document.getElementById('visualize-animated');
    if (!canvas || !animPayload || typeof Chart === 'undefined') return;
    var periods = animPayload.periods || [];
    var series = animPayload.series || [];
    if (!periods.length || !series.length) return;

    var lastIdx = periods.length - 1;
    if (animIndex === null || animIndex > lastIdx || animIndex < 0) animIndex = lastIdx; // rest = full
    var reduced = prefersReducedMotion();
    var isCount = animPayload.aggregate === 'count';
    var valueNoun = isCount ? 'Cases'
                            : ((animPayload.aggLabel || 'Value') + ' ' + (animPayload.measureLabel || ''));
    var pal = palette();
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    var datasets = series.map(function (s, i) {
      var color = pal[i % CAT_PALETTE_SIZE];
      return {
        label: s.label,
        data: animRevealData(s.values, animIndex),
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        pointRadius: periods.length > 24 ? 0 : 3,
        pointHoverRadius: 5,
        tension: 0,
        spanGaps: false,
        _ns: s.ns
      };
    });

    // a fixed y-axis top (suggestedMax) so a revealing line doesn't rescale the axis as it grows
    // — the reveal stays comparable frame to frame. yMax is the max drawn value from the server.
    var yMax = typeof animPayload.yMax === 'number' && animPayload.yMax > 0 ? animPayload.yMax : undefined;

    chart = new Chart(canvas, {
      type: 'line',
      data: { labels: periods, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: reduced ? false : { duration: 500 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom',
                    labels: { color: muted, font: { family: fontBase, size: 12 } } },
          tooltip: { callbacks: {
            title: function (items) { return items.length ? periods[items[0].dataIndex] : ''; },
            label: function (ctx) {
              var n = (ctx.dataset._ns || [])[ctx.dataIndex];
              if (isCount) return ctx.dataset.label + ': ' + (n || 0).toLocaleString()
                                  + ' case' + (n === 1 ? '' : 's');
              var out = ctx.dataset.label + ': ' + fmtValue(ctx.parsed.y);
              if (n != null) out += ' (' + n.toLocaleString() + ' case' + (n === 1 ? '' : 's') + ')';
              return out;
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick },
          // start at zero so the trend isn't visually exaggerated by a cropped axis; the fixed
          // suggestedMax keeps the top constant through the reveal.
          y: { beginAtZero: true, suggestedMax: yMax, grid: { color: border }, ticks: tick,
               title: { display: true, text: valueNoun, color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
    updateAnimOutput();
  }

  // Sync the scrubber + its output to the current reveal index (used after a render / theme flip
  // rebuild too, so the control reflects where the reveal actually is).
  function updateAnimOutput() {
    var periods = (animPayload && animPayload.periods) || [];
    var out = document.querySelector('[data-anim-out]');
    var scrub = document.querySelector('[data-anim-scrub]');
    if (out && periods.length) out.textContent = periods[animIndex] || '';
    if (scrub && String(scrub.value) !== String(animIndex)) scrub.value = animIndex;
  }

  // Move the reveal to period index `i`, mutating the live chart in place (no rebuild). `animate`
  // gates the Chart.js tween — off under reduced motion and for the instant "jump to start" that
  // begins playback. Called by the scrubber and the play loop.
  function applyAnimIndex(i, animate) {
    if (!chart || kind !== 'animated' || !animPayload) return;
    var series = animPayload.series || [];
    var periods = animPayload.periods || [];
    var lastIdx = periods.length - 1;
    i = Math.max(0, Math.min(lastIdx, i));
    animIndex = i;
    chart.data.datasets.forEach(function (ds, k) {
      if (series[k]) ds.data = animRevealData(series[k].values, i);
    });
    chart.update((animate && !prefersReducedMotion()) ? undefined : 'none');
    updateAnimOutput();
  }

  function setPlayLabel(playing) {
    var btn = document.querySelector('[data-anim-play]');
    if (!btn) return;
    btn.textContent = playing ? '❚❚ Pause' : '▶ Play';
    btn.setAttribute('aria-pressed', playing ? 'true' : 'false');
    btn.setAttribute('aria-label', playing ? 'Pause the animation'
                                           : 'Play the year-by-year animation');
  }

  function stopAnim() {
    if (animTimer) { clearInterval(animTimer); animTimer = null; }
    setPlayLabel(false);
  }

  function startAnim() {
    if (!chart || !animPayload) return;
    var periods = animPayload.periods || [];
    var lastIdx = periods.length - 1;
    if (lastIdx < 1) return;                 // a single year has nothing to play
    applyAnimIndex(0, false);               // jump to the start instantly, then grow with the tween
    setPlayLabel(true);
    animTimer = setInterval(function () {
      if (animIndex >= lastIdx) { stopAnim(); return; }
      applyAnimIndex(animIndex + 1, true);
    }, ANIM_FRAME_MS);
  }

  // Bind the player controls once per view (re-armed per htmx swap via the dataset.bound guard,
  // like the other viz sliders). The scrubber is the keyboard-accessible core; the play button
  // is disabled under reduced motion (motion is the thing being suppressed), leaving the scrubber
  // for manual year-by-year stepping.
  function initAnimControls() {
    var reduced = prefersReducedMotion();
    var scrub = document.querySelector('[data-anim-scrub]');
    if (scrub && !scrub.dataset.bound) {
      scrub.dataset.bound = '1';
      scrub.addEventListener('input', function () {
        stopAnim();                          // a manual scrub pauses any running playback
        applyAnimIndex(parseInt(scrub.value, 10) || 0, false);
      });
    }
    var play = document.querySelector('[data-anim-play]');
    if (play && !play.dataset.bound) {
      play.dataset.bound = '1';
      if (reduced) {
        play.disabled = true;
      } else {
        play.addEventListener('click', function () {
          if (animTimer) stopAnim(); else startAnim();
        });
      }
    }
    var note = document.querySelector('[data-anim-reduced]');
    if (note) note.hidden = !reduced;
  }

  /* ---------- Distribution family (Phase C3): histogram + ECDF ---------- */

  // ONE renderer for two registry variants keyed by payload.mode: histogram (native bar over the
  // B2 bins, re-binned by the client-side merge slider) and ECDF (native stepped line over B2's
  // cumulative value counts). Both read the numpy-only B2 engine's SUMMARIZED payload — the client
  // never bins raw rows; it only merges pre-binned server counts. Colors read from CSS tokens at
  // render time (theme-aware); the companion table carries the exact numbers.

  // Merge every `m` adjacent fine bins into one coarse bin -> [{lo, hi, n}]. The EXACT twin of
  // app.py's _merge_histogram, so the chart (merged at the slider width) and the server-rendered
  // companion table (merged at the default width) agree cell-for-cell at the default. Every fine
  // bin lands in one coarse bin, so the merged counts sum to the same N — bars sum to N at any width.
  function histogramMerge(edges, counts, m) {
    m = Math.max(1, Math.round(m));
    var nFine = counts.length, out = [], lo = 0;
    while (lo < nFine) {
      var hi = Math.min(lo + m, nFine), n = 0;
      for (var i = lo; i < hi; i++) n += counts[i];
      out.push({ lo: edges[lo], hi: edges[hi], n: n });
      lo = hi;
    }
    return out;
  }

  // Compact label for a histogram bin edge: ~4 significant figures, no thousands separator.
  // Bin edges are computed boundaries, not counts, so grouping commas clutter them ("2,001.9");
  // and rounding a fractional edge (uniform bins over an integer range don't land on integers)
  // reads cleanly as its nearest value ("2002"). The exact span stays in the tooltip + the table.
  function fmtEdge(v) {
    if (v == null) return '';
    var r = Number(v.toPrecision(4));
    return r.toLocaleString(undefined, { useGrouping: false, maximumFractionDigits: 4 });
  }

  function renderHistogram(canvas, payload) {
    var bins = histogramMerge(payload.fineEdges || [], payload.fineCounts || [], histM);
    var total = payload.n || 0;
    var accent = cssVar('--color-accent');
    var accentFill = tokenRgba('--color-accent', 0.55);   // readable fill (designer note)
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: bins.map(function (b) { return fmtEdge(b.lo); }),
        datasets: [{
          label: 'Cases',
          data: bins.map(function (b) { return b.n; }),
          backgroundColor: accentFill,
          borderColor: accent,
          borderWidth: 1,
          // adjacency (no gaps) is what makes a bar chart read as a histogram
          categoryPercentage: 1, barPercentage: 1,
          _bins: bins
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) {
              var b = (items[0] && items[0].dataset._bins || [])[items[0].dataIndex];
              return b ? (fmtEdge(b.lo) + ' – ' + fmtEdge(b.hi)) : '';
            },
            label: function (ctx) {
              var n = ctx.parsed.y;
              var pct = total ? (100 * n / total) : 0;
              return n.toLocaleString() + ' case' + (n === 1 ? '' : 's') + ' (' + pct.toFixed(1) + '%)';
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick, offset: false,
               title: { display: true, text: payload.xLabel || '', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } },
          y: { beginAtZero: true, grid: { color: border }, ticks: tick,
               title: { display: true, text: 'Cases', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
  }

  function renderEcdf(canvas, payload) {
    var points = (payload.points || []).map(function (p) { return { x: p.x, y: p.y }; });
    var total = payload.n || 0;
    var accent = cssVar('--color-accent');
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    chart = new Chart(canvas, {
      type: 'line',
      data: {
        datasets: [{
          label: 'Cumulative share',
          data: points,
          borderColor: accent,
          backgroundColor: accent,
          borderWidth: 2,
          // ECDF is a right-continuous step: F holds at the current point's height until the
          // next value, then jumps — 'after' draws exactly that (horizontal then vertical).
          stepped: 'after',
          pointRadius: points.length > 60 ? 0 : 2,
          pointHoverRadius: 4,
          fill: false
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) {
              return items.length ? (payload.xLabel + ': ' + fmtValue(items[0].parsed.x)) : '';
            },
            label: function (ctx) {
              var pct = 100 * ctx.parsed.y;
              return pct.toFixed(1) + '% of cases at or below'
                     + (total ? ' (' + Math.round(ctx.parsed.y * total).toLocaleString() + ' cases)' : '');
            }
          } }
        },
        scales: {
          x: { type: 'linear', grid: { color: border }, ticks: tick,
               title: { display: true, text: payload.xLabel || '', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } },
          // cumulative share is always 0..1; show it as a percent axis
          y: { min: 0, max: 1, grid: { color: border },
               ticks: { color: muted, font: { family: fontBase, size: 12 },
                        callback: function (v) { return Math.round(v * 100) + '%'; } },
               title: { display: true, text: 'Cumulative share', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
  }

  function renderDistribution() {
    var canvas = document.getElementById('visualize-distribution');
    if (!canvas || !distPayload || typeof Chart === 'undefined') return;
    if (distPayload.mode === 'ecdf') renderEcdf(canvas, distPayload);
    else renderHistogram(canvas, distPayload);
  }

  /* ---------- Density curve / KDE (Phase D2) ---------- */

  // Clamp a bandwidth into the physical grid window the server reported (bandwidthMin/Max: the same
  // floor/cap distribution_stats applies). Below the floor the kernel is finer than the grid and
  // aliases; above the cap the Gaussian wouldn't fit the grid window and the convolution would run
  // off its end. The slider's own max stops short of the cap, but this is the belt-and-braces guard.
  function clampBw(payload, bw) {
    if (payload.bandwidthMin != null) bw = Math.max(bw, payload.bandwidthMin);
    if (payload.bandwidthMax != null) bw = Math.min(bw, payload.bandwidthMax);
    return bw;
  }

  // Convolve the server's pre-binned gridded WEIGHTS with a Gaussian kernel at `bandwidth` and
  // renormalize to unit area — the exact client twin of data._binned_kde (same linear-binned
  // weights, same kernel, same np.convolve('same') centering, same rectangle-rule renormalization),
  // so at the Silverman default it reproduces the server's B2 KDE. This is what lets the bandwidth
  // slider re-smooth with no refetch: the raw values never leave the server, only the ≤512-point
  // weight array does. O(grid·kernel); at the widest bandwidth the kernel spans ~half the grid.
  function kdeDensityFromWeights(weights, grid, bandwidth) {
    var G = grid.length;
    if (!G) return [];
    var dx = (grid[G - 1] - grid[0]) / (G - 1);
    var half = Math.ceil(4 * bandwidth / dx);
    var norm = 1 / (bandwidth * Math.sqrt(2 * Math.PI));
    var kernel = new Array(2 * half + 1);
    for (var j = -half; j <= half; j++) {
      var u = (j * dx) / bandwidth;
      kernel[j + half] = Math.exp(-0.5 * u * u) * norm;
    }
    // density[i] = sum_j weights[i-j]·kernel[j+half] — np.convolve(weights, kernel, 'same') with a
    // symmetric kernel centered at index `half` (out-of-range weights count as 0, as in full conv).
    var density = new Array(G), area = 0;
    for (var i = 0; i < G; i++) {
      var s = 0;
      var jlo = Math.max(-half, i - (G - 1));   // keep i-j <= G-1
      var jhi = Math.min(half, i);              // keep i-j >= 0
      for (var jj = jlo; jj <= jhi; jj++) s += weights[i - jj] * kernel[jj + half];
      density[i] = s;
      area += s;
    }
    area *= dx;
    if (area > 0) for (var m = 0; m < G; m++) density[m] /= area;
    return density;
  }

  // Compact bandwidth label (~3 sig figs) for the slider output — mirrors the template's %.3g.
  function fmtBw(v) {
    return Number(v.toPrecision(3)).toLocaleString(undefined, { maximumSignificantDigits: 3 });
  }

  function renderKde() {
    var canvas = document.getElementById('visualize-kde');
    if (!canvas || !kdePayload || typeof Chart === 'undefined') return;
    var grid = kdePayload.grid, weights = kdePayload.weights;
    if (!grid || !weights) return;   // degenerate (no spread) — the histogram companion carries it
    var bw = clampBw(kdePayload, kdeBw == null ? kdePayload.bandwidth : kdeBw);
    var density = kdeDensityFromWeights(weights, grid, bw);
    var pts = grid.map(function (g, i) { return { x: g, y: density[i] }; });
    var domain = kdePayload.domain || null;
    var accent = cssVar('--color-accent');
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    chart = new Chart(canvas, {
      type: 'line',
      data: {
        datasets: [{
          label: 'Density',
          data: pts,
          borderColor: accent,
          backgroundColor: tokenRgba('--color-accent', 0.30),
          borderWidth: 2,
          pointRadius: 0, pointHoverRadius: 0,
          tension: 0,
          fill: 'origin'         // a filled area reads as density mass under the curve
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) {
              return items.length ? (kdePayload.xLabel + ': ' + fmtValue(items[0].parsed.x)) : '';
            },
            // density is in 1/x-units — an estimate, not a count; report it as relative height only.
            label: function (ctx) { return 'Relative density ' + Number(ctx.parsed.y.toPrecision(3)); }
          } }
        },
        scales: {
          // clip the axis to the observed data range so the KDE's 4-bandwidth padding tails (density
          // where there are no cases) are trimmed — the honest choice, matching the violin's clip.
          x: { type: 'linear',
               min: domain ? domain.min : undefined, max: domain ? domain.max : undefined,
               grid: { color: border }, ticks: tick,
               title: { display: true, text: kdePayload.xLabel || '', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } },
          // density magnitude isn't directly interpretable (the note tells the reader to read
          // relative height), so keep the axis + gridlines but drop the numeric labels.
          y: { beginAtZero: true, grid: { color: border }, ticks: { display: false },
               title: { display: true, text: 'Density', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
  }

  /* ---------- Box plot & violin (Phase D1) ---------- */

  // #rrggbb -> rgba(r,g,b,a). The --chart-N palette tokens are all 6-digit hex, so a violin body
  // can be filled translucent (its inner spine/box/median read through) without a color library.
  function hexRgba(hex, a) {
    var h = (hex || '').replace('#', '');
    if (h.length !== 6) return hex;   // non-hex token (shouldn't happen) -> use as-is, opaque
    var r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }

  // Box: the vendored @sgratzl/chartjs-chart-boxplot 'boxplot' type (self-registered on load, like
  // the treemap plugin) fed B2's PRECOMPUTED five-number summary + Tukey whiskers. No raw per-row
  // arrays cross the wire — outliers are counts (shown in the tooltip/table), never drawn as points.
  function renderBox(canvas, payload) {
    // if the plugin didn't load, leave the companion table as the fallback (same defensive posture
    // as the geo choropleth's ChartGeo guard).
    if (typeof ChartBoxPlot === 'undefined') return;
    var groups = payload.groups || [];
    var accent = cssVar('--color-accent');
    var accentFill = tokenRgba('--color-accent', 0.40);   // readable box fill; the accent median still reads over it
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var fontBase = cssVar('--font-base');
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    // ONE precomputed box per group. min/max are the whisker ends the element draws to; whiskerMin/
    // Max are supplied explicitly so the plugin uses B2's fences verbatim instead of re-deriving
    // them. outliers: [] -- we have COUNTS only, so no dots are drawn (the count is in the tooltip).
    var boxData = groups.map(function (g) {
      return { min: g.whiskerLow, max: g.whiskerHigh,
               whiskerMin: g.whiskerLow, whiskerMax: g.whiskerHigh,
               q1: g.q1, median: g.median, q3: g.q3, mean: g.mean, outliers: [] };
    });

    chart = new Chart(canvas, {
      type: 'boxplot',
      data: {
        labels: groups.map(function (g) { return g.label; }),
        datasets: [{
          label: payload.valueLabel || '',
          data: boxData,
          // one accent scheme for every box -- group identity is the x-axis label. A solid accent
          // outline + median over the subtle-accent fill stays legible; a per-group fill in the box
          // element's single color would hide the median line (the element draws it in borderColor).
          backgroundColor: accentFill,
          borderColor: accent,
          borderWidth: 1.5,
          outlierRadius: 0,   // no raw outliers to draw
          itemRadius: 0,      // no per-item points
          meanRadius: 0,      // the median is the mark; the mean lives in the tooltip/table
          _groups: groups
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) { return items.length ? items[0].label : ''; },
            label: function (ctx) {
              var g = (ctx.dataset._groups || [])[ctx.dataIndex] || {};
              var out = [(g.n || 0).toLocaleString() + ' case' + (g.n === 1 ? '' : 's'),
                         'Median ' + fmtValue(g.median),
                         'Q1–Q3 ' + fmtValue(g.q1) + ' – ' + fmtValue(g.q3),
                         'Whiskers ' + fmtValue(g.whiskerLow) + ' – ' + fmtValue(g.whiskerHigh)];
              if (g.nOutliers) out.push(g.nOutliers.toLocaleString() + ' outlier'
                + (g.nOutliers === 1 ? '' : 's') + ' beyond 1.5·IQR');
              return out;
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick,
               title: payload.grouped
                 ? { display: true, text: payload.groupLabel || '', color: muted,
                     font: { family: fontBase, size: 13, weight: '600' } }
                 : { display: false } },
          y: { grid: { color: border }, ticks: tick,
               title: { display: true, text: payload.valueLabel || '', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      }
    });
  }

  // Violin: hand-rolled (the D1 spike chose this over the plugin's violin type for cross-group-
  // comparable widths, exact token theming, and a guaranteed no-raw-array payload). A mirrored area
  // whose half-width at each value is proportional to B2's binned KDE density on the SHARED grid,
  // scaled by the max density across all groups so the shapes are comparable; an inner spine
  // (whisker-to-whisker), a slim IQR box, and a median tick carry the summary the smooth outline
  // can't. Drawn on a Chart.js bar shell (invisible bars) so it gets the axes, tooltip, and resize.
  function renderViolin(canvas, payload) {
    var groups = payload.groups || [];
    var grid = payload.grid || null;
    var domain = payload.domain || null;
    var border = cssVar('--color-border');
    var muted = cssVar('--color-text-muted');
    var surface = cssVar('--color-surface');
    var fontBase = cssVar('--font-base');
    var pal = palette();
    var tick = { color: muted, font: { family: fontBase, size: 12 } };

    // shared max density across groups -> comparable widths (each KDE integrates to ~1, so a
    // concentrated group reads tall+narrow, a spread group short+wide, all scaled to one max).
    var globalMax = 0;
    groups.forEach(function (g) {
      if (g.density) g.density.forEach(function (v) { if (v > globalMax) globalMax = v; });
    });

    var yMin = domain ? domain.min : 0, yMax = domain ? domain.max : 1;

    var violinPlugin = {
      id: 'violinBody',
      afterDatasetsDraw: function (c) {
        var g = c.ctx, xS = c.scales.x, yS = c.scales.y, area = c.chartArea;
        var n = groups.length;
        var bandW = n > 1 ? Math.abs(xS.getPixelForValue(1) - xS.getPixelForValue(0))
                          : (area.right - area.left);
        var maxHalf = (bandW / 2) * 0.85;
        var textColor = cssVar('--color-text');
        g.save();
        // clip to the plot area so the KDE's 4-bandwidth tails beyond the data range are trimmed
        // flat (an honest violin -- no density shown outside the observed min/max).
        g.beginPath();
        g.rect(area.left, area.top, area.right - area.left, area.bottom - area.top);
        g.clip();
        groups.forEach(function (grp, i) {
          var cx = xS.getPixelForValue(i);
          var color = pal[i % CAT_PALETTE_SIZE];
          var density = grp.density;
          if (density && grid && grid.length && globalMax > 0) {
            g.beginPath();
            var started = false;
            for (var k = 0; k < grid.length; k++) {
              var y = yS.getPixelForValue(grid[k]);
              var half = maxHalf * (density[k] / globalMax);
              if (!started) { g.moveTo(cx + half, y); started = true; }
              else g.lineTo(cx + half, y);
            }
            for (var k2 = grid.length - 1; k2 >= 0; k2--) {
              var y2 = yS.getPixelForValue(grid[k2]);
              var half2 = maxHalf * (density[k2] / globalMax);
              g.lineTo(cx - half2, y2);
            }
            g.closePath();
            g.fillStyle = hexRgba(color, 0.45);
            g.fill();
            g.lineWidth = 1.5; g.strokeStyle = color; g.stroke();
          }
          // inner spine (whiskers) + IQR box + median tick -- drawn for every group, so a degenerate
          // group with no KDE still shows its median/quartiles.
          var yWl = yS.getPixelForValue(grp.whiskerLow), yWh = yS.getPixelForValue(grp.whiskerHigh);
          var yQ1 = yS.getPixelForValue(grp.q1), yQ3 = yS.getPixelForValue(grp.q3);
          var yMed = yS.getPixelForValue(grp.median);
          var boxHalf = Math.min(maxHalf * 0.16, 7);
          g.strokeStyle = muted; g.lineWidth = 1;
          g.beginPath(); g.moveTo(cx, yWl); g.lineTo(cx, yWh); g.stroke();
          var boxTop = Math.min(yQ1, yQ3), boxH = Math.abs(yQ3 - yQ1) || 1;
          g.fillStyle = surface; g.fillRect(cx - boxHalf, boxTop, boxHalf * 2, boxH);
          g.strokeRect(cx - boxHalf, boxTop, boxHalf * 2, boxH);
          g.beginPath(); g.moveTo(cx - boxHalf, yMed); g.lineTo(cx + boxHalf, yMed);
          g.strokeStyle = textColor; g.lineWidth = 2; g.stroke();
        });
        g.restore();
      }
    };

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: groups.map(function (g) { return g.label; }),
        // invisible bars (median value = a sane hover target) establish the category axis + give an
        // index tooltip; the violin bodies are painted by the plugin above.
        datasets: [{ label: payload.valueLabel || '',
                     data: groups.map(function (g) { return g.median; }),
                     backgroundColor: 'transparent', borderWidth: 0, _groups: groups }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) { return items.length ? items[0].label : ''; },
            label: function (ctx) {
              var grp = (ctx.dataset._groups || [])[ctx.dataIndex] || {};
              return [(grp.n || 0).toLocaleString() + ' case' + (grp.n === 1 ? '' : 's'),
                      'Median ' + fmtValue(grp.median),
                      'Q1–Q3 ' + fmtValue(grp.q1) + ' – ' + fmtValue(grp.q3)];
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: tick,
               title: payload.grouped
                 ? { display: true, text: payload.groupLabel || '', color: muted,
                     font: { family: fontBase, size: 13, weight: '600' } }
                 : { display: false } },
          y: { min: yMin, max: yMax, grid: { color: border }, ticks: tick,
               title: { display: true, text: payload.valueLabel || '', color: muted,
                        font: { family: fontBase, size: 13, weight: '600' } } }
        }
      },
      plugins: [violinPlugin]
    });
  }

  function renderPlugin() {
    var canvas = document.getElementById('visualize-boxviolin');
    if (!canvas || !bvPayload || typeof Chart === 'undefined') return;
    if (bvPayload.mode === 'violin') renderViolin(canvas, bvPayload);
    else renderBox(canvas, bvPayload);
  }

  /* ---------- Pair plot / SPLOM (Phase D4) ---------- */

  // Bare axis config for a SPLOM mini-panel: no ticks/labels/legend (the panels are small and read
  // as SHAPES; the correlation-matrix companion table carries the numbers), faint gridlines only.
  function pairScales(border) {
    var ax = { type: 'linear', grid: { color: border, drawTicks: false },
               ticks: { display: false }, border: { display: false } };
    return { x: ax, y: { type: 'linear', grid: { color: border, drawTicks: false },
                         ticks: { display: false }, border: { display: false } } };
  }

  // Off-diagonal panel: the 2D-binned scatter (B3) as bubbles at each non-empty bin's center, area
  // ∝ case count (√count, like renderScatter) — never one dot per row. xLabel/yLabel drive the
  // tooltip so a hovered cell still names its columns + count.
  function makePairScatter(canvas, panel, xLabel, yLabel, fill, stroke, border) {
    var points = panel.points || [];
    var maxN = panel.maxCount || 1;
    var R_MIN = 1.5, R_MAX = 9;
    var data = points.map(function (p) {
      var r = maxN > 0 ? R_MIN + (R_MAX - R_MIN) * Math.sqrt(p.n / maxN) : R_MIN;
      return { x: p.x, y: p.y, r: r, n: p.n };
    });
    return new Chart(canvas, {
      type: 'bubble',
      data: { datasets: [{ data: data, backgroundColor: fill, borderColor: stroke,
                           borderWidth: 0.5, hoverBackgroundColor: fill, hoverBorderColor: stroke }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) {
              var d = items[0] && items[0].raw;
              return d ? (xLabel + ': ' + fmtValue(d.x)) : '';
            },
            label: function (ctx) {
              var d = ctx.raw;
              if (!d) return '';
              return [yLabel + ': ' + fmtValue(d.y),
                      d.n.toLocaleString() + ' case' + (d.n === 1 ? '' : 's')];
            }
          } }
        },
        scales: pairScales(border)
      }
    });
  }

  // Diagonal panel: the column's own histogram (B2) as adjacent bars over the shared bin edges.
  // Category axis with categoryPercentage/barPercentage = 1 for gapless bars (the same idiom as
  // renderHistogram); ticks/labels are hidden like the off-diagonal panels, and the bin range +
  // count ride in the tooltip via _bars.
  function makePairHist(canvas, panel, label, accent, fillColor, border) {
    var edges = panel.edges || [];
    var counts = panel.counts || [];
    var bars = counts.map(function (c, i) { return { lo: edges[i], hi: edges[i + 1], n: c }; });
    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels: bars.map(function (_, i) { return i; }),
        datasets: [{ data: bars.map(function (b) { return b.n; }),
                     backgroundColor: fillColor, borderColor: accent, borderWidth: 0.5,
                     categoryPercentage: 1, barPercentage: 1, _bars: bars }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: {
            title: function (items) {
              var b = (items[0] && items[0].dataset._bars || [])[items[0].dataIndex];
              return b ? (fmtValue(b.lo) + ' – ' + fmtValue(b.hi)) : '';
            },
            label: function (ctx) {
              var n = ctx.parsed.y;
              return label + ': ' + n.toLocaleString() + ' case' + (n === 1 ? '' : 's');
            }
          } }
        },
        scales: {
          x: { grid: { display: false }, ticks: { display: false }, border: { display: false } },
          y: { beginAtZero: true, grid: { color: border, drawTicks: false },
               ticks: { display: false }, border: { display: false } }
        }
      }
    });
  }

  function renderPairplot() {
    if (!pairPayload || typeof Chart === 'undefined') return;
    var labels = pairPayload.labels || [];
    var accent = cssVar('--color-accent');
    var histFill = tokenRgba('--color-accent', 0.55);   // diagonal histograms — readable (designer note)
    var border = cssVar('--color-border');
    var fill = tokenRgba('--color-accent', 0.70);        // off-diagonal bubbles — denser so small panels read
    var stroke = cssVar('--color-accent');
    (pairPayload.grid || []).forEach(function (line) {
      line.forEach(function (panel) {
        var canvas = document.getElementById('viz-pair-' + panel.row + '-' + panel.col);
        if (!canvas) return;
        if (panel.diag) {
          pairCharts.push(makePairHist(canvas, panel, labels[panel.row] || '',
                                       accent, histFill, border));
        } else {
          // cell (row, col): x = column[col], y = column[row] (standard SPLOM orientation)
          pairCharts.push(makePairScatter(canvas, panel, labels[panel.col] || '',
                                          labels[panel.row] || '', fill, stroke, border));
        }
      });
    });
  }

  /* ---------- Render dispatch ---------- */

  // Data-driven dispatch keyed by the active payload's kind — which mirrors each registry
  // entry's `renderer` key server-side (VIZ_CHART_TYPES in app.py). Adding a chart registers
  // its render fn here (+ a VIZ_CHART_TYPES entry); there is no per-chart `if` branch to grow.
  // A registry entry with no canvas render (correlation → server-rendered .heat-N table) has
  // no key here, so renderChart is a no-op for it. Function declarations are hoisted, so the
  // map can reference them regardless of their textual position above.
  var RENDERERS = {
    pie: renderPie,
    treemap: renderTreemap,
    waterfall: renderWaterfall,
    choropleth: renderChoropleth,
    scatter: renderScatter,
    'categorical-series': renderCategoricalSeries,
    line: renderLine,
    animated: renderAnimated,
    distribution: renderDistribution,
    kde: renderKde,
    plugin: renderPlugin,
    tiled: renderPairplot
  };

  // The pair plot draws MANY Chart instances (one per SPLOM panel) instead of the single `chart`;
  // tear them all down before a re-render (theme flip / htmx swap) so canvases aren't leaked.
  function destroyPairCharts() {
    pairCharts.forEach(function (c) { c.destroy(); });
    pairCharts = [];
  }

  function renderChart() {
    // stop any running playback before we tear the chart down (a theme flip / htmx swap rebuilds
    // it); the animated reveal position (animIndex) survives so the rebuild resumes where it was.
    if (animTimer) { clearInterval(animTimer); animTimer = null; setPlayLabel(false); }
    if (chart) { chart.destroy(); chart = null; }
    destroyPairCharts();
    var render = kind && RENDERERS[kind];
    if (render) render();
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
    } else if (kind === 'categorical-series' && catseriesPayload &&
               catseriesPayload.variant && catseriesPayload.variant.series === 'single') {
      catCutoff = window.chartBucket.wireSlider(root, catseriesPayload, function (c) {
        catCutoff = c;
        renderChart();
      });
    }
  }

  // Histogram bin slider (C3): the same "re-slice a server payload with no refetch" idiom as the
  // "Other"-cutoff slider, but re-binning instead of re-bucketing. The slider picks a target bin
  // COUNT; it snaps to a merge factor m so the coarse bins stay uniform (histogramMerge groups m
  // fine bins), and the output shows the count that actually results. renderChart() re-reads histM.
  function initHistSlider() {
    var slider = document.querySelector('[data-hist-bins]');
    if (!slider || slider.dataset.bound) return;   // absent for the ECDF / non-distribution views
    slider.dataset.bound = '1';
    var out = document.querySelector('[data-hist-bins-out]');
    var nFine = (distPayload && distPayload.nFine) || 1;
    var raf = null;
    slider.addEventListener('input', function () {
      var desiredK = Math.max(1, parseInt(slider.value, 10) || 1);
      var m = Math.min(Math.max(Math.round(nFine / desiredK), 1), nFine);
      var actualK = Math.ceil(nFine / m);
      histM = m;
      if (out) out.textContent = actualK;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(function () { renderChart(); });
    });
  }

  // KDE bandwidth slider (D2): the same "re-slice a server payload with no refetch" idiom as the
  // histogram bin slider, but re-CONVOLVING the gridded weights at the slider's bandwidth rather
  // than re-binning. The slider carries an absolute bandwidth; kdeDensityFromWeights redraws from
  // it. renderChart() re-reads kdeBw, so the choice survives a theme flip / re-render too.
  function initKdeSlider() {
    var slider = document.querySelector('[data-kde-bw]');
    if (!slider || slider.dataset.bound) return;   // absent for non-KDE (or degenerate) views
    slider.dataset.bound = '1';
    var out = document.querySelector('[data-kde-bw-out]');
    var raf = null;
    slider.addEventListener('input', function () {
      var v = parseFloat(slider.value);
      if (!isFinite(v)) return;
      kdeBw = clampBw(kdePayload || {}, v);
      if (out) out.textContent = fmtBw(kdeBw);
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(function () { renderChart(); });
    });
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
    var field = list.closest('.viz-corr-field');
    var MIN = 2;

    // The subset picker serves two charts with different caps (correlation 8, pair plot 5). Read
    // the cap for the currently-CHECKED chart off the fieldset's data-cap-<id> (data-cap is the
    // server-rendered default), so switching chart cards client-side re-caps without a reload.
    // The server enforces the real bound either way.
    function currentCap() {
      var radio = document.querySelector('input[name="chart"]:checked');
      var id = radio ? radio.value : '';
      var byId = field && field.getAttribute('data-cap-' + id);
      var v = parseInt(byId || (field && field.getAttribute('data-cap')) || '8', 10);
      return isFinite(v) ? v : 8;
    }

    function selectedCount() {
      var n = 0;
      checks.forEach(function (c) { if (c.checked) n++; });
      return n;
    }

    function updateCount() {
      if (!count) return;
      var n = selectedCount();
      var max = currentCap();
      var msg = n + ' selected';
      if (n < MIN) msg += ' — pick at least ' + MIN;
      else if (n >= max) msg += ' — max ' + max;
      count.textContent = msg;
    }

    if (!list.dataset.bound) {
      list.dataset.bound = '1';
      list.addEventListener('change', function (e) {
        var t = e.target;
        // soft cap: refuse a pick that would exceed the current chart's cap (server also enforces)
        if (t && t.type === 'checkbox' && t.checked && selectedCount() > currentCap()) {
          t.checked = false;
        }
        updateCount();
      });
    }
    // re-run the count (and thus the cap message) when the chart card changes, so the max tracks
    // correlation ↔ pair plot without a reload.
    var gallery = document.querySelector('.viz-chart-field');
    if (gallery && !gallery.dataset.capBound) {
      gallery.dataset.capBound = '1';
      gallery.addEventListener('change', function (e) {
        if (e.target && e.target.name === 'chart') updateCount();
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
    requestAnimationFrame(function () {
      if (chart) chart.resize();
      pairCharts.forEach(function (c) { c.resize(); });   // the SPLOM's panels, if any
    });
  }

  function initInteractive() {
    // one delegated listener on the gallery fieldset catches every card's radio change; the
    // fieldset is rebuilt on each htmx swap, so the dataset.bound guard re-arms per view.
    var field = document.querySelector('.viz-chart-field');
    if (field && !field.dataset.bound) {
      field.dataset.bound = '1';
      field.addEventListener('change', function (e) {
        if (e.target && e.target.name === 'chart') {
          updateInfoBox();
          syncFieldVisibility();
          syncFieldLabels();
        }
      });
    }
    initChartSearch();
    updateInfoBox();
    syncFieldVisibility();
    syncFieldLabels();
    readData();
    initSlider();
    initHistSlider();              // histogram bin slider, if present
    initKdeSlider();              // KDE bandwidth slider, if present
    initAnimControls();          // animated time-series play/pause + scrubber, if present
    initValueTable('viz-value');   // pie table, if present
    initValueTable('viz-tree');    // treemap table, if present
    initValueTable('viz-map');     // choropleth county table, if present
    initValueTable('viz-scatter'); // scatter lattice table, if present
    initValueTable('viz-cat');     // categorical-series companion table, if present
    initValueTable('viz-line');    // line-family companion table, if present
    initValueTable('viz-anim');    // animated time-series companion table, if present
    initValueTable('viz-dist');    // distribution (histogram/ECDF) companion table, if present
    initValueTable('viz-bv');      // box/violin companion table, if present
    initValueTable('viz-kde');     // KDE underlying-histogram companion table, if present
    initValueTable('viz-mosaic');  // mosaic companion crosstab table, if present
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
