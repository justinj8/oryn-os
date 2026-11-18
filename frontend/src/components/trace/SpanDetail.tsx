import { Json, Tag } from "@/components/ui";
import { cost, duration, num } from "@/lib/format";
import { KIND, type SpanLike } from "./TraceWaterfall";

export function SpanDetail({ span }: { span: SpanLike }) {
  const dur = span.ended_at ? (new Date(span.ended_at).getTime() - new Date(span.started_at).getTime()) / 1000 : null;
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-ink-3">Kind</dt>
        <dd>{KIND[span.kind]?.label ?? span.kind}</dd>
        <dt className="text-ink-3">Status</dt>
        <dd>{span.status === "error" ? <Tag tone="fail">error</Tag> : span.status}</dd>
        <dt className="text-ink-3">Duration</dt>
        <dd>{duration(dur)}</dd>
        <dt className="text-ink-3">Attempt</dt>
        <dd>{span.attempt}</dd>
        {span.kind === "llm_call" && (
          <>
            <dt className="text-ink-3">Tokens in / out</dt>
            <dd>
              {num(span.input_tokens)} / {num(span.output_tokens)}
            </dd>
            <dt className="text-ink-3">Cost</dt>
            <dd>
              {cost(span.cost_usd)} {span.simulated && <Tag>simulated</Tag>}
            </dd>
          </>
        )}
      </dl>
      <div>
        <h3 className="mb-1 text-sm font-medium">Input</h3>
        <Json value={span.input} />
      </div>
      <div>
        <h3 className="mb-1 text-sm font-medium">Output</h3>
        <Json value={span.output} />
      </div>
    </div>
  );
}
