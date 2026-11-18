import { screen } from "@testing-library/react";
import Overview from "@/pages/Overview";
import { mockApi, renderWithApp } from "@/test/render";

const metrics = {
  range_days: 30, runs_total: 42, runs_completed: 30, completion_rate: 0.75, failed: 5, escalated: 5, in_flight: 2,
  p50_duration_s: 12, p95_duration_s: 48, llm_cost_usd: 1.25, cost_per_completed_run_usd: 0.04, tokens_in: 1000,
  tokens_out: 200, simulated_cost: true, approvals_pending: 1, avg_approval_wait_s: 300, retry_rate: 0.1,
  meetings_booked: 12, pipeline_usd: 98000, tickets_resolved: 9, invoices_collected_usd: 0, reports_delivered: 2,
  minutes_saved: 600, hourly_rate_usd: 45, labor_savings_usd: 450, roi_multiple: 360,
};

function setup(overrides = {}) {
  mockApi({
    "/api/metrics/overview": { ...metrics, ...overrides },
    "/api/metrics/timeseries": [],
    "/api/metrics/agents": [],
    "/api/runs": { items: [], next_cursor: null },
  });
  renderWithApp(<Overview />);
}

test("labels cost as simulated when no real model was used", async () => {
  setup();
  expect(await screen.findByText("Simulated")).toBeInTheDocument();
  expect(screen.getByText("75%")).toBeInTheDocument();
  expect(screen.getByText("360×")).toBeInTheDocument();
});

test("shows a dash for ROI when there is no cost yet", async () => {
  setup({ roi_multiple: null, simulated_cost: false, llm_cost_usd: 0 });
  await screen.findByText("Completion rate");
  expect(screen.queryByText("Simulated")).not.toBeInTheDocument();
  expect(screen.getByTestId("roi").textContent).toBe("—");
});

test("an empty board invites the user to start some work", async () => {
  setup();
  expect(await screen.findByText(/Nothing in flight/)).toBeInTheDocument();
});
