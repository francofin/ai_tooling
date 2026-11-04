FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --system --uid 10001 --no-create-home app

WORKDIR /app
RUN chown app:app /app

# Dependencies first so this layer is cached until the lockfile changes.
# The venv stays root-owned and read-only to the app user.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY --chown=app:app . .

USER app

# SECRET_KEY and DEBUG are set for this RUN only and do not persist in the image.
RUN mkdir -p fintank_backend/static \
    && SECRET_KEY=build-only-throwaway DEBUG=True python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "fintank_backend.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
