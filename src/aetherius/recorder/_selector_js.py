"""Shared in-page selector primitives, installed on ``window.__aeSel``.

The only place that can call ``CSS.escape`` and measure a selector's uniqueness against the live DOM.
Both the action-capture script (:mod:`._capture_js`) and the pick overlay (:mod:`._overlay_js`) build
their element descriptors from here, so the candidate/uniqueness logic exists once. The ranking policy
that turns candidates into a Blueprint selector stays pure Python (:mod:`.selector_synth`).
"""

from __future__ import annotations

# Self-invoking, guarded. Attaches the primitives to window so later scripts can reuse them.
SELECTOR_JS = r"""
(() => {
  if (window.__aeSel) return;

  const CLICKABLE = 'a, button, [role="button"], input[type="submit"], input[type="button"], ' +
    'input[type="reset"], input[type="checkbox"], input[type="radio"]';

  const isUnique = (sel, root) => {
    try { return (root || document).querySelectorAll(sel).length === 1; } catch (e) { return false; }
  };

  // Escape a value for use inside an [attr="..."] string: only backslash and double-quote.
  // (CSS.escape is for identifiers like #id/.class and would over-escape `/`, spaces, etc.)
  const attrValue = (v) => String(v).replace(/\\/g, '\\\\').replace(/"/g, '\\"');

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
    if (testId) push('testid', '[' + testId[0] + '="' + attrValue(testId[1]) + '"]', 'css');
    if (el.id) push('id', '#' + CSS.escape(el.id), 'css');
    const href = tag === 'a' ? el.getAttribute('href') : null;  // the natural, stable hook for a link
    if (href) push('href', 'a[href="' + attrValue(href) + '"]', 'css');
    const name = el.getAttribute('name');
    if (name) push('name', tag + '[name="' + attrValue(name) + '"]', 'css');
    const aria = el.getAttribute('aria-label');
    if (aria) push('aria', '[aria-label="' + attrValue(aria) + '"]', 'css');
    const role = el.getAttribute('role');
    if (role) push('role', tag + '[role="' + attrValue(role) + '"]', 'css');
    for (const cls of el.classList) {  // a single class that is unique is a decent, readable hook
      const s = '.' + CSS.escape(cls);
      if (isUnique(s)) { out.push({ strategy: 'class', selector: s, selector_type: 'css', unique: true }); break; }
    }

    if (el.matches(CLICKABLE) || role === 'button') {
      const text = visibleText(el);
      if (text) {
        // Uniqueness must match get_by_text at run time: substring, case-insensitive, whole DOM.
        // Count the *deepest* elements containing the text (no child also contains it), which
        // approximates get_by_text's leaf matching. A brittle "License"-style text stays non-unique.
        const norm = (s) => (s || '').trim().replace(/\s+/g, ' ').toLowerCase();
        const needle = norm(text);
        const hits = [...document.querySelectorAll('*')].filter((e) =>
          norm(e.textContent).includes(needle) &&
          ![...e.children].some((c) => norm(c.textContent).includes(needle)));
        out.push({ strategy: 'text', selector: text, selector_type: 'text', unique: hits.length === 1 });
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

  // A selector matching `el` AND its repeating siblings (for lists/records: the shared class that
  // yields the most matches, else the tag). Distinct from candidates(), which seek a *unique* hook.
  const groupSelector = (el) => {
    let best = null, bestCount = 1;
    for (const cls of el.classList) {
      const s = '.' + CSS.escape(cls);
      const n = isUnique(s) ? 1 : (() => { try { return document.querySelectorAll(s).length; } catch (e) { return 0; } })();
      if (n >= 2 && n > bestCount) { best = s; bestCount = n; }
    }
    if (best) return best;
    const tag = el.tagName.toLowerCase();
    return tag;
  };

  // A selector for `el` scoped *within* `container` (for records: `.title` inside `.product`).
  const relativeSelector = (container, el) => {
    const testId = testIdAttr(el);
    if (testId) {
      const s = '[' + testId[0] + '="' + attrValue(testId[1]) + '"]';
      if (isUnique(s, container)) return s;
    }
    for (const cls of el.classList) {
      const s = '.' + CSS.escape(cls);
      if (isUnique(s, container)) return s;
    }
    const tag = el.tagName.toLowerCase();
    if (isUnique(tag, container)) return tag;
    // Fallback: nth-of-type path from just under the container down to el.
    const parts = [];
    let node = el;
    while (node && node !== container && node.parentElement) {
      let part = node.tagName.toLowerCase();
      const sameTag = [...node.parentElement.children].filter((c) => c.tagName === node.tagName);
      if (sameTag.length > 1) part += ':nth-of-type(' + (sameTag.indexOf(node) + 1) + ')';
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ') || tag;
  };

  window.__aeSel = { CLICKABLE, isUnique, cssPath, visibleText, candidates, descriptorFor,
                     groupSelector, relativeSelector };
})();
"""
