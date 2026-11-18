import { layoutWorkflow } from "@/components/workflow/WorkflowGraph";

const lead = {
  name: "New lead workflow",
  trigger: { event: "lead.created", filter: {} },
  steps: [
    { id: "sales", type: "agent", role: "sales", goal: "Qualify" },
    { id: "check_qualified", type: "condition", if: "blackboard.qualified == true", then: "scheduler", else: "notify_email" },
    { id: "scheduler", type: "agent", role: "scheduler", goal: "Book", next: "end" },
    { id: "notify_email", type: "notify", channel: "email", template: "nurture", next: "end" },
  ],
};

test("condition branches sit side by side on the same layer", () => {
  const { nodes, edges } = layoutWorkflow(lead);
  const at = (id: string) => nodes.find((n) => n.id === id)!;
  expect(at("sales").layer).toBe(0);
  expect(at("check_qualified").layer).toBe(1);
  expect(at("scheduler").layer).toBe(2);
  expect(at("notify_email").layer).toBe(2);
  expect(at("scheduler").x).not.toBe(at("notify_email").x);
  expect(at("end").layer).toBe(3);
  expect(edges).toContainEqual({ from: "check_qualified", to: "scheduler", label: "yes" });
  expect(edges).toContainEqual({ from: "check_qualified", to: "notify_email", label: "no" });
});

test("steps without next fall through in order", () => {
  const { edges } = layoutWorkflow({
    name: "x",
    trigger: { event: "e" },
    steps: [
      { id: "a", type: "wait", seconds: 5 },
      { id: "b", type: "wait", seconds: 5 },
    ],
  });
  expect(edges).toEqual([
    { from: "a", to: "b" },
    { from: "b", to: "end" },
  ]);
});
