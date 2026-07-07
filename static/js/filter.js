/* static/js/filter.js
   Filter workbench behaviors (Phase 4, STYLEGUIDE.md "Components"):
   - column-browser search (sidebar): filters the server-rendered list, like explore.js
   - active-column highlight kept in sync across htmx view swaps
   - categorical filter: value-list search, "select shown" / "clear" bulk actions
   - MOC chooser/stepper: option-table search
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

  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target && e.detail.target.id === 'filter-view') {
      initView();
      // picking a column from the tablet drawer should also close the drawer
      var backdrop = document.getElementById('sidebar-backdrop');
      if (backdrop && backdrop.classList.contains('open')) backdrop.click();
    }
  });

  // htmx restored a cached page snapshot (browser Back): re-init the enhancements
  document.body.addEventListener('htmx:historyRestore', initView);
})();
