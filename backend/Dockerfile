# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never PATH=/app/.venv/bin:$PATH
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /usr/local/bin/uv
WORKDIR /app
# Dependencies first so code changes don't bust the layer cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev \
 && useradd --create-home --uid 10001 oryn && chown -R oryn /app \
 && chmod +x /app/docker-entrypoint.sh
USER oryn
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["api"]
