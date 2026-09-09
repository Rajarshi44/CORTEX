"use client";
/**
 * One uncut sheet. Every lens renders inside these margins; the selection, highlights and
 * scrubber survive navigation because they live in the store, not the page.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSheet } from "@/lib/store";
import { getToken } from "@/lib/api";
import { useMe } from "@/lib/queries";
import SheetChrome from "@/components/sheet/SheetChrome";
import CommandBar from "@/components/sheet/CommandBar";
import NotesDrawer from "@/components/sheet/NotesDrawer";
import { cn } from "@/lib/utils";

export default function SheetLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const presentation = useSheet((s) => s.presentation);
  const setUser = useSheet((s) => s.setUser);
  const { data: me, isError, isLoading } = useMe();

  useEffect(() => { if (!getToken()) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`); }, [router]);
  useEffect(() => { if (me) setUser(me); }, [me, setUser]);
  useEffect(() => { if (isError) router.replace("/login"); }, [isError, router]);

  if (isLoading && !me) {
    return <div className="sheet-ground grid h-dvh place-items-center"><p className="label text-ink-faint">Opening the sheet…</p></div>;
  }
  return (
    <div className={cn("sheet-plain flex h-dvh flex-col overflow-hidden", presentation && "presentation")}>
      <SheetChrome />
      <div className="relative flex min-h-0 flex-1">
        {children}
        <NotesDrawer />
      </div>
      <CommandBar />
    </div>
  );
}
