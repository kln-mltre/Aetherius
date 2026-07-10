"""In-page capture script for the Blueprint recorder (action capture).

Listens for the real DOM events a demonstration produces (click, change, Enter) and reports a JSON
descriptor for each to the ``__aetherius_capture`` binding. Element descriptors are built by the
shared primitives on ``window.__aeSel`` (:mod:`._selector_js`), so the candidate/uniqueness logic is
defined once and shared with the pick overlay.

Two guards keep action capture and the overlay from stepping on each other: events originating in the
overlay are ignored, and while a pick mode is active (``window.__aeRecorderPicking``) page actions are
not recorded — the user is designating data, not driving the site.
"""

from __future__ import annotations

# Self-invoking, guarded against double injection. Password fields never send their value: only a
# redacted marker. Requires window.__aeSel (inject _selector_js.SELECTOR_JS first).
RECORDER_JS = r"""
(() => {
  if (window.__aetheriusRecorder) return;
  window.__aetheriusRecorder = true;

  const TEXTUAL = new Set(['text', 'email', 'search', 'tel', 'url', 'number', 'password', '']);
  const OVERLAY_ID = '__ae-recorder-overlay';

  const send = (payload) => {
    try { window.__aetherius_capture(JSON.stringify(payload)); } catch (e) {}
  };

  // Ignore events from the overlay itself, and any event while a pick mode is active.
  const ignored = (e) => {
    if (window.__aeRecorderPicking) return true;
    const path = e.composedPath ? e.composedPath() : [];
    return path.some((n) => n && n.id === OVERLAY_ID);
  };

  document.addEventListener('click', (e) => {
    if (ignored(e)) return;
    const el = e.target.closest(window.__aeSel.CLICKABLE);
    if (!el) return;  // plain clicks (focusing a text field, selecting text) are not steps
    const payload = { kind: 'click', descriptor: window.__aeSel.descriptorFor(el) };
    // A link navigating to a real URL is far more robust replayed as a navigate (stable URL) than as
    // a click (fragile selector). Buttons/submits have no reproducible URL, so they stay clicks.
    if (el.tagName === 'A') {
      const raw = el.getAttribute('href') || '';
      if (raw && !raw.startsWith('#') && !raw.startsWith('javascript:') && /^https?:/i.test(el.href)) {
        payload.href = el.href;
      }
    }
    send(payload);
  }, true);

  document.addEventListener('change', (e) => {
    if (ignored(e)) return;
    const el = e.target;
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (tag === 'select') {
      send({ kind: 'select', value: el.value, descriptor: window.__aeSel.descriptorFor(el) });
      return;
    }
    if (tag !== 'input' && tag !== 'textarea') return;
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (type === 'checkbox' || type === 'radio') return;  // captured as a click
    if (tag === 'input' && !TEXTUAL.has(type)) return;
    if (type === 'password') {
      send({ kind: 'fill', redacted: true, descriptor: window.__aeSel.descriptorFor(el) });
    } else {
      send({ kind: 'fill', value: el.value, descriptor: window.__aeSel.descriptorFor(el) });
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (ignored(e)) return;
    if (e.key !== 'Enter') return;
    const el = e.target;
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (tag !== 'input') return;  // Enter in a text field commonly submits without a visible button
    send({ kind: 'press', key: 'Enter', descriptor: window.__aeSel.descriptorFor(el) });
  }, true);
})();
"""
