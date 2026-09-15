"use client";
/** The drawing's title block, bottom-right, as on any drafted sheet. Facts only. */
import { Fragment } from "react";
import { useSheet } from "@/lib/store";
import { useSummary } from "@/lib/queries";
import { format } from "date-fns";

export default function TitleBlock({ sheet, lens }: { sheet?: string; lens: string }) {
  const user = useSheet((s) => s.user);
  const { data } = useSummary();
  const s = data?.summary;
  const rows: [string, string][] = [
    ["Sheet", sheet ?? data?.sheet?.title ?? "—"],
    ["Code", data?.sheet?.code ?? "—"],
    ["Lens", lens],
    ["Entities", s ? s.nodes.toLocaleString("en-IN") : "—"],
    ["Relations", s ? s.edges.toLocaleString("en-IN") : "—"],
    ["Analyst", user ? `${user.full_name || user.username} · ${user.role}` : "—"],
    ["Computed", data?.computed_at ? format(new Date(data.computed_at), "dd MMM yyyy HH:mm") : "—"],
  ];
  return (
    <aside aria-label="Title block" className="pointer-events-auto select-none border border-ink bg-film-lift/95 text-ink shadow-[0_1px_0_var(--rule-strong)]">
      <div className="flex items-baseline gap-3 border-b border-ink px-3 py-1.5">
        <span className="stencil text-[length:var(--fs-title)] font-bold leading-none">CORTEX</span>
        <span className="label text-ink-faint">Network analysis</span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 px-3 py-1.5 text-[length:var(--fs-note)] leading-[1.5]">
        {rows.map(([k, v]) => (<Fragment key={k}><dt className="label text-ink-faint">{k}</dt><dd className="figure truncate text-ink">{v}</dd></Fragment>))}
      </dl>
    </aside>
  );
}
