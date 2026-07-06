"""The recorder's floating "mod menu": an in-page overlay to pick data and pose meta-actions.

Injected like the debug overlay (``add_init_script``, re-installed on every navigation), but isolated
in a Shadow DOM so the page's CSS cannot mangle it and vice versa. It hosts a toolbar (Pick data /
Pick table / Wait for / Make input / Finish); a hover highlight; and small panels to choose the
extraction format. Element descriptors and selectors come from the shared ``window.__aeSel``
(:mod:`._selector_js`); the ranking policy stays pure Python (:mod:`.selector_synth`).

All emit paths funnel through ``window.__aeOverlay.{emitExtract,emitRecords,emitWaitFor,emitParam}``,
which the UI calls and integration tests drive directly (so the payload contract is testable without
replaying the whole click-through). While any mode is active, ``window.__aeRecorderPicking`` tells the
action-capture script to stand down.
"""

from __future__ import annotations

# Self-invoking, guarded. Requires window.__aeSel (inject SELECTOR_JS first). Emits through the same
# __aetherius_capture binding as action capture, with pick/records/wait_for/parameterize/finish kinds.
OVERLAY_JS = r"""
(() => {
  if (window.__aeOverlay) return;
  const OVERLAY_ID = '__ae-recorder-overlay';
  const ACCENT = '#c9a94a';

  const send = (p) => { try { window.__aetherius_capture(JSON.stringify(p)); } catch (e) {} };
  const S = () => window.__aeSel;

  const STATUS = {
    idle: 'Idle — pick a tool.',
    pick: 'Pick data: click an element to extract.',
    table: 'Pick table: click the repeating item, then each field, then Done.',
    waitfor: 'Wait for: click the element to wait for.',
    makeinput: 'Make input: click a field you filled to parameterize it.',
  };

  let host, root, statusEl, panelEl, highlight, doneBtn;
  let mode = 'idle';
  let container = null;   // repeating-record container element (table mode)
  let fields = [];        // [{name, el, as, attr}]

  const guessType = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'img') return { as: 'attr', attr: 'src' };
    if (tag === 'a') return { as: 'attr', attr: 'href' };
    const t = (el.textContent || '').trim();
    if (t && t.length < 24 && /\d/.test(t) && /^[^A-Za-z]*-?\d/.test(t)) return { as: 'number', attr: '' };
    return { as: 'text', attr: '' };
  };

  const guessName = (el) => {
    const raw = el.getAttribute('data-testid') || el.id || el.getAttribute('name') ||
      (S().visibleText(el) || '') || el.tagName.toLowerCase();
    return raw.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 24) || 'field';
  };

  // ── Emit API (called by the UI and by integration tests) ──────────────────
  window.__aeOverlay = {
    emitExtract(el, cfg) {
      // `group` (matches all siblings) is used when as is list/count; single values use the
      // unique selector Python synthesizes from the descriptor.
      send({ kind: 'extract', descriptor: S().descriptorFor(el), name: cfg.name, as: cfg.as,
             attr: cfg.attr || null, item: cfg.item || null, group: S().groupSelector(el) });
    },
    emitRecords(cont, fieldDefs, name) {
      send({ kind: 'extract_records', descriptor: S().descriptorFor(cont), name,
             each: S().groupSelector(cont),
             fields: fieldDefs.map((f) => ({
               name: f.name, selector: S().relativeSelector(cont, f.el),
               as: f.as || 'text', attr: f.attr || null })) });
    },
    emitWaitFor(el) {
      // group selector fallback: waiting is a presence check, so a class that matches the whole
      // group beats a brittle positional path when the element has no unique hook.
      send({ kind: 'wait_for', descriptor: S().descriptorFor(el), group: S().groupSelector(el) });
    },
    emitParam(el, name) { send({ kind: 'parameterize', descriptor: S().descriptorFor(el), name }); },
    setMode: (m) => setMode(m),
  };

  // ── UI ─────────────────────────────────────────────────────────────────────
  const el = (tag, css, text) => {
    const n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text != null) n.textContent = text;
    return n;
  };

  const button = (label, onclick) => {
    const b = el('button',
      'margin:0 4px 0 0;padding:4px 8px;font:12px system-ui;cursor:pointer;border-radius:5px;' +
      'border:1px solid ' + ACCENT + '55;background:#1c1830;color:#e7e2f3;', label);
    b.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); onclick(); });
    return b;
  };

  const clearPanel = () => { if (panelEl) panelEl.innerHTML = ''; };

  const setMode = (m) => {
    mode = m;
    window.__aeRecorderPicking = (m !== 'idle');
    if (statusEl) statusEl.textContent = STATUS[m] || '';
    if (highlight) highlight.style.display = (m === 'idle') ? 'none' : 'block';
    if (doneBtn) doneBtn.style.display = (m === 'table') ? 'inline-block' : 'none';
    if (m === 'idle') { clearPanel(); container = null; fields = []; }
  };

  const fieldRow = (labelText, node) => {
    const row = el('div', 'display:flex;align-items:center;gap:6px;margin:4px 0;');
    row.appendChild(el('label', 'font:12px system-ui;color:#b9b2d0;min-width:64px;', labelText));
    row.appendChild(node);
    return row;
  };

  const textInput = (value) => {
    const i = el('input', 'flex:1;padding:3px 6px;font:12px system-ui;border-radius:4px;' +
      'border:1px solid #4a4368;background:#0f0b1e;color:#e7e2f3;');
    i.value = value || '';
    return i;
  };

  const typeSelect = (value) => {
    const s = el('select', 'padding:3px;font:12px system-ui;border-radius:4px;' +
      'border:1px solid #4a4368;background:#0f0b1e;color:#e7e2f3;');
    for (const t of ['text', 'number', 'html', 'attr', 'count']) {
      const o = el('option', '', t); o.value = t; if (t === value) o.selected = true; s.appendChild(o);
    }
    return s;
  };

  // Format panel for a single element (Pick data).
  const openFormPanel = (target) => {
    clearPanel();
    const g = guessType(target);
    const name = textInput(guessName(target));
    const type = typeSelect(g.as);
    const attr = textInput(g.attr);
    const attrRow = fieldRow('attr', attr);
    const allBox = el('input'); allBox.type = 'checkbox';
    const sync = () => { attrRow.style.display = (type.value === 'attr') ? 'flex' : 'none'; };
    type.addEventListener('change', sync);

    panelEl.appendChild(fieldRow('name', name));
    panelEl.appendChild(fieldRow('type', type));
    panelEl.appendChild(attrRow);
    panelEl.appendChild(fieldRow('all matching', allBox));
    const actions = el('div', 'margin-top:6px;');
    actions.appendChild(button('Add', () => {
      const asList = allBox.checked && type.value !== 'count';
      const as = asList ? 'list' : type.value;
      window.__aeOverlay.emitExtract(target, { name: name.value, as,
        attr: type.value === 'attr' ? attr.value : '', item: asList ? type.value : null });
      setMode('idle');
    }));
    actions.appendChild(button('Cancel', () => setMode('idle')));
    panelEl.appendChild(actions);
    sync();
  };

  // Field panel for a record field (Pick table, after the container is chosen).
  const openFieldPanel = (target) => {
    clearPanel();
    const g = guessType(target);
    const name = textInput(guessName(target));
    const type = typeSelect(g.as === 'count' ? 'text' : g.as);
    panelEl.appendChild(el('div', 'font:12px system-ui;color:' + ACCENT + ';', 'Record field'));
    panelEl.appendChild(fieldRow('name', name));
    panelEl.appendChild(fieldRow('type', type));
    const actions = el('div', 'margin-top:6px;');
    actions.appendChild(button('Add field', () => {
      fields.push({ name: name.value, el: target, as: type.value, attr: g.attr });
      statusEl.textContent = fields.length + ' field(s) — click more, then Done.';
      clearPanel();
    }));
    panelEl.appendChild(actions);
  };

  const openInputPanel = (target) => {
    clearPanel();
    const name = textInput(guessName(target));
    panelEl.appendChild(fieldRow('input name', name));
    const actions = el('div', 'margin-top:6px;');
    actions.appendChild(button('Make input', () => {
      window.__aeOverlay.emitParam(target, name.value); setMode('idle');
    }));
    actions.appendChild(button('Cancel', () => setMode('idle')));
    panelEl.appendChild(actions);
  };

  const targetOf = (e) => {
    const path = e.composedPath ? e.composedPath() : [e.target];
    if (path.some((n) => n && n.id === OVERLAY_ID)) return null;  // never target the overlay
    return e.target;
  };

  const onMove = (e) => {
    if (mode === 'idle' || !highlight) return;
    const t = targetOf(e);
    if (!t || !t.getBoundingClientRect) { highlight.style.display = 'none'; return; }
    const r = t.getBoundingClientRect();
    highlight.style.display = 'block';
    highlight.style.left = r.left + 'px'; highlight.style.top = r.top + 'px';
    highlight.style.width = r.width + 'px'; highlight.style.height = r.height + 'px';
  };

  const onClick = (e) => {
    if (mode === 'idle') return;
    const t = targetOf(e);
    if (!t) return;  // clicks on the overlay's own controls fall through to their handlers
    e.preventDefault(); e.stopPropagation();
    if (mode === 'pick') { openFormPanel(t); }
    else if (mode === 'waitfor') { window.__aeOverlay.emitWaitFor(t); setMode('idle'); }
    else if (mode === 'makeinput') { openInputPanel(t); }
    else if (mode === 'table') {
      if (!container) { container = t; statusEl.textContent = 'Container set — click each field.'; }
      else { openFieldPanel(t); }
    }
  };

  const install = () => {
    const rootEl = document.documentElement;
    if (!rootEl || document.getElementById(OVERLAY_ID)) return;
    host = el('div'); host.id = OVERLAY_ID;
    host.style.cssText = 'all:initial;position:fixed;z-index:2147483647;';
    rootEl.appendChild(host);
    root = host.attachShadow({ mode: 'open' });

    highlight = el('div', 'position:fixed;z-index:2147483646;pointer-events:none;display:none;' +
      'border:2px solid ' + ACCENT + ';background:' + ACCENT + '22;box-sizing:border-box;');
    root.appendChild(highlight);

    const bar = el('div', 'position:fixed;top:10px;right:10px;width:270px;padding:8px 10px;' +
      'font:12px system-ui;background:#171327ee;color:#e7e2f3;border:1px solid ' + ACCENT + '66;' +
      'border-radius:8px;box-shadow:0 6px 24px #000a;');
    const title = el('div', 'font-weight:600;color:' + ACCENT + ';margin-bottom:6px;', 'Aetherius recorder');
    const tools = el('div', 'margin-bottom:6px;');
    tools.appendChild(button('Pick data', () => setMode('pick')));
    tools.appendChild(button('Pick table', () => setMode('table')));
    tools.appendChild(button('Wait for', () => setMode('waitfor')));
    tools.appendChild(button('Make input', () => setMode('makeinput')));
    doneBtn = button('Done', () => {
      if (container && fields.length) window.__aeOverlay.emitRecords(container, fields, 'records');
      setMode('idle');
    });
    doneBtn.style.display = 'none';
    tools.appendChild(doneBtn);
    tools.appendChild(button('Finish', () => { setMode('idle'); send({ kind: 'finish' }); }));
    statusEl = el('div', 'color:#b9b2d0;min-height:16px;', STATUS.idle);
    panelEl = el('div', 'margin-top:6px;');
    bar.appendChild(title); bar.appendChild(tools); bar.appendChild(statusEl); bar.appendChild(panelEl);
    root.appendChild(bar);

    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('click', onClick, true);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install);
  } else {
    install();
  }
})();
"""
