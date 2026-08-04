/**
 * Un passage sur le manifeste : ce qu'on garde, ce qu'on remplace, ce qu'on laisse tomber.
 *
 * Extrait du registre parce que c'est la seule partie qui **parle au reseau**, et qu'elle a sa
 * propre regle, tenue ligne apres ligne : **un refus ne remplace jamais la version en place**. Une
 * garde qui mordrait en detruisant ce qui marchait serait une panne de plus, pas une protection.
 *
 * La fonction ne touche a rien : elle rend le rapport et, quand le manifeste a pu etre lu, la
 * nouvelle surcouche. C'est l'appelant qui la publie — un seul endroit ou l'etat change.
 */

import { hostFetch, type FetchLike } from "@aetherius/engine";

import { fetchText } from "./download.js";
import { parseManifest, resolveUrl } from "./manifest.js";
import type {
  CachedBlueprint,
  RefreshEntry,
  RefreshReport,
  RegistryConfig,
} from "./types.js";
import { verify, type Bounds } from "./verify.js";

const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_MAX_BYTES = 512 * 1024;

export interface RefreshOutput {
  readonly report: RefreshReport;
  /** La surcouche a publier. Absente quand le manifeste n'a pas pu etre lu : on ne touche a rien. */
  readonly kept?: Record<string, CachedBlueprint>;
}

export async function refreshOverlay(
  config: RegistryConfig,
  previous: Readonly<Record<string, CachedBlueprint>>,
  bounds: (bundledVersion: string) => Bounds,
): Promise<RefreshOutput> {
  const url = config.manifest;
  if (config.remote === false) return { report: unread("remote delivery is switched off") };
  if (url === undefined) return { report: unread("no manifest URL") };

  const fetcher: FetchLike | undefined = config.fetch ?? hostFetch();
  if (fetcher === undefined) return { report: unread("this host has no fetch") };

  const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxBytes = config.maxBytes ?? DEFAULT_MAX_BYTES;

  let manifest;
  try {
    manifest = parseManifest(await fetchText(fetcher, url, timeoutMs, maxBytes));
  } catch (error) {
    return { report: unread(reasonOf(error)) };
  }

  const kept: Record<string, CachedBlueprint> = {};
  const entries: RefreshEntry[] = [];

  for (const [name, entry] of Object.entries(manifest.blueprints)) {
    const bundled = config.bundled[name];
    if (bundled === undefined) {
      entries.push({ name, outcome: "ignored", reason: "not bundled in this application" });
      continue;
    }
    if (manifest.disabled || entry.disabled) {
      entries.push({ name, outcome: "ignored", reason: "disabled by the manifest" });
      continue;
    }

    const known = previous[name];
    if (known?.version === entry.version && known.sha256 === entry.sha256) {
      kept[name] = known;
      entries.push({ name, outcome: "kept", version: known.version });
      continue;
    }

    let text: string;
    try {
      text = await fetchText(fetcher, resolveUrl(url, entry.url), timeoutMs, maxBytes);
    } catch (error) {
      if (known !== undefined) kept[name] = known;
      entries.push({ name, outcome: "rejected", reason: reasonOf(error) });
      continue;
    }

    const verdict = verify(
      { name, version: entry.version, sha256: entry.sha256, text, minEngine: entry.minEngine },
      bounds(bundled.version),
    );
    if (!verdict.ok) {
      if (known !== undefined) kept[name] = known;
      entries.push({ name, outcome: verdict.outcome, reason: verdict.reason });
      continue;
    }

    kept[name] = {
      name,
      version: entry.version,
      sha256: entry.sha256,
      text,
      ...(entry.minEngine !== undefined ? { min_engine: entry.minEngine } : {}),
      fetched_at: new Date().toISOString(),
    };
    entries.push({ name, outcome: "updated", version: entry.version });
  }

  // Le manifeste decrit l'etat voulu : ce qui n'y est plus revient a l'embarque, comme une entree
  // desactivee. L'interpretation la plus sure d'un manifeste partiel est toujours le socle.
  for (const name of Object.keys(previous)) {
    if (kept[name] === undefined && manifest.blueprints[name] === undefined) {
      entries.push({ name, outcome: "ignored", reason: "gone from the manifest — back to bundled" });
    }
  }

  return { report: { ok: true, entries }, kept };
}

function unread(reason: string): RefreshReport {
  return { ok: false, reason, entries: [] };
}

function reasonOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
