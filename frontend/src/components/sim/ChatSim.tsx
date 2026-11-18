import { Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, type S } from "@/api/client";
import { Button, cx } from "@/components/ui";

type Line = { who: "you" | "agent"; text: string; status?: string };

export function Thread({ lines }: { lines: Line[] }) {
  return (
    <ol className="flex h-72 flex-col gap-2 overflow-y-auto rounded-md bg-paper p-3" aria-live="polite">
      {lines.map((l, i) => (
        <li key={i} className={cx("max-w-[85%] rounded-lg px-3 py-2 text-sm", l.who === "you" ? "self-end bg-ink text-paper" : "self-start border border-line bg-panel")}>
          {l.text}
          {l.status && l.status !== "ok" && <span className="mt-1 block text-xs text-hold">{l.status.replace("_", " ")}</span>}
        </li>
      ))}
    </ol>
  );
}

export function Composer({ onSend, busy, placeholder }: { onSend: (t: string) => void; busy: boolean; placeholder: string }) {
  const [text, setText] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  }
  return (
    <form onSubmit={submit} className="mt-2 flex gap-2">
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} className="min-w-0 flex-1 rounded-md border border-line bg-paper px-3 py-1.5 text-sm" />
      <Button type="submit" variant="primary" disabled={busy} aria-label="Send">
        <Send size={15} />
      </Button>
    </form>
  );
}

export function ChatSim({ slug }: { slug: string }) {
  const [session, setSession] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [busy, setBusy] = useState(false);
  async function send(text: string) {
    setBusy(true);
    setLines((l) => [...l, { who: "you", text }]);
    try {
      const sid = session ?? (await api.post<{ session_id: string }>(`/api/chat/${slug}/sessions`)).session_id;
      setSession(sid);
      const r = await api.post<S["AgentReply"]>(`/api/chat/${slug}/sessions/${sid}/messages`, { text });
      setLines((l) => [...l, { who: "agent", text: r.text, status: r.status }]);
    } catch (e) {
      setLines((l) => [...l, { who: "agent", text: (e as Error).message, status: "error" }]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <Thread lines={lines.length ? lines : [{ who: "agent", text: "Try “I'd like to book an appointment” or “What is your refund policy?”" }]} />
      <Composer onSend={send} busy={busy} placeholder="Message as a website visitor" />
    </div>
  );
}
