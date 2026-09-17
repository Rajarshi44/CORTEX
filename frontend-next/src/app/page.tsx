"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import Image from "next/image";
import { cn } from "@/lib/utils";

const RevealStagger = ({ children, delay = 0, className }: { children: React.ReactNode, delay?: number, className?: string }) => {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
};

export default function Landing() {
  return (
    <main className="min-h-dvh bg-background text-foreground selection:bg-amber selection:text-amber-deep">
      {/* ------------------------------------------------------------------ Header */}
      <header className="fixed top-0 left-0 right-0 z-50 flex h-20 items-center justify-between px-6 md:px-12 backdrop-blur-md bg-background/80 border-b border-rule">
        <span className="sign text-xl tracking-tight text-ink">CORTEX</span>
        <nav className="flex items-center gap-6">
          <Link href="/login" className="label text-ink-soft hover:text-ink transition-colors">Documentation</Link>
          <Link
            href="/login"
            className="label text-film bg-ink px-5 py-2.5 rounded-[4px] hover:bg-ink-soft transition-colors active:scale-95"
          >
            Open Console
          </Link>
        </nav>
      </header>

      {/* ------------------------------------------------------------------ Hero */}
      <section className="relative pt-32 pb-20 md:pt-48 md:pb-32 px-6 md:px-12 max-w-[1400px] mx-auto grid lg:grid-cols-[1fr_1.1fr] gap-16 lg:gap-24 items-center">
        <div className="max-w-[34rem]">
          <RevealStagger>
            <span className="label text-pencil mb-4 block">Operation Saltwater</span>
            <h1 className="sign text-5xl md:text-7xl text-ink mb-6">
              Follow the thread through fragmented records.
            </h1>
            <p className="text-[length:var(--fs-lead)] text-ink-faint mb-10 max-w-[30ch]">
              An enterprise-grade criminal network analysis console built on a dynamic ontology engine.
            </p>
            <div className="flex items-center gap-6">
              <Link
                href="/login"
                className="label text-film bg-ink px-6 py-4 rounded-[4px] hover:bg-ink-soft transition-colors active:scale-[0.98] flex items-center gap-2"
              >
                Launch Platform <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </RevealStagger>
        </div>

        <RevealStagger delay={0.2} className="relative aspect-[4/3] w-full rounded-[4px] overflow-hidden bg-film-lift border border-rule">
          <Image 
            src="/cortex_hero.jpg" 
            alt="Conceptual network graph showing analytical focus" 
            fill 
            className="object-cover opacity-90"
            priority
          />
        </RevealStagger>
      </section>

      {/* ------------------------------------------------------------------ Features Bento */}
      <section className="py-24 md:py-32 bg-film-lift border-t border-rule">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12">
          
          <RevealStagger className="mb-16 md:mb-24">
            <h2 className="sign text-4xl md:text-5xl max-w-[20ch]">
              A resilient, extensible, and mathematically rigorous foundation.
            </h2>
          </RevealStagger>

          <div className="grid md:grid-cols-2 lg:grid-cols-12 gap-6 md:gap-8">
            
            {/* Feature 1: Dynamic Schema */}
            <RevealStagger delay={0.1} className="lg:col-span-7 flex flex-col justify-between p-8 md:p-12 border border-rule rounded-[4px] bg-film group hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] transition-shadow duration-500">
              <div className="mb-12">
                <span className="label text-blue-deep mb-3 block">Architecture</span>
                <h3 className="sign text-3xl mb-4">Dynamic Entity Schema</h3>
                <p className="text-[length:var(--fs-body)] text-ink-faint max-w-[45ch]">
                  Built on a Gotham-style property bag model. We bypassed rigid SQL columns, enabling analysts to ingest entirely new node types (like Cryptocurrency Wallets or Maritime Vessels) via simple JSON config without database migrations.
                </p>
              </div>
              <div className="relative aspect-[16/9] w-full overflow-hidden border border-rule rounded-[2px]">
                <Image src="/cortex_schema.jpg" alt="Dynamic Schema Abstraction" fill className="object-cover group-hover:scale-105 transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]" />
              </div>
            </RevealStagger>

            {/* Feature 2: Proximity Risk */}
            <RevealStagger delay={0.2} className="lg:col-span-5 flex flex-col justify-between p-8 md:p-12 border border-rule rounded-[4px] bg-film group hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] transition-shadow duration-500">
              <div className="mb-12">
                <span className="label text-amber-deep mb-3 block">Analytics</span>
                <h3 className="sign text-3xl mb-4">Proximity Risk Engine</h3>
                <p className="text-[length:var(--fs-body)] text-ink-faint max-w-[35ch]">
                  A 3-hop recursive breadth-first search logic identifying &ldquo;clean&rdquo; individuals surrounded by severe criminal activity, applying geometric decay (1.0 → 0.3 → 0.09) and multiplicative channel amplification.
                </p>
              </div>
              <div className="relative aspect-[4/3] w-full overflow-hidden border border-rule rounded-[2px]">
                 <Image src="/cortex_proximity.jpg" alt="Proximity Risk Abstraction" fill className="object-cover group-hover:scale-105 transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]" />
              </div>
            </RevealStagger>

            {/* Feature 3: Governance Gate */}
            <RevealStagger delay={0.3} className="lg:col-span-5 flex flex-col justify-between p-8 md:p-12 border border-rule rounded-[4px] bg-film group hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] transition-shadow duration-500">
              <div className="mb-12">
                <span className="label text-pencil mb-3 block">Compliance</span>
                <h3 className="sign text-3xl mb-4">Governance Gates</h3>
                <p className="text-[length:var(--fs-body)] text-ink-faint max-w-[35ch]">
                  Unverified intelligence should not masquerade as fact. High-severity model flags instantly censor entity labels in the UI until human analysts manually review and acknowledge them.
                </p>
              </div>
              <div className="relative aspect-[4/3] w-full overflow-hidden border border-rule rounded-[2px]">
                 <Image src="/cortex_governance.jpg" alt="Governance Gate Abstraction" fill className="object-cover group-hover:scale-105 transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]" />
              </div>
            </RevealStagger>

            {/* Feature 4: Global Search */}
            <RevealStagger delay={0.4} className="lg:col-span-7 flex flex-col justify-center p-8 md:p-12 border border-rule rounded-[4px] bg-ink text-film group hover:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-shadow duration-500">
              <div className="max-w-[40ch]">
                <span className="label text-film mb-3 block">Interface</span>
                <h3 className="sign text-3xl mb-4">Global Command Search</h3>
                <p className="text-[length:var(--fs-body)] text-film/70 mb-8">
                  A unified OSINT search experience (<kbd className="font-mono text-xs border border-film/30 px-1.5 py-0.5 rounded-[2px]">Ctrl+K</kbd>) scanning every graph entity, document, and alert simultaneously.
                </p>
                <Link href="/login" className="inline-flex items-center gap-2 label text-film hover:text-amber transition-colors underline decoration-film/30 hover:decoration-amber underline-offset-4">
                  Experience the interface <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </RevealStagger>

          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ Proof Metrics */}
      <section className="py-24 border-t border-rule bg-background">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12">
          <RevealStagger className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-16">
            <div>
              <dt className="figure text-5xl font-semibold tracking-tight text-ink mb-2">10/10</dt>
              <dd className="text-[length:var(--fs-note)] text-ink-soft max-w-[20ch]">key players successfully identified against benchmark truth data.</dd>
            </div>
            <div>
              <dt className="figure text-5xl font-semibold tracking-tight text-ink mb-2">&lt;20s</dt>
              <dd className="text-[length:var(--fs-note)] text-ink-soft max-w-[20ch]">to resolve 3,954 entities and 4,191 relationships on standard hardware.</dd>
            </div>
            <div>
              <dt className="figure text-5xl font-semibold tracking-tight text-ink mb-2">3-Hop</dt>
              <dd className="text-[length:var(--fs-note)] text-ink-soft max-w-[20ch]">geometric decay resolution across varied communication channels.</dd>
            </div>
            <div>
              <dt className="figure text-5xl font-semibold tracking-tight text-ink mb-2">10</dt>
              <dd className="text-[length:var(--fs-note)] text-ink-soft max-w-[20ch]">verified public source connectors including eCourts, NIA, and ICIJ.</dd>
            </div>
          </RevealStagger>
        </div>
      </section>

      {/* ------------------------------------------------------------------ Footer */}
      <footer className="border-t border-rule py-12 bg-film-lift">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 flex flex-col md:flex-row justify-between items-center gap-6">
          <span className="sign text-xl text-ink">CORTEX</span>
          <p className="label text-ink-faint">Smart India Hackathon 2024</p>
        </div>
      </footer>
    </main>
  );
}
