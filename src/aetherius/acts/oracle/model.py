"""Oracle model access is the shared cognition layer (see ``acts/_cognition/`` and ``models/registry.py``).

With the Phase 2 redefinition, Oracle grounds targets via a cognition ``Grounder`` — Claude by
default, an optional local ONNX/VLM behind the same interface. There is no bespoke per-task model to
load; this module is kept as the Act's seam for Oracle-specific model wiring if Jalon 2-B needs it.
"""
