"""Secret resolution: fill a Blueprint's declared secrets from the environment.

A Blueprint never stores secret values, only their names. At run time each declared secret is
resolved, in order of precedence:

1. a value passed explicitly by the caller (``run(..., secrets=...)`` / ``--secret``);
2. an environment variable ``AETHERIUS_SECRET_<NAME>`` (name upper-cased);

A local ``.env`` file (git-ignored) is loaded into the environment first, so a developer or another
agent can keep credentials on their machine without ever committing them to a public repo. Existing
environment variables always win over the file, which keeps CI and production in control.
"""

from __future__ import annotations

from typing import Mapping

from dotenv import find_dotenv, load_dotenv

_SECRET_ENV_PREFIX = "AETHERIUS_SECRET_"
_dotenv_loaded = False


def _secret_env_key(name: str) -> str:
    """Environment variable backing the declared secret *name* (``cas_pass`` -> ...``CAS_PASS``)."""
    return _SECRET_ENV_PREFIX + name.upper()


def load_dotenv_once() -> None:
    """Load the nearest ``.env`` into the environment, once per process, without overriding it."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)
    _dotenv_loaded = True


def resolve_secrets(
    declared: list[str],
    provided: Mapping[str, str] | None,
) -> dict[str, str]:
    """Return the secret values for *declared*, merging caller values over environment ones.

    Secrets left unresolved are simply omitted; the template engine surfaces a clear error if a
    step actually references one that was never provided.
    """
    import os

    resolved: dict[str, str] = dict(provided or {})
    missing = [name for name in declared if name not in resolved]
    if missing:
        load_dotenv_once()
        for name in missing:
            value = os.environ.get(_secret_env_key(name))
            if value is not None:
                resolved[name] = value
    return resolved


def available_from_env(declared: list[str]) -> set[str]:
    """Subset of *declared* secrets that can be resolved from the environment right now.

    Used by the Console to mark those fields optional instead of forcing the user to retype them.
    """
    import os

    if declared:
        load_dotenv_once()
    return {name for name in declared if os.environ.get(_secret_env_key(name)) is not None}
