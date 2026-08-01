/**
 * Per-run driver lifecycle, mirror of `src/aetherius/core/runtime/drivers.py`.
 *
 * Drivers are instantiated and set up on demand — at the first step that needs them — and torn
 * down together at the end of the run.
 *
 * Where Python names its four drivers in a `match`, this engine keeps a **registry**. The reason
 * is the package boundary: `@aetherius/engine` is platform-neutral, and the Continuum driver needs
 * a WebView, so it will ship in `@aetherius/react-native` (milestone 3-D) and register itself
 * there. Without the registry the neutral package would have to import a platform one, which is
 * exactly the dependency the phase set out to avoid.
 *
 * Not ported: the subsumption of the browser Acts into a single instance. It exists so Acts II/III/
 * IV share one browser; here there is one Act.
 */

import { isEmbeddedAct } from "../blueprint/capabilities.js";
import type { ActDriver, DriverFactory, HostServices, RunContext } from "../driver.js";
import { ActionError } from "../errors.js";
import { VectorDriver } from "../acts/vector/driver.js";
import type { DriverResolver } from "./steps.js";

const REGISTRY = new Map<string, DriverFactory>([
  ["vector", (host: HostServices) => new VectorDriver(host)],
]);

/**
 * Register the driver for *act*, replacing any previous one.
 *
 * The seam `@aetherius/react-native` uses to add Continuum without this package knowing it exists.
 */
export function registerDriver(act: string, factory: DriverFactory): void {
  REGISTRY.set(act, factory);
}

/** The acts a driver is registered for, in registration order. */
export function registeredActs(): readonly string[] {
  return [...REGISTRY.keys()];
}

export class DriverManager implements DriverResolver {
  private readonly drivers = new Map<string, ActDriver>();

  constructor(private readonly host: HostServices) {}

  /** The live driver for *act*, instantiated and set up on first use. */
  async resolveDriver(act: string, ctx: RunContext): Promise<ActDriver> {
    const existing = this.drivers.get(act);
    if (existing !== undefined) return existing;

    const factory = REGISTRY.get(act);
    if (factory === undefined) throw noDriver(act);

    const driver = factory(this.host);
    await driver.setup(ctx);
    this.drivers.set(act, driver);
    return driver;
  }

  /** Tear every live driver down, newest first; the first error propagates after all have run. */
  async teardownAll(ctx: RunContext): Promise<void> {
    const drivers = [...this.drivers.values()].reverse();
    this.drivers.clear();
    let first: unknown;
    for (const driver of drivers) {
      try {
        await driver.teardown(ctx);
      } catch (error) {
        // One failing teardown must not skip the others: a leaked WebView outlives the run.
        first = first ?? error;
      }
    }
    if (first !== undefined) throw first;
  }
}

/**
 * Say which of the two problems it is: an act this engine never runs (the validator already said
 * so, in better words), or one it validates but whose driver has not been brought in.
 */
function noDriver(act: string): ActionError {
  if (isEmbeddedAct(act)) {
    return new ActionError(
      `Act '${act}' is accepted by this engine but no driver is registered for it: ` +
        "import '@aetherius/react-native', which registers the WebView driver.",
    );
  }
  return new ActionError(
    `Act '${act}' is not implemented by the embedded engine. Registered acts: ` +
      `${registeredActs().join(", ")}.`,
  );
}
