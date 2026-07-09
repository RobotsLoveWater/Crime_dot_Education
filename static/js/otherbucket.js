/* static/js/otherbucket.js
   Reusable "Other"-cutoff bucketing + slider (VISUALIZATION_EXPANSION.md Phase 4).
   Shared by the Explore distribution bar and the Visualize pie — loaded (defer,
   before the per-view chart script) on every view that draws a top-N + "Other"
   chart. Given a payload that carries the capped value head plus a residual tail
   (bucket_payload in app.py), it re-buckets top-N + "Other" entirely client-side,
   so dragging the slider never refetches. Progressive enhancement: the server
   pre-buckets a sensible default and the slider markup is .js-only, so no-JS keeps
   working. Exposes window.chartBucket = { bucket, wireSlider }. */

(function () {
  'use strict';

  // Re-slice a payload to a top-`cutoff` head + an "Other" tail. Pure: returns a fresh
  // {labels, counts, other, otherValues, total}. "Other" always folds in the residual
  // tail (values beyond the server's hard cap) so it stays exact at any cutoff.
  function bucket(payload, cutoff) {
    var values = (payload && payload.values) || [];
    var n = Math.max(1, Math.min(cutoff || values.length, values.length));
    var head = values.slice(0, n);
    var tail = values.slice(n);
    var otherCount = payload.tailCount || 0;
    tail.forEach(function (v) { otherCount += v.count; });
    return {
      labels: head.map(function (v) { return v.label; }),
      counts: head.map(function (v) { return v.count; }),
      other: otherCount,
      otherValues: tail.length + (payload.tailValues || 0),
      total: payload.total || 0
    };
  }

  // Wire the [data-bucket-slider] range input inside `root` to re-render on input.
  // onChange(cutoff) fires per change (rAF-coalesced so a fast drag renders once per
  // frame). Returns the effective initial cutoff. The slider markup only renders when
  // there is something to slide, so a missing control just returns the default cutoff.
  function wireSlider(root, payload, onChange) {
    if (!root) return payload.cutoff;
    var slider = root.querySelector('[data-bucket-slider]');
    if (!slider) return payload.cutoff;

    var output = root.querySelector('[data-bucket-value]');
    var current = parseInt(slider.value, 10);
    if (slider.dataset.bound) return current;   // survive re-inits without double-binding
    slider.dataset.bound = '1';

    var raf = null;
    slider.addEventListener('input', function () {
      var c = parseInt(slider.value, 10);
      if (output) output.textContent = c;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(function () { onChange(c); });
    });
    return current;
  }

  window.chartBucket = { bucket: bucket, wireSlider: wireSlider };
})();
