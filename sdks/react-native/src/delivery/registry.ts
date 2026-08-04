/**
 * `BlueprintRegistry` — d'ou vient le Blueprint qu'on va jouer (jalon 3-F).
 *
 * Sans ce jalon, un Blueprint embarque dans le binaire n'est qu'un fichier de configuration : le
 * corriger demande une publication sur les stores. Avec lui, un site qui change se repare en
 * quelques minutes, pour tous les utilisateurs.
 *
 * Trois regles portent l'ensemble, et aucune n'est negociable :
 *
 *   1. **Le socle embarque n'est pas optionnel.** Une application doit fonctionner au premier
 *      lancement, hors ligne, sans avoir jamais contacte le reseau. Le distant est une
 *      **surcouche**. Un registre purement distant transformerait une panne de CDN en application
 *      morte.
 *   2. **La resolution ne touche jamais au reseau.** Un run n'attend pas un CDN pour savoir quoi
 *      jouer ; `refresh()` est un geste separe, que l'application declenche quand ça l'arrange.
 *   3. **Le manifeste ne peut que *mettre a jour* ce que l'application livre deja.** Un nom absent
 *      du socle est ignore : c'est ce qui garantit la regle 1 pour chaque Blueprint, et ce qui
 *      empeche un manifeste compromis d'ajouter du comportement que personne n'a relu.
 *
 * ```ts
 * const registry = new BlueprintRegistry({
 *   bundled: { "mobile.delivery.quotes": { version: "1", document: quotesV1 } },
 *   manifest: "https://cdn.exemple.fr/aetherius/manifest.json",
 *   cache: AsyncStorage,
 * });
 *
 * const { blueprint, origin } = await registry.resolve("mobile.delivery.quotes");
 * await client.run(blueprint);
 * void registry.refresh();   // hors du chemin critique
 * ```
 *
 * Format du manifeste, ordre de resolution et modele de menace : docs/embedded.md.
 */

import {
  BlueprintLoadError,
  BlueprintValidationError,
  ENGINE_VERSION,
  validateBlueprintData,
  validateForAct,
  type Blueprint,
} from "@aetherius/engine";

import { readCache, writeCache } from "./cache.js";
import { refreshOverlay } from "./refresh.js";
import type {
  BlueprintStatus,
  CachedBlueprint,
  RefreshReport,
  RegistryConfig,
  ResolvedBlueprint,
} from "./types.js";
import { verify, type Bounds } from "./verify.js";

export class BlueprintRegistry {
  private readonly allowed: ReadonlySet<string>;
  private readonly parsed = new Map<string, Blueprint>();
  private overlay: Record<string, CachedBlueprint> | undefined;

  constructor(private readonly config: RegistryConfig) {
    for (const [name, entry] of Object.entries(config.bundled)) {
      const declared = (entry.document as { name?: unknown } | null)?.name;
      // Une cle qui ment rendrait toute mise a jour distante silencieusement sans effet : le
      // manifeste designerait un nom que personne ne resout. C'est une erreur de programmation, et
      // elle doit sauter au demarrage, pas au premier run.
      if (typeof declared === "string" && declared !== name) {
        throw new BlueprintValidationError(
          `Bundled Blueprint registered as '${name}' is named '${declared}'.`,
        );
      }
    }
    this.allowed = new Set(config.allowedSecrets ?? bundledSecrets(config));
  }

  /**
   * Le Blueprint a jouer, et d'ou il vient.
   *
   * Ordre : la version distante en cache si elle passe **toutes** les gardes et bat l'embarquee,
   * sinon l'embarquee. Une entree de cache qui echoue une garde est purgee au passage — un cache
   * corrompu ou perime se soigne tout seul, il ne se traine pas.
   *
   * @throws {BlueprintLoadError} aucun Blueprint de ce nom n'est embarque.
   * @throws {BlueprintSchemaError} le document embarque n'est pas un Blueprint valide.
   * @throws {BlueprintValidationError} le document embarque n'est pas jouable ici.
   */
  async resolve(name: string): Promise<ResolvedBlueprint> {
    const bundled = this.config.bundled[name];
    if (bundled === undefined) {
      const known = Object.keys(this.config.bundled).join(", ") || "none";
      throw new BlueprintLoadError(`No bundled Blueprint named '${name}' (known: ${known}).`);
    }

    const cached = await this.remote(name, bundled.version);
    if (cached !== undefined) {
      return { name, version: cached.version, origin: "remote", blueprint: cached.blueprint };
    }
    return { name, version: bundled.version, origin: "bundled", blueprint: this.bundled(name) };
  }

  /** L'etat de la livraison, un Blueprint par ligne. De quoi l'afficher sans tout charger. */
  async list(): Promise<readonly BlueprintStatus[]> {
    const out: BlueprintStatus[] = [];
    for (const [name, bundled] of Object.entries(this.config.bundled)) {
      const cached = await this.remote(name, bundled.version);
      out.push(
        cached === undefined
          ? { name, version: bundled.version, origin: "bundled" }
          : { name, version: cached.version, origin: "remote" },
      );
    }
    return out;
  }

  /**
   * Va voir le manifeste et met la surcouche a jour.
   *
   * **Ne leve jamais** pour une panne reseau ou un manifeste malforme : elle rend un rapport. Une
   * livraison est un confort ; la transformer en erreur visible ferait d'un CDN indisponible une
   * application en panne — exactement ce que le socle embarque existe pour eviter.
   *
   * Le manifeste decrit **l'etat voulu** : une entree qui en disparait, ou qui s'y declare
   * `disabled`, ramene son Blueprint a la version embarquee. L'interpretation la plus sure d'un
   * manifeste partiel est ainsi toujours le socle.
   */
  async refresh(): Promise<RefreshReport> {
    const { report, kept } = await refreshOverlay(this.config, await this.entries(), (version) =>
      this.bounds(version),
    );
    // Un manifeste illisible ne rend pas de surcouche, et rien n'est touche : c'est la difference
    // entre « le CDN n'a rien a dire » et « le CDN dit qu'il n'y a rien ».
    if (kept !== undefined) {
      this.overlay = kept;
      await writeCache(this.config.cache, kept);
    }
    return report;
  }

  /**
   * L'interrupteur d'arret **local** : oublier la surcouche, tout de suite.
   *
   * Un mecanisme de deploiement sans mecanisme de retour arriere n'en est pas un. Celui-ci est
   * effectif au run suivant et ne demande le reseau a personne — le pendant du `disabled` du
   * manifeste, qui lui attend le prochain rafraichissement. Sans argument, tout revient a
   * l'embarque. Un `refresh()` ulterieur peut ramener une version distante : pour une coupure
   * durable, construire le registre avec `remote: false`.
   */
  async revert(name?: string): Promise<void> {
    const entries = { ...(await this.entries()) };
    if (name === undefined) {
      this.overlay = {};
      await writeCache(this.config.cache, {});
      return;
    }
    delete entries[name];
    this.overlay = entries;
    await writeCache(this.config.cache, entries);
  }

  /** La version distante utilisable pour *name*, ou `undefined`. Purge ce qui ne passe pas. */
  private async remote(
    name: string,
    bundledVersion: string,
  ): Promise<{ version: string; blueprint: Blueprint } | undefined> {
    if (this.config.remote === false) return undefined;
    const entries = await this.entries();
    const cached = entries[name];
    if (cached === undefined) return undefined;

    const verdict = verify(
      {
        name,
        version: cached.version,
        sha256: cached.sha256,
        text: cached.text,
        minEngine: cached.min_engine,
      },
      this.bounds(bundledVersion),
    );
    if (verdict.ok) return { version: cached.version, blueprint: verdict.blueprint };

    const remaining = { ...entries };
    delete remaining[name];
    this.overlay = remaining;
    await writeCache(this.config.cache, remaining);
    return undefined;
  }

  /** Le socle embarque, valide une fois puis retenu. */
  private bundled(name: string): Blueprint {
    const known = this.parsed.get(name);
    if (known !== undefined) return known;

    // Un document embarque repasse par la validation complete : il a ete relu par un humain, mais
    // c'est la seule façon de rendre un `Blueprint` typé — et un socle casse doit se voir.
    const blueprint = validateBlueprintData(
      (this.config.bundled[name] as { document: unknown }).document,
      name,
    );
    validateForAct(blueprint);
    this.parsed.set(name, blueprint);
    return blueprint;
  }

  private bounds(bundledVersion: string): Bounds {
    return {
      bundledVersion,
      engineVersion: this.config.engineVersion ?? ENGINE_VERSION,
      allowedSecrets: this.allowed,
    };
  }

  /** Le document de cache, lu une fois puis tenu en memoire (la resolution est sur le chemin d'un run). */
  private async entries(): Promise<Record<string, CachedBlueprint>> {
    if (this.overlay === undefined) this.overlay = await readCache(this.config.cache);
    return this.overlay;
  }
}

/**
 * Les secrets que le socle embarque declare : la borne par defaut du perimetre.
 *
 * C'est ce que l'application a ete construite pour fournir — un secret de plus demanderait de toute
 * façon qu'elle le range dans le trousseau, donc une livraison. Lu sans valider : le socle est
 * valide ailleurs, et un document casse ne doit pas empecher le registre d'exister.
 */
function bundledSecrets(config: RegistryConfig): string[] {
  const names = new Set<string>();
  for (const entry of Object.values(config.bundled)) {
    const declared = (entry.document as { secrets?: unknown } | null)?.secrets;
    if (!Array.isArray(declared)) continue;
    for (const name of declared) if (typeof name === "string") names.add(name);
  }
  return [...names];
}

function reasonOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
