/* static/js/palette.js
   The global chart-color control. Palette changes are client-only: they update CSS
   variables and dispatch themechange so already-rendered charts redraw without a fetch. */

(function () {
  'use strict';

  var root = document.documentElement;
  var MODES = ['default', 'universal', 'protan', 'deutan', 'tritan', 'mono', 'custom'];
  var DEFAULT_COLORS = ['#2563eb', '#f97316', '#059669', '#dc2626',
                        '#0891b2', '#ca8a04', '#8b5cf6', '#db2777'];
  var HEX6 = /^#[0-9a-f]{6}$/i;

  function readStore(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function writeStore(key, val) {
    try { localStorage.setItem(key, val); } catch (e) { /* storage blocked: session only */ }
  }
  function isMode(mode) { return MODES.indexOf(mode) !== -1; }

  function currentMode() {
    var mode = readStore('palette');
    // "cb" was the former single colorblind-safe option. Preserve a user's
    // preference by moving it to its direct replacement as soon as JS can run.
    if (mode === 'cb') {
      writeStore('palette', 'universal');
      return 'universal';
    }
    return isMode(mode) ? mode : 'default';
  }

  function validColors(colors) {
    if (Object.prototype.toString.call(colors) !== '[object Array]' || colors.length !== 8) {
      return null;
    }
    var normalized = [];
    for (var i = 0; i < 8; i++) {
      if (typeof colors[i] !== 'string' || !HEX6.test(colors[i])) return null;
      normalized.push(colors[i].toLowerCase());
    }
    return normalized;
  }

  function savedCustomColors() {
    try { return validColors(JSON.parse(readStore('paletteColors') || 'null')); }
    catch (e) { return null; }
  }

  function computedSlot(i) {
    var value = getComputedStyle(root).getPropertyValue('--chart-' + i).trim();
    return HEX6.test(value) ? value.toLowerCase() : DEFAULT_COLORS[i - 1];
  }

  function setCustomPreviewColors(colors) {
    var safe = validColors(colors);
    if (!safe) return;
    for (var i = 0; i < 8; i++) {
      root.style.setProperty('--palette-custom-' + (i + 1), safe[i]);
    }
  }
  function clearCustomPreviewColors() {
    for (var i = 1; i <= 8; i++) root.style.removeProperty('--palette-custom-' + i);
  }
  function setInlineColors(colors) {
    for (var i = 0; i < 8; i++) root.style.setProperty('--chart-' + (i + 1), colors[i]);
  }
  function clearInlineColors() {
    for (var i = 1; i <= 8; i++) root.style.removeProperty('--chart-' + i);
  }
  function redraw(mode) {
    document.dispatchEvent(new CustomEvent('themechange', { detail: { palette: mode } }));
  }

  // The sole state-changing path for a user palette selection.
  function apply(mode, customColors) {
    if (mode === 'cb') mode = 'universal';
    if (!isMode(mode)) mode = 'default';

    if (mode === 'custom') {
      var colors = validColors(customColors) || savedCustomColors() || DEFAULT_COLORS.slice();
      root.setAttribute('data-palette', 'custom');
      setCustomPreviewColors(colors);
      setInlineColors(colors);
      writeStore('paletteColors', JSON.stringify(colors));
    } else {
      clearInlineColors();
      if (mode === 'default') root.removeAttribute('data-palette');
      else root.setAttribute('data-palette', mode);
    }
    writeStore('palette', mode);
    redraw(mode);
  }

  // Mirrors the inline pre-paint guard after deferred scripts begin. It also makes
  // stale "cb" markup converge on universal if a cached layout predates the guard.
  function restore() {
    var mode = currentMode();
    var custom = savedCustomColors();
    // A partial or damaged custom array must not leave the UI claiming Custom while
    // silently showing a different set. Fall all the way back to Standard.
    if (mode === 'custom' && !custom) {
      mode = 'default';
      writeStore('palette', mode);
    }
    clearCustomPreviewColors();
    if (custom) setCustomPreviewColors(custom);
    clearInlineColors();
    if (mode === 'custom') {
      var safe = custom || DEFAULT_COLORS.slice();
      root.setAttribute('data-palette', 'custom');
      setCustomPreviewColors(safe);
      setInlineColors(safe);
    } else if (mode === 'default') {
      root.removeAttribute('data-palette');
    } else {
      root.setAttribute('data-palette', mode);
    }
  }

  function init() {
    restore();
    var toggle = document.getElementById('palette-toggle');
    var dialog = document.getElementById('palette-dialog');
    if (!toggle || !dialog || typeof dialog.showModal !== 'function') return;

    var customBox = document.getElementById('palette-custom');
    var swatchInputs = [].slice.call(dialog.querySelectorAll('#palette-swatches input[data-chart]'));
    var resetBtn = document.getElementById('palette-reset-custom');
    var modeRadios = [].slice.call(dialog.querySelectorAll('input[name="palette-mode"]'));

    function pickerColors() {
      return swatchInputs.slice().sort(function (a, b) {
        return (+a.getAttribute('data-chart')) - (+b.getAttribute('data-chart'));
      }).map(function (input) { return input.value; });
    }
    function seedPickers(colors) {
      var safe = validColors(colors);
      swatchInputs.forEach(function (input) {
        var index = (+input.getAttribute('data-chart')) - 1;
        input.value = safe ? safe[index] : computedSlot(index + 1);
      });
    }
    function showCustom(on) { if (customBox) customBox.hidden = !on; }
    function syncDialog() {
      var mode = currentMode();
      modeRadios.forEach(function (radio) { radio.checked = radio.value === mode; });
      showCustom(mode === 'custom');
      seedPickers(mode === 'custom' ? savedCustomColors() : null);
    }

    toggle.addEventListener('click', function () {
      syncDialog();
      dialog.showModal();
    });
    modeRadios.forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (!radio.checked || !isMode(radio.value)) return;
        showCustom(radio.value === 'custom');
        if (radio.value === 'custom') {
          seedPickers(null); // Start from the visible palette, ready for a small adjustment.
          apply('custom', pickerColors());
        } else {
          apply(radio.value);
        }
      });
    });
    swatchInputs.forEach(function (input) {
      input.addEventListener('input', function () {
        var customRadio = modeRadios.filter(function (radio) { return radio.value === 'custom'; })[0];
        if (customRadio) customRadio.checked = true;
        showCustom(true);
        apply('custom', pickerColors());
      });
    });
    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        seedPickers(DEFAULT_COLORS);
        apply('custom', DEFAULT_COLORS);
      });
    }
    var doneBtn = dialog.querySelector('[data-dialog-cancel]');
    if (doneBtn) doneBtn.addEventListener('click', function () { dialog.close(); });
    dialog.addEventListener('click', function (event) { if (event.target === dialog) dialog.close(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
