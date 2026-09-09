"use client";
/**
 * The investigator lens: an agent that works the case in front of you.
 *
 * Ask in plain language. The agent plans, calls retrieval tools across the graph, the documents,
 * the public-record connectors and the open web, draws what it found, and writes the answer -
 * streaming the whole way, so the reasoning is visible rather than hidden behind a spinner.
 * Everything it asserts came through a tool call listed in the trace.
 */
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryState, parseAsString } from "nuqs";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CornerDownLeft, Square, RotateCcw, FileText, Globe, ArrowUp } from "lucide-react";
import { agentApi, streamAgent, type AgentEvent, type Citation, type HighlightNode, type ToolCall, type Visual } from "@/lib/agent";
import { useSheet } from "@/lib/store";
import Markdown from "@/components/Markdown";
import SheetFooter from "@/components/sheet/SheetFooter";
import { Glyph } from "@/components/sheet/KeyRail";
import VisualBlock from "@/components/agent/Visual";
import ToolTrace from "@/components/agent/ToolTrace";
import { SHAPE } from "@/lib/notation";
import { cn } from "@/lib/utils";

interface Turn {
  id: number;
  q: string;
  text: string;
  calls: ToolCall[];
  visuals: Visual[];
  highlights: HighlightNode[];
  citations: Citation[];
  provider?: string;
  model?: string;
  steps?: number;
  seconds?: number;
  running: boolean;
  error?: string;
  stopped?: boolean;
}

const FALLBACK_EXAMPLES = [
  "Who runs this network, and what makes you say so?",
  "Which communities are suspicious? Compare them in a table.",
  "How are the top two key players connected? Draw the path.",
  "What happens to the network if we remove the top broker?",
];

function Investigator() {
  const [initial, setInitial] = useQueryState("q", parseAsString);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [atBottom, setAtBottom] = useState(true);
  const setHighlights = useSheet((s) => s.setHighlights);
  const select = useSheet((s) => s.select);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  const { data: caps } = useQuery({ queryKey: ["agentCaps"], queryFn: agentApi.capabilities, staleTime: 300_000, retry: 1 });
  const running = turns.some((t) => t.running);

  const patch = useCallback((id: number, fn: (t: Turn) => Turn) => {
    setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)));
  }, []);

  const ask = useCallback((question: string) => {
    const s = question.trim();
    if (!s || abortRef.current) return;
    const id = nextId.current++;
    const history = turns.filter((t) => !t.error && t.text).slice(-4).map((t) => ({ question: t.q, answer: t.text }));
    setTurns((ts) => [...ts, { id, q: s, text: "", calls: [], visuals: [], highlights: [], citations: [], running: true }]);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const onEvent = (e: AgentEvent) => {
      switch (e.type) {
        case "start":
          patch(id, (t) => ({ ...t, provider: e.provider, model: e.model }));
          break;
        case "text":
          patch(id, (t) => ({ ...t, text: t.text + e.delta }));
          break;
        case "tool_call":
          patch(id, (t) => ({ ...t, calls: [...t.calls, { id: e.id, name: e.name, input: e.input, label: e.label, done: false }] }));
          break;
        case "tool_done":
          patch(id, (t) => ({
            ...t,
            calls: t.calls.map((c) => (c.id === e.id && !c.done ? { ...c, done: true, ms: e.ms, summary: e.summary, ok: e.ok } : c)),
          }));
          break;
        case "visual":
          patch(id, (t) => ({ ...t, visuals: [...t.visuals, e.visual] }));
          break;
        case "fallback":
          patch(id, (t) => ({ ...t, provider: e.to }));
          break;
        case "done":
          patch(id, (t) => ({
            ...t, running: false, text: e.answer || t.text, highlights: e.highlight_nodes,
            citations: e.citations, steps: e.steps, seconds: e.seconds,
            provider: (e.usage?.provider as string) ?? t.provider, model: (e.usage?.model as string) ?? t.model,
          }));
          if (e.highlights.nodes.length) setHighlights(e.highlights.nodes, e.answer.split("\n")[0]?.slice(0, 160) ?? "");
          break;
        case "error":
          patch(id, (t) => ({ ...t, running: false, error: e.message }));
          break;
      }
    };

    streamAgent(s, history, onEvent, ctrl.signal)
      .catch((err: Error) => {
        if (ctrl.signal.aborted) patch(id, (t) => ({ ...t, running: false, stopped: true }));
        else patch(id, (t) => ({ ...t, running: false, error: err.message }));
      })
      .finally(() => {
        abortRef.current = null;
        patch(id, (t) => ({ ...t, running: false, calls: t.calls.map((c) => (c.done ? c : { ...c, done: true, ok: false, summary: "interrupted" })) }));
      });
  }, [patch, setHighlights, turns]);

  const stop = () => { abortRef.current?.abort(); abortRef.current = null; };

  // A ?q= in the url (from the command bar or a link) asks its question once.
  useEffect(() => {
    if (!initial) return;
    ask(initial);
    setInitial(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  // Follow the stream, but stop following the moment the reader scrolls up to re-read something.
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const onScroll = () => setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (atBottom) listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: turns.length > 1 ? "smooth" : "auto" });
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (running) return;
    const s = q.trim();
    if (!s) return;
    setQ("");
    ask(s);
  };

  const examples = caps?.examples?.length ? caps.examples : FALLBACK_EXAMPLES;
  const noProvider = caps && !caps.llm;

  return (
    /* A column, not a row: the title block belongs under the sheet, the way every other lens
       lays it out. Nesting it beside the content was costing half the width. */
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="mx-auto flex w-full min-h-0 max-w-[1240px] flex-1 flex-col px-6 py-5">
        <Header caps={caps} />

        <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto py-4">
          {turns.length === 0 && (
            <Empty examples={examples} onPick={ask} disabled={!!noProvider} caps={caps} />
          )}

          <ol className="space-y-7">
            {turns.map((t, i) => (
              <li key={t.id} className="scroll-mt-4">
                <div className="flex items-baseline gap-2">
                  <span className="label shrink-0 text-ink-faint">Q · {String(i + 1).padStart(2, "0")}</span>
                  <h2 className="text-[var(--fs-lead)] font-semibold leading-snug">{t.q}</h2>
                </div>

                <div className="mt-2 border-l border-ink pl-3.5">
                  <ToolTrace calls={t.calls} running={t.running} />

                  {t.visuals.map((v, vi) => (
                    <VisualBlock key={vi} visual={v} index={vi} onPick={select} />
                  ))}

                  {t.text && <Markdown text={t.text} className="max-w-[74ch] text-[var(--fs-body)] leading-relaxed" />}

                  {t.running && !t.text && !t.calls.length && (
                    <p className="note animate-pulse">Reading the sheet…</p>
                  )}
                  {t.running && t.text && <span className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse bg-pencil align-text-bottom" aria-hidden="true" />}

                  {t.error && (
                    <p className="mt-1 border-l-2 border-pencil bg-pencil-wash px-2 py-1.5 text-pencil">{t.error}</p>
                  )}
                  {t.stopped && <p className="note mt-1 text-ink-faint">Stopped.</p>}

                  {!t.running && <Footer turn={t} onSelect={select} onHighlight={setHighlights} onFollowUp={ask} />}
                </div>
              </li>
            ))}
          </ol>
          <SheetFooter lens="Investigator" />
        </div>

        {!atBottom && turns.length > 0 && (
          <button type="button" onClick={() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" })}
                  className="note-paper absolute bottom-24 left-1/2 flex -translate-x-1/2 items-center gap-1 border border-rule-strong px-2 py-1 hover:border-ink">
            <ArrowUp className="h-3 w-3 rotate-180" aria-hidden="true" /><span className="label">Latest</span>
          </button>
        )}

        <form onSubmit={submit} className="note-paper flex items-end gap-2 border border-ink px-3 py-1.5">
          <textarea
            ref={inputRef} value={q} rows={1}
            onChange={(e) => {
              setQ(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 132)}px`;
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(e); } }}
            placeholder={noProvider ? "Set a model key to ask questions" : "Ask anything about this case — the agent will search, compute and draw"}
            aria-label="Question" disabled={!!noProvider}
            className="max-h-[132px] min-h-[38px] flex-1 resize-none self-center bg-transparent py-2 text-[var(--fs-lead)] outline-none placeholder:text-ink-faint disabled:opacity-50"
          />
          {running ? (
            <button type="button" onClick={stop} className="label mb-1.5 flex shrink-0 items-center gap-1 rounded-[2px] border border-ink px-2.5 py-1.5 hover:bg-film-deep">
              <Square className="h-3 w-3 fill-current" aria-hidden="true" /> Stop
            </button>
          ) : (
            <button type="submit" disabled={!q.trim() || !!noProvider}
                    className="label mb-1.5 shrink-0 rounded-[2px] bg-ink px-3 py-1.5 text-film hover:bg-pencil disabled:opacity-40">
              Ask
            </button>
          )}
        </form>
        <p className="note mt-1 flex flex-wrap items-center gap-x-3 text-ink-faint">
          <span>Enter to send · Shift+Enter for a new line</span>
          {caps?.tools?.length ? <span>{caps.tools.length} tools</span> : null}
          {caps?.web_tier ? <span className="flex items-center gap-1"><Globe className="h-3 w-3" aria-hidden="true" />web via {caps.web_tier}</span> : null}
        </p>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------ header
function Header({ caps }: { caps?: { llm: boolean; provider: { label: string; model: string } | null; providers: { key: string; label: string; available: boolean }[] } }) {
  return (
    <div className="border-b border-ink pb-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-[var(--fs-sheet)] font-semibold leading-none tracking-tight">Investigator</h1>
        {caps && (
          <p className="label text-ink-faint">
            {caps.llm && caps.provider ? <>agent · {caps.provider.label} <span className="figure normal-case tracking-normal">{caps.provider.model}</span></> : "no model configured"}
          </p>
        )}
      </div>
      <p className="mt-1 text-ink-soft">
        Ask in plain language. The agent searches the graph, the documents, the public-record connectors and the open web,
        then draws what it found. Every claim traces back to a retrieval you can open.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------------------ empty state
function Empty({ examples, onPick, disabled, caps }: {
  examples: string[]; onPick: (q: string) => void; disabled: boolean;
  caps?: { providers: { key: string; label: string; available: boolean }[]; tools: { name: string; description: string }[] };
}) {
  const [showTools, setShowTools] = useState(false);
  return (
    <div>
      {disabled && (
        <div className="mb-4 border-l-2 border-pencil bg-pencil-wash px-3 py-2">
          <p className="label label-ink">No model provider configured</p>
          <p className="mt-1 leading-snug">
            Add one key to <code className="figure bg-film-deep px-1">backend/.env</code> and restart the API:{" "}
            <code className="figure bg-film-deep px-1">CNA_GEMINI_API_KEY</code>,{" "}
            <code className="figure bg-film-deep px-1">CNA_NVIDIA_API_KEY</code> or{" "}
            <code className="figure bg-film-deep px-1">CNA_ANTHROPIC_API_KEY</code>. Tried in that order; whichever
            answers first takes the turn.
          </p>
          {caps?.providers && (
            <ul className="note mt-1.5 flex flex-wrap gap-x-3">
              {caps.providers.map((p) => (
                <li key={p.key}>{p.available ? "●" : "○"} {p.label}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className="label mb-2 text-ink-faint">Start here</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {examples.map((ex) => (
          <button key={ex} type="button" onClick={() => onPick(ex)} disabled={disabled}
                  className="note-paper flex items-center justify-between gap-3 px-3 py-2.5 text-left text-[var(--fs-body)] hover:border-ink disabled:opacity-40">
            <span>{ex}</span>
            <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
          </button>
        ))}
      </div>
      {caps?.tools?.length ? (
        <div className="mt-4">
          <button type="button" onClick={() => setShowTools((v) => !v)} className="label text-ink-faint hover:text-ink">
            {showTools ? "Hide" : "Show"} the {caps.tools.length} tools it can reach →
          </button>
          {showTools && (
            <ul className="mt-2 grid gap-x-5 gap-y-1 sm:grid-cols-2">
              {caps.tools.map((t) => (
                <li key={t.name} className="note flex gap-2 border-b border-rule pb-1">
                  <code className="figure shrink-0 text-ink">{t.name}</code>
                  <span className="min-w-0 flex-1 text-ink-faint">{t.description}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------------------ answer footer
function Footer({ turn, onSelect, onHighlight, onFollowUp }: {
  turn: Turn; onSelect: (id: string) => void;
  onHighlight: (ids: string[], note?: string) => void; onFollowUp: (q: string) => void;
}) {
  const docs = useMemo(() => turn.citations.filter((c) => c.kind === "document"), [turn.citations]);
  const webs = useMemo(() => turn.citations.filter((c) => c.kind === "web"), [turn.citations]);
  if (!turn.highlights.length && !turn.citations.length && !turn.steps) return null;

  return (
    <div className="mt-3 space-y-2 border-t border-rule pt-2">
      {turn.highlights.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="label shrink-0 text-ink-faint">Entities</span>
          {turn.highlights.slice(0, 14).map((n) => (
            <button key={n.id} type="button" onClick={() => onSelect(n.id)}
                    className="flex items-center gap-1 border border-rule-strong px-1.5 py-0.5 text-[var(--fs-note)] hover:border-ink">
              <Glyph shape={SHAPE[n.type]} size={11} />{n.label}
            </button>
          ))}
          {turn.highlights.length > 14 && <span className="note text-ink-faint">+{turn.highlights.length - 14} more</span>}
          <Link href={`/chart?focus=${turn.highlights[0].id}`}
                onClick={() => onHighlight(turn.highlights.map((h) => h.id), turn.q)}
                className="label text-pencil hover:underline">show on chart →</Link>
        </div>
      )}

      {(docs.length > 0 || webs.length > 0) && (
        <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
          {docs.length > 0 && (
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="label shrink-0 text-ink-faint"><FileText className="mr-1 inline h-3 w-3" aria-hidden="true" />Sources</span>
              {docs.slice(0, 5).map((c) => (
                <span key={c.id} title={c.snippet}
                      className="max-w-[240px] truncate border-b border-dotted border-rule-strong text-[var(--fs-note)] text-ink-soft">
                  {c.source_type} · {c.title}
                </span>
              ))}
            </div>
          )}
          {webs.length > 0 && (
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="label shrink-0 text-ink-faint"><Globe className="mr-1 inline h-3 w-3" aria-hidden="true" />Open web</span>
              {webs.slice(0, 4).map((c) => (
                <a key={c.id} href={c.id} target="_blank" rel="noreferrer noopener" title={c.snippet}
                   className="max-w-[220px] truncate text-[var(--fs-note)] text-blue underline decoration-dotted">
                  {c.title || c.id}
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="note text-ink-faint">
          {turn.steps ? `${turn.steps} step${turn.steps === 1 ? "" : "s"}` : null}
          {turn.calls.length ? ` · ${turn.calls.length} retrieval${turn.calls.length === 1 ? "" : "s"}` : null}
          {turn.seconds ? ` · ${turn.seconds}s` : null}
          {turn.provider ? ` · ${turn.provider}` : null}
        </p>
        <button type="button" onClick={() => onFollowUp(`Go deeper on that: ${turn.q}`)}
                className="label flex items-center gap-1 text-ink-faint hover:text-pencil">
          <RotateCcw className="h-3 w-3" aria-hidden="true" /> Go deeper
        </button>
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><Investigator /></Suspense>;
}
