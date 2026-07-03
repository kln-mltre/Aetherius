# Console (Textual)

Le centre de contrôle terminal (voir aussi le [README](../README.md)). `aetherius` ou
`aetherius console` ouvre l'app Textual [`console/app.py`](../src/aetherius/console/app.py) ;
`aetherius run|validate` sont les chemins scriptables non-interactifs
([`cli.py`](../src/aetherius/cli.py)).

## Plan des écrans

```
Home ─┬─ Library   (parcourt et valide les Blueprints — examples/ + ./blueprints/)
      ├─ Runs      (atteint uniquement depuis Library ; formulaire d'inputs/secrets,
      │             exécution + événements en direct, résultat final)
      ├─ Catalog   (les 4 Acts, statut d'implémentation, capabilities par Act)
      ├─ Sessions  (en attente : stealth/session)
      ├─ Settings  (en attente : daemon)
      ├─ Recorder  (en attente : recorder)
      └─ Builder   (en attente : builder headless — Blueprint Studio)
```

`core/runtime/engine.py::IMPLEMENTED_ACTS` est la seule source de vérité pour « quel Act est
exécutable » — Home, Catalog et Runs la lisent tous ; ne jamais dupliquer cette liste.

Les écrans en attente (`console/screens/sessions.py`, `settings.py`, `recorder.py`,
`screens/builder/screen.py`) partagent une base commune,
[`console/screens/_pending.py`](../src/aetherius/console/screens/_pending.py) : ils affichent ce
que l'écran fera et le jalon dont il dépend, sans fausse interactivité.

## Streamer les événements d'un run : le pattern Sink

`RunEngine.run()` est synchrone et bloquant ; la Console le pilote depuis un worker Textual
(`@work(thread=True)`, voir [`console/screens/runs.py`](../src/aetherius/console/screens/runs.py)).
[`console/run_bridge.py`](../src/aetherius/console/run_bridge.py) fournit `TextualRunSink`, un
`Sink` (voir [`core/events/sinks.py`](../src/aetherius/core/events/sinks.py)) qui relaie chaque
`RunEvent` vers un widget via `App.call_from_thread` — le mécanisme Textual pour franchir la
frontière thread-worker → thread-UI. Ne lève jamais.

Tout futur écran qui doit streamer des événements d'un run (Act II+, daemon) doit réutiliser ce
même pattern plutôt que d'en inventer un nouveau.

## Widgets réutilisables

- [`widgets/event_log.py`](../src/aetherius/console/widgets/event_log.py) — `EventLog(RichLog)`,
  flux d'événements coloré par niveau.
- [`widgets/form.py`](../src/aetherius/console/widgets/form.py) — `BlueprintInputForm`, formulaire
  généré depuis `Blueprint.inputs`/`secrets`.
- [`widgets/json_preview.py`](../src/aetherius/console/widgets/json_preview.py) — `JsonPreview`,
  rendu JSON coloré (Rich `Syntax`).
- [`widgets/run_summary.py`](../src/aetherius/console/widgets/run_summary.py) — `RunSummary`,
  résultat final d'un run (statut, étapes, outputs).
