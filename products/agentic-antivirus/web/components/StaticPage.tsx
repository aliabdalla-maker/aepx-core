import Link from "next/link";
import type { ReactNode } from "react";

export function StaticPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main id="main" className="main" style={{ maxWidth: "46rem", margin: "2rem auto" }}>
      <p><Link href="/">Agentic Antivirus</Link></p>
      <h1>{title}</h1>
      {children}
    </main>);
}
