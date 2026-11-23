import { Segmented } from "./index";

export function RangeToggle({ value, onChange, options = [7, 30, 90] }: { value: number; onChange: (n: number) => void; options?: number[] }) {
  return <Segmented label="Time range" value={value} onChange={onChange} options={options.map((d) => ({ value: d, label: `${d}d` }))} />;
}
