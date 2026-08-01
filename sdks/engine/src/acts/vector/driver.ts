/**
 * Act I — Vector, mirror of `src/aetherius/acts/vector/driver.py`.
 *
 * The lightest Act, and the one that needs nothing from the platform beyond `fetch`: it is what
 * makes a Blueprint run on a phone at all. It executes `http.request` and hands every other action
 * to the shared, act-agnostic handlers.
 *
 * Absent by design, and each for its own reason: the network identity layer (`options.proxy`,
 * TLS impersonation, fingerprint headers) is out of the phase's scope — on a device every user
 * already leaves from their own connection; and `extract` as a standalone step is declared by the
 * capability table but dispatched by no driver, on either engine (`PENDING_ACTIONS`).
 */

import type { StepModel } from "../../blueprint/types.js";
import type { ActDriver, HostServices, Renderer, RunContext } from "../../driver.js";
import { ActionError } from "../../errors.js";
import type { EventBus } from "../../events/index.js";
import { pythonRepr, pythonStr } from "../../expr/index.js";
import { dispatchExtract } from "../../extraction/index.js";
import { sharedAction } from "../shared.js";
import { VectorClient } from "./client.js";

export class VectorDriver implements ActDriver {
  readonly act = "vector";

  private client: VectorClient | undefined;

  constructor(private readonly host: HostServices = {}) {}

  async setup(ctx: RunContext): Promise<void> {
    const options = ctx.blueprint.options ?? {};
    this.client = new VectorClient({
      fetch: this.host.fetch,
      // `|| undefined` rather than `??`: Python reads `opts.timeout_ms or 30_000`, so a zero means
      // "unset" there too.
      timeoutMs: options.timeout_ms || undefined,
      retries: options.retries,
    });
    await this.client.setup();
  }

  async teardown(): Promise<void> {
    this.client = undefined;
  }

  async runStep(
    step: StepModel,
    ctx: RunContext,
    bus: EventBus,
    render: Renderer,
  ): Promise<Record<string, unknown>> {
    if (step.action === "http.request") return this.httpRequest(step, render);

    const shared = sharedAction(step.action);
    if (shared !== undefined) return shared(step, ctx, bus, render);

    // No plugin registry on this engine (docs/embedded.md): an unknown action is unknown, and the
    // validator has already refused every action the capability table does not carry.
    throw new ActionError(`VectorDriver: unsupported action ${pythonRepr(step.action)}`);
  }

  private async httpRequest(step: StepModel, render: Renderer): Promise<Record<string, unknown>> {
    const client = this.client;
    if (client === undefined) throw new ActionError("VectorDriver: setup() was never called.");

    const expect = asObject(render(step["expect"] ?? {}));
    const status = expect["status"];

    const response = await client.request({
      method: String(render(step["method"] ?? "GET")),
      url: String(render(step["url"] ?? "")),
      headers: headerMap(render(step["headers"] ?? {})),
      // Presence is decided after rendering, exactly as in Python: `"json": null` renders to null
      // and means "no body", it does not clash with a `form`.
      json: has(step, "json") ? render(step["json"]) : undefined,
      form: has(step, "form") ? render(step["form"]) : undefined,
      params: asOptionalObject(render(step["params"])),
      expectedStatus: typeof status === "number" ? status : undefined,
    });

    const outputs: Record<string, unknown> = {
      status_code: response.status,
      headers: response.headers,
    };

    const specs = asObject(step["extract"] ?? {});
    // Extraction specs are taken verbatim — a selector or a JSONPath is never rendered, on either
    // engine (see core/extraction/dispatch.py).
    if (Object.keys(specs).length > 0) Object.assign(outputs, dispatchExtract(response.body, specs));
    return outputs;
  }
}

function headerMap(value: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, item] of Object.entries(asObject(value))) out[name] = pythonStr(item);
  return out;
}

function asObject(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asOptionalObject(value: unknown): Record<string, unknown> | undefined {
  return value !== null && value !== undefined && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function has(step: StepModel, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(step, key);
}
