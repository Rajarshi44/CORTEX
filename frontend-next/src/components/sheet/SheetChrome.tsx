"use client";
/** The sheet's fixed margins: lens tabs across the top-left, presentation toggle, sign-out. */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSheet } from "@/lib/store";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Search, Presentation, LogOut } from "lucide-react";

const LENSES = [
  ["/overview", "Overview"], ["/chart", "Chart"], ["/players", "Players"], ["/alerts", "Alerts"],
  ["/map", "Map"], ["/investigator", "Investigator"], ["/sources", "Sources"], ["/ledger", "Ledger"],
  ["/system", "System"],
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
      {/* The station nameplate: dark plate, amber rule under it, the way a platform sign is hung. */}
      <Link
        href="/overview"
        className="board mr-2 flex items-baseline gap-2 px-2.5 py-1 shadow-[inset_0_-2px_0_var(--amber)]"
        aria-label="CORTEX home"
      >
        <span className="stencil text-[length:var(--fs-lead)] leading-none board-white">CORTEX</span>
      </Link>
      <nav aria-label="Lenses" className="scrollbar-hide flex min-w-0 items-center overflow-x-auto">
        {LENSES.map(([p, l]) => {
          const active = path === p || path.startsWith(p + "/");
          return (
            <Link
              key={p}
              href={p}
              aria-current={active ? "page" : undefined}
              /* the active lens is the lit platform: amber underline, ink type */
              className={cn(
                "label shrink-0 px-2.5 py-1.5 transition-colors hover:text-ink",
                active ? "label-ink shadow-[inset_0_-2px_0_var(--amber-deep)]" : "text-ink-soft",
              )}
            >
              {l}
            </Link>
          );
        })}
      </nav>
      {/* Controls collapse to their glyphs as the concourse narrows; nothing wraps, nothing is lost. */}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <button type="button" onClick={() => setOpen(true)} className="flex shrink-0 items-center gap-2 whitespace-nowrap border border-rule-strong bg-film-lift px-2.5 py-1 text-ink-soft hover:border-ink hover:text-ink" aria-keyshortcuts="Control+K" aria-label="Find or ask">
          <Search className="h-3.5 w-3.5" aria-hidden="true" /><span className="hidden text-[length:var(--fs-note)] lg:inline">Find or ask</span><kbd className="label hidden text-ink-faint xl:inline">ctrl k</kbd>
        </button>
        <button type="button" onClick={() => setPresentation(!presentation)} aria-pressed={presentation} className={cn("flex shrink-0 items-center gap-1.5 whitespace-nowrap px-2.5 py-1 text-[length:var(--fs-note)] hover:bg-film-lift", presentation ? "text-amber-deep" : "text-ink-soft")} title="Presentation mode: larger type, thinner margins. Data unchanged.">
          <Presentation className="h-3.5 w-3.5" aria-hidden="true" /><span className="hidden lg:inline">{presentation ? "Presenting" : "Present"}</span>
        </button>
        {user && (
          <button type="button" onClick={() => { api.logout(); setUser(null); router.push("/login"); }} className="flex shrink-0 items-center gap-1.5 whitespace-nowrap px-2.5 py-1 text-[length:var(--fs-note)] text-ink-soft hover:bg-film-lift hover:text-ink" title={`Signed in as ${user.username} (${user.role})`}>
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" /><span className="hidden lg:inline">{user.username}</span>
          </button>
        )}
      </div>
    </header>
  );
}
