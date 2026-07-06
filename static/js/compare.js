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
            backgroundColor: cssVar('--chart-' + (index % 8 + 1)),
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

  // htmx restored a cached page snapshot (browser Back): canvas state is lost, re-init
  document.body.addEventListener('htmx:historyRestore', initView);

  // charts re-read the CSS tokens when the theme flips (theme.js fires this)
  document.addEventListener('themechange', function () { renderChart(currentStat()); });
})();
