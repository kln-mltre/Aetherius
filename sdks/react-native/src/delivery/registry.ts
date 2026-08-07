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
 * Le jalon 3-H leve la troisieme, **en opt-in et bornee** : `allowNew` reserve un prefixe de noms
 * sous lequel un manifeste a le droit d'*ajouter*. La regle 1 n'y perd rien — un nom nouveau n'a pas
 * de repli hors ligne a preserver, il n'existe pas encore pour l'utilisateur — et la seconde raison
 * reste entiere, portee par un perimetre de secrets **obligatoire** (voir `scope.ts`).
 *
 * ```ts
 * const registry = new BlueprintRegistry({
 *   bundled: { "mobile.delivery.quotes": { version: "1", document: quotesV1 } },
 *   manifest: "https://cdn.exemple.fr/aetherius/manifest.json",
 *   cache: AsyncStorage,
 *   // Optionnel (jalon 3-H) : ce que le manifeste a le droit d'ajouter.
 *   allowNew: { prefix: "mobile.portail.", secrets: ["portail_user", "portail_pass"] },
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

import { prune, readCache, writeCache } from "./cache.js";
import { refreshOverlay } from "./refresh.js";
import { NO_SECRETS, bundledSecrets, resolveScope, type Scope } from "./scope.js";
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
  private readonly scope: Scope | undefined;
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
    this.scope = resolveScope(config);
  }

  /**
   * Le Blueprint a jouer, et d'ou il vient.
   *
   * Ordre : la version distante en cache si elle passe **toutes** les gardes et bat l'embarquee,
   * sinon l'embarquee. Une entree de cache qui echoue une garde est purgee au passage — un cache
   * corrompu ou perime se soigne tout seul, il ne se traine pas.
   *
   * Un nom couvert par `allowNew` (jalon 3-H) et pas encore livre leve, comme n'importe quel nom
   * inconnu : il n'y a rien a jouer, et repondre autre chose serait inventer un socle. `list()` est
   * la façon de savoir ce qui est disponible avant d'essayer.
   *
   * @throws {BlueprintLoadError} aucun Blueprint de ce nom n'est embarque ni livre.
   * @throws {BlueprintSchemaError} le document embarque n'est pas un Blueprint valide.
   * @throws {BlueprintValidationError} le document embarque n'est pas jouable ici.
   */
  async resolve(name: string): Promise<ResolvedBlueprint> {
    const cached = await this.remote(name);
    if (cached !== undefined) {
      return { name, version: cached.version, origin: "remote", blueprint: cached.blueprint };
    }

    const bundled = this.config.bundled[name];
    if (bundled === undefined) throw new BlueprintLoadError(this.unknown(name));
    return { name, version: bundled.version, origin: "bundled", blueprint: this.bundled(name) };
  }

  /**
   * L'etat de la livraison, un Blueprint par ligne. De quoi l'afficher sans tout charger.
   *
   * Le socle d'abord, dans son ordre de declaration, puis ce qui est arrive par le prefixe reserve,
   * trie — une application qui affiche un catalogue a besoin d'un ordre stable, et ce qui vient du
   * reseau n'en a pas naturellement.
   */
  async list(): Promise<readonly BlueprintStatus[]> {
    const out: BlueprintStatus[] = [];
    for (const [name, bundled] of Object.entries(this.config.bundled)) {
      const cached = await this.remote(name);
      out.push(
        cached === undefined
          ? { name, version: bundled.version, origin: "bundled" }
          : { name, version: cached.version, origin: "remote" },
      );
    }

    for (const name of Object.keys(await this.entries()).sort()) {
      if (this.config.bundled[name] !== undefined) continue;
      const cached = await this.remote(name);
      if (cached !== undefined) out.push({ name, version: cached.version, origin: "remote" });
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
    const { report, kept } = await refreshOverlay(
      this.config,
      this.scope,
      await this.entries(),
      (name) => this.bounds(name),
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
      this.bounds(name),
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

  /**
   * Les bornes applicables a *name*. C'est le **nom** qui les decide, pas la version.
   *
   * Un nom embarque garde la regle de 3-F, meme s'il est aussi couvert par le prefixe : version
   * strictement superieure, et les secrets du socle. Le prefixe **ajoute** des noms, il n'assouplit
   * rien pour ceux qui existent.
   */
  private bounds(name: string): Bounds {
    const bundled = this.config.bundled[name];
    const engineVersion = this.config.engineVersion ?? ENGINE_VERSION;
    if (bundled !== undefined) {
      return { bundledVersion: bundled.version, engineVersion, allowedSecrets: this.allowed };
    }
    return { engineVersion, allowedSecrets: this.scope?.secrets ?? NO_SECRETS };
  }

  /** Ce qu'on repond a un nom qu'on ne sait pas jouer. */
  private unknown(name: string): string {
    const known = Object.keys(this.config.bundled).join(", ") || "none";
    if (this.scope === undefined) {
      return `No bundled Blueprint named '${name}' (known: ${known}).`;
    }
    return this.scope.covers(name)
      ? `No Blueprint named '${name}': it is covered by '${this.scope.prefix}' but no manifest ` +
          `has delivered it yet (bundled: ${known}).`
      : `No bundled Blueprint named '${name}', and it is outside '${this.scope.prefix}' ` +
          `(bundled: ${known}).`;
  }

  /**
   * Le document de cache, lu une fois puis tenu en memoire (la resolution est sur le chemin d'un run).
   *
   * C'est ici que la porte du jalon 3-H se referme : une entree qui n'est ni embarquee, ni couverte
   * par le prefixe courant est **purgee** — retirer `allowNew` ou changer le prefixe desinstalle ce
   * qui etait entre par la, sans reseau et des la lecture suivante.
   */
  private async entries(): Promise<Record<string, CachedBlueprint>> {
    if (this.overlay !== undefined) return this.overlay;

    const { entries, dropped } = prune(
      await readCache(this.config.cache),
      (name) => this.config.bundled[name] !== undefined || (this.scope?.covers(name) ?? false),
    );
    this.overlay = entries;
    if (dropped.length > 0) await writeCache(this.config.cache, entries);
    return entries;
  }
}
