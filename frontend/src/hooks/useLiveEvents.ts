import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

export type LiveEvent = { type: string; tenant_id: string; run_id: string | null; data: Record<string, unknown>; ts: string };

const TYPES = [
  "run.started",
  "run.updated",
  "span.started",
  "span.ended",
  "approval.requested",
  "approval.decided",
  "message.sent",
  "event.received",
] as const;

/** Subscribes to the tenant's live event stream (SSE) and keeps cached queries fresh. */
export function useLiveEvents({
  tenantId,
  token,
  onEvent,
}: {
  tenantId: string | null;
  token: string | null;
  onEvent?: (e: LiveEvent) => void;
}) {
  const qc = useQueryClient();
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!tenantId || !token || typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    let retry = 1000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const handle = (raw: MessageEvent) => {
      let ev: LiveEvent;
      try {
        ev = JSON.parse(raw.data);
      } catch {
        return;
      }
      retry = 1000;
      if (ev.type.startsWith("run.") || ev.type.startsWith("span.")) {
        qc.invalidateQueries({ queryKey: ["runs"] });
        if (ev.run_id) qc.invalidateQueries({ queryKey: ["run", ev.run_id] });
      }
      if (ev.type.startsWith("approval.")) qc.invalidateQueries({ queryKey: ["approvals"] });
      if (ev.type === "run.updated" || ev.type.startsWith("approval.")) qc.invalidateQueries({ queryKey: ["metrics"] });
      if (ev.type === "message.sent") qc.invalidateQueries({ queryKey: ["sandbox"] });
      handler.current?.(ev);
    };

    const connect = () => {
      if (stopped) return;
      es = new EventSource(`/api/events/stream?tenant_id=${encodeURIComponent(tenantId)}&token=${encodeURIComponent(token)}`);
      TYPES.forEach((t) => es!.addEventListener(t, handle as EventListener));
      es.addEventListener("error", () => {
        es?.close();
        if (stopped) return;
        timer = setTimeout(connect, retry);
        retry = Math.min(retry * 2, 30000);
      });
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      es?.close();
    };
  }, [tenantId, token, qc]);
}
