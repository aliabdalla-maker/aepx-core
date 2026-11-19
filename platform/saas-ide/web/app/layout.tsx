import type { ReactNode } from "react";
import "./style.css";
export const metadata = { title: "AEP-X Hybrid IDE", description: "Governed agentic development workspace" };
export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
