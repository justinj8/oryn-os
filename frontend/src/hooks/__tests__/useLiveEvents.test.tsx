import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { useLiveEvents } from "@/hooks/useLiveEvents";

class FakeEventSource {
  static last: FakeEventSource | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  emit(type: string, data: unknown) {
    for (const fn of this.listeners[type] ?? []) fn(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
  close() {
    this.closed = true;
  }
}

test("invalidates runs and metrics on run.updated, and closes on unmount", () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  const onEvent = vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  const { unmount } = renderHook(() => useLiveEvents({ tenantId: "t1", token: "tok", onEvent }), { wrapper });
  const es = FakeEventSource.last!;
  expect(es.url).toContain("tenant_id=t1");
  es.emit("run.updated", { type: "run.updated", run_id: "r1", data: { status: "completed" } });
  expect(spy).toHaveBeenCalledWith({ queryKey: ["runs"] });
  expect(spy).toHaveBeenCalledWith({ queryKey: ["run", "r1"] });
  expect(spy).toHaveBeenCalledWith({ queryKey: ["metrics"] });
  expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "run.updated" }));
  unmount();
  expect(es.closed).toBe(true);
  vi.unstubAllGlobals();
});

test("does nothing without a tenant", () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  FakeEventSource.last = null;
  const qc = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  renderHook(() => useLiveEvents({ tenantId: null, token: "tok" }), { wrapper });
  expect(FakeEventSource.last).toBeNull();
  vi.unstubAllGlobals();
});
