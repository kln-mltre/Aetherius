# Phase 1.5 - Jalon F (brouillon a finaliser ; voir docs/phase-1.5/f-deployment.md).
# Image du daemon Aetherius pour un hote toujours allume (VPS, Raspberry Pi, NAS).
# La base SQLite et l'etat vivent sous /data (monter un volume) pour survivre aux redemarrages.

FROM python:3.12-slim

# Repertoire d'etat persistant : schedules, historique des runs, profils.
ENV AETHERIUS_DATA_DIR=/data
ENV AETHERIUS_DAEMON_HOST=0.0.0.0
ENV AETHERIUS_DAEMON_PORT=8787

WORKDIR /app
COPY . /app

# Base + Act I + daemon + scheduler. Ajouter [browser] pour Act II (image plus lourde, Chromium).
RUN pip install --no-cache-dir . \
    && mkdir -p /data

EXPOSE 8787
VOLUME ["/data"]

# Exposer le daemon hors loopback EXIGE un token (AETHERIUS_DAEMON_TOKEN) et, en pratique,
# un reverse proxy TLS devant. Voir docs/phase-1.5/f-deployment.md.
CMD ["aetherius", "serve"]
