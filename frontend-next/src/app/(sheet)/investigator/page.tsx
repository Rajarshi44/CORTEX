"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSheet } from "@/lib/store";
import Markdown from "@/components/Markdown";
import SheetFooter from "@/components/sheet/SheetFooter";
import { Glyph } from "@/components/sheet/KeyRail";
import { SHAPE } from "@/lib/notation";
import type { AssistantAnswer } from "@/lib/types";
import { CornerDownLeft } from "lucide-react";

type Turn = { q: string; a?: AssistantAnswer; error?: string; at: number };

function Investigator() {
  const [initial, setInitial] = useQueryState("q", parseAsString);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const setHighlights = useSheet((s) => s.setHighlights);
  const select = useSheet((s) => s.select);
  const listRef = useRef<HTMLDivElement>(null);
  const { data: caps } = useQuery({ queryKey: ["caps"], queryFn: api.assistantCaps, staleTime: 600_000 });
  const ask = useMutation({
    mutationFn: (question: string) => api.ask(question),
    onMutate: (question) => setTurns((t) => [...t, { q: question, at: Date.now() }]),
    onSuccess: (a) => { setTurns((t) => t.map((x, i) => i === t.length - 1 ? { ...x, a } : x)); if (a.highlights.nodes.length) setHighlights(a.highlights.nodes, a.answer.split("\n")[0]); },
    onError: (e: Error) => setTurns((t) => t.map((x, i) => i === t.length - 1 ? { ...x, error: e.message } : x)),
  });
  useEffect(() => { if (initial) { ask.mutate(initial); setInitial(null); } // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }); }, [turns]);
  const submit = (e: React.FormEvent) => { e.preventDefault(); const s = q.trim(); if (!s || ask.isPending) return; setQ(""); ask.mutate(s); };

  return (
    <div className="relative flex min-h-0 flex-1">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col px-6 py-6">
        <div className="border-b border-ink pb-2">
          <h1 className="text-[var(--fs-sheet)] font-semibold leading-none tracking-tight">Investigator</h1>
          <p className="mt-1 text-ink-soft">Ask in plain language. Every answer is retrieved from the chart and cites entities; {caps?.llm ? "a language model phrases it" : "phrasing is template-based on this machine (no language model key set)"}. Answers highlight what they used on the chart.</p>
        </div>
        <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto py-4">
          {turns.length === 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {(caps?.examples ?? ["Who are the key players?", "Show burner phones", "Path between Salim Qureshi and Rakesh Mehta", "What happens if we arrest Salim Qureshi?"]).map((ex) => (
                <button key={ex} type="button" onClick={() => ask.mutate(ex)} className="note-paper flex items-center justify-between gap-3 px-3 py-2.5 text-left text-[var(--fs-body)] hover:border-ink"><span>{ex}</span><CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" /></button>
              ))}
            </div>
          )}
          <ol className="space-y-5">
            {turns.map((t, i) => (
              <li key={t.at + i}>
                <p className="label text-ink-faint">Q · {String(i + 1).padStart(2, "0")}</p>
                <p className="text-[var(--fs-lead)] font-semibold">{t.q}</p>
                <div className="mt-2 border-l border-ink pl-3">
                  {!t.a && !t.error && <p className="note animate-pulse">Reading the chart…</p>}
                  {t.error && <p className="text-pencil">Could not answer: {t.error}</p>}
                  {t.a && (
                    <>
                      <p className="label text-ink-faint">{t.a.intent}{t.a.llm ? " · phrased by model" : " · template"}</p>
                      <Markdown text={t.a.answer} className="text-[var(--fs-body)]" />
                      {t.a.highlight_nodes.length > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {t.a.highlight_nodes.slice(0, 12).map((n) => <button key={n.id} type="button" onClick={() => select(n.id)} className="flex items-center gap-1 border border-rule-strong px-1.5 py-0.5 text-[var(--fs-note)] hover:border-ink"><Glyph shape={SHAPE[n.type]} size={11} />{n.label}</button>)}
                          <Link href={`/chart${t.a.highlight_nodes[0] ? `?focus=${t.a.highlight_nodes[0].id}` : ""}`} onClick={() => setHighlights(t.a!.highlights.nodes, t.a!.answer.split("\n")[0])} className="label text-pencil hover:underline">show on chart →</Link>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
        <form onSubmit={submit} className="note-paper flex items-center gap-2 border border-ink px-3">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Who does Vikram Naik call at night?" aria-label="Question" className="h-12 flex-1 bg-transparent text-[var(--fs-lead)] outline-none placeholder:text-ink-faint" />
          <button type="submit" disabled={ask.isPending || !q.trim()} className="label rounded-[2px] bg-ink px-3 py-1.5 text-film hover:bg-pencil disabled:opacity-40">Ask</button>
        </form>
      </div>
      <SheetFooter lens="Investigator" />
    </div>
  );
}
export default function Page() { return <Suspense><Investigator /></Suspense>; }
