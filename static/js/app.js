/* static/js/app.js
   Shell behaviors (vanilla JS, no build step — STYLEGUIDE.md "File organization"):
   - toasts: auto-dismiss server-rendered flashes, show htmx-triggered toasts
     (HX-Trigger "toast" event) and htmx error toasts
   - confirm dialog: intercepts [data-confirm] links (revert / clear data)
   - sidebar drawer at tablet width: toggle, focus trap, Esc to close
   - global progress bar bound to htmx request events
   - form submit feedback: spinner + "Computing statistics…" on [data-loading] forms
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

  /* ---------- Sidebar drawer (768–1023px) ---------- */

  var sidebar = document.getElementById('sidebar');
  var sidebarToggle = document.getElementById('sidebar-toggle');
  var sidebarBackdrop = document.getElementById('sidebar-backdrop');

  if (sidebar && sidebarToggle && sidebarBackdrop) {
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

    var openDrawer = function () {
      sidebar.classList.add('open');
      sidebarBackdrop.classList.add('open');
      sidebarToggle.setAttribute('aria-expanded', 'true');
      var first = sidebar.querySelector(FOCUSABLE);
      (first || sidebar).focus();
      document.addEventListener('keydown', trapKeydown);
    };

    var closeDrawer = function () {
      sidebar.classList.remove('open');
      sidebarBackdrop.classList.remove('open');
      sidebarToggle.setAttribute('aria-expanded', 'false');
      document.removeEventListener('keydown', trapKeydown);
      sidebarToggle.focus();
    };

    sidebarToggle.addEventListener('click', function () {
      if (sidebar.classList.contains('open')) closeDrawer();
      else openDrawer();
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
})();
