"use client";
/** The sheet's fixed margins: lens tabs across the top-left, presentation toggle, sign-out. */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSheet } from "@/lib/store";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Search, Presentation, LogOut } from "lucide-react";

const LENSES = [
  ["/", "Overview"], ["/chart", "Chart"], ["/players", "Players"], ["/alerts", "Alerts"],
  ["/map", "Map"], ["/investigator", "Investigator"], ["/sources", "Sources"], ["/ledger", "Ledger"],
] as const;

export default function SheetChrome() {
  const path = usePathname();
  const router = useRouter();
  const setOpen = useSheet((s) => s.setCommandOpen);
  const presentation = useSheet((s) => s.presentation);
  const setPresentation = useSheet((s) => s.setPresentation);
  const user = useSheet((s) => s.user);
  const setUser = useSheet((s) => s.setUser);
  return (
    <header className="pointer-events-auto flex items-center gap-1 border-b border-rule-strong bg-film-deep/95 px-2 py-1">
      <Link href="/" className="stencil px-2 text-[var(--fs-lead)] font-bold text-ink" aria-label="SUTRA home">SUTRA</Link>
      <nav aria-label="Lenses" className="flex items-center">
        {LENSES.map(([p, l]) => {
          const active = p === "/" ? path === "/" : path.startsWith(p);
          return <Link key={p} href={p} aria-current={active ? "page" : undefined} className={cn("label rounded-[2px] px-2.5 py-1.5 transition-colors hover:text-ink", active ? "label-ink pencil-line" : "text-ink-faint")}>{l}</Link>;
        })}
      </nav>
      <div className="ml-auto flex items-center gap-1">
        <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-2 rounded-[2px] border border-rule-strong bg-film-lift px-2.5 py-1 text-ink-soft hover:border-ink hover:text-ink" aria-keyshortcuts="Control+K">
          <Search className="h-3.5 w-3.5" aria-hidden="true" /><span className="text-[var(--fs-note)]">Find or ask</span><kbd className="label text-ink-faint">ctrl k</kbd>
        </button>
        <button type="button" onClick={() => setPresentation(!presentation)} aria-pressed={presentation} className={cn("flex items-center gap-1.5 rounded-[2px] px-2.5 py-1 text-[var(--fs-note)] hover:bg-film-lift", presentation ? "text-pencil" : "text-ink-soft")} title="Presentation mode: larger type, thinner margins. Data unchanged.">
          <Presentation className="h-3.5 w-3.5" aria-hidden="true" />{presentation ? "Presenting" : "Present"}
        </button>
        {user && (
          <button type="button" onClick={() => { api.logout(); setUser(null); router.push("/login"); }} className="flex items-center gap-1.5 rounded-[2px] px-2.5 py-1 text-[var(--fs-note)] text-ink-soft hover:bg-film-lift hover:text-ink" title={`Signed in as ${user.username} (${user.role})`}>
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />{user.username}
          </button>
        )}
      </div>
    </header>
  );
}
