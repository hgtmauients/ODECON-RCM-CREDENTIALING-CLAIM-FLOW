# Multi-stage build:
#  1) builder installs deps into an isolated venv
#  2) runtime is a slim image with only the venv + app code
#  Entrypoint fixes volume ownership then drops to non-root "app" user.

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements.lock ./
RUN pip install --require-hashes --no-deps -r requirements.lock


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# util-linux ships setpriv used by the entrypoint to drop privileges.
# It is already in python:3.11-slim, no extra apt install needed.

# Non-root user. UID 10001 is well outside any host system UID range.
# We give the app user a writable HOME so libraries that look for config in
# ~/.foo (e.g. asyncpg looking for ~/.postgresql/postgresql.key) don't fall
# back to /root which would be permission-denied.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app -d /home/app -m --shell /sbin/nologin app

ENV HOME=/home/app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

# Writable storage path for EDI files. Real prod ownership is fixed by the
# entrypoint after the named volume is mounted (which mounts as root by default).
RUN mkdir -p /data/edi && chown -R app:app /data/edi

# Make entrypoint executable
RUN chmod +x /app/docker-entrypoint.sh

# IMPORTANT: do NOT switch to USER app here — the entrypoint runs as root,
# fixes volume ownership, then drops privileges via setpriv.

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
