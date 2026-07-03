# Test fixtures

Static test data for the suite: sample Blueprints, frozen HTTP/JSON responses, captured HTML pages,
and any golden files. Keep fixtures small and anonymised — no real credentials or personal data.

Suggested layout as the suite grows:

```
fixtures/
├── blueprints/   # minimal Blueprints exercising specific actions or edge cases
├── responses/    # frozen upstream payloads (JSON, HTML) for offline Act I / extraction tests
└── html/         # captured pages for selector / extraction tests
```

Resolve fixture paths through the fixtures in `tests/conftest.py` rather than hard-coding relative
paths, so tests stay independent of the working directory.
