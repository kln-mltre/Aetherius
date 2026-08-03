/**
 * `evaluate` — the one place a Blueprint's own text becomes source.
 *
 * Everywhere else, a parameter crosses encoded as JSON and the injected script is a constant. That
 * rule is what makes impossible-by-construction the commonest bug of hand-written WebViews. Here it
 * cannot hold: `script` *is* code by contract (the action's whole purpose is to run it), so it is
 * interpolated. Its `arg` is not — it crosses as a JSON literal, like every other parameter.
 *
 * Keeping this in a file of its own is deliberate: the exception should be visible, reviewable, and
 * impossible to generalise by accident.
 *
 * The function-or-expression rule is Playwright's, reproduced so the same Blueprint works on both
 * engines: `"() => document.title"` is called with `arg`; `"document.title"` is evaluated as an
 * expression. `undefined` becomes `null`, because JSON cannot carry the first and Python's
 * `page.evaluate` returns `None` for it.
 */

import { AGENT_GLOBAL } from "./protocol.js";

export function evaluateSource(id: string, script: string, arg: unknown): string {
  const idLiteral = JSON.stringify(id);
  // `arg` may be undefined; JSON.stringify would yield the literal `undefined`, which is not JSON.
  const argLiteral = arg === undefined ? "null" : JSON.stringify(arg);
  const reply = `window.${AGENT_GLOBAL}.reply`;

  return (
    `(function () {\n` +
    `  var __id = ${idLiteral};\n` +
    `  var __fail = function (error) {\n` +
    `    ${reply}(__id, { ok: false, error: { name: "ActionError",\n` +
    `      message: "evaluate: " + String((error && error.message) || error) } });\n` +
    `  };\n` +
    `  try {\n` +
    `    var __arg = ${argLiteral};\n` +
    `    var __value = (${script});\n` +
    `    if (typeof __value === "function") __value = __value(__arg);\n` +
    `    Promise.resolve(__value).then(function (resolved) {\n` +
    `      ${reply}(__id, { ok: true, value: resolved === undefined ? null : resolved });\n` +
    `    }, __fail);\n` +
    `  } catch (error) { __fail(error); }\n` +
    `})();\n` +
    `true;`
  );
}
