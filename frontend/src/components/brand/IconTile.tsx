import type { LucideIcon } from "lucide-react";
import { cx } from "@/components/ui";

/** Color for a tile, from the system palette. Each place in the product keeps one color everywhere. */
export type TileColor = "blue" | "indigo" | "orange" | "purple" | "teal" | "green" | "pink" | "red" | "gray";

const BG: Record<TileColor, string> = {
  blue: "bg-[#0a84ff]",
  indigo: "bg-[#5e5ce6]",
  orange: "bg-[#ff9f0a]",
  purple: "bg-[#bf5af2]",
  teal: "bg-[#30b0c7]",
  green: "bg-[#30d158]",
  pink: "bg-[#ff375f]",
  red: "bg-[#ff453a]",
  gray: "bg-[#8e8e93]",
};

/** A white glyph on a rounded colored square, the way macOS and iOS mark places in Settings. */
export function IconTile({ icon: Icon, color, size = 22, className }: { icon: LucideIcon; color: TileColor; size?: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-flex shrink-0 items-center justify-center text-white shadow-[inset_0_0_0_0.5px_rgb(0_0_0/0.08)]", BG[color], className)}
      style={{ width: size, height: size, borderRadius: size * 0.27 }}
    >
      <Icon size={Math.round(size * 0.62)} strokeWidth={2.2} />
    </span>
  );
}
