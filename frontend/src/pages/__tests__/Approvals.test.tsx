import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setAuth } from "@/api/client";
import Approvals from "@/pages/Approvals";
import { renderWithApp } from "@/test/render";

const approval = {
  id: "a1", run_id: "r1", run_title: "New lead workflow · Dana Reyes", step_id: "qualify", action_tool: "billing.issue_refund",
  action_args: { invoice_id: "i1", amount_usd: 750 }, description: "Refund $750.00",
  risk_reasons: ["billing.issue_refund is a high-risk action", "refund $750 exceeds $500 admin threshold"],
  min_role: "admin", status: "pending", requested_at: new Date().toISOString(), expires_at: null, decided_by: null,
  decided_at: null, comment: null, escalation_level: 0,
};

function signInAs(role: string) {
  localStorage.setItem("oryn.token", "tok");
  localStorage.setItem("oryn.tenant", "t1");
  localStorage.setItem(
    "oryn.session",
    JSON.stringify({ user: { id: "u", email: "e", name: "N" }, memberships: [{ tenant_id: "t1", slug: "n", name: "N", role }] }),
  );
  setAuth({ token: "tok", tenantId: "t1" });
}

function respond(handler: (url: string, init?: RequestInit) => [number, unknown]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const [status, body] = handler(String(input), init);
    return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
  });
}

test("approve is disabled for an operator on an admin-level approval", async () => {
  signInAs("operator");
  respond(() => [200, [approval]]);
  renderWithApp(<Approvals />);
  const btn = await screen.findByRole("button", { name: "Approve" });
  expect(btn).toBeDisabled();
  expect(screen.getByText(/Needs an admin or owner/)).toBeInTheDocument();
  expect(screen.getByText("refund $750 exceeds $500 admin threshold")).toBeInTheDocument();
});

test("a 409 tells the user someone else already decided", async () => {
  signInAs("admin");
  respond((_url, init) => (init?.method === "POST" ? [409, { detail: "already approved" }] : [200, [approval]]));
  renderWithApp(<Approvals />);
  const btn = await screen.findByRole("button", { name: "Approve" });
  await act(() => userEvent.click(btn));
  expect(await screen.findByText("Someone else already decided this one.")).toBeInTheDocument();
});
