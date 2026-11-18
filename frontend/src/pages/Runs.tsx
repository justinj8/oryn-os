import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { RunStrip } from "@/components/runs/RunStrip";
import { Button, Empty, ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import { STATUS } from "@/lib/status";

export default function Runs() {
  const { tenant } = useAuth();
  const [status, setStatus] = useState("");
  const q = useInfiniteQuery({
    queryKey: ["runs", "list", tenant?.tenant_id, status],
    queryFn: ({ pageParam }) => api.get<S["RunPage"]>("/api/runs", { status, limit: 30, before: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHeader
        title="Runs"
        sub="Every workflow, conversation and approved action, newest first."
        actions={
          <label className="flex items-center gap-2 text-sm">
            <span className="text-ink-3">Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-md border border-line bg-panel px-2 py-1.5">
              <option value="">All</option>
              {Object.entries(STATUS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
        }
      />
      <ErrorNote error={q.error} />
      {q.isLoading ? (
        <Skeleton className="h-40" />
      ) : items.length ? (
        <div className="grid gap-2">
          {items.map((r) => (
            <RunStrip key={r.id} run={r} />
          ))}
        </div>
      ) : (
        <Empty title="No runs match this filter">Runs appear here as soon as an event triggers a workflow.</Empty>
      )}
      {q.hasNextPage && (
        <div className="mt-4 text-center">
          <Button onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>
            {q.isFetchingNextPage ? "Loading…" : "Load older runs"}
          </Button>
        </div>
      )}
    </>
  );
}
