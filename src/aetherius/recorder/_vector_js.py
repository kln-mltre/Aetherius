"""In-page capture for the Vector recorder: observe API calls, pick a request and its JSON fields.

Symmetric with the DOM recorder, but for Act I. It patches ``fetch``/``XMLHttpRequest`` (and treats a
JSON *document* — navigating straight to an API URL — as a request too), lists the JSON responses in a
floating panel, and lets the user turn one into an ``http.request`` + JSONPath extraction. The panel
shows a **structured summary** of the response (a top-level array → "extract N records" with
auto-detected scalar fields; an object → a chip per key) rather than an infinite tree: simpler, and it
matches real API shapes (a list of records, or an object of fields/arrays).

Everything funnels through ``window.__aeVector.emit(request, extract)``, which the panel calls and
integration tests drive directly. The Python side (:mod:`.vector_backend`) turns it into a Blueprint.
"""

from __future__ import annotations

# Self-invoking, guarded. Emits through the shared __aetherius_capture binding with the http_request
# kind. Auth-bearing headers are handled Python-side (turned into secrets), never stored literally.
VECTOR_JS = r"""
(() => {
  if (window.__aeVector) return;
  const OVERLAY_ID = '__ae-recorder-overlay';
  const ACCENT = '#c9a94a';
  const requests = [];
  const send = (p) => { try { window.__aetherius_capture(JSON.stringify(p)); } catch (e) {} };

  const headersToObj = (h) => {
    const o = {};
    try {
      if (h && typeof h.forEach === 'function') h.forEach((v, k) => { o[k] = v; });
      else if (h && typeof h === 'object') Object.assign(o, h);
    } catch (e) {}
    return o;
  };
  const bodyToStr = (b) => (b == null ? null : (typeof b === 'string' ? b : null));

  let refresh = () => {};
  const record = (r) => {
    if ((r.contentType || '').includes('json')) { requests.push(r); refresh(); }
  };

  const origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (...args) {
      const arg0 = args[0], init = args[1] || {};
      const url = (typeof arg0 === 'string') ? arg0 : (arg0 && arg0.url) || '';
      const method = (init.method || (arg0 && arg0.method) || 'GET').toUpperCase();
      const headers = headersToObj(init.headers);
      const body = bodyToStr(init.body);
      return origFetch.apply(this, args).then((resp) => {
        const ct = resp.headers.get('content-type') || '';
        resp.clone().text()
          .then((text) => record({ method, url, headers, body, status: resp.status, contentType: ct, responseText: text }))
          .catch(() => {});
        return resp;
      });
    };
  }

  const xOpen = XMLHttpRequest.prototype.open, xSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__ae = { method: (m || 'GET').toUpperCase(), url: u };
    return xOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (b) {
    const xhr = this, info = xhr.__ae || {};
    xhr.addEventListener('load', () => {
      const ct = xhr.getResponseHeader('content-type') || '';
      record({ method: info.method, url: info.url, headers: {}, body: bodyToStr(b),
               status: xhr.status, contentType: ct, responseText: xhr.responseText });
    });
    return xSend.apply(this, arguments);
  };

  window.__aeVector = {
    requests,
    emit(request, extract) { send({ kind: 'http_request', request, extract }); },
  };

  // ── UI ──────────────────────────────────────────────────────────────────────
  const el = (tag, css, text) => {
    const n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text != null) n.textContent = text;
    return n;
  };
  const chip = (label, onclick) => {
    const b = el('button', 'margin:2px;padding:3px 7px;font:12px system-ui;cursor:pointer;' +
      'border-radius:5px;border:1px solid ' + ACCENT + '55;background:#1c1830;color:#e7e2f3;', label);
    b.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); onclick(); });
    return b;
  };

  const scalarFields = (obj) => {  // { key: '$.key' } for each scalar field of a sample record
    const out = {};
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      for (const k of Object.keys(obj)) {
        const v = obj[k];
        if (v == null || typeof v !== 'object') out[k] = '$.' + k;
      }
    }
    return out;
  };

  let host, root, statusEl, listEl, detailEl;
  const setStatus = (t) => { if (statusEl) statusEl.textContent = t; };

  const pickRecords = (request, path, sample, name) => {
    window.__aeVector.emit(request, { name, path, fields: scalarFields(sample) });
    setStatus('Added records "' + name + '". Pick more, or Finish.');
  };
  const pickValue = (request, path, name) => {
    window.__aeVector.emit(request, { name, path });
    setStatus('Added "' + name + '". Pick more, or Finish.');
  };

  const showDetail = (request) => {
    detailEl.innerHTML = '';
    let data;
    try { data = JSON.parse(request.responseText); } catch (e) { detailEl.textContent = 'Not JSON.'; return; }
    detailEl.appendChild(el('div', 'color:' + ACCENT + ';margin:4px 0;', request.method + ' ' + request.url));
    if (Array.isArray(data)) {
      detailEl.appendChild(chip('Extract ' + data.length + ' records', () =>
        pickRecords(request, '$[*]', data[0], 'records')));
    } else if (data && typeof data === 'object') {
      for (const k of Object.keys(data)) {
        const v = data[k];
        if (Array.isArray(v)) {
          detailEl.appendChild(chip(k + ' (' + v.length + ' records)', () =>
            pickRecords(request, '$.' + k + '[*]', v[0], k)));
        } else if (v == null || typeof v !== 'object') {
          detailEl.appendChild(chip(k, () => pickValue(request, '$.' + k, k)));
        }
      }
    } else {
      detailEl.appendChild(chip('Extract value', () => pickValue(request, '$', 'value')));
    }
  };

  const install = () => {
    if (!document.documentElement || document.getElementById(OVERLAY_ID)) return;
    host = el('div'); host.id = OVERLAY_ID; host.style.cssText = 'all:initial;position:fixed;z-index:2147483647;';
    document.documentElement.appendChild(host);
    root = host.attachShadow({ mode: 'open' });
    const bar = el('div', 'position:fixed;top:10px;right:10px;width:320px;max-height:80vh;overflow:auto;' +
      'padding:8px 10px;font:12px system-ui;background:#171327ee;color:#e7e2f3;' +
      'border:1px solid ' + ACCENT + '66;border-radius:8px;box-shadow:0 6px 24px #000a;');
    bar.appendChild(el('div', 'font-weight:600;color:' + ACCENT + ';', 'Aetherius recorder — API'));
    statusEl = el('div', 'color:#b9b2d0;margin:4px 0;', 'Browse to trigger API calls, then pick one.');
    bar.appendChild(statusEl);
    bar.appendChild(el('div', 'color:#8f88a8;margin-top:4px;', 'Requests'));
    listEl = el('div'); bar.appendChild(listEl);
    detailEl = el('div', 'margin-top:6px;border-top:1px solid #ffffff22;padding-top:4px;'); bar.appendChild(detailEl);
    bar.appendChild(chip('Finish', () => send({ kind: 'finish' })));
    root.appendChild(bar);

    refresh = () => {
      listEl.innerHTML = '';
      requests.slice(-12).forEach((r) => {
        const label = r.method + ' ' + (r.url.length > 34 ? '…' + r.url.slice(-33) : r.url);
        listEl.appendChild(chip(label, () => showDetail(r)));
      });
    };
    refresh();
    if ((document.contentType || '').includes('json')) {
      record({ method: 'GET', url: location.href, headers: {}, body: null,
               status: 200, contentType: 'application/json',
               responseText: document.body ? document.body.textContent : '' });
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
"""
