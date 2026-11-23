import { ArrowRight, Code } from "lucide-react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";
import { LiveDemo } from "@/components/landing/LiveDemo";

const REPO = "https://github.com/justinj8/oryn-os";

const AGENTS = [
  { name: "Sales", job: "Qualifies new leads, creates deals and proposes terms.", channels: "Web, email, SMS" },
  { name: "Support", job: "Answers tickets and issues refunds inside your limits.", channels: "Chat, email" },
  { name: "Scheduler", job: "Finds a slot, books it and sends the confirmation.", channels: "Phone, email" },
  { name: "Ops", job: "Chases overdue invoices with polite reminders.", channels: "SMS" },
  { name: "Reporting", job: "Queries your database and writes the weekly summary.", channels: "Email" },
];

const POLICY = [
  { action: "Discounts", free: "Up to 10%", above: "An operator approves" },
  { action: "Refunds", free: "Up to $200", above: "An operator approves, or an admin above $500" },
  { action: "Any amount", free: "Up to $5,000", above: "Only the owner can approve" },
  { action: "Self-approval", free: "Never", above: "The person who started a run can't approve it" },
];

const FACTS = [
  {
    title: "Runs survive crashes",
    body: "Every run is a durable Temporal workflow. Kill the worker mid-booking and it finishes with exactly one booking.",
  },
  {
    title: "Tenants can't see each other",
    body: "Postgres row-level security on every table, and the agents' SQL tool runs under a narrower read-only role.",
  },
  {
    title: "Retries never double-send",
    body: "Side effects carry idempotency keys, so a retried step can't text a customer or charge a card twice.",
  },
  {
    title: "Every step is on the record",
    body: "Model calls, tool calls, handoffs, retries and decisions are spans with tokens and cost, streamed live.",
  },
];

function NavBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-paper/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 sm:px-8">
        <Link to="/" aria-label="Oryn OS home">
          <Logo />
        </Link>
        <nav aria-label="Site" className="hidden items-center gap-8 text-sm text-ink-2 md:flex">
          <a href="#agents" className="hover:text-ink">
            Agents
          </a>
          <a href="#approvals" className="hover:text-ink">
            Approvals
          </a>
          <a href="#reliability" className="hover:text-ink">
            Reliability
          </a>
          <a href={REPO} className="inline-flex items-center gap-1.5 hover:text-ink" target="_blank" rel="noreferrer">
            <Code size={15} aria-hidden /> Source
          </a>
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/login" className="hidden h-9 items-center rounded-lg px-3 text-sm font-medium text-ink-2 hover:bg-sunk hover:text-ink sm:inline-flex">
            Sign in
          </Link>
          <Link to="/login" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-3.5 text-sm font-medium text-paper hover:bg-ink/85">
            Open the demo
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Landing() {
  return (
    <div className="min-h-dvh bg-paper text-ink">
      <NavBar />
      <main>
        <section className="mx-auto grid max-w-[1200px] items-center gap-14 px-5 pt-16 pb-24 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:pt-24 lg:pb-32">
          <div className="animate-[rise_420ms_var(--ease-out)]">
            <h1 className="max-w-[12ch] text-[52px] leading-[0.98] font-semibold tracking-[-0.045em] [font-stretch:86%] sm:text-[76px]">
              AI agents that ask before they act.
            </h1>
            <p className="mt-7 max-w-[34rem] text-[19px] leading-relaxed text-ink-2">
              Oryn OS runs your sales, support, scheduling and back-office work end to end, and stops for a person before anything risky
              happens. Try it: the run on the right is waiting for your call.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                to="/login"
                className="group inline-flex h-12 items-center gap-2 rounded-xl bg-ink px-5 text-[15px] font-medium text-paper transition-colors hover:bg-ink/85"
              >
                Open the live demo
                <ArrowRight size={17} className="transition-transform group-hover:translate-x-0.5" aria-hidden />
              </Link>
              <a
                href={REPO}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-12 items-center gap-2 rounded-xl border border-line-2 bg-panel px-5 text-[15px] font-medium hover:border-ink-3/50"
              >
                <Code size={17} aria-hidden /> Read the code
              </a>
            </div>
            <p className="mt-6 text-sm text-ink-3">Runs offline with one command. Claude, Twilio and SMTP switch on with environment variables.</p>
          </div>
          <div className="animate-[rise_520ms_var(--ease-out)]">
            <LiveDemo />
          </div>
        </section>

        <section id="agents" className="scroll-mt-20 border-t border-line bg-panel">
          <div className="mx-auto max-w-[1200px] px-5 py-24 sm:px-8">
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] lg:items-end">
              <h2 className="max-w-[16ch] text-[40px] leading-[1.02] font-semibold tracking-[-0.035em] sm:text-[52px]">One board for your whole AI workforce.</h2>
              <p className="max-w-xl text-[17px] leading-relaxed text-ink-2">
                Specialized agents hand work to each other, share what they learn on the run, and remember customers between runs. You
                watch all of it live, on one board.
              </p>
            </div>
            <ol className="mt-16 grid border-y border-line sm:grid-cols-2 lg:grid-cols-5">
              {AGENTS.map((a) => (
                <li
                  key={a.name}
                  className="flex flex-col gap-3 border-t border-line py-7 first:border-t-0 sm:pr-6 sm:nth-2:border-t-0 lg:border-t-0 lg:border-l lg:px-6 lg:py-9 lg:first:border-l-0 lg:first:pl-0"
                >
                  <span className="text-[22px] font-semibold tracking-[-0.02em]">{a.name}</span>
                  <span className="text-[15px] leading-relaxed text-ink-2">{a.job}</span>
                  <span className="mt-auto pt-3 text-[13px] text-ink-3">{a.channels}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="approvals" className="scroll-mt-20 border-t border-line">
          <div className="mx-auto grid max-w-[1200px] gap-14 px-5 py-24 sm:px-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div>
              <h2 className="max-w-[14ch] text-[40px] leading-[1.02] font-semibold tracking-[-0.035em] sm:text-[52px]">Your limits, enforced in code.</h2>
              <p className="mt-6 max-w-md text-[17px] leading-relaxed text-ink-2">
                Before an agent touches the outside world, one policy function decides whether a person must sign off, and how senior
                they need to be. Approvals wait for days if they have to, escalate up the ladder, and never run twice.
              </p>
            </div>
            <div className="overflow-hidden rounded-2xl border border-line bg-panel">
              <table className="w-full text-left text-[15px]">
                <thead className="text-[13px] text-ink-3">
                  <tr className="border-b border-line">
                    <th className="px-5 py-3 font-normal">Action</th>
                    <th className="px-5 py-3 font-normal">Agents may do alone</th>
                    <th className="px-5 py-3 font-normal">Above that</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {POLICY.map((p) => (
                    <tr key={p.action}>
                      <td className="px-5 py-4 font-medium">{p.action}</td>
                      <td className="px-5 py-4 font-figure text-[22px]">{p.free}</td>
                      <td className="px-5 py-4 text-ink-2">{p.above}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="border-t border-line bg-paper/60 px-5 py-3 text-[13px] text-ink-3">Default policy. Each workflow can set its own limits.</p>
            </div>
          </div>
        </section>

        <section id="reliability" className="scroll-mt-20 border-t border-line bg-panel">
          <div className="mx-auto max-w-[1200px] px-5 py-24 sm:px-8">
            <h2 className="max-w-[18ch] text-[40px] leading-[1.02] font-semibold tracking-[-0.035em] sm:text-[52px]">Built like infrastructure, not a chatbot.</h2>
            <dl className="mt-14 grid gap-x-10 gap-y-12 sm:grid-cols-2">
              {FACTS.map((f) => (
                <div key={f.title} className="border-t border-ink pt-5">
                  <dt className="text-[20px] font-semibold tracking-[-0.015em]">{f.title}</dt>
                  <dd className="mt-2 max-w-md text-[15px] leading-relaxed text-ink-2">{f.body}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="border-t border-line">
          <div className="mx-auto flex max-w-[1200px] flex-col items-start justify-between gap-8 px-5 py-20 sm:px-8 md:flex-row md:items-end">
            <h2 className="max-w-[18ch] text-[40px] leading-[1.02] font-semibold tracking-[-0.035em] sm:text-[52px]">See it run on two weeks of real history.</h2>
            <Link
              to="/login"
              className="group inline-flex h-12 shrink-0 items-center gap-2 rounded-xl bg-accent px-5 text-[15px] font-medium text-white transition-colors hover:bg-accent/90"
            >
              Open the live demo
              <ArrowRight size={17} className="transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          </div>
        </section>
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-5 py-8 text-sm text-ink-3 sm:px-8">
          <Logo className="opacity-80" />
          <p>A portfolio project. Every customer and number in the demo is made up.</p>
          <a href={REPO} target="_blank" rel="noreferrer" className="hover:text-ink">
            Source on GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
