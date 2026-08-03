/**
 * The injected agent against a simulated DOM.
 *
 * The operation table is where a gap does not break a run but produces **wrong data**, so every
 * value of the `as:` vocabulary is pinned here, corner cases included, next to the locator rules
 * and the auto-waiting that decides when an action may proceed.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { openPage } from "./support.mjs";

const CATALOGUE = `<!doctype html><html><body>
  <h1 id="title">Bonjour <b>Kylian</b> !</h1>
  <p class="price">£23,88</p>
  <p class="stock">Aucun chiffre ici</p>
  <p class="count">12 en stock, 3 reserves</p>
  <img class="avatar" src="/avatar.png" alt="">
  <div class="quote"><span class="text">Citation A</span><small class="author">Auteur A</small></div>
  <div class="quote"><span class="text">Citation B</span><small class="author">Auteur B</small></div>
  <div class="quote"><span class="text">Citation C</span></div>
  <p class="hidden" style="display: none">invisible</p>
  <a href="/next" id="next">Page suivante</a>
  <button id="disabled" disabled>Indisponible</button>
</body></html>`;

const pages = { "/": CATALOGUE, "/next": "<html><body><h1>Suite</h1></body></html>" };

async function extract(host, outputs) {
  return host.call("extract", { outputs }, 3000);
}

test("as: text trims and reads rendered text, hidden content excluded", async () => {
  const opened = await openPage(pages);
  try {
    const read = await extract(opened.host, {
      titre: { selector: "#title", as: "text" },
      cache: { selector: "body", as: "text" },
    });
    assert.equal(read.titre, "Bonjour Kylian !");
    assert.ok(!read.cache.includes("invisible"), "hidden text must not be read");
  } finally {
    await opened.close();
  }
});

test("as: number takes the first number, decimal comma included, and null when there is none", async () => {
  const opened = await openPage(pages);
  try {
    const read = await extract(opened.host, {
      prix: { selector: ".price", as: "number" },
      premier: { selector: ".count", as: "number" },
      aucun: { selector: ".stock", as: "number" },
    });
    assert.equal(read.prix, 23.88);
    assert.equal(read.premier, 12, "the first number, not the last");
    assert.equal(read.aucun, null);
  } finally {
    await opened.close();
  }
});

test("as: html, attr and count", async () => {
  const opened = await openPage(pages);
  try {
    const read = await extract(opened.host, {
      html: { selector: "#title", as: "html" },
      src: { selector: "img.avatar", as: "attr", attr: "src" },
      absent: { selector: "img.avatar", as: "attr", attr: "data-nope" },
      combien: { selector: ".quote", as: "count" },
      zero: { selector: ".rien-du-tout", as: "count" },
    });
    assert.equal(read.html, "Bonjour <b>Kylian</b> !");
    assert.equal(read.src, "/avatar.png");
    assert.equal(read.absent, null, "a missing attribute is null, as get_attribute returns None");
    assert.equal(read.combien, 3, "count counts every match, it does not read the first");
    assert.equal(read.zero, 0, "zero is an answer, not a failure");
  } finally {
    await opened.close();
  }
});

test("as: list reads every match, item deciding the type", async () => {
  const opened = await openPage(pages);
  try {
    const read = await extract(opened.host, {
      textes: { selector: ".quote .text", as: "list" },
      liens: { selector: "a", as: "list", item: "attr", attr: "href" },
    });
    assert.deepEqual(read.textes, ["Citation A", "Citation B", "Citation C"]);
    assert.deepEqual(read.liens, ["/next"]);
  } finally {
    await opened.close();
  }
});

test("each/fields: a missing field names itself instead of producing a wrong record", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(
      extract(opened.host, {
        citations: {
          each: ".quote",
          fields: {
            texte: { selector: ".text", as: "text" },
            auteur: { selector: ".author", as: "text" },
          },
        },
      }),
      (error) => {
        // `ExtractionError`, not `ActionError`: the field is missing from the page, so the fix is
        // in the Blueprint — not a bug to report (see failure.ts).
        assert.equal(error.name, "ExtractionError");
        assert.match(error.message, /"auteur"/);
        assert.match(error.message, /\.author/);
        return true;
      },
    );
  } finally {
    await opened.close();
  }
});

test("each/fields with every field present reads the whole table", async () => {
  const opened = await openPage({
    "/": `<html><body>
      <div class="row"><span class="t">A</span><span class="p">1,50</span></div>
      <div class="row"><span class="t">B</span><span class="p">2</span></div>
    </body></html>`,
  });
  try {
    const read = await extract(opened.host, {
      lignes: {
        each: ".row",
        fields: { titre: { selector: ".t", as: "text" }, prix: { selector: ".p", as: "number" } },
      },
    });
    assert.deepEqual(read.lignes, [
      { titre: "A", prix: 1.5 },
      { titre: "B", prix: 2 },
    ]);
  } finally {
    await opened.close();
  }
});

test("each with no container yields an empty list, as page.locator(each).all() does", async () => {
  const opened = await openPage(pages);
  try {
    const read = await extract(opened.host, {
      rien: { each: ".pas-de-conteneur", fields: { x: { selector: "span", as: "text" } } },
    });
    assert.deepEqual(read.rien, []);
  } finally {
    await opened.close();
  }
});

test("an unknown as: names the vocabulary it did not match", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(extract(opened.host, { x: { selector: "#title", as: "colour" } }), {
      name: "ActionError",
      message: /text, number, html, attr, list or count/,
    });
  } finally {
    await opened.close();
  }
});

test("as: attr without an attr name is refused", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(extract(opened.host, { x: { selector: "img", as: "attr" } }), {
      name: "ActionError",
      message: /requires an 'attr' name/,
    });
  } finally {
    await opened.close();
  }
});

test("the three locator kinds resolve the same element", async () => {
  const opened = await openPage(pages);
  try {
    const css = await extract(opened.host, { v: { selector: "#next", as: "text" } });
    const xpath = await extract(opened.host, {
      v: { selector: "//a[@id='next']", selector_type: "xpath", as: "text" },
    });
    assert.equal(css.v, "Page suivante");
    assert.equal(xpath.v, "Page suivante");
    // The text locator lives on the action path, where strict mode applies.
    await opened.host.call("hover", { selector: "Page suivante", selector_type: "text" }, 3000);
  } finally {
    await opened.close();
  }
});

test("an xpath= prefix is accepted, as the Python engine adds one", async () => {
  const opened = await openPage(pages);
  try {
    const read = await extract(opened.host, {
      v: { selector: "xpath=//a[@id='next']", selector_type: "xpath", as: "text" },
    });
    assert.equal(read.v, "Page suivante");
  } finally {
    await opened.close();
  }
});

test("acting on several matches is refused; waiting and reading take the first", async () => {
  const opened = await openPage(pages);
  try {
    // Refused at once, and named `ExtractionError`: waiting will not disambiguate a selector, and
    // the fix is in the Blueprint, not in the engine.
    await assert.rejects(opened.host.call("click", { selector: ".quote" }, 1000), {
      name: "ExtractionError",
      message: /matched 3 elements/,
    });
    // Waiting is about presence, so several matches are normal there.
    await opened.host.call("wait_for", { selector: ".quote", state: "visible" }, 1000);
    const read = await extract(opened.host, { premier: { selector: ".quote .text", as: "text" } });
    assert.equal(read.premier, "Citation A");
  } finally {
    await opened.close();
  }
});

test("acting on nothing waits for it, then fails at its deadline", async () => {
  // Zero matches is a *not yet*: a portal that renders its form a few hundred milliseconds after
  // load is the normal case, and Playwright — so the Python engine — waits. Failing on the first
  // look would defeat the auto-waiting this agent exists to provide.
  const opened = await openPage(pages);
  try {
    const started = Date.now();
    await assert.rejects(opened.host.call("click", { selector: ".absent" }, 400), {
      name: "StepTimeoutError",
    });
    assert.ok(Date.now() - started >= 300, "the action failed before waiting");
  } finally {
    await opened.close();
  }
});

test("an element that appears late is acted on, not missed", async () => {
  const opened = await openPage({ "/": `<html><body><div id="slot"></div></body></html>` });
  try {
    const clicking = opened.host.call("click", { selector: "#late" }, 2000);
    setTimeout(() => {
      opened.page.window.document.getElementById("slot").innerHTML =
        '<button id="late">Go</button>';
    }, 150);
    assert.deepEqual(await clicking, {});
  } finally {
    await opened.close();
  }
});

test("wait_for succeeds after a mutation", async () => {
  const opened = await openPage({ "/": `<html><body><div id="slot"></div></body></html>` });
  try {
    const waiting = opened.host.call("wait_for", { selector: ".late", state: "visible" }, 3000);
    setTimeout(() => {
      opened.page.window.document.getElementById("slot").innerHTML = '<span class="late">ok</span>';
    }, 120);
    assert.deepEqual(await waiting, {});
  } finally {
    await opened.close();
  }
});

test("wait_for expires with the Blueprint's named failure code", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(
      opened.host.call(
        "wait_for",
        { selector: ".jamais", state: "visible", fail_code: "LOGIN_FAILED" },
        400,
      ),
      (error) => {
        assert.equal(error.name, "StepTimeoutError");
        assert.equal(error.code, "LOGIN_FAILED");
        assert.match(error.message, /wait_for timed out for selector/);
        return true;
      },
    );
  } finally {
    await opened.close();
  }
});

test("wait_for honours hidden and detached", async () => {
  const opened = await openPage({
    "/": `<html><body><div id="spinner">chargement</div></body></html>`,
  });
  try {
    const hidden = opened.host.call("wait_for", { selector: "#spinner", state: "hidden" }, 3000);
    setTimeout(() => {
      opened.page.window.document.getElementById("spinner").style.display = "none";
    }, 120);
    assert.deepEqual(await hidden, {});

    const detached = opened.host.call("wait_for", { selector: "#spinner", state: "detached" }, 3000);
    setTimeout(() => {
      opened.page.window.document.getElementById("spinner").remove();
    }, 120);
    assert.deepEqual(await detached, {});
  } finally {
    await opened.close();
  }
});

test("an unknown wait_for state names the four it knows", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(opened.host.call("wait_for", { selector: "body", state: "sideways" }, 500), {
      name: "ActionError",
      message: /visible, attached, hidden or detached/,
    });
  } finally {
    await opened.close();
  }
});

test("an action waits for its target to become visible and enabled", async () => {
  const opened = await openPage({
    "/": `<html><body><button id="go" style="display: none" disabled>Go</button></body></html>`,
  });
  try {
    const clicking = opened.host.call("click", { selector: "#go" }, 3000);
    setTimeout(() => {
      const button = opened.page.window.document.getElementById("go");
      button.style.display = "";
      button.disabled = false;
    }, 150);
    assert.deepEqual(await clicking, {});
  } finally {
    await opened.close();
  }
});

test("an action that never becomes actionable fails saying so", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(opened.host.call("click", { selector: "#disabled" }, 400), {
      name: "StepTimeoutError",
      message: /never became visible and enabled/,
    });
  } finally {
    await opened.close();
  }
});

test("an invalid CSS selector is named, not swallowed", async () => {
  const opened = await openPage(pages);
  try {
    await assert.rejects(extract(opened.host, { x: { selector: "div[", as: "text" } }), {
      name: "ActionError",
      message: /invalid CSS selector/,
    });
  } finally {
    await opened.close();
  }
});
