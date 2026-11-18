import { useState } from "react";
import { getAuth } from "@/api/client";
import { cx } from "@/components/ui";
import { Composer, Thread } from "./ChatSim";

/** Posts the exact form payloads Twilio sends, to the real webhook handlers. */
async function twilio(path: string, form: Record<string, string>): Promise<string> {
  const { token, tenantId } = getAuth();
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(tenantId ? { "X-Tenant-Id": tenantId } : {}) },
    body: new URLSearchParams(form).toString(),
  });
  const xml = new DOMParser().parseFromString(await res.text(), "application/xml");
  return [...xml.querySelectorAll("Message, Say")].map((n) => n.textContent).filter(Boolean).join(" ") || `(${res.status})`;
}

export function PhoneSim({ slug }: { slug: string }) {
  const [mode, setMode] = useState<"sms" | "voice">("sms");
  const [phone] = useState(() => `+1555${Math.floor(1000000 + Math.random() * 8999999)}`);
  const [callSid, setCallSid] = useState<string | null>(null);
  const [lines, setLines] = useState<{ who: "you" | "agent"; text: string }[]>([]);
  const [busy, setBusy] = useState(false);

  async function send(text: string) {
    setBusy(true);
    setLines((l) => [...l, { who: "you", text }]);
    try {
      let reply: string;
      if (mode === "sms") {
        reply = await twilio(`/api/webhooks/${slug}/twilio/sms`, { From: phone, To: "+15550000000", Body: text, MessageSid: `SM${crypto.randomUUID().replace(/-/g, "")}` });
      } else {
        const sid = callSid ?? `CA${crypto.randomUUID().replace(/-/g, "")}`;
        if (!callSid) {
          setCallSid(sid);
          const greeting = await twilio(`/api/webhooks/${slug}/twilio/voice`, { CallSid: sid, From: phone });
          setLines((l) => [...l.slice(0, -1), { who: "agent", text: `📞 ${greeting}` }, l[l.length - 1]]);
        }
        reply = await twilio(`/api/webhooks/${slug}/twilio/voice`, { CallSid: sid, From: phone, SpeechResult: text });
      }
      setLines((l) => [...l, { who: "agent", text: reply }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <div className="inline-flex rounded-md border border-line p-0.5">
          {(["sms", "voice"] as const).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setLines([]);
                setCallSid(null);
              }}
              className={cx("rounded px-2 py-0.5", mode === m ? "bg-ink text-paper" : "text-ink-2")}
            >
              {m === "sms" ? "Text message" : "Phone call"}
            </button>
          ))}
        </div>
        <span className="text-ink-3">from {phone}</span>
      </div>
      <Thread lines={lines.length ? lines : [{ who: "agent", text: mode === "sms" ? "Text the business as a customer would." : "Speak (type) what the caller says." }]} />
      <Composer onSend={send} busy={busy} placeholder={mode === "sms" ? "Text message" : "What the caller says"} />
    </div>
  );
}
