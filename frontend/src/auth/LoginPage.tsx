import { ArrowLeft, Check } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";
import { Button, cx } from "@/components/ui";
import { useAuth } from "./AuthProvider";

const DEMO = [
  { email: "owner@northwind.test", who: "Olivia, owner", where: "Northwind HVAC", can: "Sees everything, manages people and keys" },
  { email: "admin@northwind.test", who: "Admin", where: "Northwind HVAC", can: "Approves refunds up to the admin limit" },
  { email: "operator@northwind.test", who: "Operator", where: "Northwind HVAC", can: "Fires events, approves everyday actions" },
  { email: "owner@brightsmile.test", who: "Owner", where: "Brightsmile Dental", can: "A second, fully isolated business" },
];

export function LoginPage() {
  const { user, login } = useAuth();
  const loc = useLocation();
  const [email, setEmail] = useState(DEMO[0].email);
  const [password, setPassword] = useState("oryn-demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={(loc.state as { from?: string } | null)?.from ?? "/"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-dvh bg-paper lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex flex-col px-6 py-6 sm:px-12">
        <div className="flex items-center justify-between">
          <Link to="/" aria-label="Oryn OS home">
            <Logo />
          </Link>
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink">
            <ArrowLeft size={15} aria-hidden /> Home
          </Link>
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-12">
          <h1 className="font-display text-[38px]">Sign in</h1>
          <p className="mt-2 text-[15px] text-ink-3">Pick a demo account to see the product as that person would.</p>
          <form onSubmit={submit} className="mt-8">
            <label className="block text-[13px] font-medium text-ink-2" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="mt-1.5 h-11 w-full rounded-xl border border-line-2 bg-panel px-3.5 text-[15px] outline-none transition-colors focus:border-accent"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
            />
            <label className="mt-4 block text-[13px] font-medium text-ink-2" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="mt-1.5 h-11 w-full rounded-xl border border-line-2 bg-panel px-3.5 text-[15px] outline-none transition-colors focus:border-accent"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
            {error && (
              <p role="alert" className="mt-3 text-sm text-fail">
                {error}
              </p>
            )}
            <Button variant="primary" size="lg" type="submit" className="mt-6 w-full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p className="mt-6 text-[13px] text-ink-3">Every demo account uses the password oryn-demo. This runs on your machine only.</p>
          <div className="mt-5 flex flex-wrap gap-2 lg:hidden">
            {DEMO.map((d) => (
              <button
                key={d.email}
                type="button"
                onClick={() => setEmail(d.email)}
                className={cx(
                  "rounded-full border px-3 py-1.5 text-[13px] transition-colors",
                  d.email === email ? "border-ink bg-ink text-paper" : "border-line-2 text-ink-2 hover:border-ink-3/50",
                )}
              >
                {d.who}, {d.where}
              </button>
            ))}
          </div>
        </div>
      </div>

      <aside className="hidden flex-col justify-center border-l border-line bg-panel px-12 py-12 lg:flex">
        <div className="mx-auto w-full max-w-[460px]">
          <p className="text-[13px] font-medium text-ink-3">Demo accounts</p>
          <ul className="mt-3 divide-y divide-line rounded-2xl border border-line" aria-label="Demo accounts">
            {DEMO.map((d) => {
              const on = d.email === email;
              return (
                <li key={d.email}>
                  <button
                    type="button"
                    onClick={() => setEmail(d.email)}
                    aria-pressed={on}
                    className={cx("flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors first:rounded-t-2xl last:rounded-b-2xl", on ? "bg-accent-soft" : "hover:bg-sunk/70")}
                  >
                    <span
                      className={cx(
                        "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                        on ? "border-accent bg-accent text-white" : "border-line-2",
                      )}
                      aria-hidden
                    >
                      {on && <Check size={12} strokeWidth={3} />}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[15px] font-medium text-ink">
                        {d.who} <span className="font-normal text-ink-3">at {d.where}</span>
                      </span>
                      <span className="block text-[13px] text-ink-3">{d.can}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-6 text-sm leading-relaxed text-ink-3">
            Try it with two windows: send a lead as the operator, then approve the discount as the admin. People can't approve runs they
            started themselves.
          </p>
        </div>
      </aside>
    </main>
  );
}
