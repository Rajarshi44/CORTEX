"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSheet } from "@/lib/store";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Search, Presentation, LogOut } from "lucide-react";

const LENSES = [
  ["/overview", "Overview"], ["/chart", "Chart"], ["/players", "Players"], ["/alerts", "Alerts"],
  ["/novelty", "Novel Intel"], ["/map", "Map"], ["/investigator", "Investigator"], ["/sources", "Sources"], ["/ledger", "Ledger"],
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
    <header className="pointer-events-auto flex items-center gap-4 border-b border-rule bg-film-lift/90 backdrop-blur-sm px-4 py-2">
      <Link
        href="/overview"
        className="flex items-center gap-2"
        aria-label="CORTEX home"
      >
        <span className="sign text-lg tracking-tight text-ink">CORTEX</span>
      </Link>
      
      <nav aria-label="Lenses" className="scrollbar-hide flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {LENSES.map(([p, l]) => {
          const active = path === p || path.startsWith(p + "/");
          return (
            <Link
              key={p}
              href={p}
              aria-current={active ? "page" : undefined}
              className={cn(
                "label px-3 py-1.5 rounded-[4px] transition-colors",
                active ? "bg-ink text-film" : "text-ink-soft hover:bg-film-deep"
              )}
            >
              {l}
            </Link>
          );
        })}
      </nav>

      <div className="flex shrink-0 items-center gap-2">
        <button 
          type="button" 
          onClick={() => setOpen(true)} 
          className="flex shrink-0 items-center gap-2 whitespace-nowrap border border-rule bg-film px-3 py-1.5 rounded-[4px] text-ink-soft hover:border-ink hover:text-ink transition-colors shadow-sm" 
          aria-keyshortcuts="Control+K" 
          aria-label="Find or ask"
        >
          <Search className="h-4 w-4" aria-hidden="true" />
          <span className="hidden text-[length:var(--fs-note)] lg:inline">Find or ask</span>
          <kbd className="hidden font-mono text-[10px] text-ink-faint xl:inline px-1 border border-rule rounded-[2px]">Ctrl K</kbd>
        </button>
        
        <button 
          type="button" 
          onClick={() => setPresentation(!presentation)} 
          aria-pressed={presentation} 
          className={cn(
            "flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-1.5 rounded-[4px] text-[length:var(--fs-note)] transition-colors",
            presentation ? "bg-amber text-amber-deep" : "text-ink-soft hover:bg-film"
          )} 
          title="Presentation mode: larger type, thinner margins. Data unchanged."
        >
          <Presentation className="h-4 w-4" aria-hidden="true" />
          <span className="hidden lg:inline">{presentation ? "Presenting" : "Present"}</span>
        </button>
        
        {user && (
          <button 
            type="button" 
            onClick={() => { api.logout(); setUser(null); router.push("/login"); }} 
            className="flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-1.5 rounded-[4px] text-[length:var(--fs-note)] text-ink-soft hover:bg-pencil-wash hover:text-pencil transition-colors" 
            title={`Signed in as ${user.username} (${user.role})`}
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            <span className="hidden lg:inline">{user.username}</span>
          </button>
        )}
      </div>
    </header>
  );
}
