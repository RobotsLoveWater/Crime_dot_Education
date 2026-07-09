/* static/js/filter.js
   Filter workbench behaviors (Phase 4, STYLEGUIDE.md "Components"):
   - column-browser search (sidebar): filters the server-rendered list, like explore.js
   - active-column highlight kept in sync across htmx view swaps
   - categorical filter: value-list search, "select shown" / "clear" bulk actions
   - MOC chooser/stepper: option-table search
   - geographic map input (Phase 11): on county/district/region, clicking a map shape
     toggles the SAME checkbox / fills the SAME numeric input a hand-picked filter uses —
     the map never builds its own filter, so the applied token and cache dir are identical
     to the list path by construction. Needs chart.umd + chartjs-chart-geo + geomap.js
     (loaded by filter.html only); on pages without them (MOC) the map code no-ops.
   The live "~N cases match" preview is pure htmx (hx-get on the preview element), so it
   needs no JS here. Everything below is enhancement — the server-rendered forms and plain
   links work without it (no preview, plain submit). */

(function () {
  'use strict';

  /* ---------- Column-browser search (sidebar, persistent across view swaps) ---------- */

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

  function syncActiveColumn() {
    var view = document.querySelector('#filter-view [data-column]');
    var code = view ? view.getAttribute('data-column') : null;

    document.querySelectorAll('.browser-item[aria-current]').forEach(function (link) {
      link.removeAttribute('aria-current');
    });
    if (code) {
      var active = document.querySelector('.browser-item[data-code="' + code + '"]');
      if (active) active.setAttribute('aria-current', 'page');
    }
  }

  /* ---------- Generic list/table search (value list, MOC options, MOC categories) ---------- */

  function bindListSearch(inputId, containerId) {
    var input = document.getElementById(inputId);
    var container = document.getElementById(containerId);
    if (!input || !container || input.dataset.bound) return;
    input.dataset.bound = '1';

    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      container.querySelectorAll('[data-search]').forEach(function (item) {
        item.hidden = !!query && (item.getAttribute('data-search') || '').indexOf(query) === -1;
      });
    });
  }

  /* ---------- Categorical: "select shown" / "clear" bulk actions ---------- */

  function initCategorical() {
    var list = document.getElementById('value-check-list');
    if (!list) return;
    var form = document.getElementById('categorical-filter-form');

    function fireChange() {
      // programmatic .checked changes don't emit 'change'; nudge the htmx preview
      if (form) form.dispatchEvent(new Event('change', { bubbles: true }));
    }

    var selectAll = document.getElementById('cat-select-all');
    if (selectAll && !selectAll.dataset.bound) {
      selectAll.dataset.bound = '1';
      selectAll.addEventListener('click', function () {
        list.querySelectorAll('.value-check').forEach(function (item) {
          if (item.hidden) return; // only the currently-visible (searched) values
          var box = item.querySelector('input[type="checkbox"]');
          if (box) box.checked = true;
        });
        fireChange();
      });
    }

    var clear = document.getElementById('cat-clear');
    if (clear && !clear.dataset.bound) {
      clear.dataset.bound = '1';
      clear.addEventListener('click', function () {
        list.querySelectorAll('input[type="checkbox"]').forEach(function (box) {
          box.checked = false;
        });
        fireChange();
      });
    }
  }

  /* ---------- Geographic map input (Phase 11) ---------- */
  // The map is an INPUT DEVICE for the form beside it, never a token builder: clicking a
  // shape toggles the same checkbox (county/region, 'multi' mode) or fills the same
  // numeric value input (district, 'single' mode) a hand-picked filter uses, then fires
  // the form's change event so the live "~N would match" preview refreshes through the
  // existing htmx trigger. The payload's per-shape `value` is the server-shipped DATASET
  // value (the checkbox's exact value attribute — "LeSueur", not the map's "Le Sueur";
  // "4.0" for a district), so the eventual POST is byte-identical to the list path.

  var mapChart = null;      // the live Chart.js selection-map instance
  var mapPayload = null;    // the #filter-map-data payload for the current column
  var mapFeatures = null;   // the drawn features (kept for theme re-renders)

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function cssEscape(value) {
    return (window.CSS && CSS.escape) ? CSS.escape(value) : value.replace(/"/g, '\\"');
  }

  function mapForm() {
    return document.getElementById('categorical-filter-form') ||
           document.getElementById('numeric-filter-form');
  }

  // Is a shape's dataset value currently selected in the form? Read live from the form —
  // the form is the single source of truth (hand edits recolor the map, not vice versa).
  function mapSelected(rec) {
    if (!mapPayload) return false;
    if (mapPayload.mode === 'multi') {
      var box = document.querySelector(
        '#value-check-list input[name="value"][value="' + cssEscape(rec.value) + '"]');
      return !!(box && box.checked);
    }
    // single (numeric): highlight only under "equal to" — under gt/lt the input value
    // isn't "this district", and a lit shape would misread as the kept geography
    var compare = document.getElementById('filter-comparison');
    if (compare && compare.value !== 'eq') return false;
    var input = document.getElementById('filter-value');
    return !!(input && input.value !== '' && Number(input.value) === Number(rec.value));
  }

  function mapClick(featureKey) {
    var rec = mapPayload && mapPayload.values && mapPayload.values[featureKey];
    if (!rec) return;                          // no cases in the current slice — inert
    var form = mapForm();
    if (mapPayload.mode === 'multi') {
      var box = document.querySelector(
        '#value-check-list input[name="value"][value="' + cssEscape(rec.value) + '"]');
      if (!box) return;
      box.checked = !box.checked;
    } else {
      var input = document.getElementById('filter-value');
      var compare = document.getElementById('filter-comparison');
      if (!input) return;
      var already = compare && compare.value === 'eq' &&
                    input.value !== '' && Number(input.value) === Number(rec.value);
      if (compare) compare.value = 'eq';       // a map click means "equal to this one"
      input.value = already ? '' : rec.value;  // click the lit shape again to clear
    }
    if (mapChart) mapChart.update();           // scriptable fill re-reads the form state
    // programmatic edits don't emit 'change'; nudge the htmx preview like initCategorical
    if (form) form.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function drawFilterMap(canvas, features) {
    if (mapChart) { mapChart.destroy(); mapChart = null; }

    var payload = mapPayload;
    var accent = cssVar('--color-accent');         // selected
    var subtle = cssVar('--color-accent-subtle');  // selectable (has cases)
    var noCases = cssVar('--color-border');        // inert (no cases in this slice)
    var sep = cssVar('--color-surface');           // shape borders read in both themes

    // recs aligned to feature order; a feature's key is its properties.name (the TopoJSON
    // county name, or the dissolved group key — exactly how payload.values is keyed)
    var recs = features.map(function (f) { return payload.values[f.properties.name] || null; });

    mapChart = new Chart(canvas, {
      type: 'choropleth',
      data: {
        labels: features.map(function (f) { return f.properties.name; }),
        datasets: [{
          outline: features,          // fit the projection to the union of the shapes
          data: features.map(function (f, i) {
            return { feature: f, value: recs[i] ? recs[i].count : 0 };
          }),
          borderColor: sep,
          borderWidth: 0.5,
          // selection state, not a value ramp: the map is an input, so it colors by
          // "selected / selectable / no cases" rather than shading a statistic
          backgroundColor: function (c) {
            var rec = recs[c.dataIndex];
            if (!rec) return noCases;
            return mapSelected(rec) ? accent : subtle;
          }
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        showOutline: false,
        showGraticule: false,
        onHover: function (evt, elements) {
          var t = evt.native && evt.native.target;
          if (!t) return;
          t.style.cursor = (elements && elements.length && recs[elements[0].index])
            ? 'pointer' : '';
        },
        onClick: function (evt, elements) {
          if (!elements || !elements.length) return;
          var f = features[elements[0].index];
          if (f) mapClick(f.properties.name);
        },
        scales: {
          projection: { axis: 'x', projection: 'mercator' },
          // required by the choropleth type, but the fill is ours — hide it
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
                var rec = recs[i.dataIndex];
                if (rec) return rec.label;   // the list's spelling, not the map's
                var f = features[i.dataIndex];
                return (f.properties && (f.properties.label || f.properties.name)) || '';
              },
              label: function (ctx) {
                var rec = recs[ctx.dataIndex];
                if (!rec) return 'No cases in your current data state';
                return [
                  rec.count.toLocaleString() + ' case' + (rec.count === 1 ? '' : 's'),
                  mapSelected(rec) ? 'Selected — click to clear' : 'Click to select'
                ];
              }
            }
          }
        }
      }
    });
  }

  // Recolor the map when the form changes by hand (checkbox clicks, typing a district
  // number) — the form is the source of truth and the map follows it.
  function bindMapFormSync() {
    var form = mapForm();
    if (form && !form.dataset.mapBound) {
      form.dataset.mapBound = '1';
      form.addEventListener('change', function () {
        if (mapChart) mapChart.update();
      });
    }
    var input = document.getElementById('filter-value');
    if (input && !input.dataset.mapBound) {
      input.dataset.mapBound = '1';
      // 'input' keeps the highlight live while typing (change only fires on blur)
      input.addEventListener('input', function () {
        if (mapChart) mapChart.update();
      });
    }
  }

  function initFilterMap() {
    var dataEl = document.getElementById('filter-map-data');
    var canvas = document.getElementById('filter-map-canvas');
    if (!dataEl || !canvas) {
      // view swapped to a non-geography column — drop any stale chart
      if (mapChart) { mapChart.destroy(); mapChart = null; }
      mapPayload = null;
      mapFeatures = null;
      return;
    }
    if (typeof Chart === 'undefined' || typeof ChartGeo === 'undefined' ||
        !window.GeoMap || !GeoMap.ensure()) return;

    try { mapPayload = JSON.parse(dataEl.textContent); } catch (e) { mapPayload = null; return; }

    var payload = mapPayload;   // capture: the view may swap while the topo is in flight
    GeoMap.getTopo(payload.topoUrl).then(function (topo) {
      if (mapPayload !== payload) return;               // a newer init superseded this
      var live = document.getElementById('filter-map-canvas');
      if (!live) return;
      var features = (payload.grain === 'county')
        ? GeoMap.countyFeatures(topo, payload.object)
        : GeoMap.dissolveFeatures(topo, payload.object, payload.dissolve, payload.groupLabels);
      if (!features || !features.length) return;
      mapFeatures = features;
      drawFilterMap(live, features);
      requestAnimationFrame(function () { if (mapChart) mapChart.resize(); });
      bindMapFormSync();
    }).catch(function () { /* map unavailable — the value list stays the whole path */ });
  }

  // theme flip: recreate the chart so the fill re-reads the CSS tokens (topo + features
  // are memoized, so this is cheap and never refetches)
  function rethemeFilterMap() {
    var canvas = document.getElementById('filter-map-canvas');
    if (canvas && mapPayload && mapFeatures) drawFilterMap(canvas, mapFeatures);
  }

  /* ---------- Wiring ---------- */

  function initView() {
    syncActiveColumn();
    bindListSearch('cat-value-search', 'value-check-list');
    bindListSearch('moc-option-search', 'moc-option-table');
    bindListSearch('moc-code-search', 'moc-code-table');
    initCategorical();
  }

  initBrowserSearch();
  initView();
  initFilterMap();

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target && e.detail.target.id === 'filter-view') {
      initView();
      // picking a column from the tablet drawer should also close the drawer
      var backdrop = document.getElementById('sidebar-backdrop');
      if (backdrop && backdrop.classList.contains('open')) backdrop.click();
    }
  });

  // the map (a chart) renders on afterSettle + next-frame resize, like every other chart
  // (explore.js / compare.js / visualize.js) — the swapped layout must settle first, or it
  // can paint blank until a refresh. The preview fragment swap targets #filter-preview,
  // not #filter-view, so preview refreshes never re-init the map.
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail.target && e.detail.target.id === 'filter-view') initFilterMap();
  });

  // htmx restored a cached page snapshot (browser Back): re-init the enhancements
  document.body.addEventListener('htmx:historyRestore', function () {
    initView();
    initFilterMap();
  });
  document.addEventListener('themechange', rethemeFilterMap);
})();
