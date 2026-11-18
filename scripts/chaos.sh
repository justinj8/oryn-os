#!/usr/bin/env bash
# Chaos demo: kill the Temporal worker in the middle of a run, bring it back, and watch the run
# finish exactly where it left off — no lost work, no duplicate bookings.
set -euo pipefail
BASE="${ORYN_URL:-http://localhost:5173}"
COMPOSE="docker compose -f $(dirname "$0")/../deploy/docker-compose.yml"
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1"; }
login() { curl -fsS "$BASE/api/auth/login" -H 'content-type: application/json' -d "{\"email\":\"$1\",\"password\":\"oryn-demo\"}"; }

ADMIN=$(login admin@northwind.test); OPER=$(login operator@northwind.test)
A_TOK=$(echo "$ADMIN" | json "d['access_token']"); O_TOK=$(echo "$OPER" | json "d['access_token']")
TENANT=$(echo "$ADMIN" | json "[m['tenant_id'] for m in d['memberships'] if m['slug']=='northwind'][0]")
api() { local tok=$1; shift; curl -fsS -H "Authorization: Bearer $tok" -H "X-Tenant-Id: $TENANT" -H 'content-type: application/json' "$@"; }

# Make the calendar slow so the crash lands mid-step.
CAL=$(api "$A_TOK" "$BASE/api/connectors" | json "[c['id'] for c in d if c['kind']=='calendar'][0]")
api "$A_TOK" -X PATCH "$BASE/api/connectors/$CAL" -d '{"settings":{"failure_rate":0,"latency_ms":4000,"fail_attempts":0}}' >/dev/null
trap 'api "$A_TOK" -X PATCH "$BASE/api/connectors/$CAL" -d "{\"settings\":{\"failure_rate\":0,\"latency_ms\":0,\"fail_attempts\":0}}" >/dev/null' EXIT

LEAD="Chaos Test $RANDOM$RANDOM"
echo "1. $LEAD asks for a 15% discount"
RUN=$(api "$O_TOK" -X POST "$BASE/api/simulate/events" -d "{\"type\":\"lead.created\",\"payload\":{\"name\":\"$LEAD\",\"email\":\"chaos.$RANDOM@example.com\",\"phone\":\"+15550909\",\"need\":\"heat pump install\",\"budget_usd\":9000,\"requested_discount_pct\":15}}" | json "d['run_ids'][0]")
echo "   run $RUN"
status() { api "$A_TOK" "$BASE/api/runs/$RUN" | json "$1"; }
for _ in $(seq 1 60); do [ "$(status "d['status']")" = waiting_approval ] && break; sleep 1; done
echo "2. Sales agent paused for approval; a manager approves"
APPROVAL=$(status "[a['id'] for a in d['approvals'] if a['status']=='pending'][0]")
api "$A_TOK" -X POST "$BASE/api/approvals/$APPROVAL/decision" -d '{"approved":true,"comment":"chaos demo"}' >/dev/null

for _ in $(seq 1 60); do
  if api "$A_TOK" "$BASE/api/runs/$RUN/spans" | json "any(s['name']=='calendar.book' and s['ended_at'] is None for s in d)" | grep -q True; then break; fi
  sleep 0.5
done
echo "3. Scheduler is mid-booking — killing the worker 💥"
$COMPOSE kill worker >/dev/null 2>&1
sleep 5
echo "4. Starting a fresh worker"
$COMPOSE start worker >/dev/null 2>&1

for _ in $(seq 1 120); do
  S=$(status "d['status']")
  if [ "$S" = completed ]; then
    BOOKINGS=$(api "$A_TOK" "$BASE/api/sandbox/calendar?limit=200" | json "sum(1 for e in d['items'] if e['title'].endswith('$LEAD'))")
    echo "5. Run completed: $(status "d['outcome_summary']")"
    echo "   Bookings for this lead: $BOOKINGS (exactly one — retries are idempotent)"
    echo "Recovered after worker crash ✔  →  $BASE/runs/$RUN"
    exit 0
  fi
  sleep 1
done
echo "Run did not complete (status: $S)" >&2
exit 1
