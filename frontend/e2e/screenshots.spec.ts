// Captures the README screenshots from a running stack: SCREENSHOTS=1 pnpm exec playwright test screenshots
import { expect, test, type Page } from "@playwright/test";

test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to capture docs screenshots");
test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });

const OUT = "../docs/screenshots";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("oryn-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Live", { exact: true })).toBeVisible({ timeout: 10_000 });
}

test("landing", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  // Capture the demo at the moment it waits for the visitor's decision.
  await expect(page.getByText("Waiting on a person")).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: `${OUT}/landing.png` });
});

for (const scheme of ["light", "dark"] as const) {
  test(`overview (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await signIn(page, "owner@northwind.test");
    await page.waitForTimeout(1500); // let chart bars finish animating
    await page.screenshot({ path: `${OUT}/overview-${scheme}.png`, fullPage: true });
  });
}

test("approval, trace, builder and simulators", async ({ browser }) => {
  const operator = await browser.newPage();
  await signIn(operator, "operator@northwind.test");
  await operator.request.post("/api/simulate/events", {
    headers: await authHeaders(operator),
    data: { type: "lead.created", payload: { name: "Dana Reyes", email: `dana.${Date.now()}@example.com`, phone: "+15550101", company: "Reyes Co", need: "heat pump install", budget_usd: 8200, requested_discount_pct: 15 } },
  });

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await signIn(page, "admin@northwind.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Approvals" }).click();
  const item = page.getByRole("list", { name: "Approval requests" }).locator("> li", { hasText: "Apply a 15.0% discount" }).first();
  const panel = page.getByRole("region", { name: "Decision" });
  await expect(item).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: `${OUT}/approvals.png` });

  await item.click();
  const href = await panel.getByRole("link", { name: /workflow/i }).getAttribute("href");
  await panel.getByRole("button", { name: "Approve" }).click();
  await page.goto(href!);
  await expect(page.getByRole("region", { name: "Run details" }).getByText("Completed")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/trace.png`, fullPage: true });

  await page.goto("/workflows/new");
  await page.getByRole("button", { name: /When a new lead arrives, have the sales agent/ }).first().click();
  await page.getByRole("button", { name: "Build workflow" }).click();
  await expect(page.getByRole("img", { name: /Workflow graph/ })).toBeVisible();
  await page.screenshot({ path: `${OUT}/builder.png`, fullPage: true });

  await page.goto("/simulators");
  const chat = page.getByLabel("Message as a website visitor");
  await chat.fill("Hi, I'd like to book an appointment");
  await chat.press("Enter");
  await expect(page.getByText(/I have these openings/)).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: `${OUT}/simulators.png` });
});

async function authHeaders(page: Page) {
  return page.evaluate(() => ({
    Authorization: `Bearer ${localStorage.getItem("oryn.token")}`,
    "X-Tenant-Id": localStorage.getItem("oryn.tenant") ?? "",
  }));
}
