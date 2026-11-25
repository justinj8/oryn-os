import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("oryn-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

test("lead → approval → booked meeting, end to end", async ({ browser }) => {
  // An operator fires the event…
  const operator = await browser.newPage();
  await signIn(operator, "operator@northwind.test");
  await operator.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Simulators" }).click();
  const preset = operator.locator("li", { hasText: "New lead asking for a 15% discount" });
  await preset.getByRole("button", { name: "Send" }).click();
  await expect(operator.getByText(/Started 1 run/)).toBeVisible();

  // …and an admin approves it (people can't approve runs they started themselves).
  const admin = await browser.newPage();
  await signIn(admin, "admin@northwind.test");
  await admin.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Approvals" }).click();
  // Scope to the approvals list: the Overview's activity feed mentions the same approval.
  const item = admin.getByRole("list", { name: "Approval requests" }).locator("> li", { hasText: "Apply a 15.0% discount" }).first();
  const panel = admin.getByRole("region", { name: "Decision" });
  await expect(item).toBeVisible({ timeout: 30_000 });
  await item.click();
  const runHref = await panel.getByRole("link", { name: /workflow/i }).getAttribute("href");
  await panel.getByRole("button", { name: "Approve" }).click();
  await expect(admin.getByText(/Approved — the agent is continuing/)).toBeVisible();

  // The run finishes with a booked meeting and a visible handoff in the trace.
  await admin.goto(runHref!);
  const run = admin.getByRole("region", { name: "Run details" });
  await expect(run.getByText("Completed")).toBeVisible({ timeout: 30_000 });
  await expect(run.getByRole("button", { name: /sales → scheduler/ })).toBeVisible();
  await expect(run.getByRole("button", { name: /calendar\.book/ })).toBeVisible();
  await expect(run.getByText(/Meeting booked/)).toBeVisible();
});
