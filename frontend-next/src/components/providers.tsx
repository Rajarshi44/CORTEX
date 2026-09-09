"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useState } from "react";
import { Toaster } from "sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
  }));
  return (
    <QueryClientProvider client={client}>
      <NuqsAdapter>{children}</NuqsAdapter>
      <Toaster
        position="bottom-left"
        toastOptions={{ className: "!bg-film-lift !text-ink !border !border-rule-strong !rounded-[2px] !shadow-none !font-sans", duration: 3200 }}
      />
    </QueryClientProvider>
  );
}
