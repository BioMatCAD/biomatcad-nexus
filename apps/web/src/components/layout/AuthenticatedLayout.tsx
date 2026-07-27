import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <a href="#main-content" className="visually-hidden">
        Pular para o conteúdo principal
      </a>
      <TopBar />
      <div style={{ display: "flex", flex: 1 }}>
        <Sidebar />
        <main id="main-content" style={{ flex: 1, padding: "var(--space-6)" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
