import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { setAuth } from "@/api/client";
import { CommandPalette, rank } from "@/components/command/CommandPalette";
import { mockApi, renderWithApp } from "@/test/render";

function signIn(role = "admin") {
  localStorage.setItem("oryn.token", "tok");
  localStorage.setItem("oryn.tenant", "t1");
  localStorage.setItem(
    "oryn.session",
    JSON.stringify({ user: { id: "u", email: "e", name: "N" }, memberships: [{ tenant_id: "t1", slug: "n", name: "Northwind", role }] }),
  );
  setAuth({ token: "tok", tenantId: "t1" });
}

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderPalette(onClose = vi.fn()) {
  renderWithApp(
    <Routes>
      <Route path="*" element={<><CommandPalette onClose={onClose} theme="system" setTheme={() => {}} /><Where /></>} />
    </Routes>,
  );
  return onClose;
}

test("rank keeps only commands containing every word, prefix matches first", () => {
  const runs = { label: "Runs", group: "Go to" };
  const newRun = { label: "New workflow", group: "Create", keywords: "builder" };
  expect(rank("ru", runs)).toBeGreaterThan(rank("ru", { label: "Approvals", group: "Go to", keywords: "inbox rules" }));
  expect(rank("new builder", newRun)).toBeGreaterThan(0);
  expect(rank("new zebra", newRun)).toBe(0);
  expect(rank("", runs)).toBe(1);
});

test("typing filters the menu and Enter goes to the highlighted page", async () => {
  signIn();
  mockApi({ "/api/search": [] });
  const onClose = renderPalette();
  const input = screen.getByRole("combobox");
  expect(input).toHaveFocus();
  await act(() => userEvent.type(input, "approv"));
  expect(screen.getByRole("option", { name: /Approvals/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByRole("option", { name: /^Agents/ })).not.toBeInTheDocument();
  await act(() => userEvent.keyboard("{Enter}"));
  expect(onClose).toHaveBeenCalled();
  expect(screen.getByTestId("where").textContent).toBe("/approvals");
});

test("viewers are not offered actions they cannot take", async () => {
  signIn("viewer");
  mockApi({ "/api/search": [] });
  renderPalette();
  expect(screen.queryByText("New workflow")).not.toBeInTheDocument();
  expect(screen.queryByText(/New lead asking for a 15% discount/)).not.toBeInTheDocument();
  expect(screen.getByText("Runs")).toBeInTheDocument();
});

test("search hits from the API appear above commands", async () => {
  signIn();
  mockApi({
    "/api/search": [{ kind: "run", id: "r1", title: "New lead workflow for Dana Reyes", subtitle: "Completed", href: "/runs/r1" }],
  });
  renderPalette();
  await act(() => userEvent.type(screen.getByRole("combobox"), "dana"));
  const hit = await screen.findByRole("option", { name: /Dana Reyes/ });
  expect(hit).toHaveAttribute("aria-selected", "true");
});
