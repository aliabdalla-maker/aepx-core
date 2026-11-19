import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Providers } from "./providers";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "Agentic Antivirus",
  description: "Endpoint protection, detection and response with governed AI investigation.",
  manifest: `${BASE}/manifest.webmanifest`,
  icons: { icon: `${BASE}/icons/icon.svg`, apple: `${BASE}/icons/apple-touch-icon.png` },
};
export const viewport: Viewport = { themeColor: "#17212b", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr" data-theme="system">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
