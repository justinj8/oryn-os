import { useState, type FormEvent } from "react";
import { api, type S } from "@/api/client";
import { Button } from "@/components/ui";

export function EmailSim({ slug }: { slug: string }) {
  const [from, setFrom] = useState("ann.lee@example.com");
  const [subject, setSubject] = useState("Question about my service");
  const [body, setBody] = useState("What is your refund policy?");
  const [reply, setReply] = useState<S["AgentReply"] | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      setReply(
        await api.post<S["AgentReply"]>(`/api/webhooks/${slug}/email/inbound`, {
          from,
          to: `help@${slug}.test`,
          subject,
          text: body,
          message_id: `<${crypto.randomUUID()}@sim>`,
        }),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-2 text-sm">
      <input aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)} className="w-full rounded-md border border-line bg-paper px-3 py-1.5" />
      <input aria-label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full rounded-md border border-line bg-paper px-3 py-1.5" />
      <textarea aria-label="Body" rows={3} value={body} onChange={(e) => setBody(e.target.value)} className="w-full rounded-md border border-line bg-paper px-3 py-1.5" />
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "Sending…" : "Send email to the business"}
      </Button>
      {reply && (
        <div className="rounded-md border border-line bg-paper p-3">
          <p className="text-ink-3">Reply sent to {from}</p>
          <p className="mt-1">{reply.text}</p>
        </div>
      )}
    </form>
  );
}
