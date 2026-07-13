/* static/js/palette.js
   The global "Chart colors" control. Partner of the inline palette guard in
   layout.html <head>, which applies the saved mode + custom colors before first
   paint; this file owns the dialog UI and switching.

   Three modes, persisted to localStorage:
     - "default" — the --chart-1..8 tokens from tokens.css (attribute removed).
     - "cb"      — colorblind-safe tokens (tokens.css [data-palette="cb"], theme-aware).
     - "custom"  — eight user hexes, applied as inline --chart-N on <html> (they win
                   over the tokens).

   A change re-reads nothing on the server; every chart redraws by re-reading its CSS
   color tokens on the "themechange" event (see explore.js / compare.js / visualize.js),
   so a palette swap dispatches that same signal to get an identical, no-refetch redraw. */

(function () {
  'use strict';

  var root = document.documentElement;

  // The Default palette hexes, mirrored from tokens.css --chart-1..8 (kept in sync there).
  // Used to seed the custom pickers and to back "Reset to default colors".
  var DEFAULT_COLORS = ['#2563eb', '#f97316', '#059669', '#dc2626',
                        '#0891b2', '#ca8a04', '#8b5cf6', '#db2777'];

  var HEX6 = /^#[0-9a-f]{6}$/i;

  function readStore(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function writeStore(key, val) {
    try { localStorage.setItem(key, val); } catch (e) { /* storage blocked — this session only */ }
  }

  function currentMode() {
    var m = readStore('palette');
    return (m === 'cb' || m === 'custom') ? m : 'default';
  }

  function savedCustomColors() {
    try {
      var arr = JSON.parse(readStore('paletteColors') || '[]');
      if (Object.prototype.toString.call(arr) === '[object Array]') return arr;
    } catch (e) { /* fall through */ }
    return [];
  }

  // Read what a chart slot currently resolves to (inline override, cb token, or default),
  // normalized to a 6-digit hex an <input type="color"> accepts.
  function computedSlot(i) {
    var v = getComputedStyle(root).getPropertyValue('--chart-' + i).trim();
    return HEX6.test(v) ? v.toLowerCase() : DEFAULT_COLORS[i - 1];
  }

  function setInlineColors(colors) {
    for (var i = 0; i < 8; i++) {
      if (colors[i]) root.style.setProperty('--chart-' + (i + 1), colors[i]);
    }
  }
  function clearInlineColors() {
    for (var i = 1; i <= 8; i++) root.style.removeProperty('--chart-' + i);
  }

  // Redraw every chart on the page: they re-read their CSS color tokens on "themechange".
  function redraw() {
    document.dispatchEvent(new CustomEvent('themechange', { detail: { palette: currentMode() } }));
  }

  // Apply a mode (+ optional custom colors), persist, and redraw. This is the one place
  // the DOM/token state changes.
  function apply(mode, customColors) {
    if (mode === 'cb') {
      clearInlineColors();
      root.setAttribute('data-palette', 'cb');
    } else if (mode === 'custom') {
      root.setAttribute('data-palette', 'custom');
      setInlineColors(customColors || savedCustomColors());
    } else {
      clearInlineColors();
      root.removeAttribute('data-palette');
      mode = 'default';
    }
    writeStore('palette', mode);
    if (mode === 'custom') writeStore('paletteColors', JSON.stringify(customColors || savedCustomColors()));
    redraw();
  }

  function init() {
    var toggle = document.getElementById('palette-toggle');
    var dialog = document.getElementById('palette-dialog');
    if (!toggle || !dialog || typeof dialog.showModal !== 'function') return;

    var customBox = document.getElementById('palette-custom');
    var swatchInputs = [].slice.call(dialog.querySelectorAll('#palette-swatches input[data-chart]'));
    var resetBtn = document.getElementById('palette-reset-custom');
    var modeRadios = [].slice.call(dialog.querySelectorAll('input[name="palette-mode"]'));

    // The color inputs, in slot order (1..8). Their live values are the working custom set.
    function pickerColors() {
      return swatchInputs
        .sort(function (a, b) { return (+a.getAttribute('data-chart')) - (+b.getAttribute('data-chart')); })
        .map(function (input) { return input.value; });
    }

    function seedPickers(colors) {
      swatchInputs.forEach(function (input) {
        var idx = (+input.getAttribute('data-chart')) - 1;
        input.value = (colors && colors[idx]) || computedSlot(idx + 1);
      });
    }

    function showCustom(on) { if (customBox) customBox.hidden = !on; }

    // Sync the dialog controls to the persisted state (called on open).
    function syncDialog() {
      var mode = currentMode();
      modeRadios.forEach(function (r) { r.checked = (r.value === mode); });
      showCustom(mode === 'custom');
      // seed the pickers from the saved custom set, else from whatever is currently showing
      seedPickers(mode === 'custom' ? savedCustomColors() : null);
    }

    toggle.addEventListener('click', function () {
      syncDialog();
      dialog.showModal();
    });

    modeRadios.forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (!radio.checked) return;
        showCustom(radio.value === 'custom');
        if (radio.value === 'custom') {
          // start Custom from whatever palette is currently showing (Default or CB), so it's
          // a tweak of the live colors rather than a jump back to Default.
          seedPickers(null);
          apply('custom', pickerColors());
        } else {
          apply(radio.value);
        }
      });
    });

    swatchInputs.forEach(function (input) {
      input.addEventListener('input', function () {
        // editing a swatch implies custom mode
        var customRadio = modeRadios.filter(function (r) { return r.value === 'custom'; })[0];
        if (customRadio) customRadio.checked = true;
        showCustom(true);
        apply('custom', pickerColors());
      });
    });

    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        seedPickers(DEFAULT_COLORS.slice());
        apply('custom', DEFAULT_COLORS.slice());
      });
    }

    // Close affordances mirror the confirm dialog (app.js): [data-dialog-cancel] + backdrop click.
    var doneBtn = dialog.querySelector('[data-dialog-cancel]');
    if (doneBtn) doneBtn.addEventListener('click', function () { dialog.close(); });
    dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
