/* static/js/app.js
   Shell behaviors (vanilla JS, no build step — STYLEGUIDE.md "File organization"):
   - toasts: auto-dismiss server-rendered flashes, show htmx-triggered toasts
     (HX-Trigger "toast" event) and htmx error toasts
   - confirm dialog: intercepts [data-confirm] links (revert / clear data)
   - sidebar drawer at tablet width: toggle, focus trap, Esc to close
   - global progress bar bound to htmx request events
   - form submit feedback: spinner + "Computing statistics…" on [data-loading] forms
   - searchable pickers over native selects ([data-picker], STYLEGUIDE.md)
   - educator checkbox on the auth pages: hide the class-code field ([data-educator-toggle])
   Everything here is an enhancement; all actions work as plain links/forms without it. */

(function () {
  'use strict';

  var TOAST_MS = 5000;
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), ' +
                  'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  /* ---------- Toasts ---------- */

  function bindToast(toast) {
    var timer = null;

    function dismiss() {
      toast.classList.add('toast-leaving');
      setTimeout(function () { toast.remove(); }, 200);
    }
    function start() { timer = setTimeout(dismiss, TOAST_MS); }
    function stop() { clearTimeout(timer); }

    // pause on hover / while focused (STYLEGUIDE.md "Toasts")
    toast.addEventListener('mouseenter', stop);
    toast.addEventListener('mouseleave', start);
    toast.addEventListener('focusin', stop);
    toast.addEventListener('focusout', start);

    var close = toast.querySelector('.toast-close');
    if (close) {
      close.addEventListener('click', function () {
        stop();
        dismiss();
      });
    }
    start();
  }

  function showToast(message, variant) {
    var region = document.getElementById('toast-region');
    if (!region || !message) return;
    if (variant !== 'success' && variant !== 'danger') variant = 'info';

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + variant;
    toast.setAttribute('role', 'status');

    var text = document.createElement('p');
    text.className = 'toast-message';
    text.textContent = message;

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.innerHTML = '&times;';

    toast.appendChild(text);
    toast.appendChild(close);
    region.appendChild(toast);
    bindToast(toast);
  }

  // server-rendered flashes
  document.querySelectorAll('#toast-region .toast').forEach(bindToast);

  // htmx paths: HX-Trigger {"toast": {"message": ..., "category": ...}} and errors
  document.body.addEventListener('toast', function (e) {
    var d = e.detail || {};
    showToast(d.message, d.category);
  });
  document.body.addEventListener('htmx:responseError', function () {
    showToast('Something went wrong loading that view. Try again.', 'danger');
  });
  document.body.addEventListener('htmx:sendError', function () {
    showToast('Could not reach the server. Check your connection and try again.', 'danger');
  });

  /* ---------- Confirm dialog ---------- */

  var dialog = document.getElementById('confirm-dialog');
  if (dialog && typeof dialog.showModal === 'function') {
    var acceptLink = document.getElementById('confirm-accept');
    var dialogTitle = document.getElementById('confirm-title');
    var dialogMessage = document.getElementById('confirm-message');

    document.addEventListener('click', function (e) {
      var trigger = e.target && e.target.closest ? e.target.closest('[data-confirm]') : null;
      if (!trigger) return;
      var href = trigger.getAttribute('href');
      if (!href) return; // only link-style confirms exist in Phase 1

      e.preventDefault();
      dialogTitle.textContent = trigger.getAttribute('data-confirm-title') || 'Are you sure?';
      dialogMessage.textContent = trigger.getAttribute('data-confirm');
      acceptLink.textContent = trigger.getAttribute('data-confirm-action') || 'Confirm';
      acceptLink.setAttribute('href', href);
      dialog.showModal(); // Esc closes and focus is restored natively
    });

    dialog.querySelector('[data-dialog-cancel]').addEventListener('click', function () {
      dialog.close();
    });

    // click on the backdrop closes (content is wrapped, so inside clicks never hit <dialog>)
    dialog.addEventListener('click', function (e) {
      if (e.target === dialog) dialog.close();
    });
  }

  /* ---------- Copy to clipboard ([data-copy], e.g. the class join code) ---------- */

  document.addEventListener('click', function (e) {
    var button = e.target && e.target.closest ? e.target.closest('[data-copy]') : null;
    if (!button) return;
    var target = document.querySelector(button.getAttribute('data-copy'));
    if (!target) return;
    var text = target.textContent.trim();

    var label = button.textContent;
    function copied() {
      button.textContent = 'Copied!';
      setTimeout(function () { button.textContent = label; }, 2000);
    }
    function failed() {
      showToast('Could not copy — select and copy the code manually.', 'danger');
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(copied, failed);
      return;
    }

    // fallback for browsers without the async Clipboard API
    var range = document.createRange();
    range.selectNodeContents(target);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    try {
      document.execCommand('copy');
      copied();
    } catch (err) {
      failed();
    }
    selection.removeAllRanges();
  });

  /* ---------- Sidebar drawer (<1024px) ----------
     Opened by any [aria-controls="sidebar"] trigger: the top-bar ☰ at tablet
     width and the full-width data-state bar on phones. Focus is trapped and
     returned to whichever trigger opened it. */

  var sidebar = document.getElementById('sidebar');
  var sidebarBackdrop = document.getElementById('sidebar-backdrop');
  var sidebarToggles = [].slice.call(document.querySelectorAll('[aria-controls="sidebar"]'));

  if (sidebar && sidebarBackdrop && sidebarToggles.length) {
    var lastOpener = null;

    var setExpanded = function (open) {
      sidebarToggles.forEach(function (t) {
        t.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    };

    var trapKeydown = function (e) {
      if (e.key === 'Escape') {
        closeDrawer();
        return;
      }
      if (e.key !== 'Tab') return;
      var items = sidebar.querySelectorAll(FOCUSABLE);
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      } else if (!sidebar.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    };

    var openDrawer = function (opener) {
      lastOpener = opener || sidebarToggles[0];
      sidebar.classList.add('open');
      sidebarBackdrop.classList.add('open');
      setExpanded(true);
      var first = sidebar.querySelector(FOCUSABLE);
      (first || sidebar).focus();
      document.addEventListener('keydown', trapKeydown);
    };

    var closeDrawer = function () {
      sidebar.classList.remove('open');
      sidebarBackdrop.classList.remove('open');
      setExpanded(false);
      document.removeEventListener('keydown', trapKeydown);
      if (lastOpener) lastOpener.focus();
    };

    sidebarToggles.forEach(function (toggle) {
      toggle.addEventListener('click', function () {
        if (sidebar.classList.contains('open')) closeDrawer();
        else openDrawer(toggle);
      });
    });
    sidebarBackdrop.addEventListener('click', closeDrawer);
  }

  /* ---------- Global progress bar (htmx requests) ---------- */

  var track = document.getElementById('progress-track');
  var thumb = track ? track.querySelector('.progress-thumb') : null;
  var inflight = 0;
  var creepTimer = null;

  function progressStart() {
    if (!track) return;
    track.classList.add('active');
    thumb.style.width = '20%';
    clearInterval(creepTimer);
    creepTimer = setInterval(function () {
      var w = parseFloat(thumb.style.width) || 20;
      if (w < 85) thumb.style.width = (w + (85 - w) * 0.15) + '%';
    }, 300);
  }

  function progressEnd() {
    if (!track) return;
    clearInterval(creepTimer);
    thumb.style.width = '100%';
    setTimeout(function () {
      track.classList.remove('active');
      thumb.style.width = '0';
    }, 250);
  }

  document.body.addEventListener('htmx:beforeRequest', function () {
    if (++inflight === 1) progressStart();
  });
  document.body.addEventListener('htmx:afterRequest', function () {
    if (inflight > 0 && --inflight === 0) progressEnd();
  });

  /* ---------- Submit feedback on [data-loading] forms ---------- */

  function resetLoadingForm(form) {
    delete form.dataset.loadingActive;
    form.querySelectorAll('input[type="submit"], button[type="submit"], button:not([type])')
      .forEach(function (el) { el.disabled = false; });
    form.querySelectorAll('.form-loading').forEach(function (n) { n.remove(); });
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.hasAttribute || !form.hasAttribute('data-loading') || e.defaultPrevented) return;
    if (form.dataset.loadingActive) { // double-submit guard
      e.preventDefault();
      return;
    }
    form.dataset.loadingActive = '1';

    // lock the UI after this tick so the submission itself is unaffected
    setTimeout(function () {
      var submits = form.querySelectorAll('input[type="submit"], button[type="submit"], button:not([type])');
      submits.forEach(function (el) { el.disabled = true; });

      var note = document.createElement('span');
      note.className = 'form-loading';
      note.setAttribute('role', 'status');
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      note.appendChild(spinner);
      note.appendChild(document.createTextNode(' ' + form.getAttribute('data-loading')));
      if (submits.length) submits[0].insertAdjacentElement('afterend', note);
      else form.appendChild(note);
    }, 0);
  });

  // restore buttons when a page comes back from the bfcache (browser Back)
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    document.querySelectorAll('form[data-loading]').forEach(resetLoadingForm);
  });

  /* ---------- Searchable pickers (STYLEGUIDE.md "Searchable picker") ----------
     Progressive enhancement over a native <select> inside a [data-picker] wrapper:
     a combobox input filters the option list client-side; arrows + Enter select,
     Esc closes. The native select stays in the form and keeps carrying the value
     (and is the no-JS fallback). */

  var pickerSeq = 0;

  // Hide the native <select> once its combobox exists (idempotent).
  function hideNative(select) {
    select.classList.add('picker-native');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
  }

  function enhancePicker(wrap) {
    var select = wrap.querySelector('select');
    if (!select) return;
    if (wrap.dataset.enhanced) {
      // Already enhanced. When a picker rides inside an htmx-swapped fragment (the
      // Visualize builder re-includes its own form), htmx's settle step re-applies the
      // server response's attributes to id-matched swapped elements — wiping the
      // .picker-native class we add to hide the native <select>, so it reappears next to
      // the combobox. The enhanced guard lives on the id-less wrapper (which htmx never
      // settles), so we don't rebuild the combobox — we just restore the hidden state.
      hideNative(select);
      return;
    }
    wrap.dataset.enhanced = '1';

    // flatten the options (placeholder rows with empty values are not results)
    var options = [];
    Array.prototype.forEach.call(select.querySelectorAll('option'), function (opt) {
      if (opt.value === '') return;
      options.push({
        value: opt.value,
        text: opt.textContent,
        group: opt.parentElement.tagName === 'OPTGROUP' ? opt.parentElement.label : ''
      });
    });

    var baseId = select.id || ('picker-' + (++pickerSeq));

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'picker-input';
    input.id = baseId + '-input';
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', baseId + '-listbox');
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = 'Type to search…';

    var menu = document.createElement('div');
    menu.className = 'picker-menu';
    menu.hidden = true;
    var list = document.createElement('ul');
    list.className = 'picker-list';
    list.id = baseId + '-listbox';
    list.setAttribute('role', 'listbox');
    menu.appendChild(list);

    // the visible input is now what the label describes
    var label = wrap.querySelector('label');
    if (label) label.htmlFor = input.id;

    hideNative(select);
    select.insertAdjacentElement('afterend', input);
    input.insertAdjacentElement('afterend', menu);

    var items = [];   // rendered .picker-option elements
    var active = -1;  // index into items

    function selectedText() {
      var opt = select.options[select.selectedIndex];
      return opt && opt.value !== '' ? opt.textContent : '';
    }

    function setActive(index) {
      if (items[active]) items[active].classList.remove('active');
      active = index;
      if (items[active]) {
        items[active].classList.add('active');
        input.setAttribute('aria-activedescendant', items[active].id);
        items[active].scrollIntoView({ block: 'nearest' });
      } else {
        input.removeAttribute('aria-activedescendant');
      }
    }

    function render(query) {
      list.innerHTML = '';
      items = [];
      var lastGroup = null;
      var selectedItem = null;

      options.forEach(function (option, index) {
        if (query && (option.text + ' ' + option.value).toLowerCase().indexOf(query) === -1) return;
        if (option.group && option.group !== lastGroup) {
          var heading = document.createElement('li');
          heading.className = 'picker-group';
          heading.setAttribute('role', 'presentation');
          heading.textContent = option.group;
          list.appendChild(heading);
          lastGroup = option.group;
        }
        var item = document.createElement('li');
        item.className = 'picker-option';
        item.id = baseId + '-opt-' + index;
        item.setAttribute('role', 'option');
        item.setAttribute('data-index', index);
        item.textContent = option.text;
        if (option.value === select.value) {
          item.setAttribute('aria-selected', 'true');
          selectedItem = item;
        }
        list.appendChild(item);
        items.push(item);
      });

      if (!items.length) {
        var empty = document.createElement('li');
        empty.className = 'picker-empty';
        empty.setAttribute('role', 'presentation');
        empty.textContent = 'No matches.';
        list.appendChild(empty);
      }

      // start on the committed choice when browsing, else the first match
      setActive(selectedItem ? items.indexOf(selectedItem) : (items.length ? 0 : -1));
    }

    function open(query) {
      menu.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      render(query || '');
    }

    function close() {
      menu.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      input.value = selectedText(); // revert uncommitted typing
    }

    function choose(item) {
      var option = options[parseInt(item.getAttribute('data-index'), 10)];
      select.value = option.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      close();
    }

    input.value = selectedText();

    input.addEventListener('focus', function () {
      if (menu.hidden) {
        open('');
        input.select();
      }
    });
    input.addEventListener('click', function () {
      if (menu.hidden) {
        open('');
        input.select();
      }
    });
    input.addEventListener('input', function () {
      var query = input.value.trim().toLowerCase();
      if (menu.hidden) open(query);
      else render(query);
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (menu.hidden) { open(''); return; }
        if (!items.length) return;
        var step = e.key === 'ArrowDown' ? 1 : -1;
        setActive((active + step + items.length) % items.length);
      } else if (e.key === 'Enter') {
        if (!menu.hidden) {
          e.preventDefault(); // choosing an option must not submit the form
          if (items[active]) choose(items[active]);
        }
      } else if (e.key === 'Escape') {
        if (!menu.hidden) {
          e.stopPropagation(); // just close the menu, not a surrounding dialog/drawer
          close();
        }
      } else if (e.key === 'Tab') {
        if (!menu.hidden) close();
      }
    });

    // selecting with the mouse: prevent the blur so the click can land
    menu.addEventListener('mousedown', function (e) { e.preventDefault(); });
    menu.addEventListener('click', function (e) {
      var item = e.target.closest('.picker-option');
      if (item) choose(item);
    });

    input.addEventListener('blur', function () {
      if (!menu.hidden) close();
    });
  }

  function initPickers() {
    document.querySelectorAll('[data-picker]').forEach(enhancePicker);
  }

  initPickers();
  // afterSwap enhances freshly-swapped pickers immediately (no flash of the raw select);
  // afterSettle re-runs so already-enhanced pickers repair the .picker-native class that
  // htmx's settle step wipes off id-matched <select>s (see enhancePicker's repair branch).
  document.body.addEventListener('htmx:afterSwap', initPickers);
  document.body.addEventListener('htmx:afterSettle', initPickers);
  document.body.addEventListener('htmx:historyRestore', initPickers);

  /* ---------- Educator checkbox (auth pages) ----------
     The "I'm an educator" checkbox hides the class-code field, which educators don't use — their
     account is looked up by username on the backend. No-JS: the field stays visible and is simply
     ignored by the server when the box is checked. */

  document.querySelectorAll('[data-educator-toggle]').forEach(function (box) {
    var field = document.getElementById(box.getAttribute('aria-controls'));
    if (!field) return;
    function sync() { field.hidden = box.checked; }
    box.addEventListener('change', sync);
    sync();
  });
})();
