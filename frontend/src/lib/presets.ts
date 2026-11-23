/** Scripted outside-world events. Used by the Simulators page and the command palette. */
export type Preset = { id: string; label: string; hint: string; type: string; payload: () => Record<string, unknown> };

export const PRESETS: Preset[] = [
  {
    id: "lead-discount",
    label: "New lead asking for a 15% discount",
    hint: "Sales qualifies, asks a manager about the discount, then hands off to scheduling.",
    type: "lead.created",
    payload: () => ({
      name: "Dana Reyes",
      email: `dana.${Date.now()}@example.com`,
      phone: "+15550101",
      company: "Reyes Co",
      need: "heat pump install",
      budget_usd: 8200,
      requested_discount_pct: 15,
      source: "web",
    }),
  },
  {
    id: "lead-small",
    label: "New lead with a small budget",
    hint: "Not qualified yet, so it goes to the nurture email.",
    type: "lead.created",
    payload: () => ({ name: "Sam Patel", email: `sam.${Date.now()}@example.com`, need: "AC tune-up", budget_usd: 600, source: "web" }),
  },
  {
    id: "ticket-refund",
    label: "Support ticket: refund of $750",
    hint: "Over the admin threshold, so an admin has to approve it.",
    type: "ticket.created",
    payload: () => ({ name: "Ann Lee", email: "ann.lee@example.com", subject: "Refund", body: "Please refund $750 on INV-1001" }),
  },
  {
    id: "invoices-overdue",
    label: "Overdue invoices",
    hint: "The ops agent texts payment reminders.",
    type: "invoice.overdue",
    payload: () => ({}),
  },
  {
    id: "weekly-report",
    label: "Weekly report",
    hint: "The reporting agent queries the warehouse and emails a summary.",
    type: "schedule.weekly",
    payload: () => ({}),
  },
];
