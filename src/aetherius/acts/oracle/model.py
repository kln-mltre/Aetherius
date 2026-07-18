"""Oracle model access is the shared cognition layer (see ``acts/_cognition/`` and ``models/registry.py``).

Oracle grounds targets via a cognition ``Grounder`` — Claude by default, an optional local
ONNX/VLM behind the same interface — resolved per run by ``resolve_provider`` from the Blueprint's
``vision`` config. There is no bespoke per-task model to load; this module remains the Act's seam
for Oracle-specific model wiring, should one become necessary.
"""
