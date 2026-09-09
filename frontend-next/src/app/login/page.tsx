"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useSheet } from "@/lib/store";
import { Glyph, LineSample } from "@/components/sheet/KeyRail";
import { INK } from "@/lib/notation";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const setUser = useSheet((s) => s.setUser);
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { const u = await api.login(username, password); setUser(u); router.replace(params.get("next") || "/"); }
    catch (ex) { setErr(ex instanceof ApiError && ex.status === 401 ? "Username or password is wrong." : "The analysis service is not reachable. Start the backend on port 8000 and try again."); }
    finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="note-paper w-[min(26rem,92vw)] border border-ink p-6" aria-describedby={err ? "login-err" : undefined}>
      <h1 className="stencil text-[var(--fs-sheet)] font-bold leading-none">SUTRA</h1>
      <p className="mt-1 text-ink-soft">Sign in to open the sheet.</p>
      <label className="mt-6 block">
        <span className="label">Username</span>
        <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className="mt-1 h-10 w-full border border-rule-strong bg-film px-3 text-[var(--fs-lead)] focus:border-ink" required />
      </label>
      <label className="mt-3 block">
        <span className="label">Password</span>
        <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 h-10 w-full border border-rule-strong bg-film px-3 text-[var(--fs-lead)] focus:border-ink" required />
      </label>
      {err && <p id="login-err" role="alert" className="mt-3 border-l border-pencil pl-2 text-[var(--fs-body)] text-pencil">{err}</p>}
      <button type="submit" disabled={busy} className="mt-5 h-10 w-full bg-ink text-[var(--fs-lead)] font-semibold text-film hover:bg-pencil disabled:opacity-50">{busy ? "Signing in…" : "Open sheet"}</button>
      <p className="mt-4 note">Demo accounts: <span className="figure">analyst / analyst@123</span> · <span className="figure">admin / admin@123</span></p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="sheet-ground grid min-h-dvh grid-cols-1 lg:grid-cols-[1.2fr_1fr]">
      <section className="hidden lg:flex flex-col justify-between border-r border-rule-strong p-10">
        <div>
          <p className="label">Ministry of Home Affairs · NCRB · SIH 26189</p>
          <h2 className="mt-8 max-w-[18ch] text-[var(--fs-monument)] font-semibold leading-[0.95] tracking-tight text-ink">Follow the thread through fragmented records.</h2>
          <p className="mt-6 max-w-[52ch] text-[var(--fs-lead)] text-ink-soft">FIRs, call records, bank transfers, surveillance notes and court judgments drawn as one link chart, in the analyst’s own notation, with the sentence that proves every line.</p>
        </div>
        <div className="grid max-w-md grid-cols-2 gap-x-8 gap-y-2 text-[var(--fs-note)] text-ink-soft" aria-label="Notation key">
          <div className="flex items-center gap-2"><Glyph shape="circle" /> person</div>
          <div className="flex items-center gap-2"><LineSample style="solid" /> structured record</div>
          <div className="flex items-center gap-2"><Glyph shape="square" /> organisation</div>
          <div className="flex items-center gap-2"><LineSample style="dashed" /> rule-extracted</div>
          <div className="flex items-center gap-2"><Glyph shape="diamond" /> phone</div>
          <div className="flex items-center gap-2"><LineSample style="dotted" /> model-inferred</div>
          <div className="flex items-center gap-2"><Glyph shape="hexagon" stroke={INK.blue} /> account</div>
          <div className="flex items-center gap-2"><LineSample style="solid" ink={INK.blue} /> money</div>
        </div>
      </section>
      <section className="grid place-items-center p-6"><Suspense><LoginForm /></Suspense></section>
    </main>
  );
}
