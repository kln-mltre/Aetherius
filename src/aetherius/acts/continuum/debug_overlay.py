"""Client-side debug overlay: a visible cursor and a red click ripple.

Injected via Playwright's ``add_init_script`` when ``options.debug`` is on, so it re-installs on
every navigation. It listens to the real mouse events Playwright dispatches, so the cursor tracks
where the bot moves and a red ripple marks every click. Purely a debug aid — never loaded otherwise,
and unrelated to the discretion layer (which does the opposite: hide automation).
"""

from __future__ import annotations

# A self-invoking script (add_init_script evaluates verbatim, it does not call a returned function).
# Guarded by a window flag so repeated injection on the same document is a no-op.
DEBUG_OVERLAY_JS = """
(() => {
  if (window.__aetheriusDebugOverlay) return;
  window.__aetheriusDebugOverlay = true;
  const install = () => {
    const root = document.documentElement;
    if (!root) return;
    const style = document.createElement('style');
    style.textContent = `
      .__ae-cursor {
        position: fixed; z-index: 2147483647; pointer-events: none;
        width: 20px; height: 20px; margin: -10px 0 0 -10px; opacity: 0;
        border: 2px solid rgba(224,48,48,0.95); border-radius: 50%;
        background: rgba(224,48,48,0.20);
        box-shadow: 0 0 8px 2px rgba(224,48,48,0.55);
        transition: opacity 0.25s linear;
      }
      .__ae-ripple {
        position: fixed; z-index: 2147483647; pointer-events: none;
        width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%;
        background: rgba(224,48,48,0.6);
        animation: __ae-ripple-anim 0.65s ease-out forwards;
      }
      @keyframes __ae-ripple-anim {
        0%   { transform: scale(1);  opacity: 0.9; }
        100% { transform: scale(6);  opacity: 0;   }
      }
    `;
    root.appendChild(style);
    const cursor = document.createElement('div');
    cursor.className = '__ae-cursor';
    root.appendChild(cursor);
    document.addEventListener('mousemove', (e) => {
      cursor.style.opacity = '1';
      cursor.style.left = e.clientX + 'px';
      cursor.style.top = e.clientY + 'px';
    }, true);
    document.addEventListener('mousedown', (e) => {
      const ripple = document.createElement('div');
      ripple.className = '__ae-ripple';
      ripple.style.left = e.clientX + 'px';
      ripple.style.top = e.clientY + 'px';
      root.appendChild(ripple);
      setTimeout(() => ripple.remove(), 700);
    }, true);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install);
  } else {
    install();
  }
})();
"""
