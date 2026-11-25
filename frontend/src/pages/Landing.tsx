import { BriefcaseBusiness, CalendarDays, ChartColumn, ChevronRight, LifeBuoy, Lock, Receipt, RotateCcw, Terminal } from "lucide-react";
import { Link } from "react-router-dom";
import { DEMO } from "@/api/client";
import { IconTile, type TileColor } from "@/components/brand/IconTile";
import { Logo } from "@/components/brand/Logo";
import { ThemeToggle } from "@/components/chrome/ThemeToggle";
import { LiveApp } from "@/components/landing/LiveApp";

const REPO = "https://github.com/justinj8/oryn-os";

const AGENTS: { name: string; job: string; channels: string; icon: typeof Lock; color: TileColor }[] = [
  { name: "Sales", job: "Qualifies new leads, creates deals and proposes terms.", channels: "Web, email, SMS", icon: BriefcaseBusiness, color: "blue" },
  { name: "Support", job: "Answers tickets and issues refunds inside your limits.", channels: "Chat, email", icon: LifeBuoy, color: "green" },
  { name: "Scheduler", job: "Finds a slot, books it and sends the confirmation.", channels: "Phone, email", icon: CalendarDays, color: "orange" },
  { name: "Ops", job: "Chases overdue invoices with polite reminders.", channels: "SMS", icon: Receipt, color: "red" },
  { name: "Reporting", job: "Queries your database and writes the weekly summary.", channels: "Email", icon: ChartColumn, color: "purple" },
];

const STEPS = [
  { title: "A lead arrives", body: "From your website, a text or an email. Oryn records it once, however many times it's delivered." },
  { title: "Sales qualifies it", body: "Looks up the contact, opens a deal and proposes terms, all on the record." },
  { title: "You approve the discount", body: "It's over your 10% limit, so the run waits for a person. Days, if it has to." },
  { title: "Scheduler books it", body: "Finds a slot, books it and emails a confirmation. The booking happens exactly once." },
];

const POLICY = [
  { action: "Discounts", free: "Up to 10%", above: "An operator approves" },
  { action: "Refunds", free: "Up to $200", above: "Operator, or admin over $500" },
  { action: "Any amount", free: "Up to $5,000", above: "Only the owner" },
];

function ChevronLink({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="group inline-flex items-center gap-0.5 text-[17px] text-accent hover:underline">
      {children}
      <ChevronRight size={17} className="transition-transform group-hover:translate-x-0.5" aria-hidden />
    </a>
  );
}

const H2 = "text-[36px] leading-[1.08] font-semibold tracking-[-0.028em] text-balance sm:text-[48px]";

export default function Landing() {
  return (
    <div className="min-h-dvh text-ink">
      <header className="material sticky top-0 z-30 shadow-[0_0.5px_0_var(--line)]">
        <div className="mx-auto flex h-12 max-w-[1240px] items-center justify-between px-5">
          <Link to="/" aria-label="Oryn OS home">
            <Logo className="scale-90" />
          </Link>
          <nav aria-label="Site" className="hidden items-center gap-8 text-[13px] text-ink-2 md:flex">
            <a href="#how" className="hover:text-ink">
              How it works
            </a>
            <a href="#agents" className="hover:text-ink">
              Agents
            </a>
            <a href="#safety" className="hover:text-ink">
              Safety
            </a>
            <a href={REPO} target="_blank" rel="noreferrer" className="hover:text-ink">
              Source
            </a>
          </nav>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link to="/login" className="hidden text-[13px] text-ink-2 hover:text-ink sm:inline">
              Sign in
            </Link>
            <Link to="/login" className="inline-flex h-7 items-center rounded-full bg-accent px-3.5 text-[12.5px] font-medium text-white hover:brightness-110">
              Open the app
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="px-5 pt-20 pb-10 text-center sm:pt-28">
          <p className="animate-[rise_500ms_var(--ease-out)] text-[17px] font-semibold text-ink-2">Oryn OS</p>
          <h1 className="mx-auto mt-3 max-w-[14ch] animate-[rise_600ms_var(--ease-out)] text-[48px] leading-[1.03] font-semibold tracking-[-0.035em] text-balance sm:text-[76px] lg:text-[88px]">
            AI agents that ask before they act.
          </h1>
          <p className="mx-auto mt-6 max-w-[36ch] animate-[rise_700ms_var(--ease-out)] text-[19px] leading-snug text-balance text-ink-3 sm:text-[22px]">
            Sales, support, scheduling and back-office work, done end to end. A person signs off on anything risky.
          </p>
          <div className="mt-9 flex animate-[rise_800ms_var(--ease-out)] flex-wrap items-center justify-center gap-x-8 gap-y-4">
            <Link to="/login" className="inline-flex h-11 items-center rounded-full bg-accent px-6 text-[16px] font-medium text-white transition hover:brightness-110 active:scale-[0.98]">
              Open the app
            </Link>
            <ChevronLink href={REPO}>Read the code</ChevronLink>
          </div>
        </section>

        <section aria-label="The app" className="px-3 pb-24 sm:px-6">
          <div className="mx-auto max-w-[1240px] animate-[rise_900ms_var(--ease-out)]">
            <LiveApp />
            <p className="mx-auto mt-5 max-w-[60ch] text-center text-[13px] text-balance text-ink-3">
              {DEMO
                ? "This is the real interface, running in your browser on a recording of the system. Click around: open a run, or approve the request that's waiting."
                : "The dashboard after you sign in."}
            </p>
          </div>
        </section>

        <section id="how" className="glass scroll-mt-14 border-y border-line/60 px-5 py-24 sm:py-28">
          <div className="mx-auto max-w-[1100px]">
            <h2 className={`${H2} max-w-[20ch]`}>How a lead becomes a booked meeting.</h2>
            <ol className="mt-14 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map((s, i) => (
                <li key={s.title} className="border-t border-line-2 pt-5">
                  <p className="font-figure text-[15px] text-accent">{i + 1}</p>
                  <p className="mt-3 text-[19px] font-semibold tracking-[-0.015em]">{s.title}</p>
                  <p className="mt-2 text-[15px] leading-relaxed text-ink-3">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="agents" className="scroll-mt-14 px-5 py-24 sm:py-28">
          <div className="mx-auto max-w-[1100px]">
            <h2 className={`${H2} max-w-[18ch]`}>Five specialists. One board.</h2>
            <p className="mt-4 max-w-[52ch] text-[17px] text-ink-3">They hand work to each other, share what they learn on the run, and remember customers between runs.</p>
            <ul className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {AGENTS.map((a) => (
                <li key={a.name} className="card flex flex-col gap-4 p-5">
                  <IconTile icon={a.icon} color={a.color} size={36} />
                  <div>
                    <p className="text-[17px] font-semibold tracking-[-0.015em]">{a.name}</p>
                    <p className="mt-1 text-[14px] leading-snug text-ink-3">{a.job}</p>
                  </div>
                  <p className="mt-auto text-[12px] text-ink-3">{a.channels}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="safety" className="scroll-mt-14 px-5 pb-24 sm:pb-28">
          <div className="mx-auto max-w-[1100px]">
            <h2 className={`${H2} max-w-[20ch]`}>Safe by design. Built to last.</h2>
            <div className="mt-12 grid gap-3 lg:grid-cols-6">
              <div className="card p-7 lg:col-span-4">
                <p className="text-[14px] font-semibold text-hold">Approvals</p>
                <p className="mt-1.5 text-[26px] leading-tight font-semibold tracking-[-0.022em]">Your limits, enforced in code.</p>
                <dl className="mt-6 divide-y divide-line/80">
                  {POLICY.map((p) => (
                    <div key={p.action} className="grid grid-cols-[1fr_auto] items-baseline gap-x-6 gap-y-1 py-3.5 sm:grid-cols-[140px_160px_1fr]">
                      <dt className="text-[14px] text-ink-3">{p.action}</dt>
                      <dd className="font-figure text-[22px] whitespace-nowrap">{p.free}</dd>
                      <dd className="col-span-2 text-[14px] text-ink-2 sm:col-span-1">{p.above}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-3 text-[12px] text-ink-3">Defaults. Each workflow sets its own. Nobody can approve a run they started.</p>
              </div>
              <div className="card flex flex-col p-7 lg:col-span-2">
                <p className="text-[14px] font-semibold text-clear">Durability</p>
                <p className="mt-auto pt-8 font-figure text-[88px] leading-none">1</p>
                <p className="mt-2 text-[17px] leading-snug font-semibold tracking-[-0.015em]">booking, after we killed the worker mid-booking.</p>
                <p className="mt-1.5 text-[14px] text-ink-3">Every run is a Temporal workflow. Crashes resume; they don't repeat.</p>
              </div>
              {[
                { icon: Lock, color: "indigo" as TileColor, title: "Tenants can't see each other.", body: "Postgres row-level security on every table. The agents' SQL tool runs under a read-only role." },
                { icon: RotateCcw, color: "teal" as TileColor, title: "Retries never double-send.", body: "Side effects carry idempotency keys, so a retry can't text a customer or refund a card twice." },
                { icon: Terminal, color: "gray" as TileColor, title: "Runs on your laptop.", body: "make up starts everything with no keys. Claude, Twilio and SMTP switch on with environment variables." },
              ].map((t) => (
                <div key={t.title} className="card p-7 lg:col-span-2">
                  <IconTile icon={t.icon} color={t.color} size={36} />
                  <p className="mt-5 text-[19px] leading-tight font-semibold tracking-[-0.018em]">{t.title}</p>
                  <p className="mt-1.5 text-[14px] text-ink-3">{t.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-line/70 px-5 py-24 text-center sm:py-28">
          <h2 className="text-[44px] leading-none font-semibold tracking-[-0.035em] sm:text-[64px]">See it run.</h2>
          <p className="mx-auto mt-4 max-w-[40ch] text-[17px] text-balance text-ink-3">Four demo roles, two weeks of history and a request waiting for a decision.</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
            <Link to="/login" className="inline-flex h-11 items-center rounded-full bg-accent px-6 text-[16px] font-medium text-white transition hover:brightness-110 active:scale-[0.98]">
              Open the app
            </Link>
            <ChevronLink href={REPO}>Read the code</ChevronLink>
          </div>
        </section>
      </main>

      <footer className="border-t border-line/70">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-4 px-5 py-6 text-[12px] text-ink-3">
          <p>A portfolio project. Every customer and number in the demo is made up.</p>
          <a href={REPO} target="_blank" rel="noreferrer" className="hover:text-ink">
            Source on GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
