#!/bin/sh
set -e
case "$1" in
  api)     exec uvicorn oryn.api.app:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers ;;
  worker)  exec python -m oryn.orchestration.worker ;;
  migrate) exec alembic upgrade head ;;
  seed)    shift; exec python -m oryn.seed "$@" ;;
  mcp)     exec python -m oryn.mcp_server --http ;;
  *)       exec "$@" ;;
esac
