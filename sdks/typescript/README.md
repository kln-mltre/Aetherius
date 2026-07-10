# @aetherius/client

Thin TypeScript client for the Aetherius daemon. Load an existing Blueprint, run it, and stream its
events — from any Node process. The Console is never involved at runtime; execution is fully
code-driven.

The engine is Python. This client talks to the local **daemon** (`aetherius serve`) over HTTP +
WebSocket. It either spawns a daemon for you or targets one you already run. The wire contracts live
in [`contracts/`](../../contracts) (OpenAPI + the events schema) and are the source of truth.

## Requirements

- Node 20+.
- The Aetherius Python package installed and on `PATH` (so the client can spawn `aetherius serve`),
  unless you point the client at an already-running daemon via `baseUrl`.

## Install

```bash
npm install @aetherius/client
```

## Usage

Spawn a local daemon automatically, run a Blueprint, stream events:

```ts
import { Aetherius } from "@aetherius/client";

const client = new Aetherius();
try {
  const result = await client.run("blueprints/ukit-planning-week.blueprint.json", {
    inputs: { group: "TP-A1", monday: "2026-09-07" },
    onEvent: (event) => console.log(event.type, event.message ?? ""),
  });
  console.log(result.status, result.outputs);
} finally {
  await client.close(); // stops the daemon this client spawned
}
```

A Blueprint may be a path the daemon resolves, or an inline object:

```ts
const result = await client.run({ aetherius: "1.0", name: "demo", act: "vector", steps: [/* ... */] });
```

Target an already-running daemon (no spawn, no `close()` teardown needed):

```ts
const client = new Aetherius({ baseUrl: "http://127.0.0.1:8787", token: "s3cr3t" });
```

Subscribe to a run's events on their own (resolves when the run finishes):

```ts
await client.onEvent(runId, (event) => console.log(event));
```

## Configuration

`new Aetherius(config)`:

| Option           | Default                 | Purpose                                                              |
| ---------------- | ----------------------- | ------------------------------------------------------------------- |
| `baseUrl`        | spawn a local daemon    | Target an already-running daemon instead of spawning one.           |
| `token`          | none                    | Bearer token, when the daemon is started with one.                  |
| `command`        | `["aetherius", "serve"]`| argv to spawn the daemon (e.g. `["python3", "-m", "aetherius", "serve"]`). |
| `startTimeoutMs` | `10000`                 | How long to wait for the spawned daemon to become healthy.          |

## Development

```bash
npm run build   # tsc, emits dist/
npm test        # build + node --test (unit transport tests + a real spawn E2E)
```

The E2E test skips cleanly when the Aetherius package is not importable. From the repo root,
`make test-ts` runs the same thing.
