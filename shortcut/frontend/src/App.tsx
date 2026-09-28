import { useState } from "react";
import { HomePage } from "./pages/HomePage";
import { DashboardPage } from "./pages/DashboardPage";
import type { PageView } from "./types";

/** Orquestra apenas a troca entre as duas telas (sem lógica de negócio). */
export default function App() {
  const [view, setView] = useState<PageView>("home");

  if (view === "dashboard") {
    return <DashboardPage onNavigate={setView} />;
  }
  return <HomePage onNavigate={setView} />;
}
