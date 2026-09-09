import type { Metadata, Viewport } from "next";
import { Archivo, Archivo_Narrow } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

// Indian Railways signage is set in industrial grotesques: wide enough to read across a
// concourse, narrow enough to fit a service name in a column. Archivo carries both roles from
// one superfamily, so the board and the timetable are the same voice at two widths.
const archivo = Archivo({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-archivo", display: "swap" });
const narrow = Archivo_Narrow({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-archivo-narrow", display: "swap" });

export const metadata: Metadata = {
  title: { default: "CORTEX", template: "%s · CORTEX" },
  description: "Criminal network analysis console. Follow the thread through fragmented records.",
  applicationName: "CORTEX",
};
export const viewport: Viewport = { themeColor: "#141613", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} ${narrow.variable}`} suppressHydrationWarning>
      <body className="min-h-dvh">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
