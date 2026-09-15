"use client";
/** The symbol key down the left margin: every shape in the notation, doubling as a filter. */
import { useSheet } from "@/lib/store";
import { SHAPE, TYPE_LABEL, TYPE_ORDER, INK, type Shape } from "@/lib/notation";
import type { EntityType } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Glyph({ shape, size = 14, stroke = INK.ink, fill = "none", className }: { shape: Shape; size?: number; stroke?: string; fill?: string; className?: string }) {
  const r = size / 2 - 1.5, c = size / 2;
  const d: Record<Shape, string> = {
    circle: `M${c + r},${c} a${r},${r} 0 1,0 ${-2 * r},0 a${r},${r} 0 1,0 ${2 * r},0`,
    square: `M${c - r},${c - r}h${2 * r}v${2 * r}h${-2 * r}z`,
    diamond: `M${c},${c - r * 1.15}L${c + r * 1.15},${c}L${c},${c + r * 1.15}L${c - r * 1.15},${c}z`,
    hexagon: Array.from({ length: 6 }, (_, i) => { const a = Math.PI / 3 * i - Math.PI / 6; return `${i ? "L" : "M"}${c + r * 1.1 * Math.cos(a)},${c + r * 1.1 * Math.sin(a)}`; }).join("") + "z",
    triangle: `M${c},${c - r * 1.2}L${c + r * 1.1},${c + r * 0.85}L${c - r * 1.1},${c + r * 0.85}z`,
    rect: `M${c - r * 1.3},${c - r * 0.75}h${2.6 * r}v${1.5 * r}h${-2.6 * r}z`,
    pin: `M${c},${c + r * 1.1} C${c - r * 1.2},${c - r * 0.2} ${c - r * 0.9},${c - r * 1.1} ${c},${c - r * 1.1} C${c + r * 0.9},${c - r * 1.1} ${c + r * 1.2},${c - r * 0.2} ${c},${c + r * 1.1}z`,
    tag: `M${c - r * 1.2},${c - r * 0.8}H${c + r * 0.7}L${c + r * 1.3},${c}L${c + r * 0.7},${c + r * 0.8}H${c - r * 1.2}z`,
    ring: `M${c + r},${c} a${r},${r} 0 1,0 ${-2 * r},0 a${r},${r} 0 1,0 ${2 * r},0 M${c + r * 0.45},${c} a${r * 0.45},${r * 0.45} 0 1,0 ${-0.9 * r},0 a${r * 0.45},${r * 0.45} 0 1,0 ${0.9 * r},0`,
    "cut-hexagon": Array.from({ length: 6 }, (_, i) => { const a = Math.PI / 3 * i - Math.PI / 6; return `${i ? "L" : "M"}${c + r * 1.1 * Math.cos(a)},${c + r * 1.1 * Math.sin(a)}`; }).join("")
      + `z M${c - r * 1.15},${c - r * 0.35}L${c - r * 0.35},${c - r * 1.15}`,
  };
  return <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={className} aria-hidden="true"><path d={d[shape]} fill={fill} stroke={stroke} strokeWidth={1.3} strokeLinejoin="round" fillRule="evenodd" /></svg>;
}

export function LineSample({ style, ink = INK.ink, width = 34 }: { style: "solid" | "dashed" | "dotted"; ink?: string; width?: number }) {
  const dash = style === "solid" ? undefined : style === "dashed" ? "6 4" : "1.5 3.5";
  return <svg width={width} height={8} viewBox={`0 0 ${width} 8`} aria-hidden="true"><line x1={1} y1={4} x2={width - 1} y2={4} stroke={ink} strokeWidth={1.4} strokeDasharray={dash} strokeLinecap="round" /></svg>;
}

export default function KeyRail({ counts }: { counts?: Record<string, number> }) {
  const hidden = useSheet((s) => s.hiddenTypes);
  const toggle = useSheet((s) => s.toggleType);
  const presentation = useSheet((s) => s.presentation);
  return (
    <nav aria-label="Symbol key and entity filters" className="flex h-full w-[var(--rail-w)] flex-col items-center border-r border-rule-strong bg-film-deep py-3">
      <span className="label mb-2 [writing-mode:vertical-rl] rotate-180 text-ink-faint">Key</span>
      <ul className="flex flex-col items-center gap-1">
        {TYPE_ORDER.map((t: EntityType) => {
          const off = hidden.includes(t);
          const n = counts?.[t];
          return (
            <li key={t}>
              <button
                type="button"
                aria-pressed={!off}
                title={`${TYPE_LABEL[t]}${n !== undefined ? ` · ${n}` : ""} — ${off ? "hidden, click to show" : "shown, click to hide"}`}
                onClick={() => toggle(t)}
                className={cn("group flex h-9 w-11 flex-col items-center justify-center rounded-[2px] transition-colors hover:bg-film-lift focus-visible:ring-2 focus-visible:ring-pencil", off && "opacity-35")}
              >
                <Glyph shape={SHAPE[t]} size={presentation ? 18 : 15} stroke={t === "BANK_ACCOUNT" || t === "CRYPTO_WALLET" ? INK.blue : INK.ink} className={cn(off && "[&>path]:stroke-ink-faint")} />
                {n !== undefined && <span className="figure mt-0.5 text-[9px] leading-none text-ink-faint">{n}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto flex flex-col items-center gap-2 pb-1" aria-label="Line key">
        <span className="note text-[9px] uppercase tracking-wider text-ink-faint">Line</span>
        <div title="Solid: structured record or checksum-validated"><LineSample style="solid" width={28} /></div>
        <div title="Dashed: extracted from text by rules"><LineSample style="dashed" width={28} /></div>
        <div title="Dotted: inferred by a model"><LineSample style="dotted" width={28} /></div>
        <div title="Blue: money"><LineSample style="solid" ink={INK.blue} width={28} /></div>
      </div>
    </nav>
  );
}
