#!/usr/bin/env bash
# Waits until Oryn OS answers, then prints where to go.
set -euo pipefail
URL="http://localhost:${ORYN_WEB_PORT:-5173}"
printf "Waiting for Oryn OS"
for _ in $(seq 1 120); do
  if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
    echo
    cat <<MSG

  Oryn OS is running → $URL
  Sign in:  owner@northwind.test / oryn-demo   (also operator@, admin@, viewer@ and *@brightsmile.test)
  Temporal UI → http://localhost:${ORYN_TEMPORAL_UI_PORT:-8233}

  Two weeks of history is being generated in the background (real workflow runs);
  watch the Overview fill up. Follow it with: docker compose -f deploy/docker-compose.yml logs -f seed
MSG
    exit 0
  fi
  printf "."
  sleep 2
done
echo; echo "Oryn OS did not come up. Check: docker compose -f deploy/docker-compose.yml logs api" >&2
exit 1
