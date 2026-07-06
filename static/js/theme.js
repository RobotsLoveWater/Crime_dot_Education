/* static/js/theme.js
   Theme toggle. Partner of the inline FOUC guard in layout.html <head>, which
   sets data-theme before first paint; this file only handles switching.
   Persists to localStorage key "theme"; dispatches a "themechange" CustomEvent
   on document so charts can re-read CSS variables (see STYLEGUIDE.md). */

(function () {
  var root = document.documentElement;

  function current() {
    return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }

  function label(button) {
    // The button names the theme it switches TO.
    button.textContent = current() === 'dark' ? 'Light theme' : 'Dark theme';
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('theme', theme);
    } catch (e) { /* storage may be blocked; the toggle still works for this page */ }
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
  }

  function init() {
    var button = document.getElementById('theme-toggle');
    if (!button) return;
    label(button);
    button.addEventListener('click', function () {
      apply(current() === 'dark' ? 'light' : 'dark');
      label(button);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
