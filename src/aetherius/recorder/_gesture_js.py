"""In-page capture script for the gesture recorder.

Streams raw pointer samples ``[x, y, t]`` (viewport pixels, seconds since page load) and click
timestamps to the ``__aetherius_gesture`` binding. Moves are buffered and flushed on a timer and on
every click, rather than sent one per ``pointermove``, so the binding is not hammered thousands of
times a second. Segmentation into individual gestures is done in pure Python (:mod:`.gesture_recorder`).
"""

from __future__ import annotations

# Self-invoking, guarded against double injection. performance.now() is milliseconds; we send seconds.
GESTURE_RECORDER_JS = r"""
(() => {
  if (window.__aetheriusGestureRecorder) return;
  window.__aetheriusGestureRecorder = true;

  let buffer = [];
  let clickAt = null;

  const flush = () => {
    if (buffer.length === 0 && clickAt === null) return;
    const payload = { moves: buffer, click: clickAt };
    buffer = [];
    clickAt = null;
    try { window.__aetherius_gesture(JSON.stringify(payload)); } catch (e) {}
  };

  document.addEventListener('pointermove', (e) => {
    buffer.push([Math.round(e.clientX), Math.round(e.clientY), +(performance.now() / 1000).toFixed(4)]);
  }, true);

  document.addEventListener('pointerdown', (e) => {
    buffer.push([Math.round(e.clientX), Math.round(e.clientY), +(performance.now() / 1000).toFixed(4)]);
    clickAt = +(performance.now() / 1000).toFixed(4);
    flush();
  }, true);

  setInterval(flush, 250);
})();
"""
