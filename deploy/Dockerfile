# Image du daemon Aetherius pour un hote toujours allume (VPS, Raspberry Pi, NAS).
# Multi-stage : le wheel est construit a part, l'image finale n'embarque ni sources ni outils de
# build. La base SQLite et l'etat vivent sous /data (monter un volume) pour survivre aux
# redemarrages. Recette complete : docs/deployment.md.

FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-deps --wheel-dir /wheels .


FROM python:3.12-slim

# BROWSER=1 ajoute Act II (Continuum) : extra [browser] + Chromium. Image nettement plus lourde.
#   docker build --build-arg BROWSER=1 ...
ARG BROWSER=0

# AETHERIUS_DATA_DIR : tout l'etat durable (aetherius.db, profiles/, runs/) sous un seul volume.
# Le bind 0.0.0.0 est confine au conteneur : c'est le mapping de port qui decide de l'exposition
# (le compose publie sur la loopback de l'hote par defaut).
ENV AETHERIUS_DATA_DIR=/data \
    AETHERIUS_DAEMON_HOST=0.0.0.0 \
    AETHERIUS_DAEMON_PORT=8787 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONUNBUFFERED=1

# Chromium et ses dependances systeme s'installent en root, dans un chemin partage
# (PLAYWRIGHT_BROWSERS_PATH) lisible par l'utilisateur de service.
COPY --from=build /wheels /tmp/wheels
RUN set -eux; \
    wheel="$(ls /tmp/wheels/*.whl)"; \
    if [ "$BROWSER" = "1" ]; then \
        pip install --no-cache-dir "${wheel}[browser]"; \
        playwright install --with-deps chromium; \
        rm -rf /var/lib/apt/lists/*; \
    else \
        pip install --no-cache-dir "${wheel}"; \
    fi; \
    rm -rf /tmp/wheels

# Le daemon tourne sans privileges ; /data appartient a l'utilisateur de service.
RUN useradd --create-home --uid 10001 aetherius \
    && mkdir -p /data \
    && chown aetherius:aetherius /data

# Les exemples zero config servent de sonde de bout en bout (les chemins relatifs des schedules
# se resolvent depuis /app). Les Blueprints utilisateur se montent sur /app/blueprints.
COPY examples /app/examples
WORKDIR /app
USER aetherius

EXPOSE 8787
VOLUME ["/data"]

# /health est non authentifie par contrat (sonde de demarrage) ; python stdlib, pas de curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('AETHERIUS_DAEMON_PORT', '8787'), timeout=4)"

# Exposer le daemon hors de l'hote EXIGE un token (AETHERIUS_DAEMON_TOKEN) et, en pratique,
# un reverse proxy TLS devant. Voir docs/deployment.md, section Securite.
CMD ["aetherius", "serve"]
