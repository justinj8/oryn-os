import { cx } from "@/components/ui";

type Step = { id: string; type: string; next?: string | null; then?: string; else?: string; [k: string]: unknown };
export type Definition = { name: string; trigger: { event: string; filter?: Record<string, unknown> }; steps: Step[] };
export type GNode = { id: string; type: string; label: string; detail: string; layer: number; x: number };
export type GEdge = { from: string; to: string; label?: string };

function nextOf(steps: Step[], i: number): string {
  return steps[i].next ?? steps[i + 1]?.id ?? "end";
}

function describe(s: Step): [string, string] {
  switch (s.type) {
    case "agent":
      return [`${String(s.role).replace(/^\w/, (c) => c.toUpperCase())} agent`, String(s.goal ?? "")];
    case "condition":
      return ["Condition", String(s.if ?? "")];
    case "approval":
      return ["Human approval", String(s.description ?? "")];
    case "wait": {
      const sec = Number(s.seconds);
      return ["Wait", sec >= 86400 ? `${sec / 86400} day(s)` : sec >= 3600 ? `${sec / 3600} hour(s)` : `${sec}s`];
    }
    case "notify":
      return [`Send ${s.channel === "sms" ? "text" : "email"}`, String(s.template ?? "").replace(/_/g, " ")];
    case "parallel":
      return ["In parallel", `${(s.branches as unknown[])?.length ?? 0} agents`];
    default:
      return [s.type, ""];
  }
}

/** Longest-path layering of the workflow DAG; siblings in a layer get distinct x slots. */
export function layoutWorkflow(def: Definition): { nodes: GNode[]; edges: GEdge[] } {
  const steps = def.steps ?? [];
  const edges: GEdge[] = [];
  steps.forEach((s, i) => {
    if (s.type === "condition") {
      edges.push({ from: s.id, to: s.then ?? "end", label: "yes" }, { from: s.id, to: s.else ?? "end", label: "no" });
    } else {
      edges.push({ from: s.id, to: nextOf(steps, i) });
    }
  });
  const layer = new Map<string, number>();
  const visit = (id: string, depth: number, seen: Set<string>) => {
    if (seen.has(id)) return; // cycle guard (the backend rejects cycles anyway)
    if ((layer.get(id) ?? -1) >= depth) return;
    layer.set(id, depth);
    for (const e of edges.filter((x) => x.from === id)) visit(e.to, depth + 1, new Set([...seen, id]));
  };
  if (steps.length) visit(steps[0].id, 0, new Set());
  const slots = new Map<number, number>();
  const nodes: GNode[] = [...steps.map((s) => s.id), "end"]
    .filter((id) => layer.has(id))
    .map((id) => {
      const s = steps.find((x) => x.id === id);
      const [label, detail] = s ? describe(s) : ["Done", ""];
      const l = layer.get(id)!;
      const x = slots.get(l) ?? 0;
      slots.set(l, x + 1);
      return { id, type: s?.type ?? "end", label, detail, layer: l, x };
    });
  return { nodes, edges };
}

const NODE_W = 210;
const NODE_H = 58;
const GAP_X = 28;
const GAP_Y = 46;

export function WorkflowGraph({ definition }: { definition: Definition }) {
  const { nodes, edges } = layoutWorkflow(definition);
  const perLayer = new Map<number, number>();
  nodes.forEach((n) => perLayer.set(n.layer, Math.max(perLayer.get(n.layer) ?? 0, n.x + 1)));
  const widest = Math.max(1, ...perLayer.values());
  const width = widest * NODE_W + (widest - 1) * GAP_X + 2;
  const layers = Math.max(...nodes.map((n) => n.layer), 0) + 1;
  const height = 40 + layers * (NODE_H + GAP_Y);
  const pos = (n: GNode) => {
    const count = perLayer.get(n.layer) ?? 1;
    const rowW = count * NODE_W + (count - 1) * GAP_X;
    return { x: (width - rowW) / 2 + n.x * (NODE_W + GAP_X), y: 40 + n.layer * (NODE_H + GAP_Y) };
  };
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return (
    <div className="overflow-x-auto">
      <svg width={width} height={height} role="img" aria-label={`Workflow graph: ${definition.name}`} className="mx-auto block">
        <text x={width / 2} y={18} textAnchor="middle" className="fill-[var(--ink-3)] text-[12px]">
          When {definition.trigger.event}
        </text>
        <line x1={width / 2} y1={24} x2={width / 2} y2={40} stroke="var(--ink-3)" />
        {edges.map((e, i) => {
          const a = byId.get(e.from);
          const b = byId.get(e.to);
          if (!a || !b) return null;
          const p = pos(a);
          const q = pos(b);
          const x1 = p.x + NODE_W / 2;
          const y1 = p.y + NODE_H;
          const x2 = q.x + NODE_W / 2;
          const y2 = q.y;
          const mid = (y1 + y2) / 2;
          return (
            <g key={i}>
              <path d={`M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2 - 4}`} fill="none" stroke="var(--ink-3)" strokeWidth={1.5} />
              <path d={`M${x2 - 4},${y2 - 8} L${x2},${y2 - 2} L${x2 + 4},${y2 - 8}`} fill="none" stroke="var(--ink-3)" strokeWidth={1.5} />
              {e.label && (
                <text x={(x1 + x2) / 2 + 6} y={mid - 2} className="fill-[var(--ink-2)] text-[12px] font-medium">
                  {e.label}
                </text>
              )}
            </g>
          );
        })}
        {nodes.map((n) => {
          const { x, y } = pos(n);
          const edge = { agent: "var(--flight)", condition: "var(--ink-3)", approval: "var(--hold)", notify: "var(--clear)", wait: "var(--idle)", end: "var(--ink)" }[n.type] ?? "var(--ink-3)";
          return (
            <g key={n.id} transform={`translate(${x},${y})`}>
              <rect width={NODE_W} height={NODE_H} rx={6} fill="var(--panel)" stroke="var(--line)" />
              <rect width={5} height={NODE_H} rx={2} fill={edge} />
              <text x={14} y={22} className={cx("fill-[var(--ink)] text-[14px] font-semibold")}>
                {n.label}
              </text>
              <text x={14} y={42} className="fill-[var(--ink-3)] text-[12px]">
                {n.detail.length > 30 ? n.detail.slice(0, 29) + "…" : n.detail}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
