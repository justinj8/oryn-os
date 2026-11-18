import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Button } from "@/components/ui";
import { useAuth } from "./AuthProvider";

const DEMO = [
  { email: "owner@northwind.test", who: "Owner at Northwind HVAC" },
  { email: "admin@northwind.test", who: "Admin at Northwind HVAC (can approve refunds)" },
  { email: "owner@brightsmile.test", who: "Owner at Brightsmile Dental" },
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
    <main className="grid min-h-screen place-items-center bg-rail px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3 text-white">
          <img src="/favicon.svg" alt="" className="h-9 w-9" />
          <div>
            <p className="font-display text-2xl font-semibold leading-none">Oryn OS</p>
            <p className="text-sm text-rail-ink">Your AI workforce, on one board</p>
          </div>
        </div>
        <form onSubmit={submit} className="rounded-lg bg-panel p-6 shadow-xl">
          <label className="block text-sm font-medium" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            className="mt-1 w-full rounded-md border border-line bg-paper px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
          />
          <label className="mt-4 block text-sm font-medium" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="mt-1 w-full rounded-md border border-line bg-paper px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          {error && <p className="mt-3 text-sm text-fail">{error}</p>}
          <Button variant="primary" type="submit" className="mt-5 w-full py-2" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <div className="mt-5 border-t border-line pt-4">
            <p className="text-sm text-ink-3">Demo accounts (password oryn-demo)</p>
            <ul className="mt-2 space-y-1">
              {DEMO.map((d) => (
                <li key={d.email}>
                  <button type="button" className="text-left text-sm text-flight hover:underline" onClick={() => setEmail(d.email)}>
                    {d.who}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </form>
      </div>
    </main>
  );
}
