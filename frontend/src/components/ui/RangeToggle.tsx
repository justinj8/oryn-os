import { cx } from "./index";

export function RangeToggle({ value, onChange, options = [7, 30, 90] }: { value: number; onChange: (n: number) => void; options?: number[] }) {
  return (
    <div role="radiogroup" aria-label="Time range" className="inline-flex rounded-md border border-line bg-panel p-0.5">
      {options.map((d) => (
        <button
          key={d}
          role="radio"
          aria-checked={value === d}
          onClick={() => onChange(d)}
          className={cx("rounded px-2.5 py-1 text-sm", value === d ? "bg-ink text-paper" : "text-ink-2 hover:text-ink")}
        >
          {d} days
        </button>
      ))}
    </div>
  );
}
