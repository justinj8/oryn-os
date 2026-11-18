import { render, screen } from "@testing-library/react";
import { buildSpanTree, TraceWaterfall, type SpanLike } from "@/components/trace/TraceWaterfall";

const t = (s: number) => new Date(Date.UTC(2026, 10, 16, 13, 0, s)).toISOString();
const span = (id: string, parent: string | null, start: number, end: number | null, kind = "tool_call"): SpanLike => ({
  id,
  parent_span_id: parent,
  agent_id: null,
  kind,
  name: id,
  status: "ok",
  input: null,
  output: null,
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: "0",
  simulated: true,
  attempt: 1,
  started_at: t(start),
  ended_at: end === null ? null : t(end),
});

test("buildSpanTree nests children under parents and orders by start time", () => {
  const rows = buildSpanTree([span("b-child", "a", 3, 4), span("a", null, 0, 10, "agent"), span("a-child", "a", 1, 2), span("z", null, 11, 12)]);
  expect(rows.map((r) => [r.span.id, r.depth])).toEqual([
    ["a", 0],
    ["a-child", 1],
    ["b-child", 1],
    ["z", 0],
  ]);
});

test("orphans whose parent is missing are treated as roots", () => {
  const rows = buildSpanTree([span("x", "missing", 0, 1)]);
  expect(rows[0].depth).toBe(0);
});

test("bar width is proportional to duration and offset to start", () => {
  render(<TraceWaterfall spans={[span("root", null, 0, 10, "agent"), span("half", "root", 5, 10)]} onSelect={() => {}} />);
  const bar = screen.getByTestId("bar-half");
  expect(bar.style.left).toBe("50%");
  expect(bar.style.width).toBe("50%");
});
