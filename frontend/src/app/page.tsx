"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useApp } from "../context/AppContext";
import { ExecutiveDashboard } from "../components/ExecutiveDashboard";

export default function DashboardPage() {
  const router = useRouter();
  const { activeDataset, setSeededPrompt } = useApp();

  const handleNavigate = (tab: string) => {
    if (tab === "chat") {
      router.push("/ai-analyst");
    } else if (tab === "dashboard") {
      router.push("/");
    } else {
      router.push(`/${tab}`);
    }
  };

  return (
    <ExecutiveDashboard
      activeDataset={activeDataset}
      onNavigateToTab={handleNavigate}
      onSeedChatPrompt={setSeededPrompt}
    />
  );
}