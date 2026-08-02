/* static/js/compare.js
   Compare (crosstab) behaviors (Phase 3, STYLEGUIDE.md "Heatmap cells" + "Charts"):
   - stat toggle: all four stats already sit in the markup, so switching is pure
     show/hide (data-stat on the table) plus re-shading the heatmap — no refetch
   - heatmap: swaps each cell's .heat-N class from its data-heat-<stat> attribute
   - grouped-bar companion chart for small tables; colors read from CSS tokens at
     render time, re-rendered on themechange and htmx swaps/history restores
   Everything here is an enhancement — without JS the table shows every stat
   stacked and keeps the server-rendered count heatmap. */

(function () {
  'use strict';

  var chart = null; // the live Chart.js instance (one chart per view)

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // The palette modes use stable textures alongside hue for grouped bars. Standard and Custom
  // remain visually unchanged; CanvasPattern is native and needs no new chart dependency.
  var ACCESSIBILITY_PALETTES = ['universal', 'protan', 'deutan', 'tritan', 'mono'];
  function usesAccessibilityCues() {
    return ACCESSIBILITY_PALETTES.indexOf(document.documentElement.getAttribute('data-palette')) !== -1;
  }

  function cuePattern(canvas, color, index) {
    if (!usesAccessibilityCues()) return color;
    var tile = document.createElement('canvas');
    tile.width = tile.height = 12;
    var g = tile.getContext('2d');
    g.fillStyle = color;
    g.fillRect(0, 0, 12, 12);
    g.strokeStyle = cssVar('--color-surface');
    g.fillStyle = cssVar('--color-surface');
    g.lineWidth = 1.5;
    var cue = index % 8;
    g.beginPath();
    if (cue === 0 || cue === 4) { g.moveTo(-3, 12); g.lineTo(12, -3); }
    if (cue === 1 || cue === 4) { g.moveTo(-3, 0); g.lineTo(12, 15); }
    if (cue === 2 || cue === 6) { g.moveTo(3, 0); g.lineTo(3, 12); g.moveTo(9, 0); g.lineTo(9, 12); }
    if (cue === 3 || cue === 6) { g.moveTo(0, 3); g.lineTo(12, 3); g.moveTo(0, 9); g.lineTo(12, 9); }
    if (cue === 5) { g.arc(3, 3, 1.25, 0, 2 * Math.PI); g.arc(9, 9, 1.25, 0, 2 * Math.PI); }
    if (cue === 7) { g.fillRect(1, 1, 3, 3); g.fillRect(7, 7, 3, 3); }
    if (cue !== 5 && cue !== 7) g.stroke(); else g.fill();
    return canvas.getContext('2d').createPattern(tile, 'repeat') || color;
  }

  function currentStat() {
    var table = document.getElementById('crosstab');
    if (!table) return 'n';
    return table.getAttribute('data-stat') || table.getAttribute('data-default-stat') || 'n';
  }

  function applyHeat(table, stat) {
    table.querySelectorAll('td.cell').forEach(function (cell) {
      for (var step = 1; step <= 8; step++) cell.classList.remove('heat-' + step);
      var heat = parseInt(cell.getAttribute('data-heat-' + stat), 10);
      if (heat > 0) cell.classList.add('heat-' + heat);
    });
  }

  function renderChart(stat) {
    if (chart) { chart.destroy(); chart = null; }

    var canvas = document.getElementById('compare-chart');
    var dataEl = document.getElementById('compare-chart-data');
    if (!canvas || !dataEl || typeof Chart === 'undefined') return;

    var payload;
    try { payload = JSON.parse(dataEl.textContent); } catch (e) { return; }
    var values = payload.stats[stat];
    if (!values) return;

    var tickStyle = {
      color: cssVar('--color-text-muted'),
      font: { family: cssVar('--font-base'), size: 12 }
    };

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: payload.labels,
        datasets: payload.columns.map(function (name, index) {
          return {
            label: String(name),
            data: values[index],
            backgroundColor: cuePattern(canvas, cssVar('--chart-' + (index % 8 + 1)), index),
            borderColor: cssVar('--chart-' + (index % 8 + 1)),
            borderWidth: usesAccessibilityCues() ? 1 : 0,
            borderRadius: 2,
            maxBarThickness: 32
          };
        })
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false, // data tool, not a dashboard demo
        plugins: {
          legend: { labels: tickStyle },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                if (ctx.parsed.y === null) return ctx.dataset.label + ': no data';
                var value = ctx.parsed.y.toLocaleString();
                return ctx.dataset.label + ': ' + value + (stat === 'n' ? ' cases' : '');
              }
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: tickStyle },
          y: { beginAtZero: true, grid: { color: cssVar('--color-border') }, ticks: tickStyle }
        }
      }
    });
  }

  function setStat(stat) {
    var table = document.getElementById('crosstab');
    if (!table) return;

    table.setAttribute('data-stat', stat);
    applyHeat(table, stat);
    document.querySelectorAll('#stat-toggle .segmented-item').forEach(function (button) {
      button.setAttribute('aria-pressed', button.getAttribute('data-stat') === stat ? 'true' : 'false');
    });
    renderChart(stat);
  }

  function initView() {
    var table = document.getElementById('crosstab');
    if (!table) return;

    var toggle = document.getElementById('stat-toggle');
    if (toggle && !toggle.dataset.bound) {
      toggle.dataset.bound = '1';
      toggle.addEventListener('click', function (e) {
        var button = e.target.closest('[data-stat]');
        if (button) setStat(button.getAttribute('data-stat'));
      });
    }

    setStat(table.getAttribute('data-default-stat') || 'n');
  }

  initView();

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target && e.detail.target.id === 'compare-view') initView();
  });

  // Chart.js measures its container on creation; during an htmx swap the layout
  // isn't final until htmx settles (it also runs `show:window:top`), so a chart
  // built on afterSwap can paint blank until a manual refresh. Re-render it once
  // the swap has settled (stable size) + resize next frame — like a full load.
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail.target && e.detail.target.id === 'compare-view') {
      renderChart(currentStat());
      requestAnimationFrame(function () { if (chart) chart.resize(); });
    }
  });

  // htmx restored a cached page snapshot (browser Back): canvas state is lost, re-init
  document.body.addEventListener('htmx:historyRestore', initView);

  // charts re-read the CSS tokens when the theme flips (theme.js fires this)
  document.addEventListener('themechange', function () { renderChart(currentStat()); });
})();
