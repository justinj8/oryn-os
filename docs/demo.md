# Five-minute demo

Start the stack with `make up` and open http://localhost:5173. The Overview fills with two weeks of
history over the first few minutes; you can start the demo straight away.

## 1. The board (30 seconds)
Sign in as `owner@northwind.test` / `oryn-demo`. The Overview opens on the live board: each run is a
strip whose left edge is its state (running, needs approval, completed, escalated, failed) and whose
second line is the route of agents that held it. Below are completion rate, cost, and business impact,
all computed from real run rows.

## 2. A lead that needs a manager (90 seconds)
1. Open a second browser profile (or a private window) and sign in as `admin@northwind.test`.
2. As the owner, go to *Simulators* and send **New lead asking for a 15% discount**.
3. The run appears on the board as *Running*, then *Needs approval*.
4. As the admin, open *Approvals*. The card shows the amount, the tool, and every reason it was held
   ("discount 15% exceeds 10% policy", "crm.apply_discount is a high-risk action"). Approve it.
5. The run turns *Completed*. Open it: the trace shows Sales qualifying, the approval, the discount
   applied, the handoff to Scheduler, the booking and the confirmation email, with tokens and cost per
   model call.

Point out: the people who start a run can't approve it, an operator can't approve admin-level refunds,
and clicking approve twice returns "already decided".

## 3. Talk to an agent (60 seconds)
In *Simulators*:
- **Website chat:** "I'd like to book an appointment", then "the first one works".
- **Phone (Twilio):** the same over SMS or a voice call. The simulator posts the exact form payloads
  Twilio sends to the real webhooks and reads back the TwiML.
- **Email:** "What is your refund policy?" gets an answer from the knowledge base.

Then try "Please refund $750 on INV-1001" in chat: the agent replies that a manager is checking, and an
admin-level approval appears.

## 4. Crash the worker (60 seconds)
```bash
./scripts/chaos.sh
```
It fires a lead, approves it, kills the worker while the Scheduler is mid-booking, starts a new worker
and waits. The run completes with exactly one booking. In the trace, the crashed attempt's spans are
marked *interrupted*, followed by a retry.

## 5. Build a workflow from a sentence (45 seconds)
*Workflows → New workflow*, pick an example (or type your own), *Build workflow*. Each clause is tagged
with how it was understood; anything not understood is a visible warning, never silently dropped. The
graph shows the branches. Save it; runs in progress keep the version they started with.

## 6. Tenant isolation (15 seconds)
Sign in as `owner@brightsmile.test`: a dental practice with its own agents, workflows and history, and no
way to see Northwind's. Isolation is enforced by Postgres row-level security, not by filters in code.

## Optional
- Temporal UI at http://localhost:8233 shows every workflow's event history (*Open in Temporal* on a run).
- *Connectors → Simulate an unreliable service* adds failures and latency to watch retries in traces.
- Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env` to run the same flows on Claude.
