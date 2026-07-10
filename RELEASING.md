# Publier une version

Comment couper une release, et comment tes autres projets la consomment. Le processus est **le même à
chaque fois** ; seule la version change. Objectif : qu'une correction de bug se publie en une checklist
courte.

## Où vit la version (à garder synchronisées, SemVer)

- **Python** : [`src/aetherius/version.py`](src/aetherius/version.py) (`__version__`) — `pyproject.toml`
  la lit dynamiquement.
- **SDK TS** : [`sdks/typescript/package.json`](sdks/typescript/package.json) (`version`).

## Couper une release (depuis `main`, à jour)

1. **Bump** la version aux deux endroits (ex. `0.2.0` → `0.2.1` pour un correctif).
2. Ajoute une entrée en tête de [`CHANGELOG.md`](CHANGELOG.md).
3. `make check-all` — le gate complet (format, lint, mypy, tests Python, build + tests SDK TS).
4. **PyPI** :
   ```bash
   make release-check          # build le wheel/sdist + twine check (dry run)
   python3 -m twine upload dist/*
   ```
5. **npm** :
   ```bash
   cd sdks/typescript && npm ci && npm run build
   npm publish --access public   # `--access public` seulement si le paquet est scopé (@scope/...)
   ```
6. **Tag + push** :
   ```bash
   git tag -a vX.Y.Z -m "Aetherius X.Y.Z" && git push origin vX.Y.Z
   ```
7. **GitHub Release** sur le tag (notes = la section du CHANGELOG) :
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" \
     --notes-file <(sed -n '/## \[X.Y.Z\]/,/## \[/p' CHANGELOG.md | sed '$d')
   ```

## Mettre à jour après un correctif (le cas courant du dogfooding)

Un bug corrigé ⇒ **patch bump** (`0.2.1`, `0.2.2`, …), puis on rejoue la checklist. Une version publiée
ne se réécrit jamais — on avance. Tant qu'on est en `0.x`, l'API peut bouger entre deux mineures.

## Consommer depuis tes autres projets

- **Python** : `pip install aetherius` (extras : `aetherius[browser]`) ; `pip install -U aetherius`
  pour mettre à jour ; épingle `aetherius==0.2.1` pour figer.
- **TypeScript** : `npm install @aetherius/client` ; `npm update @aetherius/client` pour mettre à jour.

> Adapte les noms de paquets ci-dessus s'ils diffèrent (voir `pyproject.toml` / `package.json`).
