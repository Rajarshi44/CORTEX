"use client";
/** The sheet's bottom rule on scrolling lenses: the title block laid flat, in the page flow, never over content. */
import { useSheet } from "@/lib/store";
import { useSummary } from "@/lib/queries";
import { format } from "date-fns";

export default function SheetFooter({ sheet, lens }: { sheet?: string; lens: string }) {
  const user = useSheet((s) => s.user);
  const { data } = useSummary();
  const s = data?.summary;
  const cells: [string, string][] = [
    ["Sheet", sheet ?? data?.sheet?.title ?? "—"], ["Code", data?.sheet?.code ?? "—"], ["Lens", lens],
    ["Entities", s ? s.nodes.toLocaleString("en-IN") : "—"], ["Relations", s ? s.edges.toLocaleString("en-IN") : "—"],
    ["Analyst", user ? `${user.full_name || user.username} · ${user.role}` : "—"],
    ["Computed", data?.computed_at ? format(new Date(data.computed_at), "dd MMM yyyy HH:mm") : "—"],
  ];
  return (
    <footer aria-label="Title block" className="mx-auto mt-10 w-full max-w-[1500px] px-6 pb-8">
      <div className="flex flex-wrap items-stretch border border-ink">
        <div className="flex items-center gap-3 border-r border-ink px-3 py-2"><span className="stencil text-[var(--fs-title)] font-bold leading-none">SUTRA</span><span className="label text-ink-faint">Network analysis</span></div>
        {cells.map(([k, v]) => <div key={k} className="flex min-w-[9rem] flex-col justify-center border-r border-rule-strong px-3 py-1.5 last:border-r-0"><span className="label text-ink-faint">{k}</span><span className="figure truncate text-[var(--fs-body)]">{v}</span></div>)}
      </div>
    </footer>
  );
}
