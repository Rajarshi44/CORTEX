"use client";
import type { EdgeView, NodeView } from "@/lib/types";
import { edgeCaption } from "./LinkChart";
import { lineStyleFor, TYPE_LABEL } from "@/lib/notation";
import { LineSample } from "@/components/sheet/KeyRail";

export default function HoverCaption({ hit, nodeById }: { hit: { node?: NodeView; edge?: EdgeView } | null; nodeById: Map<string, NodeView> }) {
  if (!hit || (!hit.node && !hit.edge)) return null;
  if (hit.edge) {
    const style = lineStyleFor(hit.edge.attrs?.extractor as string | undefined, hit.edge.confidence);
    return <div className="note-paper pointer-events-none flex items-center gap-2 px-3 py-1.5 text-[var(--fs-body)]"><LineSample style={style} width={26} /><span>{edgeCaption(hit.edge, nodeById)}</span></div>;
  }
  const n = hit.node!;
  return (
    <div className="note-paper pointer-events-none px-3 py-1.5 text-[var(--fs-body)]">
      <span className="font-semibold">{n.label}</span><span className="text-ink-faint"> · {TYPE_LABEL[n.type]}</span>
      {n.role && <span className="text-ink-soft"> · {n.role}</span>}
      {n.priority > 0 && <span className="figure text-pencil"> · {n.priority.toFixed(2)}</span>}
    </div>
  );
}
