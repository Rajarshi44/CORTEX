"use client";
/** One written line for every chart transition, read by assistive tech and usable as the presenter's script. */
import { useSheet } from "@/lib/store";

export default function Narrative() {
  const narrative = useSheet((s) => s.narrative);
  return (
    <p aria-live="polite" aria-atomic="true" className="pointer-events-none max-w-[48ch] text-[length:var(--fs-note)] italic leading-snug text-ink-soft">
      {narrative}
    </p>
  );
}
