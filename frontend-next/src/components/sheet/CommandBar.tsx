"use client";
/** ⌘K: jump to any entity, lens, or ask the investigator. Index cell and chart position are one deep link. */
import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSheet } from "@/lib/store";
import { Glyph } from "./KeyRail";
import { SHAPE, TYPE_LABEL } from "@/lib/notation";
import { Search, CornerDownLeft } from "lucide-react";

const LENSES = [
  ["/", "Overview"], ["/chart", "Chart"], ["/players", "Key players & communities"], ["/alerts", "Alerts register"],
  ["/map", "Map & timeline"], ["/investigator", "Investigator"], ["/sources", "Sources & ingestion"], ["/ledger", "Evidence ledger"],
] as const;

export default function CommandBar() {
  const open = useSheet((s) => s.commandOpen);
  const setOpen = useSheet((s) => s.setCommandOpen);
  const select = useSheet((s) => s.select);
  const setPresentation = useSheet((s) => s.setPresentation);
  const presentation = useSheet((s) => s.presentation);
  const [q, setQ] = useState("");
  const router = useRouter();
  const { data: hits } = useQuery({ queryKey: ["cmd", q], queryFn: () => api.entities({ q, limit: 12 }).then((p) => p.items), enabled: open && q.trim().length >= 2, staleTime: 10_000 });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(!open); }
      if (e.key === "p" && (e.metaKey || e.ctrlKey) && e.shiftKey) { e.preventDefault(); setPresentation(!presentation); }
    };
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen, presentation, setPresentation]);

  const go = (path: string) => { setOpen(false); setQ(""); router.push(path); };

  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Command bar" className="fixed inset-0 z-50 grid place-items-start justify-center bg-ink/20 pt-[12vh] backdrop-blur-[1.5px]" overlayClassName="">
      <div className="note-paper w-[min(40rem,92vw)] overflow-hidden border border-ink">
        <div className="flex items-center gap-2 border-b border-rule-strong px-3">
          <Search className="h-4 w-4 text-ink-faint" aria-hidden="true" />
          <Command.Input value={q} onValueChange={setQ} placeholder="Find a person, phone, vehicle, account… or type a question" className="h-11 w-full bg-transparent text-[var(--fs-lead)] outline-none placeholder:text-ink-faint" />
          <kbd className="label rounded-[2px] border border-rule-strong px-1.5 py-0.5 text-ink-faint">esc</kbd>
        </div>
        <Command.List className="max-h-[52vh] overflow-y-auto p-1.5">
          <Command.Empty className="px-3 py-6 text-center note">{q.length < 2 ? "Type at least two characters." : "No entity matches. Press Enter to ask the investigator."}</Command.Empty>
          {hits && hits.length > 0 && (
            <Command.Group heading={<span className="label px-2">Entities</span>}>
              {hits.map((n) => (
                <Command.Item key={n.id} value={`${n.label} ${n.id}`} onSelect={() => { select(n.id); go(`/chart?focus=${n.id}`); }} className="flex cursor-pointer items-center gap-3 rounded-[2px] px-2 py-1.5 aria-selected:bg-film-deep">
                  <Glyph shape={SHAPE[n.type]} size={14} />
                  <span className="flex-1 truncate">{n.label}{n.aliases?.length ? <span className="text-ink-faint"> @ {n.aliases.join(", ")}</span> : null}</span>
                  <span className="label text-ink-faint">{TYPE_LABEL[n.type]}</span>
                  {n.priority > 0 && <span className="figure text-[var(--fs-note)] text-pencil">{n.priority.toFixed(2)}</span>}
                </Command.Item>
              ))}
            </Command.Group>
          )}
          {q.trim().length >= 4 && (
            <Command.Group heading={<span className="label px-2">Ask</span>}>
              <Command.Item value={`ask ${q}`} onSelect={() => go(`/investigator?q=${encodeURIComponent(q)}`)} className="flex cursor-pointer items-center gap-3 rounded-[2px] px-2 py-1.5 aria-selected:bg-film-deep">
                <CornerDownLeft className="h-4 w-4 text-ink-faint" aria-hidden="true" /><span className="truncate">Ask the investigator: “{q}”</span>
              </Command.Item>
            </Command.Group>
          )}
          <Command.Group heading={<span className="label px-2">Lenses</span>}>
            {LENSES.map(([p, l]) => <Command.Item key={p} value={`lens ${l}`} onSelect={() => go(p)} className="cursor-pointer rounded-[2px] px-2 py-1.5 aria-selected:bg-film-deep">{l}</Command.Item>)}
            <Command.Item value="presentation mode" onSelect={() => { setPresentation(!presentation); setOpen(false); }} className="cursor-pointer rounded-[2px] px-2 py-1.5 aria-selected:bg-film-deep">{presentation ? "Leave" : "Enter"} presentation mode <span className="label ml-2 text-ink-faint">ctrl+shift+p</span></Command.Item>
          </Command.Group>
        </Command.List>
      </div>
    </Command.Dialog>
  );
}
