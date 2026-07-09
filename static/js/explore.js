/* static/js/explore.js
   Explore workbench behaviors (Phase 2, STYLEGUIDE.md "Charts" + "Components"):
   - distribution bar chart: Chart.js, colors read from CSS tokens at render time,
     re-rendered on themechange and after htmx view swaps
   - column-browser search (sidebar): filters the server-rendered list
   - value table: client-side search + "show more" pagination
   - active-column highlight kept in sync across htmx swaps; drawer auto-close
   Everything here is an enhancement — the server-rendered page works without it. */

(function () {
  'use strict';

  var PAGE_SIZE = 50;   // rows shown initially in the value table
  var PAGE_STEP = 100;  // rows added per "Show more" click
  var chart = null;         // the live Chart.js instance (one chart per view)
  var chartPayload = null;  // the reusable bucket payload for the active column
  var chartCutoff = null;   // current top-N cutoff (driven by the "Other" slider)

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  /* ---------- Distribution chart ---------- */

  // Read the embedded bucket payload once per view swap; the slider re-slices it
  // client-side (window.chartBucket) so dragging never refetches.
  function readChartData() {
    var dataEl = document.getElementById('explore-chart-data');
    if (!dataEl) { chartPayload = null; return; }
    try { chartPayload = JSON.parse(dataEl.textContent); }
    catch (e) { chartPayload = null; return; }
    chartCutoff = chartPayload.cutoff;
  }

  function bucketed() {
    if (chartPayload && window.chartBucket) return window.chartBucket.bucket(chartPayload, chartCutoff);
    return chartPayload; // no helper loaded: fall back to the server's default bucketing
  }

  function renderChart() {
    if (chart) { chart.destroy(); chart = null; }

    var canvas = document.getElementById('explore-chart');
    if (!canvas || !chartPayload || typeof Chart === 'undefined') return;

    var view = bucketed();
    var labels = view.labels.slice();
    var counts = view.counts.slice();
    var barColor = cssVar('--chart-1');
    var colors = labels.map(function () { return barColor; });
    if (view.other > 0) {
      labels.push('Other (' + view.otherValues.toLocaleString() + ' values)');
      counts.push(view.other);
      colors.push(cssVar('--color-text-faint')); // visually distinct catch-all bucket
    }

    // long category labels read better on a horizontal axis (STYLEGUIDE.md "Charts")
    var horizontal = labels.some(function (l) { return String(l).length > 10; });
    canvas.parentNode.style.height = horizontal
      ? (labels.length * 26 + 64) + 'px'
      : '320px';

    var tickStyle = {
      color: cssVar('--color-text-muted'),
      font: { family: cssVar('--font-base'), size: 12 }
    };
    var countAxis = {
      beginAtZero: true,
      grid: { color: cssVar('--color-border') },
      ticks: Object.assign({ precision: 0 }, tickStyle)
    };
    var labelAxis = {
      grid: { display: false },
      ticks: Object.assign({ autoSkip: false }, tickStyle)
    };

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ data: counts, backgroundColor: colors, borderRadius: 2, maxBarThickness: 40 }]
      },
      options: {
        indexAxis: horizontal ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // data tool, not a dashboard demo
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var n = horizontal ? ctx.parsed.x : ctx.parsed.y;
                return n.toLocaleString() + ' cases';
              }
            }
          }
        },
        scales: horizontal ? { x: countAxis, y: labelAxis } : { x: labelAxis, y: countAxis }
      }
    });
  }

  /* ---------- Column-browser search (persistent across view swaps) ---------- */

  function initBrowserSearch() {
    var input = document.getElementById('column-search');
    if (!input || input.dataset.bound) return;
    input.dataset.bound = '1';

    var emptyNote = document.getElementById('browser-empty');

    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      var anyVisible = false;

      document.querySelectorAll('.browser-group').forEach(function (group) {
        var visible = 0;
        group.querySelectorAll('li').forEach(function (item) {
          var match = !query || (item.getAttribute('data-search') || '').indexOf(query) !== -1;
          item.hidden = !match;
          if (match) visible++;
        });
        group.hidden = visible === 0;
        // groups start collapsed; a search opens the ones with matches and an
        // empty query collapses them all again (back to the resting state)
        group.open = !!(query && visible);
        if (visible) anyVisible = true;
      });

      if (emptyNote) emptyNote.hidden = anyVisible;
    });
  }

  /* ---------- Active column highlight ---------- */

  function syncActiveColumn() {
    var view = document.querySelector('#explore-view [data-column]');
    var code = view ? view.getAttribute('data-column') : null;

    document.querySelectorAll('.browser-item[aria-current]').forEach(function (link) {
      link.removeAttribute('aria-current');
    });
    if (code) {
      var active = document.querySelector('.browser-item[data-code="' + code + '"]');
      if (active) active.setAttribute('aria-current', 'page');
    }
  }

  /* ---------- Value table: search + "show more" ---------- */

  function initValueTable() {
    var table = document.getElementById('value-table');
    if (!table) return;

    var search = document.getElementById('value-search');
    var moreButton = document.getElementById('value-show-more');
    var countNote = document.getElementById('value-count');
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
        moreButton.hidden = true;
      } else {
        countNote.textContent = 'Showing ' + shown.toLocaleString() + ' of ' + total + ' values';
        moreButton.hidden = shown >= rows.length;
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

  /* ---------- Wiring ---------- */

  // Chart.js measures its container when it's created. During an htmx swap the
  // layout isn't final until htmx settles (it also runs `show:window:top`), so a
  // chart built on afterSwap can measure a transient size and paint blank until a
  // manual refresh. Render it on afterSettle (layout + scroll finalized) and force
  // one resize on the next frame — this makes the swap path behave like a full load.
  function renderChartSafe() {
    renderChart();
    requestAnimationFrame(function () { if (chart) chart.resize(); });
  }

  // Wire the "Other"-cutoff slider (when present) to re-render the bar on drag.
  function initSlider() {
    if (!chartPayload || !window.chartBucket) return;
    var root = document.getElementById('explore-view');
    chartCutoff = window.chartBucket.wireSlider(root, chartPayload, function (c) {
      chartCutoff = c;
      renderChart();
    });
  }

  function initInteractive() {
    initValueTable();
    syncActiveColumn();
    readChartData();
    initSlider();
  }

  initBrowserSearch();
  initInteractive();
  renderChartSafe();

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target && e.detail.target.id === 'explore-view') {
      initInteractive();
      // picking a column from the tablet drawer should also close the drawer
      var backdrop = document.getElementById('sidebar-backdrop');
      if (backdrop && backdrop.classList.contains('open')) backdrop.click();
    }
  });

  // render the chart once the swap has settled (stable container size)
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail.target && e.detail.target.id === 'explore-view') renderChartSafe();
  });

  // htmx restored a cached page snapshot (browser Back): canvas state is lost, re-init
  document.body.addEventListener('htmx:historyRestore', function () {
    initInteractive();
    renderChartSafe();
  });

  // charts re-read the CSS tokens when the theme flips (theme.js fires this)
  document.addEventListener('themechange', renderChart);
})();
