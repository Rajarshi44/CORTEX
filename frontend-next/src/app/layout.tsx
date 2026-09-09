import type { Metadata, Viewport } from "next";
import { Barlow, Barlow_Condensed, Stardos_Stencil } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const barlow = Barlow({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-barlow", display: "swap" });
const condensed = Barlow_Condensed({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-barlow-condensed", display: "swap" });
const stencil = Stardos_Stencil({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-stencil", display: "swap" });

export const metadata: Metadata = {
  title: { default: "SUTRA", template: "%s · SUTRA" },
  description: "Criminal network analysis console. Follow the thread through fragmented records.",
  applicationName: "SUTRA",
};
export const viewport: Viewport = { themeColor: "#ededea", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${barlow.variable} ${condensed.variable} ${stencil.variable}`} suppressHydrationWarning>
      <body className="min-h-dvh">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
