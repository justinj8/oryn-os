import { useEffect, useRef, useState } from "react";
import { DEMO } from "@/api/client";

const W = 1440;
const H = 900;

/**
 * The real app in a window, on the website. In the hosted demo it is live and clickable (an iframe of
 * /preview, scaled to fit); elsewhere, and on phones where it would be too small to use, it is a still.
 */
export function LiveApp() {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.75);
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      setScale(e.contentRect.width / W);
      setWide(e.contentRect.width >= 720);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const live = DEMO && wide;
  return (
    <div className="overflow-hidden rounded-[14px] bg-panel text-left shadow-[0_0_0_0.5px_rgb(0_0_0/0.12),0_40px_100px_-30px_rgb(0_0_0/0.45),0_18px_40px_-20px_rgb(0_0_0/0.25)]">
      <div className="flex h-8 items-center gap-2 border-b border-line/80 bg-sidebar px-3.5" aria-hidden>
        <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
        <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
        <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        <span className="flex-1 text-center text-[12px] font-medium text-ink-3">Oryn OS</span>
        <span className="w-12" />
      </div>
      <div ref={box} className="relative w-full" style={{ height: H * scale }}>
        {live ? (
          <iframe
            src="/preview"
            title="Oryn OS, running live in your browser"
            className="absolute top-0 left-0 origin-top-left border-0"
            style={{ width: W, height: H, transform: `scale(${scale})` }}
          />
        ) : (
          <picture>
            <source srcSet="/product/overview-dark.jpg" media="(prefers-color-scheme: dark)" />
            <img src="/product/overview-light.jpg" alt="The Oryn OS overview: a summary of the month, a metric chart, work waiting on you and live runs" className="block h-full w-full object-cover object-top" />
          </picture>
        )}
      </div>
    </div>
  );
}
