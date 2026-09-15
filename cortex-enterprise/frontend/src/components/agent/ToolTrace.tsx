"use client";
/**
 * The agent's working, shown as it happens.
 *
 * An analyst is not going to trust an answer they cannot audit, and a judge is not going to
 * believe an agent they cannot watch. Every retrieval appears here the moment it is issued, with
 * its arguments and what came back, so the answer arrives with its own provenance attached.
 */
import { useState } from "react";
import { ChevronRight, Check, X, Loader2 } from "lucide-react";
import type { ToolCall } from "@/lib/agent";
import { cn } from "@/lib/utils";

/** Retrieval versus drawing: the reader should see at a glance which calls fetched facts. */
const RENDER_TOOLS = new Set(["show_chart", "show_network", "show_table", "show_timeline", "highlight_on_chart"]);
const EXTERNAL_TOOLS = new Set(["web_search", "read_url", "crime_news", "screen_sanctions", "corporate_registry", "offshore_leaks"]);

function argSummary(input: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(input || {})) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) continue;
    const s = Array.isArray(v) ? `${v.length} item${v.length === 1 ? "" : "s"}` : String(v);
    parts.push(`${k}: ${s.length > 44 ? s.slice(0, 43) + "…" : s}`);
    if (parts.length >= 4) break;
  }
  return parts.join(" · ");
}

export default function ToolTrace({ calls, running }: { calls: ToolCall[]; running: boolean }) {
  const [open, setOpen] = useState(false);
  if (!calls.length) return null;
  const done = calls.filter((c) => c.done).length;
  const failed = calls.filter((c) => c.done && c.ok === false).length;
  const external = calls.some((c) => EXTERNAL_TOOLS.has(c.name));
  const ms = calls.reduce((s, c) => s + (c.ms ?? 0), 0);

  return (
    <div className="my-2 border border-rule-strong bg-film-deep/50">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
              className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-film-deep">
        <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 text-ink-faint transition-transform", open && "rotate-90")} aria-hidden="true" />
        <span className="label label-ink shrink-0">
          {running && done < calls.length ? "Working" : "Method"}
        </span>
        <span className="note min-w-0 flex-1 truncate">
          {running && done < calls.length
            ? calls[calls.length - 1]?.label
            : `${calls.length} retrieval${calls.length === 1 ? "" : "s"}${failed ? `, ${failed} failed` : ""}${external ? ", including external sources" : ""}`}
        </span>
        {ms > 0 && <span className="figure shrink-0 text-[length:var(--fs-note)] text-ink-faint">{(ms / 1000).toFixed(1)}s</span>}
      </button>

      {open && (
        <ol className="border-t border-rule">
          {calls.map((c, i) => (
            <li key={c.id + i} className="flex items-start gap-2 border-b border-rule px-2.5 py-1.5 last:border-b-0">
              <span className="mt-[3px] shrink-0">
                {!c.done ? <Loader2 className="h-3 w-3 animate-spin text-ink-faint" aria-label="running" />
                  : c.ok === false ? <X className="h-3 w-3 text-pencil" aria-label="failed" />
                  : <Check className="h-3 w-3 text-green" aria-label="done" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-baseline gap-x-1.5 leading-snug">
                  <span className="font-medium">{c.label}</span>
                  <code className="figure text-[10px] text-ink-faint">
                    {c.name}{RENDER_TOOLS.has(c.name) ? " · draws" : EXTERNAL_TOOLS.has(c.name) ? " · external" : ""}
                  </code>
                </p>
                {argSummary(c.input) && <p className="note truncate text-ink-faint">{argSummary(c.input)}</p>}
                {c.done && c.summary && (
                  <p className={cn("note border-l border-rule pl-2", c.ok === false ? "text-pencil" : "text-ink-soft")}>{c.summary}</p>
                )}
              </div>
              {c.ms !== undefined && <span className="figure shrink-0 text-[10px] text-ink-faint">{c.ms}ms</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
