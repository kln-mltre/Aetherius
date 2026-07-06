"""In-page capture script for the Blueprint recorder.

Injected once per document via Playwright's ``add_init_script`` so it survives navigations and new
pages. It listens for the real DOM events a demonstration produces (click, change, Enter) and, for
each, reports a JSON descriptor to the ``__aetherius_capture`` binding the Python side exposes.

The DOM work lives here on purpose: only in-page code can call ``CSS.escape`` and measure a
selector's uniqueness against the live document. It reports *facts* (candidate selectors and whether
each is unique); the ranking policy that turns them into a Blueprint selector is pure Python
(:mod:`.selector_synth`), so it stays testable without a browser.
"""

from __future__ import annotations

# Self-invoking (add_init_script evaluates verbatim). Guarded by a window flag so repeated injection
# on the same document is a no-op. Password fields never send their value: only a redacted marker.
RECORDER_JS = r"""
(() => {
  if (window.__aetheriusRecorder) return;
  window.__aetheriusRecorder = true;

  const TEXTUAL = new Set(['text', 'email', 'search', 'tel', 'url', 'number', 'password', '']);
  const CLICKABLE = 'a, button, [role="button"], input[type="submit"], input[type="button"], ' +
    'input[type="reset"], input[type="checkbox"], input[type="radio"]';

  const send = (payload) => {
    try { window.__aetherius_capture(JSON.stringify(payload)); } catch (e) {}
  };

  const isUnique = (sel) => {
    try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; }
  };

  const testIdAttr = (el) => {
    for (const name of ['data-testid', 'data-test', 'data-cy', 'data-qa']) {
      if (el.hasAttribute(name)) return [name, el.getAttribute(name)];
    }
    return null;
  };

  const cssPath = (el) => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift('#' + CSS.escape(node.id)); break; }
      const parent = node.parentElement;
      if (parent) {
        const sameTag = [...parent.children].filter((c) => c.tagName === node.tagName);
        if (sameTag.length > 1) part += ':nth-of-type(' + (sameTag.indexOf(node) + 1) + ')';
      }
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };

  const visibleText = (el) => {
    const t = (el.textContent || '').trim().replace(/\s+/g, ' ');
    return t.length > 0 && t.length <= 64 ? t : null;
  };

  const candidates = (el) => {
    const tag = el.tagName.toLowerCase();
    const out = [];
    const push = (strategy, selector, selector_type) =>
      out.push({ strategy, selector, selector_type, unique: isUnique(selector) });

    const testId = testIdAttr(el);
    if (testId) push('testid', '[' + testId[0] + '="' + CSS.escape(testId[1]) + '"]', 'css');
    if (el.id) push('id', '#' + CSS.escape(el.id), 'css');
    const name = el.getAttribute('name');
    if (name) push('name', tag + '[name="' + CSS.escape(name) + '"]', 'css');
    const aria = el.getAttribute('aria-label');
    if (aria) push('aria', '[aria-label="' + CSS.escape(aria) + '"]', 'css');
    const role = el.getAttribute('role');
    if (role) push('role', tag + '[role="' + CSS.escape(role) + '"]', 'css');

    if (el.matches(CLICKABLE) || role === 'button') {
      const text = visibleText(el);
      if (text) {
        const same = [...document.querySelectorAll(CLICKABLE)]
          .filter((e) => (e.textContent || '').trim().replace(/\s+/g, ' ') === text);
        out.push({ strategy: 'text', selector: text, selector_type: 'text', unique: same.length === 1 });
      }
    }
    return out;
  };

  const descriptorFor = (el) => ({
    tag: el.tagName.toLowerCase(),
    css_path: cssPath(el),
    text: visibleText(el),
    name: el.getAttribute('name'),
    field_type: (el.getAttribute('type') || '').toLowerCase() || null,
    autocomplete: el.getAttribute('autocomplete'),
    candidates: candidates(el),
  });

  document.addEventListener('click', (e) => {
    const el = e.target.closest(CLICKABLE);
    if (!el) return;  // plain clicks (focusing a text field, selecting text) are not steps
    send({ kind: 'click', descriptor: descriptorFor(el) });
  }, true);

  document.addEventListener('change', (e) => {
    const el = e.target;
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (tag === 'select') {
      send({ kind: 'select', value: el.value, descriptor: descriptorFor(el) });
      return;
    }
    if (tag !== 'input' && tag !== 'textarea') return;
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (type === 'checkbox' || type === 'radio') return;  // captured as a click
    if (tag === 'input' && !TEXTUAL.has(type)) return;
    if (type === 'password') {
      send({ kind: 'fill', redacted: true, descriptor: descriptorFor(el) });
    } else {
      send({ kind: 'fill', value: el.value, descriptor: descriptorFor(el) });
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const el = e.target;
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (tag !== 'input') return;  // Enter in a text field commonly submits without a visible button
    send({ kind: 'press', key: 'Enter', descriptor: descriptorFor(el) });
  }, true);
})();
"""
