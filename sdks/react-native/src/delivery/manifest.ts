/**
 * Le manifeste : ce qu'un publieur ecrit, et ce que l'appareil accepte d'en lire.
 *
 * C'est un contrat **applicatif** — le seul que ce jalon ajoute —, specifie dans docs/embedded.md.
 * Le parseur est **strict** : une cle inconnue, un type inattendu ou une version non numerique fait
 * refuser le manifeste entier. La raison n'est pas le purisme : une faute de frappe dans
 * `disabled` ou dans `sha256` ne doit pas pouvoir **desactiver une garde en silence**. Un manifeste
 * refuse ne remplace rien, donc l'application continue sur ce qu'elle avait.
 *
 * Le refus est une `ManifestError`, qui herite de `BlueprintError` : si elle s'echappait un jour
 * jusqu'a `describeFailure`, elle tomberait dans la famille `blueprint` — « le fichier est faux,
 * ne pas reessayer ». En pratique elle ne s'echappe pas : `refresh()` la contient et la rapporte.
 */

import { BlueprintError } from "@aetherius/engine";

import type { Manifest, ManifestEntry } from "./types.js";

/** La version de format que ce moteur sait lire. */
export const MANIFEST_FORMAT = "1";

export class ManifestError extends BlueprintError {}

const MANIFEST_KEYS = new Set(["manifest", "generated_at", "disabled", "blueprints"]);
const ENTRY_KEYS = new Set(["version", "url", "sha256", "min_engine", "disabled"]);

/** Chaine numerique pointee : `"2"`, `"1.4"`, `"0.4.0"`. Ordonnee, donc comparable. */
const VERSION = /^[0-9]+(\.[0-9]+)*$/;
const SHA256 = /^[0-9a-f]{64}$/;

/**
 * Cles qu'un document JSON ne peut pas porter sans intention.
 *
 * `JSON.parse` produit bien une propriete ordinaire pour `__proto__`, mais la recopier dans un objet
 * litteral ne l'est plus. Les refuser vaut mieux que compter sur le fait qu'on ne les recopiera
 * jamais.
 */
const POISONED = new Set(["__proto__", "constructor", "prototype"]);

function asObject(value: unknown, what: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ManifestError(`Manifest: ${what} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function requireKeys(source: Record<string, unknown>, allowed: Set<string>, what: string): void {
  for (const key of Object.keys(source)) {
    if (!allowed.has(key)) {
      throw new ManifestError(
        `Manifest: unknown key '${key}' in ${what} (allowed: ${[...allowed].join(", ")}).`,
      );
    }
  }
}

function requireString(value: unknown, what: string, pattern?: RegExp): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new ManifestError(`Manifest: ${what} must be a non-empty string.`);
  }
  if (pattern !== undefined && !pattern.test(value)) {
    throw new ManifestError(`Manifest: ${what} is malformed ('${value}').`);
  }
  return value;
}

function requireFlag(value: unknown, what: string): boolean {
  if (value === undefined) return false;
  if (typeof value !== "boolean") throw new ManifestError(`Manifest: ${what} must be a boolean.`);
  return value;
}

function parseEntry(name: string, value: unknown): ManifestEntry {
  const source = asObject(value, `entry '${name}'`);
  requireKeys(source, ENTRY_KEYS, `entry '${name}'`);

  const minEngine = source["min_engine"];
  return {
    version: requireString(source["version"], `entry '${name}' version`, VERSION),
    url: requireString(source["url"], `entry '${name}' url`),
    sha256: requireString(source["sha256"], `entry '${name}' sha256`, SHA256),
    ...(minEngine === undefined
      ? {}
      : { minEngine: requireString(minEngine, `entry '${name}' min_engine`, VERSION) }),
    disabled: requireFlag(source["disabled"], `entry '${name}' disabled`),
  };
}

/**
 * Lit un manifeste.
 *
 * @throws {ManifestError} le texte n'est pas un manifeste que ce moteur sache lire — JSON invalide,
 * format inconnu, ou champ malforme.
 */
export function parseManifest(text: string): Manifest {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    throw new ManifestError(`Manifest: cannot parse JSON — ${reason}`);
  }

  const source = asObject(data, "the document");
  requireKeys(source, MANIFEST_KEYS, "the document");

  const format = requireString(source["manifest"], "the 'manifest' format version");
  if (format !== MANIFEST_FORMAT) {
    // Un format inconnu est le mecanisme d'evolution : une vieille application ignore un manifeste
    // ecrit pour un moteur plus recent, au lieu d'en lire la moitie de travers.
    throw new ManifestError(
      `Manifest: unsupported format '${format}' (this engine reads '${MANIFEST_FORMAT}').`,
    );
  }

  const generatedAt = source["generated_at"];
  if (generatedAt !== undefined) requireString(generatedAt, "'generated_at'");

  const blueprints: Record<string, ManifestEntry> = {};
  const declared = asObject(source["blueprints"] ?? {}, "'blueprints'");
  for (const [name, value] of Object.entries(declared)) {
    if (name.length === 0 || POISONED.has(name)) {
      throw new ManifestError(`Manifest: '${name}' is not a usable Blueprint name.`);
    }
    blueprints[name] = parseEntry(name, value);
  }

  return {
    format,
    ...(typeof generatedAt === "string" ? { generatedAt } : {}),
    disabled: requireFlag(source["disabled"], "'disabled'"),
    blueprints,
  };
}

/**
 * Ordonne deux versions numeriques pointees. Les segments manquants valent zero (`"1"` == `"1.0"`).
 *
 * Volontairement plus pauvre que SemVer : ni pre-release, ni metadonnees. Une comparaison qu'un
 * publieur peut faire de tete vaut mieux qu'une grammaire dont il devine les coins.
 */
export function compareVersions(left: string, right: string): number {
  const a = left.split(".");
  const b = right.split(".");
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const x = Number(a[i] ?? 0);
    const y = Number(b[i] ?? 0);
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

/**
 * Resout l'`url` d'une entree contre celle du manifeste.
 *
 * Ecrit a la main plutot que par `new URL(url, base)` : React Native n'offre qu'un polyfill partiel
 * d'`URL`, et la resolution relative en fait justement partie. Trois cas suffisent au format —
 * absolue, enracinee, relative —, et une forme non couverte vaut mieux qu'une resolution qui
 * differe selon la plateforme.
 */
export function resolveUrl(base: string, url: string): string {
  if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return url;

  const scheme = base.indexOf("://");
  const originEnd = scheme < 0 ? -1 : base.indexOf("/", scheme + 3);
  const origin = originEnd < 0 ? base : base.slice(0, originEnd);
  if (url.startsWith("/")) return `${origin}${url}`;

  const path = originEnd < 0 ? "/" : base.slice(originEnd);
  const directory = path.slice(0, path.lastIndexOf("/") + 1);
  return `${origin}${directory}${url}`;
}
